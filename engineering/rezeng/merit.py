"""Merit (evaluation) function for the Phase 3 cavity optimizer.

Mirrors the C++ ``OptimizerFunction`` merit definition item by item
(see ``src/math/OptimizerFunction.h`` / ``.cpp``), so the Python
optimizer and the shipped C++ OptimizerWindow optimise the same
quantity. The one deliberate difference is the out-of-stability
penalty constants (see :data:`PENALTY_BASE` / :data:`PENALTY_SLOPE`):
the C++ code uses 1e4 + 1e5 * (overT^2 + overS^2); the Python side
follows the Gemini Phase 3 review recommendation, 1e6 +
1e4 * max(0, max(|gT|, |gS|) - 1)^2. Both are a continuous
step + ramp (never a flat dead zone), both sit far above any merit
reachable inside the stability region, and both give a gradient
pointing back towards |g| < 1. The alignment table in
``engineering/README.md`` lists the two side by side.

Merit definition (all lengths in mm here; the C++ code uses SI, the
formulas are scale-free):

* beam radius target at an element (T or S plane)::

      term = W * ((w - T) / T)^2

  i.e. the spec's ((V - T) / sigma)^2 with sigma = T (relative error).
* astigmatism at an element::

      d = |w_T - w_S|;  ref = max(max(w_T, w_S), 1e-12)
      term = W * (d / ref)^2

* stability centering::

      term = W * (g_T^2 + g_S^2)

  (target g = 0, sigma = 1).
* waist target at an element (Python-side extension -- the C++
  OptimizerWindow has no waist target kind): the waist of that
  element's beam segment, derived from its (w, R) with
  :func:`rezeng.solves.waist_from_wr`::

      term = W * ((w0 - T) / T)^2

* output-power target (optional, Mode A -- see :func:`evaluate_result`
  and the cost note there)::

      term = W * ((P_out - T) / T)^2

* out-of-stability (|gT| >= 1 or |gS| >= 1)::

      merit = 1e6 + 1e4 * max(0, max(|gT|, |gS|) - 1)^2

  (no target terms are added on top of the penalty, as in C++).
* rejected mutation / non-finite value / non-finite merit::

      merit = 1e9  (PENALTY_UNSTABLE, same as C++)

Targets are plain dicts, e.g.::

    {"kind": "beam_T", "element": "M4", "target_mm": 0.21, "weight": 1.0}
    {"kind": "astigmatism", "element": "M4", "weight": 10.0}
    {"kind": "stability_center", "weight": 1.0}
    {"kind": "waist", "element": "M1", "target_mm": 0.12, "weight": 1.0}
    {"kind": "power_out", "target_W": 2.6, "weight": 1.0}

Equality constraints are *not* penalty terms here: linear ones are
handled by variable reduction in :mod:`rezeng.optimizer`
(``L_n = L_total - sum(L_i)``), and non-linear Solve targets become
high-weight merit terms (weight x10--x100), per the Phase 3 review.
Never nest a Brent solve inside the merit loop.
"""

import math

from .solves import waist_from_wr, wavelength_nm

#: Merit returned for a rejected mutation or a non-finite value.
#: Same constant as C++ ``OptimizerFunction::PENALTY_UNSTABLE``.
PENALTY_UNSTABLE = 1e9

#: Out-of-stability penalty: base step (Gemini Phase 3 review).
#: Far above any merit reachable inside the stability region.
PENALTY_BASE = 1e6

#: Out-of-stability penalty: ramp slope on the overshoot squared.
PENALTY_SLOPE = 1e4

#: Astigmatism reference floor (mm), copied from C++ (1e-12 m in SI).
_ASTIG_REF_FLOOR_MM = 1e-9

#: Target kinds and the fields each one requires.
_TARGET_FIELDS = {
    "beam_T": ("element", "target_mm", "weight"),
    "beam_S": ("element", "target_mm", "weight"),
    "astigmatism": ("element", "weight"),
    "stability_center": ("weight",),
    "waist": ("element", "target_mm", "weight"),
    "power_out": ("target_W", "weight"),
}


class MeritError(ValueError):
    """Raised when a merit target or evaluation cannot be set up."""


