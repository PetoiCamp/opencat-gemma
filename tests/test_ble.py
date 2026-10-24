import asyncio
import io
import re
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from opencat_gemma import ble, links

GREETING = b"Petoi Bittle Xpg\r\nrest\r\nd\r\n"
QUERY_BITTLE = {"?": b"Bittle X\r\nB10_260527\r\n?\r\n"}
# Quaddle (S3 firmware Q_261022, 2026-10-23): silent on connect; the first '?' gets the handshake as separate
# notifications with no line breaks.
S3_HANDSHAKE = [b"Petoi Quaddle", b"u", b"Quaddle", b"Q_261022", b"?"]


class FakeClient:
    """Stands in for bleak.BleakClient. Notifications are delivered from the event loop thread, like bleak does."""

    def __init__(self, script=GREETING, replies=None, connect_error=None, disconnect_error=None):
        self.script, self.replies = script, {**QUERY_BITTLE, **(replies or {})}
        self.connect_error, self.disconnect_error = connect_error, disconnect_error
        self.callback, self.writes, self.disconnected = None, [], False

    def _notify(self, chunks):
        loop = asyncio.get_running_loop()
        for i, chunk in enumerate(chunks):
            loop.call_later(0.01 * (i + 1), self.callback, None, bytearray(chunk))

    async def connect(self):
        if self.connect_error:
            raise self.connect_error

    async def start_notify(self, uuid, callback):
        assert uuid == ble.NUS_TX
        self.callback = callback
        self._notify([self.script] if isinstance(self.script, bytes) else self.script)

    async def write_gatt_char(self, uuid, data, response=False):
        self.writes.append((uuid, bytes(data), response))
        chunks = self.replies.get(bytes(data).strip().decode(), [])
        self._notify([chunks] if isinstance(chunks, bytes) else chunks)

    async def disconnect(self):
        self.disconnected = True
        if self.disconnect_error:
            raise self.disconnect_error


class BleLinkTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ble, "PUSH_WAIT_S", 0.2)
        patcher.start()
        self.addCleanup(patcher.stop)

    def link(self, **kw):
        client = FakeClient(**kw)
        link = ble.BleLink(client)
        self.addCleanup(link.close)
        return client, link

    def test_esp32_style_waits_for_d_then_identifies_with_query(self):
        """ESP32 firmware pushes its greeting and forced rest; '?' goes out only after the 'd' line."""
        client, link = self.link(script=[b"Petoi Bittle Xpg\r\nrest\r\n", b"d\r\n"])
        reply = link.connect()
        self.assertEqual(reply, "Bittle X | B10_260527 | ?")
        self.assertEqual(links.robot_from_reply(reply), "bittle")
        self.assertEqual(client.writes, [(ble.NUS_RX, b"?\n", False)])

    def test_s3_style_silent_then_handshake_without_newlines(self):
        client, link = self.link(script=[], replies={"?": S3_HANDSHAKE})
        reply = link.connect()
        self.assertEqual(reply, "Petoi QuaddleuQuaddleQ_261022?")
        self.assertEqual(links.robot_from_reply(reply), "quaddle")
        self.assertEqual(client.writes, [(ble.NUS_RX, b"?\n", False)])  # nothing written before '?'

    def test_s3_style_line_based_reply_also_accepted(self):
        _, link = self.link(script=[], replies={"?": b"Petoi Quaddle\r\nu\r\nQuaddle\r\nQ_260529\r\n?\r\n"})
        self.assertEqual(links.robot_from_reply(link.connect()), "quaddle")

    def test_greeting_without_d_still_identifies_with_query(self):
        with mock.patch.object(ble, "GREETING_TIMEOUT_S", 0.2):
            _, link = self.link(script=b"Petoi Nybble Q\r\n", replies={"?": b"Nybble Q\r\nN10_260820\r\n?\r\n"})
            self.assertEqual(links.robot_from_reply(link.connect()), "nybble")

    def test_no_reply_to_query_times_out(self):
        with mock.patch.object(ble, "QUERY_TIMEOUT_S", 0.2):
            _, link = self.link(script=[], replies={"?": b"Quaddle"})
            with self.assertRaises(TimeoutError):
                link.connect()

    def test_connect_clears_buffer_so_send_sees_only_its_reply(self):
        _, link = self.link(replies={"kbalance": b"balance\r\nk\r\n"})
        link.connect()
        self.assertEqual(link._buf, "")

    def test_send_writes_to_rx_and_returns_on_echo(self):
        client, link = self.link(replies={"kbalance": b"balance\r\nk\r\n"})
        link.connect()
        self.assertEqual(link.send("kbalance", timeout=1), "balance | k")
        self.assertEqual(client.writes[-1], (ble.NUS_RX, b"kbalance\n", False))

    def test_send_waits_for_echo_override(self):
        client, link = self.link(replies={"Xo": b"mouse2up\r\nk\r\n"})
        link.connect()
        self.assertEqual(link.send("Xo", timeout=1, echo="k"), "mouse2up | k")
        self.assertTrue(link.is_ble)

    def test_notification_split_mid_line_is_joined(self):
        _, link = self.link(replies={"kbalance": [b"bal", b"ance\r\nk\r\n"]})
        link.connect()
        self.assertEqual(link.send("kbalance", timeout=1), "balance | k")

    def test_backflip_returns_only_after_the_firmwares_own_recovery(self):
        """Recorded over Web Bluetooth (Bittle X, 2026-10-23): the skill's first 'k' ends an IMU line (IMU readings have
        no newline), then the firmware itself recovers ('rc', 'up'). Only the last, standalone 'k' means done."""
        kbf = [b"bf\r\nICM: -3.63  2.26 -9.17-1460.7 -159.1  166.1\tk\r\n", b"ICM: -4.38 -0.05 -9.07-1459.1 -154.3 -179.7\trc\r\n",
               b"ICM:  0.31  0.02  9.99-1422.6    1.6    0.1\tup\r\n", b"k\r\n"]
        _, link = self.link(replies={"kbf": kbf})
        link.connect()
        self.assertRegex(link.send("kbf", timeout=2), r"\trc \| .*\tup \| k$")

    def test_send_without_echo_times_out(self):
        _, link = self.link(replies={"kbalance": b"balance\r\n"})
        link.connect()
        with self.assertRaises(TimeoutError):
            link.send("kbalance", timeout=0.2)

    def test_send_returns_on_done_pattern_without_echo(self):
        """The Wi-Fi join reboots the robot on success, so no 'w' echo ever arrives (reaction.h)."""
        _, link = self.link(replies={"w%Lab%pw": b"Successfully connected Wifi to IP Address: 10.0.0.7\r\nRebooting\r\n"})
        link.connect()
        reply = link.send("w%Lab%pw", timeout=1, done=re.compile("IP Address:"))
        self.assertIn("10.0.0.7", reply)

    def test_close_swallows_disconnect_errors(self):
        client, link = self.link(disconnect_error=RuntimeError("boom"))
        link.connect()
        link.close()
        self.assertTrue(client.disconnected)


class FindBleRobotTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(ble, "PUSH_WAIT_S", 0.2)
        patcher.start()
        self.addCleanup(patcher.stop)

    def patched(self, found, clients):
        async def discover(timeout, return_adv):
            return {d.address: (d, adv) for d, adv in found}
        return mock.patch.object(ble.BleakScanner, "discover", discover), \
            mock.patch.object(ble, "BleakClient", side_effect=lambda device: clients[device.address])

    def dev(self, address, name, rssi):
        return SimpleNamespace(address=address, name=name), SimpleNamespace(local_name=name, rssi=rssi)

    def test_strongest_first_skips_failed_connect_and_returns_good_robot(self):
        # With a name, both spellings of it can match; the strongest is tried first.
        found = [self.dev("weak", "Bittle0D_BLE", -80), self.dev("other", "Headphones", -30),
                 self.dev("strong", "Bittle0E_BLE", -50), self.dev("mid", "Bittle0E", -60)]
        clients = {"strong": FakeClient(connect_error=OSError("no")), "mid": FakeClient(), "weak": FakeClient()}
        scan, client_cls = self.patched(found, clients)
        out = io.StringIO()
        with scan, client_cls as factory, redirect_stdout(out):
            link, robot = ble.find_ble_robot(scan_s=0.1, name="Bittle0E")
        self.addCleanup(link.close)
        self.assertEqual(robot, "bittle")
        self.assertIs(link.client, clients["mid"])
        self.assertEqual([c.args[0].address for c in factory.call_args_list], ["strong", "mid"])
        self.assertTrue(clients["strong"].disconnected)
        self.assertIn("Found bittle over Bluetooth", out.getvalue())

    def test_progress_messages_while_searching_and_connecting(self):
        """The search takes ~15-20 s; silence looked like a hang (Kai, 2026-10-23)."""
        found = [self.dev("strong", "Bittle0E_BLE", -50), self.dev("mid", "Bittle0E", -60)]
        clients = {"strong": FakeClient(connect_error=OSError("no")), "mid": FakeClient()}
        scan, client_cls = self.patched(found, clients)
        out = io.StringIO()
        with scan, client_cls, redirect_stdout(out):
            link, _ = ble.find_ble_robot(scan_s=0.1, name="Bittle0E")
        self.addCleanup(link.close)
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("Searching for a Petoi robot over Bluetooth"), lines)
        self.assertIn("Connecting to Bittle0E_BLE...", lines)
        self.assertIn("Connecting to Bittle0E...", lines)

    def test_scan_keeps_quaddle_and_petoi_fallback_names(self):
        self.assertTrue("quaddle3f_ble".startswith(ble.NAME_PREFIXES))
        self.assertTrue("petoi_ble".startswith(ble.NAME_PREFIXES))
        found = [self.dev("q", "Quaddle3F_BLE", -50), self.dev("x", "Headphones", -30)]
        clients = {"q": FakeClient(script=[], replies={"?": S3_HANDSHAKE})}
        scan, client_cls = self.patched(found, clients)
        with scan, client_cls as factory, redirect_stdout(io.StringIO()):
            link, robot = ble.find_ble_robot(scan_s=0.1)
        self.addCleanup(link.close)
        self.assertEqual(robot, "quaddle")
        self.assertEqual([c.args[0].address for c in factory.call_args_list], ["q"])

    def test_no_matching_devices_raises_mentioning_bluetooth(self):
        scan, client_cls = self.patched([self.dev("x", "Headphones", -30)], {})
        out = io.StringIO()
        with scan, client_cls, redirect_stdout(out), self.assertRaisesRegex(RuntimeError, "Bluetooth"):
            ble.find_ble_robot(scan_s=0.1)
        self.assertIn("Searching for a Petoi robot over Bluetooth", out.getvalue())

    def test_several_candidates_without_name_raise_before_connecting(self):
        found = [self.dev("a", "Bittle0D_BLE", -80), self.dev("b", "Quaddle03_BLE", -45), self.dev("x", "Headphones", -30)]
        scan, client_cls = self.patched(found, {})
        with scan, client_cls as factory, redirect_stdout(io.StringIO()):
            with self.assertRaises(ble.MultipleRobotsError) as e:
                ble.find_ble_robot(scan_s=0.1)
        factory.assert_not_called()
        self.assertIsInstance(e.exception, RuntimeError)
        msg = str(e.exception)
        self.assertLess(msg.index("Quaddle03_BLE (signal -45 dBm)"), msg.index("Bittle0D_BLE (signal -80 dBm)"))
        self.assertTrue(msg.endswith("Choose yours with --bluetooth --name <name>. "
                                     "Find your robot's name over USB with --robot-name."), msg)

    def test_name_filter_picks_exact_device_with_or_without_suffix(self):
        for given in ("Quaddle03", "quaddle03_ble"):
            found = [self.dev("a", "Quaddle04_BLE", -30), self.dev("b", "Quaddle03_BLE", -70)]
            clients = {"b": FakeClient(script=[], replies={"?": S3_HANDSHAKE})}
            scan, client_cls = self.patched(found, clients)
            with scan, client_cls as factory, redirect_stdout(io.StringIO()):
                link, robot = ble.find_ble_robot(scan_s=0.1, name=given)
            self.addCleanup(link.close)
            self.assertEqual(robot, "quaddle")
            self.assertEqual([c.args[0].address for c in factory.call_args_list], ["b"])

    def test_name_filter_accepts_custom_name_without_known_prefix(self):
        found = [self.dev("t", "Team7_BLE", -70), self.dev("o", "Bittle0D_BLE", -30)]
        clients = {"t": FakeClient(script=[], replies={"?": S3_HANDSHAKE})}
        scan, client_cls = self.patched(found, clients)
        with scan, client_cls as factory, redirect_stdout(io.StringIO()):
            link, robot = ble.find_ble_robot(scan_s=0.1, name="Team7")
        self.addCleanup(link.close)
        self.assertEqual(robot, "quaddle")
        self.assertEqual([c.args[0].address for c in factory.call_args_list], ["t"])

    def test_name_not_found_names_it_in_the_error(self):
        scan, client_cls = self.patched([self.dev("a", "Bittle0D_BLE", -30)], {})
        with scan, client_cls as factory, redirect_stdout(io.StringIO()), \
                self.assertRaisesRegex(RuntimeError, "Team9") as e:
            ble.find_ble_robot(scan_s=0.1, name="Team9")
        factory.assert_not_called()
        self.assertNotIsInstance(e.exception, ble.MultipleRobotsError)


if __name__ == "__main__":
    unittest.main()
