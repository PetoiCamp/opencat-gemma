import json
import unittest

from opencat_gemma.contract import CONTRACT_DIR, ROBOTS, Contract, load, registry


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.c = load("bittle")

    def test_accepts_codes_and_step_counts(self):
        self.assertEqual(self.c.validate(["kwkF", "kwkF 5", "kbk 20", "kwkL", "ksit", "khi"]), [])

    def test_rejects_unknown_codes_bad_counts_and_turn_angles(self):
        bad = ["kfly", "kwkF 0", "kwkF 21", "kwkF 05", "kwkL 90", "ksit 2", "kwkF  5", "", 5]
        self.assertEqual(self.c.validate(bad), bad)

    def test_prompt_lists_every_code_and_example(self):
        for code, spec in self.c.codes.items():
            self.assertIn(f"{code}: {spec['meaning']}", self.c.prompt)
        self.assertIn('"take 3 steps back and wave" -> ["kbk 3","khi"]', self.c.prompt)

    def test_examples_are_valid_commands(self):
        for robot in ROBOTS:
            c = load(robot)
            for _, commands in c.examples:
                self.assertEqual(c.validate(commands), [], robot)

    def test_generated_files_are_in_sync(self):
        for robot in ROBOTS:
            c = load(robot)
            self.assertEqual((CONTRACT_DIR / f"{robot}.prompt.txt").read_text(), c.prompt + "\n", robot)
            self.assertEqual(json.loads((CONTRACT_DIR / f"{robot}.schema.json").read_text()), c.schema, robot)

    def test_robots_and_registry_come_from_contract_files(self):
        self.assertEqual(ROBOTS, ("bittle", "nybble", "quaddle"))
        self.assertEqual(registry(), {"bittle": ("Bittle", "bittle"), "nybble": ("Nybble", "nybble"),
                                      "quaddle": ("Quaddle", "quaddle")})

    def test_unknown_kind_rejected(self):
        data = {"robot": "x", "codes": {"kwkL": {"meaning": "turn left", "kind": "time"}}, "examples": []}
        with self.assertRaises(ValueError):
            Contract(data)


if __name__ == "__main__":
    unittest.main()
