# reZonator 工程层（Phase 1–4）

Python 层：`.rez` 解析、单位换算、无头 CLI 封装、工程检查、Solves 与
功率求解器、鬼像/红光/导出。只用标准库 + numpy/scipy（导出另可用
ezdxf，若未装则用手写最小 DXF 写入器）。光学计算一律复用原生 C++
（`rezonator --headless`），Python 不重算 ABCD；晶体内部的 q(z)
演化是 Python 侧的 GRIN 演化器（与 C++ `ElementGrin` /
`ElementThermalLens` 的定义逐项核对过，见下）。

## 目录

| 文件 | 内容 |
|---|---|
| `rezeng/rez.py` | `.rez` 读写（原样保留未知键、`schema_version`、各参数 `unit`） |
| `rezeng/units.py` | 单位换算（`.rez` 参数单位别名 ↔ SI） |
| `rezeng/cli.py` | `run_headless` / `run_headless_file`：调 `--headless` 批量求值 |
| `rezeng/eng.py` | side-car `<file>.rez.eng.json` 读写与格式校验 |
| `rezeng/checks.py` | LIDT / 孔径截断 / 面包板检查，`run_checks()` |
| `rezeng/solves.py` | Pickup 与束腰 Solves，`apply_pickup()` / `solve_waist_size()` / `solve_waist_position()` / `apply_solution()` |
| `rezeng/qevolve.py` | 晶体内部 q(z) GRIN 演化器（`crystal_slices()` / `evolve_element()`），与 C++ 核对过 |
| `rezeng/power.py` | 功率求解器：模式 A（Rigrod）、模式 B（三维重叠积分）、热透镜闭环、扫描、高阶模判据 |
| `rezeng/shg.py` | SHG 倍频：腔内/腔外、走离角、绿光噪声预警，`shg_pump_scan()` |
| `rezeng/jones.py` | 琼斯偏振矩阵：波片/偏振片/法拉第/双折射晶体、SW 往返矩阵与本征偏振，`round_trip_jones()` / `jones_report()` |
| `rezeng/dispersion.py` | GDD/TOD 往返累加器（含 SESAM 参数接口），`round_trip_dispersion()` |
| `rezeng/mopa.py` | MOPA / 再生放大 Frantz-Nodvik 链路，`resolve_chain()` / `run_chain()` |
| `rezeng/merit.py` | 评价函数（与 C++ OptimizerWindow 逐项对齐），`evaluate_result()` / `evaluate_batch()` |
| `rezeng/optimizer.py` | 两阶段优化器：向量化差分进化 + Nelder-Mead 精修，`optimize()` / `optimize_with_discrete()` |
| `rezeng/zones.py` | 双稳区 1D 扫描 + Brent 边界精修，`scan_zones()` |
| `rezeng/catalog.py` | 标准件库 + Snap（屈光度最近邻）+ 锁定后重优化，`snap_radius()` / `snap_and_reoptimize()` |
| `rezeng/jacobian.py` | 装调雅可比与螺丝圈数指南：解析 3×3 增广 ABCD、单镜回中指南，`jacobian()` / `screw_guide()` |
| `rezeng/ghosts.py` | 鬼像/标准具扫描：表面反射率剪枝、标准具 FSR/调制深度、一阶鬼像 q(z) 追迹与烧镜点检查（3×3 失调光轴），`scan_ghosts()` / `scan_etalons()` / `trace_ghost()` |
| `rezeng/redlight.py` | 632.8 nm 红光对照：Sellmeier 系数库、冷腔态重算、冷腔失稳时回退到外部 HeNe 注入追迹，`redlight_report()` |
| `rezeng/export.py` | 镀膜表 / `.zmx` / `.dxf` 导出：`coating_table()` / `to_zmx()` / `validate_zmx()` / `thin_lens_spot_check()` / `to_dxf()` / `validate_dxf()` |
| `rezeng/thermal.py` | 热传导：柱坐标 (r,z) FD 求解器（spsolve）、端帽分段 k/α、板条 2D (x,y)、OPD 拟合与闭环、Fox-Li 相位板，`solve_rod()` / `thermal_report()` |
| `rezeng/fracture.py` | 热应力与断裂：平面应变 σ_r/σ_θ/σ_z、最大拉应力、裕度与红线，`stress_field()` / `fracture_report()` |
| `rezeng/foxli.py` | Fox-Li 衍射引擎：混合传播子（BL-ASM + 两步菲涅耳）、分步晶体、往返迭代、D4σ M²，`CavityOperator()` / `foxli_iterate()` / `foxli_report()` / `opd_f_th_to_cli_F()` / `spot_ascii()` / `spot_png()` |
| `run_foxli.py` | Fox-Li 的命令行入口：`python3 run_foxli.py --rez <file.rez> [--eng <file.eng.json>] [--max-rounds N] [--thermal-power P] [--thermal-eng <thermal.eng.json>] [--paraxial] [--png <spot.png>]` |
| `demo_foxli.py` | 用户真实腔体交叉验证 + 2/5/10 W 热 M² 退化曲线演示 |
| `run_thermal.py` | 热传导 + 断裂的命令行入口：`python3 run_thermal.py --rez <file.rez> [--eng <file.eng.json>] [--pump 2,5,10] [--w-l-um 498]` |
| `demo_thermal.py` | 用户真实腔体 TL1 + 示例参数的 2/5/10 W 热演示 |
| `run_ghosts.py` | 鬼像/标准具扫描的命令行入口：`python3 run_ghosts.py <file.rez> [side-car] [--wavelength NM]` |
| `run_redlight.py` | 红光对照的命令行入口：`python3 run_redlight.py <file.rez> [side-car] [--red-nm NM] [--w0 MM] [--double-pass]` |
| `run_export.py` | 导出的命令行入口：`python3 run_export.py <file.rez> [side-car] [--coating] [--zmx OUT.zmx] [--dxf OUT.dxf] [--thin-lens-check] [--no-ezdxf]` |
| `rezeng/reverse.py` | 逆向拟合：腔外实测光斑反推热透镜屈光度 D_th，`fit_plane()` / `fit_thermal_lens()` / `synthetic_measurements()` |
| `run_optimizer.py` | 优化器 / Snap 的命令行入口（JSON 配置文件，打印 JSON 结果） |
| `run_zones.py` | 双稳区扫描的命令行入口：`python3 run_zones.py --rez <file.rez> [--d-max 12] [--n-points 300] [--f-mm 230]` |
| `run_montecarlo.py` | 蒙特卡洛的命令行入口：`python3 run_montecarlo.py --rez <file.rez> [--n 1000] [--chunk 250] [--seed 0]` |
| `run_reverse.py` | 逆向拟合的命令行入口：`python3 run_reverse.py --rez <file.rez> --points-T "30:0.21,200:0.39,800:1.33"` |
| `demo_montecarlo.py` | 用户真实腔体 + 示例公差带的 N=1000 蒙特卡洛演示 |
| `demo_reverse.py` | 用户真实腔体 + 合成测量数据的逆向拟合演示（3 点恢复 + 2 点远场简并陷阱） |
| `demo_optimizer.py` | 优化器 + Snap + 双稳区全流程演示（原型复现、束腰目标、用户腔体多目标优化、Snap、Zone 扫描） |
| `run_checks.py` | 检查的命令行入口：`python3 run_checks.py <file.rez> [side-car]` |
| `run_solves.py` | Solves 的命令行入口：`python3 run_solves.py pickup|waist-size|waist-position …` |
| `run_power.py` | 功率求解器的命令行入口：`python3 run_power.py --rez <file.rez> [--toc-scan]` |
| `run_shg.py` | SHG 的命令行入口：`python3 run_shg.py --rez <file.rez> [--pump 2,3,5,7,10]` |
| `run_jones.py` | 琼斯 + 色散的命令行入口：`python3 run_jones.py --rez <file.rez> [--eng <file.eng.json>]` |
| `run_mopa.py` | MOPA 链路的命令行入口：`python3 run_mopa.py --osc <osc.rez> [--eng <chain.eng.json>]` |
| `demo_solves.py` | 用户真实腔体的 Pickup + 束腰 Solve 端到端演示（输出到 /tmp） |
| `demo_power.py` | 用户真实腔体 + 示例参数的 P_out–P_pump 曲线与 T_opt 扫描演示 |
| `demo_shg.py` | 用户真实腔体 + 插入的 LBO 晶体 + 示例参数的 SHG 演示（NCPM 与 CPM 各跑一次） |
| `demo_jones.py` | 用户真实腔体 + 示例参数的琼斯往返矩阵、GDD/TOD 与波片角度调谐演示 |
| `demo_mopa.py` | 示例两级 MOPA 链（单通放大 + 再生放大）逐通能量演示 |
| `tests/` | `unittest` 测试（`python3 -m unittest discover -s tests`） |

协议（stdin/stdout JSON、批量求值、失败语义）见
`~/workspace/rezonator2-phase1-protocol.md`；`.rez` 格式与元件调查见
`~/workspace/rezonator2-phase1-notes.md`。

## Side-car 格式（v1）

`.rez` 文件里**没有任何**元件带孔径、LIDT 或安装座尺寸数据——工程
数据只能放在 side-car `<file>.rez.eng.json` 里，**绝不能往 `.rez` 写未知键**
（应用自己的保存会丢掉它们）。除 `format_version` 外所有字段可选；
缺失的数据不设默认值，检查报 `nodata`。

```json
{
  "format_version": 1,
  "laser": {
    "pulse_energy_J": 0.001,
    "pulse_duration_s": 1e-8,
    "rep_rate_Hz": 1000,
    "notes": "示例数据，非真实参数"
  },
  "board": {
    "board_mm": [600, 600],
    "hole_pitch_mm": 25
  },
  "elements": {
    "M1": {
      "aperture_diameter_mm": 25.4,
      "lidt_J_per_cm2": 2.0,
      "lidt_conditions": {"wavelength_nm": 1064, "pulse_duration_s": 1e-8},
      "mount": {
        "footprint_mm": [50, 50],
        "board_x_mm": 100,
        "board_y_mm": 100
      }
    }
  }
}
```

- `laser`（腔级）：`pulse_energy_J` 是每脉冲能量；`pulse_duration_s`、
  `rep_rate_Hz` 目前只作记录（LIDT 值本身是脉宽相关的，填在这里作条件备注）。
- `elements` 按元件 **label** 索引；side-car 里引用了 `.rez` 中不存在的
  label 时，报告 `warnings` 里会提示，该条数据被忽略，不崩溃。
- `lidt_conditions` 是自由格式的备注（波长、脉宽、脉冲数等），不参与计算。
- `mount.board_x_mm` / `board_y_mm` 是安装座 footprint **中心**在板面上的
  坐标，板面原点在板的一角，板面范围 `[0, W] × [0, D]`。

### `pulse_energy_J` 的含义（重要）

LIDT 检查里的能量是**入射到该元件的每脉冲能量**，不是输出能量。驻波腔
内循环脉冲能量与输出脉冲能量不同——使用者按元件填写（例如端镜按透过
功率折算，腔内镜按循环功率填写）。连续（CW）激光没有“每脉冲能量”，
不要编一个数填进去：留空，该项报 `nodata`。

## 检查

光斑半径一律取 `--headless` 输出的 `beam` 列表（每元件 `w_T_mm` /
`w_S_mm`）。谐振腔失稳或光线泵（RayVector）时没有光斑半径，光学检查
报 `nodata`。

### 1. LIDT 损伤检查（`lidt`）

椭圆高斯光束峰值通量：

```
F = 2E / (π · w_T · w_S)          （w 换算成 cm，F 单位 J/cm²）
```

手工核对：w_T = w_S = 0.2 mm = 0.02 cm，E = 1 mJ = 1e-3 J 时，
F = 2·1e-3 / (π·0.02²) = 2e-3 / 1.2566e-3 ≈ **1.59 J/cm²**。

分级（比值 r = F / LIDT）：

| r | 状态 |
|---|---|
| r > 1.0 | `fail` |
| 0.8 < r ≤ 1.0 | `warn` |
| r ≤ 0.8 | `ok` |

阈值常量：`checks.LIDT_WARN_RATIO = 0.8`，`LIDT_FAIL_RATIO = 1.0`。

### 2. 孔径截断检查（`aperture`、`aperture_total`）

圆孔对高斯光束的截断损耗：

```
loss = exp(-2 · a² / w²)     a = 孔径半径，w = max(w_T, w_S)（保守取大者）
```

手工核对：a = w 时 loss = exp(-2) ≈ 13.5%；a = 0（堵死）时 loss = 100%。

- 逐元件：loss > 1% → `warn`，否则 `ok`（`APERTURE_WARN_SINGLE = 0.01`）。
- 总计：`total = 1 - Π(1 - loss_i)`，> 2% → `warn`
  （`APERTURE_WARN_TOTAL = 0.02`）。总计只统计同时有孔径数据和光斑
  半径的元件；一个都没有时总计报 `nodata`。本项没有 `fail` 级——
  截断损耗是效率问题，不是损伤问题。

### 3. 面包板检查（`board_bounds`、`board_overlap`、`board_grid`）

二维轴对齐矩形几何，假设：

- 每个安装座是矩形 footprint，不考虑高度干涉（上下叠放）与光路遮挡；
- 板面坐标原点在板的一角，`board_mm = [宽, 深]`；
- 安装座中心应落在孔距网格点上。

| 检查 | 规则 |
|---|---|
| `board_bounds`（逐元件） | footprint 超出板面 → `fail`，`value` 为最大超出量（mm）；在板内 → `ok` |
| `board_overlap`（逐对安装座） | 两 footprint 重叠（正面积）→ `fail`，`value` 为重叠面积（mm²）；仅贴边（零面积）不算重叠 |
| `board_grid`（逐元件） | 安装座中心偏离最近网格点 > 1e-6 mm → `warn`，`value` 为两轴中较大的偏移量 |

缺失数据：没有安装座数据 → 对应项 `nodata`；没有 `board_mm` →
`board_bounds` 报 `nodata`（重叠检查不需要板尺寸，仍可算）；没有
`hole_pitch_mm` → `board_grid` 报 `nodata`；少于两个带位置的安装座 →
`board_overlap` 报一条 `nodata`。

## 报告格式

`run_checks(rez_path, eng_path=None)` 返回：

```json
{
  "version": 1,
  "rez_path": "...",
  "eng_path": "...",
  "checks": [
    {"id": "lidt:M1", "element": "M1", "kind": "lidt",
     "status": "ok", "value": 1.59, "limit": 2.0, "unit": "J/cm^2",
     "message": "peak fluence ..."}
  ],
  "summary": {"ok": 12, "warn": 3, "fail": 1, "nodata": 9, "total": 25},
  "warnings": ["side-car lists unknown element 'Ghost' ..."]
}
```

- `value` / `limit` 为数值或 `null`（`nodata` 时一般为 `null`）；
  `value` 的单位在 `unit` 里（`J/cm^2`、`fraction`、`mm`、`mm^2`）。
- `summary` 是各状态的计数；`warnings` 是 side-car 格式问题与未知
  label 提示（不致命）。
- CLI 退码：只要产出报告就是 0（哪怕有 `fail`，那是数据不是错误）；
  只有读文件失败、CLI 失败等硬错误才非零。

## Solves

求解一律调 `--headless` 批量求值（光学不重算），解写回 `.rez`
时保留原有 unit、`schema_version` 与未知键。求解变量必须是**未被
驱动的元件参数**（被 `formulas` / `param_links` 驱动的参数 CLI
会拒绝改写，`check_overridable` 会先报错）。

### 1. Pickup（`apply_pickup`）

把“某元件参数跟随另一参数”的关系写成**原生**机制，UI 打开后
关系仍然生效、保存不丢：

- 源参数挂到一个全局参数（已链接时复用该全局参数；否则新建
  `PK_E<源元件序号>_<参数>`，如 `PK_E1_L`）；
- 从参数挂到另一个全局参数 `PK_E<从元件序号>_<参数>`；
- 全局参数之间写一条 `formulas`：`code = "k * <源全局> + <b_si>"`
  （Lua 表达式，SI 单位；`k` 无量纲，`b` 按从参数的单位给出），
  `param_deps = [源全局]`；
- 两条 `param_links` 把全局参数分别复制进源、从元件参数（链接按
  SI 值复制，单位自动换算）。

`formulas` 只能驱动**全局参数**（`SchemaReaderJson::readFormula`），
所以元件到元件的 Pickup 必须经过全局参数中转——这正是应用自己
的 `global_params.rez` 例子用的做法。源、从参数必须是同一量纲
（长度/角度/无量纲）；从参数已被别的 formula/link 驱动时报错，
不静默覆盖；链式 Pickup 允许（一个 Pickup 的从值可以做下一个
Pickup 的源）。`verify_pickup()` 做纯检查：公式、两条链接、全局
参数存在，且存入的从值等于 `k·源+b`。

**加载语义（重要，已对真实程序验证）：公式在加载时不重算**
——`Formula::calculate` 只在依赖参数变化时触发。所以
`apply_pickup` 写入的是**一致快照**（存入的从值已等于
`k·源+b`），加载后光学与原来完全一致；在 UI 里改源全局参数时，
公式重算、链接传播，跟随关系生效；但只改源全局参数的存值而不
更新从值时，从值会 stale，直到在 UI 里碰一下源参数。求解写回
（`apply_solution`）因此拒绝被驱动的参数，不会只写一半。

示例（用户真实腔体）：`d4.L = 0.5 * d1.L + 90.862702 mm`
（b 按当前值算出，使腔体光学不变），生成 `PK_E1_L` /
`PK_E7_L` 与公式 `0.5 * PK_E1_L + 0.09086270242273697`；
CLI 加载后 g_T 与原来 12 位小数一致；源改为 340 mm（从值同步
改为 260.862702 mm）时，光学与直接改 `d1` / `d4` 的结果一致。

### 2. 束腰 Solves（`solve_waist_size` / `solve_waist_position`）

变量是某元件的某参数（如 `d1:L` 或 `M2:R`），目标是某**光束段**
的束腰：

- `element` 指定光束段：取该元件**离开后**的光束段（即该元件
  `(w, R)` 所属的段）；同一段内任意元件推出的束腰一致，跨聚焦
  元件后会变（协议 §3/§4）。
- 束腰由该段元件的 `(w, R)` 按高斯公式推导（`waist_from_wr`，
  与协议 §4 一致），**不用**顶层 `waist` 字段冒充指定位置的束腰。
- 位置坐标：`s = 0` 在第一个元件的平面，沿元件列表方向增大；
  元件的平面是它的**出口平面**（带 `L` 的元件含自身长度）。
  目标可以是绝对 `s`（mm），也可以是 `("ref", label, offset_mm)`
  （相对某元件平面的位置，`offset > 0` 为下游）。用户腔体总长
  1171.318 mm。
- `plane` 选 `"T"` 或 `"S"`（像散腔两者不同，分别求解）。

求解器：先在搜索区间上做一次批量扫描（默认 17 点，一个 CLI
调用），再：

| 扫描结果 | 做法 |
|---|---|
| 有变号括号 | 对离当前值最近的括号用 Brent 法（`scipy.optimize.brentq`）；多括号时警告并列出其余括号 |
| 无变号 | 在最优可行区间上对 `\|残差\|` 做有界最小化（`minimize_scalar`，Brent） |
| 残差处处≈0 | 退化情形（如平端镜处束腰位置恒为 0）：返回当前值并警告 |
| 全程不可行 | 无解，`converged: false` |

**不可行点**：失稳（`stable: false`，无本征模）与被 CLI 拒绝的
值（参数越界、被驱动）都当作不可行，绝不作为解；扫描中遇到会
警告计数。收敛判据：`|残差| ≤ 1e-9 × max(|目标|, 1e-3)`（mm），
括号宽度 `xtol = 1e-12`（变量的 SI 单位）。达不到判据时返回最优
点并报告 `converged: false`，不编造解。结果结构：

```json
{"kind": "waist_size", "variable": {"label": "d1", "alias": "L", "unit": "mm"},
 "element": "M1", "plane": "T", "target": "w0 = 0.12 mm",
 "solved_value": 0.36544872414414764, "solved_value_display": 365.44872414414766,
 "residual_mm": 4.95e-15, "residual_rel": 4.1e-14,
 "iterations": 6, "evaluations": 23, "converged": true,
 "warnings": ["1 of 17 scan points are infeasible ..."], "brackets_si": [[0.364375, 0.3675]]}
```

