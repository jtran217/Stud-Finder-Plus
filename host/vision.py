"""Marker detection and the pixel <-> wall-inches mapping."""
import json
from pathlib import Path

import cv2
import numpy as np

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
_detector = cv2.aruco.ArucoDetector(DICT, cv2.aruco.DetectorParameters())

FINDER_ID = 10
CALIB_PATH = Path(__file__).parent / "calib.json"


def detect(frame):
    """Return {marker_id: 4x2 corner array in pixels}."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = _detector.detectMarkers(gray)
    if ids is None:
        return {}
    return {int(i): c.reshape(4, 2) for i, c in zip(ids.flatten(), corners)}


def draw_markers(frame, markers):
    for mid, c in markers.items():
        pts = c.astype(int)
        color = (0, 255, 255) if mid == FINDER_ID else (255, 128, 0)
        cv2.polylines(frame, [pts], True, color, 3)
        cv2.putText(frame, str(mid), tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, color, 3)


class Calibration:
    """Maps image pixels to wall inches using 4 reference points.

    wall_in: the 4 reference points in inches, order TL, TR, BR, BL.
    px:      the same 4 points in image pixels (clicked, or marker centers later).
    """

    def __init__(self, wall_in):
        self.wall_in = np.array(wall_in, dtype=np.float32)
        self.px = None
        self.H = None       # pixels -> inches
        self.H_inv = None   # inches -> pixels

    @property
    def ready(self):
        return self.H is not None

    def set_wall(self, wall_in):
        """Change the reference points' inch positions (keeps the clicks)."""
        self.wall_in = np.array(wall_in, dtype=np.float32)
        if self.px is not None:
            self.set_pixels(self.px)

    def set_pixels(self, px_points):
        self.px = np.array(px_points, dtype=np.float32)
        self.H, _ = cv2.findHomography(self.px, self.wall_in)
        self.H_inv = np.linalg.inv(self.H)

    def px_to_in(self, pts):
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.H).reshape(-1, 2)

    def in_to_px(self, pts):
        pts = np.asarray(pts, dtype=np.float32).reshape(-1, 1, 2)
        return cv2.perspectiveTransform(pts, self.H_inv).reshape(-1, 2)

    # Wall extent in inches, used for drawing full-height stud lines.
    @property
    def y_range(self):
        return float(self.wall_in[:, 1].min()), float(self.wall_in[:, 1].max())

    def save(self, frame_size):
        CALIB_PATH.write_text(json.dumps({
            "wall_in": self.wall_in.tolist(),
            "px": self.px.tolist(),
            "frame_size": list(frame_size),
        }, indent=2))

    def load(self, frame_size):
        """Load the saved wall size and clicks (if taken at this resolution)."""
        if not CALIB_PATH.exists():
            return False
        d = json.loads(CALIB_PATH.read_text())
        if d["frame_size"] != list(frame_size):
            return False
        self.wall_in = np.array(d["wall_in"], dtype=np.float32)
        self.set_pixels(d["px"])
        return True


def finder_x(markers, calib, sensor_offset_in=0.0):
    """Stud finder's x position in inches, or None if marker 10 isn't visible.

    Transforms all 4 corners to inches and averages them (more accurate than
    transforming the pixel center). sensor_offset_in shifts from the marker's
    center to the stud finder's actual sensing point.
    """
    c = markers.get(FINDER_ID)
    if c is None or not calib.ready:
        return None
    return float(calib.px_to_in(c)[:, 0].mean()) + sensor_offset_in


