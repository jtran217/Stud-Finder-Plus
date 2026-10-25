"""Session log for digging into failures after a run.

Each run of the app writes to host/logs/<date-time>/:
  events.log   one line per event, e.g.
               19:52:03.418 [stud] S1 x=12.31 v=+3.2 dir=right -> paired ...
  snaps/       a camera frame (with the overlays) whenever something fails:
               a stud edge ignored, an edge pair rejected, calibration failed,
               the tracker lost for a while...

Categories: serial (every line in/out of both boards), stud, tracker, laser,
motor, calib, flow (steps), cmd (page actions), beat (1 s heartbeat), warn.
host/logs is gitignored.
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
    SNAP_GAP_S = 0.5    # at most 2 snapshots a second

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.lock = threading.Lock()
        self.snaps = 0
        self._last_snap = 0.0
        self.pending = []   # snapshot reasons, written after the frame is drawn
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
            pass   # logging must never stop the app (disk full, closed on exit)

    def snap(self, why):
        """Ask for a snapshot of the current frame (saved once it's drawn)."""
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
