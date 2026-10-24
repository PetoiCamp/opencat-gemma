# Web Bluetooth Robot Link Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From Chrome on an Android phone, a typed request goes to Gemma, then the allowlist, then the robot over Bluetooth LE, with the same safety rules as the laptop kit.

**Architecture:** Two pure JS modules port the laptop kit's tested logic:
- `web/ble.js`: `NusLink` (the Nordic UART line protocol from `opencat_gemma/ble.py`), plus a thin Web Bluetooth adapter.
- `web/runner.js`: `plan()`/`run()` from `opencat_gemma/runner.py`.

Both get `node --test` suites that mirror the Python tests. `plan()` also gets a shared fixture that runs through **both** the Python and the JS code, so the phone can't plan differently from the laptop. The page adds **Connect robot**, **Stop**, and "Ask drives the robot". A connect-only hardware check comes right after `NusLink`, before any porting builds on it.

**Tech Stack:** Web Bluetooth (Chrome on Android), plain ES modules, `node --test`, Python `unittest`.

**Safety rules carried over from `runner.py`** (unchanged):
- Walks always carry a step count (default 3). Timeout is `5 + 2 × steps` s.
- Turns are timed by the page: send the turn, wait 2.0 s, send `kbalance`.
- Any error or stop sends `kbalance`. If even that fails, say "switch the robot off".
- A `final` code (`XO`/`Xo`) ends the plan. `XO` is refused over Bluetooth.

**New for the phone:**
- A **Stop** button.
- **Hiding the page while the robot is moving sends Stop.** A backgrounded tab may lose the link, and a timed turn would then never get its `kbalance`.
- A **disconnect** is logged, and the link is dropped.

**Facts this plan relies on:**
- NUS service and characteristics, the ESP32 greeting and the S3 handshake: `docs/protocol.md` "Bluetooth (BLE)" and `opencat_gemma/ble.py`. These were verified with macOS and `bleak`.
- Advertised names `Bittle0D_BLE`, `Quaddle03_BLE`, `Petoi_BLE`. Web Bluetooth `namePrefix` filters are case-sensitive, so each lowercase `ble_prefix` is also offered capitalised.

**Not verified (Task 2 and Task 5 find out):**
- That Chrome on Android can connect, receive notifications, and write without response to the robot.
- That the greeting and `?` timings match macOS.
- How long the connection survives a screen-off.

**Out of scope:** Wi-Fi/WebSocket from the page (mixed content, see README), iOS, choosing a robot by name (the Chrome device chooser does that), and a hosted (https) page.

---

## File structure

| File | Responsibility |
|---|---|
| `web/ble.js` | `NusLink` (line protocol, transport-agnostic), `robotFromReply`, `connectWebBluetooth` (Web Bluetooth adapter). |
| `web/ble.test.mjs` | Mirrors `tests/test_ble.py` `BleLink` tests, using recorded robot output from `docs/protocol.md`. |
| `web/runner.js` | `plan`, `run`, `sleep`, constants: a port of `opencat_gemma/runner.py`. |
| `web/runner.test.mjs` | Shared `plan` fixture, plus mirrors of `tests/test_runner.py` `run` tests. |
| `web/plan_cases.json` | Shared fixture: robot, commands → plan / log / error. |
| `tests/test_web_runner_parity.py` | Runs the same fixture through the real Python `runner.plan`. |
| `web/index.html` | Quaddle in the robot menu, Connect robot, Stop, Ask drives the robot, stop on hide/disconnect. |
| `docs/protocol.md` | New "Web Bluetooth (Chrome on Android)" subsection with what was measured. |
| `README.md` | The Android line: robot control over Bluetooth. |

---

### Task 1: `NusLink` + `robotFromReply` (pure, tested)

**Files:**
- Create: `web/ble.js`
- Test: `web/ble.test.mjs`

- [ ] **Step 1: Write the failing tests**

