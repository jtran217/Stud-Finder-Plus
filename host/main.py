"""Stud Mapper: live stud overlay.

  python host/main.py --camera 1              # keyboard fake stud signal (space)
  python host/main.py --camera 1 --serial     # real Pro Micro on /dev/cu.usbmodem*
  python host/main.py --camera 1 --tape       # track colored tape instead of marker 10
  python host/main.py --fake-laser            # simulated laser + motor, for testing

Keys:  c = re-click calibration   r = reset studs   space = fake stud signal
       t = re-click tape color (--tape)   m = cycle mask views (tape / laser)
       k = calibrate laser   n = aim laser at next stud   l = laser on/off
       q = quit

First run: click the 4 tape crosses in order TL, TR, BR, BL.
Clicks are saved to host/calib.json and reused until the tripod moves (press c).
With --tape, you then click the tape on the stud finder once to sample its color.
"""
import argparse
import bisect
import time
from collections import deque

import cv2
import numpy as np

import laser
import vision
from serial_link import FakeLink, SerialLink

# ---- Edit these to match tonight's setup -----------------------------------
# Measured positions of the 4 tape crosses, in inches. Order: TL, TR, BR, BL.
WALL_CORNERS_IN = [(0, 0), (24, 0), (24, 12), (0, 12)]
# Inches from marker 10's center to the stud finder's sensing point (+ = right).
SENSOR_OFFSET_IN = 0.0
# Camera frames arrive a little late; shift frame timestamps back by this much.
CAMERA_LATENCY_S = 0.0
# Studs whose centers are closer than this are treated as the same stud.
MERGE_IN = 1.0
# Display is scaled down so a 1080p frame fits on a laptop screen.
DISPLAY_SCALE = 0.6
# Laser calibration sweeps the motor between these step positions (step 0 =
# where the motor was at power-up or the last Z). Widen if the laser doesn't
# reach both edges of the wall; narrow if it goes way past them.
LASER_STEP_RANGE = (-300, 300)
# ----------------------------------------------------------------------------

CORNER_NAMES = ["top-left", "top-right", "bottom-right", "bottom-left"]
HISTORY_S = 3.0
MAX_GAP_S = 0.3   # don't interpolate across gaps where the marker was lost


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
    def __init__(self):
        self.studs = []       # dicts: center, left, right, n
        self.open_x = None    # x at the last S1, waiting for S0

    def handle(self, kind, x):
        if kind == "S1":
            self.open_x = x
        elif kind == "S0" and self.open_x is not None:
            left, right = sorted((self.open_x, x))
            self.open_x = None
            self._add(left, right)

    def _add(self, left, right):
        center = (left + right) / 2
        for s in self.studs:
            if abs(s["center"] - center) < MERGE_IN:
                n = s["n"]
                s["center"] = (s["center"] * n + center) / (n + 1)
                s["left"] = (s["left"] * n + left) / (n + 1)
                s["right"] = (s["right"] * n + right) / (n + 1)
                s["n"] = n + 1
                print(f"refined stud @ {s['center']:.2f} in (n={s['n']})")
                return
        self.studs.append({"center": center, "left": left, "right": right, "n": 1})
        self.studs.sort(key=lambda s: s["center"])
        print(f"new stud @ {center:.2f} in  (width {right - left:.2f} in)")


def draw_studs(frame, calib, studs):
    y0, y1 = calib.y_range
    for i, s in enumerate(studs, 1):
        top, bot = calib.in_to_px([(s["center"], y0), (s["center"], y1)]).astype(int)
        cv2.line(frame, tuple(top), tuple(bot), (0, 0, 255), 4)
        # Thin lines for the detected edges.
        for edge in (s["left"], s["right"]):
            a, b = calib.in_to_px([(edge, y0), (edge, y1)]).astype(int)
            cv2.line(frame, tuple(a), tuple(b), (0, 0, 180), 1)
        cv2.putText(frame, f'Stud {i} @ {s["center"]:.1f}"', (top[0] + 8, top[1] + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 0, 255), 3)


