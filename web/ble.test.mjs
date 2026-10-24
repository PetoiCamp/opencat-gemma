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