```js
// Mirrors tests/test_ble.py (BleLink). Robot output is the recorded text from docs/protocol.md.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { NusLink, robotFromReply } from "./ble.js";

// A link with a fake clock. `replies` maps a written line to text the robot notifies back (string or chunks).
function fake(replies = {}) {
  let t = 0;
  const writes = [];
  const link = new NusLink(async (bytes) => {
    const line = new TextDecoder().decode(bytes);
    writes.push(line);
    for (const chunk of [replies[line] ?? []].flat()) link.feed(chunk);
  }, { now: () => t, tick: async (ms) => { t += ms; } });
  return { link, writes, now: () => t };
}

const registry = Object.fromEntries(["bittle", "nybble", "quaddle"].map((r) => {
  const d = JSON.parse(readFileSync(new URL(`../contract/${r}.json`, import.meta.url)));
  return [r, [d.model, d.ble_prefix]];
}));

test("ESP32 style: waits for the forced d, then identifies with ?", async () => {
  const { link, writes } = fake({ "?\n": "G\r\nBittle X\r\nB10_260527\r\n?\r\n" });
  link.feed("Petoi Bittle Xpg\r\nrest\r\nd\r\n");
  assert.equal(await link.connect(), "G | Bittle X | B10_260527 | ?");
  assert.deepEqual(writes, ["?\n"]);
});

test("S3 style: silent, then a handshake without line breaks", async () => {
  const { link, now } = fake({ "?\n": ["Petoi Quaddle", "u", "Quaddle", "Q_261022", "?"] });
  assert.equal(await link.connect(), "Petoi QuaddleuQuaddleQ_261022?");
  assert.ok(now() >= 2000, "waited the 2 s push window first");
});

test("S3 style: a line-based reply is accepted too", async () => {
  const { link } = fake({ "?\n": "Quaddle\r\nQ_261022\r\n?\r\n" });
  assert.equal(await link.connect(), "Quaddle | Q_261022 | ?");
});

test("greeting without d still identifies with ?", async () => {
  const { link } = fake({ "?\n": "Bittle X\r\n?\r\n" });
  link.feed("Petoi Bittle Xpg\r\n");
  assert.equal(await link.connect(), "Bittle X | ?");
});

test("no reply to ? times out", async () => {
  const { link } = fake();
  await assert.rejects(link.connect(), /no reply to '\?' within 5s/);
});

test("connect clears the buffer, so send sees only its own reply", async () => {
  const { link } = fake({ "?\n": "Bittle X\r\n?\r\n", "ksit\n": "sit\r\nk\r\n" });
  await link.connect();
  assert.equal(await link.send("ksit"), "sit | k");
});

test("send writes the command and returns on the first-letter echo", async () => {
  const { link, writes } = fake({ "kwkF 3\n": "up\r\nk\r\n" });
  assert.equal(await link.send("kwkF 3", 11), "up | k");
  assert.deepEqual(writes, ["kwkF 3\n"]);
});

test("send waits for an echo override", async () => {
  const { link } = fake({ "XO\n": "X\r\nk\r\n" });
  assert.equal(await link.send("XO", 10, { echo: "k" }), "X | k");
});

test("a notification split mid-line is joined", async () => {
  const { link } = fake({ "ksit\n": ["si", "t\r", "\nk", "\r\n"] });
  assert.equal(await link.send("ksit"), "sit | k");
});

test("send without an echo times out", async () => {
  const { link } = fake({ "ksit\n": "sit\r\n" });
  await assert.rejects(link.send("ksit", 1), /no "k" echo for "ksit" within 1s/);
});

test("send returns on a done pattern without an echo", async () => {
  const { link } = fake({ "?\n": "Bittle X\r\nB10\r\n" });
  assert.equal(await link.send("?", 5, { done: /^B10/ }), "Bittle X | B10");
});

test("send stops waiting when aborted", async () => {
  const { link } = fake();
  const ctl = new AbortController();
  ctl.abort(new Error("stopped"));
  await assert.rejects(link.send("kwkF 3", 11, { signal: ctl.signal }), /stopped/);
});

test("robotFromReply maps ? replies with the real contracts; first model name wins", () => {
  assert.equal(robotFromReply("G | Bittle X | B10_260527 | ?", registry), "bittle");
  assert.equal(robotFromReply("Petoi QuaddleuQuaddleQ_261022?", registry), "quaddle");
  assert.equal(robotFromReply("Nybble Q | ?", registry), "nybble");
  assert.equal(robotFromReply("hello | ?", registry), null);
});
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `node --test web/`
Expected: FAIL, `Cannot find module .../web/ble.js`.

- [ ] **Step 3: Write `web/ble.js`**

```js
// Bluetooth LE link over the Nordic UART service: a port of opencat_gemma/ble.py (BleLink) plus a Web Bluetooth adapter.
// Same handshake as the laptop kit, see docs/protocol.md "Bluetooth (BLE)".
export const NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
export const NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";  // we write commands here
export const NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";  // the robot notifies replies here
const PUSH_WAIT_S = 2;  // ESP32 firmware pushes its greeting within this time
const GREETING_TIMEOUT_S = 8;  // then the forced "d" arrives within this time
const QUERY_TIMEOUT_S = 5;

