#!/usr/bin/env python3
"""Command-line entry for the ODR (Optical Design Review) report.

Usage (from the repository root):
    python3 engineering/run_odr.py --rez <file.rez>
        [--eng <file.eng.json>] [--out report.html]
        [--foxli] [--mc-n 1000] [--pump 2,5,10] [--real]

Prints a short JSON summary to stdout and writes the full HTML report
to --out (default ``<rez basename>.odr.html`` next to the .rez file).
Without --real the report is headed as EXAMPLE parameters.  The .rez
file is never modified. See engineering/README.md, "ODR report".
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng.odr import build_odr_report


def _float_list(text):
    return [float(v) for v in text.split(",") if v.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(description="reZonator ODR report")
    ap.add_argument("--rez", required=True, help=".rez file")
    ap.add_argument("--eng", default=None,
                    help="side-car file (default <rez>.eng.json)")
    ap.add_argument("--out", default=None,
                    help="HTML output path (default <rez>.odr.html)")
    ap.add_argument("--foxli", action="store_true",
                    help="include the Fox-Li diffraction section")
    ap.add_argument("--mc-n", type=int, default=1000,
                    help="Monte Carlo sample count (default 1000)")
    ap.add_argument("--pump", default="2,5,10",
                    help="comma-separated pump powers for the thermal "
                         "section (default 2,5,10)")
    ap.add_argument("--real", action="store_true",
                    help="mark the report as based on real parameters "
                         "(default: EXAMPLE banner)")
    args = ap.parse_args(argv)

    out_html = args.out
    if not out_html:
        base, _ = os.path.splitext(args.rez)
        out_html = base + ".odr.html"
    report = build_odr_report(
        args.rez, eng_file=args.eng, include_foxli=args.foxli,
        mc_n=args.mc_n, pump_powers=_float_list(args.pump),
        example_params=not args.real, out_html=out_html)
    summary = {k: v for k, v in report.items() if k != "html"}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
