"""Build the `codes` of contract/<robot>.json from Petoi's public web-coding skill list, keeping only the codes
that exist in the robot's firmware skill table.

    python tools/build_contract.py --robot bittle --firmware <firmware skill-table header> --web <dir>

<dir> holds motion_skills.js and translations.js from Petoi's web-coding tool. Quaddle's list instead comes from
the command table of the firmware author's Gemma prompt (a Petoi-internal file, passed by path, never copied):

    python tools/build_contract.py --robot quaddle --prompt-table <prompt file> --firmware <header> --web <dir> \
        --exclude kgdb,khg,...

Quaddle's list is the union of the prompt table and the web list (checked against the firmware table); a code in
both keeps the prompt table's meaning and kind.

Only `codes` is rewritten; `robot`, `model`, `ble_prefix` and `examples` are kept.
Then run `python -m opencat_gemma.contract`.
"""
import argparse
import json
import re
from pathlib import Path

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"

# Labels from the web tool that are ambiguous for a language model.
COMMON_MEANING_FIX = {
    "kup": "stand up (normal standing pose)", "kbalance": "stand up and balance", "kwh": "wave head / shake head",
    "kck": "check around / look around", "ktbl": "be a table (hold still, back flat)", "kvtF": "step in place",
    "khlw": "small steps", "kbf": "backflip", "kflipD": "backflip (alternative)", "kff": "front flip",
    "kflipF": "front flip (alternative)", "kflip": "flip over", "krc": "recover / get back up",
}
COMMON_EXCLUDE = {"kcalib": "calibration pose (setup tool)", "kzero": "zero pose (setup tool)",
                  "kts": "servo test (setup tool)", "d": "same as krest; krest is the tested rest command"}


def _core(backward):
    """The 8 tested codes, first in every contract. Their kinds are fixed, not derived."""
    return {"kwkF": ("walk forward", "steps"), backward: ("walk backward", "steps"), "kwkL": ("turn left", "timed"),
            "kwkR": ("turn right", "timed"), "ksit": ("sit", "once"), "krest": ("lie down / rest", "once"),
            "kbalance": ("stand up and balance", "once"), "khi": ("say hi / wave", "once")}


# Per robot: the web tool's product tag, the core codes, exclusions, label fixes, and the kind rules.
# rules: walking gaits whose skill name ends with one of these suffixes take a step count ('steps'); other gaits
# are 'timed'. Quaddle (hardware check 2026-10-23): ...F gaits count steps; ...B, ...L/R and vt90L loop or are unverified.
# Quaddle's prompt-table source (Plan 3b, Task 0 on Q_261022):
# - joint moves m0/m8/m9 are described in the prompt's prose, not its table, so they are listed here;
# - XO/Xo end the turn ('final') and echo 'k', not 'X';
# - gaits with no direction suffix are 'timed'. kslide is a looping gait in the firmware source. Whether the
#   kq* moves loop is unverified; 'timed' is safe either way (a move that ends by itself just ends in kbalance).
QUADDLE_PROMPT = {
    "joint": {"m0": "turn head / neck (positive angle = left, negative = right)",
              "m8": "move left front leg / arm (negative angle = forward, positive = backward)",
              "m9": "move right front leg / arm (negative angle = forward, positive = backward)"},
    "final": ("XO", "Xo"),
    "echo": {"XO": "k", "Xo": "k"},
    "timed": ("kslide", "kqDance", "kqStep", "kqStepHalf", "kqWheel", "kqBiped", "kqScoot", "kqFrontScoot"),
    "meaning_fix": {"XO": "become a mouse: the robot turns into a Bluetooth mouse",
                    "Xo": "return to normal robot dog (undo XO)", "kvtL": "spin left", "kvtR": "spin right",
                    "kqFrontScoot": "front scoot", "T": "replay the skill that was just learned"},
    # Bare colour names ("red") are too terse for the model: say which part of the robot they change.
    "section_prefix": {"Eye color": "eye color ", "Eye expression": "eye expression: "},
}

ROBOTS = {
    "bittle": {"product": "bittle", "core": _core("kbk"), "exclude": COMMON_EXCLUDE,
               "meaning_fix": COMMON_MEANING_FIX, "rules": ("F",)},
    "nybble": {"product": "nybble", "core": _core("kbk"), "exclude": COMMON_EXCLUDE,
               "meaning_fix": COMMON_MEANING_FIX, "rules": ("F",)},
    "quaddle": {"product": "quaddle", "core": _core("kbkF"), "exclude": COMMON_EXCLUDE,
                "meaning_fix": {**COMMON_MEANING_FIX, "kwkB": "walk backward (alternative gait)"}, "rules": ("F",)},
}


def parse_skill_table(header_text):
    """Return firmware skill names from a skillNameWithType[] table, minus the trailing type letter (I/N)."""
    m = re.search(r"skillNameWithType\[\]\s*=\s*\{([^}]*)\}", header_text)
    if not m:
        raise ValueError("no skillNameWithType[] table found")
    return {n.strip().strip('"')[:-1] for n in m.group(1).split(",") if n.strip().strip('"')}


