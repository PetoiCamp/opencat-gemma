# Quaddle Command List from Dr. Li's Prompt (Plan 3b)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Dr. Li's Quaddle Gemma prompt (the firmware author's command table) the source of the starter kit's Quaddle command list. That adds eye colours and expressions, learned-skill replay (`T`), the mouse transform (`XO`/`Xo`), joint moves (`m0`/`m8`/`m9`), degree turns (`kvtL`/`kvtR <deg>`) and the extra Quaddle moves. The kit keeps its safety rules: an allowlist, finite commands, and a stop of its own.

**Architecture:**
- **The generator gets a second source:** `tools/build_contract.py` gains a parser for the command-table section of Dr. Li's prompt (lines like `kvtL [deg] turn left`, `vcr red`). Quaddle's contract comes from that table, cross-checked against the robot by a probe. The public web-coding list stays the source for Bittle and Nybble.
- **New command kinds,** so every command stays finite and allowlisted:

  | Kind | Example | Rule |
  |---|---|---|
  | `steps` (existing) | `kwkF 3` | 1–20 cycles; the robot stops itself |
  | `timed` (existing) | `kwkL` | host waits `--turn-seconds`, then `kbalance` |
  | `once` (existing) | `ksit`, `vcr`, `veH`, `T`, `d` | sent as is |
  | `degrees` (new) | `kvtL 90` | 1–360; host timeout `5 + deg/30` s, then STOP. Only if Task 0 shows these turns stop by themselves |
  | `joint` (new) | `m0 45`, `m8 -30` | joints 0, 8 and 9 only; angle −90 to 90 |
  | `final` (new) | `XO`, `Xo` | must be the **last** command of a turn; anything after it is dropped, with a warning |

- **The runner** learns the new kinds. The CLI and other links are unchanged.

## Context

- **Source of truth:** Dr. Li's Quaddle Gemma prompt file (Petoi internal, not copied into the repo).
- **Verified on Quaddle `Q_261022`** (2026-10-23): `kgdb khg kchr kmw kcmh khu kdg` reply `?name?` and do nothing, so they're **excluded**. An unknown skill still gets the `k` echo, which is why the allowlist matters.
- **`XO` (behaviour, from the latest firmware source):** it switches the robot into a Bluetooth-mouse mode, where body motion moves the computer's cursor. Over USB the robot streams motion lines. **Over our BLE link the connection may drop; unverified.** `Xo` returns to normal.
- **Degree turns use the same gyro mechanism that never stopped on Bittle X** (`kwkL 90`). This is untested on Quaddle.
- **Dr. Li's prompt says `<= 200` means steps.** Firmware source says `< 200`. The kit caps step counts at 20, so this doesn't matter here.

## Decisions (proposed, for Kai to approve)

1. **Quaddle's list = Dr. Li's command table, minus the 7 missing commands,** plus our tested core (`kbalance`, `krest`). Meanings use Dr. Li's wording.
2. **Degree turns (`kvtL/kvtR <deg>`)** are added only if the Task 0 spike shows they stop by themselves. Otherwise they stay `timed` as today, and the prompt's "spin → `kvtL 360`" becomes "spin → `kvtL`", a timed turn.
3. **`XO`/`Xo` are allowed over USB and Wi-Fi.** Over `--bluetooth`, decided by Task 0: if `XO` drops our BLE link, the kit refuses it over Bluetooth with a clear message.
4. **Joint moves are limited** to joints 0, 8 and 9 and to ±90°.
5. **Dr. Li's conversational rules are not used:** first-person speech, automatic nod or shake on yes/no answers, the `UART:` line format. The kit stays a command translator with forced JSON. A speech field could be a later plan.
6. **No commits until Kai says so.**

---

### Task 0: Spike (Quaddle on USB, on the floor, Kai present)

> **DONE, 2026-10-23. Approved by Kai.** Results:
> - Eye commands echo `v`; `T` echoes `T`; joint moves echo `m`; `d` echoes `d`.
> - **`kvtL 90` never stops** (the same gyro bug as Bittle; the host stop works). So decision 2 is resolved: **no `degrees` kind; turns stay `timed`.**
> - **`XO` disconnects BLE clients** and switches the robot to Bluetooth-mouse mode. So decision 3 is resolved: **refuse `XO` over `--bluetooth`.**
> - **`XO`/`Xo` signal "done" with `k`, not `X`:** the contract needs a per-code `echo` override (`"echo": "k"`), and links wait for that.

