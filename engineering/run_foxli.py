"""Command-line entry for the Phase 4 Fox-Li diffraction engine.

Usage (from the repository root):
    python3 engineering/run_foxli.py --rez <file.rez>
        [--eng <file.eng.json>] [--max-rounds N] [--tol 1e-5]
        [--thermal-power P] [--paraxial] [--png <spot.png>]

Prints one JSON document to stdout: the Fox-Li report (convergence,
gamma, L_diff, D4-sigma w and M2 at every element, aperture notes;
the complex field itself is not JSON, so the spot is reported as an
ASCII map plus, with --png, a PNG file).  The .rez file is never
modified; all engineering data comes from the side-car (default
``<file>.rez.eng.json``).

--thermal-power P computes the crystal OPD from the M2 thermal
solver at P watts incident pump (side-car ``thermal`` section) and
uses it as the ``foxli.opd`` (f_th/c4/c6/r_fit_max); --paraxial
uses the on-axis (paraxial) f_th for the quadratic instead of the
mode-averaged fit -- needed at 10 W, where the fitted f_th falls
in the stability gap.  The thermal section comes from
--thermal-eng (default: the --eng file itself).  See
engineering/README.md, "Fox-Li".
"""

import argparse
import copy
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng import load_rez, load_eng, validate_eng, eng_path
from rezeng.foxli import foxli_report, spot_ascii, spot_png
from rezeng.qevolve import beam_entry, entrance_entry
from rezeng.cli import run_headless_file


def _thermal_opd(data, eng, power_W, paraxial):
    """OPD dict from the M2 thermal solver at ``power_W``."""
    from rezeng.thermal import thermal_report
    eng_i = copy.deepcopy(eng)
    eng_i.setdefault("thermal", {}).setdefault("pump", {})[
        "P_pump_W"] = float(power_W)
    # Laser mode radius at the crystal from the CLI beam.
    result = run_headless_file(data["_rez_path"])["results"][0]
    w_t_in, w_s_in, _, _ = entrance_entry(data, result, "TL1")
    w_t_ex, w_s_ex, _, _ = beam_entry(result, "TL1")
    w_L_um = 1e3 * (w_t_in + w_s_in + w_t_ex + w_s_ex) / 4.0
    rep = thermal_report(data, eng_i, w_L_um=w_L_um)
    pp = rep["phase_plate"]
    f_th_mm = (rep["f_paraxial_mm"] if paraxial else pp["f_th_mm"])
    if f_th_mm is None:
        raise ValueError("thermal solver gives no f_th at %s W"
                         % (power_W,))
    return {"f_th_mm": float(f_th_mm),
            "c4_per_m3": float(pp["c4_per_m3"]),
            "c6_per_m5": float(pp["c6_per_m5"]),
            "r_fit_max_mm": float(pp["r_fit_max_mm"])}, rep


def main():
    ap = argparse.ArgumentParser(description="reZonator Fox-Li engine")
    ap.add_argument("--rez", required=True, help=".rez file")
    ap.add_argument("--eng", default=None,
                    help="side-car file (default <rez>.eng.json)")
    ap.add_argument("--max-rounds", type=int, default=None)
    ap.add_argument("--tol", type=float, default=None)
    ap.add_argument("--thermal-power", type=float, default=None,
                    help="incident pump power (W): take the crystal "
                         "OPD from the M2 thermal solver")
    ap.add_argument("--thermal-eng", default=None,
                    help="side-car with the thermal section, for "
                         "--thermal-power (default: the --eng file, "
                         "which must then carry a thermal section)")
    ap.add_argument("--paraxial", action="store_true",
                    help="with --thermal-power, use the on-axis "
                         "(paraxial) f_th for the quadratic")
    ap.add_argument("--png", default=None,
                    help="write the M1 spot intensity PNG here")
    args = ap.parse_args()

    data = load_rez(args.rez)
    data["_rez_path"] = args.rez
    eng_file = args.eng or eng_path(args.rez)
    eng = load_eng(eng_file)
    problems = validate_eng(eng)
    if problems:
        print("side-car problems in %s:" % eng_file, file=sys.stderr)
        for problem in problems:
            print("  - %s" % problem, file=sys.stderr)
        return 1
    thermal = None
    if args.thermal_power is not None:
        thermal_eng = (load_eng(args.thermal_eng)
                       if args.thermal_eng else eng)
        opd, thermal = _thermal_opd(data, thermal_eng,
                                    args.thermal_power, args.paraxial)
        eng = copy.deepcopy(eng)
        eng.setdefault("foxli", {})["opd"] = opd
    rep = foxli_report(data, eng, max_rounds=args.max_rounds,
                       tol=args.tol)
    field = rep.pop("field")
    rep["spot_ascii"] = spot_ascii(field)
    if args.png:
        rep["png"] = args.png if spot_png(
            field, rep["grid"]["dx_um"] * 1e-6, args.png,
            title="Fox-Li spot at %s" % rep["reference_element"]) \
            else None
        if rep["png"] is None:
            print("matplotlib unavailable: no PNG written",
                  file=sys.stderr)
    out = {"rez": args.rez, "eng": eng_file, "report": rep}
    if thermal is not None:
        out["thermal"] = thermal
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
