"""USB serial links to the boards: the stud finder (Pro Micro) and,
optionally, a separate laser station (see firmware/laser_station).

Every incoming line is stamped with LAPTOP time (time.time()) the moment it
arrives and put on .events as (t, line). Don't use the Arduino's millis for
matching: the two clocks differ.

FakeLink has the same interface and is driven by the keyboard, so the vision
side can be tested without the Arduino.
"""
import glob
import queue
import threading
import time

BAUD = 115200


def list_ports():
    # Pro Micro / Uno show up as usbmodem; most Nano clones as usbserial.
    pats = ["/dev/cu.usbmodem*", "/dev/cu.usbserial*", "/dev/cu.wchusbserial*"]
    return sorted(p for pat in pats for p in glob.glob(pat))


def find_port(exclude=()):
    ports = [p for p in list_ports() if p not in exclude]
    return ports[0] if ports else None


def _wait_for(ser, wanted, timeout):
    end = time.time() + timeout
    while time.time() < end:
        line = ser.readline().decode(errors="replace").strip()
        if line.startswith(wanted):
            return True
    return False


def find_laser_port():
    """The port whose board answers ID with "ID LASER", or None."""
    import serial

    for port in list_ports():
        try:
            with serial.Serial(port, BAUD, timeout=0.1) as ser:
                # Uno/Nano reset when the port opens and print READY on boot.
                if _wait_for(ser, "READY LASER", 2.5):
                    return port
                ser.write(b"ID\n")
                if _wait_for(ser, "ID LASER", 1.0):
                    return port
        except (OSError, serial.SerialException):
            continue
    return None


class SerialLink:
    def __init__(self, port=None, baud=BAUD, wait_ready=False):
        import serial  # pyserial; imported here so FakeLink works without it

        port = port or find_port()
        if port is None:
            raise RuntimeError("No USB serial board found. Is it plugged in?")
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.port = port
        if wait_ready:
            # Boards that reset on connect (Uno, Nano) drop commands until booted.
            _wait_for(self.ser, "READY", 3.0)
        self.events = queue.Queue()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def _read_loop(self):
        while not self._stop.is_set():
            try:
                raw = self.ser.readline()
            except Exception as e:  # cable pulled, etc.
                self.events.put((time.time(), f"ERR serial {e}"))
                return
            if raw:
                t = time.time()
                line = raw.decode(errors="replace").strip()
                if line:
                    self.events.put((t, line))

    def send(self, cmd):
        self.ser.write((cmd.strip() + "\n").encode())

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
