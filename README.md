# Stud Finder Plus

A $15 stud finder + Arduino + iPhone camera that maps every stud on a wall,
and (stretch) points a laser at it.

## Quick start
1. **Install** (once): see [Setup](#setup-laptop) below.
2. **Set up the wall:** 4 painter's tape crosses around the scan area, a
   bright non-red object taped to the stud finder, iPhone on the tripod
   facing the wall (Center Stage off).
3. **Run** (Pro Micro on USB, from the repo root):
   ```
   ./start.sh --flash   # first time, or after changing the firmware
   ./start.sh           # every other time
   ```
   It finds the Pro Micro's port, checks nothing else has it open, saves it
   in `host/ports.json`, optionally uploads the firmware, then starts the web
   page at http://localhost:8000 (it walks you through the wall setup). Each
   stud edge shows up in the terminal and the page's log. Extra options go to
   `web.py`, e.g. `./start.sh --camera 1`. Don't run `pio device monitor`
   alongside it; if the board drops off USB, the app reconnects by itself.
   Without the hardware: `python host/web.py --tape`, space = stud signal.
4. **Scan each stud from both sides:** hold the button with the finder flat
   on the wall left of the stud, slide right until the LED lights, release.
   Then press again right of the stud and slide left until it lights. The two
   edges make one stud on the map.

## Setup (laptop)
```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cd host/web && npm install && npm run build   # the web page (React + Vite)
```
For page development, run `npm run dev` in `host/web` alongside `web.py` and
open http://localhost:5173 (it proxies to the Python server).

## Run
```
python host/find_camera.py               # which index is the iPhone?
python host/web.py --tape                # web page at http://localhost:8000
python host/web.py --tape --serial       # with the Pro Micro (port: host/ports.json or --port)
python host/web.py --tape --fake-laser   # simulated laser + motor
python host/main.py --tape               # same thing in an OpenCV window (backup)
```
Both take the same options (`--camera N`, `--serial`, `--tape`, `--fake-laser`).
The web page walks you through setup: enter the distance between the tape
crosses, drag a box over them on the video and drag each corner onto its cross
(a magnifier helps; arrow keys nudge), then click the colored object. Keyboard shortcuts work on the page and in the window:
`c` redo corners, `t` re-pick color, `space` fake stud signal, `r` clear studs,
`m` switch views, `k` calibrate laser, `n` next stud, `l` laser on/off.

Edit the settings at the top of `host/app.py`: `WALL_CORNERS_IN` (your measured
tape crosses), `SENSOR_OFFSET_IN`, `LASER_STEP_RANGE`.

`--tape` tracks any brightly colored object on the stud finder (avoid red, the
laser is red). Without it, the program tracks ArUco marker 10
(`python markers/gen_markers.py --show` makes the markers).

## Layout
- `host/` laptop code (Python + OpenCV)
  - `app.py` the core (tracking, stud map, laser); `web.py` the web server;
    `web/` the React page; `main.py` the OpenCV window; `vision.py`,
    `laser.py`, `serial_link.py`
- `markers/` ArUco markers (DICT_4X4_50; ID 10 = stud finder, 0-3 = wall corners)
- `firmware/` Pro Micro code (PlatformIO)

Serial protocol (115200): Arduino sends `S1`/`S0 <millis>`, `OK`/`ERR`;
laptop sends `G <steps>`, `Z`, `L 1|0`, `P`. Each `S1` is a stud edge; the
host pairs two edges 0.5–3.5" apart into one stud and ignores `S0`.

## Laser (stretch goal)
Calibrate (`k`) sweeps the motor and learns steps -> inches; then click a stud
in the wall x-ray (or press `n`) to point the laser at it. Set
`LASER_STEP_RANGE` in `host/app.py` so the sweep covers the wall. Step 0 is
where the motor sits at power-up, aimed roughly at the middle of the wall.
The detector looks for bright red, so a dim room or lower exposure helps;
check it with the laser mask view.

## Arduino Readings 
As you scan the wall, the Arduino will return various digits. The number's correspond to the following:
| Reading   | Meaning                     |
|-----------|-----------------------------|
| ~1023     | On, no stud                 |
| ~720–736  | Stud                        |
| ~305      | Stud finder off             |
| ~885      | Brief, at power-on (ignore) |