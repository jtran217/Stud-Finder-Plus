"""Generate ArUco markers (DICT_4X4_50).

  python markers/gen_markers.py          -> PNGs for IDs 0-3 and 10
  python markers/gen_markers.py --show   -> also show marker 10 full-screen
                                            (hold your phone/laptop up to the camera)

Also prints marker 10 as a 6x6 grid so you can hand-draw it.
"""
import sys
from pathlib import Path

import cv2

DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
IDS = [0, 1, 2, 3, 10]
CELLS = 6          # 4x4 data cells + 1-cell black border on each side
CELL_PX = 100
OUT = Path(__file__).parent


def make(marker_id):
    img = cv2.aruco.generateImageMarker(DICT, marker_id, CELLS * CELL_PX)
    # White margin (one cell) so the detector can find the black border.
    return cv2.copyMakeBorder(img, CELL_PX, CELL_PX, CELL_PX, CELL_PX,
                              cv2.BORDER_CONSTANT, value=255)


def grid_text(marker_id):
    img = cv2.aruco.generateImageMarker(DICT, marker_id, CELLS * CELL_PX)
    rows = []
    for r in range(CELLS):
        row = ""
        for c in range(CELLS):
            v = img[r * CELL_PX + CELL_PX // 2, c * CELL_PX + CELL_PX // 2]
            row += "██" if v < 128 else "··"
        rows.append(row)
    return "\n".join(rows)


if __name__ == "__main__":
    for i in IDS:
        path = OUT / f"marker_{i}.png"
        cv2.imwrite(str(path), make(i))
        print(f"wrote {path}")

    print("\nMarker 10 for hand-drawing (██ = fill black, ·· = leave white),")
    print("top row is the top of the marker. Keep a white margin around it:\n")
    print(grid_text(10))

    if "--show" in sys.argv:
        cv2.namedWindow("marker 10", cv2.WND_PROP_FULLSCREEN)
        cv2.setWindowProperty("marker 10", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
        cv2.imshow("marker 10", make(10))
        print("\nShowing marker 10. Press any key to close.")
        cv2.waitKey(0)
