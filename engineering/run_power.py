"""Command-line entry for the Phase 2 power solver.

Usage (from the repository root):
    python3 engineering/run_power.py --rez <file.rez> [--eng <file.eng.json>]
        [--pump 0.5,1,2,5,10] [--toc-scan] [--toc-values 0.02,0.05,0.1,0.2]
        [--toc-pump 5] [--with-m2]

Prints one JSON document to stdout: the pump scan (and, with
--toc-scan, the T_oc scan). The .rez file is never modified; all
engineering data comes from the side-car (default
``<file>.rez.eng.json``). See engineering/README.md, "Power solver".
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng, eng_path
from rezeng.power import pump_scan, toc_scan


def _float_list(text):
    return [float(v) for v in text.split(",") if v.strip()]


def main():
    ap = argparse.ArgumentParser(description="reZonator power solver")
    ap.add_argument("--rez", required=True, help=".rez file")
    ap.add_argument("--eng", default=None,
                    help="side-car file (default <rez>.eng.json)")
    ap.add_argument("--pump", default="0.5,1,2,3,5,7,10",
                    help="comma-separated incident pump powers (W)")
    ap.add_argument("--toc-scan", action="store_true",
                    help="also run a T_oc scan at --toc-pump")
    ap.add_argument("--toc-values", default="0.02,0.05,0.08,0.10,0.15,0.20,0.30",
                    help="comma-separated T_oc values")
    ap.add_argument("--toc-pump", type=float, default=5.0,
                    help="pump power (W) for the T_oc scan")
    ap.add_argument("--with-m2", action="store_true",
                    help="estimate M^2 at the highest pump power")
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
    out = {"rez": args.rez, "eng": eng_file}
    out["pump_scan"] = pump_scan(data, eng, _float_list(args.pump),
                                 with_m2=args.with_m2)
    if args.toc_scan:
        out["toc_scan"] = toc_scan(data, eng, args.toc_pump,
                                   _float_list(args.toc_values))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
