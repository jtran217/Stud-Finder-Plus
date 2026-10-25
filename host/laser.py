"""Laser line: find it on the wall, map motor steps to inches, aim at studs.

The camera closes the loop since the stepper only knows step counts. FakeRig
stands in for the motor + laser when testing without hardware.
"""
import json
import math
from collections import deque
from pathlib import Path

import cv2
import numpy as np

LASER_CALIB_PATH = Path(__file__).parent / "laser_calib.json"

log = print   # app.py swaps this for its own logger


class LaserDetector:
    """Finds the vertical red line on a straight-on warp of the wall.

    Works by contrast, not fixed color cutoffs, so a faint line in daylight
    still shows: each pixel gets a redness score (red minus the stronger of
    green/blue), each row has its own median subtracted (evens out lighting),
    then the columns are averaged. The line is the column that stands out
    from the wall on either side of it."""

    PX_PER_IN = 20
    MARGIN_IN = 2.0       # look a bit past the corner crosses
    BASELINE_IN = 4.0     # wall color is judged over this width around each column
    MIN_CONTRAST = 2.5    # peak must be this much redder than its surroundings (0-255 scale)
    MIN_SNR = 6.0         # ...and this many times the column-to-column noise
    MIN_FRAC = 0.3        # line has to cover this much of the wall height

    def __init__(self):
        self.mask = None
        self.stats = {}   # numbers behind the last decision, for the log
        self.why = ""

    def find(self, frame, calib):
        """x of the laser line in wall inches, or None."""
        self.stats = {}
        if not calib.ready:
            self.why = "no wall box"
            return None
        (x0, y0), (x1, y1) = calib.wall_in.min(0), calib.wall_in.max(0)
        x0 -= self.MARGIN_IN
        x1 += self.MARGIN_IN
        p = self.PX_PER_IN
        w, h = int((x1 - x0) * p), int((y1 - y0) * p)
        to_wall = np.array([[p, 0, -x0 * p], [0, p, -y0 * p], [0, 0, 1]]) @ calib.H
        wall = cv2.warpPerspective(frame, to_wall, (w, h)).astype(np.float32)

        b, g, r = cv2.split(wall)
        red = r - np.maximum(g, b)
        red -= np.median(red, axis=1, keepdims=True)
        # "Laser mask" view: how much redder than its row each pixel is
        self.mask = np.clip(red * 12, 0, 255).astype(np.uint8)

        prof = red.mean(axis=0)
        k = int(self.BASELINE_IN * p) | 1
        if w <= k:
            return None
        pad = np.pad(prof, k // 2, mode="edge")
        base = np.median(np.lib.stride_tricks.sliding_window_view(pad, k), axis=1)
        lift = prof - base
        noise = max(1.4826 * float(np.median(np.abs(lift - np.median(lift)))), 0.3)

        peak = int(lift.argmax())
        self.stats = {"contrast": float(lift[peak]), "noise": noise,
                      "snr": float(lift[peak] / noise), "peak_in": float(x0 + (peak + 0.5) / p)}
        if lift[peak] < max(self.MIN_CONTRAST, self.MIN_SNR * noise):
            self.why = "no column stands out enough"
            return None
        # the line should run down most of the wall, not be one red blob
        a, b2 = max(peak - p // 4, 0), min(peak + p // 4 + 1, w)
        band = red[:, a:b2].mean(axis=1) - base[a:b2].mean()   # same averaging on both sides
        cover = float((band > 0.4 * lift[a:b2].mean()).mean())
        self.stats["cover"] = cover
        if cover < self.MIN_FRAC:
            self.why = "red patch, but not a line down the wall"
            return None
        self.why = ""
        # weighted center over +-0.75 in around the peak for sub-pixel x
        a, b2 = max(peak - 3 * p // 4, 0), min(peak + 3 * p // 4 + 1, w)
        wts = np.clip(lift[a:b2], 0, None)
        cx = float((np.arange(a, b2) * wts).sum() / wts.sum())
        return float(x0 + (cx + 0.5) / p)


class Stepper:
    """Sends G commands and remembers where we told the motor to go, so we
    can guess how long a move takes."""

    STEPS_PER_S = 700   # matches STEP_US in the firmware

    def __init__(self, send):
        self.send = send
        self.pos = None   # unknown until the first move

    def move(self, steps):
        """Returns the expected travel time in seconds."""
        travel = abs(steps - self.pos) / self.STEPS_PER_S if self.pos is not None else 1.5
        self.pos = steps
        self.send(f"G {steps}")
        return travel


class Settler:
    """Waits for the laser reading to stop moving after a move."""

    MIN_WAIT_S = 0.3
    WINDOW_S = 0.3
    TOL_IN = 0.1
    MISS_S = 0.8        # nothing seen this long after arriving -> off the wall
    TIMEOUT_S = 4.0

    def __init__(self, now, travel_s=0.0):
        self.t0 = now
        self.wait = self.MIN_WAIT_S + travel_s
        self.samples = deque()
        self.seen = False

    def update(self, now, x):
        """Returns (done, x). x is None if we never saw the laser."""
        elapsed = now - self.t0
        if elapsed < self.wait:
            return False, None
        if x is not None:
            self.samples.append((now, x))
            self.seen = True
        while self.samples and self.samples[0][0] < now - self.WINDOW_S:
            self.samples.popleft()
        xs = [x for _, x in self.samples]
        span = self.samples[-1][0] - self.samples[0][0] if self.samples else 0
        if len(xs) >= 3 and span >= self.WINDOW_S * 0.8 and max(xs) - min(xs) < self.TOL_IN:
            return True, float(np.median(xs))
        if not self.seen and elapsed > self.wait + self.MISS_S:
            return True, None
        if elapsed > self.wait + self.TIMEOUT_S:
            return True, (float(np.median(xs)) if xs else None)
        return False, None


class LaserCalibration:
    """Builds the steps <-> inches table in two passes:
      1. explore: step out from 0 both ways until the line leaves the wall,
         then bisect to pin down each edge
      2. measure: sweep left to right across that range, recording points
    Measuring in one direction keeps gear backlash out of the table."""

    EXPLORE_STEP = 100
    REFINE_ROUNDS = 3   # 100 -> 50 -> 25 -> 12 steps
    POINT_SPACING = 40
    MIN_POINTS, MAX_POINTS = 8, 25
    PRELOAD = 40        # start the sweep a bit left of the first point

    def __init__(self, stepper, max_steps=900):
        self.stepper = stepper
        self.max_steps = max_steps
        self.points = []   # (steps, inches)
        self.settler = None
        self.status = "not calibrated (press k)"
        self.load()

    @property
    def running(self):
        return self.settler is not None

    @property
    def ready(self):
        return len(self.points) >= 3 and not self.running

    def start(self, now):
        self.points = []
        self.phase = "explore"
        self.dir = 1
        self.misses = 0
        self.edge = {1: None, -1: None}
        self.refine = None   # (last seen, first missed, rounds left)
        self.stepper.send("L 1")
        self._go(0, now)

    def _go(self, steps, now):
        self.current = steps
        self.settler = Settler(now, self.stepper.move(steps))
        if self.phase == "explore":
            self.status = f"calibrating: finding the wall edges (step {steps:+d})"
        elif self.phase == "measure":
            self.status = f"calibrating: measuring {len(self.points) + 1}/{len(self.todo) + len(self.points) + 1}"

    def update(self, now, laser_x):
        if not self.running:
            return
        done, x = self.settler.update(now, laser_x)
        if not done:
            return
        self.settler = None
        if self.phase == "explore":
            self._explore(x, now)
        elif self.phase == "preload":
            self.phase = "measure"
            self._go(self.todo.pop(0), now)
        else:
            if x is None:
                log(f"  step {self.current:5d} -> laser not seen")
            else:
                log(f"  step {self.current:5d} -> {x:6.2f} in")
                self.points.append((self.current, x))
            if self.todo:
                self._go(self.todo.pop(0), now)
            else:
                self._finish()

    def _explore(self, x, now):
        if self.current == 0 and x is None:
            self._fail("laser not on the wall at step 0, aim it at the middle of the wall")
            return

        if self.refine:
            seen, missed, rounds = self.refine
            if x is not None:
                seen = self.edge[self.dir] = self.current
            else:
                missed = self.current
            if rounds > 1:
                self.refine = (seen, missed, rounds - 1)
                self._go((seen + missed) // 2, now)
            else:
                self.refine = None
                self._next_side(now)
            return

        if x is not None:
            self.edge[self.dir] = self.current
            self.misses = 0
        else:
            self.misses += 1
        nxt = self.current + self.dir * self.EXPLORE_STEP
        if abs(nxt) > self.max_steps:
            self._next_side(now)
        elif self.misses >= 2:
            edge = self.edge[self.dir]
            if edge is None:
                self._next_side(now)
            else:   # the edge is somewhere in the 100 steps past the last hit
                missed = edge + self.dir * self.EXPLORE_STEP
                self.refine = (edge, missed, self.REFINE_ROUNDS)
                self._go((edge + missed) // 2, now)
        else:
            self._go(nxt, now)

    def _next_side(self, now):
        if self.dir == 1:
            self.dir, self.misses = -1, 0
            self._go(-self.EXPLORE_STEP, now)
        else:
            self._plan_sweep(now)

    def _plan_sweep(self, now):
        lo, hi = self.edge[-1] or 0, self.edge[1] or 0
        if hi - lo < self.EXPLORE_STEP:
            self._fail("laser only seen near the center, is the camera seeing the wall?")
            return
        n = int(np.clip((hi - lo) // self.POINT_SPACING + 1, self.MIN_POINTS, self.MAX_POINTS))
        self.todo = [int(round(v)) for v in np.linspace(lo, hi, n)]
        log(f"  wall spans steps {lo:+d} to {hi:+d}, measuring {n} points")
        self.phase = "preload"
        self._go(lo - self.PRELOAD, now)

    def _fail(self, why):
        self.settler = None
        self.points = []
        self.status = f"calibration FAILED: {why}"
        log(self.status)

    def _finish(self):
        if len(self.points) < 3:
            self._fail(f"laser seen at only {len(self.points)} positions")
            return
        inches = np.array([x for _, x in self.points])
        d = np.diff(inches)
        if not (np.all(d > 0) or np.all(d < 0)):
            log("warning: laser positions are out of order, some readings may be off")
        self.save()
        self.status = f"calibrated: {len(self.points)} pts, {inches.min():.1f}-{inches.max():.1f} in"
        log(self.status)

    def _table(self):
        pts = sorted(self.points, key=lambda p: p[1])
        return np.array([x for _, x in pts]), np.array([s for s, _ in pts], dtype=float)

    def in_range(self, x):
        inches, _ = self._table()
        return inches[0] <= x <= inches[-1]

    def steps_for(self, x):
        inches, steps = self._table()
        return float(np.interp(x, inches, steps))

    def steps_per_inch(self, x):
        return (self.steps_for(x + 0.25) - self.steps_for(x - 0.25)) / 0.5

    def save(self):
        LASER_CALIB_PATH.write_text(json.dumps({"points": self.points}, indent=2))

    def load(self):
        try:
            self.points = [tuple(p) for p in json.loads(LASER_CALIB_PATH.read_text())["points"]]
        except (OSError, ValueError, KeyError):
            return
        if len(self.points) >= 3:
            self.status = f"calibrated: {len(self.points)} pts (loaded, k to redo)"


class Aimer:
    """Moves to the stud using the table, then nudges based on where the
    camera actually sees the line. Every move ends going left to right
    (like the calibration sweep) so gear backlash doesn't add error."""

    TOL_IN = 0.15
    MAX_CORRECTIONS = 3
    PRELOAD = 40

    def __init__(self, stepper, lcal):
        self.stepper = stepper
        self.lcal = lcal
        self.settler = None
        self.preloading = False
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
            log(f"warning: {target:.1f} in is outside the calibrated range, extrapolating")
        self.target, self.label, self.tries = target, label, 0
        self.steps = int(round(self.lcal.steps_for(target)))
        self.stepper.send("L 1")
        self._move(now)

    def _move(self, now):
        pos = self.stepper.pos
        self.preloading = pos is not None and self.steps < pos
        dest = self.steps - self.PRELOAD if self.preloading else self.steps
        self.settler = Settler(now, self.stepper.move(dest))
        self.status = f"aiming at {self.label} {self.target:.1f} in ..."

    def update(self, now, laser_x):
        if not self.running:
            return
        done, x = self.settler.update(now, laser_x)
        if not done:
            return
        self.settler = None
        if self.preloading:              # now come back from the left
            self.preloading = False
            self.settler = Settler(now, self.stepper.move(self.steps))
            return
        if x is None:
            self.status = f"{self.label}: laser not seen after move"
            return

        err = self.target - x
        if abs(err) <= self.TOL_IN or self.tries >= self.MAX_CORRECTIONS:
            result = "on target" if abs(err) <= self.TOL_IN else "best effort"
            self.status = f"{self.label} @ {self.target:.1f} in: {result}, error {err:+.2f} in"
            log(self.status)
            return

        self.tries += 1
        nudge = err * self.lcal.steps_per_inch(x)
        nudge = int(round(nudge)) or (1 if nudge > 0 else -1)
        log(f"  correction {self.tries}: laser at {x:.2f}, error {err:+.2f} in, nudge {nudge:+d} steps")
        self.steps += nudge
        self._move(now)


class FakeRig:
    """Simulated stepper + laser. Draws a red line onto the frame so the
    detector, calibration and aiming can run without hardware. ERR_DEG adds
    some position-dependent error so the corrections have work to do."""

    DEG_PER_STEP = 360 / 4096   # 28BYJ-48, half-stepping
    DIST_IN = 30.0
    ERR_DEG = 0.4
    STEPS_PER_S = Stepper.STEPS_PER_S

    def __init__(self, aim_in):
        self.aim_in = aim_in    # where step 0 points
        self.target = 0
        self.pos = 0.0
        self.on = False

    def command(self, cmd):
        parts = cmd.split()
        if parts[0] == "G":
            self.target = int(parts[1])
        elif parts[0] == "Z":
            self.pos = self.target = 0
        elif parts[0] == "L":
            self.on = parts[1] == "1"

    def x_in(self):
        angle = math.radians(self.pos * self.DEG_PER_STEP + self.ERR_DEG * math.sin(self.pos / 90))
        return self.aim_in + self.DIST_IN * math.tan(angle)

    def draw(self, frame, calib, dt):
        step = self.STEPS_PER_S * dt
        self.pos += max(-step, min(step, self.target - self.pos))
        if not (self.on and calib.ready):
            return
        x = self.x_in()
        (_, y0), (_, y1) = calib.wall_in.min(0), calib.wall_in.max(0)
        top, bot = calib.in_to_px([(x, y0 - 1), (x, y1 + 1)]).astype(int)
        cv2.line(frame, tuple(top), tuple(bot), (40, 40, 255), 6)
