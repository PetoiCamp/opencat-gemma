// Port of opencat_gemma/runner.py: make every command finite, send one at a time, always keep our own stop.
export const STOP = "kbalance";
export const DEFAULT_STEPS = 3;
export const TURN_SECONDS = 2.0;
export const WALK_BASE_S = 5;  // walk timeout = WALK_BASE_S + S_PER_STEP * steps
export const S_PER_STEP = 2;
export const CMD_TIMEOUT_S = 10;  // every other command, and STOP
export const BLE_REFUSED = { XO: "XO (mouse mode) disconnects Bluetooth; use USB or Wi-Fi" };

// Resolves after `seconds`, or rejects as soon as `signal` aborts.
export const sleep = (seconds, signal) => new Promise((resolve, reject) => {
  signal?.throwIfAborted();
  const t = setTimeout(resolve, seconds * 1000);
  signal?.addEventListener("abort", () => { clearTimeout(t); reject(signal.reason); }, { once: true });
});

// contract: {codes, pattern}. Returns [[command, timeoutS, timedByUs]]. See runner.py plan() for the reasons.
export function plan(contract, commands, log = console.log) {
  const re = new RegExp(contract.pattern);
  const bad = commands.filter((c) => typeof c !== "string" || !re.test(c));
  if (bad.length) throw new Error(`not allowed: ${JSON.stringify(bad)}`);
  const out = [];
  for (const [i, command] of commands.entries()) {
    const [name, steps] = command.split(" ");
    const kind = contract.codes[name].kind;
    if (kind === "steps") {
      const n = steps ? parseInt(steps, 10) : DEFAULT_STEPS;
      out.push([`${name} ${n}`, WALK_BASE_S + S_PER_STEP * n, false]);
    } else {
      out.push([command, CMD_TIMEOUT_S, kind === "timed"]);
    }
    if (kind === "final" && i + 1 < commands.length) {
      log(`  dropped ${commands.slice(i + 1).join(", ")} after XO/Xo`);
      break;
    }
  }
  return out;
}

// Send each command and wait for the robot. On any error or abort, send STOP, then rethrow.
export async function run(contract, commands, link, { turnSeconds = TURN_SECONDS, sleep: wait = sleep, log = console.log, signal, onSent } = {}) {
  const steps = plan(contract, commands, log);  // throws before anything is sent
  if (link.isBle) {
    for (const [command] of steps) if (BLE_REFUSED[command]) throw new Error(BLE_REFUSED[command]);
  }
  const replies = [];
  try {
    for (const [command, timeout, timed] of steps) {
      signal?.throwIfAborted();
      const echo = contract.codes[command.split(" ")[0]].echo;
      replies.push(await link.send(command, timeout, { echo, signal }));
      log(`  sent ${command.padEnd(10)} robot: ${replies.at(-1)}`);
      onSent?.(command, replies.at(-1));
      if (timed) {
        await wait(turnSeconds, signal);
        replies.push(await link.send(STOP, CMD_TIMEOUT_S));
        log(`  sent ${STOP.padEnd(10)} robot: ${replies.at(-1)}`);
        onSent?.(STOP, replies.at(-1));
      }
    }
  } catch (e) {
    log("  stopping robot");
    try {
      await link.send(STOP, CMD_TIMEOUT_S);
    } catch (e2) {
      log(`  STOP FAILED: ${e2} - switch the robot off`);
    }
    throw e;
  }
  return replies;
}
