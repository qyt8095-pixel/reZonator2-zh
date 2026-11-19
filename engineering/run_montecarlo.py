"""Command-line entry for the Phase 3 Monte Carlo tolerance simulation.

Usage (from the repository root):
    python3 engineering/run_montecarlo.py --rez <file.rez>
        [--eng <file.eng.json>] [--n 1000] [--chunk 250] [--seed 0]
        [--watch M1,M4]

Prints one JSON document to stdout: the Monte Carlo report (see
:func:`rezeng.montecarlo.run_montecarlo`). The .rez file is never
modified; tolerances come from the side-car ``tolerances`` section
(default ``<file>.rez.eng.json``). See engineering/README.md,
"Monte Carlo tolerance simulation".
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng, eng_path
from rezeng.montecarlo import run_montecarlo


def main():
    ap = argparse.ArgumentParser(description="reZonator Monte Carlo "
                                 "tolerance simulation")
    ap.add_argument("--rez", required=True, help=".rez file")
    ap.add_argument("--eng", default=None,
                    help="side-car file (default <rez>.eng.json)")
    ap.add_argument("--n", type=int, default=1000,
                    help="number of perturbed samples (default 1000)")
    ap.add_argument("--chunk", type=int, default=250,
                    help="points per CLI batch request (default 250)")
    ap.add_argument("--seed", type=int, default=0,
                    help="random seed, fixed for reproducibility "
                    "(default 0)")
    ap.add_argument("--watch", default="M1,M4",
                    help="comma-separated element labels whose spot "
                    "sizes are tracked (default M1,M4)")
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
    tolerances = eng.get("tolerances")
    if not tolerances:
        print("no tolerances section in %s" % eng_file, file=sys.stderr)
        return 1
    watch = tuple(w.strip() for w in args.watch.split(",") if w.strip())
    report = run_montecarlo(data, tolerances, n=args.n,
                            chunk_size=args.chunk, seed=args.seed,
                            watch=watch, eng=eng)
    out = {"rez": args.rez, "eng": eng_file}
    out.update(report)
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
