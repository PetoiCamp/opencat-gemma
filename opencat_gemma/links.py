"""Transports to the robot. Every link has send(command, timeout) -> reply text, and close()."""
import json
import re
import threading
import time

import serial
from serial.tools import list_ports
from websockets.sync.client import connect

BAUD = 115200
WRITE_TIMEOUT_S = 2  # pyUI uses the same
# The firmware (src/webServer.h) drops a client after 40 s without a heartbeat message; send well inside that.
HEARTBEAT_S = 15
MODELS = {"Bittle": "bittle", "Nybble": "nybble"}


def open_serial(port):
    # Leave DTR/RTS at pyserial's defaults. Clearing them (pyserial applies it while opening) pulses the ESP32 reset line
    # and reboots the robot (seen on macOS with Bittle X, 2026-10-23). Not yet checked on Windows/Linux.
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, BAUD, 0.05
    # Without this, writing to a macOS Bluetooth port whose link is down blocks forever (seen 2026-10-23).
    # A timeout raises serial.SerialTimeoutException (an OSError), which callers already handle.
    ser.write_timeout = WRITE_TIMEOUT_S
    ser.open()
    time.sleep(0.5)
    ser.reset_input_buffer()
    return ser


class SerialLink:
    """The robot prints the command's first letter (e.g. "k") on its own line when the command is done.

    The read loop in send() relies on the serial object's short read timeout (open_serial sets 0.05 s);
    with a blocking read it could not notice the deadline.
    """

    def __init__(self, ser):
        self.ser = ser

    def send(self, command, timeout=10, done=None):
        """Returns on the token echo, or earlier on a complete line matching the `done` regex (if given)."""
        self.ser.write((command + "\n").encode())
        buf, end = "", time.monotonic() + timeout
        while time.monotonic() < end:
            buf += self.ser.read(4096).decode("ISO-8859-1")
            lines = [l.strip() for l in buf.split("\n")[:-1]]  # complete lines only
            if command[0].lower() in (l.lower() for l in lines) or (done and any(done.search(l) for l in lines)):
                return " | ".join(l for l in lines if l)
            time.sleep(0.01)
        raise TimeoutError(f"no {command[0]!r} echo for {command!r} within {timeout}s, got {buf!r}")

    def close(self):
        self.ser.close()


def robot_from_reply(reply):
    """Map the reply to '?' (e.g. "G | Bittle X | B10_260527 | ?") to a contract name, or None."""
    return next((robot for name, robot in MODELS.items() if name in reply), None)


def find_robot():
    """Probe USB serial ports with '?'. Returns (SerialLink, robot) for the first Petoi robot that answers."""
    for p in list_ports.comports():
        if p.vid is None:
            continue
        try:
            link = SerialLink(open_serial(p.device))
        except (serial.SerialException, OSError):
            continue
        try:
            robot = robot_from_reply(link.send("?", timeout=3))
        except (TimeoutError, serial.SerialException, OSError):
            robot = None
        if robot:
            print(f"Found {robot} on {p.device}")
            return link, robot
        link.close()
    raise RuntimeError("No Petoi robot found on USB. Check power and the cable, and that no other app has the port open.")


IP_LINE = re.compile(r"IP Address:\s*(\d{1,3}(?:\.\d{1,3}){3})")


def wifi_setup(link, ssid, password, timeout=45):
    """Join the robot to Wi-Fi with the firmware's 'w%SSID%password' command (over USB or Bluetooth).

    Returns the robot's IP. The firmware remembers the network. The password is never printed by this function.
    On success the firmware prints the IP and then reboots, so no 'w' echo arrives: we stop at the IP line.
    Joining can take ~36 s (3 attempts of ~12 s, webServer.h connectWifi), hence the timeout.
    """
    if "%" in ssid or "%" in password:
        raise ValueError("Wi-Fi name and password can't contain '%' (the firmware uses it as a separator)")
    try:
        reply = link.send(f"w%{ssid}%{password}", timeout=timeout, done=IP_LINE)
    except TimeoutError:
        # Don't chain: the original message holds the robot's output, which shows the password's last 4 characters.
        raise TimeoutError(f"The robot did not finish joining Wi-Fi within {timeout}s. "
                           "Check the name, the password, and that the network is 2.4 GHz.") from None
    match = IP_LINE.search(reply)
    if not match:
        raise RuntimeError("The robot did not report an IP address. Check the Wi-Fi name and password, and that the "
                           "network is 2.4 GHz (the robot can't join 5 GHz); if the robot is already on Wi-Fi, "
                           "find its IP in your router.")
    return match.group(1)


def wifi_ip(link, timeout=5):
    """The robot's Wi-Fi IP, or None if it isn't on Wi-Fi. Sends a bare 'w' (no credentials): when connected,
    the firmware replies "Wifi already connected to IP Address: <ip>"; otherwise it ignores the empty command."""
    match = IP_LINE.search(link.send("w", timeout=timeout, done=IP_LINE))
    return match.group(1) if match else None


def detect_ws_robot(link):
    """Ask over WebSocket which robot this is. Returns 'bittle'/'nybble', or None if the reply names no model."""
    try:
        return robot_from_reply(link.send("?", timeout=5))
    except (TimeoutError, RuntimeError):
        return None


class WsLink:
    """Firmware WebSocket server (src/webServer.h, port 81). One command per task, so turns can be timed between tasks.

    The firmware runs a multi-command task back to back: the next command starts as soon as the previous one
    replies, so a gait in the middle of a group would be cut off immediately.
    """

    def __init__(self, url):
        self.ws = connect(url, open_timeout=5)
        self._closed = threading.Event()
        # websockets' send() of a str holds an internal mutex, so calling it from two threads is safe.
        threading.Thread(target=self._heartbeat, args=(HEARTBEAT_S,), daemon=True).start()

    def _heartbeat(self, interval):
        while not self._closed.wait(interval):
            try:
                self.ws.send(json.dumps({"type": "heartbeat", "timestamp": int(time.time() * 1000)}))
            except Exception:
                return  # the next send() will surface the error

    BUSY = "Previous web task is still running"

    def send(self, command, timeout=10):
        """Send one command as its own task. If the firmware is still running an earlier task (e.g. a walk that
        Ctrl+C interrupted), it drops our command but also clears that task (webServer.h errorWebTask), so we
        retry once. Without this, STOP was rejected over Wi-Fi and the robot kept walking."""
        try:
            return self._send_once(command, timeout)
        except RuntimeError as e:
            if str(e) != self.BUSY:
                raise
            return self._send_once(command, timeout)

    def _send_once(self, command, timeout):
        task_id = str(time.time_ns())
        self.ws.send(json.dumps({"type": "command", "taskId": task_id, "commands": [command],
                                 "timestamp": int(time.time() * 1000)}))
        end = time.monotonic() + timeout
        while True:
            msg = json.loads(self.ws.recv(timeout=max(0, end - time.monotonic())))
            # Errors may carry another task's id ("still running") or none ("Heartbeat timeout").
            if msg.get("type") == "error" or msg.get("status") == "error":
                raise RuntimeError(msg.get("error", "task failed"))
            if msg.get("taskId") == task_id and msg.get("status") == "completed":
                lines = [l.strip() for r in msg.get("results", []) for l in r.split("\n")]
                return " | ".join(l for l in lines if l)

    def close(self):
        self._closed.set()
        self.ws.close()
