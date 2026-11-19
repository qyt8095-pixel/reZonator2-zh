#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line entry for the dual stability-zone scan.

    python3 run_zones.py --rez path/to/cavity.rez [--d-max 12]
                         [--n-points 300] [--f-mm 230]

Prints the scan result (zones, Brent-refined boundaries,
trajectory, working point) as JSON.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng import load_rez, scan_zones


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rez", required=True)
    ap.add_argument("--lens-label", default="TL1")
    ap.add_argument("--lens-alias", default="F")
    ap.add_argument("--d-min", type=float, default=0.0)
    ap.add_argument("--d-max", type=float, default=12.0)
    ap.add_argument("--n-points", type=int, default=300)
    ap.add_argument("--sesam-label", default="M1")
    ap.add_argument("--crystal-label", default=None)
    ap.add_argument("--f-mm", type=float, default=None,
                    help="current focal length in mm (working point)")
    args = ap.parse_args()
    data = load_rez(args.rez)
    res = scan_zones(data, lens=(args.lens_label, args.lens_alias),
                     d_min=args.d_min, d_max=args.d_max,
                     n_points=args.n_points,
                     sesam_label=args.sesam_label,
                     crystal_label=args.crystal_label,
                     working_f_mm=args.f_mm)
    print(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
