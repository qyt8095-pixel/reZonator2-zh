"""Stock-part Snap (Phase 3 block 1).

A continuous mirror radius is snapped to the nearest stock part in
*dioptric* (1/R) space -- not linear R space: a flat mirror (R = inf)
and R = 10000 mm are optically almost identical, but their linear
distance is infinite; R = 50 mm and R = 60 mm differ by only 10 mm
linearly but by 20% in dioptric power. The distance is::

    d(R, R_std) = |1/R - 1/R_std|        (1/R = 0 for a flat mirror)

The sign is preserved: a concave mirror never snaps to a convex
stock part or vice versa (a flat input, R = inf, has no sign and
snaps to the dioptrically nearest part of either sign).

The built-in catalog is a *labelled example sequence* (common
curvature values), not a real vendor list -- real stock data comes
from a user-supplied CSV with the fields ``vendor, part_number,
R_mm, diameter_mm, coating`` (``R_mm`` may be ``inf`` for flat).

After snapping, the snapped radii are locked (removed from the
variables) and the neighbouring cavity lengths stay free; the
original merit function is re-optimised with Nelder-Mead (100--200
evaluations) so the arm lengths compensate the snap *and* the merit
is re-validated in the same step. The result is a before/after
comparison table (Delta w, Delta g, Delta Merit).
"""

import csv
import math

import numpy as np
from scipy.optimize import minimize

from .cli import DEFAULT_BINARY, run_headless
from .merit import evaluate_result
from .optimizer import BatchEvaluator, OptimizerError

#: Example stock curvature sequence (mm). The source is an example
#: sequence of common values, NOT a vendor catalogue: real parts
#: come from a user CSV (see :func:`load_catalog_csv`).
_EXAMPLE_RADII_MM = [25, 38.1, 50, 75, 100, 125, 150, 200, 250, 300,
                     500, 750, 1000, 2000, 5000, 10000, None]


def _example_catalog():
    catalog = []
    for r in _EXAMPLE_RADII_MM:
        for sign in ((1,) if r is None else (1, -1)):
            value = None if r is None else sign * r
            catalog.append({
                "vendor": "EXAMPLE-STOCK",
                "part_number": ("EX-FLAT" if value is None
                                else "EX-R%g" % value),
                "R_mm": value,
                "diameter_mm": 25.4,
                "coating": "1064nm HR",
            })
    return catalog


#: Built-in stock catalogue (example sequence, see above).
STOCK_CATALOG = _example_catalog()


class CatalogError(ValueError):
    """Raised when a catalogue cannot be loaded or a snap is impossible."""


def _parse_R_mm(raw):
    raw = (raw or "").strip()
    if raw in ("", "inf", "Inf", "INF", "∞", "infinity"):
        return None
    value = float(raw)
    if value == 0.0 or not math.isfinite(value):
        raise CatalogError("R_mm must be non-zero and finite, or inf: %r"
                           % (raw,))
    return value


def load_catalog_csv(path):
    """Load a user stock catalogue from CSV. Required columns:
    ``vendor, part_number, R_mm, diameter_mm, coating``. ``R_mm``
    may be ``inf`` for a flat mirror. Returns a list of part dicts."""
    parts = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"vendor", "part_number", "R_mm", "diameter_mm",
                    "coating"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise CatalogError("CSV %s is missing columns: %s"
                               % (path, ", ".join(sorted(missing))))
        for row in reader:
            try:
                parts.append({
                    "vendor": (row["vendor"] or "").strip(),
                    "part_number": (row["part_number"] or "").strip(),
                    "R_mm": _parse_R_mm(row["R_mm"]),
                    "diameter_mm": float(row["diameter_mm"]),
                    "coating": (row["coating"] or "").strip(),
                })
            except (ValueError, TypeError) as e:
                raise CatalogError("bad row in %s: %r (%s)"
                                   % (path, row, e))
    if not parts:
        raise CatalogError("CSV %s has no parts" % (path,))
    return parts


def dioptric(R_mm):
    """Dioptric power 1/R in 1/mm; 0 for a flat mirror (R = inf)."""
    if R_mm is None:
        return 0.0
    return 1.0 / R_mm


