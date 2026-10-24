# Bluetooth Demo Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A clean demo page, `web/demo.html`, for Chrome on Android. The model loads from a copy kept on the phone, you type a request, and the robot runs it over Bluetooth, with a big STOP and a chat history.

**Architecture:** Logic moves out of `web/index.html` into small, tested modules that both pages share:
- `web/litert.js`: the pinned LiteRT-LM import.
- `web/contracts.js`: robot contracts and the registry.
- `web/gemma.js`: load, prefill once, clone per request.
- `web/driver.js`: the robot link, one plan at a time, Stop.
- `web/model_store.js`: the OPFS copy of the model.

`runner.run` gets an `onSent` hook so the demo can show ✓ per command. `web/demo.html` is UI only. The test page keeps its behaviour and its `window.__test` hook.

**Tech Stack:** plain ES modules, `@litert-lm/core@0.18.0` (WebGPU), Web Bluetooth, OPFS (`navigator.storage.getDirectory()`), `node --test`.

**Spec:** `docs/superpowers/specs/2026-10-23-bluetooth-demo-design.md`

**Baseline:** `node --test web/` → 25 pass. `.venv/bin/python -m unittest discover tests` → 132 OK. Python isn't touched by this plan.

---

## File structure

| File | Responsibility |
|---|---|
| `web/litert.js` (new) | Re-exports `Engine`, `SamplerType` from the pinned CDN build, in one place. |
| `web/contracts.js` (new) | `ROBOTS`, `fetchContract(robot, fetchText)`, `loadRegistry(fetchText)`. |
| `web/gemma.js` (new) + `web/gemma.test.mjs` | `Gemma.load`, `setRobot`, `ask`, `contract`, `close`, `textOf`. |
| `web/model_store.js` (new) + `web/model_store.test.mjs` | `saveModel`, `loadModel`, `clearModel` on an injected OPFS directory. |
| `web/runner.js` (modify) + `web/runner.test.mjs` | `run(..., { onSent })` callback. |
| `web/driver.js` (new) + `web/driver.test.mjs` | `Driver`: `link`, `busy`, `run` → `"done"`/`"stopped"`, `stop`, `stopIfRunning`. |
| `web/ble.js` (modify) | `connectRobot(registry, log)`: connect, then identify, or close and throw. |
| `web/index.html` (modify) | The test harness, rewired onto the modules. Same buttons and same `window.__test` hook. |
| `web/demo.html` (new) | The demo UI. |
| `README.md`, this plan | How to open the demo; results. |

---

### Task 1: `litert.js`, `contracts.js`, `gemma.js`

**Files:**
- Create: `web/litert.js`, `web/contracts.js`, `web/gemma.js`
- Test: `web/gemma.test.mjs`

- [ ] **Step 1: Write the failing tests `web/gemma.test.mjs`**

