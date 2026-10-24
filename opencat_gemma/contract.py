"""Robot command contract: allowed codes, the Gemma prompt, and a JSON schema, built from contract/<robot>.json.

Run `python -m opencat_gemma.contract` to regenerate contract/<robot>.prompt.txt and .schema.json
(checked in so teams on Android or other languages can use them without Python).
"""
import json
import re
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"
ROBOTS = ("bittle", "nybble")
KINDS = ("steps", "timed", "once")
MAX_STEPS = 20
STEPS_RE = "([1-9]|1[0-9]|20)"  # 1..MAX_STEPS, no leading zeros


class Contract:
    def __init__(self, data):
        self.robot = data["robot"]
        self.codes = data["codes"]
        self.examples = data["examples"]
        for code, v in self.codes.items():
            if v["kind"] not in KINDS:
                raise ValueError(f"{code}: kind {v['kind']!r} must be one of {KINDS}")
        stepped = [c for c, v in self.codes.items() if v["kind"] == "steps"]
        plain = [c for c, v in self.codes.items() if v["kind"] != "steps"]
        self.pattern = f"^(({'|'.join(stepped)})( {STEPS_RE})?|{'|'.join(plain)})$"
        self.schema = {"type": "array", "items": {"type": "string", "pattern": self.pattern}}
        # Examples come first: with the long code list, examples placed after it were ignored and
        # Gemma 4 E2B dropped later actions ("walk forward then sit" -> ["kwkF"]). Measured 2026-10-23.
        self.prompt = "\n".join([
            "Examples:",
            *(f"{json.dumps(req)} -> {json.dumps(cmds, separators=(',', ':'))}" for req, cmds in self.examples),
            "",
            f"You control a Petoi {self.robot}. Translate my request into a JSON array of command strings, in order. "
            "Use ONLY these codes:",
            *(f"{c}: {v['meaning']}" for c, v in self.codes.items()),
            f"{', '.join(stepped)} may be followed by a space and a number of steps from 1 to {MAX_STEPS}, "
            f'e.g. "{stepped[0]} 5". Leave the number out if the request gives none.',
            "If nothing matches, return []. Reply with JSON only, no explanation.",
        ])

    def validate(self, commands):
        """Return the commands that are NOT allowed; an empty list means all are allowed."""
        return [c for c in commands if not isinstance(c, str) or not re.fullmatch(self.pattern, c)]


def load(robot):
    return Contract(json.loads((CONTRACT_DIR / f"{robot}.json").read_text()))


if __name__ == "__main__":
    for robot in ROBOTS:
        c = load(robot)
        (CONTRACT_DIR / f"{robot}.prompt.txt").write_text(c.prompt + "\n")
        (CONTRACT_DIR / f"{robot}.schema.json").write_text(json.dumps(c.schema, indent=2) + "\n")
        print(f"wrote contract/{robot}.prompt.txt and contract/{robot}.schema.json")
