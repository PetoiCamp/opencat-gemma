import io
import json
import threading
import time
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from websockets.sync.server import serve

from opencat_gemma import links
from opencat_gemma.links import SerialLink, WsLink, find_robot, robot_from_reply


class FakeSerial:
    """Replies like Bittle X did on 2026-10-23 once a full line arrives."""

    def __init__(self, replies):
        self.replies, self.written, self.pending = replies, b"", b""
        self.closed = False

    def write(self, data):
        self.written += data
        if data.endswith(b"\n"):
            self.pending += self.replies.get(data.strip().decode(), b"")

    def read(self, size):
        out, self.pending = self.pending[:size], self.pending[size:]
        return out

    def close(self):
        self.closed = True


class SerialLinkTest(unittest.TestCase):
    def test_sends_line_and_returns_on_token_echo(self):
        ser = FakeSerial({"kwkF 3": b"wkF\r\nCycle counting mode: \t3 cycles\r\nup\r\nk\r\n"})
        reply = SerialLink(ser).send("kwkF 3", timeout=1)
        self.assertEqual(ser.written, b"kwkF 3\n")
        self.assertEqual(reply, "wkF | Cycle counting mode: \t3 cycles | up | k")

    def test_partial_line_is_not_an_echo(self):
        ser = FakeSerial({"kbalance": b"balance\r\nk"})  # "k" without newline yet
        with self.assertRaises(TimeoutError):
            SerialLink(ser).send("kbalance", timeout=0.2)

    def test_query_echo_uses_question_mark(self):
        ser = FakeSerial({"?": b"G\r\nBittle X\r\nB10_260527\r\n?\r\n"})
        self.assertEqual(SerialLink(ser).send("?", timeout=1), "G | Bittle X | B10_260527 | ?")


class FindRobotTest(unittest.TestCase):
    def test_skips_no_vid_closes_failed_probe_and_returns_bittle(self):
        ports = [SimpleNamespace(vid=None, device="/dev/bt"),
                 SimpleNamespace(vid=1, device="/dev/bad"),
                 SimpleNamespace(vid=2, device="/dev/good")]
        class RaisingSerial(FakeSerial):
            def write(self, data):
                raise OSError("device gone")
        sers = {"/dev/bad": RaisingSerial({}),
                "/dev/good": FakeSerial({"?": b"G\r\nBittle X\r\nB10_260527\r\n?\r\n"})}
        opened = []
        def fake_open(device):
            opened.append(device)
            return sers[device]
        with mock.patch.object(links.list_ports, "comports", return_value=ports), \
             mock.patch.object(links, "open_serial", side_effect=fake_open), \
             redirect_stdout(io.StringIO()):
            link, robot = find_robot()
        self.assertEqual(robot, "bittle")
        self.assertIs(link.ser, sers["/dev/good"])
        self.assertEqual(opened, ["/dev/bad", "/dev/good"])
        self.assertTrue(sers["/dev/bad"].closed)
        self.assertFalse(sers["/dev/good"].closed)



class OpenSerialTest(unittest.TestCase):
    def test_leaves_dtr_and_rts_alone(self):
        """Clearing DTR/RTS after open pulsed the ESP32 reset on macOS and rebooted Bittle X (2026-10-23)."""
        touched = []

        class RecordingSerial:
            def __setattr__(self, name, value):
                touched.append(name)
                object.__setattr__(self, name, value)

            def open(self):
                pass

            def reset_input_buffer(self):
                pass

        with mock.patch.object(links.serial, "Serial", RecordingSerial), mock.patch.object(links.time, "sleep"):
            links.open_serial("/dev/fake")
        self.assertNotIn("dtr", touched)
        self.assertNotIn("rts", touched)

    def test_sets_write_timeout(self):
        """A write to a macOS Bluetooth port whose link is down blocked forever (2026-10-23)."""
        with mock.patch.object(links.serial, "Serial", mock.MagicMock()) as Serial, mock.patch.object(links.time, "sleep"):
            ser = links.open_serial("/dev/fake")
        self.assertIs(ser, Serial.return_value)
        self.assertEqual(ser.write_timeout, links.WRITE_TIMEOUT_S)

    def test_find_robot_skips_usb_port_whose_write_times_out(self):
        class StuckSerial(FakeSerial):
            def write(self, data):
                raise links.serial.SerialTimeoutException("Write timeout")
        good = FakeSerial({"?": b"G\r\nBittle X\r\nB10_260527\r\n?\r\n"})
        stuck = StuckSerial({})
        ports = [SimpleNamespace(device="/dev/cu.usbA", vid=1), SimpleNamespace(device="/dev/cu.usbB", vid=2)]
        with mock.patch.object(links.list_ports, "comports", return_value=ports), \
             mock.patch.object(links, "open_serial", side_effect=[stuck, good]), redirect_stdout(io.StringIO()):
            link, robot = links.find_robot()
        self.assertEqual(robot, "bittle")
        self.assertTrue(stuck.closed)


