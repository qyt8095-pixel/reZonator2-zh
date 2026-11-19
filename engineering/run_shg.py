"""Command-line entry for the Phase 2 SHG module.

Usage (from the repository root):
    python3 engineering/run_shg.py --rez <file.rez> [--eng <file.eng.json>]
        [--pump 2,3,5,7,10] [--toc 0.10]

Prints one JSON document to stdout: the SHG pump scan. The .rez file
is never modified; all engineering data comes from the side-car
(default ``<file>.rez.eng.json``). The cavity must contain the SHG
crystal as an ElemPlate element (see engineering/README.md, "SHG").
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng, eng_path
from rezeng.shg import shg_pump_scan, SHGError
from rezeng.power import PowerError


def _float_list(text):
    return [float(v) for v in text.split(",") if v.strip()]


def main():
    ap = argparse.ArgumentParser(description="reZonator SHG solver")
    ap.add_argument("--rez", required=True, help=".rez file")
    ap.add_argument("--eng", default=None,
                    help="side-car file (default <rez>.eng.json)")
    ap.add_argument("--pump", default="2,3,5,7,10",
                    help="comma-separated incident pump powers (W)")
    ap.add_argument("--toc", type=float, default=None,
                    help="output coupler transmission (default: side-car)")
    args = ap.parse_args()

    data = load_rez(args.rez)
    eng_file = args.eng or eng_path(args.rez)
    eng = load_eng(eng_file)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems in %s:" % eng_file, file=sys.stderr)
        for problem in problems:
            print("  - %s" % problem, file=sys.stderr)
        return 1
    try:
        out = {"rez": args.rez, "eng": eng_file}
        out["shg_scan"] = shg_pump_scan(data, eng,
                                        _float_list(args.pump),
                                        T_oc=args.toc)
    except (SHGError, PowerError) as e:
        print("SHG scan failed: %s" % (e,), file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