`solved_value` 是 SI 单位，`solved_value_display` 是参数原单位；
`evaluations` 是 CLI 求值点数（扫描 + 迭代），`iterations` 是
迭代次数。写回用 `apply_solution(data, variable, solved_value_si)`：
依赖图检查 + 原单位换算 + CLI 守卫（长度 ≥ 1e-6 m，R/F ≠ 0）。

用户腔体实测（`demo_solves.py`）：

| 求解 | 解 | 独立 CLI 复核残差 |
|---|---|---|
| `w0` 在 M1 处 = 0.12 mm，变量 `d1` | d1 = 365.4487 mm | 4.1e-14 相对误差 |
| M4 段束腰在 s = 1100 mm，变量 `d1` | d1 = 296.3413 mm | 9.7e-14 相对误差 |
| M4 段束腰在 M4 平面，变量 `d1` | **无解**（残差在稳定区内恒 > 0，趋近稳定边界时才 → 0；最优 d1 = 373.125 mm，残差 0.126 mm） | — |
| `w0` 在 M1 处 = 0.15 mm，变量 `d1` | 两解（d1 ≈ 253 mm 与 342.04 mm），取离当前值近的 342.04 mm | < 1e-6 相对误差 |

搜索区间默认是当前值的 [0.5×, 2×]（长度参数；负值镜像，不跨
0；角度 ±5°），可用 `bounds_si` 指定；长度下界不得低于 1e-6 m，
R/F 区间不得跨 0。

## 功率求解器（Phase 2 block 1）

`rezeng/qevolve.py` + `rezeng/power.py`，入口 `pump_scan()` /
`toc_scan()`（命令行 `run_power.py`，演示 `demo_power.py`）。
增益晶体就是 `.rez` 里的热透镜/GRIN 元件（用户真实腔体里 TL1 即
Nd:YVO4 晶体，L=27 mm）；全部泵浦/晶体参数来自 side-car 的
`gain_and_pump` 一节，缺失字段报 `PowerError`（不编默认值）。

```json
"gain_and_pump": {
  "gain_element": "TL1",
  "crystal": {"material": "Nd:YVO4", "sigma_em_cm2": 15.6e-19,
              "tau_f_us": 90.0, "alpha_p_per_cm": 10.0},
  "pump": {"lambda_p_nm": 808.0, "P_pump_W": 5.0, "w_p0_um": 200.0,
           "z_p0_mm": 13.5, "Mp2": 1.2, "eta_p": 0.95,
           "profile": "gaussian"},
  "cavity": {"T_oc": 0.10, "L_i": 0.02, "eta_mode": null},
  "thermal": {"F0_mm": null, "kappa_th_per_W": null,
              "kappa_th_T_per_W": null, "kappa_th_S_per_W": null,
              "anchor_F_ref_mm": null, "anchor_P_ref_W": null,
              "P_nom_W": 5.0, "eta_h": 0.24, "dn_dT_per_K": 3.0e-6,
              "K_c_W_per_mK": 5.1}
}
```

| 参数 | 含义 | 单位/备注 |
|---|---|---|
| `gain_element` | 增益晶体元件 label（缺省为唯一的 ElemThermoLens/ElemGrinLens） | 必须存在于 `.rez` |
| `crystal.sigma_em_cm2` | 受激发射截面 σ_em | cm² → m² |
| `crystal.tau_f_us` | 上能级寿命 τ_f | µs → s |
| `crystal.alpha_p_per_cm` | 泵浦吸收系数 α_p | /cm → /m；沿 z 按 exp(−αz) 分布，归一化 ∫zp dz = 1 |
| `pump.lambda_p_nm` / `w_p0_um` / `z_p0_mm` / `Mp2` / `eta_p` | 泵浦波长 / 束腰半径 / 束腰位置（晶体入口起算）/ 光束质量 / 泵浦效率 | w_p(z) = w_p0·√(1+((z−z_p0)/z_R)²)，z_R = πw_p0²/(Mp2·λ_p) |
| `pump.profile` | `gaussian` 或 `tophat` | 顶帽泵浦在晶体横截面内均匀 |
| `cavity.T_oc` / `L_i` | 输出耦合透过率 / 腔内往返损耗（不含 T_oc） | δ = T_oc + L_i |
| `cavity.eta_mode` | 模式 A 的空间重叠效率（缺省由模式 B 的阈值斜率反推，见下） | (0, 1] |
| `thermal.*` | 热透镜模型（见“热透镜锚定”） | κ_T/κ_S 可独立给 |

### q(z) 演化器与 C++ 的核对结论

动手前逐项读过 `src/core/Elements.cpp`（`ElemCurveMirror` /
`ElemGrinLens` / `ElemThermoLens` / `ElemEmptyRange`）与
`GrinCalculator::solve_n2`，并在用户真实腔体上用 CLI 验证：

- 光线矢量是几何量 `(r, θ)`；元件矩阵都是**空气到空气**的。
- CLI `beam` 列表里某元件的 `(w, R)` 取的是该元件的**出口面、空气侧**；
  镜面元件的条目是**反射后**的值。验证：把任一 CLI 条目经下一元件的
  完整矩阵传播，得到下一元件的 CLI 条目（8 个相邻对 × T/S 两面，
  w 与 R 相对误差均 < 1e-6；测试 `test_chain_consistency`）。
- GRIN 段梯度常数 `γ = sqrt(n2/n0)`，`n2` 由 `F` 经 `solve_n2` 的
  精确二分法求出（**不是**薄透镜近似 `γ = 1/sqrt(n·F·L)`——对用户
  晶体该近似偏 0.9%：精确值 γ=8.5569 /m，n2=158.155 /m²）。
- 段内子矩阵即 C++ `calcSubmatrices` 的 `TS1_ = M_grin(z)·R_in`，
  `R_in = [[1,0],[0,1/n0]]`；出口折射 `R_out = [[1,0],[0,n0]]` 把介质
  侧 q 映回空气侧（`q_air = q_med/n0`）。反例对照：若漏掉 `R_out`
  （把介质侧 R 当空气侧），TL1 出口 R 与 CLI 差一个因子 ~n0，测试
  `test_air_side_convention_negative_control` 会失败。
- `q` 用 ABCD 定律演化，波长取**当地**波长（介质内 `λ = λ0/n`）；
  T/S 各自独立演化；自由空间段用标准 `[[1,L],[0,1]]` 矩阵。
- 演化器算出的 TL1 出口 `(w, R)` 与 CLI 一致（相对误差 ~1e-15，
  测试 `test_tl1_exit_matches_cli`）；扫描中每点都用当时的变异 F
  重算并复核（`exit_rel_err` > 1e-6 即出警告）。

### 模式 A（Rigrod 快算）

按 spec §4.2.1：

```
P_th = π·h·ν_p·(w_p² + w_l²)·δ / (4·σ_em·τ_f·η_p·η_abs)
P_out = [T_oc/(T_oc+L_i)]·η_q·η_abs·η_mode·(P_pump − P_th)   (P_pump > P_th)
η_abs = 1 − exp(−α_p·L),  η_q = λ_p/λ_l
```

`w_l` 取晶体各片 `sqrt(w_T·w_S)` 的轴向平均；`w_p` 取泵浦束腰
`w_p0`。`η_mode` 缺省时由模式 B 反推：对高斯泵浦，
`η_mode = w_l²(w_l²+2w_p²)/(w_p²+w_l²)²`（由阈值处微分斜率严格导出，
使模式 A 与模式 B 在阈值处一致）；顶帽泵浦
`η_mode = tanh(w_p²/w_l²)·w_l²/w_p²`。side-car 可显式覆盖。

### 模式 B（三维重叠积分）

晶体切 N 个轴向片（Gauss-Legendre 节点，`w_T(z)`/`w_S(z)` 取演化器
输出，椭圆高斯模分布）；泵浦沿 z 按 `exp(−αz)` 吸收。往返增益
`Γ(P_circ) = (2σ τ_f P_abs/(hν_p))·O(P_circ)`，其中

```
O(P) = ∫ r_p(x,y,z)·φ_mn(x,y,z) / (1 + Σ_k 2·P_k·φ_k/I_sat) dV
```

用 `brentq` 求解 `Γ(P_circ) = δ` 的自洽单向腔内功率，
`P_out = T_oc·P_circ`；低于阈值时 `P_circ = 0`（不是错误）。
积分用 numpy 向量化：高斯泵浦走 2D Gauss-Hermite（φ_00 的
`exp(−u²−v²)` 即求积权重），顶帽泵浦走极坐标 Gauss-Legendre。

**SW 腔因子 2（关键）：** 驻波腔的饱和分母必须用
`1 + (I_+ + I_−)/I_sat = 1 + 2·P_circ·φ/I_sat`——正反两个方向的光
都饱和反转。漏掉因子 2 会使斜效率虚高一倍。
`I_sat = h·ν_l/(σ_em·τ_f)`，用**激光**频率（不是泵浦频率）。

### 热透镜闭环与锚定语义

```
1/F_th(P) = 1/F_0 + κ_th·η_abs·P_pump
```

κ_th 的解析顺序（`thermal_kappa()`，先到先用）：

1. **显式 κ**：`kappa_th_per_W`（或 `kappa_th_T/S_per_W` 独立给 T/S；
   只给其一时另一面用 `kappa_th_per_W` 补）。
2. **标定点**：`anchor_F_ref_mm` @ `anchor_P_ref_W`（某泵浦功率下
   实测的 F）反推 κ。
3. **逆向锚定**（缺省）：假设当前 `.rez` 的 F 对应额定泵浦功率
   `P_nom_W`，反推 κ，并在结果里出警告。**这是没有标定数据时的缺省
   做法，F(P) 曲线完全取决于这个假设。**
4. **纯物理估算**：`κ_th ≈ η_h·(dn/dT)/(2π·K_c·w_p²)`，仅当
   `eta_h`/`dn_dT_per_K`/`K_c_W_per_mK` 三者都给了才用；缺失任一即
   不用（不编默认值）。
5. **无热模型**：κ=0，F 在所有泵浦功率下保持 `.rez` 值（并出警告）。

每档泵浦功率：更新 TL1 的 F（经 CLI `mutations` 批量下发，**一次进程
算多点**，不要每点起进程），重算光斑，再算功率。T/S 的 κ 不同时，
CLI 变异用平均屈光度 `1/F_cli = (1/F_T + 1/F_S)/2`（原生元件只有一个
F；差异 > 1% 时出警告）。

**失稳处理：** CLI 返回 `stable: false`（`ok: true`、`beam`/`waist`
为 null）时该点 `P_out = 0` 并标记 `flag: "thermal_instability"`，
扫描继续，绝不抛异常中断。注意：用户真实腔体的 g(F) 是**非单调**
的（见演示），失稳点可以出现在扫描中间、两侧又恢复稳定。

### 扫描

- `pump_scan(data, eng, pump_powers_W)`：P_out–P_pump 曲线，一次 CLI
  批量调用算全部 F；每点同时给模式 A、模式 B、高阶模净增益。
- `toc_scan(data, eng, P_pump_W, toc_values)`：固定泵浦功率扫 T_oc，
  找最大 P_out 对应的 `T_opt`（一次 CLI 调用，损耗 δ 变化不影响光路）。

### 高阶模判据

在 TEM_00 饱和的反转下算 TEM_10 / TEM_01 的往返净增益
（`higher_order_gains()`，`net10`/`net01` = 增益指数 − δ）；任一
> 0 即标“多模起振阈值功率”（`multimode_threshold()` 在扫描点之间
线性插值）。等效 M² 用嵌套双模平衡估算（`two_mode_m2()`）：对每个
高阶模求解其与 TEM_00 同时满足 `Γ = δ` 的功率占比，
`M²_x = 1 + 2·P_10/(P_00+P_10+P_01)`（同理 y）；求解失败时退回增益
裕度启发式并注明 `method`。注意：这里所有模式共用同一 `L_i`，没有
计入高阶模额外的孔径/衍射损耗，所以算出的多模阈值是**偏低的保守
估计**。

### 验证（tests/test_power.py，共 38 个）

- **演化器对 CLI**：TL1 出口与链式一致性（< 1e-6），含空气侧约定的
  反例对照；GRIN 常数与 F↔n2 往返。
- **三极限一致性**（模式 B vs 模式 A，误差 < 0.5%）：
  顶帽大泵浦（w_p=10·w_c）下 O(0) 与解析值一致（2.9e-4）；
  极细激光束（w_c=w_p/100）阈值为均匀泵浦解析阈值的一半（0.5002）；
  小信号近阈值：模式 A 阈值处的 Γ_0 = δ（2.1e-4），1.05 倍阈值处
  P_out 一致到 0.3%，阈值处微分斜率一致到 1.5%。
  （远离阈值时分布模型比 Rigrod 切线略超线性：2 倍阈值处 +9.7%，
  5 倍阈值处 +21%——这是分布饱和与均匀饱和的模型差异，不是 bug。）
- **基准算例**（Nd:YVO4：σ_e=15.6e-19 cm²、τ_f=90 µs、w_p=200 µm、
  w_c=180 µm、δ_0=2%、T_oc=10%）：I_sat = 1.33e7 W/m²（1.33 kW/cm²）；
  **P_th ≈ 0.12 W（吸收）/ 0.15 W（入射，10 mm 晶体 α_p=1.5/cm）**；
  模式 A 斜效率 ≈ 34%（该晶体长度下），恒 < 量子亏损上限 75.9%。
  **注意：Gemini 评审里写的基准范围 P_th 1.2–2.0 W、斜效率 52–58%
  与它自己的公式不一致**——按 spec §4.2.1 的公式代入同一组参数得
  到的就是 ~0.12 W（两种独立推导复核过，见测试注释），评审的数值
  约 10 倍偏高（可能是 σ 的数量级笔误）；斜效率 52–58% 则需要
  η_mode≈0.87，而分布模型严格导出的高斯泵浦 η_mode=0.695。实现
  忠实按公式算，测试断言公式值并 guard 住“修公式去凑 1.2 W”的回退。
- 多模阈值（基准算例）：2.87 W 入射泵浦（18.7 倍阈值）；30 倍阈值
  处 M²≈1.065（双模平衡）。
- 失稳点处理（mock CLI）：F 跌破阈值的点标 `thermal_instability`、
  P_out=0，扫描不中断；批量调用次数断言（一次 CLI 调用算全部点）。

### 演示（用户真实腔体 + 示例参数）

`python3 engineering/demo_power.py`（`--with-m2` 另算 M²）。
**全部泵浦/晶体参数都是示例**（`tests/data/example-power.eng.json`：
Nd:YVO4，σ=15.6e-19 cm²，τ=90 µs，α_p=10/cm，808 nm 泵浦，
w_p0=200 µm，z_p0=晶体中点，Mp2=1.2，η_p=0.95，T_oc=10%，L_i=2%；
热透镜逆向锚定 P_nom=5 W）。2026-11-19 跑出的结果：

| P_pump (W) | F (mm) | w_l (µm) | P_th_B (W) | P_out_B (W) | 状态 |
|---|---|---|---|---|---|
| 0.5 | 2300 | — | — | 0 | 热致失稳 |
| 1.0 | 1150 | — | — | 0 | 热致失稳 |
| 2.0 | 575 | 526 | 0.616 | 0.789 | ok |
| 3.0 | 383 | 452 | 0.428 | 1.580 | ok |
| 5.0 | 230 | 500 | 0.547 | 2.619 | ok |
| 7.0 | 164 | — | — | 0 | 热致失稳 |
| 10.0 | 115 | 429 | 0.373 | 6.007 | ok |

要点：**低泵浦（≤1 W）时腔不稳定**（弱热透镜下 g≈−1.1…−1.5），
2–5 W 稳定，7 W 附近再次失稳（g≈+1.14），10 W 又恢复稳定——
g(F) 非单调，失稳带不止一个（独立 Python 往返矩阵复核与 CLI 的
g 值逐点一致）。T_opt 扫描（5 W）：T_opt=15%，P_out_max=2.631 W
（T_oc=10% 时 2.619 W，最优区很平）。高阶模净增益全程约 −0.09，
多模阈值在 0.5–10 W 内未达到（单模）。**以上数值随逆向锚定假设而
变，不是真实激光的预测**；真实泵浦功率/晶体掺杂/σ/τ/T_oc/L_i
和 F(P) 标定点仍需用户提供。

## SHG 倍频模块（Phase 2 block 2）

`rezeng/shg.py`，入口 `shg_pump_scan()`（命令行 `run_shg.py`，
演示 `demo_shg.py`）。只支持 SW 驻波腔（模式 B 本身就是驻波腔
求解器）；RR/SP 拓扑待 Phase 2 块 3（MOPA）时随单程链路一并处理。

### 模型

单程小信号转换系数（Boyd–Kleinman，聚焦高斯光束）：

```
P_2w = K · P_w²,   eta_small = K · P_w
K = 16π²·d_eff²·L_eff / (ε₀·c·n_ω²·n_2ω·λ_ω³) · h(0, ξ) · sinc²(Δk·L/2)   [1/W]
ξ = L_eff·λ_ω / (2π·w0²),   h(0, ξ) = arctan(ξ)² / ξ
L_eff = min(L_cryst, L_a),  L_a = π·w0 / ρ
```

前置因子经两种独立推导验证（测试 `test_K_matches_plane_wave_limit` /
`test_K_ppln_hand_computed`）：在准直极限（ξ→0，h→ξ）下它精确还原
平面波结果；PPLN（d_eff=14 pm/V，L=20 mm）算得 K=0.0186 /W，与手算
一致。`h(0, ξ)` 在 ξ≈1.4（L≈2.8·z_R，束腰在晶体中心）取最大值约
0.65。耗尽修正用平面波精确解 `η_1pass(P) = tanh²(√(K·P))`（小信号
时回到 K·P，大功率时饱和于 1）。

**腔内倍频**（SW 腔，每往返过晶体两次）：

```
δ_SHG(P_circ) = 2 · η_1pass(P_circ)
P_2w = 2 · P_circ · η_1pass(P_circ)   （两个方向的绿光之和）
F(P) = Γ(P) − [δ_linear + δ_SHG(P)] = 0，Γ(P) 为模式 B 往返增益指数
```

按 Gemini 评审结论用**单变量根求解器嵌套**（`brentq`，约 10 次
求值，精度 1e-9 量级），不用松弛迭代（高转换效率下松弛迭代会震荡）。
Γ(P) 随 P 单调递减、总损耗随 P 单调递增，根唯一；K→0 时严格退化
回无 SHG 的模式 B（测试 `test_degenerates_to_mode_b`）。低于阈值时
`P_circ = 0`（不是错误）。

**腔外倍频**：先按无 SHG 解出基频（模式 B），再单向转换一次，
`P_2w = P_out · η_1pass(P_out)`，不反哺腔内损耗。

### 晶体元件：必须用 ElemPlate

`.rez` 里的倍频晶体必须是 **`ElemPlate`**（真实介质板，C++ 矩阵
`[[1, L/n], [0, 1]]`）。reZonator 的 `ElemMediumRange` 在矩阵里
完全忽略 `n`（行为等同于等长真空段），用它做晶体会算错晶体内部
光斑——`resolve_shg()` 会明确报错并提示改用 ElemPlate。晶体内部
光斑由 q(z) 演化器给出（`shg_beam_in_crystal()`；出口与 CLI 的
一致性每点都复核，`exit_rel_err` > 1e-6 即出警告）。聚焦参数用
该段的束腰 `w0`（束腰在晶体内时）或晶体内的平均光斑（束腰在晶
体外、光束近似准直时）；`w_eff = √(w0_T·w0_S)`（圆等效，文档注明
的近似——用户腔体像散仅 2.65%，影响可忽略）。

### CPM 与 NCPM（严格区分）

|  | CPM（临界相位匹配，角度调谐） | NCPM（非临界，温度调谐） |
|---|---|---|
| 走离角 | 输入 `walkoff_mrad`（ρ > 0，必填） | ρ = 0（给 `walkoff_mrad` 即报错） |
| 失配因子 | Δk = 0（角度已调准；或显式给 `delta_k_per_m`） | `sinc²(ΔkL/2)`，Δk 由温度失谐导出：ΔkL/2 = 1.3916·ΔT·L / (ΔT·L 接收带宽)；ΔT·L 等于接收带宽乘积时曲线在半高处 |
| 绿光光斑 | 走离面内展宽（见下） | 无椭圆度畸变（M² = 1） |

