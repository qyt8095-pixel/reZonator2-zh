"""Dual stability-zone (Zone I / Zone II) 1D scan (Phase 3 block 1).

For a standing-wave cavity the pump power acts through the thermal
lens: the dioptric power ``D_th = 1 / f_th`` grows (roughly) linearly
with pump power, and the cavity crosses Zone I and Zone II in turn,
separated by an unstable band. This module scans ``D_th`` in one CLI
batch request (200--500 points), then locates every crossing of
``g = +1`` / ``g = -1`` precisely with Brent's method on the
sign-changing scan intervals.

Astigmatism can shift the T and S stability zones apart, so the
module always reports ``zones_T``, ``zones_S`` *and* their strict
intersection ``zones_common``; judging stability from one plane alone
is wrong. Common zones are labelled Zone I, Zone II, ... in
ascending ``D_th``.

Output (JSON-serialisable)::

    {"lens": {"label": "TL1", "alias": "F"},
     "d_range": [0.0, 12.0], "n_points": 300,
     "boundaries": [{"axis": "T", "g": 1.0, "D_th": ...,
                     "f_mm": ..., "bracket": [lo, hi]}],
     "zones_T": [{"id": "Zone_T_1", "D_range": [lo, hi],
                  "f_range": [f_hi, f_lo], "power_range": ...}],
     "zones_S": [...],
     "zones_common": [{"id": "Zone_I", ...}],
     "trajectory": [{"D_th", "g_T", "g_S",
                     "w_sesam_T_mm", "w_sesam_S_mm",
                     "w_crystal_T_mm", "w_crystal_S_mm",
                     "is_stable"}],
     "working_point": {"D_th", "f_mm", "zone", "is_stable"} | None,
     "n_cli_calls": int}

``f_range`` is ``[1/D_hi, 1/D_lo]`` in mm (``D = 0`` maps to infinite
focal length, reported as ``None``). ``power_range`` is included only
when a ``power_map`` callable (``D_th`` -> pump power in W) is given.
``w_sesam_*`` is the beam at the SESAM/end-mirror element (default
``M1``); ``w_crystal_*`` the beam at the thermal-lens/gain element
(default: found with :func:`rezeng.qevolve.find_gain_element`).
``opt_path`` (optional input) embeds optimiser evaluations as
``{"D_th", "merit"}`` points for trajectory overlays.
"""

import math

import numpy as np
from scipy.optimize import brentq

from .cli import DEFAULT_BINARY, HeadlessError, run_headless
from .qevolve import find_gain_element
from .rez import param_unit, param_value_si
from .units import from_si

#: Brent tolerance on D_th (1/m) for boundary refinement.
BRENT_XTOL = 1e-9

#: Focal length used for D_th = 0 (effectively no thermal lens).
F_AT_ZERO_D_M = 1e3


class ZoneError(ValueError):
    """Raised when a zone scan cannot be set up or evaluated."""


def _f_mm_for_D(D_th, unit):
    """Focal length (in the parameter's own unit) for a dioptric
    power ``D_th`` (1/m). ``D_th = 0`` maps to a very long focal
    length, not infinity (the CLI rejects F = 0 and cannot take
    infinity)."""
    if D_th <= 0.0:
        return float(from_si(F_AT_ZERO_D_M, unit))
    return float(from_si(1.0 / D_th, unit))


def _g_at(evaluator, D_th, axis):
    """``g_T`` or ``g_S`` at one ``D_th`` (single CLI evaluation,
    cached)."""
    return evaluator(D_th, axis)


class _ZoneEvaluator(object):
    """Single-point g(D_th) evaluation with a cache (used by the
    Brent refinement; the coarse scan itself is one batch call)."""

    def __init__(self, data, label, alias, binary=None, timeout=None):
        self.data = data
        self.label = label
        self.alias = alias
        self.unit = param_unit(data, label, alias)
        self.binary = binary if binary is not None else DEFAULT_BINARY
        self.timeout = timeout
        self.cache = {}
        self.cli_calls = 0
        self.evaluations = 0

    def __call__(self, D_th, axis):
        key = (float(D_th), axis)
        if key in self.cache:
            return self.cache[key]
        out = run_headless(
            {"base_schema": self.data,
             "mutations": [{"id": 0, "overrides": {
                 self.label: {self.alias: _f_mm_for_D(D_th, self.unit)}}}]},
            binary=self.binary, timeout=self.timeout)
        self.cli_calls += 1
        self.evaluations += 1
        results = out.get("results") or []
        if len(results) != 1:
            raise ZoneError("headless CLI returned %d results for 1 "
                            "mutation" % len(results))
        result = results[0]
        if not result.get("ok"):
            raise ZoneError("headless evaluation failed at D_th=%.9g: %s"
                            % (D_th, result.get("error")))
        value = result.get("g_T" if axis == "T" else "g_S")
        if value is None or not math.isfinite(value):
            raise ZoneError("no finite g_%s at D_th=%.9g" % (axis, D_th))
        self.cache[key] = float(value)
        return float(value)


