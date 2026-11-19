"""Pickup / waist-position Solves (Phase 1 block 3).

Two kinds of solve, both working on a loaded ``.rez`` dict. Optics are
never recomputed here: every evaluation goes through the headless CLI
(``rezeng.cli``) in batch mode, so the numbers are the application's
own.

Pickup
-------
``apply_pickup`` writes a *native* Pickup into the file: a global
parameter for the source, a global parameter for the driven value with
a Lua formula ``k * SRC + b`` (SI units, see ``Formula::calculate``),
and two ``param_links`` copying the globals into the element
parameters. The relation survives a UI save, and editing the source
global in the UI re-derives the driven value. Formula targets must be
global parameters (``SchemaReaderJson::readFormula``), so an
element-to-element Pickup is always routed through globals.

One loading subtlety matters (verified against the real binary):
formulas are *not* recalculated on load -- ``Formula::calculate`` only
runs when a dependency parameter changes. A file written by
``apply_pickup`` stores a consistent driven value, so it loads
correctly; but an external edit of the source global alone leaves the
stored driven value stale until the source is touched in the UI.
``apply_solution`` therefore refuses driven variables, and this module
never writes a bare source value without its driven counterpart.

Waist Solves
------------
``solve_waist_size`` / ``solve_waist_position`` vary one free element
parameter (the *variable*) and drive a waist quantity to a target.
The waist of a beam segment is derived from that segment's element
``(w, R)`` with the Gaussian-beam formula (protocol section 4); the
top-level CLI ``waist`` field is *not* used -- it is only the first
element's segment. Positions are absolute axial coordinates ``s`` in
mm: ``s = 0`` at the first element's plane, increasing along the
element list (the round-trip direction); an element's plane is its
exit plane (its own ``L`` included for ranges). ``total_length_mm``
is the full loop length for SW/RR.

Solver: a batch scan over the bounds (one CLI call), then Brent
(``scipy.optimize.brentq``) on a sign-changing bracket, or bounded
minimisation of ``|residual|`` when there is no sign change. Unstable
points (``stable: false``) and rejected mutations are infeasible, never
solutions. A solve that cannot reach its tolerance reports
``converged: false`` with the best point found -- it never invents a
solution.
"""

import math
import re

from scipy.optimize import brentq, minimize_scalar

from .cli import HeadlessError, run_headless
from .rez import (check_overridable, element_index, elements, param_obj,
                  param_unit, param_value_si, set_param_value)
from .units import dimension, from_si, to_si

#: CLI guards, copied from ``OptimizerFunction::validate`` (protocol §5):
#: a length parameter below this (SI) is rejected, R/F must not be 0.
MIN_LENGTH_SI = 1e-6

#: Scan points per batch evaluation of the search interval.
DEFAULT_SCAN_POINTS = 17

#: Default residual tolerance, relative to the target magnitude.
DEFAULT_FTOL_REL = 1e-9

#: Default bracketing tolerance, in the variable's SI units.
DEFAULT_XTOL_SI = 1e-12

#: Aliases of curvature / focal-length parameters (must not cross 0).
_CURVATURE_ALIASES = ("R", "R1", "R2", "F", "Fs", "Ft")


class SolveError(ValueError):
    """Raised when a solve cannot be set up or evaluated."""


class PickupError(ValueError):
    """Raised when a Pickup cannot be applied (conflict, bad values)."""


# --- Pure waist math -----------------------------------------------------

def wavelength_nm(data):
    """The schema wavelength in nm (from ``builtin_params.lambda``)."""
    builtin = data.get("builtin_params") or {}
    lam = builtin.get("lambda") if isinstance(builtin, dict) else None
    if not isinstance(lam, dict):
        raise SolveError("no builtin_params.lambda in the .rez file")
    try:
        return to_si(lam.get("value"), lam.get("unit")) * 1e9
    except (TypeError, ValueError) as e:
        raise SolveError("unreadable builtin_params.lambda: %s" % (e,))


def waist_from_wr(w_mm, R_mm, lambda_nm):
    """Waist of the beam at a plane from its ``(w, R)`` there.

    ``w_mm`` / ``R_mm`` are the beam radius and wavefront radius at the
    plane (mm); ``R_mm`` is ``None`` for a flat wavefront. Returns
    ``(w0_mm, z_mm)`` with ``z`` the signed distance from the plane to
    the waist: ``z > 0`` means the waist is *upstream* of the plane
    (protocol section 4: ``1/q = 1/R - i*lam/(pi*w^2)``, ``z = Re(q)``,
    ``w0 = sqrt(lam*z_R/pi)``).
    """
    if w_mm is None or not math.isfinite(w_mm) or w_mm <= 0:
        raise ValueError("beam radius must be a positive number: %r"
                         % (w_mm,))
    lam_m = lambda_nm * 1e-9
    w_m = w_mm * 1e-3
    if R_mm is None:
        return (float(w_mm), 0.0)
    if not math.isfinite(R_mm) or R_mm == 0:
        raise ValueError("wavefront radius must be finite and non-zero: "
                         "%r" % (R_mm,))
    inv_q = complex(1.0 / (R_mm * 1e-3), -lam_m / (math.pi * w_m * w_m))
    q = 1.0 / inv_q
    if q.imag <= 0:
        raise ValueError("non-positive Rayleigh range from (w, R) = "
                         "(%r, %r)" % (w_mm, R_mm))
    return (math.sqrt(lam_m * q.imag / math.pi) * 1e3, q.real * 1e3)