const encode = (s) => new TextEncoder().encode(s);
const joined = (lines) => lines.filter(Boolean).join(" | ");

export class NusLink {
  isBle = true;  // the runner refuses commands that would drop a Bluetooth link (XO)

  // write(Uint8Array) -> Promise. The transport calls feed(text) for every notification.
  constructor(write, { now = () => performance.now(), tick = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
    this.write = write;
    this.now = now;
    this.tick = tick;
    this.buf = "";
  }

  feed(text) {
    this.buf += text;
  }

  // Complete lines once one equals token (case-insensitive) or matches the `done` regex.
  async linesUntil(token, timeout, what, { done, signal } = {}) {
    const end = this.now() + timeout * 1000;
    for (;;) {
      signal?.throwIfAborted();
      const lines = this.buf.split("\n").slice(0, -1).map((l) => l.trim());
      if (lines.some((l) => l.toLowerCase() === token.toLowerCase()) || (done && lines.some((l) => done.test(l)))) {
        return lines;
      }
      if (this.now() >= end) {
        throw new Error(`no ${JSON.stringify(token)} echo for ${what} within ${timeout}s, got ${JSON.stringify(this.buf)}`);
      }
      await this.tick(10);
    }
  }

  // If a greeting is pushed (ESP32 firmware), wait for its forced "d" so our commands aren't overwritten.
  // Then always identify with "?" (S3 firmware only answers when asked). Returns the "?" reply.
  async connect() {
    let end = this.now() + PUSH_WAIT_S * 1000;
    while (this.now() < end && !this.buf) await this.tick(10);
    if (this.buf) {
      try {
        await this.linesUntil("d", GREETING_TIMEOUT_S, "the connect greeting");
      } catch {
        // no forced rest seen; "?" below still identifies the robot
      }
    }
    this.buf = "";
    await this.write(encode("?\n"));
    end = this.now() + QUERY_TIMEOUT_S * 1000;
    let lines;
    for (;;) {
      const buf = this.buf;
      lines = buf.split("\n").map((l) => l.trim());
      // A normal reply ends with a "?" line. The S3 firmware's first reply is "Petoi <MODEL>u<MODEL><version>?".
      if (lines.slice(0, -1).includes("?") || (buf.includes("Petoi") && buf.trim().endsWith("?"))) break;
      if (this.now() >= end) throw new Error(`no reply to '?' within ${QUERY_TIMEOUT_S}s, got ${JSON.stringify(buf)}`);
      await this.tick(10);
    }
    this.buf = "";
    return joined(lines);
  }

  // Returns on the token echo (`echo`, default the command's first letter), or earlier on a line matching `done`.
  async send(command, timeout = 10, { done, echo, signal } = {}) {
    this.buf = "";
    await this.write(encode(command + "\n"));
    return joined(await this.linesUntil(echo || command[0], timeout, JSON.stringify(command), { done, signal }));
  }
}

// Map a "?" reply to a robot from {robot: [model, blePrefix]}; the model name that appears first wins.
export function robotFromReply(reply, registry) {
  const found = Object.entries(registry)
    .filter(([, [model]]) => reply.includes(model))
    .map(([robot, [model]]) => [reply.indexOf(model), robot])
    .sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1]));
  return found.length ? found[0][1] : null;
}