`phase_matching` 未给时按走离角推断（ρ > 0 → CPM，否则 NCPM，
并出警告）。显式 `delta_k_per_m` 在两种模式下都优先于温度模型。

### 走离角与绿光光斑（只做诊断，不反哺基频 ABCD）

```
L_a = π·w0 / ρ（孔径长度）；L_eff = min(L_cryst, L_a)
w_2ω,∥ ≈ √((w_ω/2)² + (ρ·L_cryst/2)²)，w_2ω,⊥ ≈ w_ω,⊥/2
椭圆度 = w_2ω,∥ / w_2ω,⊥；M²_∥ ≈ √(1 + (ρ·L/(2·w_ω))²)（启发式估计）
```

长晶体不得高估效率：L ≫ L_a 时 K 饱和于 L_a（测试
`test_long_crystal_saturates_at_aperture_length`）。走离面由
`walkoff_plane`（`T`/`S`，缺省 `T`）指定；NCPM 时 ρ=0，椭圆度
只剩基频自身的 T/S 像散比。

### 绿光噪声（Green Problem）预警

仅腔内倍频时评估。机制（Baer 1986）：纵模之间的和频混合耦合
各纵模，多模运转 + 高转换效率时绿光出现大幅度噪声。判据是
**启发式风险带**（不是精确阈值，评估结果里明确注明）：单程
转换效率 η_1pass < 5% 为 low，5–15% 为 elevated，≥15% 为 high；
单频运转（`single_frequency: true`）或腔外倍频时风险为 low
（无模间和频耦合 / 无反馈）。缓解方向：单频运转、降低转换效率。

### Side-car 字段（`nonlinear_shg`）

```json
"nonlinear_shg": {
  "enabled": true,
  "mode": "intracavity",              // "intracavity" | "extracavity"
  "crystal_element_id": "LBO_1",      // .rez 里的 ElemPlate label
  "material": "LBO",                  // LBO | BBO | KTP | PPLN（仅作标注）
  "length_mm": 15.0,                  // 缺省用 .rez 元件的 L；不一致 > 1% 出警告
  "d_eff_pm_V": 0.85,                 // 必填（启用时缺失即报错）
  "n_omega": 1.60, "n_2omega": 1.61,  // 必填，不用内置表默认值
  "phase_matching": "NCPM",           // "CPM" | "NCPM"（缺省按走离角推断）
  "walkoff_mrad": 7.2,                // CPM 必填；NCPM 给了即报错
  "walkoff_plane": "T",               // "T" | "S"，缺省 "T"
  "delta_T_C": 0.0,                   // NCPM：偏离最佳温度
  "temp_acceptance_C_cm": 4.0,        // NCPM：FWHM 接收带宽 ΔT·L（°C·cm）
  "delta_k_per_m": null,              // 显式相位失配（优先于温度模型）
  "single_frequency": false,          // 绿光噪声评估输入
  "wavelength_2omega_nm": null        // 缺省 λ_ω/2
}
```

缺失的必填字段（`d_eff`、折射率、晶体元件、CPM 的走离角）报
`SHGError` 并点名，不编默认值。`rezeng.shg.MATERIALS` 里有
LBO/BBO/KTP/PPLN 的典型文献值（d_eff、折射率、走离角、温度接收
带宽），**仅供参考**：求解器从不自动套用，需用显式的
`fill_typical()` 填入（演示与快速上手用），且使用前应按晶体
数据手册核对。

### 验证（tests/test_shg.py，共 41 个）

- **公式**：h(0, ξ) 极限与峰值；K 的平面波极限一致性与 PPLN 手算值；
  耗尽公式小信号极限与饱和。
- **退化一致性**：K=0 时腔内求解与模式 B 的 P_circ 一致到 1e-9；
  小 K 微扰下绿光 ≈ 2·K·P_circ²（低耗尽极限）；brentq 求值 ≤ 40 次、
  自洽方程残差 < 1e-6。
- **单调性**（固定光路）：P_pump 增大 → P_2w 单调增；T_oc 增大 →
  腔内绿光下降；腔外转换不反哺基频。
- **CPM vs NCPM**：NCPM ρ=0 时无椭圆度畸变、M²=1；失谐 ΔT 增大时
  效率按 sinc² 下降（ΔT·L = 接收带宽时恰为一半）；长晶体效率饱和
  于 L_a。
- **绿光噪声**：低/中/高三档、单频与腔外时风险为 low。
- **真机 CLI**（用户腔体 + 插入的 ElemPlate）：演化器出口与 CLI
  一致（< 1e-6）、`element_matrix(ElemPlate)` 与 CLI 链式一致；
  5 W 泵浦点绿光 > 0 且 P_circ 小于无 SHG 值；扫描冒烟测试。

### 演示（用户真实腔体 + 插入的 LBO 晶体 + 示例参数）

`python3 engineering/demo_shg.py`。在用户腔体 M1 后插入 ElemPlate
LBO_1（15 mm，n=1.60，d1 缩短 15 mm，总几何长度不变；修改后的腔
体只写 /tmp）；NCPM（恒温炉，ΔT=0）与 CPM（走离角 7.2 mrad）各
跑一次 P_pump = 2/3/5/7/10 W。**全部参数都是示例**（增益按
`example-shg.eng.json`，热透镜逆向锚定 P_nom=5 W）。

| P_pump (W) | P_circ (W) | P_out (W) | P_2w (W) | η_1pass | w_xtal (µm) | 椭圆度 NCPM/CPM | 状态 |
|---|---|---|---|---|---|---|---|
| 2 | 6.07 | 0.607 | 0.0028 | 0.02% | 91 | 1.00 / 1.53 | ok |
| 3 | 15.36 | 1.536 | 0.0114 | 0.04% | 116 | 0.99 / 1.36 | ok |
| 5 | 27.69 | 2.768 | 0.0351 | 0.06% | 119 | 0.98 / 1.33 | ok |
| 7 | — | — | — | — | — | — | 热致失稳 |
| 10 | 59.91 | 5.991 | 0.0177 | 0.01% | 366 | 1.00 / 1.04 | ok |

要点：**P_2w 在 10 W 反而低于 5 W——这是该示例腔体的真实物理，
不是求解器问题**：热透镜使模场变化，F=115 mm（10 W）时晶体处束腰
胀到 ~366 µm（5 W 时 ~119 µm，已直接对 CLI 核对），ξ 与 K 塌下来
的速度超过了 P_circ 增长的速度。固定光路时 P_2w 对 P_pump 单调
（见上）。CPM 与 NCPM 的绿光功率几乎相同（L_a≈44 mm > L=15 mm，
走离角尚未限制效率），区别只在绿光椭圆度（CPM 在 5 W 时 1.33，
NCPM 只有基频像散比 ~0.98–1.00）。绿光噪声全程 low（η_1pass
< 0.1%）。**以上数值随逆向锚定假设与示例晶体参数而变，不是真实
激光的预测**；真实的非线性晶体材料/长度/相位匹配方式、d_eff、
走离角或温控条件仍需用户提供。

## 琼斯偏振矩阵（Phase 2 block 3）

`rezeng/jones.py`：2×2 复琼斯矩阵沿光路连乘，与 ABCD 独立并行
（偏振不改变 ABCD，ABCD 也不改变偏振）。基底为实验室 (T, S)
横向轴；光束正向传播为 +z。

### 元件类型（side-car `elements_ext.<label>.jones`）

| 类型 | 参数 | 矩阵 |
|---|---|---|
| `waveplate` | `retardance_rad`（Γ）、`fast_axis_deg`（θ） | `R(θ)·diag(e^{+iΓ/2}, e^{-iΓ/2})·R(−θ)`，快轴超前 +Γ/2；λ/2 即 Γ=π，λ/4 即 Γ=π/2。HWP 把偏振角 α 映为 2θ−α（关于快轴线的反射） |
| `polarizer` | `Tp`、`Ts`（功率透过率）、`angle_deg` | `R(θ)·diag(√Tp, √Ts)·R(−θ)`；布儒斯特片即 Tp=1、Ts=0 的偏振片 |
| `faraday` | `rotation_deg`（φ） | `R(φ)`，非互易 |
| `birefringent` | `retardance_rad`（Γ）、`fast_axis_deg`（θ） | 与 `waveplate` 同形（双折射晶体） |
| `mirror` | `m_T`、`m_S`（默认 −1、−1） | `diag(m_T, m_S)`；Fresnel 记号下 m_T = −r_p、m_S = r_s（p 轴反射翻转带来的负号），side-car 存的是实验室基底的 (m_T, m_S)，不要直接填 r_p/r_s |

`mirror` 规格只能放在反射镜元件上，其他规格只能放在非反射镜
元件上（错配会报错）。没有 `jones` 数据的元件按单位矩阵（透射）
或理想反射镜处理；也可以用 `insertions`（`{"after": <label>,
"jones": <spec>}`）在不改 `.rez` 的前提下插入虚拟元件（如波片）。

### 反向传播坐标翻转（最大风险点）

端镜反射后光束沿 −z 传播。为使反向横向基底仍与 −z 右手正交，
保持 S 轴不动、T 轴翻转：`(x_b, y_b) = (−x, y)`。物理直线在
反向基底里位于 −θ；用 `M = diag(−1, 1)` 共轭回实验室基底后，
波片的反向矩阵等于其正向矩阵本身 `M·J(−θ)·M = J(θ)`——与矩阵
对称性 `J^T = J` 一致。Lorentz 互易性在实验室基底里给出本模块
实际使用的紧凑规则：

- **互易元件：`J_back = J_forward^T`**（转置）；
- **法拉第旋光器：`J_back = J_forward`**（不转置，非互易）。

波片/偏振片/双折射晶体矩阵对称，转置无影响；真正区分互易旋光
器与法拉第旋光器的是旋光器：互易旋光器反向为 `R(−φ)`，往返抵
消（`R(−φ)R(φ) = I`）；法拉第反向仍为 `R(φ)`，往返加倍
（`R(2φ)`）。直接逆序相乘而不做坐标变换，会把隔离器算成透明
元件——这是本块最容易错的地方，已用测试锁定
（`tests/test_block3.py`：法拉第 45° + 偏振片 0° 往返损耗为 1，
即隔离器行为；若反向误取转置会得到损耗 0）。

### 往返矩阵与功率闭环

SW 腔（元件表 `[M1, …, M4]`）：`J_rt = J_M1 · B · J_M4 · F`，
`F` 为内部元件正向乘积（按光路顺序，最先遇到的最右），`B` 为
内部元件反向乘积（逆序 + 上述反向规则）；端镜 M1、M4 各只出现
一次。SP 为单程乘积，RR 为一圈乘积。`eigen_polarization(J_rt)`：
模最大的特征值 λ_max 对应本征向量即腔内自洽偏振态，偏振损耗
`1 − |λ_max|²`。该损耗以可选参数 `extra_loss` 注入功率求解器
（`power.py` 的 `mode_a_threshold` / `mode_a_output` /
`solve_p_circ` / `pump_scan` / `toc_scan` 均已接受；`extra_loss=0`
时与旧调用完全一致）。

注意：SW 腔里单个互易元件正反两次的乘积是 `J^T·J`，对波片即
延迟加倍——QWP 往返后等效 HWP（测试锁定），HWP 往返后为 −I
（自抵消）。因此波片角度调谐演示用 QWP：QWP + 偏振片的往返损
耗为 `sin²(2θ)`。

### 验证（tests/test_block3.py，琼斯部分）

单位矩阵、HWP(0°)/QWP(0°) 已知矩阵、HWP(45°) 旋转、QWP 两次
=HWP、偏振片投影 `J²=J`、Malus 定律、双偏振片往返损耗 0.75、
波片+偏振片无损耗（本征态被波片旋转到 45°）、法拉第 45° 往
返 `=R(90°)`、互易旋光器往返 `=I`、法拉第+偏振片隔离器损耗 1、
用户腔体 + 示例双折射 Γ=0.15 rad（往返 `diag(e^{+i0.15},
e^{−i0.15})`，损耗 0）。

### 演示（用户真实腔体 + 示例参数）

`python3 engineering/demo_jones.py`。示例数据见
`tests/data/example-jones.eng.json`（TL1 双折射 Γ=0.15 rad，
GVD 245 fs²/mm；M1 SESAM；M4 啁啾镜——**全部是示例**）：
往返矩阵 `diag(e^{+i0.15}, e^{−i0.15})`，偏振损耗 0；QWP 角度
调谐（偏振片在 d1，Tp=1、Ts=0）：

| θ（°） | 偏振损耗 | P_out（模式 A，5 W 泵浦） |
|---|---|---|
| 0 | 0.00 | 1.653 W |
| 15 | 0.25 | 0.499 W |
| 22.5 | 0.50 | 0.275 W |
| 30 | 0.75 | 0.180 W |
| 45 | 1.00 | 0.128 W |

损耗为 `sin²(2θ)`。注意：损耗 →1 时不存在自洽偏振态，标量
`extra_loss` 模型已到极限（仍给出一个小 P_out），完整矢量模型
在 45° 应给出零输出。真实的波片/偏振片/法拉第参数仍需用户提供。

## 色散累加（GDD/TOD，Phase 2 block 3）

`rezeng/dispersion.py`：`round_trip_dispersion(data, eng)`。
side-car `elements_ext.<label>` 里按元件给色散系数：

- 透射元件：`gvd_fs2_per_mm`、`tod_fs3_per_mm`，按物理厚度
  `L`（取该元件 `.rez` 里的 `L` 参数并换算为 mm）累加；
- 反射元件：`gdd_fs2`、`tod_fs3`（单次反射量），按往返反射
  次数累加；`role` 可标 `chirped_mirror` / `SESAM` 等。

**SW 腔计数**：端镜（首、尾元件）1 次，腔内其他元件各 2 次
（折叠镜 M2、M3 与晶体都在内）；SP、RR 各 1 次。输出往返总
GDD（fs²）与 TOD（fs³）及逐元件明细。SESAM 参数
（`modulation_depth`、saturation_fluence_uJ_per_cm2）一并进
side-car，只作接口记录——本块不实现调 Q/锁模动力学。色散系数
放在无 `L` 参数的元件上会跳过并告警（不静默套用）。

验证：手工小算例、SW 计数（端镜 1、晶体 2）、SP 计数、缺 L
告警。演示（`demo_jones.py` 后半段）：用户腔体 + 示例参数，
GDD = 2×27×245 − 150 − 300 = **12780 fs²**，TOD = 2×27×310 +
500 + 1200 = **18440 fs³**，与手算一致。真实的色散镜 GDD 与
SESAM 参数仍需用户提供。

## MOPA / 再生放大链路（Phase 2 block 3）

`rezeng/mopa.py`：Frantz-Nodvik 链路编排器，零 C++ 改动。数据
模型（side-car `mopa_chain`）：

```json
{
  "seed_source": {"pulse_energy_J": 5e-5, "pulse_duration_s": 40e-12,
                  "rep_rate_Hz": 120000},
  "stages": [
    {"stage_id": "amp_1", "rez_file": "mopa_amp_sp.rez", "passes": 2,
     "gain_element": "CRY",
     "gain_medium": {"material": "Nd:YVO4", "J_sat_J_per_cm2": 0.12,
                     "small_signal_gain_G0": 4.5, "recovery_time_us": 90,
                     "n2_m2_per_W": 1e-19}},
    {"stage_id": "regen_1", "rez_file": "mopa_regen_sw.rez", "passes": 10,
     "gain_element": "CRY",
     "gain_medium": {"material": "Nd:YAG", "J_sat_J_per_cm2": 0.66,
                     "initial_stored_energy_J": 0.005},
     "round_trip_loss": 0.04}
  ]
}
```

- `seed_source`：种子能量/脉宽/重频（`type` 可写
  `oscillator_ref`；暂不接振荡器功率求解器，只取种子参数）。
- 每级：`stage_id`、`rez_file`（相对 side-car 所在目录，或绝对
  路径）、`passes`（单通级 = 通数，再生级 = 往返数）、
  `gain_element`（增益晶体元件 label）、`gain_medium`
  （`material`、`J_sat_J_per_cm2`，以及 `small_signal_gain_G0`
  或 `initial_stored_energy_J` 二选一；可选 `recovery_time_us`、
  `n2_m2_per_W`）、再生级的 `round_trip_loss`（每往返损耗，
  作用于两通之间）。
- 增益介质两种给定方式：给 `small_signal_gain_G0` 时初始储能
  由模面积反推（`E_stored = J_sat·ln G0·πw²`，w 取该级晶体处
  光斑）；给 `initial_stored_energy_J` 时反推 G0。若两者都给且
  不一致（偏差 >10%）会告警，不静默选一个。

计算：每级先调一次 `--headless` 取增益晶体处的光斑
（`w_T`、`w_S`，SP 拓扑直接复用；SW 再生腔取稳态光斑）。
每通把脉冲能量转为径向能量密度
`J_in(r) = [2·E_in/(π·w²)]·exp(−2r²/w²)`（椭圆光斑用
`w² = w_T·w_S`），按径向环带应用 Frantz-Nodvik 方程
`J_out(r) = J_sat·ln[1 + G_0(r)·(exp(J_in(r)/J_sat) − 1)]`，
其中局域 `G_0(r) = exp(γ(r))`，γ 由该环带剩余储能定；每通
后更新剩余储能供下一通使用（环带局域耗尽，积分后总能量守恒
精确成立——输出能量 ≤ 种子 + 各级储能，不会算出永动机）。
环带用 `u = r²` 上的 Gauss-Legendre 网格（64 环，能量重构
误差 ~1e-8）；`exp(J_in/J_sat)` 用 `expm1` 的稳定分支
（`x > 50` 时不溢出）。

每通出口复用 Phase 1 的 LIDT 检查（`checks.py`，
`lidt_fluence_J_per_cm2`，峰值通量 `2E/(π·w_T·w_S)` 对该级
side-car 里的晶体 LIDT；无 LIDT 数据时记 `nodata`，不报错）。
B 积分每通顺带算：`B = (2π/λ)·n_2·I_pk·L`，`I_pk` 为高斯脉
冲峰值强度（峰值因子 `√(4 ln 2/π)`，取该通出口能量），
**>3 rad 时警告**自聚焦/光谱畸变（无 `n2` 时 B=0，不告警）。
再生放大按通数循环 + 每通损耗：SW 级每往返 2 通，两通之间乘
`(1 − round_trip_loss)`；储能耗尽时增益逐通下降（G0 → 1）。

### 验证（tests/test_block3.py，MOPA 部分）

环带能量重构、F-N 极限（`G0=1` 恒等、小信号 ≈G0 倍、深饱和
渐近 `J_out → J_in + J_sat·ln G0` 误差 1e-13 量级、大通量不溢
出）、单通小信号增益、双通增益耗尽、多通储能守恒（饱和种子
下输出 ≤ 种子 + 储能）、再生 5 往返（10 通，往返增益单调下
降、储能单调减少）、B 积分警告触发（`n2=1e-17` 时 B≫3）、
每通 LIDT（`fail`/`nodata`）、链路校验错误。

### 演示（示例两级链）

`python3 engineering/demo_mopa.py`。链路见
`tests/data/example-mopa.eng.json`，各级 `.rez` 在
`tests/data/`（`mopa_amp_sp.rez`：SP，种子束腰 200 µm，
CRY 为 ElemPlate L=10 mm、n=1.82，CLI 核对 w=0.221 mm；
`mopa_regen_sw.rez`：SW，R=1000 mm 对称腔，CLI 核对稳定
g=−0.293、CRY 处 w=0.369 mm）。**全部参数都是示例**：

| 级 | 通 | E_in → E_out | 增益 |
|---|---|---|---|
| amp_1（Nd:YVO4，G0=4.5） | 1 | 50.0 → 166.9 µJ | 3.338 |
| amp_1 | 2 | 166.9 → 328.7 µJ | 1.970 |
| regen_1（Nd:YAG，5 mJ 储能） | 1–2 | 328.7 µJ → 4.35 mJ | 4.767 / 2.773 |
| regen_1 | … | 逐通增益下降 | … |
| regen_1 | 20 | 11.74 → 11.90 mJ | 1.013 |