def element_plane_position_mm(data, label, overrides=None):
    """Axial position (mm) of an element's plane.

    ``s = 0`` at the first element's plane; ``s`` increases along the
    element list. An element's plane is its *exit* plane: for an element
    with an ``L`` parameter its own length is included, because the CLI
    reports its ``(w, R)`` at the exit. ``overrides`` is
    ``{label: {alias: value_si}}`` applied on top of the stored values
    (a solve variable upstream changes the positions downstream).
    Disabled elements contribute nothing, matching the CLI's
    ``total_length_mm`` (active elements only).
    """
    seen = False
    s = 0.0
    for elem in elements(data):
        if not isinstance(elem, dict):
            continue
        elabel = elem.get("label")
        if elabel == label:
            seen = True
        if elem.get("is_disabled"):
            if elabel == label:
                raise SolveError("element %r is disabled" % (label,))
            continue
        params = elem.get("params")
        length_si = None
        if isinstance(params, dict) and isinstance(params.get("L"), dict):
            if (overrides and elabel in overrides
                    and "L" in overrides[elabel]):
                length_si = overrides[elabel]["L"]
            else:
                length_si = to_si(params["L"].get("value"),
                                  params["L"].get("unit"))
        if elabel == label:
            if length_si is not None:
                s += length_si * 1e3
            return s
        if length_si is not None:
            s += length_si * 1e3
    if not seen:
        raise SolveError("unknown element %r" % (label,))
    raise SolveError("element %r has no computable plane position"
                     % (label,))


def total_length_mm(data, overrides=None):
    """Sum of the ``L`` parameters of all active elements (mm)."""
    total = 0.0
    for elem in elements(data):
        if not isinstance(elem, dict) or elem.get("is_disabled"):
            continue
        params = elem.get("params")
        if not isinstance(params, dict):
            continue
        param = params.get("L")
        if not isinstance(param, dict):
            continue
        elabel = elem.get("label")
        if overrides and elabel in overrides and "L" in overrides[elabel]:
            total += overrides[elabel]["L"] * 1e3
        else:
            total += to_si(param.get("value"), param.get("unit")) * 1e3
    return total


# --- Pickup --------------------------------------------------------------

#: Dimension -> custom-parameter ``dim`` alias (see ``Z::Dims``).
_DIM_ALIAS = {"length": "linear", "angle": "angular", "none": "none"}

_PICKUP_CODE_RE = re.compile(
    r"^\s*(?P<k>[-+0-9.eE]+)\s*\*\s*(?P<src>[a-zA-Z_][a-zA-Z_0-9]*)\s*"
    r"\+\s*(?P<b>[-+0-9.eE]+)\s*$")


def _link_source_global(data, label, alias):
    """Name of the global parameter linked into ``(label, alias)``.

    Returns ``None`` when the parameter is not link-driven.
    """
    idx = element_index(data, label)
    if idx is None:
        return None
    for link in data.get("param_links") or []:
        if not isinstance(link, dict):
            continue
        if (link.get("target_elem") == idx
                and link.get("target_param") == alias):
            return link.get("source_param")
    return None


def _formula_for(data, target_name):
    """The ``formulas`` entry targeting a global parameter, or ``None``."""
    for formula in data.get("formulas") or []:
        if isinstance(formula, dict) \
                and formula.get("target_param") == target_name:
            return formula
    return None


def _fresh_global_name(data, base):
    """``base`` made unique among ``custom_params`` (``_2``, ``_3``, ...)."""
    customs = data.setdefault("custom_params", {})
    if not isinstance(customs, dict):
        raise PickupError("custom_params is not an object")
    name = base
    n = 2
    while name in customs:
        name = "%s_%d" % (base, n)
        n += 1
    return name


def _global_name_for(data, label, alias):
    """Deterministic ASCII global name for an element parameter.

    Labels may be Chinese, and formula variable names must match
    ``[a-zA-Z_][a-zA-Z_0-9]*``, so the name is built from the element
    index: ``PK_E<index>_<alias>``.
    """
    idx = element_index(data, label)
    safe_alias = re.sub(r"[^a-zA-Z0-9_]", "_", alias)
    return "PK_E%d_%s" % (idx, safe_alias)


def _make_global_param(data, name, value_si, unit, dim_alias, descr):
    """Create a ``custom_params`` entry (value in its own unit)."""
    customs = data.setdefault("custom_params", {})
    customs[name] = {
        "value": from_si(value_si, unit),
        "unit": unit,
        "dim": dim_alias,
        "descr": descr,
        "expr": "",
        "error": "",
    }
    return customs[name]


def _check_pickup_value(dim, value_si, what):
    """Apply the CLI guards to a computed Pickup value."""
    if not math.isfinite(value_si):
        raise PickupError("%s is not finite: %r" % (what, value_si))
    if dim == "length" and value_si < MIN_LENGTH_SI:
        raise PickupError(
            "%s %.6g m is below the CLI guard for lengths (>= %.0e m)"
            % (what, value_si, MIN_LENGTH_SI))
    if dim == "length" and value_si == 0.0:
        raise PickupError("%s must not be 0" % (what,))


