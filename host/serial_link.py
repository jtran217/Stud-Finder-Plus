"""Talks to the Pro Micro over USB serial.

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


def find_port():
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    return ports[0] if ports else None


class SerialLink:
    def __init__(self, port=None, baud=BAUD):
        import serial  # pyserial; imported here so FakeLink works without it

        port = port or find_port()
        if port is None:
            raise RuntimeError("No /dev/cu.usbmodem* port found. Is the Pro Micro plugged in?")
        self.ser = serial.Serial(port, baud, timeout=0.1)
        self.port = port
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
