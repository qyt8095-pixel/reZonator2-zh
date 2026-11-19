"""Optical Design Review (ODR) report builder (Phase 4 M4).

One call assembles the sections that Phases 1-4 built as separate
tools -- beam envelope, stability zones, Monte Carlo yield, thermal
conduction + fracture, Fox-Li diffraction, ghost/etalon scan, red-light
comparison, coating BOM, .zmx/.dxf export checks -- into a single
self-contained HTML report (Jinja2 template + Matplotlib charts embedded
as base64 PNGs, no external files, printable to PDF from the browser).

Every section is computed inside a ``try/except``: a section that cannot
run (missing side-car data, an unstable cavity, a solver failure) is
reported with status ``skipped``/``error`` and its reason, and never
kills the whole report.  The report header states explicitly whether
the input parameters are EXAMPLE values (the usual case until the user
supplies real laser/crystal/pump/tolerance data) or real ones, and each
section records its data source.

The .rez file is never modified; all engineering data comes from the
side-car (default ``<file>.rez.eng.json``).
"""

import base64
import copy
import datetime
import html
import io
import json
import math
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from jinja2 import Template  # noqa: E402

from . import eng_path, load_eng, load_rez, validate_eng  # noqa: E402
from .cli import run_headless_file  # noqa: E402
from .export import coating_table, to_dxf, to_zmx  # noqa: E402
from .foxli import foxli_report  # noqa: E402
from .ghosts import scan_ghosts  # noqa: E402
from .montecarlo import run_montecarlo  # noqa: E402
from .redlight import redlight_report  # noqa: E402
from .thermal import thermal_report  # noqa: E402
from .zones import scan_zones  # noqa: E402

__all__ = ["build_odr_report", "ODR_TEMPLATE", "ODR_VERSION"]

ODR_VERSION = 1


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def _esc(value):
    """HTML-escape a cell value; ``None`` renders as an em dash."""
    if value is None:
        return "&ndash;"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "&ndash;"
        return "%.4g" % value
    return html.escape(str(value))


