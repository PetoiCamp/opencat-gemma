// Port of opencat_gemma/gemma.py:parse. Never trust model output: the web runtime does not enforce the schema.
export function parse(pattern, out) {
  let v;
  try {
    v = JSON.parse(out);
  } catch {
    return { commands: null, error: "invalid JSON" };
  }
  if (v !== null && typeof v === "object" && !Array.isArray(v)) {
    v = Object.values(v).find(Array.isArray) ?? null;
  }
  if (!Array.isArray(v)) return { commands: null, error: "not a list" };
  const re = new RegExp(pattern);
  const bad = v.filter((c) => typeof c !== "string" || !re.test(c));
  if (bad.length) return { commands: null, error: `not allowed: ${JSON.stringify(bad)}` };
  return { commands: v, error: null };
}
