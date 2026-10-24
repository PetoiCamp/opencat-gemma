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