```js
// Gemma on the page with a fake LiteRT engine: what gets prefilled, and the clone order 0.18.0 needs.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Gemma, textOf } from "./gemma.js";

const fetchText = async (p) => readFileSync(new URL(p, import.meta.url), "utf8");
const promptOf = (robot) => readFileSync(new URL(`../contract/${robot}.prompt.txt`, import.meta.url), "utf8");

// A fake engine that records what happens. Clones are named <parent>.c<n>.
function fakeEngine(reply = () => "[]") {
  const events = [], configs = [];
  let n = 0;
  const conv = (name) => ({
    async clone() { const c = conv(`${name}.c${++n}`); events.push(`clone ${c.name}`); return c; },
    async delete() { events.push(`delete ${name}`); },
    async sendMessage(text) { events.push(`send ${name}`); return { role: "model", content: reply(text) }; },
  });
  const engine = {
    async createConversation(cfg) { configs.push(cfg); const name = `base${configs.length}`; events.push(`create ${name}`); return conv(name); },
    async delete() { events.push("engine delete"); },
  };
  const Engine = { async create(opts) { Engine.opts = opts; return engine; } };
  return { deps: { Engine, SamplerType: { GREEDY: 3 } }, events, configs, Engine };
}

async function loaded(f, robot = "bittle") {
  const g = await Gemma.load(f.deps, "model.litertlm", { fetchText });
  await g.setRobot(robot);
  return g;
}

test("load creates the engine; setRobot prefills that robot's prompt once, greedy, thinking off", async () => {
  const f = fakeEngine();
  await loaded(f);
  assert.deepEqual(f.Engine.opts, { model: "model.litertlm", mainExecutorSettings: { maxNumTokens: 2048 } });
  assert.deepEqual(f.configs, [{
    preface: { messages: [{ role: "system", content: promptOf("bittle") }], extra_context: { enable_thinking: false } },
    sessionConfig: { samplerParams: { type: 3 }, maxOutputTokens: 128 },
    prefillPrefaceOnInit: true,
  }]);
});

test("each request clones the base; the previous clone is deleted only after the next clone exists", async () => {
  const f = fakeEngine();
  const g = await loaded(f);
  await g.ask("sit");
  await g.ask("stand");
  assert.deepEqual(f.events, ["create base1", "clone base1.c1", "send base1.c1", "clone base1.c2", "delete base1.c1", "send base1.c2"]);
});

test("ask returns Gemma's text and the allowlist verdict", async () => {
  const f = fakeEngine((text) => (text === "ok" ? ' ["kwkF 5", "ksit"] ' : '["kwkL 90"]'));
  const g = await loaded(f);
  const good = await g.ask("ok");
  assert.equal(good.out, '["kwkF 5", "ksit"]');
  assert.deepEqual(good.commands, ["kwkF 5", "ksit"]);
  assert.equal(good.error, null);
  assert.equal(typeof good.secs, "number");
  const bad = await g.ask("bad");
  assert.equal(bad.commands, null);
  assert.match(bad.error, /^not allowed/);
});

test("setRobot switches contract and base, leaving the old base alone", async () => {
  const f = fakeEngine(() => '["XO"]');
  const g = await loaded(f);
  await g.ask("sit");
  await g.setRobot("quaddle");
  assert.equal(f.configs[1].preface.messages[0].content, promptOf("quaddle"));
  assert.equal(g.robot, "quaddle");
  assert.equal(g.contract.codes.XO.kind, "final");
  const r = await g.ask("mouse mode");
  assert.deepEqual(r.commands, ["XO"]);
  assert.deepEqual(f.events.slice(3), ["create base2", "clone base2.c2", "send base2.c2"]);  // no deletes
});

test("close deletes the engine", async () => {
  const f = fakeEngine();
  const g = await loaded(f);
  await g.close();
  assert.equal(f.events.at(-1), "engine delete");
});

test("textOf joins text parts and ignores the rest", () => {
  assert.equal(textOf({ content: "a" }), "a");
  assert.equal(textOf({ content: [{ type: "text", text: "a" }, { type: "image" }, { type: "text", text: "b" }] }), "ab");
  assert.equal(textOf({}), "");
});
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `node --test web/`
Expected: FAIL, `Cannot find module .../web/gemma.js`.

- [ ] **Step 3: Write `web/litert.js`**

```js
// @litert-lm/core pinned to 0.18.0, the version Google's hosted chat demo ships. 0.18.1's JS does not match its own
// WASM (Engine.create fails with "getMutableMainExecutorSettings is not a function" on a Pixel 7 Pro, 2026-10-23).
export { Engine, SamplerType } from "https://cdn.jsdelivr.net/npm/@litert-lm/core@0.18.0/+esm";
```

- [ ] **Step 4: Write `web/contracts.js`**

```js
// Robot contracts: contract/<robot>.json plus the generated .prompt.txt and .schema.json, fetched relative to the page.
export const ROBOTS = ["bittle", "nybble", "quaddle"];
const DIR = "../contract";

export async function fetchContract(robot, fetchText) {
  const [prompt, schema, data] = await Promise.all(
    [`${robot}.prompt.txt`, `${robot}.schema.json`, `${robot}.json`].map((f) => fetchText(`${DIR}/${f}`)));
  return { robot, prompt, pattern: JSON.parse(schema).items.pattern, codes: JSON.parse(data).codes };
}

// {robot: [model, blePrefix]}, for robotFromReply and the Bluetooth name filters.
export async function loadRegistry(fetchText) {
  return Object.fromEntries(await Promise.all(ROBOTS.map(async (r) => {
    const d = JSON.parse(await fetchText(`${DIR}/${r}.json`));
    return [r, [d.model, d.ble_prefix]];
  })));
}
```

- [ ] **Step 5: Write `web/gemma.js`**

```js
// Gemma 4 on the page (LiteRT-LM web): load the model once, prefill the robot's system prompt once, and answer each
// request on a clone of that prefilled conversation (~2 s instead of ~9 s; docs/superpowers/plans/2026-10-23-web-prefill-reuse.md).
import { parse } from "./parse.js";
import { fetchContract } from "./contracts.js";

export const textOf = (m) => typeof m.content === "string" ? m.content
  : (m.content ?? []).filter((p) => p.type === "text").map((p) => p.text).join("");

const since = (t) => ((performance.now() - t) / 1000).toFixed(1);

export class Gemma {
  #base = null;
  #prev = null;

  // deps: { Engine, SamplerType } from ./litert.js, injected so tests can use fakes.
  constructor(deps, engine, fetchText, log) {
    this.deps = deps;
    this.engine = engine;
    this.fetchText = fetchText;
    this.log = log;
  }

  static async load(deps, model, { fetchText, log = () => {} }) {
    const t = performance.now();
    const engine = await deps.Engine.create({ model, mainExecutorSettings: { maxNumTokens: 2048 } });
    log(`model loaded in ${since(t)}s`);
    return new Gemma(deps, engine, fetchText, log);
  }

