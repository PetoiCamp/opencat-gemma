import unittest

from opencat_gemma.contract import load
from opencat_gemma.gemma import parse

C = load("bittle")


class ParseTest(unittest.TestCase):
    def test_bare_list(self):
        self.assertEqual(parse(C, '["kwkF","ksit"]'), (["kwkF", "ksit"], None))

    def test_step_count(self):
        self.assertEqual(parse(C, '["kbalance","kwkF 5"]'), (["kbalance", "kwkF 5"], None))

    def test_empty_list_is_refusal(self):
        self.assertEqual(parse(C, "[]"), ([], None))

    def test_list_wrapped_in_object(self):
        self.assertEqual(parse(C, '{"commands":["khi"]}'), (["khi"], None))

    def test_empty_object_is_not_a_list(self):
        self.assertEqual(parse(C, "{}"), (None, "not a list"))

    def test_invalid_json(self):
        self.assertEqual(parse(C, "UART: kwh"), (None, "invalid JSON"))

    def test_unknown_code_rejected(self):
        self.assertEqual(parse(C, '["kwkF","kfly"]'), (None, "not allowed: ['kfly']"))

    def test_non_string_element_rejected_not_crash(self):
        self.assertEqual(parse(C, '[{"cmd":"ksit"}]'), (None, "not allowed: [{'cmd': 'ksit'}]"))


if __name__ == "__main__":
    unittest.main()
