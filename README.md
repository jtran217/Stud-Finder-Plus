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

No marker? Put a ~2" square of bright painter's tape (blue is good; avoid red,
the laser is red) on the stud finder and add `--tape`. After the corner clicks,
click the tape once to sample its color. `t` re-samples, `m` shows the color mask.

## Layout
- `host/` laptop code (Python + OpenCV)
- `markers/` ArUco markers (DICT_4X4_50; ID 10 = stud finder, 0-3 = wall corners)
- `firmware/` Pro Micro code (PlatformIO)

Serial protocol (115200): Arduino sends `S1`/`S0 <millis>`, `OK`/`ERR`;
laptop sends `G <steps>`, `Z`, `L 1|0`, `P`.

## Laser (stretch goal)
Keys: `k` calibrate the laser (sweeps the motor and learns steps -> inches),
`n` aim at the next stud, `l` laser on/off, `m` cycles mask views.
Set `LASER_STEP_RANGE` in `host/main.py` so the sweep covers the wall.
Test without hardware: `python host/main.py --tape --fake-laser`
(draws a simulated laser line). The detector looks for bright red, so a dim
room or lower exposure helps; check it with the laser mask view (`m`).

