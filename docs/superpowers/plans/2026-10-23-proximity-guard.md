# Proximity Guard Implementation Plan (Plan 1b)

> **⏸ PAUSED (2026-10-23, Kai's decision).** Task 1 is done (`XD` is required). Tasks 2–7 are not implemented, and their unfinished tests were removed. Reasons:
> - The guard only checks **before** a walk, not during it.
> - Each check costs about 3–4 s and makes the robot sit (`XD` forces a sit).
> - Distances are rough.
> - The firmware's own `XD` walking mode already avoids obstacles continuously.
>
> A smaller alternative, if the sensor is wanted later: a `read_distance()` / `distance?` example (`XD` → median reads → `Xd`), plus documenting the firmware's obstacle-avoidance mode.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Use the Petoi double IR distance sensor so that Gemma's forward walks are skipped when something is close in front of the robot. Add a `distance?` command in chat mode.

**Architecture:**
- `SerialLink` gains `read_analog(pin)`, which sends the firmware's binary pin read: `R` `a` `<pin>` `~` → `=` / value / `R`.
- A new `opencat_gemma/proximity.py` turns reads into "nearest raw value". It takes the median of 10 reads per pin and keeps the smaller (closer) of the two. Its guard function blocks forward walks.
- `runner.run()` gets an optional `guard(command) -> reason | None`. When a reason is returned, that one command is skipped and logged, and the rest still run.
- The CLI adds `--guard`, plus `distance?` in chat. Serial only; WebSocket reads are out of scope.

**Tech Stack:** As Plan 1: Python, pyserial, unittest.

---

## Context (measured 2026-10-23, Bittle X, firmware B10_260527, USB, macOS)

- **Pins:** the sensor is on pins 34 and 35 (`ANALOG1`/`ANALOG2`, BiBoard V1.0 `RevDE`).
- **Pin-read reply:** `R` `a` `<pin>` `~` returns `=\r\n<value>\r\nR\r\n`.
- **Module on (`XD`), tennis ball held still,** median of about 38 reads per step:

  | Ball | none | 30 cm | 20 cm | 10 cm | 5 cm |
  |---|---|---|---|---|---|
  | Median raw (34 / 35) | 4095 / 4095 | ~3900 / ~3890 | 2450 / 3000 | 704 / 780 | 51 / 48 |

- **Single reads are noisy** (at 10 cm: 14–3312), but the medians are stable.
- **Module off (`Xd`):** the readings flipped between ~1000 and ~50 with no relation to the object. Whether `XD` is required is **not settled**, so Task 1 decides it.
- **`XD` side effects:** the robot sits (`loadBySkillName("sit")`) and head-tracks. While walking, the firmware's IR mode steers by itself. So the guard must **not** leave the module on during our walks.
- **`XD`/`Xd` replies:** each ends with a line `X`. `SerialLink.send` already treats that as the echo, case-insensitively.
- **`fit()`** (firmware formula) overestimates mid-range distances (10 cm → ~18 cm). Distances shown to users are labelled "rough".

## Decisions (proposed, for Kai to approve)

1. **Threshold:** a median raw value below **1000** counts as "close" (roughly 10–15 cm). Flag `--guard-threshold` to tune it.
2. **What's guarded:** walk codes ending in `F`, except `kvtF` (stepping in place). Backward walks, turns and behaviours aren't guarded.
3. **When blocked:** skip that walk, print `skipped kwkF 3: obstacle ahead (…)`, and continue with the remaining commands. Nothing is moving at that point, so no STOP is needed.
4. **Opt-in:** `--guard` is off by default, since the sensor is an accessory. `distance?` works whenever there is a serial link.
5. **Module handling:** decided in Task 1.
   - If reads need `XD`: each check does `XD` → wait 2 s → 10 reads per pin → `Xd`. That costs ~3–4 s, and the robot sits.
   - Otherwise: reads only, about 0.5 s.
6. **No commits** (same as Plan 1, until Kai says so).

---

### Task 1: Spike: is `XD` required, and how long does a check take? (Kai present)

> **DONE, 2026-10-23: `XD` is required, so `NEEDS_MODULE = True`.**
> - With the module off, the guided test read 4095 at 10 cm (the same as "nothing") and baselines drifted (3005 vs 4095).
> - With the module on, readings step down cleanly with distance.
> - Data is in `TODO.md` under question 1.1.

**Files:** none. This task uses `ir_probe.py`.

- [ ] **Step 1:** Kai runs `.venv/bin/python ir_probe.py --guided`, edited so it does **not** send `XD`. Remove the `module(True)` / `module(False)` calls in `guided()` for this run only, and restore them after.
  - **If the medians step down with distance** like the table above, `XD` is **not** needed. Set `NEEDS_MODULE = False` in Task 3.
  - **Otherwise** set `NEEDS_MODULE = True`.
- [ ] **Step 2:** Record the result and the date in `TODO.md` under question 1.1 for the firmware author.

---

### Task 2: `SerialLink.read_analog`

**Files:** Modify `opencat_gemma/links.py` and `tests/test_links.py`.

- [ ] **Step 1: Failing tests.** In `tests/test_links.py`:
  - change `FakeSerial.write` to trigger a reply when data ends with `b"\n"` **or** `b"~"`. Replace `if data.endswith(b"\n"):` with `if data.endswith((b"\n", b"~")):`.
  - add these tests to `SerialLinkTest`:

```python
    def test_read_analog_sends_binary_read_and_parses_value(self):
        ser = FakeSerial({'Ra"~': b"=\r\n704\r\nR\r\n"})
        self.assertEqual(SerialLink(ser).read_analog(34, timeout=1), 704)
        self.assertEqual(ser.written, bytes([82, 97, 34, 126]))

    def test_read_analog_without_echo_times_out(self):
        ser = FakeSerial({'Ra#~': b"=\r\n704\r\n"})
        with self.assertRaises(TimeoutError):
            SerialLink(ser).read_analog(35, timeout=0.2)
```

- [ ] **Step 2:** Run `.venv/bin/python -m unittest tests.test_links`. Expect an `AttributeError` for `read_analog`.

- [ ] **Step 3: Implement.** In `SerialLink`, move the read loop into a helper, keep `send()`'s behaviour and messages, and add `read_analog`:

```python
    def send(self, command, timeout=10):
        self.ser.write((command + "\n").encode())
        return " | ".join(self._lines_until(command[0], timeout, command))

    def read_analog(self, pin, timeout=2):
        """Raw ADC value (0-4095) via the firmware's binary pin read: 'R' 'a' <pin> '~' -> "=", value, "R"."""
        self.ser.write(bytes([ord("R"), ord("a"), pin, ord("~")]))
        lines = self._lines_until("R", timeout, f"read pin {pin}")
        return int(lines[lines.index("=") + 1])

    def _lines_until(self, token, timeout, what):
        """Read complete lines until one equals token (case-insensitive). Returns the non-empty lines."""
        buf, end = "", time.monotonic() + timeout
        while time.monotonic() < end:
            buf += self.ser.read(4096).decode("ISO-8859-1")
            lines = [l.strip() for l in buf.split("\n")[:-1]]  # complete lines only
            if token.lower() in (l.lower() for l in lines):
                return [l for l in lines if l]
            time.sleep(0.01)
        raise TimeoutError(f"no {token!r} echo for {what!r} within {timeout}s, got {buf!r}")
```

- [ ] **Step 4:** Run `.venv/bin/python -m unittest discover tests`. All tests pass: the existing ones plus 2 new.

---

### Task 3: `proximity.py`

**Files:** Create `opencat_gemma/proximity.py` and `tests/test_proximity.py`.

- [ ] **Step 1: Failing tests.** `tests/test_proximity.py`:

```python
import unittest

from opencat_gemma import proximity
from opencat_gemma.proximity import approx_cm, is_forward, make_guard, nearest_raw


class FakeLink:
    def __init__(self, values):  # values: {pin: [raw, ...]} consumed in order
        self.values, self.sent = {p: list(v) for p, v in values.items()}, []

    def read_analog(self, pin, timeout=2):
        self.sent.append(f"read{pin}")
        return self.values[pin].pop(0)

    def send(self, command, timeout=10):
        self.sent.append(command)
        return "X"


def link(a, b, n=proximity.READS):
    return FakeLink({34: [a] * n, 35: [b] * n})


class ProximityTest(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self.patch = unittest.mock.patch.object(proximity.time, "sleep", self.sleeps.append)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_median_per_pin_then_the_closer_one(self):
        noisy = FakeLink({34: [4095, 700, 704, 3312, 704, 14, 704, 710, 704, 700],
                          35: [3000] * proximity.READS})
        self.assertEqual(nearest_raw(noisy, module=False), 704)

    def test_module_on_wraps_reads_with_XD_and_Xd(self):
        fake = link(4095, 4095)
        nearest_raw(fake, module=True)
        self.assertEqual(fake.sent[0], "XD")
        self.assertEqual(fake.sent[-1], "Xd")
        self.assertEqual(self.sleeps, [proximity.MODULE_SETTLE_S])

    def test_module_turned_off_even_if_a_read_fails(self):
        class Broken(FakeLink):
            def read_analog(self, pin, timeout=2):
                raise TimeoutError("no echo")
        fake = Broken({})
        with self.assertRaises(TimeoutError):
            nearest_raw(fake, module=True)
        self.assertEqual(fake.sent, ["XD", "Xd"])

    def test_is_forward(self):
        for c in ("kwkF", "kwkF 3", "ktrF 2", "kcrF"):
            self.assertTrue(is_forward(c), c)
        for c in ("kbk 3", "kvtF 2", "kwkL", "ksit", "kbalance"):
            self.assertFalse(is_forward(c), c)

    def test_guard_blocks_forward_walk_when_close(self):
        guard = make_guard(link(51, 4095), threshold=1000, module=False)
        self.assertIn("obstacle ahead", guard("kwkF 3"))

    def test_guard_allows_when_clear_and_ignores_other_commands(self):
        fake = link(4095, 4095)
        guard = make_guard(fake, threshold=1000, module=False)
        self.assertIsNone(guard("kwkF 3"))
        self.assertIsNone(guard("ksit"))
        self.assertEqual(len(fake.sent), 2 * proximity.READS)  # ksit caused no reads

    def test_approx_cm_matches_firmware_fit(self):
        self.assertAlmostEqual(approx_cm(51), 51 / 8.0)
        self.assertAlmostEqual(approx_cm(4095), 4096.0 / (1 + 25) - 84)


if __name__ == "__main__":
    unittest.main()
```

Also add `import unittest.mock` at the top, next to `import unittest`.

- [ ] **Step 2:** Run `.venv/bin/python -m unittest tests.test_proximity`. Expect a `ModuleNotFoundError`.

- [ ] **Step 3: Implement** `opencat_gemma/proximity.py`. Set `NEEDS_MODULE` from Task 1.

```python
"""Proximity guard with the Petoi double IR distance sensor (BiBoard pins 34/35). Serial links only.

Measured on Bittle X (2026-10-23, module on, tennis ball): median raw 4095 with nothing in front, ~3900 at 30 cm,
~2450-3000 at 20 cm, ~700 at 10 cm, ~50 at 5 cm. Single reads are noisy, so we use medians.
"""
import statistics
import time

PINS = (34, 35)
READS = 10
CLOSE_RAW = 1000  # median below this = something within roughly 10-15 cm
MODULE_SETTLE_S = 2
NEEDS_MODULE = True  # set from the Task 1 spike: True if reads are only meaningful with the firmware's XD module on
NOT_FORWARD = {"kvtF"}  # stepping in place


def nearest_raw(link, module=NEEDS_MODULE, reads=READS):
    """Median of each sensor over `reads` samples; returns the smaller (closer) one.

    With module=True the firmware's IR module is switched on (XD; the robot sits and head-tracks) only for the
    reading, and always switched off again (Xd), so it can't steer the robot during our walks.
    """
    if module:
        link.send("XD", 5)
    try:
        if module:
            time.sleep(MODULE_SETTLE_S)
        return min(statistics.median(link.read_analog(pin) for _ in range(reads)) for pin in PINS)
    finally:
        if module:
            link.send("Xd", 5)


def approx_cm(raw):
    """The firmware's fit() formula. Rough: it overestimates mid-range distances (10 cm reads as ~18 cm)."""
    return raw / 8.0 if raw < 130 else 4096.0 / ((4096 - raw) ** (1 / 3) + 25) - 84


def is_forward(command):
    name = command.split(" ")[0]
    return name.endswith("F") and name not in NOT_FORWARD


def describe(raw):
    return f"sensor {raw:.0f}, about {approx_cm(raw):.0f} cm (rough)"


def make_guard(link, threshold=CLOSE_RAW, module=NEEDS_MODULE):
    """Guard for runner.run(): returns a reason to skip a forward walk, or None to allow the command."""
    def guard(command):
        if not is_forward(command):
            return None
        raw = nearest_raw(link, module=module)
        return f"obstacle ahead ({describe(raw)})" if raw < threshold else None
    return guard
```

- [ ] **Step 4:** Run `.venv/bin/python -m unittest discover tests`. All tests pass.

---

### Task 4: Guard hook in `runner.run()`

**Files:** Modify `opencat_gemma/runner.py` and `tests/test_runner.py`.

- [ ] **Step 1: Failing test.** Add to `RunTest` in `tests/test_runner.py`:

```python
    def test_guard_skips_blocked_command_and_continues(self):
        link, logs = FakeLink(), []
        guard = lambda c: "obstacle ahead" if c.startswith("kwkF") else None
        run(C, ["kwkF 3", "ksit"], link, turn_seconds=2.0, sleep=self.sleeps.append, log=logs.append, guard=guard)
        self.assertEqual([c for c, _ in link.sent], ["ksit"])
        self.assertTrue(any("skipped kwkF 3: obstacle ahead" in l for l in logs))
```

- [ ] **Step 2:** Run it to confirm it fails, with a `TypeError` for the unexpected keyword `guard`.

- [ ] **Step 3: Implement.** In `run()`, add the parameter `guard=None`. Inside the loop, before `link.send(command, timeout)`:

```python
            reason = guard(command) if guard else None
            if reason:
                log(f"  skipped {command}: {reason}")
                continue
```

Update the docstring: "If `guard` returns a reason, that command is skipped (nothing is moving yet), and the rest continue."

- [ ] **Step 4:** Run `.venv/bin/python -m unittest discover tests`. All tests pass.

---

### Task 5: CLI: `--guard`, `--guard-threshold`, `distance?`

**Files:** Modify `opencat_gemma/__main__.py` and `tests/test_cli.py`.

- [ ] **Step 1: Failing tests.** Add to `ChatTest` in `tests/test_cli.py`. The FakeLink there gains `read_analog`, which returns `self.raw`, default 4095. Add `self.raw = 4095` to its `__init__` and:

```python
    def read_analog(self, pin, timeout=2):
        return self.raw
```

Then the tests:

```python
    def test_distance_command_prints_reading(self):
        link = FakeLink()
        link.raw = 704
        with mock.patch("opencat_gemma.proximity.time.sleep"):
            out = self.chat(["distance?"], [], link=link)
        self.assertIn("sensor 704", out)

    def test_guard_blocks_walk_when_close(self):
        link = FakeLink()
        link.raw = 51
        with mock.patch("opencat_gemma.proximity.time.sleep"):
            out = self.chat(["walk 3 steps then sit"], ['["kwkF 3","ksit"]'], link=link, argv=["--guard"])
        self.assertNotIn("kwkF 3", link.sent)
        self.assertIn("ksit", link.sent)
        self.assertIn("skipped kwkF 3", out)

    def test_guard_with_websocket_is_rejected(self):
        with self.assertRaises(SystemExit):
            cli.main(["--guard", "--ws", "ws://127.0.0.1:1", "sit"])
```

In the guard test, `link.sent` also contains `XD`/`Xd` when `NEEDS_MODULE` is True. The assertions only check `kwkF 3` and `ksit`, so they hold either way.

- [ ] **Step 2:** Confirm the tests fail.

- [ ] **Step 3: Implement** in `__main__.py`:
  - Add the import `from . import proximity`.
  - Add the arguments:
    - `--guard` (`store_true`), help: "skip forward walks when the IR distance sensor sees something close (serial only)";
    - `--guard-threshold` (`int`, default `proximity.CLOSE_RAW`).
  - In `main()`, right after `parse_args`: `if args.guard and (args.ws or args.dry_run): p.error("--guard needs a USB serial connection (not --ws or --dry-run)")`.
  - In `handle()`, build the guard and pass it to `run`:
    `guard = proximity.make_guard(link, args.guard_threshold) if args.guard else None`
    `run(contract, commands, link, turn_seconds=args.turn_seconds, guard=guard)`.
  - In `chat()`, before `handle`:

```python
        if text.lower().rstrip("?") == "distance":
            if args.dry_run or not hasattr(link, "read_analog"):
                print("  distance needs a USB serial connection")
            else:
                print(f"  nearest object: {proximity.describe(proximity.nearest_raw(link))}")
            continue
```

  - Update the chat banner to mention `distance?`.

- [ ] **Step 4:** Run `.venv/bin/python -m unittest discover tests`. All tests pass.

---

### Task 6: Docs

**Files:** Modify `README.md` and `docs/protocol.md`.

- [ ] **`README.md`:** add a short "Distance sensor (optional)" section:
  - how to attach it (the port wired to pins 34/35);
  - `--guard` and `--guard-threshold`;
  - `distance?` in chat;
  - that distances are rough;
  - whether `XD` is used, from Task 1 (the robot sits during each check if so);
  - "verified on hardware" only after Task 7.
- [ ] **`docs/protocol.md`:** add a "Pin reads and the IR sensor" section covering:
  - the `R` command bytes and reply;
  - the measured table;
  - the noise and the medians;
  - the Task 1 result.

---

### Task 7: Hardware check (Kai present, Bittle on the floor, sensor attached)

- [ ] **1.** `.venv/bin/python -m opencat_gemma --guard`, then `distance?` with nothing in front. Expect "sensor ~4095". Then with the ball at 5 cm: expect "sensor ~50".
- [ ] **2.** Ball held at 5 cm, then type "walk forward 3 steps then sit". Expect `skipped kwkF 3: obstacle ahead…`, then the robot sits.
- [ ] **3.** Ball away, then the same request. Expect the robot to walk 3 cycles and then sit.
- [ ] **4.** If `NEEDS_MODULE` is True: confirm the robot does not keep head-tracking after the check, so `Xd` took effect.
- [ ] **5.** Record the results in `docs/protocol.md` → Hardware verification, and in `README.md` → Verification status.
