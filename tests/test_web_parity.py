"""web/parse_cases.json through the real Python parser; web/parse.test.mjs runs the same file through web/parse.js."""
import json
import unittest
from pathlib import Path

from opencat_gemma.contract import load
from opencat_gemma.gemma import parse

CASES = json.loads((Path(__file__).resolve().parent.parent / "web" / "parse_cases.json").read_text())


class WebParityTest(unittest.TestCase):
    def test_fixture_matches_python_parse(self):
        contract = load("bittle")
        for case in CASES:
            with self.subTest(raw=case["raw"]):
                commands, err = parse(contract, case["raw"])
                self.assertEqual(commands, case["commands"])
                if case["error"] is None:
                    self.assertIsNone(err)
                else:
                    self.assertTrue(err and err.startswith(case["error"]), err)


if __name__ == "__main__":
    unittest.main()