class RobotFromReplyTest(unittest.TestCase):
    def test_known_models(self):
        self.assertEqual(robot_from_reply("G | Bittle X | B10_260527 | ?"), "bittle")
        self.assertEqual(robot_from_reply("Nybble Q | N10_260820 | ?"), "nybble")

    def test_unknown(self):
        self.assertIsNone(robot_from_reply("hello | ?"))


class MockFirmware:
    """Mirrors src/webServer.h: 'running', a sensor event to ignore, then 'completed' with printed text."""

    def __init__(self, reply=None):
        self.received = []
        self.reply = reply or (lambda m: {"type": "response", "taskId": m["taskId"], "status": "completed",
                                          "results": [m["commands"][0][1:] + "\r\nk\r\n"]})
        self.server = serve(self.handle, "127.0.0.1", 0)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"ws://127.0.0.1:{self.server.socket.getsockname()[1]}"

    def handle(self, ws):
        for raw in ws:
            msg = json.loads(raw)
            self.received.append(msg)
            if msg["type"] != "command":
                continue
            ws.send(json.dumps({"type": "response", "taskId": msg["taskId"], "status": "running"}))
            ws.send(json.dumps({"type": "event_us", "distance": 30}))
            replies = self.reply(msg)
            for r in replies if isinstance(replies, list) else [replies]:
                ws.send(json.dumps(r))

    def close(self):
        self.server.shutdown()


class WsLinkTest(unittest.TestCase):
    def send(self, fw, command, timeout=2):
        self.addCleanup(fw.close)
        link = WsLink(fw.url)
        try:
            return link.send(command, timeout=timeout)
        finally:
            link.close()

    def test_one_command_per_task_and_completed_results(self):
        fw = MockFirmware()
        self.assertEqual(self.send(fw, "ksit"), "sit | k")
        msg = fw.received[0]
        self.assertEqual((msg["type"], msg["commands"]), ("command", ["ksit"]))
        self.assertIsInstance(msg["taskId"], str)
        self.assertIsInstance(msg["timestamp"], int)

    def test_busy_error_raises_even_with_other_task_id(self):
        fw = MockFirmware(reply=lambda m: {"type": "response", "taskId": "older-task", "status": "error",
                                           "error": "Previous web task is still running"})
        with self.assertRaisesRegex(RuntimeError, "still running"):
            self.send(fw, "ksit")

    def test_busy_error_is_retried_once(self):
        """webServer.h drops a command sent while a task runs, but also clears that task, so a retry is accepted.
        Without this, Ctrl+C's STOP was rejected over Wi-Fi and the robot kept walking (2026-10-23)."""
        calls = []

        def reply(m):
            calls.append(m["commands"][0])
            if len(calls) == 1:
                return {"type": "response", "taskId": "walk-task", "status": "error",
                        "error": "Previous web task is still running"}
            return {"type": "response", "taskId": m["taskId"], "status": "completed", "results": ["balance\r\nk\r\n"]}

        fw = MockFirmware(reply=reply)
        self.assertEqual(self.send(fw, "kbalance"), "balance | k")
        self.assertEqual(calls, ["kbalance", "kbalance"])

    def test_untagged_error_raises(self):
        fw = MockFirmware(reply=lambda m: {"type": "error", "error": "Heartbeat timeout"})
        with self.assertRaisesRegex(RuntimeError, "Heartbeat timeout"):
            self.send(fw, "ksit")

    def test_completed_with_other_task_id_is_ignored(self):
        fw = MockFirmware(reply=lambda m: [
            {"type": "response", "taskId": "someone-else", "status": "completed", "results": ["wrong\r\n"]},
            {"type": "response", "taskId": m["taskId"], "status": "completed", "results": ["sit\r\nk\r\n"]}])
        self.assertEqual(self.send(fw, "ksit"), "sit | k")

    def test_no_completed_reply_times_out(self):
        fw = MockFirmware(reply=lambda m: {"type": "response", "taskId": m["taskId"], "status": "running"})
        with self.assertRaises(TimeoutError):
            self.send(fw, "ksit", timeout=0.3)

    def test_heartbeat_is_sent_while_idle(self):
        fw = MockFirmware()
        self.addCleanup(fw.close)
        with mock.patch.object(links, "HEARTBEAT_S", 0.05):
            link = WsLink(fw.url)
        self.addCleanup(link.close)
        time.sleep(0.3)
        beats = [m for m in fw.received if m["type"] == "heartbeat"]
        self.assertGreaterEqual(len(beats), 1)
        self.assertIsInstance(beats[0]["timestamp"], int)