def parse_web_skills(motion_skills_js, translations_js):
    """Return [(group, command, english_label, [products])] from Petoi's public web-coding files."""
    def label(key):
        found = re.findall(rf"""(?<![\w])["']?{re.escape(key)}["']?\s*:\s*["']([^"']+)["']""", translations_js)
        if len(found) < 2:
            raise ValueError(f"no English label for {key!r}")
        return found[1]  # translations are listed zh, en, ja

    rows, group = [], None
    for line in motion_skills_js.splitlines():
        g = re.match(r"\s*(\w+): Object\.freeze\(\[", line)
        if g:
            group = g.group(1)
        m = re.search(r'command: "([^"]+)", labelKey: "([^"]+)", products: Object\.freeze\(\[([^\]]*)\]', line)
        if m:
            products = [p.strip(' "') for p in m.group(3).split(",") if p.strip()]
            rows.append((group, m.group(1), label(m.group(2)), products))
    return rows


def exists_in_firmware(command, firmware_skills):
    """'k'+skill is in the table, or it's an R gait mirrored from an L gait, or 'bkF' covered by 'bk'."""
    if not command.startswith("k"):
        return False
    skill = command[1:]
    return (skill in firmware_skills or (skill.endswith("R") and skill[:-1] + "L" in firmware_skills)
            or (skill == "bkF" and "bk" in firmware_skills))


def kind_for(group, command, rules):
    """'steps' / 'timed' / 'once' from the group, the command suffix, and per-robot rules (Task 0)."""
    if group != "walking":
        return "once"
    return "steps" if command.endswith(tuple(rules)) else "timed"


def build(product, firmware_skills, web_rows, core, exclude, meaning_fix, rules=("F",)):
    """Return the 'codes' dict for one robot: its core codes first, then every web row for `product` that exists in firmware.

    Also returns the web codes skipped because the firmware lacks them, as (codes, skipped).
    """
    codes = {c: {"meaning": meaning, "kind": kind} for c, (meaning, kind) in core.items()}
    skipped = []
    for group, cmd, label, products in web_rows:
        if product not in products or cmd in exclude or cmd in codes:
            continue
        if cmd == "kbkF" and "kbk" in codes:  # the firmware runs bk as bkF, so kbk already covers it
            continue
        if not exists_in_firmware(cmd, firmware_skills):
            skipped.append(cmd)
            continue
        codes[cmd] = {"meaning": meaning_fix.get(cmd, label), "kind": kind_for(group, cmd, rules)}
    return codes, skipped


# An OpenCat token at the start of a command-table line: a skill (k...), eye colour/expression (vc.../ve...),
# a joint move (m<n>), the transform (XO/Xo), replay (T) or rest (d).
_TOKEN = r"(?:k[A-Za-z0-9]+|v[ce][A-Za-z]+|m\d+|X[Oo]|T|d)"
_ROW = re.compile(rf"(?P<cmds>{_TOKEN}(?:\s*/\s*[A-Za-z0-9]+)*)(?:\s+\[(?P<arg>\w+)\])?(?:\s+(?P<meaning>.*?))?\s*")
_DIRECTION = {"F": "forward", "B": "backward", "L": "left", "R": "right"}


def _english(meaning):
    """Drop a trailing '(...)' note and any non-English alternative ('jump slide / <other language>')."""
    meaning = re.sub(r"\s*\(.*\)\s*$", "", meaning or "")
    return " / ".join(p for p in meaning.split(" / ") if p.isascii()).strip()


def _expand(cmds, meaning):
    """'kwkL / kwkR' -> kwkL, kwkR; 'ktriCatF/L/R' -> ktriCatF, ktriCatL, ktriCatR (a short part replaces the
    first code's suffix). Each expanded code gets its own direction in its meaning when it has one."""
    parts = [p.strip() for p in cmds.split("/")]
    first, codes = parts[0], [parts[0]]
    for part in parts[1:]:
        codes.append(part if re.fullmatch(_TOKEN, part) and len(part) > 1 else first[:-len(part)] + part)
    if len(codes) == 1:
        return [(first, meaning)]
    out = []
    for code in codes:
        word = _DIRECTION.get(code[-1])
        if word and "left / right" in meaning:
            out.append((code, meaning.replace("left / right", word)))
        elif word and word not in meaning:
            out.append((code, f"{meaning} {word}"))
        else:
            out.append((code, meaning))
    return out


