"""Phase 4 block 3 demo: Fox-Li on the user's cavity.

1. Cross-validation (no aperture, no aberration): the pure CLI
   Gaussian start converges in 2 rounds; w/M2/L_diff are compared
   with the CLI Gaussian element by element.
2. Thermal M2 curve at 2/5/10 W incident pump (EXAMPLE thermal
   parameters in tests/data/example-thermal.eng.json -- invented,
   not his real laser): for each power the Fox-Li runs twice, once
   with the full fitted OPD (quadratic + c4/c6 spherical
   aberration) and once with the quadratic only, so the M2
   degradation attributable to the aberration is isolated.  At
   10 W the fitted f_th (175.5 mm, D = 5.70/m) falls in the
   stability gap, so the paraxial (on-axis) f_th (93.2 mm) is used
   for the quadratic in both runs, with the fitted c4/c6 kept.
   Both runs use a small M2 aperture (radius 2.0 mm) for mode
   selection (a lossless Fox-Li operator has no differential loss
   to converge on); the quadratic-only column shows the aperture's
   own contribution.
3. Spot intensity at M1 (ASCII summary; PNG if matplotlib is
   available).

All demo numbers use EXAMPLE parameters and are NOT predictions
for his real laser.
"""

import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng import load_rez, load_eng
from rezeng.foxli import foxli_report, spot_ascii, spot_png
from run_foxli import _thermal_opd

USER_CAVITY = "/home/hatch/workspace/user/files/upload.rez"
ENG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "tests", "data", "example-foxli.eng.json")
THERMAL_ENG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "tests", "data", "example-thermal.eng.json")


def _eng_with_opd(opd):
    eng = load_eng(ENG)
    eng.setdefault("foxli", {})["opd"] = opd
    # A small aperture (M2 radius 2.0 mm) for mode selection: on a
    # lossless operator power iteration cannot converge (no
    # differential loss), and the strong example aberration leaves
    # it wandering without one.  The aperture is a Fox-Li modelling
    # choice; the quadratic-only control with the same aperture
    # gives M2 ~ 1.1, so the aberration's incremental degradation
    # is separated from the aperture's own diffraction.
    eng["foxli"]["apertures"] = {"M2": 2.0}
    return eng


def main():
    data = load_rez(USER_CAVITY)
    data["_rez_path"] = USER_CAVITY
    eng = load_eng(ENG)
    thermal_eng = load_eng(THERMAL_ENG)

    print("=== 1. Cross-validation (no aperture, no aberration) ===")
    rep = foxli_report(data, {"foxli": {"noise_frac": 0.0}},
                       max_rounds=60, tol=1e-5)
    print("converged=%s rounds=%d gamma=|%.6f| L_diff=%.2e" %
          (rep["converged"], rep["rounds"], rep["gamma"]["abs"],
           rep["L_diff"]))
    print("%-4s %-10s %-10s %-8s %-8s" % (
        "elem", "w_T/mm", "cli/mm", "dT/%", "M2_T"))
    for b in rep["beam"]:
        print("%-4s %-10.4f %-10.4f %-+8.2f %-8.4f" % (
            b["label"], b["w_T_mm"], b["cli_w_T_mm"],
            100.0 * (b["w_T_mm"] - b["cli_w_T_mm"]) / b["cli_w_T_mm"],
            b["M2_T"]))
    print("M1: w_T=%.4f (CLI %.4f) w_S=%.4f (CLI %.4f) "
          "M2_T=%.4f M2_S=%.4f" % (
              rep["w_T_mm"], rep["cli_w_T_mm"], rep["w_S_mm"],
              rep["cli_w_S_mm"], rep["M2_T"], rep["M2_S"]))
    print("spot at M1 (log scale, 64x24):")
    print(spot_ascii(rep["field"]))
    png = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "demo_foxli_spot.png")
    if spot_png(rep["field"], rep["grid"]["dx_um"] * 1e-6, png,
                title="Fox-Li spot at M1 (cross-validation)"):
        print("PNG: %s" % png)

    print()
    print("=== 2. Thermal M2 curve (EXAMPLE params) ===")
    print("%-5s %-10s %-10s %-10s %-10s %-10s" % (
        "P/W", "f_th/mm", "M2_full_T", "M2_quad_T", "w_full/mm",
        "w_quad/mm"))
    for power, paraxial in ((2.0, False), (5.0, False), (10.0, True)):
        opd, thermal = _thermal_opd(data, thermal_eng, power, paraxial)
        quad = dict(opd)
        quad["c4_per_m3"] = 0.0
        quad["c6_per_m5"] = 0.0
        rep_full = foxli_report(data, _eng_with_opd(opd),
                                max_rounds=100, tol=1e-5)
        rep_quad = foxli_report(data, _eng_with_opd(quad),
                                max_rounds=100, tol=1e-5)
        print("%-5.0f %-10.1f %-10.3f %-10.4f %-10.4f %-10.4f  "
              "full: conv=%s rounds=%d L_diff=%.2g | quad: conv=%s "
              "rounds=%d L_diff=%.2g%s" % (
                  power, opd["f_th_mm"], rep_full["M2_T"],
                  rep_quad["M2_T"], rep_full["w_T_mm"],
                  rep_quad["w_T_mm"], rep_full["converged"],
                  rep_full["rounds"], rep_full["L_diff"],
                  rep_quad["converged"], rep_quad["rounds"],
                  rep_quad["L_diff"],
                  " (paraxial quadratic)" if paraxial else ""))
    print("Note: f_th is the M2 mode-averaged fit (dn/dT only, no "
          "bulge); the 10 W fitted value falls in the stability gap, "
          "so the paraxial f_th is used there.  The example thermal "
          "params (200 um pump vs 498 um mode) make the aberration "
          "severe: the beam overfills the narrow thermal lens.  A "
          "small M2 aperture (radius 2.0 mm) is used for mode "
          "selection (lossless Fox-Li cannot converge without "
          "differential loss); the quadratic-only column shows the "
          "aperture's own contribution, so the aberration's "
          "incremental degradation is the full-vs-quad difference.")


if __name__ == "__main__":
    sys.exit(main())
