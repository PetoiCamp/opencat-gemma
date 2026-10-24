import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build_contract as bc  # noqa: E402

from opencat_gemma.contract import CONTRACT_DIR  # noqa: E402

# Skill tables from the public OpenCatEsp32 (BiBoard) firmware, InstinctBittleESP.h / InstinctNybbleESP.h.
BITTLE_TABLE = 'const char* skillNameWithType[]={"bdFI","bkI","bkArmFI","bkArmLI","bkFI","bkLI","carpetFI","carpetLI","crArmFI","crArmLI","crFI","crLI","gpFI","gpLI","hlwI","jpFI","lftFI","lftLI","phFI","phLI","trArmFI","trArmLI","trFI","trLI","vtArmFI","vtFI","vtLI","wkArmFI","wkArmLI","wkFI","wkLI","balanceI","buttUpI","calibI","droppedI","liftedI","lndI","restI","sitI","strI","upI","zeroN","angI","bfI","bxI","chrI","ckI","clapI","cmhI","dgI","dropRecI","ffI","fivI","flipI","flipDI","flipFI","gdbI","hdsI","hgI","hiI","hskI","huI","huntI","jmpI","kcI","knockI","launchI","lpovI","luckyI","mwI","ndI","pdI","peeI","pickI","pickDI","pickFI","puI","pu1I","putI","putDI","putFI","rcI","rlI","scrhI","showOffI","snfI","tblI","tossI","tossDI","tossFI","tsI","whI","zzI",};'
NYBBLE_TABLE = 'const char* skillNameWithType[]={"bdI","bkI","bkFI","bkLI","crFI","crLI","trFI","trLI","vtFI","vtLI","wkFI","wkLI","balanceI","buttUpI","calibI","droppedI","liftedI","luI","restI","sitI","strI","upI","zeroN","angI","bxI","chrI","ckI","cmhI","dgI","dropRecI","fivI","gdbI","hdsI","headTossI","hgI","hiI","hskI","huI","huntI","kcI","knockI","lkPawsI","luckyI","ndI","pdI","peeI","puI","rcI","scrhI","snfI","standI","tblI","tsI","whI","wsfI",};'
# Parsed rows of Petoi's public web-coding skill list (motion_skills.js + translations.js) for Bittle and Nybble.
WEB_ROWS = [tuple(r) for r in json.loads((Path(__file__).parent / "fixtures" / "web_rows_bittle_nybble.json").read_text())]

MOTION_JS = '''  const GROUPS = Object.freeze({
    walking: Object.freeze([
      Object.freeze({ command: "kwkF", labelKey: "gaitWalkForward", products: Object.freeze(["bittle", "quaddle"]) }),
      Object.freeze({ command: "kwkB", labelKey: "gaitWalkBackwardAlt", products: Object.freeze(["quaddle"]) }),
    ]),
    posture: Object.freeze([
      Object.freeze({ command: "ksit", labelKey: "postureSit", products: Object.freeze(["bittle", "nybble"]) }),
    ]),
'''
TRANSLATIONS_JS = '''  zh: { gaitWalkForward: "向前走", gaitWalkBackwardAlt: "后退", postureSit: "坐下" },
  en: { gaitWalkForward: "walk forward", "gaitWalkBackwardAlt": "walk backward (wkB)", postureSit: 'sit' },
  ja: { gaitWalkForward: "前進", gaitWalkBackwardAlt: "後退", postureSit: "お座り" },
'''


class ParseTest(unittest.TestCase):
    def test_skill_table_drops_type_letter(self):
        self.assertEqual(bc.parse_skill_table('x skillNameWithType[]={"wkFI","bkI","zeroN",};'), {"wkF", "bk", "zero"})

    def test_skill_table_missing_raises(self):
        with self.assertRaises(ValueError):
            bc.parse_skill_table("no table here")

    def test_web_skills_groups_english_labels_and_products(self):
        self.assertEqual(bc.parse_web_skills(MOTION_JS, TRANSLATIONS_JS), [
            ("walking", "kwkF", "walk forward", ["bittle", "quaddle"]),
            ("walking", "kwkB", "walk backward (wkB)", ["quaddle"]),
            ("posture", "ksit", "sit", ["bittle", "nybble"]),
        ])


