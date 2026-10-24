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