def validate_targets(targets):
    """Check a target list structurally (kinds, fields, positive
    targets/weights). Returns the list unchanged. Element existence is
    checked by the caller against the loaded schema."""
    if not isinstance(targets, (list, tuple)) or not targets:
        raise MeritError("targets must be a non-empty list")
    for i, t in enumerate(targets):
        if not isinstance(t, dict):
            raise MeritError("target %d is not an object" % i)
        kind = t.get("kind")
        if kind not in _TARGET_FIELDS:
            raise MeritError("target %d has unknown kind %r (expected one "
                             "of %s)" % (i, kind, ", ".join(_TARGET_FIELDS)))
        for field in _TARGET_FIELDS[kind]:
            if field not in t:
                raise MeritError("target %d (%s) is missing field %r"
                                 % (i, kind, field))
        if kind in ("beam_T", "beam_S", "waist"):
            if not (isinstance(t["target_mm"], (int, float))
                    and math.isfinite(t["target_mm"])
                    and t["target_mm"] > 0):
                raise MeritError("target %d (%s) needs a positive "
                                 "target_mm" % (i, kind))
        if kind == "power_out":
            if not (isinstance(t["target_W"], (int, float))
                    and math.isfinite(t["target_W"])
                    and t["target_W"] > 0):
                raise MeritError("target %d (power_out) needs a positive "
                                 "target_W" % i)
        w = t["weight"]
        if not (isinstance(w, (int, float)) and math.isfinite(w)
                and w >= 0):
            raise MeritError("target %d (%s) needs a non-negative finite "
                             "weight" % (i, kind))
    return targets


def _beam_entry(result, element):
    """``(w_T_mm, w_S_mm, R_T_mm, R_S_mm)`` for ``element`` in a CLI
    result, or ``None`` when the beam list is absent (unstable)."""
    beam = result.get("beam")
    if not beam:
        return None
    for entry in beam:
        if entry.get("label") == element:
            return (entry.get("w_T_mm"), entry.get("w_S_mm"),
                    entry.get("R_T_mm"), entry.get("R_S_mm"))
    return None


def _rel_term(value, target, weight):
    return weight * ((value - target) / target) ** 2


