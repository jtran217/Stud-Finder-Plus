# Stud Finder Plus: agent context

Context for AI coding agents (Claude Code, Cursor, Codex) working in this repo.
It collects the decisions and hardware facts from our planning chats so you
don't re-derive or re-litigate them. The README covers setup and run commands;
this file covers the *why* and the current state.

## Working with this team
- Two-person hackathon team. Neither of us had used OpenCV before, and we have
  very little Arduino experience.
- **Walk us through solutions instead of dumping code.** Explain each piece
  briefly, give the code, and say how to test it. Be quick about it: we're on
  a deadline.
- Show the exact wording before sending any message on our behalf.
- Person A (AJ) owns the stud finder hardware and its firmware. Person B
  (Johnny, GitHub `jtran217`) owns the Python/OpenCV host, the web page, and
  the stepper motor. Ask before making big changes to the other person's area.
- Work on a branch (`aj/...`, `johnny/...`) and merge through a PR on
  `github.com/jtran217/Stud-Finder-Plus`.

## The project
- **Hackathon theme: Revitalize.** 36 hours, started Fri Oct 23 2026 at about
  9 PM, ends Sun Oct 25 at about 9 AM.
- **Origin story:** on move-in day it took us 30–45 minutes to find studs and
  plan where to hang things, because you can't see where they are.
- **What it does:** a cheap stud finder is wired to an Arduino. Each time it
  detects a stud, the laptop gets a signal. An iPhone camera tracks where the
  stud finder is on the wall, so the laptop builds a map of every stud in
  inches from the wall's edge.
- **MVP:** sweep the stud finder across a wall; the laptop shows each stud on
  the live video with its distance from the edge.
- **Stretch:** a vertical line laser on a stepper motor points at a chosen
  stud on the real wall.
- **Pitch:** open with the move-in story, then "we revitalized a $15
  single-purpose tool and gave it memory, a map and a laser, instead of
  selling people a $200 smart scanner." Expect judges to bring up Walabot DIY
  as prior art; our edge is retrofitting cheap hardware, a persistent map,
  and marking the real wall.
- Our own scores: theme fit 5/10 as a convenience pitch, 7–8/10 with the
  "revitalize old hardware" framing. MVP feasibility 8/10, laser 6/10.

## Decisions (settled, don't reopen)
| Decision | Why |
|---|---|
| Laser, not a projector | Projectors wash out in bright hackathon halls, cost more, and fit the construction-site story less well. |
| One vertical line laser on one stepper | Studs are vertical, so we only aim left–right: one motor, one number. Shows one stud at a time (pick one or cycle). |
| 28BYJ-48 stepper + ULN2003 driver | Exact, repeatable steps (0.088° in half-step). A DC gear motor or the L298N can't hold an angle; 1° ≈ 1.4" on the wall at 2 m, about one stud width. |
| Camera closes the loop on the laser | The camera finds the red line, so calibration is automatic and each move gets corrected. |
| iPhone via Continuity Camera | Our other camera had heavy fisheye distortion, which breaks the pixel-to-inch mapping. |
| Track a marker or colored object, not "the Arduino" | ArUco markers are reliable at 30 fps. `--tape` mode tracks any bright (non-red) object as a fallback. |
| Python + OpenCV on the laptop | Far more examples than C++ OpenCV, no build setup on macOS. |
| C++ via PlatformIO on the Arduino, CLI + Cursor, no Arduino IDE | Proper project structure, but keeps the Arduino libraries (Serial, AccelStepper). |
| USB serial, not Wi-Fi | Simpler, nothing to drop out mid-demo. |
| **Separate Arduino for the motor** | The stud finder board only sends events; the motor/laser board only takes commands. Two serial ports. |
| Build our own demo wall | Drywall on 2×4s with uneven stud spacing, true centers marked on the back to prove accuracy. Don't rely on a venue wall. |

## Hardware facts
### Stud finder board (Person A)
- **Pro Micro, ATmega32U4, 5V/16 MHz** (VCC measured 4.64V). PlatformIO
  `board = leonardo`, as the seller recommends. No `LED_BUILTIN`.
- Native USB: the serial port disappears and comes back after every upload or
  reset. If an upload "bricks" it, short RST to GND twice quickly, then upload
  within 8 seconds.
- **The stud indicator is the clear LED in the arrow tip**, not the green one.
- The two pads behind the clear LED read **3.12V** (the switched signal side)
  and **5V** (supply; leave unconnected).
- **Wiring:** 3.12V pad → 10kΩ resistor → **A0** (`INPUT_PULLUP`).
  Stud finder NEG battery clip → Pro Micro GND. The stud finder keeps its own
  9V battery with the button held down.
- The battery side reads about 8V; never wire that to a Pro Micro pin.

**A0 readings and cutoffs**

| Reading | Meaning | Cutoff |
|---|---|---|
| ~1023 | On, no stud | ≥ 900 |
| ~720–736 | **Stud** | 650–820 (the cap skips the power-on blip) |
| ~305 | Stud finder off | ≤ 450 |
| ~885 | Brief at power-on, ignore | in a gap |

Any reading in a gap keeps the previous state. A new state must hold for
30 ms before it counts (debounce).

### Motor + laser board (Person B)
- 28BYJ-48 + ULN2003. IN1–IN4 on pins 4, 5, 6, 7; driver − to GND, + to 5V.
- `lib_deps = waspinator/AccelStepper`. Use
  `AccelStepper motor(AccelStepper::HALF4WIRE, 4, 6, 5, 7);` — the pin order
  IN1, IN3, IN2, IN4 is deliberate; in sequence it buzzes and doesn't turn.
- 4096 half-steps per output revolution. Call `motor.run()` every loop; no
  `delay()` anywhere in this firmware.
