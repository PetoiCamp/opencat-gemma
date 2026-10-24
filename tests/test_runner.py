import unittest

from opencat_gemma.contract import load
from opencat_gemma.runner import DEFAULT_STEPS, STOP, plan, run

C = load("bittle")
Q = load("quaddle")


class FakeLink:
    def __init__(self, fail_on=None, interrupt_on=None, stop_fails=False):
        self.sent, self.fail_on, self.interrupt_on, self.stop_fails = [], fail_on, interrupt_on, stop_fails

    def send(self, command, timeout):
        self.sent.append((command, timeout))
        if command == STOP and self.stop_fails:
            raise OSError("port gone")
        if command == self.fail_on:
            raise TimeoutError(command)
        if command == self.interrupt_on:
            raise KeyboardInterrupt
        return "ok | k"


class EchoLink(FakeLink):
    """Records the echo override, like SerialLink/BleLink accept it."""

    def __init__(self, is_ble=False, **kw):
        super().__init__(**kw)
        self.is_ble, self.echoes = is_ble, []

    def send(self, command, timeout, echo=None):
        self.echoes.append((command, echo))
        return super().send(command, timeout)


class QuaddlePlanTest(unittest.TestCase):
    def test_commands_after_a_final_code_are_dropped_and_logged(self):
        logs = []
        self.assertEqual(plan(Q, ["vcv", "XO", "ksit", "kwkF"], log=logs.append),
                         [("vcv", 10, False), ("XO", 10, False)])
        self.assertEqual(logs, ["  dropped ksit, kwkF after XO/Xo"])

    def test_final_code_last_logs_nothing(self):
        logs = []
        self.assertEqual(plan(Q, ["m0 45", "Xo"], log=logs.append), [("m0 45", 10, False), ("Xo", 10, False)])
        self.assertEqual(logs, [])

    def test_xo_over_bluetooth_is_refused_before_any_send(self):
        link = EchoLink(is_ble=True)
        with self.assertRaisesRegex(ValueError, "XO \\(mouse mode\\) disconnects Bluetooth; use USB or Wi-Fi"):
            run(Q, ["ksit", "XO"], link, log=lambda *_: None)
        self.assertEqual(link.sent, [])

    def test_xo_over_usb_and_xo_lower_over_bluetooth_are_sent(self):
        run(Q, ["XO"], EchoLink(), log=lambda *_: None)
        link = EchoLink(is_ble=True)
        run(Q, ["Xo"], link, log=lambda *_: None)
        self.assertEqual([c for c, _ in link.sent], ["Xo"])

    def test_echo_override_reaches_link_send_only_when_set(self):
        link = EchoLink()
        run(Q, ["vcb", "m0 45", "XO"], link, log=lambda *_: None)
        self.assertEqual(link.echoes, [("vcb", None), ("m0 45", None), ("XO", "k")])
        self.assertEqual(run(Q, ["ksit", "m0 45"], FakeLink(), log=lambda *_: None), ["ok | k", "ok | k"])  # no echo=


class PlanTest(unittest.TestCase):
    def test_walks_get_default_steps_and_step_timeouts(self):
        self.assertEqual(plan(C, ["kwkF", "kbk 4"]),
                         [("kwkF 3", 5 + 2 * DEFAULT_STEPS, False), ("kbk 4", 13, False)])

    def test_turns_are_timed_by_us(self):
        self.assertEqual(plan(C, ["kwkL"]), [("kwkL", 10, True)])

    def test_rejects_disallowed_before_planning(self):
        with self.assertRaisesRegex(ValueError, "kwkL 90"):
            plan(C, ["ksit", "kwkL 90"])


class RunTest(unittest.TestCase):
    def setUp(self):
        self.sleeps = []

    def go(self, link, commands):
        return run(C, commands, link, turn_seconds=2.0, sleep=self.sleeps.append, log=lambda *_: None)

    def test_sends_in_order(self):
        link = FakeLink()
        self.go(link, ["kbalance", "kwkF 5", "ksit"])
        self.assertEqual([c for c, _ in link.sent], ["kbalance", "kwkF 5", "ksit"])
        self.assertEqual(self.sleeps, [])

    def test_turn_is_held_then_stopped(self):
        link = FakeLink()
        self.go(link, ["kwkL", "ksit"])
        self.assertEqual([c for c, _ in link.sent], ["kwkL", STOP, "ksit"])
        self.assertEqual(self.sleeps, [2.0])

    def test_timeout_sends_stop_and_reraises(self):
        link = FakeLink(fail_on="kwkF 3")
        with self.assertRaises(TimeoutError):
            self.go(link, ["kwkF", "ksit"])
        self.assertEqual([c for c, _ in link.sent], ["kwkF 3", STOP])

    def test_ctrl_c_sends_stop_and_reraises(self):
        link = FakeLink(interrupt_on="kwkR")
        with self.assertRaises(KeyboardInterrupt):
            self.go(link, ["kwkR"])
        self.assertEqual([c for c, _ in link.sent], ["kwkR", STOP])

    def test_ctrl_c_during_turn_pause_sends_stop_and_reraises(self):
        def interrupt(_):
            raise KeyboardInterrupt

        link = FakeLink()
        with self.assertRaises(KeyboardInterrupt):
            run(C, ["kwkL"], link, sleep=interrupt, log=lambda *_: None)
        self.assertEqual([c for c, _ in link.sent], ["kwkL", STOP])

    def test_failed_stop_is_logged_and_original_error_raised(self):
        link = FakeLink(fail_on="kwkF 3", stop_fails=True)
        logs = []
        with self.assertRaises(TimeoutError):
            run(C, ["kwkF"], link, sleep=self.sleeps.append, log=lambda *a: logs.append(" ".join(map(str, a))))
        self.assertTrue(any("STOP FAILED" in m for m in logs))

    def test_empty_sends_nothing(self):
        link = FakeLink()
        self.assertEqual(self.go(link, []), [])
        self.assertEqual(link.sent, [])

    def test_disallowed_sends_nothing(self):
        link = FakeLink()
        with self.assertRaises(ValueError):
            self.go(link, ["kfly"])
        self.assertEqual(link.sent, [])


if __name__ == "__main__":
    unittest.main()