总输出 **11.90 mJ**（50 µJ 种子 → 238 倍；储能上限
47.54 mJ，守恒成立）；B 积分总计 0.896 rad（<3，无警告）；
LIDT：再生级第 4 通起 warn、第 7 通起 fail（示例 LIDT
5.0 J/cm²，通量达 5.56 J/cm²）——这是示例参数下的真实预警，
不是求解器问题。注意：重频 120 kHz 是种子的，再生级 5 mJ/
脉冲在 120 kHz 下相当于 600 W 泵浦，实际再生级重频要低得
多；演示看的是单脉冲链路，不是平均功率。真实的 MOPA 种子
与放大级晶体参数仍需用户提供。

## 评价函数与优化器（Phase 3 block 1）

评价函数与 C++ `OptimizerFunction`（`src/math/OptimizerFunction.h/.cpp`）
逐项对齐，同一 merit 定义、两端可互相验证。设操作数 `V_k`、目标
`T_k`、权重 `W_k`：

| 目标 | C++ 定义 | Python（`rezeng/merit.py`） | 说明 |
|---|---|---|---|
| 光斑目标 `beam_T` / `beam_S`（某元件处） | `W·((w−T)/T)²` | 相同 | σ 取目标值本身，即相对误差 |
| 像散 `astigmatism`（某元件处） | `d=\|w_T−w_S\|`，`ref=max(max(w_T,w_S),1e-12)`，`W·(d/ref)²` | 相同（`ref` 下限按 mm 计为 1e-9） | 目标为 0 |
| 稳定性居中 `stability_center` | `W·(g_T²+g_S²)` | 相同 | 目标 g=0，σ=1 |
| 束腰 `waist`（某元件所在段） | ——（C++ 无此目标） | `W·((w0−T)/T)²`，w0 由该元件 (w,R) 经 `solves.waist_from_wr` 推导 | Python 侧扩展 |
| 输出功率 `power_out`（可选） | —— | `W·((P_out−T)/T)²`，P_out 用解析模式 A（`power.mode_a_output`，泵浦束腰 w_p0、增益处几何平均模半径） | 每次评估零额外 CLI 调用；不耦合模式 B 重叠积分（那会使每次评估都变成一次完整功率求解） |
| 失稳罚项（\|g\|≥1 任一方向） | `1e4 + 1e5·(over_T²+over_S²)` | **`1e6 + 1e4·max(0, max(\|g_T\|,\|g_S\|)−1)²`** | 唯一有意不同处：Python 按 Gemini 评审建议取更大的基底、更缓的斜率；两者同为连续阶跃+斜坡（绝非纯常数死区），都远高于稳区内可达的 merit，且斜率都指回 \|g\|<1 |
| 失败变异 / 非有限值 / 非有限 merit | `1e9`（`PENALTY_UNSTABLE`） | 相同 | |

变量绑定 `.rez` 参数（label + alias），在归一化 [0,1] 空间优化
（与 C++ `normValue` / `denormValue` 一致，越界钳制到 [0,1]；
Nelder-Mead 单纯形可能越界，评估器在入口处统一钳制，见下）。
连续变量给 `{"label", "alias", "min_si", "max_si"}`（SI 单位）；
离散变量给 `{"label", "alias", "candidates_si": [...]}`，外层枚举
组合（上限：纯离散 50000、混合 2048，与 C++ 一致），每组跑一次
完整两阶段优化。被 `param_links` / `formulas` 驱动的参数不可作
变量——`BatchEvaluator` 在建构时就用 `check_overridable` 报错，
而不是让 CLI 每点都拒绝（实测教训：仓库自带的
`bin/examples/spherical_symm.rez` 里 M1.R/M2.R 都由全局参数 R0
链接，CLI 会以 "parameter 'M1.R' is driven by a link" 拒绝一切
改写；原型复现因此用去链接的 fixture
`tests/data/spherical_symm_free.rez`）。

两阶段优化器（`rezeng/optimizer.py`，`optimize()`）：

- **阶段一**：向量化差分进化
  `scipy.optimize.differential_evolution(vectorized=True,
  updating='deferred')`，种群回调一次打包成 1 个 CLI 批量请求
  （种群 10×D，默认 40 代；`tol=0` 跑满代数；`seed` 固定可复现）。
  种群规模以 scipy 的 `popsize` 计（种群 = popsize × D）。
- **阶段二**：Nelder-Mead 精修（与 C++ OptimizerWindow 同一算法），
  `xatol=1e-4`、`fatol=1e-5`、`maxfev=300`、`adaptive=True`。
- 不用 basin-hopping（梯度局部求解器遇稳区边界跳变发散），不用
  SLSQP（数值梯度 + 不连续约束易崩溃）。

等式约束用**参数化降维**，不加罚项：`fixed_total` 约束列出若干
长度参数与总和，最后一个成员由 `L_n = L_total − ΣL_i` 导出、永
不作为自由变量，精确满足；导出值非法（≤1e-6 m 或非有限）时该点
直接判不可行（merit 1e9，不发 CLI 请求）。非线性 Solve 目标转
为高权重 merit 项（权重放大 10~100 倍），**绝不在优化器每次
迭代里嵌套 Brent 求根**；优化结束后再单独跑一次 Phase 1 Solve
做最终微调锁定。

退化最优的 tie-break（与 C++ 文档和 Phase 0 原型同一规则：merit
近乎相等时取离起点最近者）：先在全部已评估点中取 merit 在
`TIE_TOL=1e-9` 内且离起点最近者；当最优 merit 基本为零且含
稳定性居中目标时，再用罚函数最小二乘
（残差 `[g_T, g_S, 1e-3·(x−x0)]`，`scipy.optimize.least_squares`）
沿 g=0 表面向起点爬行——只在缓存里挑点可能离真正的最近表面
点很远。**实测修正**：原型网格搜索报的最优 (L=90, R1=45, R2=60)
是网格受限的局部结论；连续优化找到的最近表面点是
(L=83.95, R1=R2=49.17)，归一化距离 0.023（原型点为 0.124），
两者裕度同为 1.00（|g|≈1e-9）。

实测（`demo_optimizer.py`，示例目标/权重）：

- 原型复现：裕度 0.72 → 1.000000，(83.946, 49.175, 49.175) mm，
  1521 次评估 / 332 次 CLI 调用 / 10.4 s。
- 束腰目标：用户腔体 w0(M1)=0.12 mm → d1=365.4502 mm，与 Phase 1
  Brent 解 365.4487 mm 一致（Δ=0.0015 mm）。
- 用户腔体多目标（像散@M4 ×10、稳定居中 ×1、光斑@M4 0.21 mm
  ×1；变量 M2 倾角、d1、M3 R）：merit 1.719 → 1.183；M2 倾角
  2.5° → 1.711°，**独立复现了 Phase 0 算出的 1.5° 修正方向**；
  M4 像散 0.0056 mm → 约 5×10⁻⁶ mm（基本归零）；M3 R 触及边界
  −350 mm；剩余 merit 主要来自稳定性居中（g≈0.81）与光斑
  （0.317 vs 目标 0.21 mm）的权衡。

## 标准件 Snap（Phase 3 block 1）

吸附用**屈光度空间**最近邻（`rezeng/catalog.py`）：

    d(R, R_std) = |1/R − 1/R_std|        （平镜 1/R = 0）

线性 R 距离是错的：平镜 R=∞ 与 R=10000 mm 光学上几乎等价，
线性距离却无穷大；而 R=50 与 R=60 线性只差 10 mm，屈光度却差
20%（实测：d(∞,10000)=1e-4 /mm，d(50,60)=0.0033 /mm）。
符号保留：凹镜不吸附到凸镜（平镜无符号，两侧皆可）。

内置库 `STOCK_CATALOG` 是**标注为示例的精选曲率序列**
（±25/38.1/50/75/100/125/150/200/250/300/500/750/1000/2000/
5000/10000 mm 与平镜，`EXAMPLE-STOCK`），不是真实供应商目录；
真实库存用 `load_catalog_csv()` 导入 CSV（字段 `vendor,
part_number, R_mm, diameter_mm, coating`；`R_mm` 可写 `inf` 表
平镜）。Snap 时可按口径（`min_diameter_mm`）、供应商、镀膜
子串过滤。

锁定 R 后，保留相邻腔长为自由变量，用**原 merit 函数**跑
Nelder-Mead 重优化 100~200 步（既补偿臂长又完成评价函数再验
证），输出 Snap 前后对比表（Δw、Δg、ΔMerit）。
`snap_and_reoptimize()` 的 "before" 是当前腔体原样（原始曲率、
当前腔长，一次无改写 CLI 调用），"after" 是吸附 + 重优化结果。

实测（用户腔体，示例目标）：M3 R −450 → −500 mm（EX-R-500，
屈光度距离 2.22e-4 /mm）；重优化 d2/d3 后 merit 1.718 → 1.380，
g (0.929, 0.921) → (0.833, 0.828)，M4 光斑 (0.206, 0.211) →
(0.228, 0.230) mm，像散 0.0056 → 0.0018 mm。注意 d2/d3 顶到了
设定边界（400/15 mm），说明补偿方向是缩短臂长、边界本身在起
作用。

## 双稳区扫描（Phase 3 block 1）

泵浦功率通过热透镜起作用：屈光度 `D_th = 1/f_th` 随泵浦功率
（近似）线性增加，腔体先后穿过 Zone I 与 Zone II，中间隔着失
稳带。`scan_zones()`（`rezeng/zones.py`）固定其余变量，在
`D_th ∈ [0, D_max]` 上取 200~500 点、一次 CLI 批量请求扫描，
再对每个 g 穿过 ±1 的变号区间用 Brent 法（`xtol=1e-9`）精确定
位 `D_crit`。

像散会使 T/S 稳区错位，因此**必须同时输出** `zones_T`、`zones_S`
与严格交集 `zones_common`（只按单方向判定是错的）。输出结构
（JSON）：

    {"lens": {"label": "TL1", "alias": "F"},
     "d_range": [0.0, 12.0], "n_points": 300,
     "boundaries": [{"axis": "T"|"S", "g": +1|-1, "D_th": ...,
                     "f_mm": ..., "bracket": [lo, hi]}],
     "zones_T": [{"id": "Zone_T_1", "D_range": [lo, hi],
                  "f_range": [f_hi, f_lo]}],
     "zones_S": [...],
     "zones_common": [{"id": "Zone_I"|"Zone_II", ...}],
     "trajectory": [{"D_th", "g_T", "g_S",
                     "w_sesam_T_mm", "w_sesam_S_mm",
                     "w_crystal_T_mm", "w_crystal_S_mm",
                     "is_stable"}],
     "working_point": {"D_th", "f_mm", "zone", "is_stable"} | None,
     "n_cli_calls": int}

`f_range` 为 `[1/D_hi, 1/D_lo]`（mm；D=0 对应无限焦距，记为
`None`）；`power_range` 仅当调用方给出 `D_th → 泵浦功率` 映射时
才出现；`opt_path` 可选，嵌入优化器评估点的 `(D_th, merit)`
序列供轨迹叠加。`w_sesam_*` 为 SESAM/端镜处光斑（默认 M1），
`w_crystal_*` 为热透镜/增益元件处光斑（默认由
`find_gain_element` 定位）。

实测（用户腔体，D_th ∈ [0,12] /m，300 点，154 次 CLI 调用）：

| 边界 | D_th (/m) | f (mm) |
|---|---|---|
| g_T=−1 / g_S=−1（Zone I 下沿） | 0.973 / 1.001 | 1028.0 / 998.7 |
| g_T=+1 / g_S=+1（Zone I 上沿） | 4.640 / 4.669 | 215.5 / 214.2 |
| g_S=+1 / g_T=+1（Zone II 下沿） | 7.294 / 7.302 | 137.1 / 137.0 |
| g_S=−1 / g_T=−1（Zone II 上沿） | 11.262 / 11.270 | 88.8 / 88.7 |

Zone I（交集）：D ∈ [1.001, 4.640] /m，f ∈ [215.5, 998.7] mm；
Zone II（交集）：D ∈ [7.302, 11.262] /m，f ∈ [88.8, 137.0] mm。
当前工作点 F=230 mm（D=4.348 /m）在 Zone I 内、靠近上沿
（D=4.640）。与 Phase 2 的非单调 g(F) 演示互相印证：F=1150 mm
（D=0.87）失稳、F=164 mm（D=6.10）失稳、F=115 mm（D=8.70）
在 Zone II 内稳定。边界精度：在 D_crit ± 1e-6 处直接重算，
g 的变号跨过 ±1（测试 `test_boundaries_and_common_zone`）；注
意 |g| 残差本身会被斜率放大（Zone II 远端 dg/dD ~2e3 /m，D 误
差 1e-9 已对应 |g| 误差 ~2e-6），所以精度断言以 D 为准，不以
|g| 残差为准。

## 蒙特卡洛公差仿真（Phase 3 block 2）

`rezeng/montecarlo.py` 的 `run_montecarlo()`：N 个带公差扰动的腔体
副本，分块（默认 250 点/批）一次 CLI 批量调用求值，输出失稳概率、
关键光斑/输出功率 95% CI 与敏感度排序。

### 公差模型（side-car `tolerances`）

每条是一条公差变量：`label` + `alias` 定位 `.rez` 参数，`kind`
决定扰动如何施加，`distribution` 决定分布，`sigma` / `half_width`
是扰动尺度（`length`/`angle` 用 SI 单位，`relative`/`dioptric`
用分数）：

| kind | 含义 | 例子 |
|---|---|---|
| `length` | 参数值加绝对扰动（SI：L 用 m，角度用 rad） | d1.L 正态 σ=0.5 mm |
| `relative` | 参数值乘 `(1+δ)` | M2.R 均匀 ±1% |
| `dioptric` | 在屈光度 `D=1/F` 上加相对扰动，再换回 F | TL1.F 正态 σ=5%（D 空间采样，避开 F→∞ 奇点） |
| `angle` | 二维失调锥角：θ ~ Rayleigh(σ)，方位角均匀；面内分量 θ·cosφ 施加到 `Alpha` | M2.Alpha σ=0.5 mrad |

分布默认值的理由（不要默认所有公差都是独立正态）：

- 曲率/焦距（`relative`/`dioptric`）默认**均匀分布**：采购曲率
  通常标称一个对称 ± 带，没有中心聚集； plain 正态会在尾部放
  不合物理的权重，还可能让 R/F 变号。`truncated_normal` 是备选
  （供应商分档/定心时）。
- 长度/角度默认**正态分布**：加工/装配误差围绕标称值聚集。
- 失调角度必须按二维锥角采样：θx、θy 独立正态采样在角分布上
  是错的（锥角分布不对）；正确做法是 θ ~ Rayleigh(σ)、方位角
  均匀。面内分量 θ·cosφ 的边缘分布恰好是 N(0,σ²)。
- 角度的面外分量无法通过 CLI 施加：`.rez` 里每面镜只有一个
  `Alpha`（面内倾角），没有 S 面倾角参数；且一阶理论里镜面微倾
  只改变光束位置/指向，不改变光斑尺寸 w（这正是块 3 雅可比需
  要 C++ 失调光轴模式的原因）。面外分量只记录在样本里，不参与
  求值，文档在此写明，不假装它被施加了。

每个变量在 setup 时都过 `check_overridable`（与优化器同一检查）：
被链接/驱动的参数直接报错，不会让 1000 个样本逐个返回失败。
随机种子默认固定（`seed=0`），分块只重组批量、不重采样——同
一种子、不同分块大小的结果完全一致（测试锁定）。

### 统计输出

- **失稳概率**：`p̂ = n_unstable / n_ok`（CLI 拒绝的样本计入
  `n_failed`，不进分母），95% 置信区间用 **Wilson 得分区间**：
  `p_CI = [p̂ + z²/(2N) ± z·√(p̂(1−p̂)/N + z²/(4N²))] / (1 + z²/N)`，
  z=1.96。N=1000、零失稳时上界约 0.38%，正态近似会错给 [0,0]。
- **光斑/功率 95% CI**：**非参数分位数**（2.5% / 97.5%），不用
  μ±1.96σ——稳区边缘附近分布严重左偏。光斑统计只覆盖稳定样本
  （失稳样本没有光束）；功率覆盖全部已完成样本，失稳样本
  P_out=0（另给稳定子集的 CI 作对照）。功率用模式 A 快算
  （`resolve_params` 一次 + 每稳定样本一次 `crystal_slices` +
  `mode_a_output`）；side-car 缺泵浦/晶体参数时功率报 `nodata`，
  不编默认值。
- **敏感度排序**：**Spearman 秩相关 + PRCC**（偏秩相关），复用
  同一批 N 个样本，零额外求值。PRCC 做法：秩变换后，每列对其它
  列做最小二乘回归取残差，再对残差求相关。**不默认跑 Sobol**：
  Sobol 要 N(k+2) 次求值，且失稳截断下分方差解失真。光斑敏感度
  用稳定样本，功率/稳定性敏感度用全部已完成样本（失稳 P_out=0）。
  常数输入列的 PRCC 为 nan（无信息），不编造数值。
- **进度/中断**：每批后调用 `progress(done, total)`，返回 False
  即提前停止，报告标 `interrupted: True`，只覆盖已完成的分块。

### Side-car 字段（`tolerances`）

```json
{"tolerances": [
  {"label": "d1", "alias": "L", "kind": "length",
   "distribution": "normal", "sigma": 0.0005},
  {"label": "M2", "alias": "R", "kind": "relative",
   "distribution": "uniform", "half_width": 0.01},
  {"label": "M2", "alias": "Alpha", "kind": "angle",
   "distribution": "rayleigh", "sigma": 0.0005},
  {"label": "TL1", "alias": "F", "kind": "dioptric",
   "distribution": "normal", "sigma": 0.05}
]}
```

### 验证（tests/test_phase3_block2.py，蒙特卡洛部分）

- Wilson 区间手算对照：(0,1000) 上界 0.0038、(500,1000)
  [0.469,0.531]、(10,100) [0.0552,0.1743]。
- 采样分布矩对照：Rayleigh 锥角 E[θ²]=2σ²、面内分量 std=σ；
  均匀相对扰动 |δ|≤a、std=a/√3；截断正态 |δ|≤a；D 空间采样
  （1/F′ 的均值回到 D0）。
- 分块一致性：同一种子，chunk 8 / 40 / 13 的失稳数、光斑中位
  数、敏感度排序完全一致；种子可复现（同种子结果相等，不同
  种子失稳数不同）；进度回调返回 False 时中断且 n_completed
  等于已完成的分块大小。
- Spearman/PRCC 排序对照：合成算例 y=3·x0+噪声，x0 排第一，
  无关变量 |PRCC|<0.2；常数列返回 None/nan。

### 演示（用户真实腔体 + 示例公差带）

`demo_montecarlo.py`：N=1000，ΔL ±0.5 mm（正态）、ΔR/R ±1%
（均匀）、Δα 0.5 mrad 锥角（Rayleigh）、Δf_th ±5%（D 空间正
态），4 次 CLI 批量调用：

| 指标 | 结果 |
|---|---|
| 失稳概率 | 153/1000 = 15.30%，Wilson 95% CI [13.20%, 17.66%] |
| M1 w_T | 中位 0.1049 mm，95% CI [0.0561, 0.1230] mm |
| M4 w_T | 中位 0.2176 mm，95% CI [0.1095, 0.2755] mm |
| P_out（全部样本，失稳=0） | 中位 2.794 W，95% CI [0.000, 2.822] W |
| P_out（仅稳定样本） | 中位 2.802 W，95% CI [2.422, 2.822] W |
| 敏感度（PRCC vs M1 w_T） | M2.R +0.960 第一，TL1.F −0.942 第二，d1.L −0.447；两面镜的 Alpha ≈0（一阶不影响光斑，符合理论） |

失稳率 15% 高，是因为腔体工作点本来就靠近 Zone I 上沿
（D=4.348，上沿 4.640）：±5% 的 D_th 扰动加 ±1% 的曲率扰动
很容易把 g 推出 ±1。公差带与泵浦/晶体参数全是示例，不是
真实值。

## 逆向拟合（Phase 3 block 2）

`rezeng/reverse.py` 的 `fit_plane()` / `fit_thermal_lens()`：用
Beam Profiler 在输出镜外 2~3 个位置测得的实际光斑，反推晶体
内部真实热透镜屈光度 `D_th = 1/f_th`（T/S 各自独立求解——两
平面解耦）。拟合变量用 `D_th` 而不用 `f_th`（避开 f→∞ 奇点，
与稳区扫描一致）。

