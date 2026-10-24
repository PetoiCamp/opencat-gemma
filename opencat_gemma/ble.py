"""Bluetooth LE link to the robot over the Nordic UART service (no pairing needed). Same send/close as SerialLink."""
import asyncio
import threading
import time

from bleak import BleakClient, BleakScanner

from . import links
from .contract import registry

NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e"  # we write commands here
NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e"  # the robot notifies replies here
NAME_PREFIXES = tuple(prefix for _, prefix in registry().values()) + ("petoi",)  # "Petoi_BLE": fallback name
# Two connect styles. ESP32 (BiBoard) firmware pushes "Petoi <MODEL>" on connect, then forces rest ("rest", "d");
# commands sent before that are overwritten. ESP32-S3 firmware stays silent until asked '?'.
PUSH_WAIT_S = 2  # ESP32 firmware pushes its greeting within this time
GREETING_TIMEOUT_S = 8  # then the forced "d" arrives within this time
QUERY_TIMEOUT_S = 5
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

    is_ble = True  # the runner refuses commands that would drop a Bluetooth link (XO)

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
        """Connect and subscribe. If a greeting is pushed (ESP32 firmware), wait for its forced 'd' so our
        commands aren't overwritten. Then always identify with '?' (S3 firmware only answers when asked).
        Returns the '?' reply."""
        async def start():
            await self.client.connect()
            await self.client.start_notify(NUS_TX, self._on_notify)
        _run(start(), CONNECT_TIMEOUT_S)
        end = time.monotonic() + PUSH_WAIT_S
        while time.monotonic() < end and not self._buf:
            time.sleep(0.01)
        if self._buf:
            try:
                self._lines_until("d", GREETING_TIMEOUT_S, "the connect greeting")
            except TimeoutError:
                pass  # no forced rest seen; '?' below still identifies the robot
        with self._lock:
            self._buf = ""
        _run(self.client.write_gatt_char(NUS_RX, b"?\n", response=False), QUERY_TIMEOUT_S)
        end = time.monotonic() + QUERY_TIMEOUT_S
        while True:
            with self._lock:
                buf = self._buf
            lines = [l.strip() for l in buf.split("\n")]
            # A normal reply ends with a "?" line. The S3 firmware's first reply after connecting is its handshake,
            # sent with no line breaks: "Petoi <MODEL>u<MODEL><version>?".
            if "?" in lines[:-1] or ("Petoi" in buf and buf.strip().endswith("?")):
                break
            if time.monotonic() >= end:
                raise TimeoutError(f"no reply to '?' within {QUERY_TIMEOUT_S}s, got {buf!r}")
            time.sleep(0.01)
        with self._lock:
            self._buf = ""
        return " | ".join(l for l in lines if l)

    def send(self, command, timeout=10, done=None, echo=None):
        """Like SerialLink.send: returns on the token echo (`echo`, default the command's first letter), or earlier
        on a line matching the `done` regex."""
        with self._lock:
            self._buf = ""
        _run(self.client.write_gatt_char(NUS_RX, (command + "\n").encode(), response=False), timeout)
        lines = self._lines_until(echo or command[0], timeout, repr(command), done)
        return " | ".join(l for l in lines if l)

    def close(self):
        try:
            _run(self.client.disconnect(), CLOSE_TIMEOUT_S)
        except Exception:
            pass


async def _discover(scan_s):
    return await BleakScanner.discover(timeout=scan_s, return_adv=True)


class MultipleRobotsError(RuntimeError):
    """Several Petoi robots are advertising and no name was given. Raised before connecting to any of them."""


def find_ble_robot(scan_s=8, name=None):
    """Scan for Petoi robots, strongest signal first. Returns (BleLink, robot).

    name=None: candidates are devices whose name starts with NAME_PREFIXES; more than one raises MultipleRobotsError.
    name given: only devices advertising exactly `name` or `name_BLE` (case-insensitive), whatever their prefix."""
    print(f"Searching for a Petoi robot over Bluetooth (about {scan_s} s scan, then connecting)...", flush=True)
    found = _run(_discover(scan_s), scan_s + CONNECT_TIMEOUT_S)
    wanted = {name.lower(), name.lower() + "_ble"} if name else None
    candidates = []
    for device, adv in found.values():
        advertised = adv.local_name or device.name or ""
        if (advertised.lower() in wanted) if wanted else advertised.lower().startswith(NAME_PREFIXES):
            candidates.append((adv.rssi, advertised, device))
    candidates.sort(key=lambda c: c[0], reverse=True)
    if name is None and len(candidates) > 1:
        listing = ", ".join(f"{n} (signal {rssi} dBm)" for rssi, n, _ in candidates)
        raise MultipleRobotsError(f"Several Petoi robots are nearby: {listing}. "
                                  "Choose yours with --bluetooth --name <name>. Find your robot's name over USB with --robot-name.")
    for _, advertised, device in candidates:
        print(f"Connecting to {advertised}...", flush=True)
        link = BleLink(BleakClient(device))
        try:
            robot = links.robot_from_reply(link.connect())
        except Exception:
            robot = None
        if robot:
            print(f"Found {robot} over Bluetooth ({advertised})")
            return link, robot
        link.close()
    if name:
        raise RuntimeError(f"No Petoi robot named {name!r} (Bluetooth name {name}_BLE) found over Bluetooth (BLE). "
                           "Check the spelling, that it is switched on and nearby, and that no other app (e.g. the "
                           "Petoi phone app) is connected to it. Find its name over USB with --robot-name.")
    raise RuntimeError("No Petoi robot found over Bluetooth (BLE). Is it switched on and nearby? "
                       "Close other apps connected to it (e.g. the Petoi phone app).")
