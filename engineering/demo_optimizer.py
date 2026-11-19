#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 3 block 1 end-to-end demo: optimizer + Snap + zone scan.

Runs the full flow on the user's real cavity (example targets and
weights -- the user has not supplied real target spot sizes or
weight preferences yet) plus the Phase 0 prototype reproduction.
Nothing is written back to any .rez file; the modified cavity used
for the zone scan lives only in memory.

    python3 demo_optimizer.py
"""

import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng import (load_rez, optimize, scan_zones, snap_and_reoptimize)

USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
SYMM_FREE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "tests", "data", "spherical_symm_free.rez")


def _mm(values_si):
    return {("%s.%s" % k): round(v * 1e3, 3)
            for k, v in values_si.items()}


def main():
    print("=== 1. 原型复现：最大稳定裕度 (spherical_symm, 未链接 fixture) ===")
    data = load_rez(SYMM_FREE)
    t0 = time.time()
    res = optimize(
        data, [{"label": "L", "alias": "L", "min_si": 0.0, "max_si": 0.2},
               {"label": "M1", "alias": "R",
                "min_si": 0.001, "max_si": 0.1},
               {"label": "M2", "alias": "R",
                "min_si": 0.001, "max_si": 0.1}],
        [{"kind": "stability_center", "weight": 1.0}],
        de_maxiter=40, de_popsize=10, de_seed=0, nm_maxfev=300)
    print("  起点: L=80, R1=R2=50 mm, 裕度 0.72 (g=-0.28)")
    print("  终点: %s, 裕度 %.6f (g=%.2e)"
          % (_mm(res["best_values_si"]),
             1.0 - abs(res["breakdown"][0]["value"]),
             res["breakdown"][0]["value"]))
    print("  原型网格最优 (90, 45, 60) 同为裕度 1.00, 但离起点更远 "
          "(归一化距离 0.124); 连续优化找到的最近表面点离起点 "
          "%.3f, 更符合'改动最小'的 tie-break 规则"
          % res["tie_break"]["distance"])
    print("  评估 %d 次, CLI 调用 %d 次, 用时 %.1f s"
          % (res["evaluations"], res["cli_calls"], time.time() - t0))

    print("\n=== 2. 束腰目标：用户腔体 w0(M1) = 0.12 mm ===")
    data = load_rez(USER_REZ)
    t0 = time.time()
    res = optimize(
        data, [{"label": "d1", "alias": "L",
                "min_si": 0.30, "max_si": 0.45}],
        [{"kind": "waist", "element": "M1", "target_mm": 0.12,
         "weight": 1.0}],
        de_maxiter=25, de_popsize=10, de_seed=0, nm_maxfev=200)
    print("  d1: 372.07 -> %.4f mm (Phase 1 Brent 解: 365.4487 mm)"
          % (res["best_values_si"][("d1", "L")] * 1e3))
    print("  w0(M1) = %.6f mm, merit %.2e, 用时 %.1f s"
          % (res["breakdown"][0]["value"], res["best_merit"],
             time.time() - t0))

    print("\n=== 3. 用户腔体多目标优化：像散 + 稳定居中 + M4 光斑 ===")
    print("  变量: M2 倾角 [1, 3] deg, d1 [300, 450] mm, "
          "M3 R [-550, -350] mm")
    print("  目标: 像散@M4 x10, 稳定居中 x1, 光斑@M4 0.21 mm x1")
    t0 = time.time()
    res = optimize(
        data, [{"label": "M2", "alias": "Alpha",
                "min_si": math.radians(1.0), "max_si": math.radians(3.0)},
               {"label": "d1", "alias": "L",
                "min_si": 0.30, "max_si": 0.45},
               {"label": "M3", "alias": "R",
                "min_si": -0.55, "max_si": -0.35}],
        [{"kind": "astigmatism", "element": "M4", "weight": 10.0},
         {"kind": "stability_center", "weight": 1.0},
         {"kind": "beam_T", "element": "M4", "target_mm": 0.21,
          "weight": 1.0},
         {"kind": "beam_S", "element": "M4", "target_mm": 0.21,
          "weight": 1.0}],
        de_maxiter=30, de_popsize=10, de_seed=0, nm_maxfev=300)
    print("  merit: %.4f -> %.4f" % (res["start_merit"], res["best_merit"]))
    print("  M2 倾角: 2.5 -> %.3f deg (独立复现了 Phase 0 的 1.5 deg "
          "修正方向)" % math.degrees(res["best_values_si"][("M2", "Alpha")]))
    print("  d1: 372.07 -> %.2f mm, M3 R: -450 -> %.1f mm (触及边界)"
          % (res["best_values_si"][("d1", "L")] * 1e3,
             res["best_values_si"][("M3", "R")] * 1e3))
    for b in res["breakdown"]:
        print("    %-16s value=%.6g contribution=%.6g"
              % (b["kind"], b["value"], b["contribution"]))
    print("  评估 %d 次, CLI 调用 %d 次, 用时 %.1f s"
          % (res["evaluations"], res["cli_calls"], time.time() - t0))

    print("\n=== 4. Snap: M3 R=-450 -> 标准件, 锁定后重优化 d2/d3 ===")
    t0 = time.time()
    snap = snap_and_reoptimize(
        data, [{"label": "M3", "alias": "R"}],
        [{"label": "M3", "alias": "R", "min_si": -0.55, "max_si": -0.35},
         {"label": "d2", "alias": "L", "min_si": 0.40, "max_si": 0.55},
         {"label": "d3", "alias": "L", "min_si": 0.015, "max_si": 0.04}],
        [{"kind": "astigmatism", "element": "M4", "weight": 10.0},
         {"kind": "stability_center", "weight": 1.0}],
        [("d2", "L"), ("d3", "L")], nm_maxfev=150)
    s = snap["snapped"][0]
    print("  M3 R: %.1f -> %.1f mm (%s, 屈光度距离 %.2e /mm)"
          % (s["old_R_mm"], s["new_R_mm"], s["part_number"],
             s["distance_per_mm"]))
    print("  merit: %.4f -> %.4f (delta %.4f)"
          % (snap["before"]["merit"], snap["after"]["merit"],
             snap["comparison"]["delta_merit"]))
    print("  g: (%.4f, %.4f) -> (%.4f, %.4f)"
          % (snap["before"]["g_T"], snap["before"]["g_S"],
             snap["after"]["g_T"], snap["after"]["g_S"]))
    print("  w_M4: (%.4f, %.4f) -> (%.4f, %.4f) mm"
          % (snap["before"]["beam"]["M4"][0],
             snap["before"]["beam"]["M4"][1],
             snap["after"]["beam"]["M4"][0],
             snap["after"]["beam"]["M4"][1]))
    print("  d2/d3: %.2f/%.2f -> %.2f/%.2f mm (NM %d 次评估)"
          % (snap["before"]["values_si"][("d2", "L")] * 1e3,
             snap["before"]["values_si"][("d3", "L")] * 1e3,
             snap["after"]["values_si"][("d2", "L")] * 1e3,
             snap["after"]["values_si"][("d3", "L")] * 1e3,
             snap["nm"]["nfev"]))
    print("  用时 %.1f s" % (time.time() - t0))

    print("\n=== 5. 双稳区扫描：D_th = 1/f_th, 300 点 ===")
    t0 = time.time()
    z = scan_zones(data, lens=("TL1", "F"), d_min=0.0, d_max=12.0,
                   n_points=300, sesam_label="M1", crystal_label="TL1",
                   working_f_mm=230.0)
    print("  边界 (Brent 精修):")
    for b in z["boundaries"]:
        print("    g_%s=%+d  D=%.6f /m  f=%.2f mm"
              % (b["axis"], b["g"], b["D_th"], b["f_mm"]))
    for entry in z["zones_common"]:
        print("  %s: D=[%.4f, %.4f] /m, f=[%s, %s] mm"
              % (entry["id"], entry["D_range"][0], entry["D_range"][1],
                 "inf" if entry["f_range"][0] is None
                 else "%.1f" % entry["f_range"][0],
                 "inf" if entry["f_range"][1] is None
                 else "%.1f" % entry["f_range"][1]))
    print("  当前工作点 F=230 mm (D=4.348 /m) 在 %s, 靠近 Zone I 上沿 "
          "(D=4.640)" % z["working_point"]["zone"])
    print("  与 Phase 2 印证: F=1150 mm (D=0.87) 失稳, F=164 mm "
          "(D=6.10) 失稳, F=115 mm (D=8.70) 在 Zone II 内稳定")
    print("  CLI 调用 %d 次, 用时 %.1f s"
          % (z["n_cli_calls"], time.time() - t0))

    print("\n注: 全部演示数值均为示例目标/权重, 不是用户真实激光的"
          "预测; 目标光斑、权重偏好、标准件供应商偏好仍需用户提供。")


if __name__ == "__main__":
    main()
