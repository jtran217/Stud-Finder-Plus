"""Find which camera index is the iPhone (Continuity Camera).

Tries indices 0-3, prints the resolution each one actually gives,
and shows one frame per camera. Press any key to go to the next one.
Quit Photo Booth / FaceTime first, or the camera may be busy.
"""
import cv2

WANT_W, WANT_H = 1920, 1080

for idx in range(4):
    cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print(f"[{idx}] not available")
        continue
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WANT_W)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, WANT_H)

    # First few frames are often black while the camera warms up.
    frame = None
    for _ in range(15):
        ok, frame = cap.read()
    cap.release()

    if frame is None:
        print(f"[{idx}] opened but returned no frames (check camera permissions)")
        continue

    h, w = frame.shape[:2]
    print(f"[{idx}] {w}x{h}  mean brightness={frame.mean():.0f}")
    preview = cv2.resize(frame, (w // 2, h // 2))
    cv2.putText(preview, f"camera {idx}  {w}x{h}  (any key = next)", (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow("find_camera", preview)
    cv2.waitKey(0)

cv2.destroyAllWindows()
print("Use the iPhone's index with:  python host/main.py --camera N")
