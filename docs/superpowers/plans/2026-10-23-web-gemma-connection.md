# Web Gemma Connection Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove a web page in Chrome on a Pixel 7 Pro can load gemma-4-E4B-it on-device and turn requests into allowlisted robot commands, and measure accuracy and latency against `eval/cases.json`.

**Architecture:** One static page (`web/index.html`) loads `@litert-lm/core` from jsDelivr (pinned), loads the model (Hugging Face URL or a local file picked on the phone), and runs every eval case through Gemma with the checked-in `contract/<robot>.prompt.txt` as the system prompt. Replies go through `web/parse.js`, a JS port of `opencat_gemma/gemma.py:parse`. A shared fixture (`web/parse_cases.json`) is run through BOTH the Python and the JS parser, so the browser allowlist can't drift from the laptop one. The page is served from the Mac with `python3 -m http.server` and reached on the phone through `adb reverse`, so it is `http://localhost` (a secure context, which WebGPU needs).

**Tech Stack:** `@litert-lm/core@0.18.1` (WebGPU), plain ES modules (no build step), `node --test` for the JS parser, Python `unittest` for parity.

**Out of scope:** the robot link (Web Bluetooth / Wi-Fi WebSocket), the native Kotlin app, constrained decoding via tool calling. Those get their own plans once this test reports numbers.

**Facts this plan relies on (checked 2026-10-23):**
- npm `@litert-lm/core` 0.18.1 is the latest non-nightly release. Its types (`dist/*.d.ts`): `Engine.create({model, mainExecutorSettings: {maxNumTokens}})`, `engine.createConversation({preface: {messages, extra_context}, sessionConfig: {samplerParams: {type}, maxOutputTokens}, prefillPrefaceOnInit})`, `conversation.clone()`, `conversation.sendMessage(text) -> Message` with `content: string | ContentPart[]`, `conversation.delete()`, `SamplerType.GREEDY = 3`.
- `enable_thinking` in `preface.extra_context` is from the web docs, not the type definitions.
- HF repo `litert-community/gemma-4-E4B-it-litert-lm` (not gated) has `gemma-4-E4B-it-gpu.litertlm`, 2.97 GB. The resolve URL returns `access-control-allow-origin: *`.

**Not verified (this test exists to find out):** that WebGPU works in the Pixel 7 Pro's Chrome, that a 2.97 GB model fits in a mobile tab, and how often E4B returns clean JSON without schema enforcement.

---

## File structure

| File | Responsibility |
|---|---|
| `web/parse.js` | `parse(pattern, out) -> {commands, error}`: JS port of `gemma.py:parse`. No DOM, so `node` can test it. |
| `web/parse_cases.json` | Shared fixture: raw model output → expected commands, or an error kind. |
| `web/parse.test.mjs` | `node --test`: the fixture, plus every `eval/cases.json` answer round-tripping through `parse`. |
| `tests/test_web_parity.py` | Runs the same fixture through the real Python `gemma.parse`. |
| `web/index.html` | The test page: load the model, run the eval, show and copy the results. |
| `README.md` | Replace the "Android (LiteRT + BLE): coming" line with how to run the web test. |

---

### Task 1: Shared parse fixture + Python parity test

**Files:**
- Create: `web/parse_cases.json`
- Test: `tests/test_web_parity.py`

- [ ] **Step 1: Write the fixture**

`error` is the error *kind*: the start of the Python error string. `null` means the reply is accepted.

