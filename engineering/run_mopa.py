"""Command-line entry for the MOPA / regenerative-amplifier chain.

Usage (from the repository root):
    python3 engineering/run_mopa.py --osc <oscillator.rez>
        [--eng <chain.eng.json>]

Prints one JSON document to stdout: per-stage, per-transit energies,
stored-energy depletion, B integral and LIDT status. The oscillator
.rez is used only as the seed reference (its own power is not part of
the chain); the chain data (seed source and stages) comes from the
side-car (default ``<osc>.rez.eng.json``). Stage .rez paths in the
side-car are resolved relative to the side-car file's directory.
See engineering/README.md, "MOPA / regenerative amplifier chain".
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_eng, validate_eng, eng_path
from rezeng.mopa import run_chain


def main():
    ap = argparse.ArgumentParser(
        description="reZonator MOPA / regenerative-amplifier chain")
    ap.add_argument("--osc", required=True,
                    help="oscillator .rez file (seed reference)")
    ap.add_argument("--eng", default=None,
                    help="chain side-car file (default <osc>.rez.eng.json)")
    args = ap.parse_args()

    eng_file = args.eng or eng_path(args.osc)
    if not os.path.exists(eng_file):
        print("no chain side-car: %s" % eng_file, file=sys.stderr)
        return 2
    eng = load_eng(eng_file)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems: %s" % (problems,), file=sys.stderr)
        return 2

    rep = run_chain(args.osc, eng, eng_file=eng_file)
    json.dump(rep, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    for w in rep["warnings"]:
        print("warning: %s" % w, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