  // Load `robot`'s contract and prefill a new conversation with its system prompt. The old base and its last clone
  // are left alone: deleting clones out of order broke base.clone() in 0.18.0, and robot switches are rare.
  async setRobot(robot) {
    const c = await fetchContract(robot, this.fetchText);
    const t = performance.now();
    this.#base = await this.engine.createConversation({
      preface: { messages: [{ role: "system", content: c.prompt }], extra_context: { enable_thinking: false } },
      sessionConfig: { samplerParams: { type: this.deps.SamplerType.GREEDY }, maxOutputTokens: 128 },
      prefillPrefaceOnInit: true,
    });
    this.#prev = null;
    Object.assign(this, { robot, prompt: c.prompt, pattern: c.pattern, codes: c.codes });
    this.log(`system prompt prefilled in ${since(t)}s (${robot})`);
  }

  get contract() {
    return { codes: this.codes, pattern: this.pattern };
  }

  // In 0.18.0, deleting a clone before the next base.clone() breaks it ("Dependency task 1 is invalid"), so the
  // previous clone is deleted only after the new one exists.
  async ask(text) {
    const t = performance.now();
    const conv = await this.#base.clone();
    if (this.#prev) await this.#prev.delete();
    this.#prev = conv;
    const out = textOf(await conv.sendMessage(text)).trim();
    return { out, secs: (performance.now() - t) / 1000, ...parse(this.pattern, out) };
  }

  async close() {
    await this.engine.delete();
  }
}
```

- [ ] **Step 6: Run the tests**

Run: `node --test web/`
Expected: 31 pass (25 + 6).

- [ ] **Step 7: Commit**

```bash
git add web/litert.js web/contracts.js web/gemma.js web/gemma.test.mjs
git commit -m "feat(web): Gemma, contract and LiteRT modules shared by the pages"
```

### Task 2: `model_store.js` (OPFS copy of the model)

**Files:**
- Create: `web/model_store.js`
- Test: `web/model_store.test.mjs`

- [ ] **Step 1: Write the failing tests `web/model_store.test.mjs`**

```js
// The model copy kept in the origin private file system, against a fake directory with OPFS's commit-on-close.
import { test } from "node:test";
import assert from "node:assert/strict";
import { saveModel, loadModel, clearModel } from "./model_store.js";

function fakeRoot() {
  const files = new Map();  // name -> committed bytes
  const notFound = () => Object.assign(new Error(`not found`), { name: "NotFoundError" });
  return {
    files,
    async getFileHandle(name, { create = false } = {}) {
      if (!files.has(name)) {
        if (!create) throw notFound();
        files.set(name, new Uint8Array());
      }
      return {
        async getFile() { return new File([files.get(name)], name); },
        async createWritable() {
          const chunks = [];
          return new WritableStream({  // like OPFS: data appears in the file only when the stream closes
            write(c) { chunks.push(new Uint8Array(c)); },
            close() { files.set(name, new Uint8Array(Buffer.concat(chunks))); },
          });
        },
      };
    },
    async removeEntry(name) { if (!files.delete(name)) throw notFound(); },
  };
}

const bytes = (f) => f.arrayBuffer().then((b) => [...new Uint8Array(b)]);

test("save then load gives back the same bytes and name", async () => {
  const root = fakeRoot();
  await saveModel(new File([new Uint8Array([1, 2, 3, 4])], "gemma.litertlm"), root);
  const m = await loadModel(root);
  assert.equal(m.name, "gemma.litertlm");
  assert.deepEqual(await bytes(m.file), [1, 2, 3, 4]);
});

test("load with nothing saved returns null", async () => {
  assert.equal(await loadModel(fakeRoot()), null);
});

test("clear removes the copy, and clearing twice is fine", async () => {
  const root = fakeRoot();
  await saveModel(new File([new Uint8Array([1])], "m.litertlm"), root);
  await clearModel(root);
  await clearModel(root);
  assert.equal(await loadModel(root), null);
  assert.equal(root.files.size, 0);
});

test("a copy that fails midway rejects and leaves nothing behind", async () => {
  const root = fakeRoot();
  const broken = {
    name: "m.litertlm", size: 10,
    stream: () => new ReadableStream({ start(c) { c.enqueue(new Uint8Array([1, 2])); c.error(new Error("disk full")); } }),
  };
  await assert.rejects(saveModel(broken, root), /disk full/);
  assert.equal(await loadModel(root), null);
  assert.equal(root.files.size, 0);
});