def dioptric_distance(R_mm, R_std_mm):
    """``|1/R - 1/R_std|`` in 1/mm."""
    return abs(dioptric(R_mm) - dioptric(R_std_mm))


def snap_radius(R_mm, catalog=None, vendor=None, min_diameter_mm=None,
                coating=None):
    """Snap a radius (mm, ``None`` for flat) to the nearest stock
    part in dioptric space. ``vendor`` (str or list), ``min_diameter_mm``
    and ``coating`` (substring) filter the candidates. Returns
    ``(part, distance)`` where ``distance`` is in 1/mm, or raises
    :class:`CatalogError` when no candidate survives the filters
    (e.g. a concave radius with only convex parts in stock)."""
    catalog = list(catalog if catalog is not None else STOCK_CATALOG)
    vendors = None
    if vendor is not None:
        vendors = {vendor} if isinstance(vendor, str) else set(vendor)
    candidates = []
    for part in catalog:
        if vendors is not None and part["vendor"] not in vendors:
            continue
        if min_diameter_mm is not None \
                and part["diameter_mm"] < min_diameter_mm:
            continue
        if coating is not None and coating not in part["coating"]:
            continue
        if R_mm is not None and part["R_mm"] is not None:
            # Sign preserved: concave never snaps to convex. A flat
            # part (R = inf) has no sign and matches either side.
            if (R_mm > 0) != (part["R_mm"] > 0):
                continue
        candidates.append(part)
    if not candidates:
        raise CatalogError("no stock part matches R=%s mm with the "
                           "given filters" % (R_mm,))
    best = min(candidates,
               key=lambda p: dioptric_distance(R_mm, p["R_mm"]))
    return best, dioptric_distance(R_mm, best["R_mm"])


def _beam_w(result, element):
    beam = result.get("beam") or []
    for entry in beam:
        if entry.get("label") == element:
            return entry.get("w_T_mm"), entry.get("w_S_mm")
    return None, None