def draw_hud(frame, lines):
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (20, 50 + i * 45), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0, 0, 0), 6)
        cv2.putText(frame, text, (20, 50 + i * 45), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0, 255, 0), 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--serial", action="store_true", help="use the real Pro Micro")
    ap.add_argument("--port", default=None, help="serial port (default: auto)")
    ap.add_argument("--tape", action="store_true",
                    help="track colored tape on the stud finder instead of marker 10")
    ap.add_argument("--fake-laser", action="store_true",
                    help="simulate the laser + motor (draws a red line on the video)")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.camera, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    ok, frame = cap.read()
    if not ok:
        raise SystemExit(f"Camera {args.camera} gave no frame. Run host/find_camera.py.")
    frame_size = (frame.shape[1], frame.shape[0])
    print(f"camera {args.camera}: {frame_size[0]}x{frame_size[1]}")

    link = SerialLink(args.port) if args.serial else FakeLink()
    print(f"stud signal: {link.port}")

    rig = None
    if args.fake_laser:
        x0, x1 = min(p[0] for p in WALL_CORNERS_IN), max(p[0] for p in WALL_CORNERS_IN)
        rig = laser.FakeRig(aim_in=(x0 + x1) / 2)

    def send(cmd):
        link.send(cmd)
        if rig is not None:
            rig.command(cmd)

    calib = vision.Calibration(WALL_CORNERS_IN)
    clicks = []
    if calib.load(frame_size):
        print("loaded saved calibration (press c to redo)")
    clicking = not calib.ready
    tape = vision.TapeTracker() if args.tape else None
    tape_click = []        # pending click on the tape, sampled on the next frame
    view = "video"         # or "tape mask" / "laser mask"
    detector = laser.LaserDetector()
    lcal = laser.LaserCalibration(send, *LASER_STEP_RANGE)
    aimer = laser.Aimer(send, lcal)
    laser_on = False
    aim_index = -1

    def on_mouse(event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN:
            return
        px = (x / DISPLAY_SCALE, y / DISPLAY_SCALE)
        if clicking and len(clicks) < 4:
            clicks.append(px)
        elif tape is not None and not tape.ready:
            tape_click[:] = [px]

    win = "Stud Mapper"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_mouse)

    finder_name = "tape" if tape is not None else "marker 10"
    history = History()
    studmap = StudMap()
    fps, last = 0.0, time.time()

    while True:
        ok, frame = cap.read()
        now = time.time()
        if not ok:
            continue
        dt = now - last
        fps = 0.9 * fps + 0.1 / max(dt, 1e-6)
        last = now
        if rig is not None:
            rig.draw(frame, calib, dt)

        # --- calibration by clicking ---
        if clicking and len(clicks) == 4:
            calib.set_pixels(clicks)
            calib.save(frame_size)
            clicking = False
            print("calibration saved")

        if tape_click:
            tape.sample(frame, int(tape_click[0][0]), int(tape_click[0][1]))
            tape_click.clear()

        markers = vision.detect(frame)
        tape_box = None
        if tape is not None:
            # The tape replaces marker 10 as the stud finder's position.
            markers.pop(vision.FINDER_ID, None)
            tape_box = tape.find(frame, calib)
            x = vision.finder_x({vision.FINDER_ID: tape_box} if tape_box is not None else {},
                                calib, SENSOR_OFFSET_IN)
        else:
            x = vision.finder_x(markers, calib, SENSOR_OFFSET_IN)
        if x is not None:
            history.add(now - CAMERA_LATENCY_S, x)

        # --- laser ---
        laser_x = detector.find(frame, calib)
        lcal.update(now, laser_x)
        aimer.update(now, laser_x)

        # --- stud signal events ---
        while not link.events.empty():
            t, line = link.events.get()
            kind = line.split()[0]
            if kind in ("S1", "S0"):
                ex = history.x_at(t)
                if ex is None:
                    print(f"{kind} ignored: {finder_name} not seen at that moment")
                else:
                    studmap.handle(kind, ex)
            else:
                print(f"arduino: {line}")

        # --- drawing ---
        if view == "tape mask" and tape is not None and tape.mask is not None:
            frame = cv2.cvtColor(tape.mask, cv2.COLOR_GRAY2BGR)
        elif view == "laser mask" and detector.mask is not None:
            frame = cv2.resize(cv2.cvtColor(detector.mask, cv2.COLOR_GRAY2BGR),
                               (frame.shape[1], frame.shape[0]),
                               interpolation=cv2.INTER_NEAREST)
        vision.draw_markers(frame, markers)
        if tape_box is not None:
            cv2.polylines(frame, [tape_box.astype(np.int32)], True, (0, 255, 255), 3)
            cv2.putText(frame, "tape", tuple(tape_box[1].astype(int)),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 255, 255), 3)
        for p in clicks if clicking else (calib.px if calib.ready else []):
            cv2.drawMarker(frame, (int(p[0]), int(p[1])), (255, 0, 255),
                           cv2.MARKER_CROSS, 40, 3)
        if calib.ready and not clicking and view == "video":
            draw_studs(frame, calib, studmap.studs)
            if laser_x is not None:
                y0, y1 = calib.y_range
                top, bot = calib.in_to_px([(laser_x, y0), (laser_x, y1)]).astype(int)
                cv2.line(frame, tuple(top), tuple(bot), (255, 255, 0), 1)
                cv2.putText(frame, f"laser {laser_x:.1f}", (bot[0] + 8, bot[1] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)

        hud = [f"{fps:4.1f} fps   markers: {sorted(markers)}"]
        if clicking:
            hud.append(f"CLICK the {CORNER_NAMES[len(clicks)]} cross "
                       f"{WALL_CORNERS_IN[len(clicks)]} in")
        elif tape is not None and not tape.ready:
            hud.append("CLICK the tape on the stud finder")
        else:
            hud.append(f"x = {x:.2f} in" if x is not None else f"x = --  ({finder_name} not seen)")
            if studmap.open_x is not None:
                hud.append(f"stud started @ {studmap.open_x:.1f} in ...")
            seen = f"{laser_x:.2f} in" if laser_x is not None else "--"
            hud.append(f"laser: {seen}   {lcal.status}")
            if aimer.status:
                hud.append(aimer.status)
        if view != "video":
            hud.append(f"[{view}]  m = next view")
        draw_hud(frame, hud)

        cv2.imshow(win, cv2.resize(frame, None, fx=DISPLAY_SCALE, fy=DISPLAY_SCALE))
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("c"):
            clicks.clear()
            clicking = True
        elif key == ord("r"):
            studmap = StudMap()
        elif key == ord("t") and tape is not None:
            tape.lo = tape.hi = None
        elif key == ord("m"):
            views = ["video"] + (["tape mask"] if tape is not None else []) + ["laser mask"]
            view = views[(views.index(view) + 1) % len(views)]
        elif key == ord("k") and calib.ready and not clicking:
            if rig is None and isinstance(link, FakeLink):
                print("note: no laser hardware (--serial) and no simulator (--fake-laser); "
                      "calibration will only work if a real red line is on the wall")
            print("laser calibration: sweeping the motor ...")
            aimer.status = ""
            lcal.start(now)
            laser_on = True
        elif key == ord("n") and not lcal.running:
            if not studmap.studs:
                aimer.status = "no studs found yet"
            else:
                aim_index = (aim_index + 1) % len(studmap.studs)
                s = studmap.studs[aim_index]
                aimer.aim(s["center"], now, label=f"Stud {aim_index + 1}")
                laser_on = laser_on or aimer.running
        elif key == ord("l"):
            laser_on = not laser_on
            send(f"L {int(laser_on)}")
        elif key == ord(" ") and isinstance(link, FakeLink):
            link.toggle()

    link.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