test("data without its record, or of the wrong size, is not trusted", async () => {
  const root = fakeRoot();
  await saveModel(new File([new Uint8Array([1, 2, 3])], "m.litertlm"), root);
  root.files.set("model.litertlm", new Uint8Array([1]));  // truncated
  assert.equal(await loadModel(root), null);
  root.files.delete("model.json");  // e.g. the tab was killed mid-copy
  assert.equal(await loadModel(root), null);
});
```

- [ ] **Step 2: Run them to make sure they fail**

Run: `node --test web/`
Expected: FAIL, `Cannot find module .../web/model_store.js`.

- [ ] **Step 3: Write `web/model_store.js`**

```js
// Keep one copy of the model file in the origin private file system (OPFS), so later visits load it without a picker.
// root: navigator.storage.getDirectory(), injected so tests can fake it. The small record is written only after the
// copy completes, so a copy cut short (error, tab killed) is never loaded.
const DATA = "model.litertlm";
const RECORD = "model.json";

export async function saveModel(file, root) {
  await clearModel(root);
  try {
    await file.stream().pipeTo(await (await root.getFileHandle(DATA, { create: true })).createWritable());
  } catch (e) {
    await clearModel(root);
    throw e;
  }
  const record = JSON.stringify({ name: file.name, size: file.size });
  await new Blob([record]).stream().pipeTo(await (await root.getFileHandle(RECORD, { create: true })).createWritable());
}

// Returns { file, name }, or null when there is no complete copy.
export async function loadModel(root) {
  try {
    const record = JSON.parse(await (await (await root.getFileHandle(RECORD)).getFile()).text());
    const file = await (await root.getFileHandle(DATA)).getFile();
    return file.size === record.size ? { file, name: record.name } : null;
  } catch {
    return null;  // nothing saved, or unreadable
  }
}

export async function clearModel(root) {
  for (const name of [RECORD, DATA]) await root.removeEntry(name).catch(() => {});
}
```

- [ ] **Step 4: Run the tests**

Run: `node --test web/`
Expected: 36 pass (31 + 5).

- [ ] **Step 5: Commit**

```bash
git add web/model_store.js web/model_store.test.mjs
git commit -m "feat(web): keep the model in OPFS between visits"
```

### Task 3: `runner.run` `onSent`, `driver.js`, `connectRobot`

**Files:**
- Modify: `web/runner.js` (in `run`), `web/runner.test.mjs` (one test), `web/ble.js` (append `connectRobot`)
- Create: `web/driver.js`
- Test: `web/driver.test.mjs`

- [ ] **Step 1: Add the failing `onSent` test** to the end of `web/runner.test.mjs`:

```js
test("onSent sees each command and the page's STOP after a turn, with the robot's reply", async () => {
  const seen = [];
  await run(B, ["kwkL"], fakeLink(), { ...quiet, onSent: (c, r) => seen.push([c, r]) });
  assert.deepEqual(seen, [["kwkL", "k"], [STOP, "k"]]);
});
```

- [ ] **Step 2: Write the failing tests `web/driver.test.mjs`**

```js
// Driver: the robot link plus one plan at a time, with Stop. Uses the real runner and contracts.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { Driver } from "./driver.js";
import { STOP } from "./runner.js";

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url)));
const B = { codes: read("../contract/bittle.json").codes, pattern: read("../contract/bittle.schema.json").items.pattern };

// Records sends; commands in `block` wait until the run is aborted; commands in `fail` throw.
function fakeLink({ block = [], fail = [] } = {}) {
  const sent = [];
  return {
    sent,
    async send(command, timeout, { signal } = {}) {
      sent.push(command);
      if (fail.includes(command)) throw new Error(`timeout on ${command}`);
      if (block.includes(command)) {
        return new Promise((_, reject) => signal.addEventListener("abort", () => reject(signal.reason), { once: true }));
      }
      return "k";
    },
  };
}
const driver = (link) => Object.assign(new Driver(() => {}), { link });

test("run sends the plan and resolves done", async () => {
  const d = driver(fakeLink());
  assert.equal(await d.run(B, ["kwkF", "ksit"]), "done");
  assert.deepEqual(d.link.sent, ["kwkF 3", "ksit"]);
  assert.equal(d.busy, false);
});

test("stop during a run resolves stopped and sends STOP", async () => {
  const d = driver(fakeLink({ block: ["kwkF 10"] }));
  const running = d.run(B, ["kwkF 10", "ksit"]);
  assert.equal(d.busy, true);
  await d.stop("STOP button");
  assert.equal(await running, "stopped");
  assert.deepEqual(d.link.sent, ["kwkF 10", STOP]);
  assert.equal(d.busy, false);
});

test("stop when idle sends STOP directly; stopIfRunning when idle sends nothing", async () => {
  const d = driver(fakeLink());
  d.stopIfRunning("page hidden");
  assert.deepEqual(d.link.sent, []);
  await d.stop("STOP button");
  assert.deepEqual(d.link.sent, [STOP]);
});

test("without a link, stop does nothing and run is refused", async () => {
  const d = driver(null);
  await d.stop("STOP button");
  await assert.rejects(d.run(B, ["ksit"]), /no robot connected/);
});

