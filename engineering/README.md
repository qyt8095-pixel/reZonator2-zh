# reZonator 工程层（Phase 1）

Python 层：`.rez` 解析、单位换算、无头 CLI 封装、工程检查与（后续）
Solves。只用标准库。光学计算一律复用原生 C++（`rezonator --headless`），
Python 不重算光学。

## 目录

| 文件 | 内容 |
|---|---|
| `rezeng/rez.py` | `.rez` 读写（原样保留未知键、`schema_version`、各参数 `unit`） |
| `rezeng/units.py` | 单位换算（`.rez` 参数单位别名 ↔ SI） |
| `rezeng/cli.py` | `run_headless` / `run_headless_file`：调 `--headless` 批量求值 |
| `rezeng/eng.py` | side-car `<file>.rez.eng.json` 读写与格式校验 |
| `rezeng/checks.py` | LIDT / 孔径截断 / 面包板检查，`run_checks()` |
| `rezeng/solves.py` | Pickup 与束腰 Solves，`apply_pickup()` / `solve_waist_size()` / `solve_waist_position()` / `apply_solution()` |
| `run_checks.py` | 检查的命令行入口：`python3 run_checks.py <file.rez> [side-car]` |
| `run_solves.py` | Solves 的命令行入口：`python3 run_solves.py pickup|waist-size|waist-position …` |
| `demo_solves.py` | 用户真实腔体的 Pickup + 束腰 Solve 端到端演示（输出到 /tmp） |
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

## 运行与测试

```sh
cd engineering
python3 -m unittest discover -s tests        # 全部测试（71 个）
python3 run_checks.py /path/to/cavity.rez    # 手动跑检查（side-car 默认同名 .eng.json）
python3 run_checks.py cavity.rez other.eng.json
python3 run_solves.py pickup cavity.rez --driven d4:L --source d1:L --k 0.5 --b 90.862702 --out cavity.pickup.rez
python3 run_solves.py waist-size cavity.rez --variable d1:L --element M1 --target 0.12 --bounds 330:380 --apply
python3 run_solves.py waist-position cavity.rez --variable d1:L --element M4 --target-ref M4:0 --bounds 270:380
python3 demo_solves.py                        # 用户真实腔体的端到端演示（输出到 /tmp）
```

示例数据：`tests/data/example.eng.json` 是给用户真实腔体
（`~/workspace/user/files/upload.rez`）配的**示例** side-car，所有数
值都是编的、仅用于演示分级，绝不是用户的真实激光参数。
