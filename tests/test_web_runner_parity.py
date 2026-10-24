"""web/plan_cases.json through the real runner.plan; web/runner.test.mjs runs the same file through web/runner.js."""
import json
import unittest
from pathlib import Path

from opencat_gemma.contract import load
from opencat_gemma.runner import plan

CASES = json.loads((Path(__file__).resolve().parent.parent / "web" / "plan_cases.json").read_text())


class WebRunnerParityTest(unittest.TestCase):
    def test_fixture_matches_python_plan(self):
        for case in CASES:
            with self.subTest(robot=case["robot"], commands=case["commands"]):
                logs = []
                if case["error"]:
                    with self.assertRaises(ValueError) as cm:
                        plan(load(case["robot"]), case["commands"], log=logs.append)
                    self.assertTrue(str(cm.exception).startswith(case["error"]), cm.exception)
                else:
                    got = plan(load(case["robot"]), case["commands"], log=logs.append)
                    self.assertEqual([list(step) for step in got], case["plan"])
                self.assertEqual(logs, case["log"])


if __name__ == "__main__":
    unittest.main()
