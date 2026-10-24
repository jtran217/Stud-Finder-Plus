"""Stud Mapper in an OpenCV window (backup for the web page in web.py).

  python host/main.py --camera 0                  # space bar = fake stud signal
  python host/main.py --camera 0 --serial         # real Pro Micro on /dev/cu.usbmodem*
  python host/main.py --camera 0 --tape           # track a colored object, not marker 10
  python host/main.py --fake-laser                # simulated laser + motor

Keys:  c = re-click wall corners   r = reset studs   space = fake stud signal
       t = re-click object color   m = cycle views (video / object mask / laser mask)
       k = calibrate laser   n = aim laser at next stud   l = laser on/off   q = quit

First run: click the 4 tape crosses in order TL, TR, BR, BL (saved to
host/calib.json; press c if the tripod moves). With --tape, then click the
colored object once. --wall 24x12 sets the distance between the crosses
(otherwise the saved size, or the default at the top of host/app.py).
"""
import argparse

import cv2

from app import StudApp

DISPLAY_SCALE = 0.6   # so a 1080p frame fits on a laptop screen

KEYS = {
    ord("c"): "recalibrate",
    ord("r"): "reset_studs",
    ord(" "): "stud_signal",
    ord("t"): "resample_object",
    ord("m"): "view",
    ord("k"): "laser_calibrate",
    ord("n"): "next_stud",
    ord("l"): "laser_toggle",
}


def open_camera(index):
    cap = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    ok, frame = cap.read()
    if not ok:
        raise SystemExit(f"Camera {index} gave no frame. Run host/find_camera.py.")
    print(f"camera {index}: {frame.shape[1]}x{frame.shape[0]}")
    return cap


def wall_size(text):
    """'24x12' -> (24.0, 12.0)"""
    try:
        w, h = (float(v) for v in text.lower().replace("by", "x").split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT in inches, e.g. 24x12")
    return w, h


def add_common_args(ap):
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--serial", action="store_true", help="use the real Pro Micro")
    ap.add_argument("--port", default=None, help="serial port (default: host/ports.json, else the first usbmodem)")
    ap.add_argument("--tape", action="store_true",
                    help="track a colored object on the stud finder instead of marker 10")
    ap.add_argument("--fake-laser", action="store_true",
                    help="simulate the laser + motor (draws a red line on the video)")
    ap.add_argument("--wall", type=wall_size, default=None, metavar="WxH",
                    help="distance between the tape crosses in inches, e.g. 24x12 "
                         "(default: the saved size)")


def draw_hud(frame, lines):
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (20, 50 + i * 45), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0, 0, 0), 6)
        cv2.putText(frame, text, (20, 50 + i * 45), cv2.FONT_HERSHEY_SIMPLEX,
                    1.2, (0, 255, 0), 2)


def main():
    ap = argparse.ArgumentParser()
    add_common_args(ap)
    args = ap.parse_args()

    cap = open_camera(args.camera)
    app = StudApp(serial=args.serial, port=args.port, tape=args.tape,
                  fake_laser=args.fake_laser, wall_size=args.wall)

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            app.click(x / DISPLAY_SCALE, y / DISPLAY_SCALE)

    win = "Stud Mapper"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_mouse)

    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        out = app.process(frame)
        draw_hud(out, app.hud_lines())
        cv2.imshow(win, cv2.resize(out, None, fx=DISPLAY_SCALE, fy=DISPLAY_SCALE))
        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key in KEYS:
            app.command(KEYS[key])

    app.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
