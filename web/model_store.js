// Keep one copy of the model file in the origin private file system (OPFS), so later visits load it without a picker.
// root: navigator.storage.getDirectory(), injected so tests can fake it. The small record is written only after the
// copy completes, so a copy cut short (error, tab killed) is never loaded.
const DATA = "model.litertlm";
const RECORD = "model.json";

export async function saveModel(file, root) {
  await clearModel(root);
  try {
    await file.stream().pipeTo(await (await root.getFileHandle(DATA, { create: true })).createWritable());
  } catch (e) {
    await clearModel(root);
    throw e;
  }
  const record = JSON.stringify({ name: file.name, size: file.size });
  await new Blob([record]).stream().pipeTo(await (await root.getFileHandle(RECORD, { create: true })).createWritable());
}

// Returns { file, name }, or null when there is no complete copy.
export async function loadModel(root) {
  try {
    const record = JSON.parse(await (await (await root.getFileHandle(RECORD)).getFile()).text());
    const file = await (await root.getFileHandle(DATA)).getFile();
    return file.size === record.size ? { file, name: record.name } : null;
  } catch {
    return null;  // nothing saved, or unreadable
  }
}

export async function clearModel(root) {
  for (const name of [RECORD, DATA]) await root.removeEntry(name).catch(() => {});
}