def snap_and_reoptimize(data, snap_specs, variables, targets,
                        free_length_vars, constraints=None,
                        nm_maxfev=150, binary=None, timeout=None,
                        power=None, catalog=None):
    """Snap radii and re-optimise the neighbouring lengths.

    ``snap_specs`` is a list of ``{"label", "alias", "vendor",
    "min_diameter_mm", "coating"}`` (the last three optional) -- one
    per mirror radius to snap. ``variables`` is the full variable
    list (as in :func:`rezeng.optimizer.optimize`); the snapped
    variables are locked at their stock values and removed from the
    free set. ``free_length_vars`` lists the (label, alias) length
    variables that stay free for compensation (they must be in
    ``variables`` with bounds). Returns::

        {"snapped": [{"label", "alias", "old_R_mm", "new_R_mm",
                      "part_number", "vendor", "distance_per_mm"}],
         "before": {"values_si", "merit", "breakdown",
                    "g_T", "g_S", "beam": {element: (w_T, w_S)}},
         "after": {...same...},
         "comparison": {"delta_merit", "delta_g_T", "delta_g_S",
                        "delta_w": {element: {"T": ..., "S": ...}}},
         "nm": {"nfev": int, "nit": int, "success": bool}}

    ``before`` is the current schema state (start point); ``after``
    is the Nelder-Mead re-optimisation result. The merit in both
    cases is the *same* original merit function.
    """
    from .rez import param_value_si

    free_length_vars = [tuple(k) for k in free_length_vars]
    snapped = []
    fixed = {}
    snapped_keys = set()
    for spec in snap_specs:
        label, alias = spec["label"], spec["alias"]
        r_si = param_value_si(data, label, alias)
        if r_si is None or not math.isfinite(r_si):
            raise CatalogError("snap variable %s.%s has no finite value"
                               % (label, alias))
        r_mm = r_si * 1e3
        part, dist = snap_radius(
            None if math.isinf(r_mm) else r_mm,
            catalog=catalog, vendor=spec.get("vendor"),
            min_diameter_mm=spec.get("min_diameter_mm"),
            coating=spec.get("coating"))
        new_R_mm = part["R_mm"]
        snapped.append({"label": label, "alias": alias,
                        "old_R_mm": r_mm, "new_R_mm": new_R_mm,
                        "part_number": part["part_number"],
                        "vendor": part["vendor"],
                        "distance_per_mm": dist})
        fixed[(label, alias)] = (float("inf") if new_R_mm is None
                                 else new_R_mm * 1e-3)
        snapped_keys.add((label, alias))

    free_vars = []
    for v in variables:
        key = (v.get("label"), v.get("alias"))
        if key in snapped_keys:
            continue
        if key not in free_length_vars:
            raise OptimizerError(
                "variable %s.%s is neither snapped nor listed in "
                "free_length_vars" % key)
        free_vars.append(v)
    for key in free_length_vars:
        if key not in [(v.get("label"), v.get("alias"))
                       for v in free_vars]:
            raise OptimizerError(
                "free length variable %s.%s is not in variables"
                % key)

    evaluator = BatchEvaluator(data, free_vars, targets,
                               constraints=constraints, binary=binary,
                               timeout=timeout, power=power)
    if fixed:
        base_overrides = evaluator._overrides_for_point

        def _with_fixed(values_si):
            merged = dict(values_si)
            merged.update(fixed)
            return base_overrides(merged)

        evaluator._overrides_for_point = _with_fixed

    def _snapshot_values(result, values_si):
        merit, breakdown = evaluate_result(result, targets, data=data,
                                           power=power)
        beam = {}
        for t in targets:
            el = t.get("element")
            if el and el not in beam:
                beam[el] = _beam_w(result, el)
        return {"values_si": dict(values_si), "merit": merit,
                "breakdown": breakdown, "g_T": result.get("g_T"),
                "g_S": result.get("g_S"), "beam": beam}

    def snapshot(x01):
        result = evaluator.result_at(x01)
        if result is None:
            raise CatalogError("evaluation at a snapshot point is "
                               "infeasible")
        values_si = {}
        for i, v in enumerate(evaluator.continuous):
            values_si[(v["label"], v["alias"])] = \
                evaluator._denormalize(i, x01[i])
        for key, value in fixed.items():
            values_si[key] = value
        return _snapshot_values(result, values_si)

    # "Before" is the current schema as-is (original radii, current
    # lengths): a plain base-schema evaluation, no overrides at all.
    base_out = run_headless(
        {"base_schema": data, "mutations": [{"id": 0, "overrides": {}}]},
        binary=binary or DEFAULT_BINARY, timeout=timeout)
    base_results = base_out.get("results") or []
    if len(base_results) != 1 or not base_results[0].get("ok"):
        raise CatalogError("base-schema evaluation failed: %s"
                           % (base_results[0].get("error")
                              if base_results else "no result"))
    before_values = {}
    for v in variables:
        key = (v.get("label"), v.get("alias"))
        before_values[key] = param_value_si(data, key[0], key[1])
    before = _snapshot_values(base_results[0], before_values)

    start01 = evaluator.start01
    # Re-optimise the free lengths from the start point (snapped
    # radii locked).
    nm = minimize(evaluator, start01, method="Nelder-Mead",
                  options={"xatol": 1e-4, "fatol": 1e-5,
                           "maxfev": nm_maxfev, "adaptive": True})
    after = snapshot(np.clip(np.array(nm.x, dtype=float), 0.0, 1.0))

    comparison = {
        "delta_merit": after["merit"] - before["merit"],
        "delta_g_T": (after["g_T"] - before["g_T"]
                      if after["g_T"] is not None
                      and before["g_T"] is not None else None),
        "delta_g_S": (after["g_S"] - before["g_S"]
                      if after["g_S"] is not None
                      and before["g_S"] is not None else None),
        "delta_w": {},
    }
    for el in set(before["beam"]) | set(after["beam"]):
        b_w = before["beam"].get(el, (None, None))
        a_w = after["beam"].get(el, (None, None))
        comparison["delta_w"][el] = {
            "T": (a_w[0] - b_w[0] if a_w[0] is not None
                  and b_w[0] is not None else None),
            "S": (a_w[1] - b_w[1] if a_w[1] is not None
                  and b_w[1] is not None else None),
        }
    return {
        "snapped": snapped,
        "before": before,
        "after": after,
        "comparison": comparison,
        "nm": {"nfev": int(nm.nfev), "nit": int(nm.nit),
               "success": bool(nm.success)},
    }