def find_pickup(data, driven):
    """Describe the Pickup driving ``driven`` (``(label, alias)``).

    Returns ``None`` when the parameter is not pickup-driven, otherwise
    ``{"source": (label, alias) or None, "source_global": str,
    "driven_global": str, "formula": code}``. ``source`` is ``None``
    when the source global is not linked to any element (a free global
    used as the source).
    """
    label, alias = driven
    driven_global = _link_source_global(data, label, alias)
    if driven_global is None:
        return None
    formula = _formula_for(data, driven_global)
    if formula is None:
        return None
    src_name = None
    for dep in formula.get("param_deps") or []:
        src_name = dep
        break
    source = None
    if src_name is not None:
        for link in data.get("param_links") or []:
            if isinstance(link, dict) \
                    and link.get("source_param") == src_name:
                idx = link.get("target_elem")
                elems = elements(data)
                if isinstance(idx, int) and 0 <= idx < len(elems):
                    source = (elems[idx].get("label"),
                              link.get("target_param"))
                break
    return {"source": source, "source_global": src_name,
            "driven_global": driven_global,
            "formula": formula.get("code")}


def apply_pickup(data, driven, source, k, b, b_unit=None):
    """Write a native Pickup into a loaded .rez dict (in place).

    ``driven`` / ``source`` are ``(label, alias)`` pairs; the relation
    is ``driven = k * source + b`` with ``k`` dimensionless and ``b``
    given in the driven parameter's unit (``b_unit`` overrides).
    Both parameters must have the same dimension (length/angle/none).
    The formula is evaluated by the application in SI (Lua, see
    ``Formula::calculate``), so the stored code is
    ``"<k> * <SRC> + <b_si>"``.

    The source element parameter becomes link-driven by a new (or
    reused) global parameter; the driven element parameter becomes
    link-driven by a new global parameter carrying the formula. Returns
    an info dict ``{"source_global", "driven_global", "formula",
    "k", "b_si", "source_value_si", "driven_value_si",
    "created_globals", "links_added", "warnings"}``.
    """
    d_label, d_alias = driven
    s_label, s_alias = source
    if driven == source:
        raise PickupError("driven and source are the same parameter %s.%s"
                          % (d_label, d_alias))
    if param_obj(data, d_label, d_alias) is None:
        raise PickupError("unknown driven parameter %s.%s"
                          % (d_label, d_alias))
    if param_obj(data, s_label, s_alias) is None:
        raise PickupError("unknown source parameter %s.%s"
                          % (s_label, s_alias))
    conflict = check_overridable(data, d_label, d_alias)
    if conflict is not None:
        raise PickupError("driven parameter %s.%s is not free: %s"
                          % (d_label, d_alias, conflict))
    try:
        k = float(k)
        b = float(b)
    except (TypeError, ValueError):
        raise PickupError("k and b must be numbers: %r, %r" % (k, b))
    if not math.isfinite(k) or not math.isfinite(b):
        raise PickupError("k and b must be finite: %r, %r" % (k, b))

    s_unit = param_unit(data, s_label, s_alias)
    d_unit = param_unit(data, d_label, d_alias)
    try:
        s_dim = dimension(s_unit)
        d_dim = dimension(d_unit)
    except ValueError as e:
        raise PickupError("unknown unit: %s" % (e,))
    if s_dim != d_dim:
        raise PickupError(
            "dimension mismatch: source %s.%s is %s (%s), driven %s.%s "
            "is %s (%s); a Pickup needs the same dimension"
            % (s_label, s_alias, s_dim, s_unit, d_label, d_alias, d_dim,
               d_unit))
    if s_dim not in _DIM_ALIAS:
        raise PickupError("Pickup is not supported for dimension %r"
                          % (s_dim,))
    dim_alias = _DIM_ALIAS[s_dim]

    if b_unit is None:
        b_unit = d_unit
    try:
        b_si = to_si(b, b_unit)
    except ValueError as e:
        raise PickupError("unknown b unit %r: %s" % (b_unit, e))
    src_si = param_value_si(data, s_label, s_alias)
    if src_si is None or not math.isfinite(src_si):
        raise PickupError("source parameter %s.%s has no finite value"
                          % (s_label, s_alias))
    driven_si = k * src_si + b_si
    _check_pickup_value(d_dim, driven_si, "driven value")

    warnings = []
    created_globals = []
    links_added = []

    # Source global: reuse the global already linked into the source
    # parameter (chains work: a pickup-driven value can be a source).
    src_global = _link_source_global(data, s_label, s_alias)
    if src_global is not None:
        src_param = (data.get("custom_params") or {}).get(src_global)
        if isinstance(src_param, dict):
            try:
                global_si = to_si(src_param.get("value"),
                                  src_param.get("unit"))
            except (TypeError, ValueError):
                global_si = None
            if global_si is not None and abs(global_si - src_si) > \
                    1e-12 * max(1.0, abs(src_si)):
                warnings.append(
                    "source global %r holds %.9g (SI) but the element "
                    "parameter holds %.9g; on load the link overwrites "
                    "the element value" % (src_global, global_si, src_si))
    else:
        src_global = _fresh_global_name(
            data, _global_name_for(data, s_label, s_alias))
        _make_global_param(
            data, src_global, src_si, s_unit, dim_alias,
            "Pickup source for %s.%s" % (s_label, s_alias))
        created_globals.append(src_global)
        data.setdefault("param_links", []).append({
            "source_param": src_global,
            "target_elem": element_index(data, s_label),
            "target_param": s_alias,
        })
        links_added.append({"source_param": src_global,
                            "target_elem": element_index(data, s_label),
                            "target_param": s_alias})

    driven_global = _fresh_global_name(
        data, _global_name_for(data, d_label, d_alias))
    _make_global_param(
        data, driven_global, driven_si, d_unit, dim_alias,
        "Pickup driven by %s.%s (k=%r, b=%r %s)"
        % (s_label, s_alias, k, b, b_unit))
    created_globals.append(driven_global)
    code = "%r * %s + %r" % (k, src_global, b_si)
    data.setdefault("formulas", []).append({
        "code": code,
        "param_deps": [src_global],
        "target_param": driven_global,
    })
    data.setdefault("param_links", []).append({
        "source_param": driven_global,
        "target_elem": element_index(data, d_label),
        "target_param": d_alias,
    })
    links_added.append({"source_param": driven_global,
                        "target_elem": element_index(data, d_label),
                        "target_param": d_alias})

    return {"source_global": src_global, "driven_global": driven_global,
            "formula": code, "k": k, "b_si": b_si,
            "source_value_si": src_si, "driven_value_si": driven_si,
            "created_globals": created_globals,
            "links_added": links_added, "warnings": warnings}


