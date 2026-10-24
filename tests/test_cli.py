import io
import shlex
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

from opencat_gemma import __main__ as cli


class CliTest(unittest.TestCase):
    def test_dry_run_prints_plan_and_opens_no_robot(self):
        out = io.StringIO()
        with mock.patch.object(cli, "ask", return_value='["kbalance","kwkF","kwkL"]'), \
             mock.patch.object(cli, "find_robot") as find, redirect_stdout(out):
            cli.main(["--dry-run", "--robot", "bittle", "stand up, walk, turn left"])
        find.assert_not_called()
        self.assertIn("would send: kbalance, kwkF 3, kwkL (then kbalance after 2.0s)", out.getvalue())

    def test_quaddle_is_a_robot_choice(self):
        out = io.StringIO()
        with mock.patch.object(cli, "ask", return_value='["kbkF 2"]'), redirect_stdout(out):
            cli.main(["--dry-run", "--robot", "quaddle", "walk backward 2 steps"])
        self.assertIn("would send: kbkF 2", out.getvalue())

    def test_rejected_output_exits_nonzero(self):
        with mock.patch.object(cli, "ask", return_value="UART: kwh"), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as e:
                cli.main(["--dry-run", "sit"])
        self.assertIn("invalid JSON", str(e.exception.code))


class FakeLink:
    def __init__(self, interrupt_on=None):
        self.sent, self.closed, self.interrupt_on = [], False, interrupt_on

    def send(self, command, timeout):
        self.sent.append(command)
        if command == self.interrupt_on:
            raise KeyboardInterrupt
        return "ok | k"

    def close(self):
        self.closed = True