class DetectWsRobotTest(unittest.TestCase):
    def test_reply_with_model_name(self):
        fw = MockFirmware(reply=lambda m: {"type": "response", "taskId": m["taskId"], "status": "completed",
                                           "results": ["G\r\nBittle X\r\nB10_260527\r\n?\r\n"]})
        self.addCleanup(fw.close)
        link = WsLink(fw.url)
        self.addCleanup(link.close)
        self.assertEqual(links.detect_ws_robot(link), "bittle")

    def test_reply_without_model_name_returns_none(self):
        fw = MockFirmware()  # replies "<command minus first char>\r\nk"
        self.addCleanup(fw.close)
        link = WsLink(fw.url)
        self.addCleanup(link.close)
        self.assertIsNone(links.detect_ws_robot(link))


class WifiSetupTest(unittest.TestCase):
    def test_success_returns_ip_although_robot_reboots_without_echo(self):
        """On success the firmware prints the IP, then reboots: the 'w' echo never comes (reaction.h:436-474)."""
        ser = FakeSerial({"w%Lab%s3cret": b"Successfully connected Wifi to IP Address: 192.168.1.50\r\n"
                                         b"Rebooting to use web server.\r\n"})
        self.assertEqual(links.wifi_setup(SerialLink(ser), "Lab", "s3cret", timeout=1), "192.168.1.50")

    def test_already_connected_returns_ip(self):
        ser = FakeSerial({"w%Lab%s3cret": b"Wifi already connected to IP Address: 10.0.0.7\r\nw\r\n"})
        self.assertEqual(links.wifi_setup(SerialLink(ser), "Lab", "s3cret", timeout=1), "10.0.0.7")

    def test_sends_join_command_and_returns_ip(self):
        ser = FakeSerial({"w%Lab%s3cret": b"WifiSSID: \tLab\r\nPassword: \t**cret\r\n"
                                         b"Successfully connected Wifi to IP Address: 192.168.1.50\r\nw\r\n"})
        self.assertEqual(links.wifi_setup(SerialLink(ser), "Lab", "s3cret"), "192.168.1.50")
        self.assertEqual(ser.written, b"w%Lab%s3cret\n")

    def test_failure_raises_without_echoing_password(self):
        ser = FakeSerial({"w%Lab%s3cret": b"connection failed\r\nw\r\n"})
        with self.assertRaises(RuntimeError) as e:
            links.wifi_setup(SerialLink(ser), "Lab", "s3cret")
        self.assertNotIn("s3cret", str(e.exception))

    def test_wifi_ip_when_connected(self):
        ser = FakeSerial({"w": b"Wifi already connected to IP Address: 10.0.0.7\r\nw\r\n"})
        self.assertEqual(links.wifi_ip(SerialLink(ser)), "10.0.0.7")
        self.assertEqual(ser.written, b"w\n")

    def test_wifi_ip_when_not_on_wifi_returns_none(self):
        ser = FakeSerial({"w": b"The wifi info should start with 'w'...\r\nw\r\n"})
        self.assertIsNone(links.wifi_ip(SerialLink(ser)))

    def test_percent_sign_rejected(self):
        with self.assertRaises(ValueError):
            links.wifi_setup(SerialLink(FakeSerial({})), "Lab%2", "pw")

    def test_timeout_does_not_leak_masked_password(self):
        """The firmware echoes the password with its last 4 characters visible; a timeout must not show it."""
        ser = FakeSerial({"w%Lab%s3cret": b"WifiSSID: \tLab\r\nPassword: \t**cret\r\n"})  # no IP, no 'w' echo
        with self.assertRaises(TimeoutError) as e:
            links.wifi_setup(SerialLink(ser), "Lab", "s3cret", timeout=0.2)
        self.assertNotIn("cret", str(e.exception))


if __name__ == "__main__":
    unittest.main()