def verify_pickup(data, driven, source, k, b, b_unit=None):
    """Check a Pickup in a loaded .rez dict; return problem strings.

    Pure (no CLI): checks the formula entry, both links, the global
    parameters, and that the stored driven value equals ``k*source+b``.
    An empty list means the Pickup is present and consistent.
    """
    problems = []
    d_label, d_alias = driven
    s_label, s_alias = source
    found = find_pickup(data, driven)
    if found is None:
        return ["no Pickup found driving %s.%s" % (d_label, d_alias)]
    src_global = found["source_global"]
    driven_global = found["driven_global"]
    if found["source"] is not None and found["source"] != source:
        problems.append("Pickup source is %s.%s, expected %s.%s"
                        % (found["source"][0], found["source"][1],
                           s_label, s_alias))
    if src_global is None:
        problems.append("formula for %r has no dependency" % driven_global)
        return problems
    match = _PICKUP_CODE_RE.match(found["formula"] or "")
    if match is None:
        problems.append("formula code for %r is not a k*x+b expression: %r"
                        % (driven_global, found["formula"]))
        return problems
    if match.group("src") != src_global:
        problems.append("formula references %r, expected source global %r"
                        % (match.group("src"), src_global))
    try:
        code_k = float(match.group("k"))
        code_b_si = float(match.group("b"))
    except ValueError:
        problems.append("formula code has unparsable numbers: %r"
                        % (found["formula"],))
        return problems
    d_unit = param_unit(data, d_label, d_alias)
    if b_unit is None:
        b_unit = d_unit
    try:
        b_si = to_si(b, b_unit)
    except ValueError as e:
        return ["unknown b unit %r: %s" % (b_unit, e)]
    if abs(code_k - float(k)) > 1e-12 * max(1.0, abs(float(k))):
        problems.append("formula k is %.17g, expected %.17g"
                        % (code_k, float(k)))
    if abs(code_b_si - b_si) > 1e-12 * max(1.0, abs(b_si)):
        problems.append("formula b is %.17g (SI), expected %.17g"
                        % (code_b_si, b_si))
    customs = data.get("custom_params") or {}
    src_param = customs.get(src_global)
    driven_param = customs.get(driven_global)
    if not isinstance(src_param, dict):
        problems.append("source global %r missing from custom_params"
                        % (src_global,))
    if not isinstance(driven_param, dict):
        problems.append("driven global %r missing from custom_params"
                        % (driven_global,))
    if isinstance(src_param, dict) and isinstance(driven_param, dict):
        try:
            src_si = to_si(src_param.get("value"), src_param.get("unit"))
            drv_si = to_si(driven_param.get("value"),
                           driven_param.get("unit"))
        except (TypeError, ValueError) as e:
            problems.append("unreadable global values: %s" % (e,))
        else:
            expected = code_k * src_si + code_b_si
            if abs(drv_si - expected) > 1e-9 * max(1.0, abs(expected)):
                problems.append(
                    "stored driven value %.9g (SI) != k*source+b = %.9g"
                    % (drv_si, expected))
    return problems


# --- 1-D solver core -----------------------------------------------------

class _Infeasible(Exception):
    """A single evaluation point is infeasible (unstable / rejected)."""


