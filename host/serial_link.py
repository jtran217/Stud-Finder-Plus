"""USB serial links to the boards: the stud finder (Pro Micro) and,
optionally, a separate laser station (see firmware/laser_station).

Every incoming line is stamped with LAPTOP time (time.time()) the moment it
arrives and put on .events as (t, line). Don't use the Arduino's millis for
matching: the two clocks differ.

FakeLink has the same interface and is driven by the keyboard, so the vision
side can be tested without the Arduino.

The port is opened exclusively: two programs reading one port (e.g. this app
and `pio device monitor`) each get only some of the lines. If the board drops
off USB, the link keeps retrying until it's back.
"""
import fcntl
import glob
import json
import os
import queue
import subprocess
import termios
import threading
import time
from pathlib import Path

BAUD = 115200
RECONNECT_S = 0.5
# This machine's ports, e.g. {"stud": "/dev/cu.usbmodem1101", "laser": ...}. Gitignored:
# port names differ between laptops (and between USB sockets).
PORTS_PATH = Path(__file__).parent / "ports.json"


def configured_port(name):
    """Port for `name` from host/ports.json, or None if it isn't set."""
    try:
        return json.loads(PORTS_PATH.read_text()).get(name)
    except (FileNotFoundError, ValueError):
        return None


def save_port(name, port):
    if configured_port(name) == port:
        return
    try:
        saved = json.loads(PORTS_PATH.read_text())
    except (FileNotFoundError, ValueError):
        saved = {}
    PORTS_PATH.write_text(json.dumps({**saved, name: port}) + "\n")


def list_ports():
    # Pro Micro / Uno show up as usbmodem; most Nano clones as usbserial.
    pats = ["/dev/cu.usbmodem*", "/dev/cu.usbserial*", "/dev/cu.wchusbserial*"]
    return sorted(p for pat in pats for p in glob.glob(pat))


def find_port(exclude=()):
    ports = [p for p in list_ports() if p not in exclude]
    return ports[0] if ports else None


def resolve_port(explicit=None, exclude=()):
    """Stud finder port: --port wins, then host/ports.json (if that port
    exists right now), then the first board found that isn't in `exclude`."""
    if explicit:
        return explicit
    exclude = (*exclude, configured_port("laser"))   # never grab the laser station
    saved = configured_port("stud")
    if saved and os.path.exists(saved) and saved not in exclude:
        return saved
    return find_port(exclude)


def port_users(port):
    """Other programs that have `port` open, as 'command (pid N)' strings."""
    try:
        out = subprocess.run(["lsof", "-t", port], capture_output=True, text=True).stdout
    except FileNotFoundError:
        return []
    users = []
    for pid in out.split():
        if int(pid) == os.getpid():
            continue
        cmd = subprocess.run(["ps", "-o", "command=", "-p", pid],
                             capture_output=True, text=True).stdout.strip()
        users.append(f"{cmd[-60:] or '?'} (pid {pid})")
    return users


def _wait_for(ser, wanted, timeout):
    end = time.time() + timeout
    while time.time() < end:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith(wanted):
            return True
    return False


def find_laser_port():
    """Laser station port: host/ports.json "laser" if that port exists,
    else the board that answers ID with "ID LASER". None if not found."""
    saved = configured_port("laser")
    if saved and os.path.exists(saved):
        return saved
    import serial

    for port in list_ports():
        if port_users(port):
            continue
        try:
            with serial.Serial(port, BAUD, timeout=0.1) as ser:
                # Uno/Nano reset when the port opens and print READY on boot.
                found = _wait_for(ser, "READY LASER", 2.5)
                if not found:
                    ser.write(b"ID\n")
                    found = _wait_for(ser, "ID LASER", 1.0)
        except (OSError, serial.SerialException):
            continue
        if found:
            save_port("laser", port)
            return port
    return None


class SerialLink:
    def __init__(self, port=None, baud=BAUD, wait_ready=False, exclude=()):
        import serial  # pyserial; imported here so FakeLink works without it

        self._serial = serial
        self.explicit_port = port
        self.exclude = tuple(exclude)
        self.wait_ready = wait_ready
        self.baud = baud
        self.ser = None
        self.port = None
        self._open()   # first open raises, so a bad setup fails at startup
        self.events = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _open(self):
        port = resolve_port(self.explicit_port, self.exclude)
        if port is None:
            raise RuntimeError("No USB serial board found. Is the Pro Micro plugged in?")
        users = port_users(port)
        if users:
            raise RuntimeError(f"{port} is already open in another program: "
                               f"{', '.join(users)}. Close it (Ctrl+C in the pio monitor).")
        ser = self._serial.Serial(port, self.baud, timeout=0.1)
        fcntl.ioctl(ser.fileno(), termios.TIOCEXCL)  # later opens fail with "busy"
        if self.wait_ready:
            # Boards that reset on connect (Uno, Nano) drop commands until booted.
            _wait_for(ser, "READY", 3.0)
        self.ser, self.port = ser, port

    def _read_loop(self):
        while not self._stop.is_set():
            try:
                raw = self.ser.readline()
            except Exception as e:  # cable pulled, board reset, etc.
                self.events.put((time.time(), f"ERR serial lost ({e}), reconnecting"))
                self._reconnect()
                continue
            if raw:
                t = time.time()
                line = raw.decode(errors="replace").strip()
                if line:
                    self.events.put((t, line))

    def _reconnect(self):
        try:
            self.ser.close()
        except Exception:
            pass
        last_err = None
        while not self._stop.is_set():
            time.sleep(RECONNECT_S)
            try:
                self._open()
            except Exception as e:
                if str(e) != last_err:   # say each new problem once
                    last_err = str(e)
                    self.events.put((time.time(), f"ERR serial {e}"))
                continue
            self.events.put((time.time(), f"serial reconnected on {self.port}"))
            return

    def send(self, cmd):
        try:
            self.ser.write((cmd.strip() + "\n").encode())
        except Exception:
            pass   # disconnected; the read loop is reconnecting

    def close(self):
        self._stop.set()
        self.ser.close()


class FakeLink:
    """Keyboard stand-in: call toggle() on each space press (S1, then S0)."""

    port = "fake (space = stud signal)"

    def __init__(self):
        self.events = queue.Queue()
        self.on = False

    def toggle(self):
        self.on = not self.on
        self.events.put((time.time(), "S1" if self.on else "S0"))

    def send(self, cmd):
        print(f"[fake] would send: {cmd}")

    def close(self):
        pass


def check_port(explicit=None):
    """Port check for start.sh: prints the port the app will use and saves it
    in host/ports.json, or explains what's wrong. Returns an exit code."""
    import sys

    port = resolve_port(explicit)
    if port is None or not os.path.exists(port):
        print(f"No Pro Micro found ({port or '/dev/cu.usbmodem*'}). Is it plugged in, "
              "with a data cable?", file=sys.stderr)
        return 1
    users = port_users(port)
    if users:
        print(f"{port} is already open in: {', '.join(users)}. Close it first "
              "(Ctrl+C in the pio monitor).", file=sys.stderr)
        return 1
    if configured_port("stud") != port:
        save_port("stud", port)
        print(f"saved {port} in {PORTS_PATH.name}", file=sys.stderr)
    print(port)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(check_port(sys.argv[1] if len(sys.argv) > 1 else None))
