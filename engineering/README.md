# reZonator 工程层（Phase 1–2）

Python 层：`.rez` 解析、单位换算、无头 CLI 封装、工程检查、Solves 与
功率求解器。只用标准库 + numpy/scipy。光学计算一律复用原生 C++
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
| `run_checks.py` | 检查的命令行入口：`python3 run_checks.py <file.rez> [side-car]` |
| `run_solves.py` | Solves 的命令行入口：`python3 run_solves.py pickup|waist-size|waist-position …` |
| `run_power.py` | 功率求解器的命令行入口：`python3 run_power.py --rez <file.rez> [--toc-scan]` |
| `demo_solves.py` | 用户真实腔体的 Pickup + 束腰 Solve 端到端演示（输出到 /tmp） |
| `demo_power.py` | 用户真实腔体 + 示例参数的 P_out–P_pump 曲线与 T_opt 扫描演示 |
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

## 运行与测试

```sh
cd engineering
python3 -m unittest discover -s tests        # 全部测试（109 个）
python3 run_checks.py /path/to/cavity.rez    # 手动跑检查（side-car 默认同名 .eng.json）
python3 run_checks.py cavity.rez other.eng.json
python3 run_solves.py pickup cavity.rez --driven d4:L --source d1:L --k 0.5 --b 90.862702 --out cavity.pickup.rez
python3 run_solves.py waist-size cavity.rez --variable d1:L --element M1 --target 0.12 --bounds 330:380 --apply
python3 run_solves.py waist-position cavity.rez --variable d1:L --element M4 --target-ref M4:0 --bounds 270:380
python3 demo_solves.py                        # 用户真实腔体的端到端演示（输出到 /tmp）
python3 run_power.py --rez /path/to/cavity.rez --toc-scan   # 功率扫描（JSON 输出到 stdout）
python3 demo_power.py                         # 用户真实腔体 + 示例参数的功率演示
```

示例数据：`tests/data/example.eng.json` 是给用户真实腔体
（`~/workspace/user/files/upload.rez`）配的**示例** side-car，所有数
值都是编的、仅用于演示分级，绝不是用户的真实激光参数。
`tests/data/example-power.eng.json` 同理：全部泵浦/晶体/热透镜参数
都是文献典型示例值（见“功率求解器”一节），演示用，不是实测。
