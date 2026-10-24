# Stud Finder Plus

A $15 stud finder + Arduino + iPhone camera that maps every stud on a wall,
and (stretch) points a laser at it.

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
python host/web.py --tape --serial       # with the Pro Micro
python host/web.py --tape --fake-laser   # simulated laser + motor
python host/main.py --tape               # same thing in an OpenCV window (backup)
```
Both take the same options (`--camera N`, `--serial`, `--tape`, `--fake-laser`).
The web page walks you through setup: enter the distance between the tape
crosses, drag a box over them on the video and drag each corner onto its cross
(a magnifier helps; arrow keys nudge), then click the colored object. Keyboard shortcuts work on the page and in the window:
`c` redo corners, `t` re-pick color, `space` fake stud signal, `r` clear studs,
`m` switch views, `k` calibrate laser, `n` next stud, `l` laser on/off.

Other settings are at the top of `host/app.py` (`SENSOR_OFFSET_IN`,
`LASER_MAX_STEPS`, ...).

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
laptop sends `G <steps>`, `Z`, `L 1|0`, `P`.

## Laser (stretch goal)
Point the laser roughly at the middle of the wall before connecting (that's
step 0). Calibrate (`k`) then finds the wall edges by itself and sweeps left
to right to learn steps -> inches, so any wall width works (takes ~30 s).
Click Aim on a stud (or press `n`) to point the laser at it.
The detector looks for bright red, so a dim room or lower exposure helps;
check it with the laser mask view.

## Laser station (second board)
The stepper and laser can run on their own Arduino, separate from the stud
finder's Pro Micro. Firmware: `firmware/laser_station` (Uno by default; also
`nano`, `nano_old`, `mega`, `promicro`):
```
cd firmware/laser_station && pio run -e uno -t upload
```
Wiring: pins 4-7 -> ULN2003 IN1-IN4; pin 9 -> 1k -> 2N2222 base (laser);
driver board + laser powered from the 5V power module; **all grounds joined**.
Run the laptop with `--laser-serial` (finds the station by its `ID LASER`
reply) or `--laser-port /dev/cu.xxx`:
```
python host/web.py --tape --serial --laser-serial
```

## Arduino Readings 
As you scan the wall, the Arduino will return various digits. The number's correspond to the following:
| Reading   | Meaning                     |
|-----------|-----------------------------|
| ~1023     | On, no stud                 |
| ~720–736  | Stud                        |
| ~305      | Stud finder off             |
| ~885      | Brief, at power-on (ignore) |