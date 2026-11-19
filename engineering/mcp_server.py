#!/usr/bin/env python3
"""MCP server for the reZonator2 engineering package (Phase 4 M4).

Exposes the Phase 1-4 Python engines as coarse-grained MCP tools over
stdio (compatible with Cursor / Claude Desktop and any MCP client).
The server only accepts .rez paths, side-car paths and explicit numeric
parameters -- it never runs arbitrary shell commands.

Tools (7):
    run_foxli, analyze_thermal_fracture, scan_ghosts, redlight_compare,
    export_cad_zmx, run_montecarlo, generate_odr_report

Run:
    python3 engineering/mcp_server.py        # stdio transport

Note: the installed ``mcp`` SDK is 2.x, where FastMCP was renamed to
``MCPServer`` (``from mcp.server.mcpserver import MCPServer``); the
usage pattern is unchanged.  Requires the ``mcp`` package
(``pip install --user mcp``); the other dependencies are the same as
the rest of the engineering package (numpy, scipy, ezdxf, jinja2,
matplotlib).
"""

import functools
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402

from rezeng import eng_path, load_eng, load_rez, validate_eng  # noqa: E402


def _anticipated(fn):
    """Turn expected engine errors into the SDK's ToolError.

    The MCP SDK only forwards the message of an anticipated failure
    (ToolError) to the client; any other exception is treated as a
    crash and the client sees just "Error executing tool <name>".
    Missing files, bad side-cars and infeasible solves are anticipated,
    so they are reported with their detail.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except (ValueError, FileNotFoundError, OSError) as exc:
            raise ToolError(str(exc)) from exc
    return wrapper

server = MCPServer(
    "rezonator-engineering",
    instructions=(
        "Engineering analysis tools for reZonator2 laser cavities. "
        "Every tool takes a .rez cavity file and an optional side-car "
        "engineering file (<file>.rez.eng.json by default). All "
        "engineering parameters come from the side-car; demo side-cars "
        "contain EXAMPLE values, not the user's real laser parameters."))


def _load(rez_path, eng_file=None):
    """Load .rez + side-car; raise ValueError with a clear message."""
    if not os.path.exists(rez_path):
        raise ValueError("no such .rez file: %s" % rez_path)
    eng_file = eng_file or eng_path(rez_path)
    eng = load_eng(eng_file) if os.path.exists(eng_file) else {}
    problems = validate_eng(eng)
    if problems:
        raise ValueError("side-car problems in %s: %s"
                         % (eng_file, "; ".join(problems)))
    return load_rez(rez_path), eng, eng_file


def _jsonable(value):
    """Round-trip through JSON so numpy scalars become plain types."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


@server.tool()
@_anticipated
def run_foxli(rez_path: str, eng_path: str = "", max_rounds: int = 200,
              thermal_power: float = 0.0, paraxial: bool = False) -> dict:
    """Run the Fox-Li FFT diffraction engine on a cavity.

    Returns convergence, round-trip eigenvalue gamma, diffraction loss
    L_diff, and D4-sigma spot radii / M2 at every element. When
    thermal_power > 0, the crystal OPD is computed from the M2 thermal
    solver at that incident pump power (W) instead of the side-car OPD.
    """
    from rezeng.foxli import foxli_report
    data, eng, _ = _load(rez_path, eng_path or None)
    if thermal_power and thermal_power > 0:
        import copy
        from run_foxli import _thermal_opd
        opd, _rep = _thermal_opd(data, eng, thermal_power, paraxial)
        eng = copy.deepcopy(eng)
        eng.setdefault("foxli", {})["opd"] = opd
    return _jsonable(foxli_report(data, eng, max_rounds=max_rounds))


@server.tool()
@_anticipated
def analyze_thermal_fracture(rez_path: str, eng_path: str = "",
                             pump_powers: str = "5") -> dict:
    """Thermal conduction + fracture safety analysis of the crystal.

    pump_powers is a comma-separated list of incident pump powers in W.
    Returns, per power: T_max, end-face bulge, max tensile stress and
    fracture margin (red line: margin >= 0.50), the OPD fit (paraxial
    f_th, spherical aberration) and the Fox-Li phase plate.
    """
    from rezeng.thermal import thermal_report
    import copy
    data, eng, _ = _load(rez_path, eng_path or None)
    powers = [float(v) for v in pump_powers.split(",") if v.strip()]
    if not powers:
        raise ValueError("pump_powers must list at least one power")
    reports = []
    for power in powers:
        eng_i = copy.deepcopy(eng)
        eng_i.setdefault("thermal", {}).setdefault("pump", {})[
            "P_pump_W"] = power
        reports.append(thermal_report(data, eng_i))
    return _jsonable({"rez": rez_path, "reports": reports})