class RulesTest(unittest.TestCase):
    def test_exists_in_firmware(self):
        skills = {"wkF", "wkL", "bk", "sit"}
        self.assertTrue(bc.exists_in_firmware("kwkF", skills))
        self.assertTrue(bc.exists_in_firmware("kwkR", skills))  # R gaits are mirrored from L
        self.assertTrue(bc.exists_in_firmware("kbkF", skills))  # bk covers bkF
        self.assertFalse(bc.exists_in_firmware("ktrR", skills))
        self.assertFalse(bc.exists_in_firmware("khi", skills))
        self.assertFalse(bc.exists_in_firmware("d", skills))

    def test_kinds_quaddle_rules(self):
        rules = bc.ROBOTS["quaddle"]["rules"]
        self.assertEqual(bc.kind_for("walking", "kwkF", rules), "steps")
        self.assertEqual(bc.kind_for("walking", "kmarchF", rules), "steps")
        for gait in ("ktrB", "kwkB", "kwkL", "kcrR", "kvt90L", "kgallop"):
            self.assertEqual(bc.kind_for("walking", gait, rules), "timed", gait)
        self.assertEqual(bc.kind_for("posture", "kstrF", rules), "once")
        self.assertEqual(bc.kind_for("behavior", "khi", rules), "once")


class BuildTest(unittest.TestCase):
    ROWS = [("walking", "kwkF", "walk forward", ["q"]), ("walking", "kbkF", "walk backward", ["q", "b"]),
            ("walking", "ktrR", "trot right", ["q"]), ("walking", "kwkB", "walk backward (wkB)", ["q"]),
            ("posture", "kcalib", "calibrate", ["q"]), ("posture", "kup", "stand", ["q"]),
            ("behavior", "khi", "hi", ["b"]), ("behavior", "kpd2", "play dead 2", ["q"])]

    def test_core_first_then_rows_in_firmware_with_fixes_and_exclusions(self):
        core = {"kwkF": ("walk forward", "steps"), "kbkF": ("walk backward", "steps")}
        codes, skipped = bc.build("q", {"wkF", "bkF", "trL", "wkB", "calib", "up"}, self.ROWS, core,
                                  exclude={"kcalib": "setup"}, meaning_fix={"kup": "stand up"})
        self.assertEqual(list(codes), ["kwkF", "kbkF", "ktrR", "kwkB", "kup"])
        self.assertEqual(codes["ktrR"], {"meaning": "trot right", "kind": "timed"})
        self.assertEqual(codes["kwkB"], {"meaning": "walk backward (wkB)", "kind": "timed"})
        self.assertEqual(codes["kup"], {"meaning": "stand up", "kind": "once"})
        self.assertEqual(skipped, ["kpd2"])

    def test_kbkF_is_dropped_when_core_has_kbk(self):
        codes, _ = bc.build("b", {"bk"}, self.ROWS, {"kbk": ("walk backward", "steps")}, {}, {})
        self.assertEqual(list(codes), ["kbk"])

    def test_quaddle_core(self):
        self.assertEqual(list(bc.ROBOTS["quaddle"]["core"]),
                         ["kwkF", "kbkF", "kwkL", "kwkR", "ksit", "krest", "kbalance", "khi"])


class GoldenTest(unittest.TestCase):
    """Regenerating Bittle and Nybble from the public inputs must not change their codes (or their order)."""

    def check(self, robot, table):
        spec = bc.ROBOTS[robot]
        codes, skipped = bc.build(spec["product"], bc.parse_skill_table(table), WEB_ROWS, spec["core"],
                                  spec["exclude"], spec["meaning_fix"], spec["rules"])
        current = json.loads((CONTRACT_DIR / f"{robot}.json").read_text())["codes"]
        self.assertEqual(list(codes.items()), list(current.items()))
        self.assertEqual(skipped, [])

    def test_bittle(self):
        self.check("bittle", BITTLE_TABLE)

    def test_nybble(self):
        self.check("nybble", NYBBLE_TABLE)


class QuaddleContractTest(unittest.TestCase):
    def test_kind_rules_hold_in_the_committed_contract(self):
        codes = json.loads((CONTRACT_DIR / "quaddle.json").read_text())["codes"]
        core = bc.ROBOTS["quaddle"]["core"]
        for code, spec in codes.items():
            want = core[code][1] if code in core else None
            if want is None and spec["kind"] != "once":  # a walking gait
                want = "steps" if code.endswith("F") else "timed"
            if want:
                self.assertEqual(spec["kind"], want, code)
        self.assertNotIn("kbk", codes)
        self.assertEqual(codes["kbkF"]["kind"], "steps")
        for setup in ("kcalib", "kzero", "kts", "d"):
            self.assertNotIn(setup, codes)


if __name__ == "__main__":
    unittest.main()