def parse_prompt_table(text):
    """Return [(command, arg_hint, meaning, section)] from the '# Command table' section of a Quaddle Gemma prompt.

    Rows look like 'kwkF [n]   walk forward' or 'vcr red'. arg_hint is 'n', 'deg' or None. Slash forms are
    expanded into one row per code. Prose lines and the '## Examples' section are skipped.
    """
    rows, section, inside = [], None, False
    for line in text.splitlines():
        line = line.strip()
        if re.fullmatch(r"#\s*Command table", line, re.I):
            inside = True
            continue
        if not inside:
            continue
        if line.startswith("```"):
            break
        heading = re.fullmatch(r"##\s+(.*)", line)
        if heading:
            section = heading.group(1).strip()
            if section.lower() == "examples":
                break
            continue
        m = _ROW.fullmatch(line)
        if not m or line.endswith("."):
            continue
        for code, meaning in _expand(m.group("cmds"), _english(m.group("meaning"))):
            rows.append((code, m.group("arg"), meaning, section))
    if not inside:
        raise ValueError("no '# Command table' section found")
    return rows


def prompt_kind(command, arg_hint, spec):
    """Kind of a prompt-table row: final (XO/Xo); [n] -> steps; [deg] -> timed (degree turns never stop, Task 0);
    k gaits ending in F -> steps, in L/R/B -> timed; listed suffix-less gaits -> timed; everything else -> once."""
    if command in spec["final"]:
        return "final"
    if arg_hint == "n":
        return "steps"
    if arg_hint == "deg" or command in spec["timed"]:
        return "timed"
    if command.startswith("k") and command[-1] in "FLRB":
        return "steps" if command[-1] == "F" else "timed"
    return "once"


def build_from_prompt(rows, core, exclude, meaning_fix, spec, web_codes=None):
    """Return the 'codes' dict: the core codes first, then every prompt-table row not excluded, then the codes
    of `web_codes` (a build() result) not already listed or excluded, then the joints."""
    codes = {c: {"meaning": meaning, "kind": kind} for c, (meaning, kind) in core.items()}
    fixes = {**meaning_fix, **spec["meaning_fix"]}
    for cmd, arg, meaning, section in rows:
        if cmd in exclude or cmd in codes:
            continue
        prefix = next((v for k, v in spec["section_prefix"].items() if (section or "").startswith(k)), "")
        codes[cmd] = {"meaning": fixes.get(cmd, prefix + meaning), "kind": prompt_kind(cmd, arg, spec)}
        if cmd in spec["echo"]:
            codes[cmd]["echo"] = spec["echo"][cmd]
    for cmd, v in (web_codes or {}).items():
        if cmd not in exclude and cmd not in codes:
            codes[cmd] = v
    for cmd, meaning in spec["joint"].items():
        codes[cmd] = {"meaning": meaning, "kind": "joint"}
    return codes


def main(argv=None):
    p = argparse.ArgumentParser(description="Rewrite the codes of contract/<robot>.json from Petoi's web-coding "
                                            "skill list and a firmware skill table, or from a prompt's command table.")
    p.add_argument("--robot", choices=sorted(ROBOTS), required=True)
    p.add_argument("--firmware", type=Path, help="the firmware header that holds this robot's skillNameWithType[] table")
    p.add_argument("--web", type=Path, help="directory with motion_skills.js and translations.js")
    p.add_argument("--prompt-table", type=Path, metavar="PATH",
                   help="(Quaddle) a Gemma prompt file with a '# Command table' section; merged with --firmware/--web")
    p.add_argument("--exclude", default="", help="with --prompt-table: comma-separated codes to leave out")
    args = p.parse_args(argv)
    if not (args.firmware and args.web):
        p.error("give --firmware and --web (and, for Quaddle, --prompt-table)")
    if args.prompt_table and args.robot != "quaddle":
        p.error("--prompt-table is for --robot quaddle")

    spec = ROBOTS[args.robot]
    rows = parse_web_skills((args.web / "motion_skills.js").read_text(encoding="utf-8"),
                            (args.web / "translations.js").read_text(encoding="utf-8"))
    skills = parse_skill_table(args.firmware.read_text(encoding="utf-8"))
    codes, skipped = build(spec["product"], skills, rows, spec["core"], spec["exclude"], spec["meaning_fix"],
                           spec["rules"])
    skipped = f"in the web list but not in the firmware (skipped): {skipped}"
    if args.prompt_table:
        table = parse_prompt_table(args.prompt_table.read_text(encoding="utf-8"))
        exclude = {c.strip() for c in args.exclude.split(",") if c.strip()}
        codes = build_from_prompt(table, spec["core"], exclude, spec["meaning_fix"], QUADDLE_PROMPT, web_codes=codes)
        skipped += f"\nexcluded: {sorted(exclude)}"
    path = CONTRACT_DIR / f"{args.robot}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["codes"] = codes
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    kinds = {k: sum(v["kind"] == k for v in codes.values()) for k in ("steps", "timed", "once", "joint", "final")}
    print(f"{args.robot}: {len(codes)} codes {kinds}")
    print(skipped)
    print("Now run: python -m opencat_gemma.contract")


if __name__ == "__main__":
    main()