- Approach targets from the same direction to cancel gear slack.
- If the board resets or readings jump while the motor moves, power the
  driver from its own 5V supply with a shared ground.
- Laser: check its current before wiring to a pin. Under 30 mA can run from a
  pin; otherwise switch it with an NPN transistor or MOSFET. Keep the beam
  below eye level, pointed at the wall.

### Camera
- iPhone on a tripod, landscape, locked, cabled to the Mac, Do Not Disturb on.
- **Turn off Center Stage, Portrait, Studio Light and Desk View** (Control
  Center → Video Effects while the camera is live). Center Stage crops and pans
  on its own, which silently breaks the inch mapping.
- Quit Photo Booth before running Python. The camera index can change between
  reboots; use `host/find_camera.py`. Black frames mean the terminal or editor
  lacks camera permission.
- A desk lamp on the wall reduces motion blur. Dimmer light helps laser
  detection.

## Serial protocol (115200 baud, one `\n`-terminated line per message)
Stud finder board → laptop:
- `S1 <millis>` stud starts, `S0 <millis>` stud ends. Only sent on changes.
  Also send `S0` if the finder switches off mid-stud.
- The millis value is for debugging only. `serial_link.py` stamps each line
  with laptop time on arrival, and that's what gets matched to camera frames.

Laptop → motor board:
- `G <steps>` move to an absolute step, `Z` set current position as step 0,
  `L 1` / `L 0` laser on/off, `P` report position.
- Replies `OK ...` / `ERR ...` are optional; the app only logs them. Step 0 is
  the power-up position, aimed roughly at the middle of the wall.

## Code map
- `firmware/src/` Pro Micro code. `platformio.ini` sits at the repo root with
  `src_dir = firmware/src`, env `pimicro`.
- `host/app.py` the core: tracking history, stud map, setup steps, laser.
  Settings at the top: `WALL_SIZE_IN`, `SENSOR_OFFSET_IN`, `CAMERA_LATENCY_S`,
  `MERGE_IN`, `LASER_STEP_RANGE`.
- `host/web.py` web server (http://localhost:8000); `host/web/` the React +
  Vite page. `host/main.py` the OpenCV-window backup front end.
- `host/vision.py` ArUco detection and homography (DICT_4X4_50; ID 10 = stud
  finder, 0–3 = wall corners). `host/laser.py` laser detection, calibration,
  aiming, plus `FakeRig` simulator. `host/serial_link.py` serial reader and
  keyboard-driven `FakeLink`.
- `markers/` marker PNGs; `python markers/gen_markers.py --show` regenerates
  them.
- How a stud is placed: on `S1`/`S0`, `app.py` looks up where the tracked
  object was at that laptop timestamp (interpolated, refusing gaps > 0.3 s),
  pairs the edges, and uses their average as the stud center. Studs within
  `MERGE_IN` are merged.

Common commands:
```bash
pio run -t upload -t monitor        # flash + watch the stud finder board
pio device list                     # find /dev/cu.usbmodem… ports
python host/web.py --tape --serial --port /dev/cu.usbmodemXXXX
python host/web.py --tape --fake-laser   # no hardware needed
```
Only one program can hold a serial port: close `pio device monitor` before
running Python.

## Current state (Sat Oct 24, morning)
- Done: stud finder wired and reading clean levels on A0; Python side already
  handles `S1`/`S0`; web page with box-drag corner setup; laser detection,
  auto-calibration and aiming (tested in the simulator).
- `firmware/src/main.cpp` is still the raw `analogRead` print test. Replace it
  with the OFF/CLEAR/STUD state machine (cutoffs above, 30 ms hold, prints
  only `S1`/`S0`).
- **Two-board change not yet in the Python code.** `serial_link.find_port()`
  takes the first `usbmodem` port, and `StudApp` has one `self.link` that
  receives motor commands. Plan: add `--motor-port`, open a second
  `SerialLink` as `self.motor`, send commands via `(self.motor or self.link)`,
  drain and log the motor board's replies, close it on exit. Always pass
  `--port` explicitly with two boards plugged in.
- Measure `SENSOR_OFFSET_IN` (tracked object center → sensor center); it's
  0.0, and a wrong value shifts every stud by the same amount.
- Hot-glue the solder joints on the stud finder: a torn wire mid-demo is the
  biggest hardware risk.

## Remaining plan
1. **MVP by about noon Saturday:** flash S1/S0 firmware, run
   `web.py --tape --serial`, sweep a real wall, studs within about 0.5" of
   truth. **Screen-record it immediately** as the backup demo.
2. Print the ArUco markers (0–3 at about 4", 10 at about 3") and anything for
   the scanner; start long prints early.
3. Build the demo wall (½" drywall panel, 3–4 2×4s, drywall screws, uneven
   spacing like 12" / 19" / 14", centers marked on the back).
4. Motor firmware on its own board, mount the laser with the line vertical on
   a rigid base, wire the two-port Python change, calibrate (`k`), aim (`n`).
5. Polish: blueprint view with distances, predicted studs at the measured
   spacing, accuracy comparison against the marks on the back of the wall.
6. **Laser go/no-go Sat ~8 PM.** If it isn't reliable, drop it and polish the
   MVP. Freeze code about 3 hours before the deadline; bug fixes only after.
7. Record a backup demo video and practice the pitch at least 3 times.

## Fallbacks
| Problem | Fallback |
|---|---|
| Stud finder signal unreadable | Press space on the laptop when the LED lights |
| Tracked object blurs or flickers | More light, bigger marker, sweep slower |
| iPhone camera flaky | Camo app, or the other phone |
| Stepper too imprecise | Laser closer to the wall, more correction passes |
| Laser doesn't work | The on-screen map alone is the demo |
