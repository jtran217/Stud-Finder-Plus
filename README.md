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
python host/find_camera.py               # which index is the iPhone?
python host/web.py --tape                # web page at http://localhost:8000
python host/web.py --tape --serial       # with the Pro Micro
python host/web.py --tape --fake-laser   # simulated laser + motor
python host/main.py --tape               # same thing in an OpenCV window (backup)
```
Both take the same options (`--camera N`, `--serial`, `--tape`, `--fake-laser`).
The web page walks you through setup: click the 4 tape crosses on the video,
then the colored object. Keyboard shortcuts work on the page and in the window:
`c` redo corners, `t` re-pick color, `space` fake stud signal, `r` clear studs,
`m` switch views, `k` calibrate laser, `n` next stud, `l` laser on/off.

Edit the settings at the top of `host/app.py`: `WALL_CORNERS_IN` (your measured
tape crosses), `SENSOR_OFFSET_IN`, `LASER_STEP_RANGE`.

`--tape` tracks any brightly colored object on the stud finder (avoid red, the
laser is red). Without it, the program tracks ArUco marker 10
(`python markers/gen_markers.py --show` makes the markers).

## Layout
- `host/` laptop code (Python + OpenCV)
  - `app.py` the core (tracking, stud map, laser); `web.py` + `web/` the browser
    page; `main.py` the OpenCV window; `vision.py`, `laser.py`, `serial_link.py`
- `markers/` ArUco markers (DICT_4X4_50; ID 10 = stud finder, 0-3 = wall corners)
- `firmware/` Pro Micro code (PlatformIO)

Serial protocol (115200): Arduino sends `S1`/`S0 <millis>`, `OK`/`ERR`;
laptop sends `G <steps>`, `Z`, `L 1|0`, `P`.

## Laser (stretch goal)
Calibrate (`k`) sweeps the motor and learns steps -> inches; then click a stud
in the wall x-ray (or press `n`) to point the laser at it. Set
`LASER_STEP_RANGE` in `host/app.py` so the sweep covers the wall. Step 0 is
where the motor sits at power-up, aimed roughly at the middle of the wall.
The detector looks for bright red, so a dim room or lower exposure helps;
check it with the laser mask view.