### 模型 w_model(z; D_th)

1. 在 `D_th` 处一次 CLI 求值（热透镜 F 改写为 1/D_th），得腔
   内光束。
2. 透射输出光束 = **入射到输出镜的光束**：CLI 报告的前一元件
   出口条目正好位于输出镜平面，它的 (w,R) 就是透射光束的
   (w,R)（透射一阶上保持两者不变）。镜面自己的 CLI 条目是
   **反射光束**，R 符号相反——已在用户腔体上核实：M4 条目
   R=−99999.99… mm，d4 出口 R=+100000.00… mm，w 相同。输出镜
   是第一个元件时才用自身条目并翻转 R 符号。
3. 输出镜基底（平行平板）按 `q → q + L/n` 施加（ElemPlate 矩
   阵 `[[1,L/n],[0,1]]`），数据来自 side-car `output_mirror`
   （`thickness_mm`、`n`）。**基底数据缺失时平板直接省略，并
   报警告 + 误差估计**：用标称 6.35 mm / n=1.45 基底重算各测
   量点的光斑，取最大相对差——只是量级估计，明确标注，拟合本
   身不用它。
4. 自由空间传播到 `z_i`：`q → q + z`。

### M² 处理

CLI 算的是基模（M²=1）光斑。实测 M² 给出时，模型用内嵌高斯
波长 `λ_eff = M²·λ` 构造 q 并传播——远场光斑随之按 M  scaling。
实测 M² 缺失时报警告并给偏差估计：拟合会把 M² 误差全部吸收
进 f_th；报告给出解处的中位 `dw/dD_th` 敏感度，换算成未建模
M²=1.2 时 D_th 的位移量级与方向（沿 dw/dD_th 的符号，朝最近
的稳区边界）。

### 求解

`scipy.optimize.least_squares(method='trf')`，残差：

```
r_i(D_th) = (w_model(z_i; D_th) − w_meas,i) / σ_w，σ_w = 5%·w_meas,i
r_prior(D_th) = λ·(D_th − D_rez) / σ_prior，σ_prior = 0.5·D_rez，λ = 0.1
```

`D_th` 的 bounds 取当前工作稳区（`Zone_Common` 中包含当前
`.rez` 值的那个区间，见 `working_zone_bounds()`）；收敛判据为
相对残差 RMS < 3%（Beam Profiler 典型误差 2~5%）；
ftol=xtol=1e-6。失稳/失败的模型求值返回大残差 10.0，不使求解
器崩溃。

**数值雅可比步长（实测教训）**：CLI 输出的光斑只打印到约
1e-6 mm，`least_squares` 默认的 sqrt(eps) 步长（~1.5e-8）看到
的只是量化噪声——h=1e-8 时差商为 0，h=1e-7 时差商偏大 ~20 倍，
h≥1e-4 才收敛到真雅可比；默认步长下求解器一步就误以为已最
优。实现用 `diff_step=1e-3`（相对步长），模型在该尺度上光滑，
截断误差可忽略。

### 可辨识性与简并（必读）

- **至少 3 个点，且跨过束腰 / 覆盖 z_R 两侧**。2 个点理论可
  解，但工程上极易病态：两点都在远场同一侧时，几乎只量到发
  散角这 1 个有效信息，束腰位置信息丢失。
- 在用户腔体上简并是**精确的**，不只是远场近似：`w0(D_th)`
  在每个稳区内单调，两个稳区的取值范围重叠，所以 Zone I 的
  D=4.0 /m 与 Zone II 的 D=9.5 /m 给出同一个输出束腰
  （w0=253 µm，z0=−0.4 mm），各 z 处的光斑差异 <0.4%。任何一
  组腔外光斑测量都区分不了这对 D——束腰位置 z0 在（近平面）
  输出镜处基本不动，布点也破不了 Zone I/Zone II 的平局。破
  局靠的是拟合的 bounds（工作稳区）+ 朝 D_rez 的弱先验。
- 报告在全部测量点都处于远场同一侧（|z_i−z0| > 2·z_R）时标
  记 `degeneracy risk` 警告；点数 <3 时也警告。

### 输入要求

- 每平面至少 2 个点（`{"z_mm", "w_mm"}` 或 `(z_mm, w_mm)`），
  强烈建议 ≥3 个；**传播距离 z_i 必须作为已知输入**（从输出
  镜面起算，单位 mm）。
- 输出镜 label（默认 M4）、热透镜参数（默认 TL1:F）、实测
  M²（可选）、输出镜基底数据（side-car `output_mirror`，可
  选）。
- 工作点必须在某个公共稳区内，否则 `working_zone_bounds()`
  报错——失稳腔的反推没有意义。

### 验证（tests/test_phase3_block2.py，逆向拟合部分）

- R 符号约定：M4 条目 w 与 d4 出口一致、R 符号相反（真实 CLI）。
- 合成数据恢复：真值 F=250 mm（D=4.0 /m），3 点（z=30/200/
  800 mm，跨束腰）加 3% 噪声，T/S 两平面恢复误差 0.03% /
  0.05%，RMS 0.87% / 0.88%，收敛。
- 简并陷阱：真值 D=9.5 /m（Zone II），2 个远场点（z=1500/
  2500 mm），D=4.0 与 D=9.5 的模型光斑在测量点处差异 <1%；
  Zone I 有界拟合收敛到 D=4.0026 /m、RMS 0.06%——“成功”但答案
  在错误的稳区；`degeneracy risk` 警告被触发（测试锁定）。
- M² 修正：M²=1.3 的合成数据，不修正时拟合偏差 >2%（且报告
  给出 `m2_bias_estimate`），修正后恢复误差 <5%。
- 基底：给基底数据时无警告、无误差估计；缺失时报警告且
  `substrate_error_estimate.max_rel_diff` 在 (0, 5%) 内。
- 输入校验：<2 个点、未知输出镜、bounds 不含工作点时均报
  `ReverseError`。

### 演示（用户真实腔体 + 合成测量数据）

`demo_reverse.py`：测量数据全是合成的（模型生成，真值已知），
基底数据是示例标称值。

| 演示 | 结果 |
|---|---|
| 3 点恢复（真值 F=250 mm，3% 噪声） | T：D=3.9988 /m，误差 0.03%，RMS 0.87%；S：D=3.9979 /m，误差 0.05%，RMS 0.88% |
| 2 点远场简并（真值 D=9.5 /m，Zone II） | 拟合 D=4.0026 /m（Zone I），RMS 0.06%——收敛但答案错误，演示了陷阱 |

## 装调雅可比与螺丝圈数指南（Phase 3 block 3）

镜面微倾对光斑尺寸 w 的一阶偏导为零，只改变光轴位置/指向；
没有光轴输出，有限差分对光斑求导只会得到数值噪声。因此 C++ CLI
增加了失调光轴模式（协议 §12），本节是它的 Python 层
（`rezeng/jacobian.py`）。

### 坐标系与符号约定（必读）

- **右手坐标系**：S 为全局 +y（折叠面法向）；T = S × z，z 为展开
  光束前进方向；T/S 两面解耦。
- **δ_T > 0**：镜面法线向 +T 偏；**δ_S > 0**：法线向 +S 偏。
- **kick 为 +2δ**：展开坐标系中，每次经过一面镜，光线角获得
  +2δ 的增量（反射，2 倍因子），**第一遍与返回遍都加**。
- 光轴输出的参考面 = 该元件的**出射面**（与 beam 条目同一平面），
  对镜面是反射后的光轴；单位 mm / mrad。
- **θ 是镜面机械倾角，光束偏转角是其 2 倍**。雅可比的列是机械倾角；
  螺丝圈数用机械倾角算：`N = θ·L_arm/p`。

### 雅可比矩阵

`jacobian_analytic(data, ref_label)`：解析雅可比——对增广 3×3
往返系统 `(I−M_rt)v = E_rt` 求导，`dE/dδ_k` 为该镜在往返列表中
每次出现前的矩阵乘积之和 `Σ P_before·(0,2)`；返回 `(4, 2n)` 数组，
行 `[x_T, th_T, x_S, th_S]`（mm/mrad、mrad/mrad），列
`[dT(M1), dS(M1), dT(M2), dS(M2), ...]`。光轴是倾角的**严格线性
函数**（矩阵与倾角无关），所以雅可比是精确的，不是近似。

`jacobian_finite_difference(data, ref_label, dtheta=1e-4)`：一次 CLI
批量请求，每倾角一组（Δθ = 1e-4 rad），差分 CLI 光轴输出；
与解析法一致到 1e-6 量级才算通过（用户真实腔体实测 3.7e-15）。

### 螺丝圈数与方向映射表

- `screw_turns(theta_rad, arm_mm, tpi)`：`N = θ·L_arm/p`，100 TPI
  p = 0.254 mm/圈，80 TPI p = 0.3175 mm/圈。手算对照：θ = 1 mrad、
  臂长 50 mm、100 TPI → N = 1e-3·50/0.254 = 0.19685 圈。
- `tilt_to_screws(dT, dS, tpi, arm_T_mm, arm_S_mm, azimuth_deg)`：
  按镜架方位角 φ 做 2×2 旋转映射，给出每颗螺丝的圈数与方向。
- `recenter_guide(...)`：单镜位置回中指南（位置归零，指向残差报告；
  一面镜不能同时归零四个输出量）。

方向映射表（**背视图**，即从镜架背面、螺丝所在的一侧看向镜面；
右手螺纹；标准运动学镜架布局：俯仰螺丝 A 在 +T 侧、偏摆螺丝 B
在 +S 侧）：

| 想要的倾角变化 | 螺丝 | 方向（背视图） |
|---|---|---|
| δ_T 增大 | A（俯仰） | 逆时针 CCW |
| δ_T 减小 | A（俯仰） | 顺时针 CW |
| δ_S 增大 | B（偏摆） | 逆时针 CCW |
| δ_S 减小 | B（偏摆） | 顺时针 CW |

顺时针 = 螺丝前进（向镜面顶进该侧边缘，法线向反方向转）。
方位角 φ ≠ 0 时，螺丝 A/B 的作用方向按 `R(−φ)` 旋转
（φ = 90° 时纯 δ_T 由 B 螺丝单独产生，方向相反）。

**⚠ 方向映射必须实测标定**：不同镜架的螺丝位置、螺纹旋向可能
与上表相反。标定方法：单镜拧一颗螺丝已知圈数，看输出光斑是否
按预测方向移动；若反向，把该镜架的映射表符号取反。用户待提供
实测单镜微调标定数据（见本节末尾“仍需用户提供的真实参数”）。

### 验证（tests/test_jacobian.py，19 个）

- 解析雅可比 vs 有限差分：M4（输出）与 M1（SESAM）两处参考面，
  最大绝对差 3.7e-15（要求 < 1e-6）。
- CLI 光轴线性：M2 +1 mrad = 10 × (+0.1 mrad)；M2+M3 叠加 = 各自之和。
- 零失调 → 光轴全零；T/S 两面解耦（dT 列只动 T 行）。
- 平面-平面腔（g=+1）解析雅可比报 `JacobianError`；SP 报
  `JacobianError`；往返列表 SW/RR 顺序与 C++ 一致。
- 螺丝换算手算对照（θ=1 mrad、臂长 50 mm：100 TPI 0.19685 圈、
  80 TPI 0.15748 圈；1 圈 = 5.08 mrad）、方向映射表、方位角 90° 映射。

### 演示（用户真实腔体 + 示例镜架参数）

`demo_jacobian.py`：镜架参数全是**示例**（100 TPI、臂长 50 mm、
方位角 0°），不是用户的真实镜架。

| 演示 | 结果 |
|---|---|
| M2 dT = +0.1 mrad → M4 输出光轴 | x_T = +0.0643 mm，th_T = −0.0006 mrad；x_S = th_S = 0 |
| M4 处完整雅可比（解析 vs 有限差分） | 最大绝对差 3.7e-15；M2 dT：x_T 0.6435 mm/mrad、th_T −0.0064 mrad/mrad；M4 dT：th_T 1.0065 mrad/mrad |
| 用 M2 把光斑移回中心 | 修正 dT = −0.1000 mrad；俯仰螺丝 A 拧 0.0197 圈、顺时针（背视图）；位置残差 0，指向残差 < 1e-3 mrad |

### 仍需用户提供的真实参数

- 镜架规格：牙距（100/80 TPI 或其他）、俯仰/偏摆臂长 L_x/L_y、
  方位角 φ（镜架螺丝轴相对腔 T/S 轴的旋转）。
- 实测单镜微调标定数据：拧一颗螺丝已知圈数后输出光斑的移动量
  与方向，用于验证方向映射表（上表）是否与实际镜架一致。
- 其余 Phase 1/2/3 参数请求仍未答复（见本 README 其它各节）。

## 鬼像/标准具扫描（Phase 4 M1）

### Alpha 的定义：入射角 AOI（已从源码核实）

`.rez` 里每面镜的 `Alpha` 是**入射角 AOI**（入射光线与法线的夹角），
不是全折叠角。核实依据（`src/core/Elements.cpp`）：

- `ElemCurveMirror` 构造函数（约第 201 行）：Alpha 的参数说明为
  “入射角”，“zero angle is normal incidence”（零角度即正入射）；
  矩阵为 T 面 `C = -2/(R·cos α)`、S 面 `C = -2·cos α/R`——标准
  斜入射反射镜矩阵，α 即 AOI。
- `ElemThinLens`（约第 232 行）、`ElemTiltedCrystal`（约第 286 行）、
  `ElemTiltedPlate` 同样以 Alpha 为入射角。
- `ElemFlatMirror`（约第 188 行）没有 Alpha 参数（单位矩阵）。

全折叠角 = 2·Alpha。镀膜表的 AOI、`.zmx` 的 COORDBRK 倾角、鬼像
的折叠角旋转都直接用 Alpha。Phase 0 的像散分析（T 面
`C = -2/(R·cos α)`、S 面 `C = -2·cos α/R`）与源码定义一致，
无差异。`ElemThickLens` 的 R1/R2 约定（第 665–674 行）：正值 =
表面向左凸；前表面反射功率 `C = +2/R1`，后表面 `C = -2/R2`。

### 输入：side-car `surfaces`

每光学表面一条（`surfaces.<label>.faces[]`，见 `eng.py` 的校验）：

```json
"surfaces": {
  "TL1": {"faces": [
    {"face": "front", "R_1064": 0.002, "R_808": 0.002, "R_532": 0.002,
     "wedge_mrad": 0.1, "wedge_plane": "T",
     "role": "AR-coated crystal face", "R_face_mm": null}]},
  "M2": {"faces": [
    {"face": "back", "R_1064": 0.005, "role": "substrate back"}]}
}
```

- 镜面**正面不列**：它的反射就是主光束，不是鬼像；镜的**衬底背面**
  列出来（它的反射才是鬼像源）。平板/晶体列前后两面。
- `R_1064` / `R_808` / `R_532` 是该面的残余反射率（分波长）。
  **缺失时报 nodata，绝不编默认值。**
- `wedge_mrad` 是面的楔角（mrad），`wedge_plane` 为 `"T"` 或 `"S"`；
  `R_face_mm` 是面的曲率半径（mm，`null` 为平面）。

### 剪枝阈值

- 寄生标准具：只扫描表面对 `R_i·R_j > 1e-6`（低于此值的对，
  调制深度 < 0.4%，可忽略）。
- 一阶鬼像聚焦：只追迹单次反射率 `R_i > 1e-3` 的曲率面反射
  （`R ≠ ∞` 的面）。
- 标准具只看近平行表面对：两面夹角 < 发散角 `θ_div`
  （`θ_div = λ/(π·w)`，取两面处光斑的较小值）。

### 标准具：FSR 与调制深度

`FSR = c/(2·n·L_etalon)`，调制深度
`M = 4√(R₁R₂)/(1+√(R₁R₂))²`。`M > 5%` 时报 warn（跳模风险）。
`L_etalon` 是两面之间的光程（`n·L`，`n` 为间介质折射率），
`c = 299792458 m/s`。

### 烧镜点：鬼像 q(z) 追迹

对每个曲率面生成的反射鬼像（`R_ghost` 为该面反射率）：

1. 鬼像的 q 由主光束在该面处的时间反演得到：
   `q_ghost = M_face · (−conj(q_main))`（`M_face` 为该面的
   反射矩阵；平面为单位矩阵）。
2. 沿 C++ 往返光路表**反向**走（最多一整圈），用 ABCD 追迹
   q(z)，在每段内找束腰：束腰是 `Re(q_med(u)) = 0` 的深度
   `u`——`q_med` 为介质内 q（GRIN 子矩阵的标量形式）。
   **不能用空气侧 `Re(q)`**：`n > 1` 的段内物理束腰在
   `u = -n·Re(q_air)`，不是 `-Re(q_air)`（对称腔验证：空气侧
   位置 46.67/53.33 mm，真实束腰在板中心 50 mm）。
3. 束腰落在某元件内（或镜面在 2·z_R 内）即为候选烧镜点；
   空气段内的束腰无害，永不入选。鬼像峰值通量
   `F_ghost = 2·E_p·R_ghost/(π·w_T·w_S)` 与该处 LIDT 对比
   （复用 `checks.py` 的 LIDT 数据与阈值：>1 fail、>0.8 warn；
   无脉冲能量或无 LIDT 时报 nodata）。主元件（包含束腰者）
   的结论为准；邻近镜面只在 warn/fail 时升级结论，无 LIDT
   的邻近镜面只在备注中说明，不覆盖主元件的结论。

### 离轴鬼像：必须用 Phase 3 的 3×3 失调光轴模式

带楔角/折叠角的元件，鬼像中心光线用增广 ABCD 追迹
`(x_g, θ_g)`：楔角面的反射给光线 `2·wedge` 的初始角，
倾斜平板给 `2Δ` 的横向偏移（`Δ` 为平板横向位移），镜面
反射角加 `C·x`。只用共轴 2×2 ABCD 会漏掉离轴鬼像——测试
锁定了一个带楔角晶体算例（2×2 追迹漏掉、3×3 追迹抓到）。
每走一段后检查光线是否仍在镜片口径内（取共享该面的两
元件中较小的口径）；飞出即判定该鬼像无效（`exited`），
不再继续追迹。

### 验证（tests/test_phase4_block1.py，鬼像部分，共 8 个）

- Alpha 定义源码对照（`Elements.cpp` 的曲面镜矩阵与“入射角”
  说明）。
- 剪枝对照：`R_i·R_j = 1.1e-6` 入选、`9e-7` 排除；单次
  `R = 1.1e-3` 追迹、`9e-4` 不追迹。
- 标准具 FSR/调制深度手算对照：TL1（`L=27 mm, n=2.16`）
  FSR = 2.5702 GHz。
- 烧镜点定位对照：对称腔（R=200 mm、L=100 mm、20 mm 平板）
  的鬼像束腰恰好在板中心 s = 50.0 mm。
- 离轴鬼像锁定测试：楔角 5 mrad 的平板，鬼像光线在板入口处
  横向位移 `2·wedge·L/n = 0.133333 mm`；小口径（Ø1.0 mm）时
  鬼像在 M1 处飞出（`exited`），大口径时保留。
- 鬼像重合验证：TL1 前/后面与 M4 背面的鬼像重走主光束，
  最坏相对误差 6.5e-15。

### 演示（用户真实腔体 + 示例参数）

side-car：`tests/data/example-phase4.eng.json`。**全部表面反射率、
LIDT、楔角、口径、脉冲参数都是示例值（编的），不是实测。**

```sh
python3 run_ghosts.py /path/to/upload.rez tests/data/example-phase4.eng.json
```

结果（`summary`：ok 6 / warn 1 / fail 0 / nodata 0，共 7 项）：

- 6 个一阶鬼像全部 ok：最坏的是 M1 衬底背面（R=4%）的鬼像，
  束腰在 M1 面上（w₀ 0.100/0.103 mm），通量 0.247 J/cm²，
  为示例 LIDT 5 J/cm² 的 4.9%。TL1 背面鬼像的束腰在 TL1 内部
  s = 875.5 mm，通量 0.0005 J/cm²（示例 LIDT 10 J/cm² 的 0.005%）。
- 1 个 warn：M1 衬底背面 ↔ M4 衬底背面形成的腔长标准具
  （`R₁·R₂ = 1.6e-3`），FSR = 0.128 GHz，调制深度 14.8% > 5%
  阈值——若两端镜衬底背面未镀 AR 或未楔角，有跳模风险。
  （演示用的背面反射率 4% 是示例值；真实值未知。）