```json
[
  {"raw": "[\"kwkF\",\"ksit\"]", "commands": ["kwkF", "ksit"], "error": null},
  {"raw": "[\"kwkF 5\", \"krest\"]", "commands": ["kwkF 5", "krest"], "error": null},
  {"raw": "{\"commands\": [\"khi\"]}", "commands": ["khi"], "error": null},
  {"raw": "  []  ", "commands": [], "error": null},
  {"raw": "[\"kwkF 21\"]", "commands": null, "error": "not allowed"},
  {"raw": "[\"kwkF 05\"]", "commands": null, "error": "not allowed"},
  {"raw": "[\"kwkL 90\"]", "commands": null, "error": "not allowed"},
  {"raw": "[\"ksit\\n\"]", "commands": null, "error": "not allowed"},
  {"raw": "[\"KSIT\"]", "commands": null, "error": "not allowed"},
  {"raw": "[\"ksit\", \"rm -rf\"]", "commands": null, "error": "not allowed"},
  {"raw": "[1]", "commands": null, "error": "not allowed"},
  {"raw": "```json\n[\"ksit\"]\n```", "commands": null, "error": "invalid JSON"},
  {"raw": "\"ksit\"", "commands": null, "error": "not a list"},
  {"raw": "null", "commands": null, "error": "not a list"},
  {"raw": "{\"a\": 1}", "commands": null, "error": "not a list"}
]
```

- [ ] **Step 2: Write the Python parity test**

```python
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
```

- [ ] **Step 3: Run it**

Run: `.venv/bin/python -m unittest tests.test_web_parity -v`
Expected: PASS. This pins down the existing Python behaviour. If a case fails, the fixture is wrong about Python, not the other way round: fix the fixture and note why.

- [ ] **Step 4: Commit**

```bash
git add web/parse_cases.json tests/test_web_parity.py
git commit -m "test: shared parse fixture pinned to the Python allowlist"
```

### Task 2: JS parser (`web/parse.js`)

**Files:**
- Create: `web/parse.js`
- Test: `web/parse.test.mjs`

- [ ] **Step 1: Write the failing test**

```js
// Same fixture as tests/test_web_parity.py, so the browser allowlist matches the Python one.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { parse } from "./parse.js";

const read = (p) => JSON.parse(readFileSync(new URL(p, import.meta.url)));
const pattern = read("../contract/bittle.schema.json").items.pattern;

test("fixture matches the Python parser", () => {
  for (const c of read("./parse_cases.json")) {
    const { commands, error } = parse(pattern, c.raw);
    assert.deepEqual(commands, c.commands, c.raw);
    if (c.error === null) assert.equal(error, null, c.raw);
    else assert.ok(error?.startsWith(c.error), `${c.raw}: ${error}`);
  }
});

