# Web Prefill Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut per-request latency on the phone from ~8.8 s to ~2-3 s by prefilling the system prompt once and reusing it, without the 0.18.0 `clone()` failure.

**Architecture:** First measure, then change the page. A small experiments module (`web/prefill_experiments.js`) runs the 16 eval cases twice under each reuse strategy against the already-loaded engine. A debug hook on `window` lets it reach that engine. The strategy that survives 32 requests with no error, and gives the same answers as the fresh-conversation baseline, goes into `ask()` in `web/index.html`.

**Tech Stack:** `@litert-lm/core` 0.18.0 (unchanged), plain ES modules. The experiments are run from the Mac over Chrome DevTools (CDP over `adb forward`), or by pasting one line into `chrome://inspect`.

**Background (from `2026-10-23-web-gemma-connection.md` results):**
- With the prompt prefilled once and cloned, one request took 2.1 s. The second `base.clone()`, made after the first clone had been used and deleted, failed with `Dependency task 1 is invalid`.
- A fresh conversation per request works, but takes ~8.8 s. About 7 s of that is prefilling the ~600-token system prompt.
- Google's demo never clones. `Conversation` has no reset method in 0.18.0 (`dist/conversation.d.ts`).

**Hypothesis under test:** deleting a clone invalidates state that later clones of the base depend on. If so, `clone_keep` and probably `clone_defer` work, and `fresh` stays the baseline.

**Success criteria for the winner:**
1. 32 requests (16 cases × 2 rounds) with no error.
2. Answers identical to `fresh`. Sampling is greedy, so reuse must not change outputs.
3. Average ≤ 3 s.

**Out of scope:** shortening the prompt (it changes accuracy, so it gets its own plan if needed), the robot link, and constrained output.

---

## File structure

| File | Responsibility |
|---|---|
| `web/index.html` | Add a debug hook `window.__test`, and later the winning strategy in `ask()`. |
| `web/prefill_experiments.js` | Strategies `fresh`, `clone_keep`, `clone_defer`, plus `run(name, rounds)` returning a summary. Dev-only; the page doesn't import it. |
| `docs/superpowers/plans/2026-10-23-web-prefill-reuse.md` | This plan, plus a Results section. |
| `README.md` | Update the phone latency number. |

---

### Task 1: Debug hook + experiments module

**Files:**
- Modify: `web/index.html` (after `textOf` is defined)
- Create: `web/prefill_experiments.js`

- [ ] **Step 1: Add the debug hook to `web/index.html`**, directly after the `const textOf = ...` definition:

```js
// Dev hook for web/prefill_experiments.js (run over CDP / chrome://inspect). Getters, so it sees the loaded engine.
window.__test = { get engine() { return engine; }, get prompt() { return prompt; }, get pattern() { return pattern; },
                  parse, textOf, SamplerType };
```

- [ ] **Step 2: Create `web/prefill_experiments.js`**

