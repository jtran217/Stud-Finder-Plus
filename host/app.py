"""Stud Mapper core: everything except the user interface.

StudApp takes camera frames and user actions (clicks, commands) and keeps the
stud map, calibration and laser state. Two front ends drive it:
  main.py  an OpenCV window with keyboard shortcuts
  web.py   a browser page (http://localhost:8000)
"""
import bisect
import threading
import time
from collections import deque

import cv2
import numpy as np

import laser
import vision
from serial_link import FakeLink, SerialLink

# ---- Edit these to match tonight's setup -----------------------------------
# Default scan-area size in inches (width, height): the distance between the
# tape crosses. The web page asks for it; it's saved in host/calib.json.
WALL_SIZE_IN = (24, 12)
# Inches from the tracked object's center to the stud finder's sensing point
# (+ = sensor is to the right of the object).
SENSOR_OFFSET_IN = 0.0
# Camera frames arrive a little late; shift frame timestamps back by this much.
CAMERA_LATENCY_S = 0.0
# Studs whose centers are closer than this are treated as the same stud.
MERGE_IN = 1.0
# A stud is two edges, one found sliding in from each side. Edges closer or
# farther apart than this aren't paired into one stud.
MIN_STUD_IN = 0.5
MAX_STUD_IN = 3.5
# Laser calibration sweeps the motor between these step positions (step 0 =
# where the motor was at power-up or the last Z). Widen if the laser doesn't
# reach both edges of the wall; narrow if it goes way past them.
LASER_STEP_RANGE = (-300, 300)
# ----------------------------------------------------------------------------

CORNER_NAMES = ["top-left", "top-right", "bottom-right", "bottom-left"]
HISTORY_S = 3.0
MAX_GAP_S = 0.3   # don't interpolate across gaps where the tracker was lost
VIEWS = ["video", "object mask", "laser mask"]


def corners_for(width, height):
    """Tape-cross positions in inches, order TL, TR, BR, BL."""
    return [(0, 0), (width, 0), (width, height), (0, height)]


class History:
    """Recent (time, finder_x) samples, for looking up x when an event arrives."""

    def __init__(self):
        self.t = deque()
        self.x = deque()

    def add(self, t, x):
        self.t.append(t)
        self.x.append(x)
        while self.t and self.t[0] < t - HISTORY_S:
            self.t.popleft()
            self.x.popleft()

    def x_at(self, t):
        ts = list(self.t)
        if not ts:
            return None
        i = bisect.bisect_left(ts, t)
        if i == 0:
            return self.x[0] if ts[0] - t < MAX_GAP_S else None
        if i == len(ts):
            return self.x[-1] if t - ts[-1] < MAX_GAP_S else None
        t0, t1 = ts[i - 1], ts[i]
        if t1 - t0 > MAX_GAP_S:
            return None
        x0, x1 = self.x[i - 1], self.x[i]
        return x0 + (x1 - x0) * (t - t0) / (t1 - t0)


class StudMap:
    def __init__(self, log=print):
        self.studs = []       # dicts: center, left, right, n
        self.open_x = None    # x of the first edge, waiting for the other side's
        self.log = log

    def handle(self, kind, x):
        # Each S1 is a stud edge (the LED came on while sliding in from one
        # side). S0 only means the finder was lifted or switched off: ignore it.
        if kind != "S1":
            return
        if self.open_x is None:
            self.open_x = x
            self.log(f"edge @ {x:.2f} in, waiting for the other side")
            return
        width = abs(x - self.open_x)
        if MIN_STUD_IN <= width <= MAX_STUD_IN:
            left, right = sorted((self.open_x, x))
            self.open_x = None
            self._add(left, right)
        else:
            # Same side twice, or a different stud: start over from this edge.
            self.log(f"edge @ {x:.2f} in doesn't pair with {self.open_x:.2f} in "
                     f"({width:.2f} in apart), starting over")
            self.open_x = x

    def _add(self, left, right):
        center = (left + right) / 2
        for s in self.studs:
            if abs(s["center"] - center) < MERGE_IN:
                n = s["n"]
                s["center"] = (s["center"] * n + center) / (n + 1)
                s["left"] = (s["left"] * n + left) / (n + 1)
                s["right"] = (s["right"] * n + right) / (n + 1)
                s["n"] = n + 1
                self.log(f"refined stud @ {s['center']:.2f} in (n={s['n']})")
                return
        self.studs.append({"center": center, "left": left, "right": right, "n": 1})
        self.studs.sort(key=lambda s: s["center"])
        self.log(f"new stud @ {center:.2f} in  (width {right - left:.2f} in)")


