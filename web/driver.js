// The robot link plus one plan at a time, with Stop. A Stop the user asked for is not an error.
import { run, STOP, CMD_TIMEOUT_S } from "./runner.js";

export class Driver {
  link = null;
  #running = null;
  #stops = 0;  // bumped by every stop/cancel; a plan whose ticket is older never starts

  constructor(log = console.log) {
    this.log = log;
  }

  get busy() {
    return this.#running !== null;
  }

  // Take one before Gemma's inference and pass it to run(): a stop during inference then cancels the plan.
  ticket() {
    return this.#stops;
  }

  // Resolves "done" or "stopped". Rejects on a robot error; runner.run has already sent STOP by then.
  // opts.ticket: from ticket(); if any stop came after it, resolves "stopped" without sending anything.
  async run(contract, commands, { ticket, ...opts } = {}) {
    if (!this.link) throw new Error("no robot connected");
    if (this.#running) throw new Error("the robot is already running a plan");
    if (ticket !== undefined && ticket !== this.#stops) return "stopped";
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
    this.#stops++;
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

  // Cancel, for page-hide: drop any plan still being inferred and abort a running one, but send nothing
  // when idle. A hidden tab may lose the Bluetooth link, and a timed turn would then never get its STOP.
  stopIfRunning(why) {
    this.#stops++;
    if (this.#running) this.stop(why);
  }
}
