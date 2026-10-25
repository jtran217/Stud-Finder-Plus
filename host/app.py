"""Stud Mapper core. Everything except the UI.

StudApp takes camera frames + user actions and keeps the stud map,
calibration and laser state. main.py (OpenCV window) and web.py (browser)
both drive it.
"""
import bisect
import threading
import time
from collections import deque

import cv2
import numpy as np

import laser
import vision
from diag import Diag
from serial_link import FakeLink, SerialLink, find_laser_port

# --- setup-specific settings ---
WALL_SIZE_IN = (24, 12)    # default scan area (distance between tape crosses)
SENSOR_OFFSET_IN = 0.0     # tracked object center -> sensor center (+ = sensor to the right). TODO measure
CAMERA_LATENCY_S = 0.0
MERGE_IN = 1.0             # studs closer than this are the same stud

# Stud = an edge found moving right (left side) + one found moving left.
# Camera lag pushes the two edges toward each other on a fast sweep, so there's
# no minimum width for that case, just a limit on how far they can cross.
MAX_STUD_IN = 3.5
MAX_OVERLAP_IN = 1.0
MIN_STUD_IN_UNSURE = 0.3   # if we don't know which way it was moving
EDGE_TTL_S = 20.0
MIN_SPEED_IN_S = 0.3       # slower than this = direction unknown

LASER_MAX_STEPS = 900      # calibration won't turn further than this from step 0 (~80 deg)

CORNER_NAMES = ["top-left", "top-right", "bottom-right", "bottom-left"]
STAGES = ["calibrate", "finder", "scan"]
HISTORY_S = 3.0
MAX_GAP_S = 0.3   # don't interpolate across tracker dropouts longer than this
VIEWS = ["video", "object mask", "laser mask"]


def corners_for(width, height):
    """Tape crosses in inches: TL, TR, BR, BL."""
    return [(0, 0), (width, 0), (width, height), (0, height)]


class History:
    """Recent (time, x) samples of the stud finder, so we can look up where
    it was when a serial event arrives."""

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

    def v_at(self, t, span=0.15):
        """Speed in in/s around t (+ = moving right), None if not enough data."""
        pts = [(ti, xi) for ti, xi in zip(self.t, self.x) if abs(ti - t) <= span]
        if len(pts) < 3 or pts[-1][0] - pts[0][0] < span * 0.6:
            return None
        ts = np.array([p[0] for p in pts]) - t
        xs = np.array([p[1] for p in pts])
        return float(np.polyfit(ts, xs, 1)[0])

    def last_seen(self):
        return self.t[-1] if self.t else None


class StudMap:
    """Turns S1 edges into studs.

    Each S1 = the LED came on sliding onto a stud from one side. We keep a few
    unpaired edges around so one bad edge doesn't throw away a half-found stud.
    """

    def __init__(self, log=print):
        self.studs = []   # center, left, right, n
        self.edges = []   # unpaired edges: x, dir (+1/-1/0), t
        self.log = log

    @property
    def open_x(self):
        return self.edges[-1]["x"] if self.edges else None

    def handle(self, kind, x, direction=0, t=None):
        """Returns (stud or None, description for the log)."""
        if kind != "S1":
            return None, "S0 ignored (only S1 edges count)"
        t = time.time() if t is None else t
        self.edges = [e for e in self.edges if t - e["t"] < EDGE_TTL_S]

        def fits(e):
            gap = abs(e["x"] - x)
            if gap > MAX_STUD_IN:
                return False
            if direction and e["dir"]:
                if e["dir"] == direction:
                    return False
                # left-side edge has to be left of the right-side one (+ some overlap from lag)
                left_side = x if direction > 0 else e["x"]
                right_side = e["x"] if direction > 0 else x
                return right_side - left_side >= -MAX_OVERLAP_IN
            return gap >= MIN_STUD_IN_UNSURE

        partners = [e for e in self.edges if fits(e)]
        if partners:
            e = min(partners, key=lambda e: abs(e["x"] - x))
            self.edges.remove(e)
            left, right = sorted((e["x"], x))
            stud = self._add(left, right)
            return stud, (f"paired with edge @ {e['x']:.2f} in "
                          f"(dir {e['dir']:+d}, {t - e['t']:.1f} s ago) -> stud @ {stud['center']:.2f} in")

        why = ("too far from the other edges: "
               + ", ".join(f"{e['x']:.1f}(dir {e['dir']:+d})" for e in self.edges)
               if self.edges else "first edge")
        # same edge passed again -> replace the old one
        self.edges = [e for e in self.edges
                      if not (e["dir"] == direction and abs(e["x"] - x) < 1.0)]
        self.edges = (self.edges + [{"x": x, "dir": direction, "t": t}])[-6:]
        side = {1: "left side (moving right)", -1: "right side (moving left)"}.get(
            direction, "unknown side (not moving)")
        self.log(f"edge @ {x:.2f} in, {side}: waiting for the other side")
        return None, f"edge kept, {why}"

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
                return s
        s = {"center": center, "left": left, "right": right, "n": 1}
        self.studs.append(s)
        self.studs.sort(key=lambda s: s["center"])
        self.log(f"new stud @ {center:.2f} in  (edges {left:.2f} / {right:.2f})")
        return s