def _table(headers, rows):
    """Render a list of rows as a simple HTML table."""
    out = ["<table><thead><tr>"]
    out.extend("<th>%s</th>" % html.escape(str(h)) for h in headers)
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        out.extend("<td>%s</td>" % _esc(c) for c in row)
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _fig_uri(fig):
    """Render a Matplotlib figure to a base64 data-URI PNG and close it."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return "data:image/png;base64," + base64.b64encode(
        buf.getvalue()).decode("ascii")


def _section(sec_id, title, status, note, body_html="", chart_uri=None,
             source=""):
    return {"id": sec_id, "title": title, "status": status, "note": note,
            "body_html": body_html, "chart_uri": chart_uri,
            "source": source}


def _fmt(x, digits=4):
    if x is None:
        return None
    try:
        return round(float(x), digits)
    except (TypeError, ValueError):
        return x


# --------------------------------------------------------------------------
# charts
# --------------------------------------------------------------------------

def _chart_envelope(beam):
    """Spot size at each element exit (CLI Gaussian beam)."""
    labels = [b.get("label", "?") for b in beam]
    w_t = [b.get("w_T_mm") for b in beam]
    w_s = [b.get("w_S_mm") for b in beam]
    if not labels or all(v is None for v in w_t + w_s):
        return None
    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    xs = list(range(len(labels)))
    if any(v is not None for v in w_t):
        ax.plot(xs, [v if v is not None else float("nan") for v in w_t],
                "o-", label="w_T")
    if any(v is not None for v in w_s):
        ax.plot(xs, [v if v is not None else float("nan") for v in w_s],
                "s--", label="w_S")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels, rotation=30, ha="right")
    ax.set_ylabel("spot radius (mm)")
    ax.set_title("Beam envelope (Gaussian model, element exits)")
    ax.grid(True, alpha=0.3)
    ax.legend()
    return _fig_uri(fig)


def _chart_zones(traj, working):
    """g_T / g_S vs D_th with the |g| = 1 stability lines."""
    d = [p.get("D_th") for p in traj]
    g_t = [p.get("g_T") for p in traj]
    g_s = [p.get("g_S") for p in traj]
    if not d:
        return None
    fig, ax = plt.subplots(figsize=(8.5, 3.6))
    ax.plot(d, g_t, label="g_T")
    ax.plot(d, g_s, label="g_S")
    ax.axhline(1.0, color="r", lw=0.8, ls="--")
    ax.axhline(-1.0, color="r", lw=0.8, ls="--")
    ax.axhspan(-1.0, 1.0, color="green", alpha=0.06)
    if working and working.get("D_th") is not None:
        ax.plot([working["D_th"]], [working.get("g_T")], "ko",
                label="working point")
    ax.set_xlabel("D_th = 1/f_th (1/m)")
    ax.set_ylabel("g")
    ax.set_title("Stability trajectory vs thermal-lens dioptric power")
    ax.grid(True, alpha=0.3)
    ax.legend()
    return _fig_uri(fig)


def _chart_mc(mc):
    """Stable/unstable counts and watched spot medians with 95% CI."""
    n_stable = mc.get("n_stable", 0)
    n_unstable = mc.get("n_unstable", 0)
    watch = mc.get("watch") or {}
    fig, axes = plt.subplots(1, 2, figsize=(8.5, 3.4))
    axes[0].bar(["stable", "unstable"], [n_stable, n_unstable],
                color=["#2ca02c", "#d62728"])
    axes[0].set_ylabel("samples")
    axes[0].set_title("Stability yield (N=%d)" % mc.get("n_completed", 0))
    labels, meds, los, his = [], [], [], []
    for label, entry in watch.items():
        for plane in ("w_T_mm", "w_S_mm"):
            stat = entry.get(plane) or {}
            if stat.get("median") is None:
                continue
            labels.append("%s %s" % (label, plane))
            meds.append(stat["median"])
            ci = stat.get("ci95") or [None, None]
            los.append(stat["median"] - ci[0] if ci[0] is not None else 0)
            his.append(ci[1] - stat["median"] if ci[1] is not None else 0)
    if labels:
        axes[1].errorbar(range(len(labels)), meds,
                         yerr=[los, his], fmt="o", capsize=4)
        axes[1].set_xticks(range(len(labels)))
        axes[1].set_xticklabels(labels, rotation=30, ha="right")
        axes[1].set_ylabel("spot radius (mm)")
        axes[1].set_title("Watched spots: median + 95% CI (stable only)")
    else:
        axes[1].text(0.5, 0.5, "no watch data", ha="center")
    fig.tight_layout()
    return _fig_uri(fig)


def _chart_thermal(rows):
    """Fracture margin vs pump power, with the 50% red line."""
    powers = [r["P_pump_W"] for r in rows]
    margins = [r.get("margin_c") for r in rows]
    if not powers or all(m is None for m in margins):
        return None
    fig, ax = plt.subplots(figsize=(8.5, 3.4))
    xs = list(range(len(powers)))
    vals = [m if m is not None else float("nan") for m in margins]
    colors = ["#2ca02c" if (m is not None and m >= 0.5) else "#d62728"
              for m in margins]
    ax.bar(xs, vals, color=colors)
    ax.axhline(0.5, color="r", lw=1.0, ls="--", label="red line 50%")
    ax.set_xticks(xs)
    ax.set_xticklabels(["%.0f W" % p for p in powers])
    ax.set_ylabel("fracture margin 1 - sigma_max/sigma_fracture")
    ax.set_title("Thermal fracture margin vs pump power")
    ax.set_ylim(0, 1.05)
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend()
    return _fig_uri(fig)


# --------------------------------------------------------------------------
# section builders (each returns a section dict; never raises)
# --------------------------------------------------------------------------

def _sec_cavity(data, result):
    beam = result.get("beam") or []
    rows = [[b.get("label"), _fmt(b.get("w_T_mm")), _fmt(b.get("w_S_mm")),
             _fmt(b.get("R_T_mm")), _fmt(b.get("R_S_mm"))]
            for b in beam]
    body = _table(["element", "w_T (mm)", "w_S (mm)", "R_T (mm)",
                   "R_S (mm)"], rows)
    note = ("g_T=%s, g_S=%s, stable=%s, total length %s mm"
            % (_fmt(result.get("g_T")), _fmt(result.get("g_S")),
               result.get("stable"), _fmt(result.get("total_length_mm"))))
    return _section("cavity", "1. Cavity and Gaussian beam", "ok", note,
                    body, _chart_envelope(beam),
                    "C++ headless CLI (--headless), Gaussian model")


def _sec_zones(data):
    try:
        from .rez import param_value_si
        f_si = param_value_si(data, "TL1", "F")
        working_f = f_si * 1e3 if f_si else None
    except Exception:
        working_f = None
    res = scan_zones(data, working_f_mm=working_f)
    common = res.get("zones_common") or []
    rows = [[z.get("label"), _fmt(z.get("D_min")), _fmt(z.get("D_max")),
             _fmt(z.get("f_min_mm")), _fmt(z.get("f_max_mm"))]
            for z in common]
    body = _table(["zone", "D_min (1/m)", "D_max (1/m)",
                   "f_min (mm)", "f_max (mm)"], rows)
    note = ("%d common zone(s); working point F=%s mm"
            % (len(common), _fmt(working_f)))
    return _section("zones", "2. Stability zones and trajectory", "ok",
                    note, body,
                    _chart_zones(res.get("trajectory") or [],
                                 res.get("working_point")),
                    "Phase 3 zones.py: 1D D_th scan + Brent boundaries")


def _sec_montecarlo(data, eng, mc_n):
    tolerances = (eng or {}).get("tolerances")
    if not tolerances:
        return _section("montecarlo", "3. Monte Carlo tolerance yield",
                        "skipped",
                        "no tolerances section in the side-car",
                        "", None, "Phase 3 montecarlo.py")
    mc = run_montecarlo(data, tolerances, n=mc_n, seed=0,
                        watch=("M1", "M4"), eng=eng)
    rows = []
    for label, entry in (mc.get("watch") or {}).items():
        for plane in ("w_T_mm", "w_S_mm"):
            stat = entry.get(plane) or {}
            ci = stat.get("ci95") or [None, None]
            rows.append([label, plane, _fmt(stat.get("median")),
                         _fmt(ci[0]), _fmt(ci[1]), stat.get("n")])
    body = _table(["element", "plane", "median (mm)", "CI95 lo",
                   "CI95 hi", "n"], rows)
    power = mc.get("power") or {}
    p_note = ""
    if power.get("status") == "ok":
        p_out = power.get("P_out_W") or {}
        p_note = ("; P_out median %s W, 95%% CI [%s, %s] W"
                  % (_fmt(p_out.get("median")),
                     _fmt((p_out.get("ci95") or [None, None])[0]),
                     _fmt((p_out.get("ci95") or [None, None])[1])))
    note = ("N=%d, unstable %d (%.1f%%), Wilson 95%% CI [%.1f%%, %.1f%%]%s"
            % (mc.get("n_completed", 0), mc.get("n_unstable", 0),
               100.0 * mc.get("p_unstable", 0),
               100.0 * (mc.get("wilson_95") or [0, 0])[0],
               100.0 * (mc.get("wilson_95") or [0, 0])[1], p_note))
    return _section("montecarlo", "3. Monte Carlo tolerance yield", "ok",
                    note, body, _chart_mc(mc),
                    "Phase 3 montecarlo.py: N=%d, seed 0" % mc_n)


def _sec_thermal(data, eng, pump_powers):
    thermal = (eng or {}).get("thermal")
    if not thermal:
        return _section("thermal", "4. Thermal conduction and fracture",
                        "skipped", "no thermal section in the side-car",
                        "", None, "Phase 4 M2 thermal.py / fracture.py")
    rows, chart_rows = [], []
    for power in pump_powers:
        eng_i = copy.deepcopy(eng)
        eng_i.setdefault("thermal", {}).setdefault("pump", {})[
            "P_pump_W"] = float(power)
        rep = thermal_report(data, eng_i)
        frac = rep.get("fracture") or {}
        prim = (frac.get("primary") or {})
        margin_c = prim.get("margin_c")
        rows.append([power, _fmt(rep.get("T_max_C"), 1),
                     _fmt(rep.get("bulge_max_um"), 3),
                     _fmt(prim.get("sigma_c_MPa"), 2),
                     _fmt(margin_c, 3),
                     _fmt(rep.get("f_paraxial_mm"), 1),
                     _fmt(rep.get("f_analytic_gaussian_mm"), 1),
                     _fmt(rep.get("closed_loop_dev"), 4)])
        chart_rows.append({"P_pump_W": power, "margin_c": margin_c})
    body = _table(["P_pump (W)", "T_max (C)", "bulge (um)",
                   "sigma_c (MPa)", "margin_c", "f_paraxial (mm)",
                   "f_analytic (mm)", "closed-loop dev"], rows)
    note = ("margins use the conservative (c-axis) stress bound; "
            "red line margin >= 0.50")
    return _section("thermal", "4. Thermal conduction and fracture",
                    "ok", note, body, _chart_thermal(chart_rows),
                    "Phase 4 M2: spsolve FD + plane-strain stress")


def _sec_foxli(data, eng, include_foxli):
    if not include_foxli:
        return _section("foxli", "5. Fox-Li diffraction (M2)", "skipped",
                        "not requested for this report "
                        "(pass include_foxli=True)",
                        "", None, "Phase 4 M3 foxli.py")
    if not (eng or {}).get("foxli"):
        return _section("foxli", "5. Fox-Li diffraction (M2)", "skipped",
                        "no foxli section in the side-car",
                        "", None, "Phase 4 M3 foxli.py")
    rep = foxli_report(data, eng)
    beam = rep.get("beam") or []
    rows = [[b.get("label"), _fmt(b.get("w_T_mm")),
             _fmt(b.get("M2_T")), _fmt(b.get("w_S_mm")),
             _fmt(b.get("M2_S"))] for b in beam]
    body = _table(["element", "w_T (mm)", "M2_T", "w_S (mm)", "M2_S"],
                  rows)
    note = ("converged=%s in %s rounds, L_diff=%s"
            % (rep.get("converged"), rep.get("rounds"),
               _fmt(rep.get("L_diff"))))
    return _section("foxli", "5. Fox-Li diffraction (M2)", "ok", note,
                    body, None,
                    "Phase 4 M3: BL-ASM + two-step Fresnel")


def _sec_ghosts(data, eng):
    rep = scan_ghosts(data, eng)
    summary = rep.get("summary") or {}
    etalons = rep.get("etalons") or []
    rows = [[e.get("surface_a"), e.get("surface_b"),
             _fmt(e.get("FSR_GHz"), 4), _fmt(e.get("modulation"), 3),
             e.get("status")] for e in etalons]
    body = _table(["surface A", "surface B", "FSR (GHz)",
                   "modulation", "status"], rows)
    note = ("ghosts ok %s / warn %s / fail %s / nodata %s; "
            "etalons %d" % (summary.get("ok"), summary.get("warn"),
                            summary.get("fail"), summary.get("nodata"),
                            len(etalons)))
    return _section("ghosts", "6. Ghost and etalon scan", "ok", note,
                    body, None,
                    "Phase 4 M1 ghosts.py (3x3 off-axis ray trace)")


def _sec_redlight(data, eng):
    rep = redlight_report(data, eng)
    table = rep.get("table") or []
    rows = [[r.get("element"), _fmt(r.get("w_1064_T_mm")),
             _fmt(r.get("w_633_T_mm")), _fmt(r.get("dw_T_pct"), 1),
             _fmt(r.get("dx_T_mm"), 4)] for r in table]
    body = _table(["element", "w_1064 T (mm)", "w_633 T (mm)",
                   "dw_T (%)", "dx_T (mm)"], rows)
    note = ("path=%s (cold cavity g_T=%s, g_S=%s)"
            % (rep.get("path"), _fmt((rep.get("cold") or {}).get("g_T")),
               _fmt((rep.get("cold") or {}).get("g_S"))))
    return _section("redlight", "7. Red-light (632.8 nm) comparison",
                    "ok", note, body, None,
                    "Phase 4 M1 redlight.py (Sellmeier + HeNe fallback)")


def _sec_coating(data, eng):
    rep = coating_table(data, eng)
    rows = [[r.get("element"), r.get("face"), r.get("polarization"),
             _fmt(r.get("AOI_deg"), 2), r.get("spec"),
             _fmt(r.get("fluence_J_per_cm2"), 3), r.get("status")]
            for r in (rep.get("rows") or [])]
    body = _table(["element", "face", "pol.", "AOI (deg)", "spec",
                   "fluence (J/cm2)", "status"], rows)
    note = "%d surfaces; %d warnings" % (len(rows),
                                          len(rep.get("warnings") or []))
    return _section("coating", "8. Coating BOM", "ok", note, body, None,
                    "Phase 4 M1 export.py (AOI = Alpha, T=P / S=S)")


def _sec_exports(data, eng):
    zmx_text, zmx_val = to_zmx(data, eng)
    dxf_text, dxf_val = to_dxf(data, eng)
    zmx_checks = zmx_val.get("checks") or []
    dxf_checks = dxf_val.get("checks") or []
    lines = [
        "ZMX: %d lines, self-check ok=%s (%d/%d checks pass)"
        % (zmx_text.count("\n"), zmx_val.get("ok"),
           sum(1 for c in zmx_checks if c.get("ok")), len(zmx_checks)),
        "DXF: %d lines, writer=%s, validation ok=%s (%d/%d checks pass)"
        % (dxf_text.count("\n"), dxf_val.get("writer"),
           dxf_val.get("ok"),
           sum(1 for c in dxf_checks if c.get("ok")), len(dxf_checks)),
    ]
    body = "<p>" + "<br>".join(html.escape(l) for l in lines) + "</p>"
    note = "ZMx + DXF generated and structurally validated in-memory"
    return _section("exports", "9. CAD / Zemax export checks", "ok", note,
                    body, None,
                    "Phase 4 M1 export.py (NOT verified in OpticStudio)")


# --------------------------------------------------------------------------
# template + builder
# --------------------------------------------------------------------------

ODR_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>光学设计评审报告 (ODR) - {{ title }}</title>
<style>
body { font-family: sans-serif; max-width: 960px; margin: 2em auto;
       padding: 0 1em; color: #222; }
h1 { border-bottom: 3px solid #333; padding-bottom: 0.3em; }
h2 { border-bottom: 1px solid #ccc; padding-bottom: 0.2em; margin-top: 2em; }
.banner { background: #fff3cd; border: 1px solid #e6c200; padding: 0.8em;
          margin: 1em 0; }
.banner.real { background: #d4edda; border-color: #28a745; }
table { border-collapse: collapse; margin: 0.5em 0; width: 100%; }
th, td { border: 1px solid #bbb; padding: 4px 8px; text-align: left;
         font-size: 0.9em; }
th { background: #eee; }
img { max-width: 100%; }
.status-ok { color: #2ca02c; font-weight: bold; }
.status-skipped { color: #888; font-weight: bold; }
.status-error { color: #d62728; font-weight: bold; }
.note { color: #555; font-size: 0.95em; }
.source { color: #777; font-size: 0.85em; }
footer { margin-top: 3em; border-top: 1px solid #ccc; padding-top: 0.5em;
         color: #777; font-size: 0.85em; }
@media print { body { max-width: none; } }
</style></head><body>
<h1>光学设计评审报告 (ODR)</h1>
<p><b>谐振腔：</b>{{ title }} &nbsp; <b>类型：</b>{{ trip_type }} &nbsp;
<b>波长：</b>{{ wavelength_nm }} nm &nbsp; <b>生成时间：</b>{{ generated_at }}</p>
<div class="banner{% if not example_params %} real{% endif %}">
{% if example_params %}
<b>注意：本报告的全部工程输入参数均为示例值（EXAMPLE），不是该激光器的真实参数，结论不可直接作为设计决策依据。</b>
真实参数（泵浦、晶体、镀膜、公差、实测光斑等）补齐后重新生成。
{% else %}
<b>本报告基于用户提供的真实参数生成。</b>
{% endif %}
</div>
<p class="note">完成 {{ n_ok }} / {{ n_sections }} 节；
{% for s in sections %}{{ s.title }}: <span class="status-{{ s.status }}">{{ s.status }}</span>{% if not loop.last %}；{% endif %}{% endfor %}</p>
{% for s in sections %}
<h2>{{ s.title }}</h2>
<p class="note">{{ s.note }}</p>
{% if s.chart_uri %}<p><img src="{{ s.chart_uri }}" alt="{{ s.title }} chart"></p>{% endif %}
{{ s.body_html | safe }}
<p class="source">来源：{{ s.source }}</p>
{% endfor %}
<footer>reZonator2-zh 二次开发工程包（Phase 1-4）ODR v{{ odr_version }}。
.zmx 未在 OpticStudio 中验证；Fox-Li 与热分析的数值结论以各节标注的收敛状态为准。</footer>
</body></html>
"""