// Web Bluetooth adapter. Must be called from a user tap (Chrome shows its device chooser).
// prefixes: lowercase name prefixes; namePrefix filters are case-sensitive, so each is also offered capitalised.
export async function connectWebBluetooth(prefixes, log = console.log) {
  const names = [...new Set(prefixes.flatMap((p) => [p, p[0].toUpperCase() + p.slice(1)]))];
  const device = await navigator.bluetooth.requestDevice({
    filters: names.map((namePrefix) => ({ namePrefix })), optionalServices: [NUS_SERVICE],
  });
  log(`connecting to ${device.name} ...`);
  const service = await (await device.gatt.connect()).getPrimaryService(NUS_SERVICE);
  const rx = await service.getCharacteristic(NUS_RX);
  const tx = await service.getCharacteristic(NUS_TX);
  let queue = Promise.resolve();  // one GATT write at a time
  const link = new NusLink((bytes) => (queue = queue.catch(() => {}).then(() => rx.writeValueWithoutResponse(bytes))));
  tx.addEventListener("characteristicvaluechanged", (e) => {
    const v = e.target.value;
    link.feed(String.fromCharCode(...new Uint8Array(v.buffer, v.byteOffset, v.byteLength)));  // ISO-8859-1, as ble.py
  });
  await tx.startNotifications();
  link.device = device;
  link.close = () => device.gatt.disconnect();
  return { link, name: device.name, reply: await link.connect() };
}
```

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `node --test web/`
Expected: all pass: 2 parse tests + 13 ble tests.

- [ ] **Step 5: Commit**

```bash
git add web/ble.js web/ble.test.mjs
git commit -m "feat(web): NUS link + robot detection, ported from ble.py"
```

### Task 2: Connect-only hardware check (needs the user and a robot)

Find out early whether Chrome on Android reaches the robot at all, before building on it.

**Files:**
- Modify: `web/index.html` (robot menu, Connect button, `connect()`)

- [ ] **Step 1: Add Quaddle and a Connect button**

In the HTML, the robot menu becomes `<option>bittle</option><option>nybble</option><option>quaddle</option>`. After the `Run eval` button, add:

```html
<p><button id="connect">Connect robot (Bluetooth)</button> <button id="stop">Stop</button></p>
```

- [ ] **Step 2: Add the registry and `connect()`**

Import `import { connectWebBluetooth, robotFromReply } from "./ble.js";`. Then, before `load()`, add:

```js
const ROBOTS = ["bittle", "nybble", "quaddle"];  // contract/<robot>.json
let link = null;
// Fetched at page start: requestDevice() needs the user's tap, so connect() must not wait on the network first.
const registryReady = Promise.all(ROBOTS.map(async (r) => {
  const d = JSON.parse(await fetchText(`../contract/${r}.json`));
  return [r, [d.model, d.ble_prefix]];
})).then(Object.fromEntries);

