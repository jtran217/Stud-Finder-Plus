"""Per-run debug log: host/logs/<date-time>/events.log + snaps/.

    19:52:03.418 [stud] S1 0 -> paired with edge @ 11.25 in ...  x=12.31 dir=-1

Categories: serial, stud, tracker, laser, motor, flow, cmd, app, beat (1/s),
snap. Snapshots get saved when something goes wrong (edge ignored, tracker
lost, calibration failed...).
"""
import threading
import time
from pathlib import Path

import cv2

LOG_DIR = Path(__file__).parent / "logs"


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}"
    if v is None:
        return "-"
    return str(v)


class Diag:
    MAX_SNAPS = 300
    SNAP_GAP_S = 0.5

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.lock = threading.Lock()
        self.snaps = 0
        self._last_snap = 0.0
        self.pending = []   # saved once the frame has its overlays drawn
        if not enabled:
            self.dir = None
            return
        self.dir = LOG_DIR / time.strftime("%Y%m%d-%H%M%S")
        (self.dir / "snaps").mkdir(parents=True, exist_ok=True)
        self.f = open(self.dir / "events.log", "a", buffering=1)
        print(f"diagnostics log: {self.dir / 'events.log'}")

    def write(self, cat, msg, **fields):
        if not self.enabled:
            return
        t = time.time()
        stamp = time.strftime("%H:%M:%S", time.localtime(t)) + f".{int(t % 1 * 1000):03d}"
        line = f"{stamp} [{cat}] {msg}"
        if fields:
            line += "  " + " ".join(f"{k}={_fmt(v)}" for k, v in fields.items())
        try:
            with self.lock:
                self.f.write(line + "\n")
        except (OSError, ValueError):
            pass   # never let logging take the app down

    def snap(self, why):
        if self.enabled:
            self.pending.append(why)

    def flush_snaps(self, frame, now):
        if not self.pending:
            return
        reasons, self.pending = self.pending, []
        if self.snaps >= self.MAX_SNAPS or now - self._last_snap < self.SNAP_GAP_S:
            return
        self._last_snap = now
        self.snaps += 1
        tag = "-".join(r.replace(" ", "_") for r in reasons)[:60]
        name = f"{time.strftime('%H%M%S')}-{self.snaps:03d}-{tag}.jpg"
        try:
            cv2.imwrite(str(self.dir / "snaps" / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        except cv2.error:
            return
        self.write("snap", name, why=",".join(reasons))

    def close(self):
        if self.enabled:
            self.enabled = False
            with self.lock:
                self.f.close()
