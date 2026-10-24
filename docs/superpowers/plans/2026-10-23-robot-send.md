# opencat-gemma Starter Kit, Plan 1 of 2: Contract + Laptop Path

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public repo, `PetoiCamp/opencat-gemma`, that hackathon teams clone to control a Petoi Bittle X or Nybble Q with Gemma running on-device. Plan 1 delivers the shared command contract and the laptop path (Ollama → USB serial or WebSocket), with a stop on the computer's side.

**Architecture:**
- **Language-neutral contract.** `contract/<robot>.json` (codes, meanings, kinds, examples) generates the Gemma system prompt and a JSON schema. The generated files (`<robot>.prompt.txt`, `<robot>.schema.json`) are checked in, so Kotlin/C++ teams can use them without Python.
- **Python package `opencat_gemma`** contains:
  - `contract.py`: load the contract and validate commands;
  - `gemma.py`: Ollama call and parsing;
  - `links.py`: serial and WebSocket transports;
  - `runner.py`: sends commands with a stop of its own;
  - `__main__.py`: the CLI.
- **Plan 2 (separate):** an Android app (LiteRT + BLE) that consumes the same contract files.

**Tech Stack:** Python ≥3.10, `pyserial`, `websockets==17.3`, stdlib `unittest`; Ollama with `gemma4:e2b-it-qat`; MIT license.

---

## Context (verified 2026-10-23 unless marked)

### Event rules (from Kai)
- Every project uses a Gemma model with 100% on-device inference. A laptop counts as a demo device.
- Teams of 3–4. Tracks: Mobile AI, Physical AI, IoT & Robotics.
- First platforms: **Android phone (LiteRT)** and **laptop**. Robots: **Bittle X and Nybble Q**.

### Robot protocol (USB serial)
- 115200 8N1. Send `<command>\n`.
- When a command is done, the robot prints the command's first letter (`k`) on its own line. Example:
  - Sent: `kbalance`
  - Replies: `balance`, `k`
- `?` returns the model and firmware version. Bittle X replied: `G`, `Bittle X`, `B10_260527`, `?`.

### Gait arguments (firmware B10_260527, tested on Bittle X)
- **`kwkF 3` works.** The robot walks 3 cycles (about 1.3 s each) and then stands up (`up`) by itself. `k` is printed only after it stops, 4.3 s in total. `kbk N` is the same code path (`bk`→`bkF`, from reading the source).
- **Angle turns don't stop.** With `kwkL 90`, the yaw read `5363.72` (outside ±180), the turn never ended, and Kai had to power-cycle the robot.
- **No timed turns either.** With a gyro, a number after a turn is always read as degrees.
- **So turns go bare.** Send `kwkL`/`kwkR` with no number. A bare gait echoes `k` right away and loops until the next command. The computer times the turn, then sends `kbalance`.

### WebSocket (`src/webServer.h`, OpenCatEsp32 `main` @ `84dd6ef`)
- Endpoint: `ws://<ip>:81`.
- Request: `{"type":"command","taskId":str,"commands":[…],"timestamp":ms}`.
- Replies:
  - `{"type":"response","taskId":…,"status":"running"}`;
  - then `{"type":"response","taskId":…,"status":"completed","results":[text…]}`.
- Errors carry the **running** task's id, or no id at all.
- One task runs at a time. The server disconnects after 40 s with no heartbeat, and it pushes `event_us`/`event_cam` sensor events.
- **Unverified on hardware:** the exact `results` text, and whether the deferred echo for `kwkF N` also delays `completed`.

### Commands
- The same 8 core codes exist on Bittle X and Nybble Q (`skillNameWithType[]` in `InstinctBittleESP.h` / `InstinctNybbleESP.h`). `wkR` is mirrored from `wkL` at runtime.
- **Nybble Q is untested on hardware.**