async function connect() {
  const registry = await registryReady;
  const t = performance.now();
  const c = await connectWebBluetooth([...Object.values(registry).map(([, p]) => p), "petoi"], log);
  const robot = robotFromReply(c.reply, registry);
  log(`connected to ${c.name} in ${((performance.now() - t) / 1000).toFixed(1)}s: ${c.reply} -> ${robot ?? "unknown"}`);
  if (!robot) {
    c.link.close();
    throw new Error("not a robot this page knows (no contract model name in the '?' reply)");
  }
  link = c.link;
  link.device.addEventListener("gattserverdisconnected", () => { log("robot disconnected"); link = null; });
}
```

Wire it up: `$("connect").onclick = guard(connect);`.

- [ ] **Step 3: Check on hardware**

Setup: robot charged and on, the Petoi phone app closed, and the page served and reverse-forwarded as before. The user taps **Connect robot** and picks the robot. Expected log: `connected to Bittle0D_BLE in …s: … -> bittle`, and an ESP32 robot lies down (forced rest). Then, over CDP: `link.send("ksit")` and `link.send("kbalance")`. Expected: the robot sits, then stands, and each call returns a reply ending in `k`.

**If connect fails**, stop and report the exact error, and get `chrome://bluetooth-internals` from the user. Possible causes: no permission, the robot not in the chooser, or no notifications.

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "feat(web): connect a Petoi robot over Web Bluetooth"
```

### Task 3: Runner port + shared plan fixture

**Files:**
- Create: `web/plan_cases.json`, `tests/test_web_runner_parity.py`, `web/runner.js`, `web/runner.test.mjs`

- [ ] **Step 1: Write the shared fixture `web/plan_cases.json`**

```json
[
  {"robot": "bittle", "commands": ["kwkF", "ksit"], "plan": [["kwkF 3", 11, false], ["ksit", 10, false]], "log": [], "error": null},
  {"robot": "bittle", "commands": ["kwkF 5", "kwkL"], "plan": [["kwkF 5", 15, false], ["kwkL", 10, true]], "log": [], "error": null},
  {"robot": "bittle", "commands": ["kbk 20"], "plan": [["kbk 20", 45, false]], "log": [], "error": null},
  {"robot": "bittle", "commands": [], "plan": [], "log": [], "error": null},
  {"robot": "bittle", "commands": ["kwkL 90"], "plan": null, "log": [], "error": "not allowed"},
  {"robot": "bittle", "commands": ["ksit", "XO"], "plan": null, "log": [], "error": "not allowed"},
  {"robot": "quaddle", "commands": ["vcv", "XO", "ksit", "kwkF"], "plan": [["vcv", 10, false], ["XO", 10, false]], "log": ["  dropped ksit, kwkF after XO/Xo"], "error": null},
  {"robot": "quaddle", "commands": ["m0 45", "Xo"], "plan": [["m0 45", 10, false], ["Xo", 10, false]], "log": [], "error": null},
  {"robot": "quaddle", "commands": ["m0"], "plan": null, "log": [], "error": "not allowed"}
]
```

- [ ] **Step 2: Write the Python parity test `tests/test_web_runner_parity.py`**

```python
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
```

- [ ] **Step 3: Run it**

Run: `.venv/bin/python -m unittest tests.test_web_runner_parity -v`
Expected: PASS. This pins the Python behaviour. If a case fails, the fixture is wrong about Python, so fix the fixture.

- [ ] **Step 4: Write the failing JS tests `web/runner.test.mjs`**

```js
// Shared plan fixture (also run by tests/test_web_runner_parity.py) + mirrors of tests/test_runner.py run tests.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { plan, run, STOP } from "./runner.js";

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url)));
const contract = (r) => ({ codes: read(`../contract/${r}.json`).codes, pattern: read(`../contract/${r}.schema.json`).items.pattern });
const B = contract("bittle"), Q = contract("quaddle");

// Records sends; throws for commands in `fail`.
function fakeLink({ isBle = false, fail = [] } = {}) {
  const sent = [];
  return {
    isBle, sent,
    async send(command, timeout, opts = {}) {
      sent.push([command, timeout, opts.echo]);
      if (fail.includes(command)) throw new Error(`timeout on ${command}`);
      return "k";
    },
  };
}
const quiet = { log: () => {}, sleep: async () => {} };

test("plan fixture matches the Python runner", () => {
  for (const c of read("./plan_cases.json")) {
    const logs = [];
    if (c.error) assert.throws(() => plan(contract(c.robot), c.commands, (s) => logs.push(s)), new RegExp(`^Error: ${c.error}`));
    else assert.deepEqual(plan(contract(c.robot), c.commands, (s) => logs.push(s)), c.plan);
    assert.deepEqual(logs, c.log, JSON.stringify(c.commands));
  }
});

test("sends in order with step counts and timeouts", async () => {
  const link = fakeLink();
  await run(B, ["kwkF", "ksit"], link, quiet);
  assert.deepEqual(link.sent.map(([c, t]) => [c, t]), [["kwkF 3", 11], ["ksit", 10]]);
});

test("a turn is held, then stopped", async () => {
  const link = fakeLink(), slept = [];
  await run(B, ["kwkL"], link, { log: () => {}, sleep: async (s) => { slept.push(s); }, turnSeconds: 2 });
  assert.deepEqual(link.sent.map(([c]) => c), ["kwkL", STOP]);
  assert.deepEqual(slept, [2]);
});

