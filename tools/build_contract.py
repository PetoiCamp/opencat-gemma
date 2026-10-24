"""Build the `codes` of contract/<robot>.json from Petoi's public web-coding skill list, keeping only the codes
that exist in the robot's firmware skill table.

    python tools/build_contract.py --robot bittle --firmware <firmware skill-table header> --web <dir>

<dir> holds motion_skills.js and translations.js from Petoi's web-coding tool. Only `codes` is rewritten;
`robot`, `model`, `ble_prefix` and `examples` are kept. Then run `python -m opencat_gemma.contract`.
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


def main(argv=None):
    p = argparse.ArgumentParser(description="Rewrite the codes of contract/<robot>.json from Petoi's web-coding "
                                            "skill list and a firmware skill table.")
    p.add_argument("--robot", choices=sorted(ROBOTS), required=True)
    p.add_argument("--firmware", required=True, type=Path,
                   help="the firmware header that holds this robot's skillNameWithType[] table")
    p.add_argument("--web", required=True, type=Path, help="directory with motion_skills.js and translations.js")
    args = p.parse_args(argv)

    spec = ROBOTS[args.robot]
    rows = parse_web_skills((args.web / "motion_skills.js").read_text(encoding="utf-8"),
                            (args.web / "translations.js").read_text(encoding="utf-8"))
    skills = parse_skill_table(args.firmware.read_text(encoding="utf-8"))
    codes, skipped = build(spec["product"], skills, rows, spec["core"], spec["exclude"], spec["meaning_fix"],
                           spec["rules"])
    path = CONTRACT_DIR / f"{args.robot}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["codes"] = codes
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    kinds = {k: sum(v["kind"] == k for v in codes.values()) for k in ("steps", "timed", "once")}
    print(f"{args.robot}: {len(codes)} codes {kinds}")
    print(f"in the web list but not in the firmware (skipped): {skipped}")
    print("Now run: python -m opencat_gemma.contract")


if __name__ == "__main__":
    main()
