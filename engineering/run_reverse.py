"""Command-line entry for the Phase 3 reverse fitter (measured spots ->
thermal-lens D_th).

Usage (from the repository root):
    python3 engineering/run_reverse.py --rez <file.rez>
        [--eng <file.eng.json>]
        --points-T "30:0.210,200:0.285,800:0.95"
        [--points-S "30:0.215,200:0.290,800:0.97"]
        [--m2-T 1.0] [--m2-S 1.0] [--output M4] [--lens TL1:F]

Each ``--points-*`` value is a comma-separated list of ``z_mm:w_mm``
pairs (``z`` = distance downstream of the output mirror, ``w`` = the
measured spot radius there). At least 2 points per plane are required;
at least 3, spanning the waist, are strongly recommended (see
engineering/README.md, "Reverse fitting"). ``--m2-*`` is the measured
M^2 of the beam (omit it when unknown: the fit then warns and reports
a bias estimate instead of correcting). Prints one JSON document to
stdout: the fit reports for both planes. The .rez file is never
modified.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng, eng_path
from rezeng.reverse import fit_thermal_lens


def _points(text):
    points = []
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        z_mm, w_mm = item.split(":")
        points.append({"z_mm": float(z_mm), "w_mm": float(w_mm)})
    return points


def main():
    ap = argparse.ArgumentParser(description="reZonator reverse fitter: "
                                 "measured spots -> thermal-lens D_th")
    ap.add_argument("--rez", required=True, help=".rez file")
    ap.add_argument("--eng", default=None,
                    help="side-car file (default <rez>.eng.json)")
    ap.add_argument("--points-T", required=True,
                    help="T-plane measurements as z_mm:w_mm,...")
    ap.add_argument("--points-S", default=None,
                    help="S-plane measurements as z_mm:w_mm,... "
                    "(default: same z as T is NOT assumed; omit to fit "
                    "T only)")
    ap.add_argument("--m2-T", type=float, default=None,
                    help="measured M^2, T plane (omit when unknown)")
    ap.add_argument("--m2-S", type=float, default=None,
                    help="measured M^2, S plane (omit when unknown)")
    ap.add_argument("--output", default="M4",
                    help="output-mirror element label (default M4)")
    ap.add_argument("--lens", default="TL1:F",
                    help="thermal-lens parameter label:alias "
                    "(default TL1:F)")
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
    lens_label, lens_alias = args.lens.split(":")
    points_T = _points(args.points_T)
    points_S = _points(args.points_S) if args.points_S else None
    out = {"rez": args.rez, "eng": eng_file}
    if points_S is None:
        from rezeng.reverse import fit_plane
        out["T"] = fit_plane(data, points_T, "T",
                             lens=(lens_label, lens_alias),
                             output_label=args.output, eng=eng,
                             m2=args.m2_T)
    else:
        out.update(fit_thermal_lens(
            data, points_T, points_S, lens=(lens_label, lens_alias),
            output_label=args.output, eng=eng,
            m2_T=args.m2_T, m2_S=args.m2_S))
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
