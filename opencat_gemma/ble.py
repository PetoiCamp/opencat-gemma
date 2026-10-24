"""Bluetooth LE link to the robot over the Nordic UART service (no pairing needed). Same send/close as SerialLink."""
import asyncio
import threading
import time

from bleak import BleakClient, BleakScanner

from . import links

NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # we write commands here
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # the robot notifies replies here
NAME_PREFIXES = ("bittle", "nybble")
# On connect the firmware prints "Petoi <MODEL>" and then forces rest ("rest", "d"); commands sent before that are overwritten.
GREETING_TIMEOUT_S = 8
CONNECT_TIMEOUT_S = 15
CLOSE_TIMEOUT_S = 5

_loop = None
_loop_lock = threading.Lock()


def _get_loop():
    """One event loop in a daemon thread, so every bleak object lives on the same loop."""
    global _loop
    with _loop_lock:
        if _loop is None:
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, daemon=True, name="ble-loop").start()
        return _loop


def _run(coro, timeout):
    future = asyncio.run_coroutine_threadsafe(coro, _get_loop())
    try:
        return future.result(timeout)
    except TimeoutError:
        future.cancel()
        raise


class BleLink:
    """client: a bleak.BleakClient, or anything with async connect/start_notify/write_gatt_char/disconnect."""

    def __init__(self, client):
        self.client = client
        self._buf, self._lock = "", threading.Lock()

    def _on_notify(self, sender, data):  # called on the loop thread
        with self._lock:
            self._buf += bytes(data).decode("ISO-8859-1")

    def _lines_until(self, token, timeout, what, done=None):
        """Complete lines once one equals token (case-insensitive) or matches the `done` regex."""
        end = time.monotonic() + timeout
        while True:
            with self._lock:
                buf = self._buf
            lines = [l.strip() for l in buf.split("\n")[:-1]]
            if token.lower() in (l.lower() for l in lines) or (done and any(done.search(l) for l in lines)):
                return lines
            if time.monotonic() >= end:
                raise TimeoutError(f"no {token!r} echo for {what} within {timeout}s, got {buf!r}")
            time.sleep(0.01)

    def connect(self):
        """Connect, subscribe, and wait for the firmware's forced-rest line. Returns the greeting text."""
        async def start():
            await self.client.connect()
            await self.client.start_notify(NUS_TX, self._on_notify)
        _run(start(), CONNECT_TIMEOUT_S)
        try:
            lines = self._lines_until("d", GREETING_TIMEOUT_S, "the connect greeting")
        except TimeoutError:
            with self._lock:
                text = self._buf
            if not links.robot_from_reply(text):
                raise
            lines = [l.strip() for l in text.split("\n")]
        with self._lock:
            self._buf = ""
        return " | ".join(l for l in lines if l)

    def send(self, command, timeout=10, done=None):
        """Like SerialLink.send: returns on the token echo, or earlier on a line matching the `done` regex."""
        with self._lock:
            self._buf = ""
        _run(self.client.write_gatt_char(NUS_RX, (command + "\n").encode(), response=False), timeout)
        lines = self._lines_until(command[0], timeout, repr(command), done)
        return " | ".join(l for l in lines if l)

    def close(self):
        try:
            _run(self.client.disconnect(), CLOSE_TIMEOUT_S)
        except Exception:
            pass


async def _discover(scan_s):
    return await BleakScanner.discover(timeout=scan_s, return_adv=True)


def find_ble_robot(scan_s=8):
    """Scan for Bittle/Nybble by name, strongest signal first. Returns (BleLink, robot)."""
    print(f"Searching for a Petoi robot over Bluetooth (about {scan_s} s scan, then connecting)...", flush=True)
    found = _run(_discover(scan_s), scan_s + CONNECT_TIMEOUT_S)
    candidates = []
    for device, adv in found.values():
        name = adv.local_name or device.name or ""
        if name.lower().startswith(NAME_PREFIXES):
            candidates.append((adv.rssi, name, device))
    for _, name, device in sorted(candidates, key=lambda c: c[0], reverse=True):
        print(f"Connecting to {name}...", flush=True)
        link = BleLink(BleakClient(device))
        try:
            robot = links.robot_from_reply(link.connect())
        except Exception:
            robot = None
        if robot:
            print(f"Found {robot} over Bluetooth ({name})")
            return link, robot
        link.close()
    raise RuntimeError("No Petoi robot found over Bluetooth (BLE). Is it switched on and nearby? "
                       "Close other apps connected to it (e.g. the Petoi phone app).")