test("a timeout sends STOP and rethrows", async () => {
  const link = fakeLink({ fail: ["kwkF 3"] });
  await assert.rejects(run(B, ["kwkF", "ksit"], link, quiet), /timeout on kwkF 3/);
  assert.deepEqual(link.sent.map(([c]) => c), ["kwkF 3", STOP]);
});

test("abort during a turn pause sends STOP and rethrows", async () => {
  const link = fakeLink(), ctl = new AbortController();
  const sleep = async () => { ctl.abort(new Error("Stop button")); ctl.signal.throwIfAborted(); };
  await assert.rejects(run(B, ["kwkL", "ksit"], link, { log: () => {}, sleep, signal: ctl.signal }), /Stop button/);
  assert.deepEqual(link.sent.map(([c]) => c), ["kwkL", STOP]);
});

test("a failed STOP is logged and the original error raised", async () => {
  const link = fakeLink({ fail: ["ksit", STOP] }), logs = [];
  await assert.rejects(run(B, ["ksit"], link, { log: (s) => logs.push(s), sleep: async () => {} }), /timeout on ksit/);
  assert.ok(logs.some((l) => l.includes("STOP FAILED") && l.includes("switch the robot off")));
});

test("XO over Bluetooth is refused before any send; Xo is sent", async () => {
  const link = fakeLink({ isBle: true });
  await assert.rejects(run(Q, ["ksit", "XO"], link, quiet), /XO \(mouse mode\) disconnects Bluetooth; use USB or Wi-Fi/);
  assert.deepEqual(link.sent, []);
  await run(Q, ["Xo"], link, quiet);
  assert.deepEqual(link.sent, [["Xo", 10, "k"]]);
});

test("echo override reaches send only for codes that set it", async () => {
  const link = fakeLink();
  await run(Q, ["ksit", "XO"], link, quiet);
  assert.deepEqual(link.sent.map(([c, , e]) => [c, e]), [["ksit", undefined], ["XO", "k"]]);
});

test("empty and disallowed send nothing", async () => {
  const link = fakeLink();
  await run(B, [], link, quiet);
  await assert.rejects(run(B, ["kwkL 90"], link, quiet), /not allowed/);
  assert.deepEqual(link.sent, []);
});
```

- [ ] **Step 5: Run them to make sure they fail**

Run: `node --test web/`
Expected: FAIL, `Cannot find module .../web/runner.js`.

- [ ] **Step 6: Write `web/runner.js`**

```js
// Port of opencat_gemma/runner.py: make every command finite, send one at a time, always keep our own stop.
export const STOP = "kbalance";
export const DEFAULT_STEPS = 3;
export const TURN_SECONDS = 2.0;
export const WALK_BASE_S = 5;  // walk timeout = WALK_BASE_S + S_PER_STEP * steps
export const S_PER_STEP = 2;
export const CMD_TIMEOUT_S = 10;  // every other command, and STOP
export const BLE_REFUSED = { XO: "XO (mouse mode) disconnects Bluetooth; use USB or Wi-Fi" };

// Resolves after `seconds`, or rejects as soon as `signal` aborts.
export const sleep = (seconds, signal) => new Promise((resolve, reject) => {
  signal?.throwIfAborted();
  const t = setTimeout(resolve, seconds * 1000);
  signal?.addEventListener("abort", () => { clearTimeout(t); reject(signal.reason); }, { once: true });
});

// contract: {codes, pattern}. Returns [[command, timeoutS, timedByUs]]. See runner.py plan() for the reasons.
export function plan(contract, commands, log = console.log) {
  const re = new RegExp(contract.pattern);
  const bad = commands.filter((c) => typeof c !== "string" || !re.test(c));
  if (bad.length) throw new Error(`not allowed: ${JSON.stringify(bad)}`);
  const out = [];
  for (const [i, command] of commands.entries()) {
    const [name, steps] = command.split(" ");
    const kind = contract.codes[name].kind;
    if (kind === "steps") {
      const n = steps ? parseInt(steps, 10) : DEFAULT_STEPS;
      out.push([`${name} ${n}`, WALK_BASE_S + S_PER_STEP * n, false]);
    } else {
      out.push([command, CMD_TIMEOUT_S, kind === "timed"]);
    }
    if (kind === "final" && i + 1 < commands.length) {
      log(`  dropped ${commands.slice(i + 1).join(", ")} after XO/Xo`);
      break;
    }
  }
  return out;
}