def draw_studs(frame, calib, studs, highlight=None):
    y0, y1 = calib.y_range
    for i, s in enumerate(studs):
        top, bot = calib.in_to_px([(s["center"], y0), (s["center"], y1)]).astype(int)
        thick = 7 if i == highlight else 4
        cv2.line(frame, tuple(top), tuple(bot), (0, 0, 255), thick)
        # Thin lines for the detected edges.
        for edge in (s["left"], s["right"]):
            a, b = calib.in_to_px([(edge, y0), (edge, y1)]).astype(int)
            cv2.line(frame, tuple(a), tuple(b), (0, 0, 180), 1)
        cv2.putText(frame, f'Stud {i + 1} @ {s["center"]:.1f}"', (top[0] + 8, top[1] + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)


class StudApp:
    """All program state. Thread-safe: every public method takes the lock."""

    def __init__(self, serial=False, port=None, tape=False, fake_laser=False,
                 wall_size=None, ask_wall_size=False):
        """wall_size: (width, height) in inches, overrides the saved size.
        ask_wall_size: make entering the size the first setup step (web page)."""
        self.lock = threading.RLock()
        self.messages = deque(maxlen=60)   # (time, text) for the UI log
        laser.log = self.log

        self.link = SerialLink(port) if serial else FakeLink()
        self.log(f"stud signal: {self.link.port}")
        self.rig = None
        if fake_laser:
            self.rig = laser.FakeRig(aim_in=(wall_size or WALL_SIZE_IN)[0] / 2)
            self.log("laser: simulated (--fake-laser)")

        self.calib = vision.Calibration(corners_for(*(wall_size or WALL_SIZE_IN)))
        self.wall_override = wall_size
        self.wall_size_set = not ask_wall_size or wall_size is not None
        self.frame_size = None
        self.clicks = []
        self.clicking = True
        self.tape = vision.TapeTracker() if tape else None
        self.tape_click = None
        self.finder_name = "colored object" if tape else "marker 10"

        self.view = "video"
        self.detector = laser.LaserDetector()
        self.lcal = laser.LaserCalibration(self.send, *LASER_STEP_RANGE)
        self.aimer = laser.Aimer(self.send, self.lcal)
        self.laser_on = False
        self.aim_index = None

        self.history = History()
        self.studmap = StudMap(self.log)
        self.markers = {}
        self.finder_box = None
        self.x = None
        self.laser_x = None
        self.fps = 0.0
        self._last = None

    # ------------------------------------------------------------- helpers --
    def log(self, text):
        print(text)
        self.messages.append((time.time(), text))

    def send(self, cmd):
        self.link.send(cmd)
        if self.rig is not None:
            self.rig.command(cmd)

    @property
    def wall_size(self):
        w = self.calib.wall_in
        return float(w[:, 0].max() - w[:, 0].min()), float(w[:, 1].max() - w[:, 1].min())

    @property
    def setup_step(self):
        """What the user needs to do next, or None when setup is done."""
        if not self.wall_size_set:
            return "Enter the distance between the tape crosses"
        if self.clicking:
            i = len(self.clicks)
            x, y = self.calib.wall_in[i]
            return f"Click the {CORNER_NAMES[i]} cross ({x:g}, {y:g} in)"
        if self.tape is not None and not self.tape.ready:
            return "Click the colored object on the stud finder"
        return None

    # ------------------------------------------------------------- actions --
    def click(self, x, y):
        """A click on the video, in full-resolution frame pixels."""
        with self.lock:
            if not self.wall_size_set:
                return
            if self.clicking and len(self.clicks) < 4:
                self.clicks.append((float(x), float(y)))
                if len(self.clicks) == 4:
                    self.calib.set_pixels(self.clicks)
                    if self.frame_size:
                        self.calib.save(self.frame_size)
                    self.clicking = False
                    self.log("wall calibration saved")
            elif self.tape is not None and not self.tape.ready:
                self.tape_click = (int(x), int(y))

    def command(self, name, arg=None):
        """Named actions shared by the keyboard and the web buttons."""
        with self.lock:
            now = time.time()
            if name == "set_wall":
                try:
                    w, h = float(arg["width"]), float(arg["height"])
                except (TypeError, KeyError, ValueError):
                    self.log("wall size: enter two numbers")
                    return
                if not (1 <= w <= 600 and 1 <= h <= 600):
                    self.log("wall size: use inches between 1 and 600")
                    return
                self.calib.set_wall(corners_for(w, h))
                self.wall_size_set = True
                if self.rig is not None:
                    self.rig.aim_in = w / 2
                if self.calib.ready and not self.clicking and self.frame_size:
                    self.calib.save(self.frame_size)   # clicks kept, inches updated
                self.log(f"scan area set to {w:g} x {h:g} in")
            elif name == "set_corners":
                # 4 corners from the web page's box, as fractions of the frame,
                # order TL, TR, BR, BL.
                if not self.frame_size or not self.wall_size_set:
                    return
                try:
                    pts = [(float(x) * self.frame_size[0], float(y) * self.frame_size[1])
                           for x, y in arg["corners"]]
                    assert len(pts) == 4
                except (TypeError, KeyError, ValueError, AssertionError):
                    self.log("corners: expected 4 points")
                    return
                self.clicks = pts
                self.calib.set_pixels(pts)
                self.calib.save(self.frame_size)
                self.clicking = False
                self.log("wall corners saved")
            elif name == "recalibrate":
                self.clicks = []
                self.clicking = True
            elif name == "undo_click" and self.clicking and self.clicks:
                self.clicks.pop()
            elif name == "reset_studs":
                self.studmap = StudMap(self.log)
                self.aim_index = None
                self.log("studs cleared")
            elif name == "stud_signal" and isinstance(self.link, FakeLink):
                self.link.toggle()
            elif name == "resample_object" and self.tape is not None:
                self.tape.lo = self.tape.hi = None
            elif name == "view":
                self.view = arg if arg in VIEWS else \
                    VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)]
            elif name == "laser_calibrate":
                if not self.calib.ready:
                    self.log("finish the wall setup first")
                    return
                if self.rig is None and isinstance(self.link, FakeLink):
                    self.log("note: no laser connected (--serial) or simulated "
                             "(--fake-laser); calibration needs a red line on the wall")
                self.log("laser calibration: sweeping the motor ...")
                self.aimer.status = ""
                self.lcal.start(now)
                self.laser_on = True
            elif name in ("next_stud", "aim"):
                if self.lcal.running:
                    return
                studs = self.studmap.studs
                if not studs:
                    self.aimer.status = "no studs found yet"
                    return
                if name == "aim":
                    self.aim_index = int(arg) % len(studs)
                else:
                    self.aim_index = 0 if self.aim_index is None else \
                        (self.aim_index + 1) % len(studs)
                s = studs[self.aim_index]
                self.aimer.aim(s["center"], now, label=f"Stud {self.aim_index + 1}")
                self.laser_on = self.laser_on or self.aimer.running
            elif name == "laser_toggle":
                self.laser_on = not self.laser_on
                self.send(f"L {int(self.laser_on)}")

    # ----------------------------------------------------- per-frame work --
    def process(self, frame, now=None):
        """Update everything from one camera frame. Returns the annotated frame."""
        with self.lock:
            now = time.time() if now is None else now
            if self.frame_size is None:
                self.frame_size = (frame.shape[1], frame.shape[0])
                if self.calib.load(self.frame_size):
                    self.clicking = False
                    self.wall_size_set = True
                    w, h = self.wall_size
                    self.log(f"loaded saved wall calibration ({w:g} x {h:g} in)")
                    if self.wall_override:
                        self.calib.set_wall(corners_for(*self.wall_override))
                        self.calib.save(self.frame_size)
            if self._last is not None:
                self.fps = 0.9 * self.fps + 0.1 / max(now - self._last, 1e-6)
            dt = now - self._last if self._last is not None else 0.0
            self._last = now

            if self.rig is not None:
                self.rig.draw(frame, self.calib, dt)
            if self.tape_click is not None:
                self.tape.sample(frame, *self.tape_click)
                self.tape_click = None

            # --- where is the stud finder? ---
            self.markers = vision.detect(frame)
            self.finder_box = None
            if self.tape is not None:
                self.markers.pop(vision.FINDER_ID, None)
                self.finder_box = self.tape.find(frame, self.calib)
            else:
                self.finder_box = self.markers.pop(vision.FINDER_ID, None)
            self.x = vision.finder_x(
                {vision.FINDER_ID: self.finder_box} if self.finder_box is not None else {},
                self.calib, SENSOR_OFFSET_IN)
            if self.x is not None:
                self.history.add(now - CAMERA_LATENCY_S, self.x)

            # --- laser ---
            self.laser_x = self.detector.find(frame, self.calib)
            self.lcal.update(now, self.laser_x)
            self.aimer.update(now, self.laser_x)

            # --- stud signal events ---
            while not self.link.events.empty():
                t, line = self.link.events.get()
                kind = line.split()[0]
                if kind in ("S1", "S0"):
                    ex = self.history.x_at(t)
                    if ex is None:
                        self.log(f"{kind} ignored: {self.finder_name} not seen at that moment")
                    else:
                        self.studmap.handle(kind, ex)
                else:
                    self.log(f"arduino: {line}")

            return self._draw(frame)

    def _draw(self, frame):
        if self.view == "object mask" and self.tape is not None and self.tape.mask is not None:
            return cv2.cvtColor(self.tape.mask, cv2.COLOR_GRAY2BGR)
        if self.view == "laser mask" and self.detector.mask is not None:
            return cv2.resize(cv2.cvtColor(self.detector.mask, cv2.COLOR_GRAY2BGR),
                              (frame.shape[1], frame.shape[0]),
                              interpolation=cv2.INTER_NEAREST)
        vision.draw_markers(frame, self.markers)
        if self.finder_box is not None:
            cv2.polylines(frame, [self.finder_box.astype(np.int32)], True, (0, 255, 255), 3)
        for p in self.clicks if self.clicking else (self.calib.px if self.calib.ready else []):
            cv2.drawMarker(frame, (int(p[0]), int(p[1])), (255, 0, 255),
                           cv2.MARKER_CROSS, 40, 3)
        if self.calib.ready and not self.clicking:
            draw_studs(frame, self.calib, self.studmap.studs, self.aim_index)
            if self.laser_x is not None:
                y0, y1 = self.calib.y_range
                top, bot = self.calib.in_to_px([(self.laser_x, y0),
                                                (self.laser_x, y1)]).astype(int)
                cv2.line(frame, tuple(top), tuple(bot), (255, 255, 0), 1)
        return frame

    # --------------------------------------------------------------- state --
    def hud_lines(self):
        """Short status text, for the OpenCV window."""
        with self.lock:
            lines = [f"{self.fps:4.1f} fps   markers: {sorted(self.markers)}"]
            step = self.setup_step
            if step:
                lines.append(step.upper())
                return lines
            lines.append(f"x = {self.x:.2f} in" if self.x is not None
                         else f"x = --  ({self.finder_name} not seen)")
            if self.studmap.open_x is not None:
                lines.append(f"edge @ {self.studmap.open_x:.1f} in, now come from the other side")
            seen = f"{self.laser_x:.2f} in" if self.laser_x is not None else "--"
            lines.append(f"laser: {seen}   {self.lcal.status}")
            if self.aimer.status:
                lines.append(self.aimer.status)
            if self.view != "video":
                lines.append(f"[{self.view}]  m = next view")
            return lines

    def state(self):
        """Everything the web page shows, as plain JSON-able data."""
        with self.lock:
            corners = [[float(v) for v in p] for p in self.calib.wall_in]
            xs = [p[0] for p in corners]
            ys = [p[1] for p in corners]
            return {
                "fps": round(self.fps, 1),
                "frame_size": self.frame_size,
                "setup_step": self.setup_step,
                "clicks": len(self.clicks) if self.clicking else 4,
                "wall": {"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys)},
                "corners_in": corners,
                # saved corner positions as fractions of the frame (for the box editor)
                "corners_norm": ([[float(x) / self.frame_size[0], float(y) / self.frame_size[1]]
                                  for x, y in self.calib.px]
                                 if self.calib.px is not None and self.frame_size else None),
                "wall_size": self.wall_size,
                "wall_size_set": self.wall_size_set,
                "tracker": {
                    "mode": "object" if self.tape is not None else "marker",
                    "name": self.finder_name,
                    "ready": self.tape is None or self.tape.ready,
                    "x": self.x,
                },
                "signal": {
                    "source": "fake" if isinstance(self.link, FakeLink) else "serial",
                    "port": self.link.port,
                    "on": getattr(self.link, "on", None),
                },
                "studs": [dict(s) for s in self.studmap.studs],
                "open_x": self.studmap.open_x,
                "laser": {
                    "simulated": self.rig is not None,
                    "x": self.laser_x,
                    "on": self.laser_on,
                    "calibrated": self.lcal.ready,
                    "calibrating": self.lcal.running,
                    "status": self.lcal.status,
                    "aiming": self.aimer.running,
                    "aim_status": self.aimer.status,
                    "aim_index": self.aim_index,
                },
                "view": self.view,
                "views": VIEWS if self.tape is not None else ["video", "laser mask"],
                "messages": [{"t": t, "text": m} for t, m in list(self.messages)[-25:]],
            }

    def close(self):
        self.link.close()