@server.tool()
@_anticipated
def scan_ghosts(rez_path: str, eng_path: str = "",
                wavelength_nm: float = 1064.0) -> dict:
    """Ghost / parasitic-etalon scan of a cavity.

    Returns first-order ghost foci with burn-point LIDT checks and the
    etalon list (FSR, modulation depth, hop warning). Surface residual
    reflectivities come from the side-car; missing values are nodata,
    never invented.
    """
    from rezeng.ghosts import scan_ghosts as _scan
    data, eng, _ = _load(rez_path, eng_path or None)
    return _jsonable(_scan(data, eng, wavelength_nm=wavelength_nm))


@server.tool()
@_anticipated
def redlight_compare(rez_path: str, eng_path: str = "",
                     w0_mm: float = 0.5) -> dict:
    """632.8 nm red-light alignment comparison.

    Cold cavity (thermal lens removed, indices from the Sellmeier
    library) vs the 1064 nm working cavity: per-element spot-size and
    axis-offset table. Falls back to external HeNe single-pass tracing
    when the cold cavity is unstable.
    """
    from rezeng.redlight import redlight_report
    data, eng, _ = _load(rez_path, eng_path or None)
    return _jsonable(redlight_report(data, eng, w0_mm=w0_mm))


@server.tool()
@_anticipated
def export_cad_zmx(rez_path: str, eng_path: str = "",
                   out_dir: str = "", write_zmx: bool = True,
                   write_dxf: bool = True, coating: bool = True) -> dict:
    """Export the coating table, .zmx and .dxf for a cavity.

    Files are written to out_dir (default: next to the .rez file).
    Returns the written paths plus the structural validation results.
    The .zmx is NOT verified in OpticStudio (no licence here).
    """
    from rezeng.export import coating_table, to_dxf, to_zmx
    data, eng, _ = _load(rez_path, eng_path or None)
    out_dir = out_dir or os.path.dirname(os.path.abspath(rez_path))
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(rez_path))[0]
    result = {"out_dir": out_dir, "files": {}}
    if coating:
        rep = coating_table(data, eng)
        path = os.path.join(out_dir, base + ".coating.txt")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(rep.get("text", ""))
        result["files"]["coating_txt"] = path
        result["coating_rows"] = len(rep.get("rows") or [])
        result["coating_warnings"] = rep.get("warnings") or []
    if write_zmx:
        text, validation = to_zmx(data, eng)
        path = os.path.join(out_dir, base + ".zmx")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        result["files"]["zmx"] = path
        result["zmx_validation"] = validation
    if write_dxf:
        text, validation = to_dxf(data, eng)
        path = os.path.join(out_dir, base + ".dxf")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        result["files"]["dxf"] = path
        result["dxf_validation"] = validation
    return _jsonable(result)


@server.tool()
@_anticipated
def run_montecarlo(rez_path: str, eng_path: str = "", n: int = 1000,
                   seed: int = 0, watch: str = "M1,M4") -> dict:
    """Monte Carlo tolerance simulation (Phase 3).

    Returns the instability probability with Wilson 95% CI, watched
    spot medians + CIs, output-power percentiles and the sensitivity
    ranking (Spearman + PRCC). Tolerances come from the side-car.
    """
    from rezeng.montecarlo import run_montecarlo as _mc
    data, eng, _ = _load(rez_path, eng_path or None)
    tolerances = eng.get("tolerances")
    if not tolerances:
        raise ValueError("no tolerances section in the side-car")
    watch_tuple = tuple(w.strip() for w in watch.split(",") if w.strip())
    return _jsonable(_mc(data, tolerances, n=n, seed=seed,
                         watch=watch_tuple, eng=eng))


@server.tool()
@_anticipated
def generate_odr_report(rez_path: str, eng_path: str = "",
                        out_html: str = "", include_foxli: bool = False,
                        mc_n: int = 1000,
                        pump_powers: str = "2,5,10") -> dict:
    """Generate the Optical Design Review (ODR) HTML report.

    One call assembles beam envelope, stability zones, Monte Carlo
    yield, thermal + fracture, Fox-Li (optional), ghost scan, red-light
    comparison, coating BOM and CAD/Zemax export checks. Returns the
    section summary and the written HTML path (the HTML itself is not
    returned -- read the file).
    """
    from rezeng.odr import build_odr_report
    data, eng, _ = _load(rez_path, eng_path or None)
    out = out_html or os.path.splitext(rez_path)[0] + ".odr.html"
    powers = tuple(float(v) for v in pump_powers.split(",") if v.strip())
    report = build_odr_report(rez_path, eng=eng,
                              include_foxli=include_foxli, mc_n=mc_n,
                              pump_powers=powers, example_params=True,
                              out_html=out)
    return _jsonable({k: v for k, v in report.items() if k != "html"})


if __name__ == "__main__":
    server.run()
