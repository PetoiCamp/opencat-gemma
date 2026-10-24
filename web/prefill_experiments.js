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