## 632.8 nm 红光对照（Phase 4 M1）

### Sellmeier 系数库（`redlight.py`）

内置公开文献值（注明来源）：熔融石英 Malitson 1965、BK7
Schott、Nd:YVO4 的 n_o/n_e、LBO 的 n_x/n_y/n_z。核对值：
Nd:YVO4 n_e 2.165069 @1064 nm、n_o 1.957136 @1064 nm、
n_e 2.215462 @632.8 nm；熔融石英 1.457018 @632.8 nm；
BK7 1.515089 @632.8 nm；LBO:x 1.564776 @1064 nm。
side-car 只存材料 ID（`materials.<label>.material`）与可选的
`(n_1064, n_633)` 覆盖值（`materials.<label>.n_1064` /
`n_633`），不存整套系数。

### 冷腔态

热透镜 `F_th → 1e9 mm`（近似 ∞），所有晶体/衬底折射率替换
为 `n(632.8 nm)`，物理间距与曲率不变；调用 CLI 在 632.8 nm
参数下重算，输出各参考光阑处的 `(x_633, w_633)` 与 1064 nm
热腔的 `(x_1064, w_1064)` 之差（装调偏差表）。

### 回退逻辑（必须实现，已实现）

冷腔 `F_th → ∞` 时往往失稳，CLI 报 Unstable——此时自动切换
为外部 HeNe 准直光（默认 `w₀ = 0.5 mm`，从 M4 注入，可选
`--double-pass` 往返）的单程 ABCD 追迹（`qevolve.py` 的演化器），
并在输出中明确标注 `path: "fallback"`。冷腔稳定时走
`path: "cold_eigenmode"`，不注入。注入光的折返用
`q' = M·(−conj(q))`、光线角 `θ' = θ + C·x`；倾斜平板的
`Δ` 与 `(n−1)·wedge` 透射偏转已计入。

### 验证（tests/test_phase4_block1.py，红光部分，共 3 个）

- 回退测试：用户真实腔体冷腔失稳（g_T −1.9545 / g_S −1.9875）
  → 自动切单程追迹并标注 `fallback`。
- 冷本征模测试：无热透镜的对称腔冷腔稳定 → 走
  `cold_eigenmode`，不注入。
- Sellmeier 数值对照：上述 5 个核对值。

### 演示（用户真实腔体 + 示例参数）

```sh
python3 run_redlight.py /path/to/upload.rez tests/data/example-phase4.eng.json
```

结果：`path: "fallback"`，冷腔 g_T −1.9545 / g_S −1.9875（失稳），
注入 HeNe w₀ = 0.5 mm 自 M4 单程。偏差表要点：M4/d4 处
w_633 0.5 mm 对 w_1064 0.2057 mm（+143%，注入光斑本身就比
腔模大）；M1 处 w_633 0.1040 对 0.1000（+4.0%），x_633
偏移 −0.0177 mm；d1 处 w_633 1.6519 对 1.2641（+30.7%）。
红光与红外腔模的差异主要来自波长（衍射）与冷腔无热透镜，
不是装调误差——装调时以光斑中心（x）为准，w 的差异是预期的。

## 镀膜表 / .zmx / .dxf 导出（Phase 4 M1）

### 镀膜表（`coating_table()`）

遍历所有光学表面（含镜面正面——HR/OC/SESAM 行，见下），按
AOI（入射角，见上）、偏振态（T 面 = P 偏振、S 面 = S 偏振；
AOI = 0 时单行 unpolarized）、泵浦/基频/倍频波长与表面峰值
功率密度（复用 `checks.py`），生成供应商镀膜指标表（文本 +
JSON）。镜面正面行：M1（标题含 "sesam"）→ SESAM
`R>99%@1064nm` + 饱和参数（side-car `elements_ext` 的
`F_sat` / 调制深度）；输出镜（side-car `output_mirror.label`）
→ OC `PR T=...%@1064nm`；其余镜面 → HR `>99.9%@1064nm`；
衬底背面/晶体面 → AR `R<0.2%@1064nm`。峰值功率密度
`2·(E/τ)/(π·w_T·w_S)`；要求 LIDT = 计算通量 × 安全系数 2
（`LIDT_SAFETY_FACTOR`）；`margin = LIDT / fluence`。示例格式：

```
M2 front: R=500mm, AOI=2.5 deg, S-pol, HR>99.9%@1064nm, HT>95%@808nm, R<1%@532nm, fluence 0.04105 J/cm^2, LIDT > 0.08211 J/cm^2
```

### .zmx（`to_zmx()` / `validate_zmx()`）

序列模式，只写正向（第一元件 → 最后一元件），不把 SW 往返
再展开一次。规则：

- 每面折叠镜前后各一个 COORDBRK（前转 AOI、放 MIRROR、后转
  AOI）；反射后所有后续 THICKNESS 符号取反（`validate_zmx`
  逐面跟踪符号）。
- SESAM → MIRROR + 备注饱和参数。
- 27 mm 热透镜 GRIN → 两段 L/2 的 Nd:YVO4 玻璃，中间夹一个
  PARAXIAL 薄透镜 + 备注。PARAXIAL 的焦距取**矩阵导出的有效
  焦距** `f = −1/C`（T 面），不是 .rez 的 `F`：精确 GRIN 矩阵
  的 `C = −1/236.28 mm`，而 .rez `F` 是 230 mm（`solve_n2`
  的精确 γ 与薄透镜 γ 差 ~0.9%）。用 .rez `F` 会使腔的 g
  从 0.929 变到 0.985、光斑差 ~35%；用有效焦距残差为 7.8%
  （见下）。`.rez F` 记在 PARAXIAL 的 NOTE 里，不丢失。
  GrinLens / GrinMedium（无 `F` 参数）同样由矩阵导出有效焦距。
- 两段 L/2 必须是**玻璃板**（ElemPlate，`[[1, L/n], [0, 1]]`），
  不是空气段——用空气段会使 B 项翻倍，光斑对照误差达 ~35%。

**验证方式**：本机无 OpticStudio，**不得谎称已在 OpticStudio
中验证**。验证方法是解析自查（逐行格式对照、COORDBRK 配对
检查、厚度符号检查、PARAXIAL 焦距对照）+ CLI 光斑对照
（`thin_lens_spot_check()`：把 GRIN 换成 `[plate L/2, thin lens
f, plate L/2]`，与原腔逐元件比光斑）。`.zmx` 文本中明确写
"NOT verified in OpticStudio"。用户真实腔体：解析自查 ok
（21 个面、4 面镜 COORDBRK 全部配对、厚度符号翻转正确、
PARAXIAL f = 236.278 mm、.rez F = 230.0 mm）；薄透镜光斑对照
最大相对误差 7.76%——残差是稳定性边缘放大（腔在 g_T = 0.929，
薄透镜模型的 0.06% A/D 失配把 g 推到 0.955），不是导出错误；
测试阈值放宽到 10% 并注明该数值。

### .dxf（`to_dxf()` / `validate_dxf()`）

- ezdxf（1.4.5）已装就用 ezdxf；未装则尝试 `pip install ezdxf`，
  装不上则用手写最小 DXF R2000 写入器（只写 LWPOLYLINE / LINE /
  TEXT + 图层，文档注明子集；LWPOLYLINE 含 `AcDbEntity` /
  `AcDbPolyline` 子类标记，ezdxf 才能解析）。
- 图层分离：OPTICAL_AXIS、BEAM_1E2、BEAM_2W、ELEMENTS、
  ANNOTATIONS。
- 沿光路每段采样 40 点（束腰附近加密），将局部 `(z, ±w(z))`
  按折叠角旋转平移到全局 2D 坐标，输出 LWPOLYLINE；`w(z)` 用
  GRIN 子矩阵精确计算（范围与 GRIN 元件精确，见鬼像一节）。
- 验证：重新解析导出的 `.dxf`（ezdxf，若无则用最小解析器），
  检查图层、折线点数、包络最大值与 CLI 的 `w(z)` 一致。
  用户真实腔体：ezdxf 与最小写入器两种往返验证均通过，
  包络最大值 1.2640978169391182 mm 与 CLI 的 1.264097816939118 mm
  一致（相对误差 < 1e-12）。

### Side-car 新增字段

`eng.py` 的 `validate_eng` 新增 `surfaces`（见鬼像一节）、
`materials`（`{label: {material, n_1064, n_633}}`）、`layout`
（每元件 `{x_mm, y_mm, angle_deg}`，DXF 绘图的位置覆盖）。

### 验证（tests/test_phase4_block1.py，导出部分，共 7 个）

- 镀膜表：AOI 取 Alpha（M2 2.5°、M3 4°）、P/S 双行、通量手算
  对照（M4：2·1e-3/(π·0.0205657·0.0211257) J/cm²）、镜面正面
  行（M2 前 HR 双行、M1 前 SESAM、反射率 nodata）。
- `.zmx` 结构：COORDBRK 4 面镜全部配对、厚度符号翻转、
  PARAXIAL f = 236.278 mm（有效焦距）/ .rez F = 230.0 mm、
  TILT X 用 AOI（2.5°/4°，不是 5°/8°）、SESAM 备注、
  "NOT verified in OpticStudio"。
- `.zmx` 薄透镜光斑对照：最大相对误差 0.0776 < 0.10。
- `.dxf` 往返解析：ezdxf 与最小写入器各一次，图层、点数、
  包络最大值与 CLI 一致。

### 演示（用户真实腔体 + 示例参数）

```sh
python3 run_export.py /path/to/upload.rez tests/data/example-phase4.eng.json \
    --coating --zmx /tmp/demo-phase4.zmx --dxf /tmp/demo-phase4.dxf --thin-lens-check
```

镀膜表 14 行（含 6 行镜面正面：M1 SESAM、M2/M3 HR 各 P/S、
M4 HR；8 行衬底背面/晶体面 AR）。要点：M1 SESAM 正面通量
6.176 J/cm²（示例 LIDT 5 J/cm² 的 123.5%——与 Phase 1 检查的
示例结论一致，是示例参数的问题，不是实测）；M4 背面通量
1.465 J/cm²；TL1 两面约 0.25 J/cm²。`.zmx` 与 `.dxf` 各导出
一份到 /tmp（不污染仓库），验证结果见上两节。

## 热传导与热断裂（Phase 4 M2）

`rezeng/thermal.py`（柱坐标 FD 求解器 + OPD 闭环）与
`rezeng/fracture.py`（平面应变应力 + 断裂裕度），入口
`run_thermal.py`（JSON 报告）与 `demo_thermal.py`（用户真实
腔体 TL1 的 2/5/10 W 扫描）。纯 Python，不改 C++；求解中间值
不写进 `.rez`，全部在 side-car `thermal` 一节。

### 离散化与边界条件

柱坐标 (r, z) 稳态泊松方程 `∇·(k∇T) + Q(r,z) = 0`，有限差分
+ `scipy.sparse.linalg.spsolve`（稀疏直接 LU，不写 SOR）。
默认网格 Nr×Nz = 60×150；r=0 奇点用 L'Hôpital 展开
（径向拉普拉斯化为 `2∂²T/∂r² ≈ 4(T₁−T₀)/Δr²`）；圆柱侧面
Robin 边界 `−k∂T/∂r = h(T − T_cool)`；两端面按对流/绝热可
选（`end_faces: adiabatic|robin|dirichlet`）。**h 没有默认值**：
它决定绝对温度，必须由用户给定（铟箔接触典型 5000 W/m²K
只是示例值）；不给 h 时 `resolve_thermal` 直接报错。

### 热源

`Q(r,z) = η_h·α(z)·P_pump/[2πw_p²(z)]·exp(−2r²/w_p²(z))·exp(−∫₀^z α dz′)`，
泵浦沿 z 按 Beer–Lambert 指数衰减、径向高斯/平顶可选
（`profile: gaussian|tophat`）；w_p(z) 按泵浦高斯光束发散
（M_p²、λ_p、腰位 z_p0）。**注意：Gemini 评审给的高斯热源
前置因子错了 4 倍**——`η_h·α·P/(2πw_p²)·exp(−2r²/w_p²)`
对 r 积分只得到 `η_h·P_abs/4`，正确前置因子是 `2/(πw_p²)`
（标准光束强度归一化）；能量平衡测试已锁定。求解后 Q 按离散
积分重标定（形状不变），使总产热严格等于 `η_h·P_abs`。

### 端帽键合晶体

`thermal.end_caps` 给出分段 `[{z0_mm, z1_mm, alpha_per_cm,
k_W_per_mK}]`：无掺杂端帽区 α=0（Q=0，只导热）；界面处导热
系数取调和平均 `k_{i+1/2} = 2k_i·k_{i+1}/(k_i + k_{i+1})`。
`thermal.pump.alpha_p_per_cm` 与 `end_caps` 二选一。

### 板条（Slab）

板条破坏轴对称性，不可硬套柱坐标。`solve_poisson_slab`
用直角坐标 2D (x,y) 网格：上下大面 Robin 冷却、左右侧面
绝热；支持与柱坐标相同的热源/端帽分段形式。3D 板条未实现，
需要时应报 `ThermalError` 而不是静默近似。

### 材料库与各向异性

`MATERIALS_THERMAL` 内置 Nd:YVO4、Nd:YAG、Yb:YAG、
Yb:YVO4、Ti:sapphire 的热学参数（k、dn/dT、α_T、E、ν、
σ_fracture、n），来源为公开文献值（Koechner；Innocenzi
et al.；Castech 数据表；YAG/蓝宝石手册值），side-car 只存
材料 ID + 可选覆盖值（`material_overrides`）。**Nd:YVO4 各
向异性必须显式处理**：α_c ≈ 11.4e-6/K 是 α_a ≈ 4.4e-6/K 的
2.6 倍。应力按 α_a 算主值、按 α_c 算保守界，报告同时给出
两者并在 `warnings` 中标注；用各向同性近似时结论要留余量。

### 应力与断裂裕度

`rezeng/fracture.py`：平面应变解析公式（Koechner）给出
σ_r/σ_θ/σ_z，取全域最大拉应力
`σ_max = max(σ_r, σ_θ, σ_z)`（只看正值拉应力，脆性晶体抗
压不抗拉）；安全裕度 `= 1 − σ_max/σ_fracture`，工程红线
≥50%（安全系数 ≥2）：低于红线报 `fail`、50–70% 报 `warn`、
≥70% 为 `ok`。应力分两项报告：z 平均主值与逐层局部峰值，
取两者较大者作判据。端面鼓包
`u_z(r) ≈ (1+ν)α_T∫ΔT dz`（z_eff 默认取 R0，积分到精确
z_eff，含插值）。

**局限性（评审指出，文档必须写明）**：平面应变公式会低估
泵浦端面峰值拉应力 20%~40%；抛光表面微裂纹会使实际
σ_fracture 骤降至理论值一半。裕度结论要留安全余量，不能
贴着红线用。另：应力公式只计热应力，不含装夹/胶合预应力。

### OPD 闭环

沿 z 积分 `OPD(r) = ∫₀^L (dn/dT)·ΔT(r,z) dz + (n−1)·u_z(r)`，
在激光模斑范围 r ≤ 1.5·w_L 内做偶次多项式拟合
`OPD(r) = c₀ + c₂r² + c₄r⁴ + c₆r⁶`，提取等效焦距
`f_th = −1/(2c₂)` 与球差系数 c₄/c₆；`phase_plate()`
输出给 M3 Fox-Li 的相位板（`f_th_mm`、`c4_per_m3`、
`c6_per_m5`、`rms_m`）。闭环分两层：

- **轴上闭环（求解器验证）**：直接曲率 `2∫T″(0,z)dz`
  与解析值 `−∫Q(0,z)/k·dz` 的恒等式（绝热端面，精确成立），
  实测偏差 **−0.00%**（60×150 与 240×600 网格一致）。这是
  本块的验收标准。
- **模平均拟合（工程量）**：r ≤ 1.5·w_L 的拟合值是模斑范围
  内的*有效*透镜，不是轴上透镜。用户腔体 w_L ≈ 498 µm ≫
  w_p = 200 µm 时，模斑采到平坦的外围 OPD，拟合 f_th 比轴
  上值长 **+88.3%**（与功率无关的几何效应）。比较 Phase 2
  线性模型时用轴上值，Fox-Li 相位板用拟合值，不要混用。

**高斯 vs 平顶因子 2**：高斯泵浦的轴上热透镜
`1/f = η_h·P_abs·(dn/dT)/(π·K·w_p²)`；Phase 2 的线性模型
系数 κ 是平顶结果（恰为高斯的一半）。闭环测试用高斯解析
值，线性模型比对时另附因子 2 的说明，不要直接断言 <10%。

### 网格收敛性（实测，200 µm 泵浦）

| 网格 | T_max 温升 | 拟合 f_th |
|---|---|---|
| 60×150 | 91.3 K | 134.9 mm |
| 120×300 | 83.6 K（−8.4%） | 155.3 mm（+15.2%） |
| 240×600 | 81.8 K（−2.2%） | 163.7 mm（+5.4%） |

二阶收敛（每加密一倍误差约 ÷4）。**60×150 默认网格对
200 µm 泵浦偏粗**（T_max 高估 ~12%、f_th 低估 ~19%）；
演示 side-car 用 120×300。spsolve 实测：60×150 求解
0.239 s（含组装；Gemini 评审说的 20–50 ms 是纯求解量级，
实测组装占大头），120×300 约 1 s，240×600 约 4 s。

### 验证（tests/test_phase4_block2.py，共 23 个）

解析解对照（均匀产热圆柱 + 固定边温，与解析式吻合到
1e-9；常数温度场 → 应力为零；线性温度场 → 解析值对照）；
制造解（圆柱 + 板条各一，Robin/绝热/Dirichlet 全覆盖）；
能量平衡（高斯/平顶，离散积分 = η_h·P_abs）；端帽
（端帽区 Q=0、界面 k 调和平均）；轴上闭环（直接曲率与
解析值偏差 0.00%）；拟合范围效应（窄拟合 r≤1.0·w_L 与解
析值偏差 −1.8%，宽拟合 r≤1.5·w_L 长 +6.2%）；网格收敛
（二阶速率 + 120 vs 240 的界）；应力阈值（裕度分段）；
spsolve 计时（打印实测值）。

### 演示（用户真实腔体 TL1 + 示例参数）

```sh
python3 demo_thermal.py
python3 run_thermal.py --rez /path/to/upload.rez --eng tests/data/example-thermal.eng.json --w-l-um 498.3 --pump 2,5,10
```

w_L = 498.3 µm（CLI 光束在 TL1 入/出口的平均值）。示例参数：
27 mm Nd:YVO4、α_p=10/cm、w_p0=200 µm、M_p²=1.2、η_h=0.24、
dn/dT=3e-6/K（Phase 2 示例覆盖值；库值 3.9e-6/K）、K=5.1、
h=5000 W/m²K（铟箔示例）、杆半径 5 mm——**全部是示例值，
不是实测**。

| 泵浦 | T_max | 鼓包 | σ_a / 裕度 | σ_c / 裕度 | f_th 轴上 | f_th 拟合 | f_th 含鼓包 | 锚点 |
|---|---|---|---|---|---|---|---|---|
| 2 W | 54.1 °C | 0.325 µm | 1.86 MPa / 0.965 | 4.83 MPa / 0.909 | 465.9 mm | 877.5 mm | 269.6 mm | 575 mm |
| 5 W | 105.3 °C | 0.813 µm | 4.66 MPa / 0.912 | 12.08 MPa / 0.772 | 186.4 mm | 351.0 mm | 107.8 mm | 230 mm |
| 10 W | 190.5 °C | 1.625 µm | 9.32 MPa / 0.824 | 24.15 MPa / 0.544 | 93.2 mm | 175.5 mm | 53.9 mm | 115 mm |

轴上闭环偏差 −0.00%（三档一致）。结论：**端面鼓包主导热
透镜**——5 W 时含鼓包 f_th=107.8 mm，纯 dn/dT 为 186.4 mm；
Phase 2 线性模型（锚点 230 mm）没算鼓包，与示例参数的轴
上值差 −19%，与含鼓包值差 −53%。锚点本身是 Phase 2 的假设
值，与示例材料参数并不自洽；真实锚点应由实测光斑经 Phase 3
逆向拟合得到。10 W 时保守界（α_c）裕度 0.544，已进 warn
带（红线 0.50），主值仍 ok；T_max 190.5 °C 已接近 Nd:YVO4
长期工作的谨慎区间，10 W 档需实测 h 与 σ_fracture 再定。