class ChatTest(unittest.TestCase):
    def chat(self, lines, replies, link=None, argv=()):
        out = io.StringIO()
        with mock.patch.object(cli, "ask", side_effect=replies), \
             mock.patch.object(cli, "find_robot", return_value=(link, "bittle")), \
             mock.patch("builtins.input", side_effect=[*lines, EOFError]), redirect_stdout(out):
            cli.main(list(argv))
        return out.getvalue()

    def test_dry_run_chat_keeps_going_after_rejection(self):
        out = self.chat(["sit down", "", "nonsense"], ['["ksit"]', "UART: kwh"], argv=["--dry-run"])
        self.assertIn("would send: ksit", out)
        self.assertIn("Rejected: invalid JSON", out)

    def test_chat_sends_to_robot_on_one_open_link(self):
        link = FakeLink()
        self.chat(["walk 3 steps", "sit"], ['["kwkF 3"]', '["ksit"]'], link=link)
        self.assertEqual(link.sent, ["kwkF 3", "ksit"])
        self.assertTrue(link.closed)

    def test_ctrl_c_during_move_stops_robot_and_returns_to_prompt(self):
        link = FakeLink(interrupt_on="kwkF 3")
        self.chat(["walk", "sit"], ['["kwkF"]', '["ksit"]'], link=link)
        self.assertEqual(link.sent, ["kwkF 3", "kbalance", "ksit"])
        self.assertTrue(link.closed)

    def test_bluetooth_flag_uses_ble_discovery(self):
        link = FakeLink()
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "bittle")) as find, \
             mock.patch.object(cli, "find_robot") as usb, \
             mock.patch.object(cli, "ask", return_value='["ksit"]'), redirect_stdout(io.StringIO()):
            cli.main(["--bluetooth", "sit"])
        find.assert_called_once_with()
        usb.assert_not_called()
        self.assertEqual(link.sent, ["ksit"])

    def test_ws_detects_robot_when_robot_not_given(self):
        link = FakeLink()
        with mock.patch.object(cli, "WsLink", return_value=link), \
             mock.patch.object(cli, "detect_ws_robot", return_value="nybble") as detect, \
             mock.patch.object(cli, "ask", return_value='["ksit"]'), redirect_stdout(io.StringIO()):
            cli.main(["--ws", "ws://127.0.0.1:81", "sit"])
        detect.assert_called_once_with(link)
        self.assertEqual(link.sent, ["ksit"])
        self.assertTrue(link.closed)

    def test_wifi_ip_prints_ip_without_asking_for_credentials(self):
        link = FakeLink()
        out = io.StringIO()
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "bittle")), \
             mock.patch.object(cli, "wifi_ip", return_value="10.0.0.7"), \
             mock.patch("builtins.input", side_effect=AssertionError("must not prompt")), redirect_stdout(out):
            cli.main(["--bluetooth", "--wifi-ip"])
        self.assertIn("Robot IP address: 10.0.0.7", out.getvalue().splitlines())
        self.assertIn("ws://10.0.0.7:81", out.getvalue())
        self.assertTrue(link.closed)

    def test_wifi_ip_not_on_wifi_exits_with_hint(self):
        link = FakeLink()
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "bittle")), \
             mock.patch.object(cli, "wifi_ip", return_value=None), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as e:
                cli.main(["--bluetooth", "--wifi-ip"])
        self.assertIn("--wifi-setup", str(e.exception.code))
        self.assertTrue(link.closed)

    def test_wifi_setup_prompts_and_prints_ws_url(self):
        link = FakeLink()
        out = io.StringIO()
        with mock.patch.object(cli, "find_robot", return_value=(link, "bittle")), \
             mock.patch.object(cli, "wifi_setup", return_value="192.168.1.50") as setup, \
             mock.patch("builtins.input", return_value="Lab"), \
             mock.patch.object(cli.getpass, "getpass", return_value="s3cret"), redirect_stdout(out):
            cli.main(["--wifi-setup"])
        setup.assert_called_once_with(link, "Lab", "s3cret")
        self.assertIn("ws://192.168.1.50:81", out.getvalue())
        self.assertIn("Robot IP address: 192.168.1.50", out.getvalue().splitlines())
        self.assertNotIn("s3cret", out.getvalue())
        self.assertTrue(link.closed)

    def test_wifi_setup_over_bluetooth_uses_ble(self):
        link = FakeLink()
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "bittle")) as find, \
             mock.patch.object(cli, "wifi_setup", return_value="192.168.1.50") as setup, \
             mock.patch("builtins.input", return_value="Lab"), \
             mock.patch.object(cli.getpass, "getpass", return_value="s3cret"), redirect_stdout(io.StringIO()):
            cli.main(["--wifi-setup", "--bluetooth"])
        find.assert_called_once_with()
        setup.assert_called_once_with(link, "Lab", "s3cret")
        self.assertTrue(link.closed)

    def test_single_shot_closes_link_when_ask_raises(self):
        link = FakeLink()
        with mock.patch.object(cli, "ask", side_effect=RuntimeError("ollama down")), \
             mock.patch.object(cli, "find_robot", return_value=(link, "bittle")), redirect_stdout(io.StringIO()):
            with self.assertRaises(RuntimeError):
                cli.main(["sit"])
        self.assertTrue(link.closed)




