"""Command-line entry for the Phase 4 thermal conduction solver.

Usage (from the repository root):
    python3 engineering/run_thermal.py --rez <file.rez>
        [--eng <file.eng.json>] [--pump 2,5,10] [--w-l-um 210]

Prints one JSON document to stdout: the thermal + OPD + fracture
report at each pump power (the side-car ``thermal.pump.P_pump_W``
is the default when --pump is omitted). The .rez file is never
modified; all engineering data comes from the side-car (default
``<file>.rez.eng.json``). See engineering/README.md, "Thermal
conduction and fracture".
"""

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng, eng_path
from rezeng.thermal import thermal_report


def _float_list(text):
    return [float(v) for v in text.split(",") if v.strip()]


def main():
    ap = argparse.ArgumentParser(description="reZonator thermal solver")
    ap.add_argument("--rez", required=True, help=".rez file")
    ap.add_argument("--eng", default=None,
                    help="side-car file (default <rez>.eng.json)")
    ap.add_argument("--pump", default=None,
                    help="comma-separated incident pump powers (W); "
                         "default: the side-car value")
    ap.add_argument("--w-l-um", type=float, default=None,
                    help="laser mode radius at the crystal in um "
                         "(default: side-car thermal.w_L_um, else the "
                         "mean pump radius)")
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
    powers = _float_list(args.pump) if args.pump else [None]
    out = {"rez": args.rez, "eng": eng_file, "reports": []}
    for power in powers:
        eng_i = copy.deepcopy(eng)
        if power is not None:
            eng_i.setdefault("thermal", {}).setdefault("pump", {})[
                "P_pump_W"] = power
        out["reports"].append(thermal_report(data, eng_i,
                                             w_L_um=args.w_l_um))
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
