import asyncio
import io
import re
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest import mock

from opencat_gemma import ble, links

GREETING = b"Petoi Bittle Xpg\r\nrest\r\nd\r\n"


class FakeClient:
    """Stands in for bleak.BleakClient. Notifications are delivered from the event loop thread, like bleak does."""

    def __init__(self, script=GREETING, replies=None, connect_error=None, disconnect_error=None):
        self.script, self.replies = script, replies or {}
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
    def link(self, **kw):
        client = FakeClient(**kw)
        link = ble.BleLink(client)
        self.addCleanup(link.close)
        return client, link

    def test_connect_waits_for_d_line_and_greeting_identifies_robot(self):
        client, link = self.link(script=[b"Petoi Bittle Xpg\r\nrest\r\n", b"d\r\n"])
        greeting = link.connect()
        self.assertTrue(greeting.endswith("d"))
        self.assertEqual(links.robot_from_reply(greeting), "bittle")

    def test_connect_without_d_but_with_model_name_still_succeeds(self):
        with mock.patch.object(ble, "GREETING_TIMEOUT_S", 0.2):
            _, link = self.link(script=b"Petoi Nybble Q\r\n")
            self.assertEqual(links.robot_from_reply(link.connect()), "nybble")

    def test_send_writes_to_rx_and_returns_on_echo(self):
        client, link = self.link(replies={"kbalance": b"balance\r\nk\r\n"})
        link.connect()
        self.assertEqual(link.send("kbalance", timeout=1), "balance | k")
        self.assertEqual(client.writes, [(ble.NUS_RX, b"kbalance\n", False)])

    def test_notification_split_mid_line_is_joined(self):
        _, link = self.link(replies={"kbalance": [b"bal", b"ance\r\nk\r\n"]})
        link.connect()
        self.assertEqual(link.send("kbalance", timeout=1), "balance | k")

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
    def patched(self, found, clients):
        async def discover(timeout, return_adv):
            return {d.address: (d, adv) for d, adv in found}
        return mock.patch.object(ble.BleakScanner, "discover", discover), \
            mock.patch.object(ble, "BleakClient", side_effect=lambda device: clients[device.address])

    def dev(self, address, name, rssi):
        return SimpleNamespace(address=address, name=name), SimpleNamespace(local_name=name, rssi=rssi)

    def test_strongest_first_skips_failed_connect_and_returns_good_robot(self):
        found = [self.dev("weak", "Bittle0D_BLE", -80), self.dev("other", "Headphones", -30),
                 self.dev("strong", "Bittle0E_BLE", -50), self.dev("mid", "Nybble12_BLE", -60)]
        clients = {"strong": FakeClient(connect_error=OSError("no")), "mid": FakeClient(), "weak": FakeClient()}
        scan, client_cls = self.patched(found, clients)
        out = io.StringIO()
        with scan, client_cls as factory, redirect_stdout(out):
            link, robot = ble.find_ble_robot(scan_s=0.1)
        self.addCleanup(link.close)
        self.assertEqual(robot, "bittle")
        self.assertIs(link.client, clients["mid"])
        self.assertEqual([c.args[0].address for c in factory.call_args_list], ["strong", "mid"])
        self.assertTrue(clients["strong"].disconnected)
        self.assertIn("Found bittle over Bluetooth", out.getvalue())

    def test_progress_messages_while_searching_and_connecting(self):
        """The search takes ~15-20 s; silence looked like a hang (Kai, 2026-10-23)."""
        found = [self.dev("strong", "Bittle0E_BLE", -50), self.dev("mid", "Nybble12_BLE", -60)]
        clients = {"strong": FakeClient(connect_error=OSError("no")), "mid": FakeClient()}
        scan, client_cls = self.patched(found, clients)
        out = io.StringIO()
        with scan, client_cls, redirect_stdout(out):
            link, _ = ble.find_ble_robot(scan_s=0.1)
        self.addCleanup(link.close)
        lines = out.getvalue().splitlines()
        self.assertTrue(lines[0].startswith("Searching for a Petoi robot over Bluetooth"), lines)
        self.assertIn("Connecting to Bittle0E_BLE...", lines)
        self.assertIn("Connecting to Nybble12_BLE...", lines)

    def test_no_matching_devices_raises_mentioning_bluetooth(self):
        scan, client_cls = self.patched([self.dev("x", "Headphones", -30)], {})
        out = io.StringIO()
        with scan, client_cls, redirect_stdout(out), self.assertRaisesRegex(RuntimeError, "Bluetooth"):
            ble.find_ble_robot(scan_s=0.1)
        self.assertIn("Searching for a Petoi robot over Bluetooth", out.getvalue())


if __name__ == "__main__":
    unittest.main()
