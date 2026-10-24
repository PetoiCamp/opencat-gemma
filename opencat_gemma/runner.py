"""Send validated commands one at a time. The computer always keeps its own stop: never rely only on the robot."""
import time

STOP = "kbalance"
DEFAULT_STEPS = 3
TURN_SECONDS = 2.0
WALK_BASE_S = 5  # walk timeout = WALK_BASE_S + S_PER_STEP * steps
S_PER_STEP = 2
CMD_TIMEOUT_S = 10  # timeout for every other command and for STOP
BLE_REFUSED = {"XO": "XO (mouse mode) disconnects Bluetooth; use USB or Wi-Fi"}


def plan(contract, commands, log=print):
    """Make every command finite. Returns [(command, timeout_s, timed_by_us)].

    - "steps" codes always carry a count; the robot walks that many cycles, stands up, then echoes "k".
      Measured ~1.3 s per cycle on Bittle X, so the timeout is WALK_BASE_S + S_PER_STEP * steps (5 + 2 * steps).
    - "timed" codes (turns) are sent bare: angle turns (`kwkL 90`) never stopped on firmware B10_260527,
      so we time them and send STOP ourselves.
    - "final" codes (XO/Xo) change the robot's mode, so they end the turn: later commands are dropped.
    """
    bad = contract.validate(commands)
    if bad:
        raise ValueError(f"not allowed: {bad}")
    out = []
    for i, command in enumerate(commands):
        name, _, steps = command.partition(" ")
        kind = contract.codes[name]["kind"]
        if kind == "steps":
            steps = int(steps or DEFAULT_STEPS)
            out.append((f"{name} {steps}", WALK_BASE_S + S_PER_STEP * steps, False))
        else:
            out.append((command, CMD_TIMEOUT_S, kind == "timed"))
        if kind == "final" and commands[i + 1:]:
            log(f"  dropped {', '.join(commands[i + 1:])} after XO/Xo")
            break
    return out


def run(contract, commands, link, turn_seconds=TURN_SECONDS, sleep=time.sleep, log=print):
    """Send each command and wait for the robot. On any error or Ctrl+C, send STOP, then re-raise.

    A code with an "echo" in the contract (XO/Xo reply "k") is sent with echo=, so the link waits for that token."""
    steps = plan(contract, commands, log=log)  # raises ValueError before anything is sent
    if getattr(link, "is_ble", False):
        for command, _, _ in steps:
            if command in BLE_REFUSED:
                raise ValueError(BLE_REFUSED[command])
    replies = []
    try:
        for command, timeout, timed in steps:
            echo = contract.codes[command.partition(" ")[0]].get("echo")
            replies.append(link.send(command, timeout, echo=echo) if echo else link.send(command, timeout))
            log(f"  sent {command:10} robot: {replies[-1]}")
            if timed:
                sleep(turn_seconds)
                replies.append(link.send(STOP, CMD_TIMEOUT_S))
                log(f"  sent {STOP:10} robot: {replies[-1]}")
    except BaseException:
        log("  stopping robot")
        try:
            link.send(STOP, CMD_TIMEOUT_S)
        except Exception as e:
            log(f"  STOP FAILED: {e!r} - switch the robot off")
        raise
    return replies
