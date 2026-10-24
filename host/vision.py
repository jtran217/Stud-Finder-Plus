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
        """Load saved clicks if they match the current wall points and resolution."""
        if not CALIB_PATH.exists():
            return False
        d = json.loads(CALIB_PATH.read_text())
        if d["frame_size"] != list(frame_size) or \
                not np.allclose(d["wall_in"], self.wall_in):
            return False
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
