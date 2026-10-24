// Bluetooth LE link over the Nordic UART service: a port of opencat_gemma/ble.py (BleLink) plus a Web Bluetooth adapter.
// Same handshake as the laptop kit, see docs/protocol.md "Bluetooth (BLE)".
export const NUS_SERVICE = "6e400001-b5a3-f393-e0a9-e50e24dcca9e";
export const NUS_RX = "6e400002-b5a3-f393-e0a9-e50e24dcca9e";  // we write commands here
export const NUS_TX = "6e400003-b5a3-f393-e0a9-e50e24dcca9e";  // the robot notifies replies here
const PUSH_WAIT_S = 2;  // ESP32 firmware pushes its greeting within this time
const GREETING_TIMEOUT_S = 8;  // then the forced "d" arrives within this time
const QUERY_TIMEOUT_S = 5;

const encode = (s) => new TextEncoder().encode(s);
const joined = (lines) => lines.filter(Boolean).join(" | ");

export class NusLink {
  isBle = true;  // the runner refuses commands that would drop a Bluetooth link (XO)

  // write(Uint8Array) -> Promise. The transport calls feed(text) for every notification.
  constructor(write, { now = () => performance.now(), tick = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
    this.write = write;
    this.now = now;
    this.tick = tick;
    this.buf = "";
  }

  feed(text) {
    this.buf += text;
  }

  // Complete lines once one equals token (case-insensitive) or matches the `done` regex.
  async linesUntil(token, timeout, what, { done, signal } = {}) {
    const end = this.now() + timeout * 1000;
    for (;;) {
      signal?.throwIfAborted();
      const lines = this.buf.split("\n").slice(0, -1).map((l) => l.trim());
      if (lines.some((l) => l.toLowerCase() === token.toLowerCase()) || (done && lines.some((l) => done.test(l)))) {
        return lines;
      }
      if (this.now() >= end) {
        throw new Error(`no ${JSON.stringify(token)} echo for ${what} within ${timeout}s, got ${JSON.stringify(this.buf)}`);
      }
      await this.tick(10);
    }
  }

  // If a greeting is pushed (ESP32 firmware), wait for its forced "d" so our commands aren't overwritten.
  // Then always identify with "?" (S3 firmware only answers when asked). Returns the "?" reply.
  async connect() {
    let end = this.now() + PUSH_WAIT_S * 1000;
    while (this.now() < end && !this.buf) await this.tick(10);
    if (this.buf) {
      try {
        await this.linesUntil("d", GREETING_TIMEOUT_S, "the connect greeting");
      } catch {
        // no forced rest seen; "?" below still identifies the robot
      }
    }
    this.buf = "";
    await this.write(encode("?\n"));
    end = this.now() + QUERY_TIMEOUT_S * 1000;
    let lines;
    for (;;) {
      const buf = this.buf;
      lines = buf.split("\n").map((l) => l.trim());
      // A normal reply ends with a "?" line. The S3 firmware's first reply is "Petoi <MODEL>u<MODEL><version>?".
      if (lines.slice(0, -1).includes("?") || (buf.includes("Petoi") && buf.trim().endsWith("?"))) break;
      if (this.now() >= end) throw new Error(`no reply to '?' within ${QUERY_TIMEOUT_S}s, got ${JSON.stringify(buf)}`);
      await this.tick(10);
    }
    this.buf = "";
    return joined(lines);
  }

  // Returns on the token echo (`echo`, default the command's first letter), or earlier on a line matching `done`.
  async send(command, timeout = 10, { done, echo, signal } = {}) {
    this.buf = "";
    await this.write(encode(command + "\n"));
    return joined(await this.linesUntil(echo || command[0], timeout, JSON.stringify(command), { done, signal }));
  }
}

// Map a "?" reply to a robot from {robot: [model, blePrefix]}; the model name that appears first wins.
export function robotFromReply(reply, registry) {
  const found = Object.entries(registry)
    .filter(([, [model]]) => reply.includes(model))
    .map(([robot, [model]]) => [reply.indexOf(model), robot])
    .sort((a, b) => a[0] - b[0] || a[1].localeCompare(b[1]));
  return found.length ? found[0][1] : null;
}

// Web Bluetooth adapter. Must be called from a user tap (Chrome shows its device chooser).
// prefixes: lowercase name prefixes; namePrefix filters are case-sensitive, so each is also offered capitalised.
export async function connectWebBluetooth(prefixes, log = console.log) {
  const names = [...new Set(prefixes.flatMap((p) => [p, p[0].toUpperCase() + p.slice(1)]))];
  const device = await navigator.bluetooth.requestDevice({
    filters: names.map((namePrefix) => ({ namePrefix })), optionalServices: [NUS_SERVICE],
  });
  log(`connecting to ${device.name} ...`);
  const service = await (await device.gatt.connect()).getPrimaryService(NUS_SERVICE);
  const rx = await service.getCharacteristic(NUS_RX);
  const tx = await service.getCharacteristic(NUS_TX);
  let queue = Promise.resolve();  // one GATT write at a time
  const link = new NusLink((bytes) => (queue = queue.catch(() => {}).then(() => rx.writeValueWithoutResponse(bytes))));
  tx.addEventListener("characteristicvaluechanged", (e) => {
    const v = e.target.value;
    link.feed(String.fromCharCode(...new Uint8Array(v.buffer, v.byteOffset, v.byteLength)));  // ISO-8859-1, as ble.py
  });
  await tx.startNotifications();
  link.device = device;
  link.close = () => device.gatt.disconnect();
  return { link, name: device.name, reply: await link.connect() };
}

// Connect over Web Bluetooth and identify the robot from its '?' reply. Must be called from a user tap.
// registry: {robot: [model, blePrefix]} (contracts.js loadRegistry). Returns { link, name, reply, robot }.
export async function connectRobot(registry, log = console.log) {
  const c = await connectWebBluetooth([...Object.values(registry).map(([, prefix]) => prefix), "petoi"], log);
  const robot = robotFromReply(c.reply, registry);
  if (!robot) {
    c.link.close();
    throw new Error(`not a robot this page knows: '?' replied ${JSON.stringify(c.reply)}`);
  }
  return { ...c, robot };
}