class _Evaluator(object):
    """Batch CLI evaluation of a scalar residual over one variable.

    ``residual_fn(result, x_si, overrides)`` returns the residual in mm
    (or ``None`` when the point is infeasible). Results are cached, so
    Brent's repeated endpoint probes cost no extra CLI call.
    """

    def __init__(self, data, variable, residual_fn, binary=None,
                 timeout=None):
        from .cli import DEFAULT_BINARY
        self.data = data
        self.label, self.alias = variable
        self.unit = param_unit(data, self.label, self.alias)
        self.current_si = param_value_si(data, self.label, self.alias)
        if self.current_si is None or not math.isfinite(self.current_si):
            raise SolveError("variable %s.%s has no finite value"
                             % (self.label, self.alias))
        self.residual_fn = residual_fn
        self.binary = binary if binary is not None else DEFAULT_BINARY
        self.timeout = timeout
        self.cache = {}
        self.evaluations = 0

    def _overrides(self, x_si):
        """``{label: {alias: value_si}}`` for residual functions (SI)."""
        return {self.label: {self.alias: x_si}}

    def batch(self, values_si):
        # Coerce to plain floats: scipy hands back numpy scalars
        # (``res.x``), which would otherwise leak into the cache keys,
        # the overrides and the residual arithmetic (and break json).
        values_si = [float(v) for v in values_si]
        todo = [v for v in values_si if v not in self.cache]
        if todo:
            mutations = [{"id": i, "overrides":
                          {self.label: {self.alias: from_si(v, self.unit)}}}
                         for i, v in enumerate(todo)]
            try:
                out = run_headless({"base_schema": self.data,
                                    "mutations": mutations},
                                   binary=self.binary,
                                   timeout=self.timeout)
            except HeadlessError as e:
                raise SolveError("headless evaluation failed: %s" % (e,))
            results = out.get("results") or []
            if len(results) != len(todo):
                raise SolveError("headless CLI returned %d results for %d "
                                 "mutations" % (len(results), len(todo)))
            for v, result in zip(todo, results):
                self.cache[v] = self.residual_fn(
                    result, v, self._overrides(v))
                self.evaluations += 1
        return [self.cache[v] for v in values_si]

    def single(self, x_si):
        """Residual at one point; raises ``_Infeasible`` when not feasible."""
        value = self.batch([x_si])[0]
        if value is None:
            raise _Infeasible("x=%.9g (SI) is infeasible" % (x_si,))
        return value


