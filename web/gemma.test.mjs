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
  const conv = (name) => ({ name,
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