// Send each command and wait for the robot. On any error or abort, send STOP, then rethrow.
export async function run(contract, commands, link, { turnSeconds = TURN_SECONDS, sleep: wait = sleep, log = console.log, signal } = {}) {
  const steps = plan(contract, commands, log);  // throws before anything is sent
  if (link.isBle) {
    for (const [command] of steps) if (BLE_REFUSED[command]) throw new Error(BLE_REFUSED[command]);
  }
  const replies = [];
  try {
    for (const [command, timeout, timed] of steps) {
      signal?.throwIfAborted();
      const echo = contract.codes[command.split(" ")[0]].echo;
      replies.push(await link.send(command, timeout, { echo, signal }));
      log(`  sent ${command.padEnd(10)} robot: ${replies.at(-1)}`);
      if (timed) {
        await wait(turnSeconds, signal);
        replies.push(await link.send(STOP, CMD_TIMEOUT_S));
        log(`  sent ${STOP.padEnd(10)} robot: ${replies.at(-1)}`);
      }
    }
  } catch (e) {
    log("  stopping robot");
    try {
      await link.send(STOP, CMD_TIMEOUT_S);
    } catch (e2) {
      log(`  STOP FAILED: ${e2} - switch the robot off`);
    }
    throw e;
  }
  return replies;
}
```

- [ ] **Step 7: Run all tests**

Run: `node --test web/ && .venv/bin/python -m unittest discover tests`
Expected: all node tests pass (2 parse + 13 ble + 9 runner). Python: 131 OK (130 + the plan parity test).

- [ ] **Step 8: Commit**

```bash
git add web/plan_cases.json tests/test_web_runner_parity.py web/runner.js web/runner.test.mjs
git commit -m "feat(web): runner port with a plan fixture shared with runner.py"
```

### Task 4: Ask drives the robot; Stop, hide and disconnect

**Files:**
- Modify: `web/index.html`

- [ ] **Step 1: Load the contract per robot, and re-prefill when the robot changes**

Import `import { run, STOP, CMD_TIMEOUT_S } from "./runner.js";`. Add `codes` and `running = null` to the `let` line. Replace `load()` with `loadRobot()` + `load()`:

```js
// Contract for `robot`; with a loaded model, also a new prefilled conversation (the old base and its last clone
// are left alone: deleting clones out of order broke base.clone() in 0.18.0, and robot switches are rare).
async function loadRobot(robot) {
  prompt = await fetchText(`../contract/${robot}.prompt.txt`);
  pattern = JSON.parse(await fetchText(`../contract/${robot}.schema.json`)).items.pattern;
  codes = JSON.parse(await fetchText(`../contract/${robot}.json`)).codes;
  if (!engine) return;
  const t = performance.now();
  base = await engine.createConversation({
    preface: { messages: [{ role: "system", content: prompt }], extra_context: { enable_thinking: false } },
    sessionConfig: { samplerParams: { type: SamplerType.GREEDY }, maxOutputTokens: 128 },
    prefillPrefaceOnInit: true,
  });
  prev = null;
  log(`system prompt prefilled in ${((performance.now() - t) / 1000).toFixed(1)}s (${robot})`);
}

async function load() {
  const model = $("file").files[0] ?? $("url").value;
  log(`loading ${model.name ?? model} ...`);
  const t = performance.now();
  engine = await Engine.create({ model, mainExecutorSettings: { maxNumTokens: 2048 } });
  log(`model loaded in ${((performance.now() - t) / 1000).toFixed(1)}s`);
  await loadRobot($("robot").value);
  $("eval").disabled = $("ask").disabled = false;
}
```

At the end of `connect()`, after the `gattserverdisconnected` listener, add: `if (robot !== $("robot").value) { $("robot").value = robot; await loadRobot(robot); }`.

Add a handler for the robot menu: `$("robot").onchange = guard(() => loadRobot($("robot").value));`.

- [ ] **Step 2: Make Ask drive the robot, and add Stop and stop-on-hide**

Replace the `$("ask").onclick` handler with:

```js
$("ask").onclick = guard(async () => {
  const r = await ask($("req").value);
  log(`${r.secs.toFixed(1)}s | ${r.out} -> ${r.error ?? JSON.stringify(r.commands)}`);
  if (!link || r.error || !r.commands.length) return;  // refused or empty: the robot is untouched
  running = new AbortController();
  try {
    await run({ codes, pattern }, r.commands, link, { log, signal: running.signal });
  } finally {
    running = null;
  }
});