def _solve_1d(evaluator, lo_si, hi_si, n_scan=DEFAULT_SCAN_POINTS,
              ftol_mm=None, xtol_si=DEFAULT_XTOL_SI, maxiter=100):
    """Solve ``residual(x) = 0`` for ``x`` in ``[lo_si, hi_si]``.

    ``ftol_mm`` is the residual tolerance in mm (default: 1e-9 relative
    to the largest |residual| seen on the scan, floored at 1e-12 mm).
    Returns ``{"solved_value", "residual", "iterations",
    "evaluations", "converged", "warnings", "brackets"}``; the solved
    value is in SI. Never invents a solution: when no point reaches the
    tolerance, ``converged`` is False and the best point found is
    returned.
    """
    warnings = []
    iterations = 0
    if not (math.isfinite(lo_si) and math.isfinite(hi_si)) or lo_si >= hi_si:
        raise SolveError("invalid bounds [%r, %r]" % (lo_si, hi_si))

    # Shortcut: the current value already satisfies the target.
    current = evaluator.current_si
    if lo_si <= current <= hi_si:
        try:
            f_current = evaluator.single(current)
            if ftol_mm is None:
                ftol_mm = 1e-12
            if abs(f_current) <= ftol_mm:
                return {"solved_value": current, "residual": f_current,
                        "iterations": 0,
                        "evaluations": evaluator.evaluations,
                        "converged": True,
                        "warnings": ["target already satisfied at the "
                                     "current value"],
                        "brackets": []}
        except _Infeasible:
            pass  # current point infeasible: fall through to the scan

    grid = [lo_si + (hi_si - lo_si) * i / (n_scan - 1)
            for i in range(n_scan)]
    f_grid = evaluator.batch(grid)
    feasible = [(x, f) for x, f in zip(grid, f_grid) if f is not None]
    n_infeasible = len(grid) - len(feasible)
    if n_infeasible:
        warnings.append("%d of %d scan points are infeasible (unstable "
                        "cavity or rejected value)" % (n_infeasible, n_scan))
    if not feasible:
        return {"solved_value": None, "residual": None, "iterations": 0,
                "evaluations": evaluator.evaluations, "converged": False,
                "warnings": warnings + ["no feasible point in the search "
                                        "interval"],
                "brackets": []}
    if ftol_mm is None:
        scale = max(abs(f) for _, f in feasible)
        ftol_mm = max(1e-9 * scale, 1e-12)

    # Degenerate: the target is satisfied (nearly) everywhere.
    best_x, best_f = min(feasible, key=lambda p: abs(p[1]))
    if all(abs(f) <= ftol_mm for _, f in feasible):
        warnings.append("residual is within tolerance over the whole "
                        "scanned interval; the target is satisfied "
                        "(nearly) everywhere -- returning the best point")
        return {"solved_value": best_x, "residual": best_f,
                "iterations": 0, "evaluations": evaluator.evaluations,
                "converged": True, "warnings": warnings, "brackets": []}

    # Sign-changing brackets between adjacent grid points (an infeasible
    # grid point between two feasible ones breaks the bracket).
    brackets = []
    for i in range(len(grid) - 1):
        f0, f1 = f_grid[i], f_grid[i + 1]
        if f0 is None or f1 is None:
            continue
        if f0 == 0.0:
            brackets.append((grid[i], grid[i]))
        elif f0 * f1 < 0:
            brackets.append((grid[i], grid[i + 1]))
    if f_grid[-1] is not None and f_grid[-1] == 0.0:
        brackets.append((grid[-1], grid[-1]))
    if brackets:
        # Solve the bracket closest to the current value first.
        brackets.sort(key=lambda br: abs(0.5 * (br[0] + br[1]) - current))
        if len(brackets) > 1:
            warnings.append(
                "multiple sign-change brackets found: %s; solving the one "
                "closest to the current value"
                % ([(round(a, 9), round(b, 9)) for a, b in brackets],))
        a, b = brackets[0]
        if a == b:
            f_a = evaluator.single(a)
            return {"solved_value": a, "residual": f_a, "iterations": 0,
                    "evaluations": evaluator.evaluations, "converged": True,
                    "warnings": warnings, "brackets": brackets}
        try:
            sol, info = brentq(evaluator.single, a, b, xtol=xtol_si,
                               maxiter=maxiter, full_output=True)
            iterations = info.iterations
            residual = evaluator.single(sol)
            converged = abs(residual) <= ftol_mm
            if not converged:
                warnings.append("Brent stopped with residual %.3g mm, "
                                "above tolerance %.3g mm"
                                % (residual, ftol_mm))
            return {"solved_value": sol, "residual": residual,
                    "iterations": iterations,
                    "evaluations": evaluator.evaluations,
                    "converged": converged, "warnings": warnings,
                    "brackets": brackets}
        except (_Infeasible, ValueError, RuntimeError) as e:
            warnings.append("Brent failed on bracket [%.9g, %.9g]: %s; "
                            "falling back to bounded minimisation"
                            % (a, b, e))

    # No sign change (or Brent failed): minimise |residual| over the
    # largest contiguous feasible grid run holding the best point.
    feasible_xs = {x for x, _ in feasible}
    best_gi = grid.index(best_x)
    lo_gi = best_gi
    while lo_gi > 0 and grid[lo_gi - 1] in feasible_xs:
        lo_gi -= 1
    hi_gi = best_gi
    while hi_gi + 1 < len(grid) and grid[hi_gi + 1] in feasible_xs:
        hi_gi += 1
    a, b = grid[lo_gi], grid[hi_gi]
    if a == b:
        return {"solved_value": best_x, "residual": best_f,
                "iterations": 0, "evaluations": evaluator.evaluations,
                "converged": abs(best_f) <= ftol_mm,
                "warnings": warnings + ["no sign change; best scan point "
                                        "returned"],
                "brackets": brackets}

    def _abs_residual(x):
        try:
            return abs(evaluator.single(x))
        except _Infeasible:
            return math.inf

    res = minimize_scalar(_abs_residual, bounds=(a, b), method="bounded",
                          options={"xatol": xtol_si})
    iterations = res.nit or 0
    solved = res.x
    try:
        residual = evaluator.single(solved) \
            if math.isfinite(res.fun) else None
    except _Infeasible:
        residual = None
    if residual is None:
        return {"solved_value": best_x, "residual": best_f,
                "iterations": iterations,
                "evaluations": evaluator.evaluations, "converged": False,
                "warnings": warnings + ["minimisation ended on an "
                                        "infeasible point; best scan point "
                                        "returned"],
                "brackets": brackets}
    converged = abs(residual) <= ftol_mm
    if not converged:
        warnings.append("no sign change in the interval; smallest "
                        "|residual| found is %.3g mm, above tolerance "
                        "%.3g mm" % (abs(residual), ftol_mm))
    return {"solved_value": solved, "residual": residual,
            "iterations": iterations, "evaluations": evaluator.evaluations,
            "converged": converged, "warnings": warnings,
            "brackets": brackets}


def _check_variable(data, variable):
    """Validate a solve variable; return ``(label, alias, unit, dim)``."""
    label, alias = variable
    if param_obj(data, label, alias) is None:
        raise SolveError("unknown variable %s.%s" % (label, alias))
    conflict = check_overridable(data, label, alias)
    if conflict is not None:
        raise SolveError("variable %s.%s cannot be solved: %s"
                         % (label, alias, conflict))
    unit = param_unit(data, label, alias)
    try:
        dim = dimension(unit)
    except ValueError as e:
        raise SolveError("variable %s.%s has unknown unit: %s"
                         % (label, alias, e))
    return label, alias, unit, dim


def _check_bounds(dim, alias, lo_si, hi_si):
    if not (math.isfinite(lo_si) and math.isfinite(hi_si)):
        raise SolveError("bounds must be finite: [%r, %r]" % (lo_si, hi_si))
    if lo_si >= hi_si:
        raise SolveError("bounds must satisfy lo < hi: [%r, %r]"
                         % (lo_si, hi_si))
    if dim == "length" and lo_si < MIN_LENGTH_SI:
        raise SolveError("length bounds must stay >= %.0e m (CLI guard): "
                         "[%r, %r]" % (MIN_LENGTH_SI, lo_si, hi_si))
    if alias in _CURVATURE_ALIASES and lo_si <= 0.0 <= hi_si:
        raise SolveError("curvature/focal interval [%r, %r] crosses 0 "
                         "(CLI guard: R/F must not be 0)"
                         % (lo_si, hi_si))