## FFT Fox-Li 物理光学衍射引擎（Phase 4 M3）

`rezeng/foxli.py`（混合传播子 + 分步晶体 + 往返迭代 +
D4σ M²），入口 `run_foxli.py`（JSON 报告）与
`demo_foxli.py`（用户真实腔体交叉验证 + 2/5/10 W 热 M²
曲线）。纯 Python，不改 C++；求解中间值不写进 `.rez`，
全部在 side-car `foxli` 一节。

### 往返算符（逐元件，不压缩为单一 ABCD）

`CavityOperator` 按 `.rez` 元件顺序建往返算符：前向腿
（M1 参考面 → M4）→ 端镜反射 → 返回腿 → M1 反射。
每段自由空间按元件逐段传播，曲面镜/薄透镜按相位因子
处理，每元件处乘圆形孔径截断（半径来自 side-car
`elements` 的 `aperture_diameter_mm` 或 `foxli.apertures`
覆盖；无孔径数据时不截断并在 `aperture_notes` 中标注）。
T/S 两平面分别演化（像散腔），输出 w_T/w_S。**绝不把腔
压成单一等效往返 ABCD**——孔径截断与热 OPD 的空间耦合
只在逐元件传播中保留（Gemini 评审 §1）。

### 传播子选择与 z_c

约定 `exp(+ikz)`：角谱传递函数
`exp(+i·k·z·√(1−(λf)²))`，菲涅耳核
`exp(+i·k·(x₂−x₁)²/(2z))`；会聚透镜乘
`exp(−i·k·r²/(2f))`，ABCD 的 C 元件镜乘
`exp(+i·k·C·r²/2)`。场按 FFT 顺序存储（下标 0 为 x=0）。

临界采样距离 `z_c = N·Δx²/λ`（手算复核：N=256、
Δx=15.625 µm、λ=1064 nm → **58.74 mm**；用户腔网格
256、窗口 8 mm、Δx=31.25 µm → **235 mm**）。短距
（z ≤ z_c）用**带限角谱法 BL-ASM**（2× 补零到 512×512 +
频域截断窗）；长距（z > z_c）用**两步菲涅耳**
（Two-Step Fresnel，等分步、输入/输出网格尺寸一致）。
单 FFT 菲涅耳不用作长腿：z=400 mm 时输出步长
`λz/(NΔx)` = **106.4 µm**，约 0.2 mm 光斑的一半。两步
菲涅耳在小 z 是错的（等分中间网格比光斑窄、截断光束：
z=10 mm 时 w 偏大 **+37%**、M²=7.05），所以分发器加了
护栏：只有当 z > z_c **且**中间半宽 `λz/(4Δx)` ≥ 3 倍
中间光斑半径时才用两步菲涅耳，否则回退 BL-ASM；负 z
恒用 ASM。用户腔：d1/d2/d4（372/470/277 mm）走两步菲
涅耳，d3（25.67 mm）与晶体薄片（6.75 mm）走 ASM。

实测（高斯 w₀=0.2 mm、256、8 mm 窗口）：分发器在
z=10/30/100/200/300/400/470 mm 全段 w 偏差 **0.00%**、
M²=1.0000、功率守恒；ASM +400/−400 mm 往返相对 L2 误差
2.4e-11。

### 晶体分步与锚点焦距的三个定义

27 mm 热透镜晶体做 4 层分步薄透镜（Split-Step）：半片
玻璃 + 每层一片 OPD 相位板（总 OPD 的 1/4）+ 玻璃片，
对称 Strang 分裂；玻璃内传播用介质波长 λ/n；相位板
`exp(+i·k₀·OPD)`，`OPD(r) = −r²/(2f_th) + c₄r⁴ + c₆r⁶`
（Gemini 评审在相反约定下写 `exp(−ik·OPD)`，此处符号
由分步–GRIN 对照与 CLI 交叉验证锁定；符号反了会散焦晶
体，两项验证都失败）。

**锚点 f_th 有三个不同的值，只能用 OPD 等效值**：对用户
TL1（γL=0.231），`.rez` 的 F=230 mm 是 C++ `calc_focus`
定义 `F = 1/(tan(γL)·n·γ)`；矩阵等效薄透镜 `−1/C =
1/(n·γ·sin γL)` = 236.3 mm；分步 OPD 等效值
`f_th = 1/(n₂L)`（n₂ = n₀γ²）= **234.2 mm**。三者差 ~3%，
只有 OPD 等效值是抛物折射率分布的忠实分步离散化：
与精确 GRIN（`qevolve.evolve_element`）对照，4 片时出口
R 偏差 **−0.08%**、8 片 **−0.02%**；用 `.rez` F 得
−2.7%，用矩阵 F 得 +1.3%（收敛到错误的连续极限）。
`CavityOperator` 的锚点直接由 γ 算
`f_th = 1/(n₀γ²L)`（T/S 可分别取值，散焦 γ<0 时 f_th
为负），不读 `.rez` F。**拟合 OPD 另有钳制**：`fit_opd`
只在 r ≤ 1.5·w_L 内拟合，超出拟合半径多项式发散（5 W
示例在 r=2 mm 处 OPD −200 µm、约 190 个波长，网格上严重
混叠），所以 `crystal_pass` 的 `r_max_m` 把 OPD 在拟合
半径外钳制为该半径处的值（`phase_plate()` 现返回
`r_fit_max_mm`；锚点二次项不限幅）。

### 收敛与本征模

初场：CLI 高斯解（参考面光斑）叠加 **5% 随机复噪声**
（固定种子可复现；噪声功率占比 noise_frac²，测试锁定
0.05 → 0.25%）。纯高斯会锁死在对称模上，纯随机收敛太
慢。**有 OPD 时初场必须是该热透镜腔自身的 CLI 高斯**：
`resolve_foxli` 把晶体 F 覆盖为与 OPD 的 f_th 等效的 CLI
F（`opd_f_th_to_cli_F`：f_th=351 mm → F=346.8 mm；
f_th=877.5 mm → F=873.3 mm；f_th=93.2 mm → F=89.0 mm，
由 γ=1/√(n₀f_thL)、F=1/(tan(γL)·n·γ) 换算）再取 CLI 光
束——用锚点腔（F=230 mm）的高斯作初场，等于从热腔多
个模式的叠加态出发，而无损耗算符没有甄别能力（见下）。

双收敛判据（Gemini 评审 §2）：`|γ_n − γ_{n−1}|/|γ_n| <
1e-5` **且**场重叠缺陷 `1 − |⟨E_n, E_{n−1}⟩|/(‖E_n‖‖E_{n−1}‖)
< 1e-5`；`γ_n = ⟨E_{n−1}, E_n⟩/‖E_{n−1}‖²`（归一化前），
往返衍射损耗 `L_diff = 1 − |γ|²`；迭代上限 1000 圈。若
两个损耗相近的模式拍频导致不收敛，输出明确标注
`converged=False` + 当前 γ 与重叠值，不编造收敛结果：
重叠缺陷连续 50 圈相对改善 <1% 且 γ 已稳定时判为
`plateau=True`、提前停止。

**无损耗算符的功率迭代本质上不收敛**（实测，不是理论
推测）——这是 Fox-Li 方法本身的特性，不是代码 bug：往
返算符近乎幺正，所有模式的 |γ| 都 ≈1，没有损耗甄别，
功率迭代只能让场在模式叠加态里旋转，无法选出单一本征
模。证据有三：① 无孔径 5% 噪声起点重叠缺陷在 ~6e-4 处
进入平台（75 圈判 plateau，L_diff ≈ 1.1e-3，而真实功率
损耗仅 1.2e-6——L_diff 在此被模式混合主导，不是真实损
耗）；② 锚点算符从偏离的初场（w=0.12 mm 而非本征模
0.100 mm）出发也不收敛（缺陷卡在 8.4e-3）；③ 纯二次
f_th=351 mm 从正确的热腔高斯出发，缺陷仍以每圈 ~0.4%
缓慢衰减（60 圈 5.8e-4），严格 1e-5 判据需 ~1000 圈，
平台检测会提前触发——场本身已是高斯（w 与 CLI 差 0.6%、
M²=1.004），只是缺陷判据达不到。所以交叉验证从纯 CLI
高斯出发（它是无孔径算符的本征模，2 圈收敛，见下）；
**热球差演示必须加小孔径提供模式甄别**（M2 半径 2.0 mm，
见热 M² 一节），否则强球差下迭代直接发散（5 W 全 OPD
无孔径 100 圈缺陷 0.32、M² 漂到 6–10）。**Arnoldi
加速已试过、不可行**：`scipy.sparse.linalg.eigs` 在本征
值密集分布于单位圆上时 270 次矩阵–向量乘（289 s）仍只
得到 3% 残差的混合模（M1 w 偏大 58%、M²=1.59），不是
基模；README 留作后续（更合适的本征求解器或 Gouy 相位
滤波），不纳入本块。

### M² 与光斑输出

D4σ M² **必须含位置–角度协方差项**
`M_x² = 4π√(σ_x²σ_fx² − σ_{x,fx}²)`，或先传播到束腰再
用 `M_x² = 4πσ_{x0}σ_{fx}`。非束腰截面直接套用
`4πσ_xσ_{fx}` 会严重虚高：R=100 mm、w=0.2 mm 的曲率
波前，naive 值 1.55、协方差修正后 1.00（测试锁定两者），
与传播到束腰（z₀=−58.2 mm）再算的 M² 一致（±0.02）。

输出：收敛后（或 plateau）的二维光斑强度图——数值数组
（`foxli_report` 的 `field`）+ 可选 PNG（`spot_png`，
matplotlib；未装时返回 False、不安装）+ ASCII 摘要
（`spot_ascii`，对数标度 64×24）；各参考面处的 w_D4σ、
M²、L_diff、收敛圈数与 γ（`foxli_report` 的 `beam` 逐元
件对照 CLI）。

### 交叉验证（验收标准，实测）

关闭所有孔径截断与高阶像差（c₄=c₆=0）、纯 CLI 高斯起
点、用户真实腔体：

| 面 | w_T/mm（Fox-Li） | CLI/mm | 偏差 | M²_T |
|---|---|---|---|---|
| M1 | 0.0998 | 0.1000 | −0.2% | 1.0000 |
| d1/M2 | 1.2664 | 1.2641 | +0.2% | 1.0000 |
| d2/M3 | 0.4896 | 0.4892 | +0.1% | 1.0000 |
| d3/TL1 | 0.5057 | 0.5054 | +0.1% | 1.0000 |
| d4/M4 | 0.2051 | 0.2057 | −0.3% | 1.0000 |

2 圈收敛，L_diff = **1.4e-6**（< 1e-4），M² 全段
∈ [1.00, 1.02]，w 偏差全段 <1%——**验收标准全部满足**。
带 5% 噪声的同配置 60 圈不收敛（plateau 机制，见上），
但 w/M² 仍在 1% / 1.02 内（M1 w +0.74%、M²=1.0036），
报告如实写 `converged=False`。

孔径算例（M2 半径 2.0 mm，光斑 w=1.26 mm）：58 圈收敛，
L_diff = **0.0128**，与截断估计
`1−(1−exp(−2a²/w²))²` = 0.0133（往返两次）量级一致；
硬边衍射使 M²=1.26、D4σ w 偏大 +30%（衍射环抬高二阶
矩，物理效应，不是数值误差）。

### 热球差 M² 退化（演示，示例参数）

M2 相位板（dn/dT 拟合，`thermal_report` 的
`phase_plate`；**不含端面鼓包**——鼓包主导热透镜，见
M2 节，含鼓包的拟合 f_th 在 5 W 为 107.8 mm 而非 351 mm；
Fox-Li 相位板目前只接 dn/dT 拟合）按泵浦功率取 2/5/10 W
三档；每档各跑两次——全 OPD（二次 + c₄/c₆）与纯二次
（c₄=c₆=0），分离球差的贡献。10 W 拟合 f_th=175.5 mm
（D=5.70/m）落在稳区 I/II 之间的间隙（腔失稳），故 10 W
档二次项改用轴上（近轴）f_th=93.2 mm（D=10.73/m，稳区
II 内），c₄/c₆ 保留拟合值，并注明原因（模平均透镜不是
稳定性判据，约束模看到的是中心强曲率）。**三档都加小孔
径（M2 半径 2.0 mm）选模**：无损耗算符的功率迭代无法收
敛（见上），强球差下无孔径时 5 W 全 OPD 100 圈缺陷仍
0.32；孔径是 Fox-Li 建模选择，纯二次列给出孔径自身的
贡献，球差的增量效应是全 OPD 与纯二次之差。

| 泵浦 | f_th/mm | M² 全 OPD（T） | M² 纯二次（T） | w(M1)/mm 全/纯二次 | 收敛 |
|---|---|---|---|---|---|
| 2 W | 877.5 | 10.22 | 3.38 | 0.617 / 0.268 | 全 30 圈 / 纯 12 圈 |
| 5 W | 351.0 | 5.83 | 1.13 | 0.389 / 0.132 | 全 42 圈 / 纯 19 圈 |
| 10 W | 93.2（近轴） | 2.97* | 1.58 | 0.800 / 1.175 | 全 **未收敛**（100 圈）/ 纯 95 圈 |

\* 10 W 全 OPD 未收敛：100 圈时 M²=2.97，200 圈时漂到
5.03（缺陷仍 0.075），数值不可靠，只说明该档示例参数
下模式严重畸变、Fox-Li 无法稳定——10 W 档不是可用的
演示工作点。**曲线不是单调的**，原因不在球差本身，而
在傍轴透镜随功率变化：2 W 的 f_th=877.5 mm 靠近稳区 I
下沿（D=1.14/m），模斑巨大、孔径截断主导 M²（纯二次
已达 3.38）；5 W 在稳区 I 中部，球差主导（全 5.83 vs
纯 1.13，增量 ~5 倍）；10 W 在稳区 II，模斑又大
（M1 w=1.04 mm）且球差最强。**这组演示数不是他的真实
激光的预测**：真实热 OPD（实测或 M2 真实热参数）与真实
孔径拿到后要重算；自洽做法是 Fox-Li 模斑与热 OPD 拟合
的 w_L 迭代（本块未做，见局限性）。

### 局限性

- **模式拍频与无损耗收敛**：无孔径/弱甄别时功率迭代收敛
  极慢或平台化（上文），需本征求解器或孔径提供甄别；
  报告如实标 `plateau`，不编造收敛。**热球差演示用小孔
  径（M2 半径 2.0 mm）选模**，这是 Fox-Li 的建模选择，
  不是真实镜面口径（真实镜面 Ø25.4 mm，相对 1.26 mm 光
  斑几乎无截断）；纯二次对照列给出孔径自身的贡献
  （M²≈1.1），球差的增量效应是全 OPD 与纯二次之差。
  真实孔径拿到后应改用真实值重算。
- **初场必须与算符的腔一致**：有 OPD 时初场取热透镜腔
  自身的 CLI 高斯（`opd_f_th_to_cli_F` 换算），不是锚点
  腔的高斯；否则迭代从多模式叠加态出发，在无损耗算符
  上无法收敛。
- **OPD 钳制**：二次项延展全网格（傍轴透镜），只有拟合
  的 c4/c6 在 r_fit 外冻结；光束宽于拟合半径时（如本演示
  5 W 档模斑胀到 1.66 mm 而拟合半径仅 0.747 mm），冻结
  的球差项本身成为一个人为边界，结果需按自洽性解读。
  钳制二次项是错的（已修，见上文）：它会把透镜截成硬
  边，纯二次对照 M² 变成 1.42。
- **网格尺寸与计算时间**：N=256、窗口 8 mm 时单圈约
  **1.2 s**（24 次 512² FFT 量级）；60 圈约 70 s、100 圈
  约 2 分钟。窗口 4 mm 会截断 M2 光斑（w=1.26 mm，单程
  损耗 ~0.65%），破坏 L_diff < 1e-4 的判据，故用户腔用
  8 mm 窗口（截断 ~2e-9）。更大网格/更长迭代按比例变慢；
  Arnoldi 加速已试过不可行（上文），留作后续。
- **相位板不含鼓包**：`thermal_report` 的 `phase_plate`
  是 dn/dT 拟合；鼓包主导时（5 W 含鼓包 f_th=107.8 mm
  vs 纯 dn/dT 351 mm）需另行接入含鼓包拟合。
- **自洽性**：Fox-Li 用的 OPD 按固定 w_L 拟合，若算出
  的模斑与 w_L 不符（本演示 5 W 档），应迭代 w_L →
  OPD → 模斑直至自洽；本块只做单程演示。
- **单圈传播子近似**：两步菲涅耳在小 z 有已知失效（见
  上），由分发器护栏规避；晶体分步为 Strang 分裂（4 片
  时 R 偏差 0.08%），非精确 GRIN。

### 验证（tests/test_phase4_block3.py，共 30 个）

采样手算（z_c=58.74 mm、单 FFT 步长 106.4 µm）；传播子
对照（分发器全段 w 偏差 0.00%、M²=1.0000、功率守恒；
ASM 可逆 2.4e-11；两步菲涅耳长距准确、小 z 失效锁定）；
分步晶体 vs 精确 GRIN（4 片 R 偏差 0.08%、8 片 0.02%；
`.rez` F 得 −2.7% 的反例锁定；锚点 f_th=234.2 mm 锁定；
OPD 钳制锁定——**只钳制 c4/c6，二次项延展全网格**，纯
二次对照回归测试锁住该修复；无二次项 = 玻璃传播）；初
场（5% 噪声功率占比 0.25%、种子可复现、纯高斯 M²=1）；
M² 协方差修正（曲率波前 naive 1.55 vs 修正 1.00、束腰
传播一致）；收敛判据（恒等算符 2 圈收敛；双模拍频
plateau 如实报告；相位漂移跑满 max_rounds）；交叉验证
（无孔径 w<1%、M²∈[1.00,1.02]、L_diff<1e-4；带噪声平
台化如实报告）；孔径（M2 2.0 mm 收敛、L_diff 量级与截断
估计一致）；热球差（5 W 相位板 + M2 孔径选模 M²>1.5；
纯二次对照 M²∈[1.00,1.02]、w 与 CLI 差 <3%）；side-car
`foxli` 一节校验（合法通过、8 类非法值拒绝）。

### 演示（用户真实腔体 + 示例参数）

```sh
python3 demo_foxli.py
python3 run_foxli.py --rez /path/to/upload.rez --eng tests/data/example-foxli.eng.json [--max-rounds 60] [--thermal-power 5] [--paraxial] [--png /tmp/spot.png]
```

`demo_foxli.py`：交叉验证（2 圈收敛、L_diff=1.4e-6、
M1 光斑 ASCII + PNG `demo_foxli_spot.png`）与 2/5/10 W
热 M² 曲线（全 OPD vs 纯二次对照，M2 孔径选模）。
`run_foxli.py`：单次 Fox-Li 报告（JSON 到 stdout，光斑
ASCII 含在 `spot_ascii` 中）；`--thermal-power P` 从 M2
热求解器取 P 瓦时的相位板作 OPD（thermal 一节来自
`--thermal-eng`，默认与 `--eng` 同文件），`--paraxial`
改用轴上 f_th。全部演示数用示例参数，**不是他的真实激
光的预测**。

## 运行与测试