class TapeTracker:
    """Tracks a patch of colored tape on the stud finder (alternative to marker 10).

    Click the tape once; its color is sampled from the live frame, so any tape
    color works under whatever lighting you have. Each frame, the blob of that
    color (inside the wall area, if calibrated) that best matches the tape's
    size and last position is the stud finder.
    """

    HUE_TOL = 10        # OpenCV hue runs 0-179
    MIN_AREA_PX = 300   # ignore specks smaller than this
    SIZE_TOL = 1.4      # keep blobs within e^1.4 = 4x of the tape's size (blur, tilt)
    LOCK_RADIUS_PX = 200  # first find after a click: nearest blob within this

    def __init__(self):
        self.lo = self.hi = None   # HSV bounds; hue may wrap past 179
        self.mask = None           # last threshold mask, for debugging
        self.last = None           # last tape center in pixels
        self.ref_area = None       # tape's blob area, learned on the first find
        self.why = "no color picked"   # why the last find failed (for the log)
        self.stats = {}            # blob counts/areas from the last find
        self.sampled = None        # (h, s, v) of the click

    @property
    def ready(self):
        return self.lo is not None

    def sample(self, frame, x, y, r=8):
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        patch = hsv[max(y - r, 0):y + r, max(x - r, 0):x + r].reshape(-1, 3)
        h, s, v = np.median(patch, axis=0)
        if s < 60:
            print(f"warning: clicked color is washed out (saturation {s:.0f}); "
                  "tracking may be unreliable. Use a more colorful tape.")
        self.lo = (h - self.HUE_TOL, max(s * 0.5, 50), max(v * 0.4, 40))
        self.hi = (h + self.HUE_TOL, 255, 255)
        self.last, self.ref_area = (x, y), None
        self.sampled = (float(h), float(s), float(v))
        print(f"tape color sampled: HSV ({h:.0f}, {s:.0f}, {v:.0f})")

    def _threshold(self, hsv):
        (h0, s0, v0), (h1, _, _) = self.lo, self.hi
        m = cv2.inRange(hsv, (max(h0, 0), s0, v0), (min(h1, 179), 255, 255))
        if h0 < 0:     # hue wraps around (reds)
            m |= cv2.inRange(hsv, (180 + h0, s0, v0), (179, 255, 255))
        if h1 > 179:
            m |= cv2.inRange(hsv, (0, s0, v0), (h1 - 180, 255, 255))
        return m

    def find(self, frame, calib=None, margin_in=2.0):
        """Return the tape's 4 corner points in pixels (like a marker), or None."""
        self.stats = {}
        if not self.ready:
            self.why = "no color picked"
            return None
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = self._threshold(hsv)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        if calib is not None and calib.ready:
            # Only look on the wall (plus a margin), so a blue shirt doesn't count.
            (x0, y0), (x1, y1) = calib.wall_in.min(0), calib.wall_in.max(0)
            m = margin_in
            area = calib.in_to_px([(x0 - m, y0 - m), (x1 + m, y0 - m),
                                   (x1 + m, y1 + m), (x0 - m, y1 + m)])
            wall = np.zeros_like(mask)
            cv2.fillPoly(wall, [area.astype(np.int32)], 255)
            mask &= wall
        self.mask = mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        self.stats["pixels"] = int(cv2.countNonZero(mask))
        if not contours:
            self.why = "no pixels of that color on the wall"
            return None
        blobs = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < self.MIN_AREA_PX:
                continue
            (cx, cy), _, _ = rect = cv2.minAreaRect(c)
            blobs.append((area, (cx, cy), rect, c))
        self.stats["blobs"] = len(blobs)
        self.stats["biggest"] = int(max((b[0] for b in blobs), default=0))
        if not blobs:
            self.why = f"only specks of that color (< {self.MIN_AREA_PX} px)"
            return None
        if self.ref_area is None:
            # First find after a click: the blob under the click is the tape,
            # or failing that the nearest one (the finder may have moved a bit).
            under = [b for b in blobs if cv2.pointPolygonTest(b[3], self.last, False) >= 0]
            if not under:
                near = [b for b in blobs if np.hypot(b[1][0] - self.last[0],
                                                     b[1][1] - self.last[1]) < self.LOCK_RADIUS_PX]
                under = sorted(near, key=lambda b: np.hypot(b[1][0] - self.last[0],
                                                            b[1][1] - self.last[1]))
            if not under:
                self.why = "no blob of that color near the click"
                return None
            best = under[0]
            self.ref_area = best[0]
            print(f"tape locked on: {best[0]:.0f} px blob")
        else:
            # Keep blobs roughly the tape's size, then prefer the one closest in
            # size and position to where the tape was last seen.
            size_err = lambda b: abs(np.log(b[0] / self.ref_area))
            sized = [b for b in blobs if size_err(b) < self.SIZE_TOL]
            if not sized:
                self.why = (f"blobs the wrong size (biggest {self.stats['biggest']} px, "
                            f"tape is {self.ref_area:.0f} px)")
                return None
            blobs = sized
            best = min(blobs, key=lambda b: size_err(b) + np.hypot(
                b[1][0] - self.last[0], b[1][1] - self.last[1]) / 300.0)
        self.last = best[1]
        self.stats["area"] = int(best[0])
        self.why = ""
        return cv2.boxPoints(best[2]).astype(np.float32)