// Stop: abort a running plan (run() sends STOP on the way out), else send STOP directly.
function stop(why) {
  if (running) {
    log(`stop: ${why}`);
    running.abort(new Error(why));
  } else if (link) {
    link.send(STOP, CMD_TIMEOUT_S).then((r) => log(`  sent ${STOP} robot: ${r}`), (e) => log(`  STOP FAILED: ${e} - switch the robot off`));
  }
}
$("stop").onclick = () => stop("Stop button");
// A hidden tab may lose the Bluetooth link; a timed turn would then never get its kbalance.
document.addEventListener("visibilitychange", () => { if (document.hidden && running) stop("page hidden"); });
```

- [ ] **Step 3: Check nothing else broke**

Run: `node --test web/ && .venv/bin/python -m unittest discover tests`
Expected: same counts as Task 3, all passing.

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "feat(web): Ask drives the robot over Bluetooth; Stop and stop-on-hide"
```

### Task 5: Hardware verification on the phone (needs the user and a robot)

Run with Bittle X (and Quaddle if available), the Petoi app closed, the model loaded, and **Connect robot** tapped. Record the results as you go.

- [ ] **Step 1:** Connect: time, the `?` reply, the detected robot. ESP32 robots lie down on connect.
- [ ] **Step 2:** Ask "stand up then sit" → `kbalance`/`kup`, then `ksit`, with each reply ending in `k`.
- [ ] **Step 3:** Ask "walk forward 3 steps" → `kwkF 3`. The robot walks and stands up by itself; record the time to the `k`.
- [ ] **Step 4:** Ask "turn left" → `kwkL`, then `kbalance` after 2.0 s.
- [ ] **Step 5:** Ask "walk forward 10 steps", then tap **Stop** mid-walk. Expected: `stop: Stop button`, `stopping robot`, then the robot stands. Record whether `kbalance` needed a retry. Over Wi-Fi the firmware rejected a new task during a walk; over BLE that's unknown.
- [ ] **Step 6:** Ask "turn left", then switch apps during the 2 s hold. Expected: `stop: page hidden`, and the robot stops. Record whether the link survived.
- [ ] **Step 7:** Ask "do a backflip" with the robot on the floor and space clear, **or** skip it and record that it was skipped. Ask "make me a sandwich" → `[]`, nothing sent.
- [ ] **Step 8:** Lock the screen for 30 s while connected and idle. Record whether `robot disconnected` appears and whether **Connect robot** works again.
- [ ] **Step 9:** If any step fails, fix it with a failing test first where the logic is testable (`ble.js`/`runner.js`), then commit (`fix(web): …`).

### Task 6: Record results

**Files:**
- Modify: `docs/protocol.md` (add a `### Web Bluetooth (Chrome on Android)` subsection at the end of the "Bluetooth (BLE)" section)
- Modify: `README.md` (the "Android (web, experimental)" line)
- Modify: this plan (add `## Results`)

- [ ] **Step 1:** In `docs/protocol.md`, record what Task 5 measured: chooser names, connect time, greeting and `?` behaviour compared with macOS, the Stop timing, and screen-off/hidden behaviour. Mark each item as observed (with date and phone), and say what wasn't tested.
- [ ] **Step 2:** In the README, change "No robot connection yet." to "Tap **Connect robot** to drive a Petoi robot over Bluetooth LE (Chrome on Android; Bittle X verified 2026-10-23)", adjusted to what Task 5 actually verified.
- [ ] **Step 3:** In this plan, add `## Results` with the Task 5 checklist outcomes and any deviations from the plan.
- [ ] **Step 4: Commit**

```bash
git add docs/protocol.md README.md docs/superpowers/plans/2026-10-23-web-bluetooth.md
git commit -m "docs: Web Bluetooth on Android results"
```