test("every acceptable eval answer round-trips through parse", () => {
  for (const [text, acceptable] of read("../eval/cases.json")) {
    for (const answer of acceptable) {
      assert.deepEqual(parse(pattern, JSON.stringify(answer)), { commands: answer, error: null }, text);
    }
  }
});
```

- [ ] **Step 2: Run it to make sure it fails**

Run: `node --test web/`
Expected: FAIL, `Cannot find module .../web/parse.js`.

- [ ] **Step 3: Write the implementation**

```js
// Port of opencat_gemma/gemma.py:parse. Never trust model output: the web runtime does not enforce the schema.
export function parse(pattern, out) {
  let v;
  try {
    v = JSON.parse(out);
  } catch {
    return { commands: null, error: "invalid JSON" };
  }
  if (v !== null && typeof v === "object" && !Array.isArray(v)) {
    v = Object.values(v).find(Array.isArray) ?? null;
  }
  if (!Array.isArray(v)) return { commands: null, error: "not a list" };
  const re = new RegExp(pattern);
  const bad = v.filter((c) => typeof c !== "string" || !re.test(c));
  if (bad.length) return { commands: null, error: `not allowed: ${JSON.stringify(bad)}` };
  return { commands: v, error: null };
}
```

(`pattern` is anchored `^(...)$` and the RegExp has no `m` flag, so `test` is a full match, the same as Python's `re.fullmatch`. The `"ksit\n"` fixture case checks this.)

- [ ] **Step 4: Run the tests and make sure they pass**

Run: `node --test web/ && .venv/bin/python -m unittest discover tests`
Expected: 2 node tests pass. Python: 74 tests OK (73 existing + 1 parity).

- [ ] **Step 5: Commit**

```bash
git add web/parse.js web/parse.test.mjs
git commit -m "feat(web): JS allowlist parser matching gemma.py:parse"
```

### Task 3: Test page (`web/index.html`)

**Files:**
- Create: `web/index.html`

No automated test: this needs WebGPU and a 3 GB model. It's checked by hand in Tasks 4 and 5.

- [ ] **Step 1: Write the page**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gemma web test</title>
<style>
  body { font: 15px/1.4 system-ui, sans-serif; margin: 16px; background: #fff; color: #111; }
  input[type=text] { width: 100%; box-sizing: border-box; }
  button, select, input { font: inherit; margin: 4px 0; }
  pre { white-space: pre-wrap; word-break: break-word; background: #f3f3f3; padding: 8px; }
  @media (prefers-color-scheme: dark) { body { background: #111; color: #eee; } pre { background: #222; } }
</style>
</head>
<body>
<h1>Gemma web test</h1>
<p id="env"></p>
<label>Robot <select id="robot"><option>bittle</option><option>nybble</option></select></label>
<p>Model: URL <input id="url" type="text"
  value="https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it-gpu.litertlm"><br>
  or file <input id="file" type="file" accept=".litertlm"></p>
<button id="load">Load model</button>
<button id="eval" disabled>Run eval</button>
<p><input id="req" type="text" placeholder="walk forward then sit"> <button id="ask" disabled>Ask</button></p>
<button id="copy">Copy log</button>
<pre id="log"></pre>
<script type="module">
import { Engine, SamplerType } from "https://cdn.jsdelivr.net/npm/@litert-lm/core@0.18.1/+esm";
import { parse } from "./parse.js";

const $ = (id) => document.getElementById(id);
const log = (s) => { $("log").textContent += s + "\n"; console.log(s); };
const fetchText = async (p) => { const r = await fetch(p); if (!r.ok) throw new Error(`${p}: ${r.status}`); return r.text(); };
$("env").textContent = `WebGPU: ${"gpu" in navigator ? "yes" : "NO"} | ${navigator.userAgent}`;

let engine, base, pattern;

async function load() {
  const robot = $("robot").value;
  const prompt = await fetchText(`../contract/${robot}.prompt.txt`);
  pattern = JSON.parse(await fetchText(`../contract/${robot}.schema.json`)).items.pattern;
  const model = $("file").files[0] ?? $("url").value;
  log(`loading ${model.name ?? model} ...`);
  let t = performance.now();
  engine = await Engine.create({ model, mainExecutorSettings: { maxNumTokens: 2048 } });
  log(`model loaded in ${((performance.now() - t) / 1000).toFixed(1)}s`);
  t = performance.now();
  // One conversation with the system prompt prefilled; each request runs on a clone so they don't see each other.
  base = await engine.createConversation({
    preface: { messages: [{ role: "system", content: prompt }], extra_context: { enable_thinking: false } },
    sessionConfig: { samplerParams: { type: SamplerType.GREEDY }, maxOutputTokens: 128 },
    prefillPrefaceOnInit: true,
  });
  log(`system prompt prefilled in ${((performance.now() - t) / 1000).toFixed(1)}s (${robot})`);
  $("eval").disabled = $("ask").disabled = false;
}

const textOf = (m) => typeof m.content === "string" ? m.content
  : (m.content ?? []).filter((p) => p.type === "text").map((p) => p.text).join("");

async function ask(text) {
  const conv = await base.clone();
  const t = performance.now();
  try {
    const out = textOf(await conv.sendMessage(text)).trim();
    return { out, secs: (performance.now() - t) / 1000, ...parse(pattern, out) };
  } finally {
    await conv.delete();
  }
}

async function runEval() {
  const cases = JSON.parse(await fetchText("../eval/cases.json"));
  let passed = 0; const times = [];
  for (const [text, acceptable] of cases) {
    const r = await ask(text);
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
$("eval").onclick = guard(runEval);
$("ask").onclick = guard(async () => {
  const r = await ask($("req").value);
  log(`${r.secs.toFixed(1)}s | ${r.out} -> ${r.error ?? JSON.stringify(r.commands)}`);
});
$("copy").onclick = () => navigator.clipboard.writeText($("log").textContent);
</script>
</body>
</html>
```