Record every result in `QUADDLE_S3_NOTES.md` (local).
- [ ] **Echo for each new shape:** `vcr`, `veH`, `ved`, `T`, `d`, `m0 30`, then `m0 0`. Record the echo character and whether anything moves.
- [ ] **Degree turn:** `kvtL 90`, with a host watchdog of 10 s, then `kbalance`. Record when the `k` echo arrives (immediately, or after the turn), and whether the robot stops at about 90° by itself.
- [ ] **Mouse transform over USB:** `XO`. Record about 3 s of output, then send `Xo`. Does `Xo` return it to normal?
- [x] ~~**Mouse transform over BLE:**~~ **Dropped from the hardware checklist (Kai, 2026-10-23).** The USB log already shows `XO` disconnecting BLE clients, so the kit refuses `XO` over `--bluetooth` (unit-tested).

### Task 1: Generator second source

- **`parse_prompt_table(text)`:** read the "Command table" section of Dr. Li's prompt. Return `[(command, arg_hint, meaning, section)]` for lines like `kwkF [n]   walk forward`, `vcv purple`, `T  replay…`. Skip prose and the Examples.
- **Kind rules for prompt rows:**
  - `[n]` → `steps`;
  - `[deg]` → `degrees` if Task 0 allows, otherwise `timed`;
  - the `m0`/`m8`/`m9` joint rows → `joint`;
  - `XO`/`Xo` → `final`;
  - everything else → `once`.
  - Commands with a `/` (`kwkL / kwkR`, `ktriCatF/L/R`) expand into separate codes.
- **CLI:** `python tools/build_contract.py --robot quaddle --prompt-table <path to Dr. Li's prompt> --exclude kgdb,khg,kchr,kmw,kcmh,khu,kdg`.
- **Tests:** an inline excerpt of the table format. Cover the expansion of `/` forms, arg hints, the exclude list, and skipping the Examples.

### Task 2: Contract and runner support for the new kinds

- **`contract.py` patterns:**
  - `degrees` codes allow an optional ` <1-360>`;
  - `joint` is `m(0|8|9) -?(90|[1-8]?[0-9])`;
  - `final` codes are plain.
- **The prompt text explains each:** "number of degrees 1–360", and "joint moves: m0 (head), m8 (left front leg/arm), m9 (right front leg/arm), angle −90 to 90".
- **`runner.plan()`:**
  - `degrees` timeout is `5 + ceil(deg / 30)` s;
  - `joint` and `once` timeout is 10 s;
  - **`final` must be last:** drop any later commands and log `dropped … after XO/Xo`.
- **Tests:** patterns accept and reject correctly (`m0 91`, `m5 10`, `kvtL 400`); `plan()` truncates after `XO`; the timeouts are right.

### Task 3: Regenerate Quaddle, eval

- Regenerate `contract/quaddle.json` from Dr. Li's table, keeping Quaddle's tuned `examples` and adding examples for an eye colour, `XO` and a joint move.
- **Extend `eval/cases.quaddle.json`:** "make your eyes purple" → `vcv`; "become a mouse" → `XO`; "turn your head left" → `m0 45` (accept a range: any angle from 20 to 90); "replay the trick you just learned" → `T`; "look happy" → `veH`.
- **Bar:** all cases pass, under 3 s each warm. Bittle and Nybble are unchanged.

### Task 4: Docs (behaviour only)

- **README Quaddle section:** eye colours and expressions, `T`, `XO`/`Xo` (with the BLE caveat from Task 0), joint moves, and the degree-turn status.
- **`contract/README.md`:** the new kinds.

### Task 5: Hardware check (Kai present)

- **Chat over USB and BLE:** "make your eyes blue", "look happy", "turn your head left", "become a mouse" (USB), "turn back into a dog", and a degree turn if enabled.
- **Record the results.**