```js
// Prefill-reuse experiments against the engine the page already loaded. From the DevTools console on the phone tab:
//   await (await import("./prefill_experiments.js")).run("clone_keep")
const now = () => performance.now();
const config = (T, prefill) => ({
  preface: { messages: [{ role: "system", content: T.prompt }], extra_context: { enable_thinking: false } },
  sessionConfig: { samplerParams: { type: T.SamplerType.GREEDY }, maxOutputTokens: 128 },
  prefillPrefaceOnInit: prefill,
});

// Each strategy: next() gives a conversation for one request, done(c) runs after it, end() cleans up.
const strategies = {
  async fresh(T) {
    return { next: () => T.engine.createConversation(config(T, false)), done: (c) => c.delete(), end: async () => {} };
  },
  async clone_keep(T) {  // never delete a clone until the end
    const base = await T.engine.createConversation(config(T, true));
    const kept = [];
    return {
      next: () => base.clone(),
      done: async (c) => { kept.push(c); },
      end: async () => { for (const c of kept) await c.delete(); await base.delete(); },
    };
  },
  async clone_defer(T) {  // delete the previous clone only after the next clone exists
    const base = await T.engine.createConversation(config(T, true));
    let prev = null;
    return {
      next: async () => { const c = await base.clone(); if (prev) await prev.delete(); prev = c; return c; },
      done: async () => {},
      end: async () => { if (prev) await prev.delete(); await base.delete(); },
    };
  },
};

export async function run(name, rounds = 2) {
  const T = window.__test;
  if (!T?.engine) throw new Error("load the model on the page first");
  const cases = await (await fetch("../eval/cases.json")).json();
  const t0 = now();
  const s = await strategies[name](T);
  const setup = (now() - t0) / 1000;
  const rows = [];
  let error = null;
  try {
    for (let r = 0; r < rounds; r++) {
      for (const [text, acceptable] of cases) {
        const t1 = now();
        const c = await s.next();
        try {
          const out = T.textOf(await c.sendMessage(text)).trim();
          const p = T.parse(T.pattern, out);
          const ok = p.error === null && acceptable.some((a) => JSON.stringify(a) === JSON.stringify(p.commands));
          rows.push({ out: out.replace(/\s+/g, ""), secs: (now() - t1) / 1000, ok });
        } finally {
          await s.done(c);
        }
      }
    }
  } catch (e) {
    error = String(e?.stack ?? e).slice(0, 600);
  } finally {
    await s.end().catch((e) => { error ??= String(e); });
  }
  const secs = rows.map((r) => r.secs);
  return {
    name, setup: +setup.toFixed(1), requests: rows.length, passed: rows.filter((r) => r.ok).length,
    avg: +(secs.reduce((a, b) => a + b, 0) / (secs.length || 1)).toFixed(2), max: +Math.max(0, ...secs).toFixed(2),
    error, outputs: rows.map((r) => r.out),
  };
}
```

- [ ] **Step 3: Check nothing else broke**

Run: `node --test web/ && .venv/bin/python -m unittest discover tests`
Expected: 2 node tests pass, 74 Python tests OK. The module has no node test because it needs WebGPU and a loaded model.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/prefill_experiments.js
git commit -m "feat(web): prefill-reuse experiments + debug hook"
```

### Task 2: Run the experiments on the phone

Needs the user once: reload `http://localhost:8000/web/`, pick `gemma-4-E2B-it-web.litertlm`, then **Load model**. Everything after that runs from the Mac.

- [ ] **Step 1:** Run `fresh` first, as the baseline (~5 min), then `clone_keep`, then `clone_defer`. Over CDP: `Runtime.evaluate` with `awaitPromise: true` on `(await import("./prefill_experiments.js")).run("<name>")`. Or paste the same line into the console at `chrome://inspect`.
- [ ] **Step 2:** For each run, record `setup`, `requests`, `passed`, `avg`, `max`, `error`, and whether `outputs` equals the `fresh` outputs.
- [ ] **Step 3:** If a strategy errors, the engine may be in a bad state. Reload the page, have the user load the model again, and carry on with the next strategy. A tab crash (out of memory from kept clones) counts as a result.
- [ ] **Step 4:** Choose the winner: no error over 32 requests, outputs equal to `fresh`, lowest `avg`. **If none qualifies, stop here** and report back with the options: the lower-level `Session` API (`engine.createSession` + `session.clone()`), a newer `@litert-lm/core` nightly, a shorter prompt, or the native app.

### Task 3: Put the winner in `ask()`

**Files:**
- Modify: `web/index.html` (`load()` and `ask()`)

- [ ] **Step 1: Change `load()` and `ask()`.** If `clone_keep` wins:

```js
let engine, prompt, pattern, base, kept = [];
```

At the end of `load()`, before enabling the buttons:

```js
  t = performance.now();
  base = await engine.createConversation({
    preface: { messages: [{ role: "system", content: prompt }], extra_context: { enable_thinking: false } },
    sessionConfig: { samplerParams: { type: SamplerType.GREEDY }, maxOutputTokens: 128 },
    prefillPrefaceOnInit: true,
  });
  log(`system prompt prefilled in ${((performance.now() - t) / 1000).toFixed(1)}s`);
```

And `ask()`:

```js
// Clone the prefilled conversation per request and keep the clones: in 0.18.0 deleting a clone breaks the next
// base.clone() ("Dependency task 1 is invalid"). Measured in docs/superpowers/plans/2026-10-23-web-prefill-reuse.md.
async function ask(text) {
  const t = performance.now();
  const conv = await base.clone();
  kept.push(conv);
  const out = textOf(await conv.sendMessage(text)).trim();
  return { out, secs: (performance.now() - t) / 1000, ...parse(pattern, out) };
}
```

If `clone_defer` wins, `ask()` deletes the previous clone after creating the new one instead of keeping them all. Use the same code as `strategies.clone_defer.next` in `web/prefill_experiments.js`.

- [ ] **Step 2: Verify on the phone.** Reload, load the model, then click **Run eval** twice in a row (32 requests). Expected: no `ERROR:`, 14/16 both times with the same answers as before, average ≤ 3 s.
- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "perf(web): reuse the prefilled system prompt (<strategy>)"
```

### Task 4: Record results

**Files:**
- Modify: `docs/superpowers/plans/2026-10-23-web-prefill-reuse.md` (add `## Results`)
- Modify: `README.md` (the "Android (web, experimental)" line: replace "about 9 s per request" with the measured number)

- [ ] **Step 1:** Add `## Results`: a table with one row per strategy (setup, passed/requests, avg, max, error, outputs equal to fresh), the winner, and the Run eval ×2 numbers from Task 3.
- [ ] **Step 2:** Update the README latency number.
- [ ] **Step 3: Commit**

```bash
git add README.md docs/superpowers/plans/2026-10-23-web-prefill-reuse.md
git commit -m "docs: prefill reuse results"
```

---

## Results (2026-10-23)

Pixel 7 Pro, Chrome 156, `gemma-4-E2B-it-web.litertlm`, `@litert-lm/core` 0.18.0. Each strategy ran 16 cases × 2 rounds against one loaded engine, driven over CDP.

| Strategy | Setup (prefill) | Errors | Passed | Avg / max | Answers vs `fresh` |
|---|---|---|---|---|---|
| `fresh` (previous page) | 0 s | none | 28/32 | 8.80 s / 10.72 s | baseline |
| `clone_keep` | 6.8 s | none | 30/32 | 2.00 s / 3.92 s | 1 case differs |
| `clone_defer` | 6.8 s | none | 30/32 | **1.93 s / 4.04 s** | 1 case differs (same as `clone_keep`) |

**Hypothesis confirmed:** a clone only breaks the next `base.clone()` if it was deleted *before* that clone was made. Keeping clones (`clone_keep`), or deleting the previous one after the next exists (`clone_defer`), both ran 32 requests without an error.

**The one changed answer:** `"stand up and walk forward for 5 steps, then turn left for 30 degrees"`. `fresh` gives `["kbalance 5","kwkL 30"]` (rejected by the allowlist). Both clone strategies give `["kbalance","kwkF 5","kwkL"]` (correct). Each strategy is deterministic across rounds. The likely cause (not verified) is that prefilling the prompt separately from the request changes GPU numerics enough to flip this borderline token. **Deviation:** success criterion 2 ("identical to `fresh`") was not met. The user accepted `clone_defer`, with the criterion relaxed to "no reuse errors, deterministic, accuracy not worse".

**Winner: `clone_defer`.** Fastest, and only one clone alive at a time, so memory doesn't grow with chat length.

**Page after the change** (Task 3; Run eval twice in a row on one load):

| Run | Passed | Avg / max | Errors |
|---|---|---|---|
| 1 | 15/16 | 1.9 s / 3.7 s | none |
| 2 | 15/16 | 1.8 s / 3.9 s | none |

Model load 7.1 s, plus a one-time system-prompt prefill of 7.3 s. The only remaining failure is `"go back a bit and lie down" -> ["kbk 1","krest"]` (allowed; the eval wants `kbk`). Same pass count as the laptop (Ollama, 15/16, avg 0.9 s).

Task 2 also ran from the Mac. The model file had to be picked on the phone each time: a page reload clears the file input, and loading 2 GB from a URL over the same USB link starved the DevTools connection.