The output format matches `eval/run_eval.py`, so the laptop and phone runs can be compared line by line.

- [ ] **Step 2: Check it serves and the module graph resolves**

Run (from the worktree root): `python3 -m http.server 8000 --bind 127.0.0.1` (in the background), then
`curl -sf http://localhost:8000/web/index.html >/dev/null && curl -sf http://localhost:8000/web/parse.js >/dev/null && curl -sf http://localhost:8000/contract/bittle.prompt.txt >/dev/null && curl -sfI "https://cdn.jsdelivr.net/npm/@litert-lm/core@0.18.1/+esm" | head -1`
Expected: each fetch succeeds and the last line is `HTTP/2 200`.

- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat(web): Gemma connection test page (LiteRT-LM WebGPU + eval)"
```

### Task 4: Desktop smoke test (Mac Chrome)

Catches page and API bugs before involving the phone.

- [ ] **Step 1:** With the server from Task 3 running, open `http://localhost:8000/web/` in Chrome on the Mac. Check `WebGPU: yes`.
- [ ] **Step 2:** Click **Load model** with the default URL. It downloads 2.97 GB. Expected: `model loaded in …s`, then `system prompt prefilled in …s`. On `ERROR:`, fix the page against the 0.18.1 types (most likely place: `enable_thinking`. If it's rejected, drop `extra_context` and record that) and repeat.
- [ ] **Step 3:** Click **Run eval**. Expected: 16 result lines and a summary line. Copy the log into the results section of this plan (Task 6).
- [ ] **Step 4:** If the page changed, commit with `git commit -am "fix(web): <what changed>"`.

### Task 5: Pixel 7 Pro test (needs the user)

- [ ] **Step 1:** The user turns on USB debugging and plugs in the phone. Run `adb devices`. Expected: one device listed as `device` (not `unauthorized`).
- [ ] **Step 2:** `adb reverse tcp:8000 tcp:8000`
- [ ] **Step 3:** Optional, to avoid a 3 GB download over phone Wi-Fi each time: `curl -L -o ~/Downloads/gemma-4-E4B-it-gpu.litertlm "https://huggingface.co/litert-community/gemma-4-E4B-it-litert-lm/resolve/main/gemma-4-E4B-it-gpu.litertlm"`, then `adb push ~/Downloads/gemma-4-E4B-it-gpu.litertlm /sdcard/Download/`. Pick it with the page's file input.
- [ ] **Step 4:** On the phone, open `http://localhost:8000/web/` in Chrome. Record the `WebGPU:` line and the Chrome version.
- [ ] **Step 5:** **Load model**, then **Run eval**. Record load time, prefill time, every result line, and the summary. Also record failures: tab crash ("Aw, Snap"), out-of-memory, or a WebGPU error. These are results too.
- [ ] **Step 6 (optional, to read the console from the Mac):** with the phone attached, open `chrome://inspect` in Mac Chrome and inspect the tab.

### Task 6: Record results and decide the next step

**Files:**
- Modify: `docs/superpowers/plans/2026-10-23-web-gemma-connection.md` (this file: add `## Results`)
- Modify: `README.md` (the "Android (LiteRT + BLE): coming" line under "Build your own")

- [ ] **Step 1:** Add a `## Results` section to this file: device, Chrome version, model file, load and prefill time, pass count, avg and max latency for Mac and Pixel, and the full failure lines. Next to them, put the laptop Ollama E2B result from `eval/run_eval.py` if it's at hand; otherwise say it wasn't run.
- [ ] **Step 2:** Replace the README line with:

```markdown
- **Android (web, experimental):** `web/index.html` runs Gemma 4 E4B in Chrome on the phone (LiteRT-LM, WebGPU) and runs the eval. Serve the repo with `python3 -m http.server 8000`, run `adb reverse tcp:8000 tcp:8000`, then open `http://localhost:8000/web/` on the phone. No robot connection yet.
```

- [ ] **Step 3:** Write down the next decision from the results:
  - JSON failures common → plan constrained output via `enableConstrainedDecoding` + a tool whose parameter is an `enum` of every allowed command string.
  - Too slow or crashes → try `gemma-4-E2B-it-gpu.litertlm` on the same page, or fall back to the native Kotlin app.
  - Works → plan the robot link (Web Bluetooth first).
- [ ] **Step 4:** Commit

```bash
git add README.md docs/superpowers/plans/2026-10-23-web-gemma-connection.md
git commit -m "docs: web Gemma connection test results"
```

---

## Results (2026-10-23)

**Device:** Pixel 7 Pro, Android 17, Chrome 156.0.8078.47, `WebGPU: yes`. Page served from the Mac over `adb reverse`; model picked from the phone's Downloads with the file input.

| | Phone (web) | Laptop (Ollama) |
|---|---|---|
| Model | `gemma-4-E2B-it-web.litertlm` (2.0 GB) | `gemma4:e2b-it-qat` |
| Runtime | `@litert-lm/core` 0.18.0, WebGPU | Ollama, JSON schema enforced |
| Model load | 6.7-8.8 s | n/a |
| Eval | **14/16** | **15/16** |
| Latency avg / max | **8.8 s / 10.6 s** | **0.9 s / 5.3 s** |

Phone failures (same answers in every run; greedy sampling):
- `"go back a bit and lie down" -> ["kbk 1","krest"]`: allowed, but the eval wants `kbk` with no count.
- `"stand up and walk forward for 5 steps, then turn left for 30 degrees" -> ["kbalance 5","kwkL 30"]`: **rejected by the allowlist**, so nothing would reach a robot. The laptop fails the same case differently: `["kbalance","kwkL"]` (it drops `kwkF 5` too, but the schema keeps the codes valid).

Where the phone's time goes: with the system prompt prefilled once and reused (the first `clone()` version), one request took **2.1 s**. With a fresh conversation per request it takes ~8.8 s. So about 7 s per request is re-reading the ~600-token system prompt, which matches the 7.3 s prefill measured on its own.

### Deviations from the plan
- **Model E2B, not E4B:** the user's choice. E2B is what AI Edge Gallery runs on this phone and what the laptop kit uses. E4B never got past loading, because of the next bug.
- **`@litert-lm/core` 0.18.0, not 0.18.1:** 0.18.1's JS calls WASM methods its own builds don't have (`Engine.create` fails with `getMutableMainExecutorSettings is not a function`, hidden by `m.delete is not a function` from its cleanup). Found by pausing on exceptions over CDP. 0.18.0 is the pair Google's hosted chat demo ships.
- **Fresh conversation per request, not `clone()`:** in 0.18.0 the second clone of a prefilled conversation fails with `Dependency task 1 is invalid`. The demo never clones.
- **`web/package.json`** (`{"type":"module"}`) so `node --test` doesn't warn about module type.
- **Run eval locks while running:** a double tap ran two evals at once and doubled every latency.
- Task 4 (Mac Chrome smoke test) was skipped; the phone was tested directly.

### Next decision
Accuracy is close to the laptop and the allowlist caught the bad output, so the blocker is **speed** (8.8 s vs 0.9 s). Next: reuse the prefilled system prompt without the `clone()` bug (target: ~2 s per request), e.g. clone without deleting clones, or keep one conversation and reset it. If that fails: shorten the prompt. Then the robot link (Web Bluetooth first). Constrained output (`enableConstrainedDecoding` + an `enum` tool) is optional: it would block `kbalance 5`-style codes but not dropped steps.
