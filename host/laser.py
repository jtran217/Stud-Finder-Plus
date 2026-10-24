"""Laser line: find it in the camera image, learn steps -> inches, aim at studs.

The motor only knows step numbers, so the camera closes the loop:
  1. LaserDetector  finds the red vertical line and returns its x in wall inches.
  2. LaserCalibration  moves the motor to ~10 step positions, records where the
     line landed at each, and builds a steps <-> inches lookup table.
  3. Aimer  converts a stud's inches to steps, moves there, measures where the
     line actually landed, and nudges by the error (1-2 extra moves).

FakeRig simulates the motor + laser (draws a red line into the frame) so all
of this can be tested without hardware.
"""
import json
import math
from collections import deque
from pathlib import Path

import cv2
import numpy as np

LASER_CALIB_PATH = Path(__file__).parent / "laser_calib.json"


# ---------------------------------------------------------------- detection --

class LaserDetector:
    """Finds a vertical red laser line on the wall.

    The frame is warped to a straight-on view of the wall (PX_PER_IN pixels per
    inch), red pixels are counted per column, and the strongest column is the
    line. Dimming the room or the camera exposure makes the laser stand out.
    """

    PX_PER_IN = 20
    MARGIN_IN = 2.0      # also look a little past the left/right crosses
    S_MIN = 90           # min saturation for "red"
    V_MIN = 120          # min brightness for "red"
    MIN_FRAC = 0.15      # line must cover at least this much of the wall height

    def __init__(self):
        self.mask = None   # last red mask in wall view, for debugging

    def find(self, frame, calib):
        """Return the laser line's x in wall inches, or None."""
        if not calib.ready:
            return None
        (x0, y0), (x1, y1) = calib.wall_in.min(0), calib.wall_in.max(0)
        x0 -= self.MARGIN_IN
        x1 += self.MARGIN_IN
        p = self.PX_PER_IN
        w, h = int((x1 - x0) * p), int((y1 - y0) * p)
        # pixels -> inches (calib.H), then inches -> wall-view pixels
        S = np.array([[p, 0, -x0 * p], [0, p, -y0 * p], [0, 0, 1]], dtype=np.float64)
        wall = cv2.warpPerspective(frame, S @ calib.H, (w, h))

        hsv = cv2.cvtColor(wall, cv2.COLOR_BGR2HSV)
        lo1, hi1 = (0, self.S_MIN, self.V_MIN), (10, 255, 255)
        lo2, hi2 = (170, self.S_MIN, self.V_MIN), (179, 255, 255)
        mask = cv2.inRange(hsv, lo1, hi1) | cv2.inRange(hsv, lo2, hi2)
        self.mask = mask

        cols = mask.sum(axis=0).astype(np.float64) / 255
        peak = int(cols.argmax())
        if cols[peak] < self.MIN_FRAC * h:
            return None
        # Sub-pixel center: weighted average of columns within 0.5 in of the peak.
        a, b = max(peak - p // 2, 0), min(peak + p // 2 + 1, w)
        weights = cols[a:b]
        cx = float((np.arange(a, b) * weights).sum() / weights.sum())
        return x0 + (cx + 0.5) / p


# --------------------------------------------------------------- settling ----

class Settler:
    """After a move, waits until the laser reading stops changing."""

    MIN_WAIT_S = 0.3     # let the motor start/finish moving
    WINDOW_S = 0.3       # readings over this long ...
    TOL_IN = 0.1         # ... must agree within this much
    TIMEOUT_S = 4.0

    def __init__(self, now):
        self.t0 = now
        self.samples = deque()

    def update(self, now, x):
        """Return (done, x). x is None if the laser was never seen."""
        if now - self.t0 < self.MIN_WAIT_S:
            return False, None
        if x is not None:
            self.samples.append((now, x))
        while self.samples and self.samples[0][0] < now - self.WINDOW_S:
            self.samples.popleft()
        xs = [s[1] for s in self.samples]
        span = self.samples[-1][0] - self.samples[0][0] if self.samples else 0
        if len(xs) >= 3 and span >= self.WINDOW_S * 0.8 and max(xs) - min(xs) < self.TOL_IN:
            return True, float(np.median(xs))
        if now - self.t0 > self.TIMEOUT_S:
            return True, float(np.median(xs)) if xs else None
        return False, None


# ------------------------------------------------------------ calibration ----

class LaserCalibration:
    """Steps <-> inches lookup table, measured by sweeping the motor."""

    def __init__(self, send, step_min, step_max, n_points=10):
        self.send = send
        self.positions = [int(round(s)) for s in np.linspace(step_min, step_max, n_points)]
        self.points = []        # (steps, inches)
        self.queue = []
        self.settler = None
        self.status = "not calibrated (press k)"
        self.load()

    @property
    def ready(self):
        return len(self.points) >= 3 and not self.running

    @property
    def running(self):
        return self.settler is not None

    # --- the sweep, driven one frame at a time ---
    def start(self, now):
        self.points = []
        self.queue = list(self.positions)
        self.send("L 1")
        self._next(now)

    def _next(self, now):
        if not self.queue:
            self.settler = None
            self._finish()
            return
        self.current = self.queue.pop(0)
        self.send(f"G {self.current}")
        self.settler = Settler(now)
        self.status = (f"calibrating: step {self.current} "
                       f"({len(self.positions) - len(self.queue)}/{len(self.positions)})")

    def update(self, now, laser_x):
        if not self.running:
            return
        done, x = self.settler.update(now, laser_x)
        if done:
            if x is None:
                print(f"  step {self.current:5d} -> laser not seen (off the wall?)")
            else:
                print(f"  step {self.current:5d} -> {x:6.2f} in")
                self.points.append((self.current, x))
            self._next(now)

    def _finish(self):
        if len(self.points) < 3:
            self.status = f"calibration FAILED: laser seen at only {len(self.points)} positions"
            print(self.status)
            self.points = []
            return
        steps = np.array([p[0] for p in self.points], dtype=float)
        inches = np.array([p[1] for p in self.points], dtype=float)
        d = np.diff(inches)
        if not (np.all(d > 0) or np.all(d < 0)):
            print("warning: laser positions are not in order; some readings may be wrong")
        self.save()
        self.status = (f"calibrated: {len(self.points)} pts, "
                       f"{inches.min():.1f}-{inches.max():.1f} in")
        print(self.status)

    # --- lookups ---
    def _sorted_by_inches(self):
        pts = sorted(self.points, key=lambda p: p[1])
        return np.array([p[1] for p in pts]), np.array([p[0] for p in pts], dtype=float)

    def in_range(self, x):
        inches, _ = self._sorted_by_inches()
        return inches[0] <= x <= inches[-1]

    def steps_for(self, x):
        """Steps that should put the laser at x inches (linear between points)."""
        inches, steps = self._sorted_by_inches()
        return float(np.interp(x, inches, steps))

    def steps_per_inch(self, x):
        """Local slope, used to turn an aiming error in inches into steps."""
        return (self.steps_for(x + 0.25) - self.steps_for(x - 0.25)) / 0.5

    # --- persistence ---
    def save(self):
        LASER_CALIB_PATH.write_text(json.dumps({"points": self.points}, indent=2))

    def load(self):
        if LASER_CALIB_PATH.exists():
            self.points = [tuple(p) for p in json.loads(LASER_CALIB_PATH.read_text())["points"]]
            if len(self.points) >= 3:
                self.status = f"calibrated: {len(self.points)} pts (loaded; k to redo)"


# ----------------------------------------------------------------- aiming ----

class Aimer:
    """Points the laser at a target x, then corrects using what the camera sees."""

    TOL_IN = 0.15        # good enough
    MAX_CORRECTIONS = 3

    def __init__(self, send, lcal):
        self.send = send
        self.lcal = lcal
        self.settler = None
        self.target = None
        self.label = ""
        self.status = ""

    @property
    def running(self):
        return self.settler is not None

    def aim(self, target, now, label=""):
        if not self.lcal.ready:
            self.status = "laser not calibrated (press k)"
            return
        if not self.lcal.in_range(target):
            print(f"warning: {target:.1f} in is outside the calibrated range; extrapolating")
        self.target, self.label, self.tries = target, label, 0
        self.steps = int(round(self.lcal.steps_for(target)))
        self.send("L 1")
        self._move(now)

    def _move(self, now):
        self.send(f"G {self.steps}")
        self.settler = Settler(now)
        self.status = f"aiming at {self.label} {self.target:.1f} in ..."

    def update(self, now, laser_x):
        if not self.running:
            return
        done, x = self.settler.update(now, laser_x)
        if not done:
            return
        self.settler = None
        if x is None:
            self.status = f"{self.label}: laser not seen after move"
            return
        err = self.target - x
        if abs(err) <= self.TOL_IN or self.tries >= self.MAX_CORRECTIONS:
            ok = "on target" if abs(err) <= self.TOL_IN else "best effort"
            self.status = f"{self.label} @ {self.target:.1f} in: {ok}, error {err:+.2f} in"
            print(self.status)
            return
        self.tries += 1
        nudge = int(round(err * self.lcal.steps_per_inch(x)))
        if nudge == 0:
            nudge = 1 if err * self.lcal.steps_per_inch(x) > 0 else -1
        print(f"  correction {self.tries}: laser at {x:.2f}, error {err:+.2f} in, "
              f"nudge {nudge:+d} steps")
        self.steps += nudge
        self._move(now)


# --------------------------------------------------------------- simulator ---

class FakeRig:
    """Pretend stepper + line laser, for testing without hardware.

    Laser sits DIST_IN from the wall, aimed at AIM_IN when at step 0. A small
    built-in error (ERR_DEG) makes the simulated lookup table imperfect so the
    correction step has something to fix.
    """

    DEG_PER_STEP = 360 / 4096   # 28BYJ-48 in half-step mode
    DIST_IN = 30.0
    ERR_DEG = 0.4

    def __init__(self, aim_in):
        self.aim_in = aim_in
        self.target = 0
        self.pos = 0.0
        self.on = False
        self.calls = 0

    def command(self, cmd):
        parts = cmd.split()
        if parts[0] == "G":
            self.target = int(parts[1])
        elif parts[0] == "Z":
            self.pos = self.target = 0
        elif parts[0] == "L":
            self.on = parts[1] == "1"

    def x_in(self):
        # Simulated backlash/slop: a small error that varies with position.
        angle = math.radians(self.pos * self.DEG_PER_STEP
                             + self.ERR_DEG * math.sin(self.pos / 90))
        return self.aim_in + self.DIST_IN * math.tan(angle)

    def draw(self, frame, calib, dt):
        """Move toward the target at ~500 steps/s and draw the line on the wall."""
        step = 500 * dt
        self.pos += max(-step, min(step, self.target - self.pos))
        if not (self.on and calib.ready):
            return
        x = self.x_in()
        (_, y0), (_, y1) = calib.wall_in.min(0), calib.wall_in.max(0)
        top, bot = calib.in_to_px([(x, y0 - 1), (x, y1 + 1)]).astype(int)
        cv2.line(frame, tuple(top), tuple(bot), (40, 40, 255), 6)