class BluetoothNameTest(unittest.TestCase):
    def test_bluetooth_with_name_passes_it_through(self):
        link = FakeLink()
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "bittle")) as find, \
             mock.patch.object(cli, "ask", return_value='["ksit"]'), redirect_stdout(io.StringIO()):
            cli.main(["--bluetooth", "--name", "Team7", "sit"])
        find.assert_called_once_with(name="Team7")

    def test_bluetooth_request_is_not_taken_as_name(self):
        link, asked = FakeLink(), []
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "bittle")) as find, \
             mock.patch.object(cli, "ask", side_effect=lambda c, t, model: asked.append(t) or '["ksit"]'), \
             redirect_stdout(io.StringIO()):
            cli.main(["--bluetooth", "walk forward"])
        find.assert_called_once_with()
        self.assertEqual(asked, ["walk forward"])

    def test_name_without_bluetooth_errors(self):
        with mock.patch("sys.stderr", io.StringIO()), self.assertRaises(SystemExit) as e:
            cli.main(["--name", "Team7", "sit"])
        self.assertEqual(e.exception.code, 2)

    def test_wifi_setup_with_bluetooth_name(self):
        link = FakeLink()
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "bittle")) as find, \
             mock.patch.object(cli, "wifi_setup", return_value="192.168.1.50"), \
             mock.patch("builtins.input", return_value="Lab"), \
             mock.patch.object(cli.getpass, "getpass", return_value="x"), redirect_stdout(io.StringIO()):
            cli.main(["--wifi-setup", "--bluetooth", "--name", "Team7"])
        find.assert_called_once_with(name="Team7")

    def test_wifi_ip_with_bluetooth_name(self):
        link = FakeLink()
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "bittle")) as find, \
             mock.patch.object(cli, "wifi_ip", return_value="10.0.0.7"), redirect_stdout(io.StringIO()):
            cli.main(["--wifi-ip", "--bluetooth", "--name", "Team7"])
        find.assert_called_once_with(name="Team7")

    def test_multiple_robots_exits_with_message_not_traceback(self):
        err = ble_error = cli.MultipleRobotsError("Several Petoi robots are nearby: A, B.")
        with mock.patch.object(cli, "find_ble_robot", side_effect=err):
            with self.assertRaises(SystemExit) as e:
                cli.main(["--bluetooth", "sit"])
        self.assertEqual(e.exception.code, str(ble_error))


class RobotNameCliTest(unittest.TestCase):
    def test_prints_bluetooth_name_and_connect_hint(self):
        link, out = FakeLink(), io.StringIO()
        with mock.patch.object(cli, "find_robot", return_value=(link, "quaddle")), \
             mock.patch.object(cli, "robot_name", return_value="Quaddle03"), redirect_stdout(out):
            cli.main(["--robot-name"])
        # The hint names the interpreter actually running (quoted), not a bare "python" that may lack our
        # packages: a bare "python" hint led to ModuleNotFoundError: bleak (2026-10-23).
        run = f"{shlex.quote(sys.executable)} -m opencat_gemma"
        self.assertEqual(out.getvalue().splitlines(), ["Your robot's Bluetooth name: Quaddle03_BLE",
                                                       f"Connect with: {run} --bluetooth --name Quaddle03"])
        self.assertTrue(link.closed)

    def test_rename_prints_power_cycle_hint(self):
        link, out = FakeLink(), io.StringIO()
        with mock.patch.object(cli, "find_robot", return_value=(link, "quaddle")), \
             mock.patch.object(cli, "rename_robot", return_value="Team7 | n") as rename, redirect_stdout(out):
            cli.main(["--robot-name", "Team7"])
        rename.assert_called_once_with(link, "Team7")
        self.assertEqual(out.getvalue().strip(),
                         "Renamed to Team7. Switch the robot off and on, then connect with --bluetooth --name Team7")
        self.assertTrue(link.closed)

    def test_over_bluetooth_with_name(self):
        link = FakeLink()
        with mock.patch.object(cli, "find_ble_robot", return_value=(link, "quaddle")) as find, \
             mock.patch.object(cli, "robot_name", return_value="Team7"), redirect_stdout(io.StringIO()):
            cli.main(["--robot-name", "--bluetooth", "--name", "Team7"])
        find.assert_called_once_with(name="Team7")

    def test_over_port(self):
        link = FakeLink()
        with mock.patch.object(cli, "open_serial"), mock.patch.object(cli, "SerialLink", return_value=link), \
             mock.patch.object(cli, "robot_name", return_value="Bittle0D"), redirect_stdout(io.StringIO()):
            cli.main(["--robot-name", "--port", "/dev/x"])
        self.assertTrue(link.closed)


if __name__ == "__main__":
    unittest.main()
