# Contract

`bittle.json` and `nybble.json` are the single source of truth for what Gemma may send to a robot. The Gemma prompt and the output schema are generated from them.

## Fields

```json
{
  "robot": "Bittle X robot dog",
  "codes": { "kwkF": {"meaning": "walk forward", "kind": "steps"}, "...": {} },
  "examples": [ ["walk forward then sit", ["kwkF", "ksit"]] ]
}
```

- `robot`: used in the first line of the prompt ("You control a Petoi ...").
- `codes`: every allowed command (69 for Bittle X, 52 for Nybble Q). `meaning` goes into the prompt. `kind` says how the starter sends it:
  - `steps`: accepts an optional step count of 1 to 20 (`kwkF 5`). The starter always adds a count (default 3), so the walk ends by itself.
  - `timed`: sent with no number. The computer waits a few seconds, then sends `kbalance`. Used for turns, because angle turns never stop on firmware B10_260527.
  - `once`: sent as is, and the robot reports when it is done.
- `examples`: `[request, [commands]]` pairs shown to Gemma in the prompt. Examples are the only thing to tune when Gemma gets a case wrong. Keep both robots' examples identical.

## How the prompt and schema are built

`opencat_gemma/contract.py` builds one regex from the codes:

```
^((<steps codes>)( ([1-9]|1[0-9]|20))?|<other codes>)$
```

The schema is `{"type": "array", "items": {"type": "string", "pattern": <regex>}}`. The prompt is the code list, a sentence about step counts, the "return [] if nothing matches" rule, and the examples.

## Changing it

Edit the JSON, then regenerate:

```bash
.venv/bin/python -m opencat_gemma.contract
```

This rewrites `<robot>.prompt.txt` and `<robot>.schema.json`. The tests fail if you forget (`test_generated_files_are_in_sync`). Then re-check Gemma with `eval/run_eval.py`.

## Using it on Android or in another language

- Load `bittle.prompt.txt` (or `nybble.prompt.txt`) as the system prompt.
- If your runtime supports constrained output, use `bittle.schema.json` for it.
- **Always** validate every command against the same regex before sending it to the robot, even when the output was constrained. Models and runtimes differ, and the check is what keeps any code outside the contract off the robot.