def draw_studs(frame, calib, studs, highlight=None):
    y0, y1 = calib.y_range
    for i, s in enumerate(studs):
        top, bot = calib.in_to_px([(s["center"], y0), (s["center"], y1)]).astype(int)
        thick = 7 if i == highlight else 4
        cv2.line(frame, tuple(top), tuple(bot), (0, 0, 255), thick)
        for edge in (s["left"], s["right"]):
            a, b = calib.in_to_px([(edge, y0), (edge, y1)]).astype(int)
            cv2.line(frame, tuple(a), tuple(b), (0, 0, 180), 1)
        cv2.putText(frame, f'Stud {i + 1} @ {s["center"]:.1f}"', (top[0] + 8, top[1] + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)


class StudApp:
    """All the state. Every public method takes the lock."""

    def __init__(self, serial=False, port=None, tape=False, fake_laser=False,
                 wall_size=None, ask_wall_size=False, laser_serial=False, laser_port=None):
        # ask_wall_size=True is the web page (guided steps), False is main.py
        self.lock = threading.RLock()
        self.messages = deque(maxlen=60)
        self.diag = Diag()
        laser.log = self.log

        self.laser_link = None
        if laser_serial or laser_port:
            lport = laser_port or find_laser_port()
            if lport is None:
                raise RuntimeError("Laser station not found. Is it plugged in and flashed "
                                   "with firmware/laser_station?")
            self.laser_link = SerialLink(lport, wait_ready=True)
            self.laser_link.tap = lambda d, line: self._serial_tap("laser", d, line)
            self.log(f"laser station: {lport}")

        if serial:
            exclude = [self.laser_link.port] if self.laser_link else []
            self.link = SerialLink(port, exclude=exclude)
        else:
            self.link = FakeLink()
        self.link.tap = lambda d, line: self._serial_tap("stud", d, line)
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
        self.stepper = laser.Stepper(self.send)
        self.lcal = laser.LaserCalibration(self.stepper, LASER_MAX_STEPS)
        self.aimer = laser.Aimer(self.stepper, self.lcal)
        self.laser_on = False
        self.lcal_this_run = False   # we want a fresh sweep every launch, even if one was loaded

        # Current step lives on the server so all open tabs agree (two tabs
        # fighting over it was turning stud detection on/off constantly).
        self.guided = ask_wall_size
        self.stage = "calibrate" if ask_wall_size else "scan"
        self.scanning = not ask_wall_size
        self.forget_box = False      # after Restart setup, don't prefill the old box
        self.laser_skipped = False
        self.finder_seen = False     # marker mode only
        self.aim_index = None
        self.found = {"seq": 0, "index": None, "new": False, "aimed": False}  # page flashes on seq change

        self.history = History()
        self.studmap = StudMap(self.log)
        self.markers = {}
        self.finder_box = None
        self.x = None
        self.laser_x = None
        self.fps = 0.0
        self._last = None

        # diagnostics
        self.counts = {"S1": 0, "S0": 0, "edges": 0, "paired": 0, "ignored": 0,
                       "not_seen": 0, "frames": 0, "tracker_seen": 0, "laser_seen": 0}
        self._beat_t = 0.0
        self._beat_counts = dict(self.counts)
        self._tracker_lost_since = None
        self._tracker_lost_snapped = False
        self._laser_was_seen = None
        self._tx_pending = None      # (t, cmd) waiting for the laser station's OK
        self.last_stud_event = None

    def log(self, text):
        print(text)
        self.messages.append((time.time(), text))
        self.diag.write("app", text)

    def _serial_tap(self, board, direction, line):
        self.diag.write("serial", f"{board} {direction}: {line}")

    def send(self, cmd):
        (self.laser_link or self.link).send(cmd)
        if self.laser_link is not None and not cmd.startswith("ID"):
            self._tx_pending = (time.time(), cmd)
        if self.rig is not None:
            self.rig.command(cmd)

    def _clear_studs(self):
        self.studmap = StudMap(self.log)
        self.aim_index = None
        self.found = {"seq": self.found["seq"], "index": None, "new": False, "aimed": False}

    # --- steps ---
    def flow(self):
        laser_needed = (self.rig is not None or self.laser_link is not None) and not self.laser_skipped
        laser_done = not laser_needed or (self.lcal.ready and self.lcal_this_run)
        size_done = self.wall_size_set
        box_done = self.wall_size_set and not self.clicking
        finder_ready = self.tape.ready if self.tape is not None else self.finder_seen
        calibrated = size_done and box_done and laser_done
        allowed = 0 if not calibrated else 1 if not finder_ready else 2
        stage = STAGES[min(STAGES.index(self.stage), allowed)]
        return {
            "stage": stage, "allowed_index": allowed, "size_done": size_done,
            "box_done": box_done, "laser_needed": laser_needed, "laser_done": laser_done,
            "laser_failed": (not self.lcal.running and not self.lcal.ready
                             and "FAIL" in self.lcal.status),
            "finder_ready": finder_ready, "calibrated": calibrated,
        }

    def _update_flow(self):
        # If an earlier step got undone (e.g. box reopened), drop back to it.
        # Stud detection is only on during the scan step.
        f = self.flow()
        if not self.guided:   # main.py has no steps
            self.scanning = True
            return f
        if f["stage"] != self.stage:
            self.diag.write("flow", f"step {self.stage} -> {f['stage']} (earlier step not done)",
                            **{k: v for k, v in f.items() if k != "stage"})
            self.stage = f["stage"]
        scanning = self.stage == "scan" and not self.lcal.running
        if scanning != self.scanning:
            self.scanning = scanning
            self.log("stud detection on" if scanning else "stud detection paused (not on the scan step)")
        return f

    @property
    def wall_size(self):
        w = self.calib.wall_in
        return float(w[:, 0].max() - w[:, 0].min()), float(w[:, 1].max() - w[:, 1].min())

    @property
    def setup_step(self):
        """Next setup instruction for the OpenCV window, None when done."""
        if not self.wall_size_set:
            return "Enter the distance between the tape crosses"
        if self.clicking:
            i = len(self.clicks)
            x, y = self.calib.wall_in[i]
            return f"Click the {CORNER_NAMES[i]} cross ({x:g}, {y:g} in)"
        if self.tape is not None and not self.tape.ready:
            return "Click the colored object on the stud finder"
        return None

    # --- user actions ---
    def click(self, x, y):
        """Click on the video, in full-res frame pixels."""
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
        with self.lock:
            now = time.time()
            if name != "view":
                self.diag.write("cmd", name, arg=arg if not isinstance(arg, dict) else
                                {k: v for k, v in arg.items() if k != "corners"})
            self._command(name, arg, now)
            self._update_flow()

    def _command(self, name, arg, now):
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
                self.calib.save(self.frame_size)
            self.log(f"scan area set to {w:g} x {h:g} in")
        elif name == "set_corners":
            # from the web box editor: 4 points as fractions of the frame, TL TR BR BL
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
            self.forget_box = False
            self.calib.set_pixels(pts)
            self.calib.save(self.frame_size)
            self.clicking = False
            self.log("wall corners saved")
        elif name == "recalibrate":
            self.clicks = []
            self.clicking = True
            self.stage = "calibrate"
        elif name == "go":
            if arg in STAGES:
                self.stage = arg   # _update_flow clamps it
        elif name == "skip_laser":
            self.laser_skipped = True
            self.log("laser skipped: map only")
        elif name == "restart_setup":
            self.wall_size_set = False
            self.clicks = []
            self.clicking = True
            self.forget_box = True
            if self.tape is not None:
                self.tape.lo = self.tape.hi = None
            self._clear_studs()
            self.stage = "calibrate"
            self.laser_skipped = False
            self.finder_seen = False
            self.lcal_this_run = False
            self.lcal.settler = None   # stops a sweep if one is running
            self.lcal.status = "not calibrated (press k)"
            self.aimer.settler = None
            self.aimer.status = ""
            self.laser_on = False
            self.send("L 0")
            self.log("setup restarted from the beginning")
        elif name == "reset_studs":
            self._clear_studs()
            self.log("studs cleared")
        elif name == "stud_signal" and isinstance(self.link, FakeLink):
            self.link.toggle()
        elif name == "resample_object" and self.tape is not None:
            self.tape.lo = self.tape.hi = None
            self.stage = "finder"
        elif name == "view":
            self.view = arg if arg in VIEWS else \
                VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)]
        elif name == "laser_calibrate":
            if not self.calib.ready:
                self.log("finish the wall setup first")
                return
            if self.rig is None and self.laser_link is None and isinstance(self.link, FakeLink):
                self.log("note: no laser connected (--serial) or simulated "
                         "(--fake-laser); calibration needs a red line on the wall")
            self.log("laser calibration: sweeping the motor ...")
            self.aimer.status = ""
            self.laser_skipped = False
            self.stage = "calibrate"
            self.lcal.start(now)
            self.lcal_this_run = True
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
            self._aim(self.aim_index, now)
        elif name == "laser_toggle":
            self.laser_on = not self.laser_on
            self.send(f"L {int(self.laser_on)}")

    def _aim(self, index, now):
        self.aim_index = index
        s = self.studmap.studs[index]
        self.aimer.aim(s["center"], now, label=f"Stud {index + 1}")
        self.laser_on = self.laser_on or self.aimer.running

    def _stud_found(self, stud, now):
        index = self.studmap.studs.index(stud)
        aimed = self.lcal.ready and not self.lcal.running
        self.diag.write("motor", f"auto-aim at stud {index + 1} ({stud['center']:.2f} in)"
                        if aimed else "no auto-aim: laser not calibrated",
                        target=stud["center"], motor=self.stepper.pos)
        if aimed:
            self._aim(index, now)
        elif self.aim_index is not None and self.aim_index >= index and stud["n"] == 1:
            self.aim_index += 1   # new stud to the left shifts the numbering
        self.found = {"seq": self.found["seq"] + 1, "index": index,
                      "new": stud["n"] == 1, "aimed": aimed}

    def _laser_station_restarted(self):
        # Uno reset = wherever the motor is becomes step 0, so the old table is wrong
        self.lcal.points = []
        self.lcal.settler = None
        self.lcal.status = "laser station restarted, press Calibrate"
        self.stepper.pos = None
        self.aimer.settler = None
        self.laser_on = False
        self.log("laser station restarted (USB drop or power dip?): recalibrate the laser")

    # --- per frame ---
    def process(self, frame, now=None):
        """Run one camera frame through everything. Returns the frame to show."""
        with self.lock:
            now = time.time() if now is None else now
            if self.frame_size is None:
                self.frame_size = (frame.shape[1], frame.shape[0])
                if self.calib.load(self.frame_size):
                    self.clicking = self.guided   # web page makes you confirm the saved box
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

            # stud finder position
            self.finder_box = None
            if self.tape is not None:
                self.markers = {}
                self.finder_box = self.tape.find(frame, self.calib)
            else:
                self.markers = vision.detect(frame)
                self.finder_box = self.markers.pop(vision.FINDER_ID, None)
                if self.finder_box is not None:
                    self.finder_seen = True
            self.x = vision.finder_x(
                {vision.FINDER_ID: self.finder_box} if self.finder_box is not None else {},
                self.calib, SENSOR_OFFSET_IN)
            if self.x is not None:
                self.history.add(now - CAMERA_LATENCY_S, self.x)
            self._watch_tracker(now)

            # laser. Calibration only uses readings inside the box; aiming can
            # use a bit past it to correct overshoot.
            self.laser_x = self.detector.find(frame, self.calib)
            x_box = self.laser_x
            if x_box is not None:
                xs = self.calib.wall_in[:, 0]
                if not (xs.min() <= x_box <= xs.max()):
                    x_box = None
            was_running = self.lcal.running
            self.lcal.update(now, x_box)
            if was_running and not self.lcal.running and not self.lcal.ready:
                self.diag.snap("laser_calibration_failed")
            self.aimer.update(now, self.laser_x)
            self._watch_laser(now)

            if self.laser_link is not None:
                while not self.laser_link.events.empty():
                    _, line = self.laser_link.events.get()
                    if line.startswith("OK"):
                        self._tx_pending = None
                    else:
                        self.log(f"laser station: {line}")
                    if line.startswith(("READY", "serial reconnected")):
                        self._laser_station_restarted()

            self._update_flow()
            while not self.link.events.empty():
                t, line = self.link.events.get()
                kind = line.split()[0]
                if kind in ("S1", "S0"):
                    self._stud_event(kind, line, t, now)
                else:
                    self.log(f"stud finder board: {line}")

            self._heartbeat(now)
            out = self._draw(frame)
            self.diag.flush_snaps(out if self.view == "video" else frame, now)
            return out

    def _stud_event(self, kind, line, t, now):
        self.counts[kind] += 1
        if not self.scanning:
            self.counts["ignored"] += 1
            self.diag.write("stud", f"{line} ignored: not on the scan step", step=self.stage)
            if kind == "S1":
                self.last_stud_event = (now, "edge ignored: go to the Scan step first")
            return
        ex = self.history.x_at(t)
        if ex is None:
            self.counts["not_seen"] += 1
            seen = self.history.last_seen()
            age = f"{t - seen:.2f} s before" if seen else "never"
            self.log(f"{kind} ignored: {self.finder_name} not seen at that moment "
                     f"(last seen {age})")
            self.diag.write("stud", f"{line} ignored: finder not tracked at that moment",
                            last_seen=age, tracker_why=getattr(self.tape, "why", None))
            if kind == "S1":
                self.diag.snap("edge_ignored_finder_not_seen")
                self.last_stud_event = (now, "edge ignored: camera lost the stud finder")
            return
        v = self.history.v_at(t)
        direction = 0 if v is None or abs(v) < MIN_SPEED_IN_S else (1 if v > 0 else -1)
        stud, what = self.studmap.handle(kind, ex, direction, t)
        if kind == "S1":
            self.counts["edges"] += 1
            self.last_stud_event = (now, what)
        self.diag.write("stud", f"{line} -> {what}", x=ex, v=v, dir=direction,
                        delay=now - t, open_edges=len(self.studmap.edges))
        # snapshot if an edge from the other side was nearby but they didn't pair
        if kind == "S1" and stud is None and any(
                e["dir"] == -direction and direction and abs(e["x"] - ex) < MAX_STUD_IN + 2
                for e in self.studmap.edges[:-1]):
            self.diag.snap("edge_not_paired_near_other_side")
        if stud is not None:
            self.counts["paired"] += 1
            self._stud_found(stud, now)

    def _watch_tracker(self, now):
        self.counts["frames"] += 1
        if self.x is not None:
            self.counts["tracker_seen"] += 1
        needed = self.stage in ("finder", "scan") and self.flow()["finder_ready"]
        if self.x is None and needed:
            if self._tracker_lost_since is None:
                self._tracker_lost_since = now
                self.diag.write("tracker", "lost", why=getattr(self.tape, "why", "marker not seen"),
                                **(self.tape.stats if self.tape else {}))
            elif now - self._tracker_lost_since > 2.0 and not self._tracker_lost_snapped:
                self._tracker_lost_snapped = True
                self.diag.snap("tracker_lost_2s")
        elif self.x is not None and self._tracker_lost_since is not None:
            self.diag.write("tracker", "found again", x=self.x,
                            lost_for=now - self._tracker_lost_since,
                            **(self.tape.stats if self.tape else {}))
            self._tracker_lost_since = None
            self._tracker_lost_snapped = False

    def _watch_laser(self, now):
        seen = self.laser_x is not None
        if seen:
            self.counts["laser_seen"] += 1
        if self.laser_on and seen != self._laser_was_seen:
            self.diag.write("laser", "line seen" if seen else "line not seen",
                            x=self.laser_x, why=self.detector.why or None, **self.detector.stats)
            self._laser_was_seen = seen
        if self._tx_pending and now - self._tx_pending[0] > 1.0:
            self.log(f"warning: laser station didn't answer '{self._tx_pending[1]}' "
                     "(unplugged, crashed, or another program has the port?)")
            self.diag.snap("laser_station_no_reply")
            self._tx_pending = None

    def _heartbeat(self, now):
        if now - self._beat_t < 1.0:
            return
        c, b = self.counts, self._beat_counts
        frames = max(c["frames"] - b["frames"], 1)
        self.diag.write(
            "beat", self.stage, fps=self.fps, scanning=self.scanning,
            finder_x=self.x, finder_seen_pct=100 * (c["tracker_seen"] - b["tracker_seen"]) / frames,
            tracker_why=(getattr(self.tape, "why", "") or None) if self.x is None else None,
            laser_x=self.laser_x, laser_seen_pct=100 * (c["laser_seen"] - b["laser_seen"]) / frames,
            laser_on=self.laser_on, motor=self.stepper.pos, lcal=self.lcal.status,
            aim=self.aimer.status or None, studs=len(self.studmap.studs),
            open_edges=len(self.studmap.edges), S1=c["S1"], S0=c["S0"],
            ignored=c["ignored"], not_seen=c["not_seen"])
        self._beat_t = now
        self._beat_counts = dict(c)

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
                cv2.line(frame, tuple(top), tuple(bot), (255, 255, 0),
                         3 if self.lcal.running else 1)
        if self.calib.ready and self.lcal.running:
            # measured points so far, across the middle of the box
            y_mid = sum(self.calib.y_range) / 2
            for _, x in self.lcal.points:
                p = self.calib.in_to_px([(x, y_mid)]).astype(int)[0]
                cv2.circle(frame, tuple(p), 12, (0, 0, 255), -1)
                cv2.circle(frame, tuple(p), 12, (255, 255, 255), 2)
            text = self.lcal.status.replace("calibrating: ", "Calibrating: ")
            cv2.putText(frame, text, (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 6)
            cv2.putText(frame, text, (40, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (0, 0, 255), 3)
        return frame

    # --- for the front ends ---
    def hud_lines(self):
        """Status text for the OpenCV window."""
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
        """Everything the web page needs, JSON-able."""
        with self.lock:
            flow = self._update_flow()
            now = time.time()
            corners = [[float(v) for v in p] for p in self.calib.wall_in]
            xs = [p[0] for p in corners]
            ys = [p[1] for p in corners]
            return {
                "fps": round(self.fps, 1),
                "clicks": len(self.clicks) if self.clicking else 4,
                "wall": {"x0": min(xs), "x1": max(xs), "y0": min(ys), "y1": max(ys)},
                "corners_in": corners,
                # saved box as fractions of the frame, for the box editor
                "corners_norm": ([[float(x) / self.frame_size[0], float(y) / self.frame_size[1]]
                                  for x, y in self.calib.px]
                                 if self.calib.px is not None and self.frame_size
                                 and not self.forget_box else None),
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
                "open_edges": [{"x": e["x"], "dir": e["dir"]} for e in self.studmap.edges],
                "scanning": self.scanning,
                "stage": flow["stage"],
                "flow": flow,
                "diag": {
                    "log": str(self.diag.dir) if self.diag.dir else None,
                    "counts": dict(self.counts),
                    "tracker_why": (getattr(self.tape, "why", "") or None) if self.x is None else None,
                    "laser_why": self.detector.why or None,
                    "laser_stats": self.detector.stats,
                    "last_stud_event": ({"ago": now - self.last_stud_event[0],
                                         "text": self.last_stud_event[1]}
                                        if self.last_stud_event else None),
                },
                "found": dict(self.found),
                "laser": {
                    "simulated": self.rig is not None,
                    "available": self.rig is not None or self.laser_link is not None,
                    "port": self.laser_link.port if self.laser_link else None,
                    "x": self.laser_x,
                    "on": self.laser_on,
                    "calibrated": self.lcal.ready,
                    "calibrated_this_run": self.lcal.ready and self.lcal_this_run,
                    "calibrating": self.lcal.running,
                    "status": self.lcal.status,
                    "points": [float(x) for _, x in self.lcal.points],
                    "phase": getattr(self.lcal, "phase", None) if self.lcal.running else None,
                    "todo": len(getattr(self.lcal, "todo", []) or []) if self.lcal.running else 0,
                    "aiming": self.aimer.running,
                    "aim_status": self.aimer.status,
                    "aim_index": self.aim_index,
                },
                "messages": [{"t": t, "text": m} for t, m in list(self.messages)[-25:]],
            }

    def close(self):
        if self.laser_link is not None:
            # park at 0: the Uno resets on next connect and calls its current spot step 0
            self.laser_link.send("L 0")
            self.laser_link.send("G 0")
            time.sleep(1.0)
            self.laser_link.close()
        self.link.close()
        self.diag.write("app", "closed")
        self.diag.close()