def evaluate_result(result, targets, data=None, power=None):
    """Merit of one CLI result dict.

    ``targets`` is a validated target list. ``data`` (the loaded .rez
    dict) is needed only when a ``waist`` target is present (for the
    wavelength). ``power`` is needed only when a ``power_out`` target
    is present: ``{"params": <resolve_params() output>,
    "pump_W": <incident pump power, W>, "gain_element": <label>}``.
    The power term uses analytic Mode A (``mode_a_output``) with the
    pump waist ``w_p0`` and the geometric-mean mode radius at the gain
    element -- cheap (no extra CLI call, no overlap integral), but only
    as good as the Mode A parameters. Coupling the full Mode B overlap
    solve into every merit evaluation would cost a complete power solve
    per point and is deliberately *not* done here.

    Returns ``(merit, breakdown)`` where ``breakdown`` is a list of
    ``{"kind", "element", "value", "target", "weight",
    "contribution"}`` dicts (plus a ``{"kind": "penalty", ...}`` entry
    when the point is unstable). ``value`` is the measured operand
    ``V_k`` (mm, W or dimensionless, per kind); ``None`` when the
    operand could not be measured (failed mutation).
    """
    validate_targets(targets)
    breakdown = []
    if not result.get("ok"):
        for t in targets:
            breakdown.append({"kind": t["kind"],
                              "element": t.get("element"),
                              "value": None, "target": _target_value(t),
                              "weight": t["weight"],
                              "contribution": None})
        return PENALTY_UNSTABLE, breakdown

    g_T = result.get("g_T")
    g_S = result.get("g_S")
    if g_T is None or g_S is None:
        # Single-pass schema: no stability parameters.
        if any(t["kind"] == "stability_center" for t in targets):
            raise MeritError("stability_center target needs a resonator "
                             "(SW/RR); this schema is single-pass")
    else:
        if not (math.isfinite(g_T) and math.isfinite(g_S)):
            return PENALTY_UNSTABLE, breakdown
        over = max(0.0, max(abs(g_T), abs(g_S)) - 1.0)
        if over > 0.0:
            penalty = PENALTY_BASE + PENALTY_SLOPE * over * over
            breakdown.append({"kind": "penalty", "element": None,
                              "value": max(abs(g_T), abs(g_S)),
                              "target": 1.0, "weight": None,
                              "contribution": penalty})
            return penalty, breakdown

    lam_nm = None
    if any(t["kind"] == "waist" for t in targets):
        if data is None:
            raise MeritError("waist target needs the loaded .rez data "
                             "(for the wavelength)")
        lam_nm = wavelength_nm(data)

    merit = 0.0
    for t in targets:
        kind = t["kind"]
        weight = t["weight"]
        if kind in ("beam_T", "beam_S"):
            entry = _beam_entry(result, t["element"])
            if entry is None:
                return PENALTY_UNSTABLE, breakdown
            w = entry[0] if kind == "beam_T" else entry[1]
            if w is None or not math.isfinite(w):
                return PENALTY_UNSTABLE, breakdown
            term = _rel_term(w, t["target_mm"], weight)
            breakdown.append({"kind": kind, "element": t["element"],
                              "value": w, "target": t["target_mm"],
                              "weight": weight, "contribution": term})
        elif kind == "astigmatism":
            entry = _beam_entry(result, t["element"])
            if entry is None:
                return PENALTY_UNSTABLE, breakdown
            w_T, w_S = entry[0], entry[1]
            if (w_T is None or w_S is None
                    or not math.isfinite(w_T) or not math.isfinite(w_S)):
                return PENALTY_UNSTABLE, breakdown
            d = abs(w_T - w_S)
            ref = max(max(w_T, w_S), _ASTIG_REF_FLOOR_MM)
            term = weight * (d / ref) ** 2
            breakdown.append({"kind": kind, "element": t["element"],
                              "value": d, "target": 0.0,
                              "weight": weight, "contribution": term})
        elif kind == "stability_center":
            term = weight * (g_T * g_T + g_S * g_S)
            breakdown.append({"kind": kind, "element": None,
                              "value": math.sqrt(g_T * g_T + g_S * g_S),
                              "target": 0.0, "weight": weight,
                              "contribution": term})
        elif kind == "waist":
            entry = _beam_entry(result, t["element"])
            if entry is None:
                return PENALTY_UNSTABLE, breakdown
            w_T, w_S, R_T, R_S = entry
            plane = t.get("plane", "T")
            w = w_T if plane == "T" else w_S
            R = R_T if plane == "T" else R_S
            if w is None or not math.isfinite(w):
                return PENALTY_UNSTABLE, breakdown
            try:
                w0, _z = waist_from_wr(w, R, lam_nm)
            except ValueError:
                return PENALTY_UNSTABLE, breakdown
            term = _rel_term(w0, t["target_mm"], weight)
            breakdown.append({"kind": kind, "element": t["element"],
                              "value": w0, "target": t["target_mm"],
                              "weight": weight, "contribution": term})
        elif kind == "power_out":
            if power is None:
                raise MeritError("power_out target needs the power "
                                 "context (params, pump_W, gain_element)")
            entry = _beam_entry(result, power.get("gain_element")
                                or _gain_label(power))
            if entry is None:
                return PENALTY_UNSTABLE, breakdown
            w_T, w_S = entry[0], entry[1]
            if (w_T is None or w_S is None
                    or not math.isfinite(w_T) or not math.isfinite(w_S)):
                return PENALTY_UNSTABLE, breakdown
            from .power import mode_a_output
            params = power["params"]
            w_l_m = math.sqrt(w_T * w_S) * 1e-3
            out = mode_a_output(params, power["pump_W"],
                                params["w_p0"], w_l_m)
            p_out = out["P_out"]
            term = _rel_term(p_out, t["target_W"], weight)
            breakdown.append({"kind": kind, "element": power.get(
                "gain_element") or _gain_label(power), "value": p_out,
                "target": t["target_W"], "weight": weight,
                "contribution": term})
        merit += term
    if not math.isfinite(merit):
        return PENALTY_UNSTABLE, breakdown
    return merit, breakdown


def _target_value(target):
    """The target number of a target dict (for breakdown display)."""
    if target["kind"] in ("beam_T", "beam_S", "waist"):
        return target["target_mm"]
    if target["kind"] == "power_out":
        return target["target_W"]
    return 0.0


def _gain_label(power):
    params = power.get("params") or {}
    return params.get("gain_label")


def evaluate_batch(results, targets, data=None, power=None):
    """Merits for a list of CLI results. Returns a list of
    ``(merit, breakdown)`` in the same order."""
    return [evaluate_result(r, targets, data=data, power=power)
            for r in results]