### Gemma (Mac M1, `gemma4:e2b-it-qat`, `think:false`, temperature 0)
- Schema-constrained output scored 8/8 with plain codes and 10/10 with numbers, using a regex `pattern`.
- Plain chat with no constraints produces invented codes like `kwh` (Kai's screenshot). That's why the prompt, schema and allowlist are all needed.

### Process notes
- GBrain (MCP) was disconnected, and the Master Brain query failed (`CSRF token not found`). No prior decisions were consulted.
- `pyserial` and `websockets` install into a venv. Verified: `websockets` 17.3 on Python 3.15.

## Decisions (approved by Kai, 2026-10-23)

1. MIT license, repo `PetoiCamp/opencat-gemma`, robots Bittle X + Nybble Q, Android + laptop.
2. **Copyright line:** `Copyright (c) 2026 Petoi LLC`.
3. **`HANDOFF.md`, `gemma_test.py` and `test_parse.py` stay out of the repo** (`.gitignore`); `eval/` and `tests/` replace the scratch files.
4. **Plans in `docs/superpowers/plans/` will be public** in the repo.
5. **Step numbers:** `kwkF`/`kbk` accept 1–20 steps, defaulting to **3** when the request gives none. Every walk ends by itself.
6. **Turns:** always bare and timed by the computer, for **2.0 s** by default (`--turn-seconds`), then `kbalance`. Requests like "turn 90°" lose the angle until the firmware bug is fixed. The README says so.
7. **Safety stop:** on a timeout, an error or Ctrl+C, the runner sends `kbalance`. The timeout for walks is `5 + 2 × steps` seconds, and 10 s otherwise.
8. **Ship `--dry-run`,** so teams without a robot at hand can still develop with Gemma.
9. **Publishing to GitHub is a separate, explicit step** after this plan. It is not part of any task.
10. **⚠️ No git commits (Kai's override of the Spec Gate's commit rule):**
    - Task 0 runs `git init` and creates the `feat/starter-kit` branch, but makes **no commits**.
    - **Skip every "Commit" step** in Tasks 0–10, and don't `git add` anything either.
    - Kai will decide when to commit.
11. **Execution:** subagent-driven.

## File structure

| Path | Responsibility |
|---|---|
| `contract/bittle.json`, `contract/nybble.json` | Source of truth: robot name, codes (meaning + kind), prompt examples |
| `contract/<robot>.prompt.txt`, `contract/<robot>.schema.json` | Generated from the JSON and checked in, for non-Python teams |
| `contract/README.md` | How the prompt and schema are built; how to add a code |
| `opencat_gemma/contract.py` | `load(robot)` → `Contract` (prompt, schema, `validate`); `python -m opencat_gemma.contract` regenerates the files |
| `opencat_gemma/gemma.py` | `ask()` (Ollama), `parse()` (never trust model output) |
| `opencat_gemma/links.py` | `SerialLink`, `open_serial()`, `find_robot()`, `robot_from_reply()`, `WsLink` |
| `opencat_gemma/runner.py` | `plan()` makes every command finite; `run()` sends and stops on failure |
| `opencat_gemma/__main__.py` | CLI: `python -m opencat_gemma "walk forward then sit"` |
| `eval/cases.json`, `eval/run_eval.py` | Gemma accuracy and latency check against a running Ollama (replaces `gemma_test.py`) |
| `tests/` | Unit and round-trip tests (no Ollama or robot needed) |
| `docs/protocol.md` | Serial, WebSocket, gait arguments, known turn bug |
| `README.md`, `LICENSE`, `requirements.txt`, `.gitignore` | Repo basics |

**About the round-trip contract:** the real consumers are the robot firmware and Ollama, and neither can run in unit tests.
- Unit tests use fakes built from the observed robot output and the firmware source.
- The real round trips are **Task 8 (Ollama eval)** and **Task 9 (robot)**. Plan 1 is not done until both pass.

---

### Task 0: Repo init and plan commit

**Files:** Create `.gitignore`, `requirements.txt`

- [ ] **Step 1: Create the files**

`.gitignore`:
```
.venv/
__pycache__/
HANDOFF.md
gemma_test.py
test_parse.py
```

`requirements.txt`:
```
pyserial==3.5
websockets==17.3
```

- [ ] **Step 2: Init, with an empty root commit on main; branch; commit the plan first**

```bash
cd opencat-gemma   # your clone of this repo
git init -b main
git commit --allow-empty -m "chore: init repository

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git switch -c feat/starter-kit
git add docs/superpowers/plans/2026-10-23-robot-send.md
git commit -m "docs: plan 1 for opencat-gemma starter kit

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git add .gitignore requirements.txt
git commit -m "chore: gitignore and pinned requirements

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 3: Create the venv**

```bash
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
.venv/bin/python -c "import serial, websockets; print(serial.VERSION, websockets.__version__)"
```
Expected: `3.5 17.3`

---

### Task 1: Contract

**Files:**
- Create: `contract/bittle.json`, `contract/nybble.json`, `opencat_gemma/__init__.py`, `opencat_gemma/contract.py`
- Test: `tests/__init__.py`, `tests/test_contract.py`

- [ ] **Step 1: Create the contract data**

`contract/bittle.json`:
```json
{
  "robot": "Bittle X robot dog",
  "codes": {
    "kwkF": {"meaning": "walk forward", "kind": "steps"},
    "kbk": {"meaning": "walk backward", "kind": "steps"},
    "kwkL": {"meaning": "turn left", "kind": "timed"},
    "kwkR": {"meaning": "turn right", "kind": "timed"},
    "ksit": {"meaning": "sit", "kind": "once"},
    "krest": {"meaning": "lie down / rest", "kind": "once"},
    "kbalance": {"meaning": "stand up", "kind": "once"},
    "khi": {"meaning": "say hi / wave", "kind": "once"}
  },
  "examples": [
    ["walk forward then sit", ["kwkF", "ksit"]],
    ["take 3 steps back and wave", ["kbk 3", "khi"]],
    ["stand up and turn left", ["kbalance", "kwkL"]],
    ["fly to the moon", []]
  ]
}
```

`contract/nybble.json`: identical, except `"robot": "Nybble Q robot cat"`.

`opencat_gemma/__init__.py`: an empty file. `tests/__init__.py`: an empty file.

- [ ] **Step 2: Write the failing tests**

`tests/test_contract.py`:
```python
import json
import unittest

from opencat_gemma.contract import CONTRACT_DIR, ROBOTS, load


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.c = load("bittle")

    def test_accepts_codes_and_step_counts(self):
        self.assertEqual(self.c.validate(["kwkF", "kwkF 5", "kbk 20", "kwkL", "ksit", "khi"]), [])

    def test_rejects_unknown_codes_bad_counts_and_turn_angles(self):
        bad = ["kwh", "kwkF 0", "kwkF 21", "kwkF 05", "kwkL 90", "ksit 2", "kwkF  5", "", 5]
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run them to confirm they fail**

Run: `.venv/bin/python -m unittest -v tests.test_contract`
Expected: `ModuleNotFoundError: No module named 'opencat_gemma.contract'`

- [ ] **Step 4: Write the implementation**

`opencat_gemma/contract.py`:
```python
"""Robot command contract: allowed codes, the Gemma prompt, and a JSON schema, built from contract/<robot>.json.

Run `python -m opencat_gemma.contract` to regenerate contract/<robot>.prompt.txt and .schema.json
(checked in so teams on Android or other languages can use them without Python).
"""
import json
import re
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"
ROBOTS = ("bittle", "nybble")
MAX_STEPS = 20
STEPS_RE = "([1-9]|1[0-9]|20)"  # 1..MAX_STEPS, no leading zeros


class Contract:
    def __init__(self, data):
        self.robot = data["robot"]
        self.codes = data["codes"]
        self.examples = data["examples"]
        stepped = [c for c, v in self.codes.items() if v["kind"] == "steps"]
        plain = [c for c, v in self.codes.items() if v["kind"] != "steps"]
        self.pattern = f"^(({'|'.join(stepped)})( {STEPS_RE})?|{'|'.join(plain)})$"
        self.schema = {"type": "array", "items": {"type": "string", "pattern": self.pattern}}
        self.prompt = "\n".join([
            f"You control a Petoi {self.robot}. Translate my request into a JSON array of command strings, in order. "
            "Use ONLY these codes:",
            *(f"{c}: {v['meaning']}" for c, v in self.codes.items()),
            f"{', '.join(stepped)} may be followed by a space and a number of steps from 1 to {MAX_STEPS}, "
            f'e.g. "{stepped[0]} 5". Leave the number out if the request gives none.',
            "If nothing matches, return []. Reply with JSON only, no explanation.",
            "",
            "Examples:",
            *(f"{json.dumps(req)} -> {json.dumps(cmds, separators=(',', ':'))}" for req, cmds in self.examples),
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
```

- [ ] **Step 5: Generate the files, then run the tests to confirm they pass**

```bash
.venv/bin/python -m opencat_gemma.contract
.venv/bin/python -m unittest -v tests.test_contract
```
Expected: two `wrote …` lines; then `Ran 5 tests … OK`.

- [ ] **Step 6: Commit**

```bash
git add contract opencat_gemma tests
git commit -m "feat: robot command contract with generated prompt and schema

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Gemma call and parsing

**Files:**
- Create: `opencat_gemma/gemma.py`
- Test: `tests/test_gemma.py`

- [ ] **Step 1: Write the failing tests** (these port the 7 cases from `test_parse.py`, plus step counts)

`tests/test_gemma.py`:
```python
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
        self.assertEqual(parse(C, '["kwkF","kwh"]'), (None, "not allowed: ['kwh']"))

    def test_non_string_element_rejected_not_crash(self):
        self.assertEqual(parse(C, '[{"cmd":"ksit"}]'), (None, "not allowed: [{'cmd': 'ksit'}]"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/python -m unittest -v tests.test_gemma`
Expected: `ModuleNotFoundError: No module named 'opencat_gemma.gemma'`

- [ ] **Step 3: Write the implementation**

`opencat_gemma/gemma.py`:
```python
"""Ask a local Gemma (through Ollama) to turn a request into robot commands."""
import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:e2b-it-qat"


def ask(contract, text, model=MODEL, url=OLLAMA_URL, timeout=180):
    """Return Gemma's raw reply. think=False matters: with thinking on, replies took 6-20 s instead of ~1 s."""
    body = json.dumps({
        "model": model, "stream": False, "think": False, "format": contract.schema,
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": contract.prompt}, {"role": "user", "content": text}],
    }).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["message"]["content"].strip()


def parse(contract, out):
    """Return (commands, error). Never trust model output: other runtimes may not enforce the schema."""
    try:
        v = json.loads(out)
    except json.JSONDecodeError:
        return None, "invalid JSON"
    if isinstance(v, dict):
        v = next((x for x in v.values() if isinstance(x, list)), None)
    if not isinstance(v, list):
        return None, "not a list"
    bad = contract.validate(v)
    if bad:
        return None, f"not allowed: {bad}"
    return v, None
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/python -m unittest -v tests.test_gemma`
Expected: `Ran 8 tests … OK`

- [ ] **Step 5: Commit**

```bash
git add opencat_gemma/gemma.py tests/test_gemma.py
git commit -m "feat: Ollama call and defensive parsing of Gemma output

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Runner, with a stop on the computer's side

**Files:**
- Create: `opencat_gemma/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_runner.py`:
```python
import unittest

from opencat_gemma.contract import load
from opencat_gemma.runner import DEFAULT_STEPS, STOP, plan, run

C = load("bittle")


class FakeLink:
    def __init__(self, fail_on=None, interrupt_on=None):
        self.sent, self.fail_on, self.interrupt_on = [], fail_on, interrupt_on

    def send(self, command, timeout):
        self.sent.append((command, timeout))
        if command == self.fail_on:
            raise TimeoutError(command)
        if command == self.interrupt_on:
            raise KeyboardInterrupt
        return "ok | k"


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

    def test_empty_sends_nothing(self):
        link = FakeLink()
        self.assertEqual(self.go(link, []), [])
        self.assertEqual(link.sent, [])

    def test_disallowed_sends_nothing(self):
        link = FakeLink()
        with self.assertRaises(ValueError):
            self.go(link, ["kwh"])
        self.assertEqual(link.sent, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/python -m unittest -v tests.test_runner`
Expected: `ModuleNotFoundError: No module named 'opencat_gemma.runner'`

- [ ] **Step 3: Write the implementation**

`opencat_gemma/runner.py`:
```python
"""Send validated commands one at a time. The computer always keeps its own stop: never rely only on the robot."""
import time

STOP = "kbalance"
DEFAULT_STEPS = 3
TURN_SECONDS = 2.0


def plan(contract, commands):
    """Make every command finite. Returns [(command, timeout_s, timed_by_us)].

    - "steps" codes always carry a count; the robot walks that many cycles, stands up, then echoes "k".
      Measured ~1.3 s per cycle on Bittle X, so the timeout is 5 + 2 * steps.
    - "timed" codes (turns) are sent bare: angle turns (`kwkL 90`) never stopped on firmware B10_260527,
      so we time them and send STOP ourselves.
    """
    bad = contract.validate(commands)
    if bad:
        raise ValueError(f"not allowed: {bad}")
    out = []
    for command in commands:
        name, _, steps = command.partition(" ")
        kind = contract.codes[name]["kind"]
        if kind == "steps":
            steps = int(steps or DEFAULT_STEPS)
            out.append((f"{name} {steps}", 5 + 2 * steps, False))
        else:
            out.append((command, 10, kind == "timed"))
    return out


def run(contract, commands, link, turn_seconds=TURN_SECONDS, sleep=time.sleep, log=print):
    """Send each command and wait for the robot. On any error or Ctrl+C, send STOP, then re-raise."""
    steps = plan(contract, commands)  # raises ValueError before anything is sent
    replies = []
    try:
        for command, timeout, timed in steps:
            replies.append(link.send(command, timeout))
            log(f"  sent {command:10} robot: {replies[-1]}")
            if timed:
                sleep(turn_seconds)
                replies.append(link.send(STOP, 10))
                log(f"  sent {STOP:10} robot: {replies[-1]}")
    except BaseException:
        log("  stopping robot")
        try:
            link.send(STOP, 10)
        except Exception:
            pass
        raise
    return replies
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/python -m unittest -v tests.test_runner`
Expected: `Ran 9 tests … OK`

- [ ] **Step 5: Commit**

```bash
git add opencat_gemma/runner.py tests/test_runner.py
git commit -m "feat: runner makes every command finite and always keeps its own stop

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Serial link and robot detection

**Files:**
- Create: `opencat_gemma/links.py`
- Test: `tests/test_links.py`

`SerialLink` takes an already-open, serial-like object, so its tests run on any OS without hardware. The real port is exercised in Task 9.

- [ ] **Step 1: Write the failing tests**

`tests/test_links.py`:
```python
import unittest

from opencat_gemma.links import SerialLink, robot_from_reply


class FakeSerial:
    """Replies like Bittle X did on 2026-10-23 once a full line arrives."""

    def __init__(self, replies):
        self.replies, self.written, self.pending = replies, b"", b""

    def write(self, data):
        self.written += data
        if data.endswith(b"\n"):
            self.pending += self.replies.get(data.strip().decode(), b"")

    def read(self, size):
        out, self.pending = self.pending[:size], self.pending[size:]
        return out

    def close(self):
        pass


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


class RobotFromReplyTest(unittest.TestCase):
    def test_known_models(self):
        self.assertEqual(robot_from_reply("G | Bittle X | B10_260527 | ?"), "bittle")
        self.assertEqual(robot_from_reply("Nybble Q | N10_260820 | ?"), "nybble")

    def test_unknown(self):
        self.assertIsNone(robot_from_reply("hello | ?"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/python -m unittest -v tests.test_links`
Expected: `ModuleNotFoundError: No module named 'opencat_gemma.links'`

- [ ] **Step 3: Write the implementation**

`opencat_gemma/links.py`:
```python
"""Transports to the robot. Every link has send(command, timeout) -> reply text, and close()."""
import time

import serial
from serial.tools import list_ports

BAUD = 115200
MODELS = {"Bittle": "bittle", "Nybble": "nybble"}


def open_serial(port):
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = port, BAUD, 0.05
    ser.dtr = ser.rts = False  # avoid pulsing the ESP32 reset line on open (unverified on Windows/Linux)
    ser.open()
    time.sleep(0.5)
    ser.reset_input_buffer()
    return ser


class SerialLink:
    """The robot prints the command's first letter (e.g. "k") on its own line when the command is done."""

    def __init__(self, ser):
        self.ser = ser

    def send(self, command, timeout=10):
        self.ser.write((command + "\n").encode())
        buf, end = "", time.time() + timeout
        while time.time() < end:
            buf += self.ser.read(4096).decode("ISO-8859-1")
            lines = [l.strip() for l in buf.split("\n")[:-1]]  # complete lines only
            if command[0].lower() in (l.lower() for l in lines):
                return " | ".join(l for l in lines if l)
            time.sleep(0.01)
        raise TimeoutError(f"no {command[0]!r} echo for {command!r} within {timeout}s, got {buf!r}")

    def close(self):
        self.ser.close()


def robot_from_reply(reply):
    """Map the reply to '?' (e.g. "G | Bittle X | B10_260527 | ?") to a contract name, or None."""
    return next((robot for name, robot in MODELS.items() if name in reply), None)


def find_robot():
    """Probe USB serial ports with '?'. Returns (SerialLink, robot) for the first Petoi robot found."""
    for p in list_ports.comports():
        if p.vid is None:  # skips Bluetooth and debug ports, which can hang on open
            continue
        try:
            link = SerialLink(open_serial(p.device))
        except serial.SerialException:
            continue
        try:
            robot = robot_from_reply(link.send("?", timeout=3))
        except TimeoutError:
            robot = None
        if robot:
            print(f"Found {robot} on {p.device}")
            return link, robot
        link.close()
    raise RuntimeError("No Petoi robot found on USB. Check the cable, power, and that no other app has the port open.")
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/python -m unittest -v tests.test_links`
Expected: `Ran 5 tests … OK`

- [ ] **Step 5: Commit**

```bash
git add opencat_gemma/links.py tests/test_links.py
git commit -m "feat: serial link with token-echo wait and USB robot detection

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: WebSocket link, with a mock-firmware round trip

**Files:**
- Modify: `opencat_gemma/links.py` (add `import json`, a `websockets` import, and the `WsLink` class at the end)
- Modify: `tests/test_links.py` (imports; add classes before `if __name__`)

- [ ] **Step 1: Write the failing tests**

Change the imports at the top of `tests/test_links.py` to:
```python
import json
import threading
import unittest

from websockets.sync.server import serve

from opencat_gemma.links import SerialLink, WsLink, robot_from_reply
```

Add before `if __name__ == "__main__":`:
```python
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
            ws.send(json.dumps(self.reply(msg)))

    def close(self):
        self.server.shutdown()


class WsLinkTest(unittest.TestCase):
    def send(self, fw, command):
        link = WsLink(fw.url)
        try:
            return link.send(command, timeout=2)
        finally:
            link.close()
            fw.close()

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

    def test_untagged_error_raises(self):
        fw = MockFirmware(reply=lambda m: {"type": "error", "error": "Heartbeat timeout"})
        with self.assertRaisesRegex(RuntimeError, "Heartbeat timeout"):
            self.send(fw, "ksit")
```

- [ ] **Step 2: Run them to confirm they fail**

Run: `.venv/bin/python -m unittest -v tests.test_links`
Expected: `ImportError: cannot import name 'WsLink'`

- [ ] **Step 3: Write the implementation**

Change the imports at the top of `opencat_gemma/links.py` to:
```python
import json
import time

import serial
from serial.tools import list_ports
from websockets.sync.client import connect
```

Append to `opencat_gemma/links.py`:
```python
class WsLink:
    """Firmware WebSocket server (src/webServer.h, port 81). One command per task, so turns can be timed between tasks.

    The firmware runs a multi-command task back to back: the next command starts as soon as the previous one
    replies, so a gait in the middle of a group would be cut off immediately.
    """

    def __init__(self, url):
        self.ws = connect(url, open_timeout=5)

    def send(self, command, timeout=10):
        task_id = str(time.time_ns())
        self.ws.send(json.dumps({"type": "command", "taskId": task_id, "commands": [command],
                                 "timestamp": int(time.time() * 1000)}))
        end = time.time() + timeout
        while True:
            msg = json.loads(self.ws.recv(timeout=max(0, end - time.time())))
            # Errors may carry another task's id ("still running") or none ("Heartbeat timeout").
            if msg.get("type") == "error" or msg.get("status") == "error":
                raise RuntimeError(msg.get("error", "task failed"))
            if msg.get("taskId") == task_id and msg.get("status") == "completed":
                lines = [l.strip() for r in msg.get("results", []) for l in r.split("\n")]
                return " | ".join(l for l in lines if l)

    def close(self):
        self.ws.close()
```

- [ ] **Step 4: Run the tests to confirm they pass**

Run: `.venv/bin/python -m unittest -v tests.test_links`
Expected: `Ran 8 tests … OK`

- [ ] **Step 5: Commit**

```bash
git add opencat_gemma/links.py tests/test_links.py
git commit -m "feat: WebSocket link, one command per firmware task

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: CLI

**Files:**
- Create: `opencat_gemma/__main__.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** (dry run with Gemma faked, so no Ollama or robot is needed)

`tests/test_cli.py`:
```python
import io
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

    def test_rejected_output_exits_nonzero(self):
        with mock.patch.object(cli, "ask", return_value="UART: kwh"), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as e:
                cli.main(["--dry-run", "sit"])
        self.assertIn("invalid JSON", str(e.exception.code))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `.venv/bin/python -m unittest -v tests.test_cli`
Expected: `ImportError` (no `opencat_gemma.__main__`).

- [ ] **Step 3: Write the implementation**

`opencat_gemma/__main__.py`:
```python
"""python -m opencat_gemma "walk forward then sit"  — request -> Gemma -> allowlist -> robot."""
import argparse
import sys
import time

from .contract import ROBOTS, load
from .gemma import MODEL, ask, parse
from .links import SerialLink, WsLink, find_robot, open_serial
from .runner import STOP, TURN_SECONDS, plan, run


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m opencat_gemma", description=__doc__)
    p.add_argument("request")
    p.add_argument("--robot", choices=ROBOTS, help="default: detected over USB; bittle for --ws/--dry-run")
    p.add_argument("--port", help="USB serial device (default: auto-detect)")
    p.add_argument("--ws", metavar="URL", help="use WebSocket, e.g. ws://192.168.1.50:81")
    p.add_argument("--model", default=MODEL, help="Ollama model (default: %(default)s)")
    p.add_argument("--turn-seconds", type=float, default=TURN_SECONDS, help="how long turns run (default: %(default)s)")
    p.add_argument("--dry-run", action="store_true", help="show what would be sent; don't touch the robot")
    args = p.parse_args(argv)

    link = None
    if args.dry_run or args.ws or args.port:
        robot = args.robot or "bittle"
    else:
        link, robot = find_robot()
    contract = load(robot)

    t = time.time()
    out = ask(contract, args.request, model=args.model)
    commands, err = parse(contract, out)
    print(f"Gemma ({time.time() - t:.1f}s): {args.request!r} -> {out}")
    if err:
        if link:
            link.close()
        sys.exit(f"Rejected: {err}")

    if args.dry_run:
        shown = [c + (f" (then {STOP} after {args.turn_seconds}s)" if timed else "") for c, _, timed in plan(contract, commands)]
        print("would send: " + (", ".join(shown) or "nothing"))
        return

    link = link or (WsLink(args.ws) if args.ws else SerialLink(open_serial(args.port)))
    try:
        run(contract, commands, link, turn_seconds=args.turn_seconds)
    finally:
        link.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run all the tests**

Run: `.venv/bin/python -m unittest discover -v tests`
Expected: `Ran 32 tests … OK` (contract 5 + gemma 8 + runner 9 + links 8 + cli 2).

- [ ] **Step 5: Commit**

```bash
git add opencat_gemma/__main__.py tests/test_cli.py
git commit -m "feat: CLI with USB auto-detect, WebSocket and dry-run

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 6b: Interactive chat mode (approved by Kai, 2026-10-23)

Run `python -m opencat_gemma` with no request to get a `Bittle>` prompt.
- The port opens **once** and stays open, so there's no repeated detection and no reboot risk between lines.
- **Ctrl+C during a move** sends STOP (via `run()`) and returns to the prompt.
- **Ctrl+C or Ctrl+D at the prompt** quits.
- **A rejected or failed request** prints a message, and the loop continues.
- **Single-shot mode** is unchanged: it still exits non-zero when a request is rejected.

**Files:** Modify `opencat_gemma/__main__.py` and `tests/test_cli.py`.

- [ ] **Step 1: Write the failing tests.** Add to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Confirm they fail.** Run `.venv/bin/python -m unittest -v tests.test_cli`. They fail because `request` is still required.

- [ ] **Step 3: Implement.** Restructure `main()` in `opencat_gemma/__main__.py` as follows. Keep the existing argument flags, and keep `--dry-run` working in both modes.

```python
def handle(contract, text, link, args):
    """One request: Gemma -> check -> robot (or just print, with --dry-run). Returns an error message, or None."""
    t = time.time()
    out = ask(contract, text, model=args.model)
    commands, err = parse(contract, out)
    print(f"Gemma ({time.time() - t:.1f}s): {text!r} -> {out}")
    if err:
        return f"Rejected: {err}"
    if args.dry_run:
        shown = [c + (f" (then {STOP} after {args.turn_seconds}s)" if timed else "") for c, _, timed in plan(contract, commands)]
        print("would send: " + (", ".join(shown) or "nothing"))
        return None
    run(contract, commands, link, turn_seconds=args.turn_seconds)
    return None


def chat(contract, robot, link, args):
    print(f"Chatting with {robot}. Ctrl+C stops a move; Ctrl+D (or Ctrl+C here) quits.")
    while True:
        try:
            text = input(f"{robot.capitalize()}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        try:
            err = handle(contract, text, link, args)
        except KeyboardInterrupt:
            err = "interrupted (robot told to stop)"
        except (TimeoutError, RuntimeError, OSError) as e:
            err = f"error: {e}"
        if err:
            print(f"  {err}")
```

In `main()`:
- make `request` optional: `p.add_argument("request", nargs="?", help="omit to chat interactively")`;
- open the link up front, unless `--dry-run`: use `find_robot()`, or `WsLink`/`SerialLink(open_serial(...))` as before;
- then wrap everything in `try: … finally: if link: link.close()`.

Inside the `try`:
- **With a request:** `err = handle(...)`, then `if err: sys.exit(err)`.
- **Without one:** `chat(...)`.

- [ ] **Step 4: Run all the tests.** Run `.venv/bin/python -m unittest discover -v tests`. The 2 existing CLI tests must still pass, plus the 3 new ones.

---

### Task 7: Docs and license

**Files:** Create `README.md`, `LICENSE`, `docs/protocol.md`, `contract/README.md`

- [ ] **Step 1: `LICENSE`**: the standard MIT text, with the line `Copyright (c) 2026 Petoi LLC` (decision 2).

- [ ] **Step 2: `docs/protocol.md`**, with these sections, all filled from the Context section above:
  1. **Serial:** baud rate, line format, token echo (with the real `kbalance` and `?` transcripts), and the `?` reply format.
  2. **Gait arguments:**
     - the `kwkF 3` transcript with timings;
     - values under 200 are cycles, 200 or more are milliseconds;
     - the `kwkL 90` failure transcript;
     - why turns are timed by the computer.
  3. **WebSocket:**
     - request and response JSON, with an example of each;
     - one task at a time; the 40 s heartbeat; sensor events;
     - why the starter sends one command per task;
     - **Unverified on hardware:** the `results` text.
  4. **Robot Wi-Fi:** `w%SSID%password` over serial, and the IP line it prints. Tell readers never to commit Wi-Fi passwords.

- [ ] **Step 3: `contract/README.md`:**
  - what each field means, and the meaning of `kind` (`steps` / `timed` / `once`);
  - how the prompt and schema are generated, and the regex;
  - "edit the JSON, then run `python -m opencat_gemma.contract`; the tests fail if you forget";
  - "on Android, load `bittle.prompt.txt` as the system prompt, use `bittle.schema.json` to constrain output if your runtime supports it, and **always** validate against the same regex before sending".

- [ ] **Step 4: `README.md`**, in this order:
  1. **One-line pitch:** "Talk to a Petoi robot with Gemma running 100% on-device."
  2. **How it works:**
     ```
     request → Gemma (local) → JSON commands → allowlist check → robot (USB / Wi-Fi)
     ```
     Include the "why" in three bullets: plain chat invents commands (the `UART: kwh` example), so we use a prompt with meanings, a schema-constrained output, and an allowlist check.
  3. **Quickstart (laptop):**
     - install Ollama, `ollama pull gemma4:e2b-it-qat`;
     - `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`;
     - `.venv/bin/python -m opencat_gemma --dry-run "walk forward then sit"`;
     - plug in the robot and close the Petoi Desktop App;
     - `.venv/bin/python -m opencat_gemma "walk forward then sit"`.
  4. **Commands table:** generated from `contract/bittle.json`, plus a note that Nybble is the same set.
  5. **Safety:**
     - walks always carry a step count;
     - turns are timed by the computer;
     - timeout or Ctrl+C sends `kbalance`;
     - keep a hand near the power switch;
     - known bug: angle turns never stop (link to `docs/protocol.md`).
  6. **Build your own:** use `contract/` from any language, the eval, the tests, and an Android guide marked "coming".
  7. **License: MIT.**

- [ ] **Step 5: Check that every command in the README actually runs**

```bash
.venv/bin/python -m opencat_gemma --help
.venv/bin/python -m opencat_gemma.contract
git diff --exit-code contract   # generated files unchanged
```

- [ ] **Step 6: Commit**

```bash
git add README.md LICENSE docs/protocol.md contract/README.md
git commit -m "docs: README quickstart, protocol reference, contract guide, MIT license

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Gemma eval (real consumer #1: Ollama)

**Files:** Create `eval/cases.json`, `eval/run_eval.py`

- [ ] **Step 1: Create `eval/cases.json`.** Each case is a request plus a list of acceptable answers:

```json
[
  ["walk forward then sit", [["kwkF", "ksit"]]],
  ["stand up then sit", [["kbalance", "ksit"]]],
  ["say hello to everyone", [["khi"]]],
  ["go back a bit and lie down", [["kbk", "krest"]]],
  ["go back 2 steps and lie down", [["kbk 2", "krest"]]],
  ["stand up, turn left, then wave", [["kbalance", "kwkL", "khi"]]],
  ["stand up and walk forward for 5 steps, then turn left for 30 degrees", [["kbalance", "kwkF 5", "kwkL"]]],
  ["walk forward, turn right, walk forward, then sit", [["kwkF", "kwkR", "kwkF", "ksit"]]],
  ["turn around", [["kwkL"], ["kwkR"]]],
  ["sit down", [["ksit"]]],
  ["take a nap", [["krest"]]],
  ["do a backflip", [[]]]
]
```

- [ ] **Step 2: Create `eval/run_eval.py`**

```python
"""Accuracy and latency of Gemma on eval/cases.json. Needs Ollama running. Exit 0 if every case passes."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from opencat_gemma.contract import ROBOTS, load  # noqa: E402
from opencat_gemma.gemma import MODEL, ask, parse  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--robot", choices=ROBOTS, default="bittle")
p.add_argument("--model", default=MODEL)
args = p.parse_args()
contract = load(args.robot)
cases = json.loads((Path(__file__).parent / "cases.json").read_text())

passed, times = 0, []
for text, acceptable in cases:
    t = time.time()
    out = ask(contract, text, model=args.model)
    times.append(time.time() - t)
    commands, err = parse(contract, out)
    ok = err is None and commands in acceptable
    passed += ok
    print(f"{times[-1]:5.1f}s | {'PASS' if ok else 'FAIL'} | {text!r:72} -> {out}" + ("" if ok else f"  (want {acceptable})"))
print(f"\n{passed}/{len(cases)} passed | latency avg {sum(times) / len(times):.1f}s, max {max(times):.1f}s")
sys.exit(0 if passed == len(cases) else 1)
```

- [ ] **Step 3: Run it on both contracts**

```bash
.venv/bin/python eval/run_eval.py --robot bittle
.venv/bin/python eval/run_eval.py --robot nybble
```
**Bar:** 12/12 on each, and warm latency under 3 s per case. The first case may take about 9 s while the model loads.

If a case fails, change **only** `examples` in `contract/<robot>.json`, then regenerate (`python -m opencat_gemma.contract`) and re-run. Record every prompt change and its effect in the commit message. If 12/12 can't be reached after 3 example changes, stop and report the failing cases to Kai rather than loosening `cases.json`.

- [ ] **Step 4: Commit**

```bash
git add eval contract
git commit -m "test: Gemma eval cases and runner (bittle N/12, nybble N/12)

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
(Replace N with the actual results.)

---

### Task 9: Robot round trip (real consumer #2), with Kai present

Bittle X on a flat surface, USB connected, about 50 cm clear, with a hand near the power switch. Close the Petoi Desktop App and Arduino Serial Monitor first. Kai confirms what the robot physically does at each step.

- [ ] **Step 1: Detection, and check that opening the port doesn't reboot the robot**

Run: `.venv/bin/python -m opencat_gemma "stand up"`
Expected: `Found bittle on /dev/cu.…`, then `sent kbalance … robot: balance | k`. The robot must **not** print boot lines (`rst:` / `* Start *`). If it does, leaving DTR/RTS at pyserial's defaults isn't preventing a reset on this OS (clearing them caused one, found 2026-10-23): record that and report it.

- [ ] **Step 2: A walk with steps ends by itself**

Run: `.venv/bin/python -m opencat_gemma "walk forward 3 steps then sit"`
Expected: `sent kwkF 3 … | up | k` after about 4–5 s, then `sent ksit`. Robot: 3 cycles, stands up, sits.

- [ ] **Step 3: A turn is timed by the computer**

Run: `.venv/bin/python -m opencat_gemma "turn left"`
Expected: `sent kwkL`, a pause of about 2 s, then `sent kbalance`. Robot: turns about 2 s, then stands. Tune with `--turn-seconds` if needed, and record the chosen value.

- [ ] **Step 4: Ctrl+C stops the robot**

Run: `.venv/bin/python -m opencat_gemma "walk forward 20 steps"` and press Ctrl+C after about 3 s.
Expected: `stopping robot`, and the robot stops walking within about 1 s.

- [ ] **Step 5: A refusal sends nothing**

Run: `.venv/bin/python -m opencat_gemma "do a backflip"`
Expected: `-> []`, no `sent` lines, and no movement.

- [ ] **Step 6 (optional): WebSocket.** Kai (not Claude) sends `w%SSID%password` over serial and reads the IP. Then:

Run: `.venv/bin/python -m opencat_gemma --ws ws://<IP>:81 "walk forward 3 steps then sit"`
- Record the actual `results` text, and whether `completed` waits for the 3 cycles to finish.
- If either differs from `MockFirmware`, update the mock and `docs/protocol.md`, then re-run the tests.

- [ ] **Step 7: Nybble Q, if one is available.** Repeat Steps 1–5. If no Nybble is available, mark Nybble as "untested on hardware" in the README.

- [ ] **Step 8: Record the results** in `docs/protocol.md` (a "Hardware verification" section with the date, firmware version and what Kai saw), and commit:

```bash
git add docs/protocol.md opencat_gemma tests
git commit -m "docs: hardware verification results for Bittle X

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 10: Finish

- [ ] **Step 1:** Run `.venv/bin/python -m unittest discover -v tests`. Expected: all tests OK.
- [ ] **Step 2:** Merge `feat/starter-kit` into `main` locally (superpowers:finishing-a-development-branch).
- [ ] **Step 3:** **Don't push.** Creating `PetoiCamp/opencat-gemma` on GitHub and publishing is outward-facing. Ask Kai first, and review the plans folder and `git log` for anything internal.

## Plan 2 (separate, after this one): Android app
Gemma on a Pixel through LiteRT, loading `contract/<robot>.prompt.txt`, validating with the same regex, and sending over BLE (`src/bleUart.h`) or WebSocket. It needs research first: the LiteRT-LM API, and the Petoi BLE UUIDs and framing.