def _default_bounds(current_si, dim, alias):
    """Search interval around the current value (SI).

    Lengths: [0.5x, 2x] (mirrored for negative values, never crossing
    0 for R/F). Angles: current +/- 5 deg. Anything else needs explicit
    bounds.
    """
    if dim == "length":
        if current_si == 0.0:
            raise SolveError("variable is 0; explicit bounds are required")
        if current_si > 0:
            return (0.5 * current_si, 2.0 * current_si)
        return (2.0 * current_si, 0.5 * current_si)
    if dim == "angle":
        return (current_si - math.radians(5), current_si + math.radians(5))
    raise SolveError("explicit bounds are required for this variable")


def _beam_entry(result, label):
    """The beam entry for ``label`` in a CLI result, or ``None``."""
    beam = result.get("beam") if isinstance(result, dict) else None
    if not beam:
        return None
    for entry in beam:
        if isinstance(entry, dict) and entry.get("label") == label:
            return entry
    return None


def _waist_residual_fn(data, element, plane, mode, target_mm):
    """Build a residual function for a waist solve.

    ``mode`` is ``"size"`` (``target_mm`` is a waist radius) or
    ``"position"`` (``target_mm`` is an absolute axial position ``s``).
    The returned function takes ``(result, x_si, overrides)`` and
    returns the residual in mm, or ``None`` when the point is
    infeasible. ``target_mm`` may be a callable
    ``(overrides) -> float`` for targets that move with the variable
    (e.g. a position relative to a moving element plane).
    """
    lam_nm = wavelength_nm(data)

    def residual(result, x_si, overrides):
        if not result.get("ok"):
            return None
        if result.get("stable") is False:
            return None
        entry = _beam_entry(result, element)
        if entry is None:
            return None
        w_key = "w_%s_mm" % plane
        r_key = "R_%s_mm" % plane
        w_mm = entry.get(w_key)
        r_mm = entry.get(r_key)
        if w_mm is None or not math.isfinite(w_mm) or w_mm <= 0:
            return None
        try:
            w0_mm, z_mm = waist_from_wr(w_mm, r_mm, lam_nm)
        except ValueError:
            return None
        target = target_mm(overrides) if callable(target_mm) else target_mm
        if mode == "size":
            return w0_mm - target
        # position: waist s = plane position minus z (z > 0: upstream).
        plane_mm = element_plane_position_mm(data, element, overrides)
        return (plane_mm - z_mm) - target

    return residual


def _resolve_target(data, target):
    """Normalise a waist-position target to a callable.

    ``target`` is an absolute ``s`` in mm (a number), or a tuple
    ``("ref", label, offset_mm)``: ``s = plane(label) + offset`` with
    ``offset > 0`` downstream of that element's plane. Returns
    ``(callable, description)``.
    """
    if isinstance(target, (int, float)) and not isinstance(target, bool):
        if not math.isfinite(target):
            raise SolveError("target must be finite: %r" % (target,))
        return (lambda overrides: float(target),
                "absolute s=%.6g mm" % (target,))
    if (isinstance(target, (tuple, list)) and len(target) == 3
            and target[0] == "ref"):
        _, label, offset = target
        if not isinstance(offset, (int, float)) or isinstance(offset, bool) \
                or not math.isfinite(offset):
            raise SolveError("reference offset must be a finite number: "
                             "%r" % (offset,))
        element_plane_position_mm(data, label)  # validates the label
        return (lambda overrides: element_plane_position_mm(
                    data, label, overrides) + float(offset),
                "s = plane(%s) %+.6g mm" % (label, offset))
    raise SolveError(
        "target must be an absolute s in mm or (\"ref\", label, offset_mm), "
        "got %r" % (target,))


def _finish_result(kind, data, variable, element, plane, target_desc,
                   target_value, solve, unit):
    """Attach the descriptive fields to a ``_solve_1d`` result."""
    label, alias = variable
    solved = solve["solved_value"]
    residual = solve["residual"]
    result = {
        "kind": kind,
        "variable": {"label": label, "alias": alias, "unit": unit},
        "element": element,
        "plane": plane,
        "target": target_desc,
        "target_value_mm": target_value,
        "solved_value": (None if solved is None else float(solved)),
        "solved_value_display": (None if solved is None
                                 else from_si(float(solved), unit)),
        "residual_mm": (None if residual is None else float(residual)),
        "residual_rel": (None if residual is None
                         or target_value in (None, 0)
                         else abs(float(residual))
                         / max(abs(target_value), 1e-12)),
        "iterations": int(solve["iterations"]),
        "evaluations": int(solve["evaluations"]),
        "converged": bool(solve["converged"]),
        "warnings": solve["warnings"],
        "brackets_si": solve["brackets"],
    }
    return result