def _beam_at(result, label):
    beam = result.get("beam") or []
    for entry in beam:
        if entry.get("label") == label:
            return entry.get("w_T_mm"), entry.get("w_S_mm")
    return None, None


def _intersect_intervals(a_list, b_list):
    """Intersection of two lists of [lo, hi] intervals."""
    out = []
    for lo_a, hi_a in a_list:
        for lo_b, hi_b in b_list:
            lo, hi = max(lo_a, lo_b), min(hi_a, hi_b)
            if hi > lo:
                out.append((lo, hi))
    return sorted(out)


def _f_range(D_lo, D_hi):
    """``[f(D_hi), f(D_lo)]`` in mm; ``None`` for infinite focal
    length (D = 0)."""
    f_lo = None if D_lo <= 0 else 1.0 / D_lo * 1e3
    f_hi = None if D_hi <= 0 else 1.0 / D_hi * 1e3
    return [f_hi, f_lo]


def scan_zones(data, lens=("TL1", "F"), d_min=0.0, d_max=12.0,
               n_points=300, sesam_label="M1", crystal_label=None,
               binary=None, timeout=None, power_map=None,
               working_f_mm=None, opt_path=None):
    """1D ``D_th`` scan with Brent-refined boundaries.

    ``lens`` is the (label, alias) of the thermal-lens focal-length
    parameter. ``d_min``/``d_max`` are dioptric powers in 1/m.
    ``working_f_mm`` (the current focal length, in mm) marks the
    working point in the output. ``opt_path`` is an optional list of
    ``{"D_th", "merit"}`` optimiser points, embedded verbatim.
    """
    label, alias = lens
    current_si = param_value_si(data, label, alias)
    if current_si is None or not math.isfinite(current_si) \
            or current_si == 0:
        raise ZoneError("lens parameter %s.%s has no finite non-zero "
                        "value" % (label, alias))
    unit = param_unit(data, label, alias)
    if crystal_label is None:
        try:
            crystal_label = find_gain_element(data, None)
        except Exception:
            crystal_label = None
    if not (math.isfinite(d_min) and math.isfinite(d_max)
            and 0.0 <= d_min < d_max):
        raise ZoneError("need 0 <= d_min < d_max, got %r, %r"
                        % (d_min, d_max))
    if n_points < 3:
        raise ZoneError("need at least 3 scan points")

    D = np.linspace(d_min, d_max, n_points)
    mutations = [{"id": i, "overrides": {
        label: {alias: _f_mm_for_D(float(d), unit)}}}
        for i, d in enumerate(D)]
    try:
        out = run_headless({"base_schema": data, "mutations": mutations},
                           binary=binary or DEFAULT_BINARY,
                           timeout=timeout)
    except HeadlessError as e:
        raise ZoneError("headless evaluation failed: %s" % (e,))
    results = out.get("results") or []
    if len(results) != n_points:
        raise ZoneError("headless CLI returned %d results for %d "
                        "mutations" % (len(results), n_points))
    n_cli_calls = 1

    g_T = np.array([r.get("g_T") if r.get("ok") else np.nan
                    for r in results], dtype=float)
    g_S = np.array([r.get("g_S") if r.get("ok") else np.nan
                    for r in results], dtype=float)
    if not (np.isfinite(g_T).all() and np.isfinite(g_S).all()):
        bad = [i for i in range(n_points)
               if not (math.isfinite(g_T[i]) and math.isfinite(g_S[i]))]
        raise ZoneError("non-finite g at scan points %s" % (bad[:5],))

    trajectory = []
    for i, d in enumerate(D):
        w_s_T, w_s_S = _beam_at(results[i], sesam_label)
        w_c_T, w_c_S = (_beam_at(results[i], crystal_label)
                        if crystal_label else (None, None))
        trajectory.append({
            "D_th": float(d),
            "g_T": float(g_T[i]), "g_S": float(g_S[i]),
            "w_sesam_T_mm": w_s_T, "w_sesam_S_mm": w_s_S,
            "w_crystal_T_mm": w_c_T, "w_crystal_S_mm": w_c_S,
            "is_stable": bool(abs(g_T[i]) < 1.0 and abs(g_S[i]) < 1.0),
        })

    # --- refine every g = +/-1 crossing with Brent ------------------
    evaluator = _ZoneEvaluator(data, label, alias, binary=binary,
                               timeout=timeout)
    boundaries = []
    for axis, g in (("T", g_T), ("S", g_S)):
        for level in (1.0, -1.0):
            f = g - level
            for i in range(1, n_points):
                if f[i - 1] == 0.0:
                    boundaries.append({"axis": axis, "g": level,
                                       "D_th": float(D[i - 1]),
                                       "f_mm": _f_mm_for_D(
                                           float(D[i - 1]), unit),
                                       "bracket": [float(D[i - 1]),
                                                   float(D[i - 1])]})
                elif f[i - 1] * f[i] < 0.0:
                    lo, hi = float(D[i - 1]), float(D[i])
                    root = brentq(lambda d: evaluator(d, axis) - level,
                                  lo, hi, xtol=BRENT_XTOL,
                                  rtol=8.9e-16, maxiter=100)
                    boundaries.append({"axis": axis, "g": level,
                                       "D_th": float(root),
                                       "f_mm": _f_mm_for_D(
                                           float(root), unit),
                                       "bracket": [lo, hi]})
    boundaries.sort(key=lambda b: (b["D_th"], b["axis"]))
    n_cli_calls += evaluator.cli_calls

    # --- stable intervals per axis (refined cuts) --------------------
    def axis_zones(axis, g):
        cuts = [d_min]
        for b in boundaries:
            if b["axis"] == axis:
                cuts.append(b["D_th"])
        cuts.append(d_max)
        cuts = sorted(set(cuts))
        zones = []
        for lo, hi in zip(cuts[:-1], cuts[1:]):
            if hi <= lo:
                continue
            mid = 0.5 * (lo + hi)
            # |g| at the exact midpoint decides the stability of the
            # interval (one cached CLI evaluation per interval).
            g_mid = evaluator(mid, axis)
            if abs(g_mid) < 1.0:
                zones.append((lo, hi))
        return zones

    zones_T = axis_zones("T", g_T)
    zones_S = axis_zones("S", g_S)
    zones_common = _intersect_intervals(zones_T, zones_S)

    def zone_dicts(intervals, prefix, power_map=None):
        out_zones = []
        for k, (lo, hi) in enumerate(intervals, start=1):
            entry = {"id": "%s_%d" % (prefix, k),
                     "D_range": [float(lo), float(hi)],
                     "f_range": _f_range(lo, hi)}
            if power_map is not None:
                entry["power_range"] = [power_map(lo), power_map(hi)]
            out_zones.append(entry)
        return out_zones

    common = zone_dicts(zones_common, "Zone", power_map)
    for k, entry in enumerate(common):
        entry["id"] = ["Zone_I", "Zone_II", "Zone_III", "Zone_IV",
                       "Zone_V"][k] if k < 5 else "Zone_%d" % (k + 1)

    working_point = None
    if working_f_mm is not None:
        D_w = 1.0 / (working_f_mm * 1e-3) if working_f_mm > 0 else 0.0
        zone = None
        for entry in common:
            lo, hi = entry["D_range"]
            if lo <= D_w <= hi:
                zone = entry["id"]
                break
        w_idx = int(np.argmin(np.abs(D - D_w))) \
            if len(D) else None
        working_point = {
            "D_th": float(D_w), "f_mm": float(working_f_mm),
            "zone": zone,
            "is_stable": bool(trajectory[w_idx]["is_stable"])
            if w_idx is not None else None,
        }

    result = {
        "lens": {"label": label, "alias": alias},
        "d_range": [float(d_min), float(d_max)],
        "n_points": n_points,
        "boundaries": boundaries,
        "zones_T": zone_dicts(zones_T, "Zone_T", power_map),
        "zones_S": zone_dicts(zones_S, "Zone_S", power_map),
        "zones_common": common,
        "trajectory": trajectory,
        "working_point": working_point,
        "n_cli_calls": n_cli_calls,
    }
    if opt_path is not None:
        result["opt_path"] = opt_path
    return result
