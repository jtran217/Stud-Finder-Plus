"""Stud Mapper in the browser.

  python host/web.py --tape                    # then open http://localhost:8000
  python host/web.py --tape --fake-laser       # with the simulated laser
  python host/web.py --tape --serial           # with the Pro Micro
  python host/web.py --tape --host 0.0.0.0     # also reachable from a phone on the same Wi-Fi

http://localhost:8000/?still shows one frame instead of live video (screenshots).

Same options as main.py. The page is a React app in host/web; build it once
with `npm install && npm run build` (in host/web). For live-reload while
editing the page, run `npm run dev` there and open http://localhost:5173.
"""
import argparse
import json
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cv2

from app import StudApp
from main import add_common_args, open_camera

DIST = (Path(__file__).parent / "web" / "dist").resolve()
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}
NOT_BUILT = b"""<!doctype html><meta charset="utf-8"><title>Stud Mapper</title>
<p style="font:16px sans-serif;margin:2rem">The web page isn't built yet. Run
<code>cd host/web && npm install && npm run build</code>, then reload.</p>"""
STREAM_WIDTH = 1280      # video is scaled to this width for the browser
JPEG_QUALITY = 80


class FrameHub:
    """Runs the camera loop and holds the latest JPEG for the video stream."""

    def __init__(self, cap, app):
        self.cap, self.app = cap, app
        self.jpeg = None
        self.seq = 0
        self.cond = threading.Condition()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok:
                time.sleep(0.01)
                continue
            out = self.app.process(frame)
            h, w = out.shape[:2]
            if w > STREAM_WIDTH:
                out = cv2.resize(out, (STREAM_WIDTH, int(h * STREAM_WIDTH / w)))
            ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                with self.cond:
                    self.jpeg = buf.tobytes()
                    self.seq += 1
                    self.cond.notify_all()

    def wait_frame(self, last_seq, timeout=2.0):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq or not self.running, timeout)
            return self.seq, self.jpeg


def make_handler(app, hub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):   # keep the terminal quiet
            pass

        def _send(self, body, ctype, status=HTTPStatus.OK):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, data, status=HTTPStatus.OK):
            # default=: numpy numbers (float32 etc.) become plain Python numbers
            self._send(json.dumps(data, default=lambda o: o.item()).encode(),
                       "application/json", status)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/api/state":
                self._json(app.state())
            elif path == "/stream.mjpg":
                self._stream()
            elif path == "/snapshot.jpg":     # one still frame (for slides/screenshots)
                _, jpeg = hub.wait_frame(-1)
                self._send(jpeg or b"", "image/jpeg")
            else:
                self._static(path)

        def _static(self, path):
            if not (DIST / "index.html").exists():
                return self._send(NOT_BUILT, "text/html; charset=utf-8")
            file = (DIST / path.lstrip("/")).resolve()
            if path == "/" or not file.is_file():
                file = DIST / "index.html"
            if not file.is_relative_to(DIST):     # no ../ escapes
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            ctype = CONTENT_TYPES.get(file.suffix, "application/octet-stream")
            self._send(file.read_bytes(), ctype)

        def do_POST(self):
            try:
                n = int(self.headers.get("Content-Length", 0))
                data = json.loads(self.rfile.read(n) or b"{}")
            except ValueError:
                return self._json({"error": "bad json"}, HTTPStatus.BAD_REQUEST)
            if self.path == "/api/click":
                # x, y arrive as fractions of the image (0-1), so the page's
                # display size doesn't matter.
                if app.frame_size:
                    w, h = app.frame_size
                    app.click(float(data["x"]) * w, float(data["y"]) * h)
                self._json({"ok": True})
            elif self.path == "/api/command":
                app.command(str(data.get("name", "")), data.get("arg"))
                self._json({"ok": True})
            else:
                self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def _stream(self):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seq = -1
            try:
                while hub.running:
                    seq, jpeg = hub.wait_frame(seq)
                    if jpeg is None:
                        continue
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n"
                                     b"Content-Length: " + str(len(jpeg)).encode() +
                                     b"\r\n\r\n" + jpeg + b"\r\n")
            except (BrokenPipeError, ConnectionResetError):
                pass   # browser tab closed

    return Handler


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    ap.add_argument("--host", default="127.0.0.1",
                    help="0.0.0.0 to allow other devices on the network")
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    args = ap.parse_args()

    cap = open_camera(args.camera)
    app = StudApp(serial=args.serial, port=args.port, tape=args.tape,
                  fake_laser=args.fake_laser, wall_size=args.wall, ask_wall_size=True)
    hub = FrameHub(cap, app)

    server = ThreadingHTTPServer((args.host, args.http_port), make_handler(app, hub))
    server.daemon_threads = True
    url = f"http://localhost:{args.http_port}"
    print(f"Stud Mapper running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        hub.running = False
        server.server_close()
        app.close()
        cap.release()


if __name__ == "__main__":
    main()
