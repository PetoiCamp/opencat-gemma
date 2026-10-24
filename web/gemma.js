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