test("a second run while one is running is refused", async () => {
  const d = driver(fakeLink({ block: ["kwkF 10"] }));
  const first = d.run(B, ["kwkF 10"]);
  await assert.rejects(d.run(B, ["ksit"]), /already running/);
  await d.stop("STOP button");
  assert.equal(await first, "stopped");
});

test("a robot error rejects, after the runner's STOP", async () => {
  const d = driver(fakeLink({ fail: ["ksit"] }));
  await assert.rejects(d.run(B, ["ksit"]), /timeout on ksit/);
  assert.deepEqual(d.link.sent, ["ksit", STOP]);
  assert.equal(d.busy, false);
});
```

- [ ] **Step 3: Run them to make sure they fail**

Run: `node --test web/`
Expected: FAIL. `driver.test.mjs` fails with `Cannot find module .../web/driver.js`. The `onSent` test fails because `seen` stays `[]`.

- [ ] **Step 4: Add `onSent` to `run` in `web/runner.js`**

Change the signature line:

```js
export async function run(contract, commands, link, { turnSeconds = TURN_SECONDS, sleep: wait = sleep, log = console.log, signal, onSent } = {}) {
```

In the loop, after `log(`  sent ${command.padEnd(10)} robot: ${replies.at(-1)}`);` add:

```js
      onSent?.(command, replies.at(-1));
```

After `log(`  sent ${STOP.padEnd(10)} robot: ${replies.at(-1)}`);` (inside `if (timed)`) add:

```js
        onSent?.(STOP, replies.at(-1));
```

- [ ] **Step 5: Write `web/driver.js`**

```js
// The robot link plus one plan at a time, with Stop. A Stop the user asked for is not an error.
import { run, STOP, CMD_TIMEOUT_S } from "./runner.js";

export class Driver {
  link = null;
  #running = null;

  constructor(log = console.log) {
    this.log = log;
  }

  get busy() {
    return this.#running !== null;
  }

  // Resolves "done" or "stopped". Rejects on a robot error; runner.run has already sent STOP by then.
  async run(contract, commands, opts = {}) {
    if (!this.link) throw new Error("no robot connected");
    if (this.#running) throw new Error("the robot is already running a plan");
    const running = (this.#running = new AbortController());
    try {
      await run(contract, commands, this.link, { log: this.log, ...opts, signal: running.signal });
      return "done";
    } catch (e) {
      if (running.signal.aborted) return "stopped";
      throw e;
    } finally {
      this.#running = null;
    }
  }

  // Abort a running plan (runner.run sends STOP on the way out), else send STOP directly.
  async stop(why) {
    if (this.#running) {
      this.log(`stop: ${why}`);
      this.#running.abort(new Error(why));
      return;
    }
    if (!this.link) return;
    try {
      this.log(`  sent ${STOP} robot: ${await this.link.send(STOP, CMD_TIMEOUT_S)}`);
    } catch (e) {
      this.log(`  STOP FAILED: ${e} - switch the robot off`);
    }
  }

  // For page-hide: a hidden tab may lose the Bluetooth link, and a timed turn would then never get its STOP.
  stopIfRunning(why) {
    if (this.#running) this.stop(why);
  }
}
```

- [ ] **Step 6: Append `connectRobot` to `web/ble.js`**

```js
// Connect over Web Bluetooth and identify the robot from its '?' reply. Must be called from a user tap.
// registry: {robot: [model, blePrefix]} (contracts.js loadRegistry). Returns { link, name, reply, robot }.
export async function connectRobot(registry, log = console.log) {
  const c = await connectWebBluetooth([...Object.values(registry).map(([, prefix]) => prefix), "petoi"], log);
  const robot = robotFromReply(c.reply, registry);
  if (!robot) {
    c.link.close();
    throw new Error(`not a robot this page knows: '?' replied ${JSON.stringify(c.reply)}`);
  }
  return { ...c, robot };
}
```

- [ ] **Step 7: Run the tests**

Run: `node --test web/`
Expected: 43 pass (36 + 1 runner + 6 driver).

- [ ] **Step 8: Commit**

```bash
git add web/runner.js web/runner.test.mjs web/driver.js web/driver.test.mjs web/ble.js
git commit -m "feat(web): Driver (link, one plan at a time, Stop), runner onSent, connectRobot"
```

### Task 4: Rewire the test page onto the modules

**Files:**
- Modify: `web/index.html` (replace the whole `<script type="module">…</script>` block; the HTML above it stays)

- [ ] **Step 1: Replace the module script** with:

```html
<script type="module">
import { Engine, SamplerType } from "./litert.js";
import { parse } from "./parse.js";
import { Gemma, textOf } from "./gemma.js";
import { loadRegistry } from "./contracts.js";
import { connectRobot } from "./ble.js";
import { Driver } from "./driver.js";

const $ = (id) => document.getElementById(id);
const log = (s) => { $("log").textContent += s + "\n"; console.log(s); };
const fetchText = async (p) => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.text(); };
$("env").textContent = `WebGPU: ${"gpu" in navigator ? "yes" : "NO"} | ${navigator.userAgent}`;

let gemma = null;
const driver = new Driver(log);
// Fetched at page start: requestDevice() needs the user's tap, so connect() must not wait on the network first.
const registryReady = loadRegistry(fetchText);

async function connect() {
  const t = performance.now();
  const c = await connectRobot(await registryReady, log);
  log(`connected to ${c.name} in ${((performance.now() - t) / 1000).toFixed(1)}s: ${c.reply} -> ${c.robot}`);
  driver.link = c.link;
  c.link.device.addEventListener("gattserverdisconnected", () => { log("robot disconnected"); driver.link = null; });
  if (c.robot !== $("robot").value) {
    $("robot").value = c.robot;
    if (gemma) await gemma.setRobot(c.robot);
  }
}

async function load() {
  const model = $("file").files[0] ?? $("url").value;
  log(`loading ${model.name ?? model} ...`);
  gemma = await Gemma.load({ Engine, SamplerType }, model, { fetchText, log });
  await gemma.setRobot($("robot").value);
  $("eval").disabled = $("ask").disabled = false;
}

// Dev hook for web/prefill_experiments.js and hardware checks over CDP / chrome://inspect.
window.__test = { get engine() { return gemma?.engine; }, get prompt() { return gemma?.prompt; },
                  get pattern() { return gemma?.pattern; }, get link() { return driver.link; },
                  parse, textOf, SamplerType };

async function runEval() {
  const cases = JSON.parse(await fetchText("../eval/cases.json"));
  let passed = 0; const times = [];
  for (const [text, acceptable] of cases) {
    const r = await gemma.ask(text);
    times.push(r.secs);
    const ok = r.error === null && acceptable.some((a) => JSON.stringify(a) === JSON.stringify(r.commands));
    passed += ok;
    log(`${r.secs.toFixed(1)}s | ${ok ? "PASS" : "FAIL"} | ${JSON.stringify(text)} -> ${r.out}` +
        (ok ? "" : `  (${r.error ?? "want " + JSON.stringify(acceptable)})`));
  }
  const avg = times.reduce((a, b) => a + b, 0) / times.length;
  log(`\n${passed}/${cases.length} passed | latency avg ${avg.toFixed(1)}s, max ${Math.max(...times).toFixed(1)}s`);
}

const guard = (fn) => async () => { try { await fn(); } catch (e) { log(`ERROR: ${e?.stack ?? e}`); } };
$("load").onclick = guard(load);
$("connect").onclick = guard(connect);
$("eval").onclick = guard(async () => {  // a second run in parallel doubles every latency
  $("eval").disabled = true;
  try { await runEval(); } finally { $("eval").disabled = false; }
});
$("ask").onclick = guard(async () => {
  const r = await gemma.ask($("req").value);
  log(`${r.secs.toFixed(1)}s | ${r.out} -> ${r.error ?? JSON.stringify(r.commands)}`);
  if (!driver.link || r.error || !r.commands.length) return;  // refused or empty: the robot is untouched
  if (await driver.run(gemma.contract, r.commands) === "stopped") log("  stopped");
});
$("stop").onclick = () => driver.stop("Stop button");
document.addEventListener("visibilitychange", () => { if (document.hidden) driver.stopIfRunning("page hidden"); });
$("robot").onchange = guard(async () => { if (gemma) await gemma.setRobot($("robot").value); });
$("copy").onclick = () => navigator.clipboard.writeText($("log").textContent);
</script>
```

- [ ] **Step 2: Syntax check and the unit tests**

Run:
```bash
python3 -c "import re;t=open('web/index.html').read();open('/tmp/page.mjs','w').write(re.search(r'<script type=\"module\">(.*)</script>',t,re.S).group(1))" && node --check /tmp/page.mjs && node --test web/
```
Expected: no syntax error; 43 pass. (Use the session scratchpad instead of `/tmp` when one exists.)

- [ ] **Step 3: Regression check on the phone (needs the user once).** On the Pixel, reload `http://localhost:8000/web/`, pick `gemma-4-E2B-it-web.litertlm`, and tap **Load model**. Then, from the Mac, run the eval over CDP (or the user taps **Run eval**). Expected: 15/16, avg about 2 s, no `ERROR:`. Then **Connect robot** and Ask "sit down". Expected: `sent ksit robot: sit | k`.

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "refactor(web): test page uses the shared Gemma, contract and Driver modules"
```

### Task 5: The demo page

**Files:**
- Create: `web/demo.html`

- [ ] **Step 1: Write `web/demo.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Petoi Gemma Demo</title>
<style>
  :root { --bg: #fff; --fg: #111; --muted: #666; --card: #f2f2f2; --ok: #1a7f37; --bad: #c62828; --stop: #d32f2f; }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #111; --fg: #eee; --muted: #aaa; --card: #222; --ok: #4caf50; --bad: #ef5350; --stop: #e53935; }
  }
  * { box-sizing: border-box; }
  [hidden] { display: none !important; }
  body { margin: 0; padding: 16px; font: 16px/1.4 system-ui, sans-serif; background: var(--bg); color: var(--fg);
         display: flex; flex-direction: column; gap: 12px; min-height: 100vh; }
  h1 { font-size: 20px; margin: 0; }
  #status { color: var(--muted); font-size: 14px; }
  .row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  button { font: inherit; padding: 10px 14px; border-radius: 8px; border: 1px solid var(--muted); background: var(--card); color: var(--fg); }
  button:disabled { opacity: .4; }
  #chat { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
  .turn { background: var(--card); border-radius: 8px; padding: 8px 10px; }
  .req { font-weight: 600; }
  .line { font-family: ui-monospace, monospace; font-size: 14px; word-break: break-word; }
  .ok { color: var(--ok); }
  .bad { color: var(--bad); }
  .muted { color: var(--muted); font-size: 13px; }
  form { display: flex; gap: 8px; }
  input[type=text] { flex: 1; min-width: 0; font: inherit; padding: 10px; border-radius: 8px; border: 1px solid var(--muted); background: var(--bg); color: var(--fg); }
  #stop { width: 100%; min-height: 56px; font-size: 20px; font-weight: 700; background: var(--stop); color: #fff; border: none; }
</style>
</head>
<body>
<h1>Petoi + Gemma, on this phone</h1>
<div id="status"></div>
<div class="row">
  <label id="pick" hidden>Model file <input id="file" type="file" accept=".litertlm"></label>
  <button id="change" hidden>Change model</button>
  <button id="connect">Connect robot</button>
</div>
<div id="chat"></div>
<form id="form"><input id="req" type="text" placeholder="walk forward then sit" autocomplete="off"><button id="go" disabled>Go</button></form>
<button id="stop" disabled>STOP</button>
<script type="module">
import { Engine, SamplerType } from "./litert.js";
import { Gemma } from "./gemma.js";
import { saveModel, loadModel } from "./model_store.js";
import { loadRegistry } from "./contracts.js";
import { connectRobot } from "./ble.js";
import { Driver } from "./driver.js";

const $ = (id) => document.getElementById(id);
const fetchText = async (p) => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.text(); };
const since = (t) => ((performance.now() - t) / 1000).toFixed(1);

let gemma = null, robot = "bittle", opfs = null, turn = null;
const status = { model: "not loaded", robot: "not connected" };
const registryReady = loadRegistry(fetchText);  // ready before the Connect tap (requestDevice needs the tap)

// Robot progress goes into the current chat entry: "sent ..." lines become ✓ lines.
const driver = new Driver((s) => {
  s = s.trim();
  if (!turn || s.startsWith("sent ")) return;  // sent lines come through onSent instead
  turn.line(s.startsWith("STOP FAILED") ? `✗ ${s}` : s, s.startsWith("STOP FAILED") ? "line bad" : "muted");
});

function refresh() {
  $("status").textContent = `model: ${status.model} · robot: ${status.robot}`;
  $("go").disabled = !gemma || !driver.link || driver.busy;
  $("stop").disabled = !driver.link;
}
const setStatus = (key, value) => { status[key] = value; refresh(); };

// A chat entry: the request, then one line per event.
function newTurn(text) {
  const div = document.createElement("div");
  div.className = "turn";
  const req = document.createElement("div");
  req.className = "req";
  req.textContent = text;
  div.append(req);
  $("chat").append(div);
  div.scrollIntoView({ block: "end" });
  return {
    line(s, cls = "line") {
      const d = document.createElement("div");
      d.className = cls;
      d.textContent = s;
      div.append(d);
      d.scrollIntoView({ block: "end" });
    },
  };
}
const note = (s) => newTurn("").line(s, "muted");

// file: a picked File, or null to use the copy kept on the phone.
async function startModel(file) {
  try {
    let model = file;
    if (file) {
      setStatus("model", "keeping a copy on this phone…");
      try {
        if (!opfs) throw new Error("no private storage in this browser");
        await saveModel(file, opfs);
      } catch (e) {
        note(`Couldn't keep a copy of the model (${e.message}); you'll need to pick it again next time.`);
      }
    } else {
      const stored = opfs && await loadModel(opfs);
      if (!stored) {
        $("pick").hidden = false;
        setStatus("model", "pick the model file (gemma-4-E2B-it-web.litertlm)");
        return;
      }
      model = stored.file;
    }
    setStatus("model", "loading…");
    const t = performance.now();
    await gemma?.close();
    gemma = null;
    const g = await Gemma.load({ Engine, SamplerType }, model, { fetchText });
    await g.setRobot(robot);
    gemma = g;
    $("pick").hidden = true;
    $("change").hidden = false;
    setStatus("model", `ready (loaded in ${since(t)}s)`);
  } catch (e) {
    gemma = null;
    setStatus("model", `error: ${e.message}`);
  }
}

$("file").onchange = () => { if ($("file").files[0]) startModel($("file").files[0]); };
$("change").onclick = () => { $("pick").hidden = false; };

$("connect").onclick = async () => {
  try {
    const c = await connectRobot(await registryReady, () => {});
    driver.link = c.link;
    c.link.device.addEventListener("gattserverdisconnected", () => { driver.link = null; setStatus("robot", "disconnected"); });
    setStatus("robot", `${c.name} (${c.robot})`);
    if (c.robot !== robot) {
      robot = c.robot;
      if (gemma) {
        setStatus("model", `switching to ${robot}…`);
        await gemma.setRobot(robot);
        setStatus("model", "ready");
      }
    }
  } catch (e) {
    note(`Connect failed: ${e.message}`);
  }
};

$("form").onsubmit = async (ev) => {
  ev.preventDefault();
  const text = $("req").value.trim();
  if (!text || $("go").disabled) return;
  $("req").value = "";
  turn = newTurn(text);
  const t = performance.now();
  $("go").disabled = true;
  try {
    const r = await gemma.ask(text);
    if (r.error) return turn.line(`✗ not allowed, robot untouched (${r.error})`, "line bad");
    if (!r.commands.length) return turn.line("nothing to do", "muted");
    turn.line(`Gemma (${r.secs.toFixed(1)}s): ${r.commands.join(", ")}`, "muted");
    const outcome = driver.run(gemma.contract, r.commands, { onSent: (c, reply) => turn.line(`✓ ${c} → ${reply}`, "line ok") });
    refresh();
    if (await outcome === "stopped") turn.line("stopped", "line bad");
  } catch (e) {
    turn.line(`✗ ${e.message}`, "line bad");
  } finally {
    turn.line(`total ${since(t)}s`, "muted");
    refresh();
  }
};

$("stop").onclick = () => driver.stop("STOP button");
document.addEventListener("visibilitychange", () => { if (document.hidden) driver.stopIfRunning("page hidden"); });

refresh();
try { opfs = await navigator.storage.getDirectory(); } catch { opfs = null; }
startModel(null);
</script>
</body>
</html>
```

- [ ] **Step 2: Syntax check**

Run (with `web/demo.html`), the same extraction as Task 4 Step 2, then `node --check`.
Expected: no syntax error. `node --test web/` → 43 pass.

- [ ] **Step 3: Commit**

```bash
git add web/demo.html
git commit -m "feat(web): Bluetooth demo page"
```

### Task 6: Hardware checks (needs the user, the Pixel and the Bittle X)

Serve the repo (`python3 -m http.server 8000` from the worktree root), run `adb reverse tcp:8000 tcp:8000`, and open `http://localhost:8000/web/demo.html`. Record each result.

- [ ] **Step 1: First visit.** The status asks for the model file, and the picker appears. Pick `gemma-4-E2B-it-web.litertlm`. Record how long "keeping a copy…" takes and how long the load takes, and confirm the status reads `ready`. If the copy fails, record the message (the fallback is expected to load the picked file anyway).
- [ ] **Step 2: Reload.** The model loads with **no picker**. Record the load time.
- [ ] **Step 3: Connect robot,** then pick the robot. The status shows `Bittle0D_… (bittle)`, and **Go** and **STOP** become enabled.
- [ ] **Step 4:** "stand up then sit" → `Gemma (…s): kbalance, ksit`, then ✓ lines and a total.
- [ ] **Step 5:** "walk forward 10 steps", then tap **STOP** mid-walk. Expected: `stop: STOP button`, then `stopped`, and the robot stands still (the user confirms).
- [ ] **Step 6:** "make me a sandwich" → `nothing to do`. "do a backflip" is **not** sent unless the user explicitly asks for it during this step.
- [ ] **Step 7:** "walk forward 10 steps", then switch apps mid-walk. Expected: the robot stops (the user confirms), and the entry shows `stop: page hidden` / `stopped`.
- [ ] **Step 8:** If a step fails, fix it test-first where the logic lives in a tested module, then commit (`fix(web): …`).

### Task 7: Record results

**Files:**
- Modify: `README.md` (the "Android (web, experimental)" line)
- Modify: this plan (add `## Results`)

- [ ] **Step 1:** Add the demo to the README's Android line. Replace "and runs the eval." with "and runs the eval; `web/demo.html` is a cleaner demo (model kept on the phone after the first pick, chat history, big STOP)."
- [ ] **Step 2:** Add `## Results` to this plan: the Task 6 outcomes with times, and any deviations.
- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/plans/2026-10-23-bluetooth-demo.md
git commit -m "docs: Bluetooth demo page results"
```
