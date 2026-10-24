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

// A ticket taken before Gemma's inference: a stop (or page hide) during inference cancels the plan it produces.
test("stop between ticket and run cancels the plan; only stop's own STOP is sent", async () => {
  const d = driver(fakeLink());
  const ticket = d.ticket();
  await d.stop("STOP button");
  assert.equal(await d.run(B, ["kwkF", "ksit"], { ticket }), "stopped");
  assert.deepEqual(d.link.sent, [STOP]);
  assert.equal(d.busy, false);
});

test("stopIfRunning between ticket and run cancels the plan and sends nothing", async () => {
  const d = driver(fakeLink());
  const ticket = d.ticket();
  d.stopIfRunning("page hidden");
  assert.equal(await d.run(B, ["kwkF", "ksit"], { ticket }), "stopped");
  assert.deepEqual(d.link.sent, []);
});

test("a ticket with no stop since runs normally", async () => {
  const d = driver(fakeLink());
  const ticket = d.ticket();
  assert.equal(await d.run(B, ["kwkF", "ksit"], { ticket }), "done");
  assert.deepEqual(d.link.sent, ["kwkF 3", "ksit"]);
});
