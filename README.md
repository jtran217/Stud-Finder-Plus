# Stud Finder Plus

A $15 stud finder + Arduino + iPhone camera that maps every stud on a wall,
and (stretch) points a laser at it.

## Setup (laptop)
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run
```
python markers/gen_markers.py --show   # make markers; show marker 10 to test
python host/find_camera.py             # which index is the iPhone?
python host/main.py --camera N         # space bar = fake stud signal
python host/main.py --camera N --serial  # with the Pro Micro
```
Edit `WALL_CORNERS_IN` at the top of `host/main.py` to your measured tape crosses.
Keys: `c` re-calibrate, `r` reset studs, `space` fake signal, `q` quit.

## Layout
- `host/` laptop code (Python + OpenCV)
- `markers/` ArUco markers (DICT_4X4_50; ID 10 = stud finder, 0-3 = wall corners)
- `firmware/` Pro Micro code (PlatformIO)

Serial protocol (115200): Arduino sends `S1`/`S0 <millis>`, `OK`/`ERR`;
laptop sends `G <steps>`, `Z`, `L 1|0`, `P`.
