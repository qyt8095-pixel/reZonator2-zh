"""Command-line entry for the Jones polarisation + dispersion report.

Usage (from the repository root):
    python3 engineering/run_jones.py --rez <file.rez> [--eng <file.eng.json>]

Prints one JSON document to stdout: the round-trip Jones matrix and
eigen-polarisation, the polarisation loss, and the round-trip GDD/TOD.
The .rez file is never modified; all engineering data comes from the
side-car (default ``<file>.rez.eng.json``). See engineering/README.md,
"Jones polarisation" and "Dispersion (GDD/TOD)".
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng, eng_path
from rezeng.jones import jones_report
from rezeng.dispersion import round_trip_dispersion


def main():
    ap = argparse.ArgumentParser(
        description="reZonator Jones polarisation + dispersion report")
    ap.add_argument("--rez", required=True, help=".rez file")
    ap.add_argument("--eng", default=None,
                    help="side-car file (default <rez>.eng.json)")
    args = ap.parse_args()

    data = load_rez(args.rez)
    eng_file = args.eng or eng_path(args.rez)
    eng = load_eng(eng_file) if os.path.exists(eng_file) else {}
    problems = validate_eng(eng)
    if problems:
        print("side-car problems: %s" % (problems,), file=sys.stderr)
        return 2

    out = {"jones": jones_report(data, eng),
           "dispersion": round_trip_dispersion(data, eng)}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
