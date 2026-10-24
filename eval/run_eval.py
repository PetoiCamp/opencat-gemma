"""Accuracy and latency of Gemma on eval/cases.json. Needs Ollama running. Exit 0 if every case passes."""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from opencat_gemma.contract import ROBOTS, load  # noqa: E402
from opencat_gemma.gemma import MODEL, ask, parse  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--robot", choices=ROBOTS, default="bittle")
p.add_argument("--model", default=MODEL)
args = p.parse_args()
contract = load(args.robot)
cases = json.loads((Path(__file__).parent / "cases.json").read_text())

passed, times = 0, []
for text, acceptable in cases:
    t = time.time()
    out = ask(contract, text, model=args.model)
    times.append(time.time() - t)
    commands, err = parse(contract, out)
    ok = err is None and commands in acceptable
    passed += ok
    print(f"{times[-1]:5.1f}s | {'PASS' if ok else 'FAIL'} | {text!r:72} -> {out}" + ("" if ok else f"  (want {acceptable})"))
print(f"\n{passed}/{len(cases)} passed | latency avg {sum(times) / len(times):.1f}s, max {max(times):.1f}s")
sys.exit(0 if passed == len(cases) else 1)