def solve_waist_size(data, variable, element, target_w0_mm, plane="T",
                     bounds_si=None, binary=None, timeout=None,
                     n_scan=DEFAULT_SCAN_POINTS, ftol_rel=DEFAULT_FTOL_REL,
                     xtol_si=DEFAULT_XTOL_SI):
    """Solve for the variable value making a segment's waist radius
    equal ``target_w0_mm``.

    ``variable`` is ``(label, alias)``; ``element`` selects the beam
    segment (the segment downstream of that element); ``plane`` is
    ``"T"`` or ``"S"``. ``bounds_si`` is ``(lo, hi)`` in SI units
    (default: [0.5x, 2x] of the current value for lengths). The result
    is the dict documented in the module docstring; ``solved_value``
    is in SI, ``residual_mm`` in mm.
    """
    if plane not in ("T", "S"):
        raise SolveError("plane must be 'T' or 'S': %r" % (plane,))
    if not isinstance(target_w0_mm, (int, float)) \
            or isinstance(target_w0_mm, bool) \
            or not math.isfinite(target_w0_mm) or target_w0_mm <= 0:
        raise SolveError("target waist radius must be a positive number: "
                         "%r" % (target_w0_mm,))
    label, alias, unit, dim = _check_variable(data, variable)
    current_si = param_value_si(data, label, alias)
    if bounds_si is None:
        bounds_si = _default_bounds(current_si, dim, alias)
    _check_bounds(dim, alias, bounds_si[0], bounds_si[1])
    element_plane_position_mm(data, element)  # validates the element
    residual_fn = _waist_residual_fn(data, element, plane, "size",
                                     float(target_w0_mm))
    evaluator = _Evaluator(data, variable, residual_fn, binary=binary,
                           timeout=timeout)
    ftol_mm = ftol_rel * max(abs(float(target_w0_mm)), 1e-3)
    solve = _solve_1d(evaluator, bounds_si[0], bounds_si[1], n_scan=n_scan,
                      ftol_mm=ftol_mm, xtol_si=xtol_si)
    return _finish_result("waist_size", data, variable, element, plane,
                          "w0 = %.6g mm" % (target_w0_mm,),
                          float(target_w0_mm), solve, unit)


def solve_waist_position(data, variable, element, target, plane="T",
                         bounds_si=None, binary=None, timeout=None,
                         n_scan=DEFAULT_SCAN_POINTS,
                         ftol_rel=DEFAULT_FTOL_REL,
                         xtol_si=DEFAULT_XTOL_SI):
    """Solve for the variable value placing a segment's waist at
    ``target``.

    ``target`` is an absolute axial position ``s`` in mm (``s = 0`` at
    the first element's plane, increasing along the element list), or
    ``("ref", label, offset_mm)`` for a position relative to an
    element's plane (``offset > 0`` downstream). ``element`` selects
    the beam segment, ``plane`` is ``"T"`` or ``"S"``. Other arguments
    as in :func:`solve_waist_size`.
    """
    if plane not in ("T", "S"):
        raise SolveError("plane must be 'T' or 'S': %r" % (plane,))
    label, alias, unit, dim = _check_variable(data, variable)
    current_si = param_value_si(data, label, alias)
    if bounds_si is None:
        bounds_si = _default_bounds(current_si, dim, alias)
    _check_bounds(dim, alias, bounds_si[0], bounds_si[1])
    element_plane_position_mm(data, element)  # validates the element
    target_fn, target_desc = _resolve_target(data, target)
    residual_fn = _waist_residual_fn(data, element, plane, "position",
                                     target_fn)
    evaluator = _Evaluator(data, variable, residual_fn, binary=binary,
                           timeout=timeout)
    total = total_length_mm(data)
    ftol_mm = ftol_rel * max(abs(total), 1e-3)
    solve = _solve_1d(evaluator, bounds_si[0], bounds_si[1], n_scan=n_scan,
                      ftol_mm=ftol_mm, xtol_si=xtol_si)
    return _finish_result("waist_position", data, variable, element, plane,
                          target_desc, None, solve, unit)


def apply_solution(data, variable, solved_value_si):
    """Write a solved value back into a loaded .rez dict (in place).

    The value is stored in the parameter's own unit; ``schema_version``
    and unknown keys are untouched. Refuses driven parameters
    (``check_overridable``) and values violating the CLI guards.
    """
    label, alias = variable
    if param_obj(data, label, alias) is None:
        raise SolveError("unknown variable %s.%s" % (label, alias))
    conflict = check_overridable(data, label, alias)
    if conflict is not None:
        raise SolveError("cannot write back to %s.%s: %s"
                         % (label, alias, conflict))
    if solved_value_si is None or not math.isfinite(solved_value_si):
        raise SolveError("solved value is not finite: %r"
                         % (solved_value_si,))
    unit = param_unit(data, label, alias)
    dim = dimension(unit)
    if dim == "length" and solved_value_si < MIN_LENGTH_SI:
        raise SolveError("solved value %.9g m is below the CLI guard for "
                         "lengths (>= %.0e m)" % (solved_value_si,
                                                  MIN_LENGTH_SI))
    if alias in _CURVATURE_ALIASES and solved_value_si == 0.0:
        raise SolveError("solved value must not be 0 for %s.%s"
                         % (label, alias))
    param = param_obj(data, label, alias)
    param["value"] = from_si(solved_value_si, unit)
