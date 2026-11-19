"""End-to-end demo of the Solves on the user's real cavity.

Runs one complete Pickup and two waist Solves, verifies each against
a fresh headless-CLI run, and prints a JSON summary. Nothing is
written into the repository: outputs go to /tmp.

    python3 demo_solves.py
"""

import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng import load_rez, save_rez, run_headless, to_si, from_si
from rezeng.solves import (apply_pickup, verify_pickup, solve_waist_size,
                           solve_waist_position, apply_solution,
                           waist_from_wr, element_plane_position_mm)

USER_CAVITY = os.path.join(os.path.expanduser("~"), "workspace", "user",
                           "files", "upload.rez")


def _beam_at(data, label, overrides=None):
    request = {"base_schema": data}
    if overrides:
        request["mutations"] = [{"id": 0, "overrides": overrides}]
    out = run_headless(request)
    result = out["results"][0]
    assert result["ok"], result.get("error")
    assert result["stable"], "cavity is unstable"
    for entry in result["beam"]:
        if entry["label"] == label:
            return entry
    raise AssertionError("no beam entry for %r" % label)


def main():
    data = load_rez(USER_CAVITY)
    summary = {}

    # --- Pickup: d4.L = 0.5 * d1.L + b (b chosen so the current values
    # are preserved: the cavity optics must not change) ---
    k = 0.5
    src_si = to_si(data["elements"][1]["params"]["L"]["value"], "mm")
    drv_si = to_si(data["elements"][7]["params"]["L"]["value"], "mm")
    b_mm = from_si(drv_si - k * src_si, "mm")
    picked = copy.deepcopy(data)
    info = apply_pickup(picked, ("d4", "L"), ("d1", "L"), k, b_mm)
    problems = verify_pickup(picked, ("d4", "L"), ("d1", "L"), k, b_mm)
    base = run_headless({"base_schema": data})["results"][0]
    after = run_headless({"base_schema": picked})["results"][0]
    save_rez("/tmp/demo_pickup.rez", picked)
    summary["pickup"] = {
        "relation": "d4.L = 0.5 * d1.L + %.6f mm" % b_mm,
        "source_global": info["source_global"],
        "driven_global": info["driven_global"],
        "formula": info["formula"],
        "verify_problems": problems,
        "g_T_unchanged": abs(after["g_T"] - base["g_T"]) < 1e-12,
        "written_to": "/tmp/demo_pickup.rez",
    }

    # --- Waist size: w0 at M1 = 0.12 mm, variable d1.L ---
    size = solve_waist_size(data, ("d1", "L"), "M1", 0.12,
                            bounds_si=(0.33, 0.38))
    solved = copy.deepcopy(data)
    apply_solution(solved, ("d1", "L"), size["solved_value"])
    entry = _beam_at(solved, "M1")
    w0, _ = waist_from_wr(entry["w_T_mm"], entry["R_T_mm"], 1064.0)
    save_rez("/tmp/demo_solved_size.rez", solved)
    summary["waist_size"] = {
        "target_w0_mm": 0.12,
        "solved_d1_mm": size["solved_value_display"],
        "converged": size["converged"],
        "evaluations": size["evaluations"],
        "recheck_w0_mm": w0,
        "recheck_rel_error": abs(w0 - 0.12) / 0.12,
        "written_to": "/tmp/demo_solved_size.rez",
    }

    # --- Waist position: M4-segment waist at s = 1100 mm, variable d1 ---
    pos = solve_waist_position(data, ("d1", "L"), "M4", 1100.0,
                               bounds_si=(0.25, 0.38))
    entry = _beam_at(data, "M4",
                     {"d1": {"L": pos["solved_value_display"]}})
    _, z = waist_from_wr(entry["w_T_mm"], entry["R_T_mm"], 1064.0)
    plane = element_plane_position_mm(
        data, "M4", {"d1": {"L": pos["solved_value"]}})
    waist_s = plane - z
    summary["waist_position"] = {
        "target_s_mm": 1100.0,
        "solved_d1_mm": pos["solved_value_display"],
        "converged": pos["converged"],
        "evaluations": pos["evaluations"],
        "recheck_waist_s_mm": waist_s,
        "recheck_rel_error": abs(waist_s - 1100.0) / 1100.0,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
