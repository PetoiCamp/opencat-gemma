// Robot contracts: contract/<robot>.json plus the generated .prompt.txt and .schema.json, fetched relative to the page.
export const ROBOTS = ["bittle", "nybble", "quaddle"];
const DIR = "../contract";

export async function fetchContract(robot, fetchText) {
  const [prompt, schema, data] = await Promise.all(
    [`${robot}.prompt.txt`, `${robot}.schema.json`, `${robot}.json`].map((f) => fetchText(`${DIR}/${f}`)));
  return { robot, prompt, pattern: JSON.parse(schema).items.pattern, codes: JSON.parse(data).codes };
}

// {robot: [model, blePrefix]}, for robotFromReply and the Bluetooth name filters.
export async function loadRegistry(fetchText) {
  return Object.fromEntries(await Promise.all(ROBOTS.map(async (r) => {
    const d = JSON.parse(await fetchText(`${DIR}/${r}.json`));
    return [r, [d.model, d.ble_prefix]];
  })));
}