def _run_section(fn, *args, **kwargs):
    """Run one section builder; failures become an error section."""
    sec_id = kwargs.pop("sec_id", "unknown")
    title = kwargs.pop("sec_title", sec_id)
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        return _section(sec_id, title, "error", "failed: %s" % (exc,),
                        "", None, "")


def build_odr_report(rez_path, eng=None, eng_file=None,
                     include_foxli=False, mc_n=1000,
                     pump_powers=(2.0, 5.0, 10.0), example_params=True,
                     out_html=None):
    """Build the full ODR report for ``rez_path``.

    ``eng`` may be a loaded side-car dict; otherwise it is loaded from
    ``eng_file`` or the default side-car next to the .rez file.  Returns
    a dict with the section reports and (when ``out_html`` is given) the
    written HTML path.  Never raises for a single failing section.
    """
    data = load_rez(rez_path)
    # Fox-Li needs the file path to run the headless CLI for its
    # initial Gaussian (resolve_foxli reads data["_rez_path"]).
    # The C++ schema reader ignores unknown top-level keys, so this
    # extra key is harmless for the zones / Monte Carlo sections,
    # which pass the same dict as base_schema.
    data["_rez_path"] = rez_path
    if eng is None:
        eng_file = eng_file or eng_path(rez_path)
        eng = load_eng(eng_file) if os.path.exists(eng_file) else {}
    problems = validate_eng(eng)
    result = run_headless_file(rez_path)["results"][0]
    if not result.get("ok"):
        raise ValueError("headless CLI failed on %s: %s"
                         % (rez_path, result.get("error")))

    sections = []
    sections.append(_run_section(_sec_cavity, data, result,
                                 sec_id="cavity",
                                 sec_title="1. Cavity and Gaussian beam"))
    sections.append(_run_section(_sec_zones, data,
                                 sec_id="zones",
                                 sec_title="2. Stability zones"))
    sections.append(_run_section(_sec_montecarlo, data, eng, mc_n,
                                 sec_id="montecarlo",
                                 sec_title="3. Monte Carlo tolerance"))
    sections.append(_run_section(_sec_thermal, data, eng, pump_powers,
                                 sec_id="thermal",
                                 sec_title="4. Thermal and fracture"))
    sections.append(_run_section(_sec_foxli, data, eng, include_foxli,
                                 sec_id="foxli",
                                 sec_title="5. Fox-Li diffraction"))
    sections.append(_run_section(_sec_ghosts, data, eng,
                                 sec_id="ghosts",
                                 sec_title="6. Ghost and etalon scan"))
    sections.append(_run_section(_sec_redlight, data, eng,
                                 sec_id="redlight",
                                 sec_title="7. Red-light comparison"))
    sections.append(_run_section(_sec_coating, data, eng,
                                 sec_id="coating",
                                 sec_title="8. Coating BOM"))
    sections.append(_run_section(_sec_exports, data, eng,
                                 sec_id="exports",
                                 sec_title="9. CAD / Zemax export"))

    n_ok = sum(1 for s in sections if s["status"] == "ok")
    wavelength = None
    try:
        from .rez import param_value_si  # noqa: PLC0415
        lam = param_value_si(data, "__global__", "wavelength")
        wavelength = lam * 1e9 if lam else 1064.0
    except Exception:  # noqa: BLE001
        wavelength = 1064.0

    context = {
        "title": data.get("title") or os.path.basename(rez_path),
        "trip_type": data.get("trip_type") or result.get("trip_type"),
        "wavelength_nm": wavelength,
        "generated_at": datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"),
        "example_params": bool(example_params),
        "sections": sections,
        "n_ok": n_ok,
        "n_sections": len(sections),
        "odr_version": ODR_VERSION,
    }
    html_text = Template(ODR_TEMPLATE).render(**context)
    out = {"version": ODR_VERSION, "rez": rez_path,
           "generated_at": context["generated_at"],
           "example_params": bool(example_params),
           "validation_problems": problems,
           "sections": [{"id": s["id"], "title": s["title"],
                         "status": s["status"], "note": s["note"],
                         "source": s["source"]} for s in sections],
           "n_ok": n_ok, "n_sections": len(sections),
           "out_html": out_html}
    if out_html:
        with open(out_html, "w", encoding="utf-8") as fh:
            fh.write(html_text)
    out["html"] = html_text
    return out