```sh
cd engineering
python3 -m unittest discover -s tests        # 全部测试（324 个）
python3 run_optimizer.py --config config.json  # 优化器 / Snap（JSON 配置，打印 JSON 结果）
python3 run_zones.py --rez /path/to/cavity.rez [--d-max 12] [--n-points 300] [--f-mm 230]  # 双稳区扫描
python3 demo_optimizer.py                     # 优化器 + Snap + 双稳区全流程演示
python3 run_montecarlo.py --rez <file.rez> [--n 1000] [--chunk 250] [--seed 0]  # 蒙特卡洛公差（JSON 输出到 stdout）
python3 demo_montecarlo.py                    # 用户真实腔体 + 示例公差带的 N=1000 蒙特卡洛演示
python3 run_reverse.py --rez <file.rez> --points-T "30:0.21,200:0.39,800:1.33" [--points-S ...]  # 逆向拟合（JSON 输出到 stdout）
python3 demo_reverse.py                       # 用户真实腔体 + 合成测量数据的逆向拟合演示（3 点恢复 + 2 点远场简并陷阱）
python3 run_checks.py /path/to/cavity.rez    # 手动跑检查（side-car 默认同名 .eng.json）
python3 run_checks.py cavity.rez other.eng.json
python3 run_solves.py pickup cavity.rez --driven d4:L --source d1:L --k 0.5 --b 90.862702 --out cavity.pickup.rez
python3 run_solves.py waist-size cavity.rez --variable d1:L --element M1 --target 0.12 --bounds 330:380 --apply
python3 run_solves.py waist-position cavity.rez --variable d1:L --element M4 --target-ref M4:0 --bounds 270:380
python3 demo_solves.py                        # 用户真实腔体的端到端演示（输出到 /tmp）
python3 run_power.py --rez /path/to/cavity.rez --toc-scan   # 功率扫描（JSON 输出到 stdout）
python3 demo_power.py                         # 用户真实腔体 + 示例参数的功率演示
python3 run_shg.py --rez /path/to/cavity.rez --pump 2,3,5,7,10  # SHG 扫描（JSON 输出到 stdout）
python3 demo_shg.py                           # 用户真实腔体 + 插入的 LBO 晶体 + 示例参数的 SHG 演示
python3 run_jones.py --rez /path/to/cavity.rez [--eng <file.eng.json>]  # 琼斯 + 色散报告（JSON 输出到 stdout）
python3 demo_jones.py                         # 用户真实腔体 + 示例参数的琼斯/GDD/TOD 演示
python3 run_mopa.py --osc /path/to/osc.rez --eng <chain.eng.json>  # MOPA 链路（JSON 输出到 stdout）
python3 demo_mopa.py                          # 示例两级 MOPA 链演示
python3 demo_jacobian.py                      # 用户真实腔体 + 示例镜架参数的雅可比/螺丝指南演示
python3 run_ghosts.py /path/to/cavity.rez [side-car] [--wavelength 1064]  # 鬼像/标准具扫描（JSON 输出到 stdout）
python3 run_redlight.py /path/to/cavity.rez [side-car] [--w0 0.5] [--double-pass]  # 632.8 nm 红光对照（JSON 输出到 stdout）
python3 run_export.py /path/to/cavity.rez [side-car] --coating --zmx /tmp/cavity.zmx --dxf /tmp/cavity.dxf --thin-lens-check  # 镀膜表 / .zmx / .dxf 导出
python3 run_thermal.py --rez /path/to/cavity.rez [--eng <file.eng.json>] [--pump 2,5,10] [--w-l-um 498]  # 热传导 + 断裂报告（JSON 输出到 stdout）
python3 demo_thermal.py                         # 用户真实腔体 TL1 + 示例参数的 2/5/10 W 热演示
python3 run_foxli.py --rez /path/to/cavity.rez [--eng <file.eng.json>] [--max-rounds 60] [--thermal-power 5] [--thermal-eng <thermal.eng.json>] [--paraxial] [--png /tmp/spot.png]  # Fox-Li 衍射报告（JSON 输出到 stdout，含光斑 ASCII）
python3 demo_foxli.py                           # 用户真实腔体交叉验证 + 2/5/10 W 热 M² 曲线演示
python3 run_odr.py --rez /path/to/cavity.rez [--eng <file.eng.json>] [--out /tmp/cavity.odr.html] [--foxli] [--mc-n 1000] [--pump 2,5,10] [--real]  # ODR 评审报告（HTML + JSON 摘要到 stdout）
python3 demo_odr.py                             # 用户真实腔体 + 四个示例 side-car 合并的 ODR 演示
python3 mcp_server.py                           # MCP 服务端（stdio，供 Cursor / Claude Desktop 调用 7 个工具）
```

示例数据：`tests/data/example.eng.json` 是给用户真实腔体
（`~/workspace/user/files/upload.rez`）配的**示例** side-car，所有数
值都是编的、仅用于演示分级，绝不是用户的真实激光参数。
`tests/data/example-power.eng.json` 同理：全部泵浦/晶体/热透镜参数
都是文献典型示例值（见“功率求解器”一节），演示用，不是实测。
`tests/data/example-shg.eng.json` 同理：LBO 晶体与倍频参数也都是
示例（见“SHG 倍频模块”一节）。
`tests/data/example-jones.eng.json` 同理：双折射、GVD/TOD、SESAM
与色散镜参数也都是示例（见“琼斯偏振矩阵”“色散累加”两节）。
`tests/data/example-mopa.eng.json` 同理：种子与两级放大器参数
也都是示例（见“MOPA / 再生放大链路”一节）；各级 `.rez`
（`mopa_amp_sp.rez`、`mopa_regen_sw.rez`）是为演示新建的最小
SP/SW 文件（晶体均为 ElemPlate，见“SHG 倍频模块”中关于
ElemMediumRange 的说明）。
`tests/data/spherical_symm_free.rez` 是 `bin/examples/spherical_symm.rez`
去掉 `param_links` 的 fixture（M1.R/M2.R 不再由全局 R0 链接），
专供优化器复现 Phase 0 原型最优（见“评价函数与优化器”一节）；
原文件本身未改动。
`tests/data/example-mc.eng.json` 同理：公差带（ΔL ±0.5 mm、ΔR/R
±1%、Δα 0.5 mrad 锥角、Δf_th ±5%）与泵浦/晶体参数也都是示例
（见“蒙特卡洛公差仿真”一节）。
`tests/data/example-reverse.eng.json` 同理：输出镜基底数据是标称
示例值（6.35 mm 熔融石英，n=1.45），真实 M4 基底数据未知
（见“逆向拟合”一节）。
`tests/data/example-phase4.eng.json` 同理：各表面残余反射率
（M1/M4 衬底背面 4%、M2/M3 衬底背面 0.5%、TL1 两面 0.2%）、
LIDT（镜面 5、TL1 10 J/cm²）、楔角（TL1 0.1 mrad）、口径
（镜面 Ø25.4、TL1 Ø10 mm）、脉冲参数（1 mJ、10 ns、1 kHz）
也都是示例（见“鬼像/标准具扫描”“镀膜表”两节）；演示的
`.zmx` / `.dxf` / JSON 报告写到 /tmp，不进仓库。
`tests/data/example-thermal.eng.json` 同理：泵浦/晶体/冷却
参数（α_p 10/cm、w_p0 200 µm、M_p² 1.2、η_h 0.24、
dn/dT 3e-6/K、K_c 5.1 W/mK、h 5000 W/m²K、杆半径 5 mm）
也都是示例（见“热传导与热断裂”一节），演示用，不是实测。
`tests/data/example-foxli.eng.json` 同理：Fox-Li 网格与
迭代参数（256、窗口 8 mm、λ=1064 nm、噪声 5%、种子 0、
60 圈、容差 1e-5、分步 4 片）也都是示例配置（见“FFT Fox-Li
物理光学衍射引擎”一节）；无孔径、无 OPD，热 OPD 由演示
调用 M2 热求解器现场算出，不在 side-car 里。
## ODR 评审报告（Phase 4 M4）

`rezeng/odr.py`（入口 `run_odr.py`、`demo_odr.py`）把前面各
块的结果汇总成一份 HTML 评审报告：一键出光路包络、稳区轨迹、
公差良率、热应力裕度、Fox-Li 衍射、鬼像、红光对照、镀膜 BOM
与 CAD/Zemax 导出检查，共 9 节。

```sh
python3 run_odr.py --rez /path/to/cavity.rez [--eng <file.eng.json>] \
    [--out /tmp/cavity.odr.html] [--foxli] [--mc-n 1000] \
    [--pump 2,5,10] [--real]
```

- `--foxli`：默认不含 Fox-Li 节（跑衍射较慢）；加此开关才
  跑 Fox-Li（需要 side-car 里有 `foxli` 节；`data["_rez_path"]`
  由 `build_odr_report` 自动补上，供 Fox-Li 跑 headless CLI 取
  初始高斯光束）。
- `--mc-n`：蒙特卡洛样本数（默认 1000；演示常用 250）。
- `--pump`：热分析泵浦功率档（逗号分隔，默认 `2,5,10` W）。
- `--real`：去掉页眉的“示例值”横幅——只有参数确实是实测
  值时才用；默认报告明确标注**参数为示例值，不是真实激光
  参数**。
- 每一节都标注数据来源（模块名）与示例/真实属性；某一节
  失败时该节记为 `skipped`/`error`，报告其余部分照常生成，
  绝不整份崩溃。stdout 另打印一份 JSON 摘要（各节 id /
  status / note、n_ok、out_html 路径）。
- 图表用 Matplotlib 画成 base64 PNG 内嵌进 HTML（光束包络、
  稳区轨迹、公差直方图），无外部图片链接，单文件可离线打开；
  不用 ReportLab 或 Sphinx。WeasyPrint 转 PDF 未装，不做；
  需要 PDF 时用浏览器打开 HTML 后打印为 PDF。

报告结构（9 节）：1. 腔体与高斯光束（g_T/g_S、总长、各元件
光斑，来源：headless CLI） 2. 稳区轨迹（Zone I/II 与工作点，
来源：zones.py） 3. 蒙特卡洛公差（失稳率 Wilson 95% CI、监
测点中位数、灵敏度排序，来源：montecarlo.py） 4. 热与断裂
（各泵浦档 T_max、鼓包、σ_c、断裂裕度，红线裕度 ≥ 50%，
来源：thermal.py + fracture.py） 5. Fox-Li 衍射（收敛、L_diff、
各元件 M²，来源：foxli.py；默认跳过） 6. 鬼像与标准具扫描
（来源：ghosts.py） 7. 红光对照（来源：redlight.py）
8. 镀膜 BOM 清单（来源：export.py 镀膜表） 9. CAD/Zemax
导出检查（.zmx/.dxf 内存生成 + 结构自检，来源：export.py；
.zmx 未在 OpticStudio 里验证过）。

## MCP 服务端（Phase 4 M4）

`mcp_server.py` 把同一套 Python 引擎以 MCP 服务端暴露给
Cursor / Claude Desktop 等 AI 客户端：stdio 传输、粗粒度
工具、底层直接 import `rezeng`，不接受任意 shell 命令。

```sh
python3 mcp_server.py          # stdio 服务端，直接跑
```

工具清单（7 个，输入输出均为 JSON Schema，由函数签名自动
生成）：

| 工具 | 作用 |
| --- | --- |
| `run_foxli` | Fox-Li 衍射（`max_rounds`、`thermal_power`、`paraxial`） |
| `analyze_thermal_fracture` | 热传导 + 热断裂（泵浦功率档） |
| `scan_ghosts` | 鬼像 / 标准具扫描 |
| `redlight_compare` | 632.8 nm 红光对照 |
| `export_cad_zmx` | 镀膜表 + .zmx + .dxf 写到 `out_dir` |
| `run_montecarlo` | 蒙特卡洛公差（`n`、`seed`、`watch`） |
| `generate_odr_report` | ODR HTML 报告（`include_foxli`、`mc_n`、`pump_powers`） |

每个工具只接受 `.rez` 路径 + side-car 路径 + 明确参数；
缺失文件、side-car 校验失败等预期错误以 MCP `ToolError`
返回（客户端看到 `Error executing tool <name>: <原因>`，
`isError=true`），服务端不崩溃、后续调用照常；非预期异常
按 SDK 惯例只返回通用文本、详情只记服务端日志。

依赖注意：`mcp` 包的版本是 **2.3.0**，其中的 FastMCP 已
改名为 **`MCPServer`**（`from mcp.server.mcpserver import
MCPServer`），用法与旧 FastMCP 相同；stdio 传输用
**NDJSON**（每行一个 JSON 对象），不是 LSP 式的
Content-Length 分帧——测试客户端 `tests/test_mcp_stdio.py`
按 NDJSON 实现，旧分帧写法会无限挂起。MCP 工具不跑 Fox-Li
与蒙特卡洛之外的慢调用测试（端到端测试覆盖 tools/list、
scan_ghosts、redlight_compare、export_cad_zmx、缺失文件错
误、错误后存活；Fox-Li 与蒙特卡洛已有各自的测试文件）。

## C++ 原生集成：工程中心（Phase 4 M4）

`src/funcs/EngineeringHubDialog.h/.cpp` + `src/funcs/
EngineeringBackend.h/.cpp` 是 Phase 4 的 C++/Qt MVP 入口：
主窗口菜单 `函数 --> 工程中心…`（`CalcManager::
funcEngineeringHub`，参考 OptimizerWindow 的接入方式），
打开一个模态多标签页对话框；每个标签页经 QProcess 调用
对应的 Python 后端脚本，把 JSON 结果展示为摘要 + 数值表
（结果图先以文本摘要 + 数值表呈现，图片嵌入留待后续）。

| 标签页 | 后端脚本 | 结果 |
| --- | --- | --- |
| Fox-Li | `run_foxli.py --max-rounds 200` | 收敛、圈数、L_diff、M1 处 M² |
| 热分析 | `run_thermal.py --pump 2,5,10` | 各泵浦档 T_max、鼓包、σ_c、裕度 |
| 鬼像 | `run_ghosts.py <rez> <eng>` | ok/warn/fail/nodata、标准具个数 |
| 红光 | `run_redlight.py <rez> <eng>` | 路径（cold/fallback）、冷腔 g_T/g_S |
| 导出 / ODR | `run_export.py <rez> <eng> --coating --zmx … --dxf …`，随后 `run_odr.py --mc-n 250` | 镀膜表文本 + .zmx/.dxf 验证、ODR 报告路径；“打开 ODR 报告”按钮用浏览器打开 HTML |

后端定位规则（`EngineeringBackend::locateEngineeringDir`，
按顺序取第一个含 `run_foxli.py` 的目录）：

1. 程序可执行文件所在目录旁的 `engineering/`；
2. 环境变量 `REZONATOR_ENGINEERING_DIR`；
3. 用户设置 `EngineeringHub/engineeringDir`（QSettings）。

Python 解释器路径同样可配置（设置 `EngineeringHub/
pythonExecutable`，默认 `python3`）。找不到后端时，对话框
明确显示已查找的位置与安装说明，运行按钮禁用，**不崩溃、
不静默失败**；后端退出非零时显示退出码与标准错误输出。
对话框要求方案已保存（未保存的方案无法运行，须先保存）；
工程参数全部来自方案文件旁的 side-car（`<方案>.rez.eng.json`），
求解中间值不写进 `.rez`。

未做的项（明确列出，不硬凑）：Solves 实时滑块联动推迟到
Phase 4.5。以下两项在 Phase 4 后的跟进工作中已完成
（见下一节）。

C++ 测试：`src/tests/test_EngineeringHub.cpp`（9 个：后端定
位三档、脚本解析、命令拼接、JSON 解析正/反、解释器缺失、
真实后端 smoke——对用户真实腔体跑 `run_ghosts.py`，断言
ok=6/warn=1），注册在 `src/tests/TestSuite.h`；帮助文本见
`help/func_engineering_hub.rst`（已加入 `help/functions.rst`
的函数列表）。

## C++ 原生集成：LIDT 红框与红光一键切换（Phase 4 跟进）

Phase 4 M4 留下的两项主界面工作（C++ 为主，Python 侧零改动——
`checks.py` 的 JSON 已含 `value`/`limit`，`redlight.py` 的
材料库内置）：

### LIDT 红框预警（元件列表）

`src/funcs/LidtMarks.h/.cpp`（`parseLidtReport`）解析
`run_checks.py` 的 JSON：只取 `kind == "lidt"` 且状态为
`fail`/`warn` 的条目；`ok`/`nodata` 与其他检查项
（aperture/board）不标记。`src/funcs/LidtCheckRunner.h/.cpp`
经 QProcess 异步跑 `run_checks.py <rez> <eng>`（与
EngineeringBackend 同一套定位规则）；新一次运行会丢弃进行
中的旧运行。`src/widgets/ElementsTable.h/.cpp` 的模型按标记
着色：`fail`（比值 > 1）浅红底 `0xffc9c9`，`warn`（比值 > 0.8）
琥珀底 `0xffe4a8`；行 tooltip 为“峰值 X J/cm² / LIDT Y，比值 Z”
（例如用户腔体 M1：峰值 6.18 J/cm² / LIDT 5.0，比值 1.24）。

触发时机：`src/windows/SchemaViewWindow.h/.cpp` 在 `schemaLoaded`
时自动跑一次——前提是方案已保存且 `<方案>.rez.eng.json` 存在；
另有菜单/工具栏入口“刷新 LIDT 检查”手动重跑。光路参数改变后
**不自动重跑**（避免频繁调 Python），标记反映的是上一次运行
的结果。side-car 缺失、后端找不到或运行失败时静默清除标记，
不弹窗、不崩溃。

实测（用户真实腔体 + `tests/data/example-phase4.eng.json`，
激光与 LIDT 均为示例值）：38 项检查中 LIDT 仅 M1 为 fail
（6.1755 / 5.0 J/cm²，比值 1.2351），其余 M2/M3/TL1/M4 均为 ok，
d1–d4 为 nodata；元件列表只标红 M1 一行。

### 红光一键切换（主界面）

主窗口工具栏 + `函数` 菜单新增可勾选的“红光模式”
（`src/windows/ProjectWindow.h/.cpp`，`CalcManager::
funcRedlightToggle`）；按下即切换，状态可见（按钮按下/菜单
勾选），再点一次切回。复用与工程中心红光页同一后端
`run_redlight.py <rez>`（无 side-car 参数；脚本缺省自动加载
`<方案>.rez.eng.json`——有 side-car 时楔角等数据照常用，无则
用内置材料库，仍能跑）。

展示复用主界面已有的“元件处光束参数”表
（`src/math/BeamParamsAtElemsFunction.h/.cpp` 新增第 4 列
“X 光轴偏移”；`src/funcs/BeamParamsAtElemsWindow.h/.cpp`
新增红光覆盖）：红光模式下 W 列显示每元件的 `w_633_T/S`，
X 列显示 `x_633_T/S`，R/V 列显示 N/A；窗口标题标明当前波长与
路径，如“元件处光束参数 — 红光 632.8 nm（外部注入）”或
“……（冷腔本征模）”。正常模式 X 列恒为 0（热本征模光轴即参考
轴）。切回时恢复 1064 nm 的正常显示。红光报告只描述已保存的
文件，方案一经编辑即清除覆盖（`recalcRequired` 钩子），避免
用过期数据误导。

降级行为：未保存方案或找不到后端时按钮置灰，tooltip 说明
原因（“请先保存方案”/后端未找到）；后端运行失败时开关自动
弹回，不崩溃。实测（用户真实腔体）：path 为 fallback（冷腔
g_T −1.95 / g_S −1.99 失稳，自动走外部 HeNe 单程）；无 side-car
时 M1 w_633_T = 0.1040 mm（vs w_1064_T = 0.1000 mm，+4.0%），
偏移 0；带示例 side-car（TL1 楔角 0.1 mrad）时 M1 x_633_T =
−0.0177 mm。

C++ 测试：`src/tests/test_LidtRedlight.cpp`（7 个：LIDT 解析
只取 warn/fail、空报告、side-car 路径、红光解析 fallback 与
坏报告拒绝、光束参数红光覆盖端到端、真实后端 smoke——对用户
腔体跑 `run_checks.py`，断言仅 M1 fail 6.1755/5.0）；另
`src/tests/test_TableFunction.cpp` 的 `complare_between_elems`
（11 个）因新增 X 列把 `valCount` 从 3 改为 4，并加了 X 左右
连续性断言。Python 侧无改动，测试数保持 324；C++ 全套
555 个（548 + 7）。帮助文本见 `help/func_engineering_hub.rst`
新增的两节。

## 依赖清单（Phase 4 M4 新增）

除 Phase 1–3 已有的 numpy 1.26.4、scipy 1.11.4、ezdxf 1.4.5
外，本块新增三个用户级 pip 依赖（`pip3 install --user
--break-system-packages …`，与 ezdxf 同样的安装方式）：

- `mcp` 2.3.0（MCP 服务端；注意 FastMCP 已改名 MCPServer）
- `jinja2` 3.1.6（ODR 报告模板）
- `matplotlib` 3.6.3（ODR 报告内嵌图；此前已装）

C++ 侧无新增第三方依赖（Qt 5.15.2 + QProcess + QSettings）。
