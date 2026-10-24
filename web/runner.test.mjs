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

test("onSent sees each command and the page's STOP after a turn, with the robot's reply", async () => {
  const seen = [];
  await run(B, ["kwkL"], fakeLink(), { ...quiet, onSent: (c, r) => seen.push([c, r]) });
  assert.deepEqual(seen, [["kwkL", "k"], [STOP, "k"]]);
});
