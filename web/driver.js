// The robot link plus one plan at a time, with Stop. A Stop the user asked for is not an error.
import { run, STOP, CMD_TIMEOUT_S } from "./runner.js";

export class Driver {
  link = null;
  #running = null;

  constructor(log = console.log) {
    this.log = log;
  }

  get busy() {
    return this.#running !== null;
  }

  // Resolves "done" or "stopped". Rejects on a robot error; runner.run has already sent STOP by then.
  async run(contract, commands, opts = {}) {
    if (!this.link) throw new Error("no robot connected");
    if (this.#running) throw new Error("the robot is already running a plan");
    const running = (this.#running = new AbortController());
    try {
      await run(contract, commands, this.link, { log: this.log, ...opts, signal: running.signal });
      return "done";
    } catch (e) {
      if (running.signal.aborted) return "stopped";
      throw e;
    } finally {
      this.#running = null;
    }
  }

  // Abort a running plan (runner.run sends STOP on the way out), else send STOP directly.
  async stop(why) {
    if (this.#running) {
      this.log(`stop: ${why}`);
      this.#running.abort(new Error(why));
      return;
    }
    if (!this.link) return;
    try {
      this.log(`  sent ${STOP} robot: ${await this.link.send(STOP, CMD_TIMEOUT_S)}`);
    } catch (e) {
      this.log(`  STOP FAILED: ${e} - switch the robot off`);
    }
  }

  // For page-hide: a hidden tab may lose the Bluetooth link, and a timed turn would then never get its STOP.
  stopIfRunning(why) {
    if (this.#running) this.stop(why);
  }
}
