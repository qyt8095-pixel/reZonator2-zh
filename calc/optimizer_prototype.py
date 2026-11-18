#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reZonator2 一键优化器 — 原型验证脚本（最大稳定裕度）

目标：在给定的参数范围内，找出离稳定边界最远的参数组合，
优先稳妥，不追极限束腰。

方法（与 2026-10-29 和 ching 定下的方案一致）：
- 用 reZonator 自带的 Python 往返计算（calc/rezonator.py 的 make_abcd /
  calc_stab）构造往返矩阵，不改 C++ 界面；
- 粗扫 + 最优点附近细搜，自动跳过不稳定组合；
- 输出优化前后参数对照表。

稳定裕度定义：往返矩阵 M 的稳定参数 g = (A+D)/2，稳定条件 |g| < 1，
裕度 = 1 - |g|。裕度越大，离稳定边界越远。

默认算例：仓库自带的 bin/examples/spherical_symm.rez（对称双镜腔：
M1 曲率半径 50 cm，腔长 80 cm，M2 曲率半径 50 cm）。
可调参数与范围是演示用的默认值；ching 给出自己的参数和范围后，
直接改下面的 PARAMS 即可重跑。
"""

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rezonator import make_abcd, calc_stab, calc_w  # noqa: E402

# ---------------------------------------------------------------- 参数
SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "bin", "examples", "spherical_symm.rez")
WAVELENGTH_MKM = 0.64  # 例子的波长 0.64 微米，仅用于对照表里的束腰参考值

# 可调参数：(名字, 单位, 下限, 上限, 粗扫步长)
# 2026-11-18：ching 指定范围——腔长 0–2 m，镜片曲率 0–1000 mm
# （脚本内统一用 cm：腔长 0–200 cm，曲率 0–100 cm）。
# 注意：曲率半径 0 没有物理意义（平面镜对应无穷大，不是 0），且公式
# 里要除以 R，R=0 的组合在 stability_margin 里直接按无效跳过。
PARAMS = [
    ("L", "cm", 0.0, 200.0, 2.0),     # 腔长
    ("R1", "cm", 0.0, 100.0, 5.0),    # M1 曲率半径
    ("R2", "cm", 0.0, 100.0, 5.0),    # M2 曲率半径
]
PARAM_NAMES = ("腔长 L", "M1 曲率半径 R1", "M2 曲率半径 R2")


# ---------------------------------------------------------------- 模型
def round_trip_matrix(L, R1, R2):
    """从 M1 出发的往返矩阵：M1 镜 · 传 L · M2 镜 · 传 L。"""
    prop = make_abcd(1, L, 0, 1)          # 自由空间传播 L
    mir1 = make_abcd(1, 0, -2.0 / R1, 1)  # 曲率半径 R1 的反射镜
    mir2 = make_abcd(1, 0, -2.0 / R2, 1)  # 曲率半径 R2 的反射镜
    return np.linalg.multi_dot([mir1, prop, mir2, prop])


def stability_margin(L, R1, R2):
    """返回 (裕度, g)；不稳定时裕度为 None。"""
    if R1 == 0 or R2 == 0:
        # 曲率半径为 0 没有物理意义，且 -2/R 会除零，直接按无效组合跳过
        return None, float("nan")
    g = float(calc_stab(round_trip_matrix(L, R1, R2)))
    if abs(g) >= 1.0:
        return None, g
    return 1.0 - abs(g), g


def waist_at_m1(L, R1, R2):
    """M1 处束腰参考值（mm），仅作对照，不参与优化目标。"""
    try:
        w = float(calc_w(round_trip_matrix(L, R1, R2),
                         WAVELENGTH_MKM * 1e-6, 1))
    except (ValueError, ZeroDivisionError):
        return float("nan")
    return w * 1e3


def load_start_point():
    """从例子方案文件读初始参数（M1 R、腔长 L、M2 R）。"""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        schema = json.load(f)
    vals = {}
    for elem in schema["elements"]:
        if elem["type"] == "ElemCurveMirror":
            vals[elem["label"]] = elem["params"]["R"]["value"]
        elif elem["type"] == "ElemEmptyRange":
            vals["L"] = elem["params"]["L"]["value"]
    return vals["L"], vals["M1"], vals["M2"]


# ---------------------------------------------------------------- 搜索
def coarse_scan(start):
    """粗扫：遍历全部参数网格，返回 (最优组合, 扫描总数, 稳定组合数)。

    裕度最大值 1.0 对应 g = 0，在参数空间里是一整片曲面而不是孤立点，
    所以只比裕度会撞上“第一个 g=0 的格点”（常落在搜索范围边缘）。
    并列时取离初始参数最近的一组：改动最小的才是最可用的最优解。
    """
    grids = [np.arange(lo, hi + step / 2, step)
             for _, _, lo, hi, step in PARAMS]
    ranges = [hi - lo for _, _, lo, hi, _ in PARAMS]
    best = None  # (margin, L, R1, R2)
    total = stable = 0
    for L in grids[0]:
        for R1 in grids[1]:
            for R2 in grids[2]:
                total += 1
                margin, _ = stability_margin(float(L), float(R1), float(R2))
                if margin is None:
                    continue
                stable += 1
                cand = (margin, float(L), float(R1), float(R2))
                if best is None or _better(cand, best, start, ranges):
                    best = cand
    return best, total, stable


def _dist(point, start, ranges):
    """归一化欧氏距离：衡量候选参数离初始参数有多远。"""
    return sum(((p - s) / r) ** 2 for p, s, r in zip(point[1:], start, ranges)) ** 0.5


def _better(cand, best, start, ranges):
    """裕度更大者胜；裕度并列（差值 < 1e-9）时离初始参数更近者胜。"""
    if cand[0] > best[0] + 1e-9:
        return True
    if abs(cand[0] - best[0]) <= 1e-9:
        return _dist(cand, start, ranges) < _dist(best, start, ranges)
    return False


def fine_search(center, steps, start):
    """在最优点附近细搜：每轮步长缩小 10 倍，共两轮；并列规则与粗扫一致。"""
    ranges = [hi - lo for _, _, lo, hi, _ in PARAMS]
    best_margin, best_L, best_R1, best_R2 = center[0], center[1], center[2], center[3]
    cur_steps = list(steps)
    for _ in range(2):
        improved = False
        # 在中心 ±1 步内以当前步长重扫
        lo = [max(PARAMS[j][2], c - s) for j, (c, s) in
              enumerate(zip((best_L, best_R1, best_R2), cur_steps))]
        hi = [min(PARAMS[j][3], c + s) for j, (c, s) in
              enumerate(zip((best_L, best_R1, best_R2), cur_steps))]
        grids = [np.arange(lo[j], hi[j] + cur_steps[j] / 2, cur_steps[j])
                 for j in range(3)]
        for L in grids[0]:
            for R1 in grids[1]:
                for R2 in grids[2]:
                    margin, _ = stability_margin(float(L), float(R1), float(R2))
                    if margin is None:
                        continue
                    cand = (margin, float(L), float(R1), float(R2))
                    best = (best_margin, best_L, best_R1, best_R2)
                    if _better(cand, best, start, ranges):
                        best_margin, best_L, best_R1, best_R2 = cand
                        improved = True
        cur_steps = [s / 10.0 for s in cur_steps]
        if not improved:
            break
    return best_margin, best_L, best_R1, best_R2


def main():
    L0, R1_0, R2_0 = load_start_point()
    margin0, g0 = stability_margin(L0, R1_0, R2_0)
    print("初始参数（bin/examples/spherical_symm.rez）：")
    print("  腔长 L = {} cm，M1 曲率半径 R1 = {} cm，M2 曲率半径 R2 = {} cm"
          .format(L0, R1_0, R2_0))
    print("  稳定参数 g = {:.4f}，稳定裕度 = {:.4f}".format(g0, margin0))

    print("\n粗扫范围：L {}–{} cm（步长 {}），R1/R2 {}–{} cm（步长 {}）…"
          .format(PARAMS[0][2], PARAMS[0][3], PARAMS[0][4],
                  PARAMS[1][2], PARAMS[1][3], PARAMS[1][4]))
    best, total, stable = coarse_scan((L0, R1_0, R2_0))
    print("  扫描 {} 组组合，其中稳定 {} 组，不稳定 {} 组已自动跳过"
          .format(total, stable, total - stable))
    print("  粗扫最优：L = {} cm，R1 = {} cm，R2 = {} cm，裕度 = {:.4f}"
          .format(best[1], best[2], best[3], best[0]))

    fine = fine_search(best, [PARAMS[0][4], PARAMS[1][4], PARAMS[2][4]],
                       (L0, R1_0, R2_0))
    print("细搜后最优：L = {:.2f} cm，R1 = {:.2f} cm，R2 = {:.2f} cm，"
          "裕度 = {:.4f}".format(fine[1], fine[2], fine[3], fine[0]))

    margin1, g1 = stability_margin(fine[1], fine[2], fine[3])
    w0 = waist_at_m1(L0, R1_0, R2_0)
    w1 = waist_at_m1(fine[1], fine[2], fine[3])
    print("\n优化前后对照表（目标：稳定裕度最大）：")
    print("  {:<16} {:>12} {:>12}".format("参数", "优化前", "优化后"))
    for name, before, after in zip(PARAM_NAMES,
                                   (L0, R1_0, R2_0), fine[1:]):
        print("  {:<16} {:>10.2f} cm {:>10.2f} cm".format(name, before, after))
    print("  {:<16} {:>12.4f} {:>12.4f}".format("稳定参数 g", g0, g1))
    print("  {:<16} {:>12.4f} {:>12.4f}".format("稳定裕度", margin0, margin1))
    print("  {:<16} {:>10.2f} mm {:>10.2f} mm".format("M1 处束腰（参考）", w0, w1))
    print("\n结论：裕度从 {:.4f} 提高到 {:.4f}（+{:.1f}%），"
          "优化后仍稳定。".format(margin0, margin1,
                                  (margin1 - margin0) / margin0 * 100))


if __name__ == "__main__":
    main()
