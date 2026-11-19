"""Reverse fitting: measured external spots -> true thermal-lens D_th
(Phase 3 block 2).

The cavity output beam is measured with a Beam Profiler at 2--3
positions ``z_i`` downstream of the output mirror; this module fits
the thermal-lens dioptric power ``D_th = 1 / f_th`` (T and S solved
independently -- the planes decouple) that reproduces the measured
spots. The fit variable is ``D_th``, never ``f_th``: it avoids the
``f_th -> infinity`` singularity and matches the zone scan.

Model ``w_model(z; D_th)`` (one plane):

1. One headless-CLI evaluation at ``D_th`` (the thermal-lens ``F``
   is overridden to ``1 / D_th``) gives the intracavity beam.
2. The *transmitted* output beam is the beam *incident* on the
   output mirror: the CLI reports the previous element's exit entry,
   which sits exactly at the output mirror's plane, so its ``(w, R)``
   is the transmitted beam's ``(w, R)`` (transmission preserves both
   to first order; the mirror's own CLI entry is the *reflected*
   beam, whose ``R`` has the opposite sign -- verified: on the user's
   cavity the M4 entry has ``R = -99999.99...`` mm while the d4 exit
   has ``R = +100000.00...`` mm, same ``w``). When the output mirror
   is the first element (no preceding element), the mirror's own
   entry is used with the sign of ``R`` flipped.
3. The output-mirror substrate (a plane-parallel plate) is applied
   as ``q -> q + L/n`` (the ``ElemPlate`` matrix ``[[1, L/n], [0, 1]]``)
   when the side-car ``output_mirror`` section gives ``thickness_mm``
   and ``n``. **Without substrate data the plate is omitted and a
   warning is raised** with an error estimate (the largest relative
   spot change a nominal 6.35 mm / n=1.45 substrate would cause at
   the measurement planes -- an estimate only, clearly labelled).
4. Free-space propagation to ``z_i``: ``q -> q + z``.

``M^2``: the CLI computes the fundamental mode (``M^2 = 1``). When
the measured ``M^2`` is given, the model uses the embedded-Gaussian
wavelength ``lambda_eff = M^2 * lambda`` in the ``q`` construction
and propagation -- far-field spots then scale by ``M`` as expected.
When ``M^2`` is missing, a warning is raised and the fit reports a
bias estimate: the median ``dw/dD_th`` sensitivity at the solution,
converted to the ``D_th`` shift that an unmodelled ``M^2 = 1.2``
would produce, and the direction (toward the nearer stability-zone
boundary). A real ``M^2 > 1`` forced through an ``M^2 = 1`` model is
otherwise absorbed entirely into ``f_th``.

Fit (per plane, ``scipy.optimize.least_squares``, ``method='trf'``)::

    r_i(D_th) = (w_model(z_i; D_th) - w_meas,i) / sigma_w,
        sigma_w = 5% * w_meas,i
    r_prior(D_th) = lambda * (D_th - D_rez) / sigma_prior,
        sigma_prior = 0.5 * D_rez, lambda = 0.1

``D_th`` is bounded to the *working* common stability zone (the
``Zone_Common`` interval containing the current ``.rez`` value; see
:func:`rezeng.zones.scan_zones`). Convergence is a relative-residual
RMS below 3% (Beam Profiler spot error is typically 2--5%);
``ftol = xtol = 1e-6``. Unstable / failed model evaluations return a
large residual (10.0) instead of crashing the solver.

Identifiability warning (locked in by tests): **at least 3 points,
spanning the waist / covering both sides of the Rayleigh range**.
Two points both in the far field on the same side of the waist
measure essentially only the divergence angle -- one effective
number -- and two different ``D_th`` can give nearly identical
spots there. On the user's cavity the degeneracy is even exact:
``w0(D_th)`` is monotonic within each zone and the two zones' ranges
overlap, so a Zone I value and a Zone II value share the same output
waist (``D = 4.0 /m`` in Zone I and ``D = 9.5 /m`` in Zone II both
give ``w0 = 253 um`` at ``z0 = -0.4 mm``; their spots agree to
<0.4% at *every* ``z``). No set of external spot measurements can
distinguish such a pair -- the waist position ``z0`` sits at the
(nearly flat) output mirror for all ``D_th`` here, so point
placement alone cannot break the Zone I / Zone II tie either. What
breaks it is the fit's bounds (the working zone) plus the weak
prior toward ``D_rez``. A 2-point far-field fit then "succeeds"
(small residual) with the wrong answer. The report therefore flags
it when all measurement points lie in the far field on one side of
the waist (``|z_i - z0| > 2 * z_R`` for all ``i``), and the bounds
are always the working common zone, never the full ``D`` range.
"""

import math

import numpy as np
from scipy.optimize import least_squares

from .cli import DEFAULT_BINARY, HeadlessError, run_headless
from .qevolve import (QevolveError, beam_entry, entrance_entry,
                      q_from_wr, waist_from_q, wr_from_q)
from .rez import param_unit, param_value_si
from .solves import wavelength_nm
from .units import from_si
from .zones import scan_zones

#: Relative spot-measurement sigma (5% of the measured value).
SIGMA_W_FRAC = 0.05
#: Weak-prior weight and width (fractions of D_rez).
PRIOR_LAMBDA = 0.1
PRIOR_SIGMA_FRAC = 0.5
#: Convergence: relative-residual RMS below this.
RMS_CONVERGED = 0.03
#: Residual returned for an unstable / failed model evaluation.
BAD_RESIDUAL = 10.0
#: Far-field factor for the degeneracy warning (|z - z0| > k * z_R).
FAR_FIELD_FACTOR = 2.0
#: Nominal substrate used ONLY for the error estimate when the real
#: substrate data is missing (6.35 mm fused silica, n = 1.45).
NOMINAL_SUBSTRATE_MM = 6.35
NOMINAL_SUBSTRATE_N = 1.45
#: M^2 assumed ONLY for the bias illustration when the real M^2 is
#: unknown (never used in the fit itself).
M2_BIAS_ILLUSTRATION = 1.2
#: Relative finite-difference step for the least_squares Jacobian.
#: MUST be >= ~1e-4: the CLI prints spot radii to ~1e-6 mm, so the
#: default sqrt(eps) step (~1.5e-8) sees only quantisation noise --
#: the difference quotient is 0 at h=1e-8 and ~20x too large at
#: h=1e-7, and only converges to the true Jacobian at h >= 1e-4.
#: With the default step the solver stops after one iteration
#: believing it is optimal. 1e-3 is safely above the noise floor
#: while the model is smooth on that scale.
DIFF_STEP = 1e-3


class ReverseError(ValueError):
    """Raised when a reverse fit cannot be set up."""


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def output_mirror_q(data, result, output_label, lam_m):
    """``(q_T, q_S)`` of the *transmitted* beam at the output plane.

    Takes the beam incident on the output mirror (the previous
    element's exit entry, which is exactly at the mirror's plane).
    When the output mirror is the first element, falls back to its
    own CLI entry with the sign of ``R`` flipped (the CLI entry is
    the reflected beam). ``lam_m`` is the wavelength to build ``q``
    with (``M^2 * lambda`` when an M^2 correction is applied).
    """
    try:
        w_T, w_S, R_T, R_S = entrance_entry(data, result, output_label)
        incident = True
    except QevolveError:
        w_T, w_S, R_T, R_S = beam_entry(result, output_label)
        incident = False
    q_T = q_from_wr(w_T * 1e-3,
                    None if R_T is None
                    else (-R_T * 1e-3 if not incident else R_T * 1e-3),
                    lam_m)
    q_S = q_from_wr(w_S * 1e-3,
                    None if R_S is None
                    else (-R_S * 1e-3 if not incident else R_S * 1e-3),
                    lam_m)
    return q_T, q_S, incident


def _propagate(q, matrix):
    """``q`` through an ABCD matrix (numpy 2x2)."""
    A, B = matrix[0]
    C, D = matrix[1]
    return (A * q + B) / (C * q + D)


def model_spot(data, result, output_label, z_mm, plane, lam_m,
               substrate=None):
    """Model spot radius (mm) at ``z_mm`` downstream of the output.

    ``plane`` is ``"T"`` or ``"S"``. ``substrate`` is ``None`` or
    ``{"thickness_mm": ..., "n": ...}`` (the output-mirror substrate
    plate, applied as ``q -> q + L/n``). ``lam_m`` already carries
    any M^2 correction (``M^2 * lambda``).
    """
    q_T, q_S, _incident = output_mirror_q(data, result, output_label,
                                          lam_m)
    q = q_T if plane == "T" else q_S
    if substrate is not None:
        L_m = float(substrate["thickness_mm"]) * 1e-3
        n = float(substrate["n"])
        q = _propagate(q, np.array([[1.0, L_m / n], [0.0, 1.0]]))
    q = _propagate(q, np.array([[1.0, float(z_mm) * 1e-3], [0.0, 1.0]]))
    w_m, _R_m = wr_from_q(q, lam_m)
    return w_m * 1e3


class _ModelEvaluator(object):
    """Single-point CLI evaluation at ``D_th`` (cached).

    ``D_th`` is the dioptric power (1/m) of the thermal-lens element;
    the CLI override sets ``F = 1 / D_th`` in the parameter's own
    unit. Returns the raw CLI result dict, or ``None`` when the
    evaluation is not usable (``ok`` false or unstable).
    """

    def __init__(self, data, lens=("TL1", "F"), binary=None, timeout=None):
        self.data = data
        self.label, self.alias = lens
        self.unit = param_unit(data, self.label, self.alias)
        if self.unit is None:
            raise ReverseError("lens parameter %s.%s is not in the "
                               "schema" % (self.label, self.alias))
        self.binary = binary if binary is not None else DEFAULT_BINARY
        self.timeout = timeout
        self.cache = {}
        self.evaluations = 0
        self.cli_calls = 0

    def __call__(self, D_th):
        key = round(float(D_th), 12)
        if key in self.cache:
            return self.cache[key]
        if D_th <= 0:
            self.cache[key] = None
            return None
        f_value = from_si(1.0 / float(D_th), self.unit)
        try:
            out = run_headless(
                {"base_schema": self.data,
                 "mutations": [{"id": 0, "overrides": {
                     self.label: {self.alias: f_value}}}]},
                binary=self.binary, timeout=self.timeout)
        except HeadlessError as e:
            raise ReverseError("headless evaluation failed: %s" % (e,))
        self.cli_calls += 1
        self.evaluations += 1
        results = out.get("results") or []
        if len(results) != 1:
            raise ReverseError("headless CLI returned %d results for 1 "
                               "mutation" % len(results))
        result = results[0]
        usable = result.get("ok") and result.get("stable")
        self.cache[key] = result if usable else None
        return self.cache[key]


def working_zone_bounds(data, lens=("TL1", "F"), binary=None,
                        timeout=None, n_points=300, d_max=12.0):
    """``(lo, hi, zone_id)``: the common stable zone containing the
    current ``.rez`` working point (Brent-refined, via
    :func:`rezeng.zones.scan_zones`). Raises :class:`ReverseError`
    when the working point is outside every common stable zone.
    """
    label, alias = lens
    f_si = param_value_si(data, label, alias)
    if f_si is None or not math.isfinite(f_si) or f_si == 0:
        raise ReverseError("lens parameter %s.%s has no finite non-zero "
                           "value" % (label, alias))
    d_rez = 1.0 / f_si
    zones = scan_zones(data, lens=lens, d_max=d_max, n_points=n_points,
                       binary=binary, timeout=timeout)
    for entry in zones["zones_common"]:
        lo, hi = entry["D_range"]
        if lo <= d_rez <= hi:
            return float(lo), float(hi), entry["id"]
    raise ReverseError(
        "working point D_th=%.4f /m is outside every common stable "
        "zone %s; reverse fitting needs a stable working point"
        % (d_rez, [e["D_range"] for e in zones["zones_common"]]))


def _validate_points(points, what):
    if not isinstance(points, (list, tuple)) or len(points) < 2:
        raise ReverseError("%s needs >= 2 measurement points "
                           "(strongly recommended >= 3), got %r"
                           % (what, points))
    clean = []
    for i, p in enumerate(points):
        if isinstance(p, dict):
            z_mm = p.get("z_mm")
            w_mm = p.get("w_mm")
        elif isinstance(p, (list, tuple)) and len(p) == 2:
            z_mm, w_mm = p
        else:
            raise ReverseError("%s[%d] must be {z_mm, w_mm} or a "
                               "(z_mm, w_mm) pair, got %r"
                               % (what, i, p))
        if not (_is_number(z_mm) and _is_number(w_mm)) \
                or float(z_mm) < 0 or float(w_mm) <= 0:
            raise ReverseError("%s[%d] needs z_mm >= 0 and w_mm > 0, "
                               "got %r" % (what, i, p))
        clean.append({"z_mm": float(z_mm), "w_mm": float(w_mm)})
    return clean


def _output_beam_geometry(data, result, output_label, lam_m):
    """``(w0_T, z0_T, z_R_T, w0_S, z0_S, z_R_S)`` of the output beam.

    Waist radius (mm), waist position (mm downstream of the output
    plane; negative = waist upstream, inside the cavity) and Rayleigh
    range (mm), per plane, from the transmitted beam at the output.
    """
    q_T, q_S, _incident = output_mirror_q(data, result, output_label,
                                          lam_m)
    out = []
    for q in (q_T, q_S):
        w0_m, z_up_m = waist_from_q(q, lam_m)
        z_R_m = math.pi * w0_m ** 2 / lam_m
        out.extend([w0_m * 1e3, -z_up_m * 1e3, z_R_m * 1e3])
    return out


def fit_plane(data, points, plane, lens=("TL1", "F"),
              output_label="M4", eng=None, m2=None, substrate=None,
              zone_bounds=None, binary=None, timeout=None,
              max_nfev=200):
    """Fit ``D_th`` for one plane from measured external spots.

    ``points`` is a list of ``{"z_mm", "w_mm"}`` (or ``(z_mm, w_mm)``
    pairs) measured downstream of the output mirror. ``m2`` is the
    measured ``M^2`` of the beam (``None`` = unknown: a warning and a
    bias estimate are reported instead of a correction). ``substrate``
    is ``None`` or ``{"thickness_mm", "n"}`` for the output-mirror
    substrate; when ``None`` the side-car ``output_mirror`` section
    is used when present. ``zone_bounds`` is ``(lo, hi)`` in 1/m
    (from :func:`working_zone_bounds`); when omitted it is computed
    with a zone scan. Returns a report dict (see module docstring).
    """
    if plane not in ("T", "S"):
        raise ReverseError("plane must be 'T' or 'S', got %r" % (plane,))
    points = _validate_points(points, "points")
    from .rez import element_index
    if element_index(data, output_label) is None:
        raise ReverseError("output element %r is not in the schema"
                           % (output_label,))
    label, alias = lens
    f_si = param_value_si(data, label, alias)
    if f_si is None or not math.isfinite(f_si) or f_si == 0:
        raise ReverseError("lens parameter %s.%s has no finite non-zero "
                           "value" % (label, alias))
    d_rez = 1.0 / f_si
    if zone_bounds is None:
        lo, hi, zone_id = working_zone_bounds(
            data, lens=lens, binary=binary, timeout=timeout)
    else:
        if len(zone_bounds) == 3:
            lo, hi, zone_id = (float(zone_bounds[0]),
                               float(zone_bounds[1]), zone_bounds[2])
        else:
            lo, hi = float(zone_bounds[0]), float(zone_bounds[1])
            zone_id = None
        if not (lo < d_rez < hi):
            raise ReverseError("zone_bounds %r do not contain the "
                               "working point D_th=%.4f /m"
                               % ((lo, hi), d_rez))
    # Small inset so the solver never sits exactly on |g| = 1.
    span = hi - lo
    lo_b = lo + 1e-6 * span
    hi_b = hi - 1e-6 * span

    lam_m = wavelength_nm(data) * 1e-9
    if m2 is not None:
        if not _is_number(m2) or float(m2) < 1.0:
            raise ReverseError("m2 must be >= 1, got %r" % (m2,))
        lam_eff = float(m2) * lam_m
    else:
        lam_eff = lam_m
    if substrate is None and eng is not None:
        substrate = (eng.get("output_mirror") or None)
    if substrate is not None:
        if not (_is_number(substrate.get("thickness_mm"))
                and _is_number(substrate.get("n"))
                and float(substrate["thickness_mm"]) > 0
                and float(substrate["n"]) > 0):
            raise ReverseError("output_mirror needs positive "
                               "thickness_mm and n, got %r" % (substrate,))
        substrate = {"thickness_mm": float(substrate["thickness_mm"]),
                     "n": float(substrate["n"])}

    warnings = []
    if len(points) < 3:
        warnings.append("only %d measurement point(s): 2 points can "
                        "determine D_th in theory but are highly prone "
                        "to the far-field degeneracy (see README); use "
                        ">= 3 points spanning the waist" % len(points))
    if m2 is None:
        warnings.append("measured M^2 is unknown: the fit uses the "
                        "fundamental-mode (M^2 = 1) model, so any real "
                        "M^2 > 1 is absorbed into the fitted D_th; see "
                        "m2_bias_estimate")
    if substrate is None:
        warnings.append("output-mirror substrate data is missing: the "
                        "cavity-external propagation omits the substrate "
                        "plate; see substrate_error_estimate")

    evaluator = _ModelEvaluator(data, lens=lens, binary=binary,
                                timeout=timeout)
    sigma_prior = PRIOR_SIGMA_FRAC * d_rez

    def residuals(x):
        d_th = float(x[0])
        result = evaluator(d_th)
        if result is None:
            return [BAD_RESIDUAL] * len(points) + [
                PRIOR_LAMBDA * (d_th - d_rez) / sigma_prior]
        out = []
        for p in points:
            try:
                w_model = model_spot(data, result, output_label,
                                     p["z_mm"], plane, lam_eff,
                                     substrate=substrate)
            except (QevolveError, ValueError):
                out.append(BAD_RESIDUAL)
                continue
            out.append((w_model - p["w_mm"])
                       / (SIGMA_W_FRAC * p["w_mm"]))
        out.append(PRIOR_LAMBDA * (d_th - d_rez) / sigma_prior)
        return out

    sol = least_squares(residuals, [d_rez],
                        bounds=([lo_b], [hi_b]),
                        method="trf", ftol=1e-6, xtol=1e-6,
                        diff_step=DIFF_STEP, max_nfev=max_nfev)
    d_fit = float(sol.x[0])
    f_fit_mm = 1.0 / d_fit * 1e3
    result_fit = evaluator(d_fit)

    # --- per-point residuals at the solution --------------------------
    point_report = []
    rel_errs = []
    if result_fit is None:
        for p in points:
            point_report.append({"z_mm": p["z_mm"], "w_meas_mm": p["w_mm"],
                                 "w_model_mm": None, "rel_err": None})
        rms_rel = None
    else:
        for p in points:
            w_model = model_spot(data, result_fit, output_label,
                                 p["z_mm"], plane, lam_eff,
                                 substrate=substrate)
            rel = (w_model - p["w_mm"]) / p["w_mm"]
            rel_errs.append(rel)
            point_report.append({"z_mm": p["z_mm"],
                                 "w_meas_mm": p["w_mm"],
                                 "w_model_mm": w_model, "rel_err": rel})
        rms_rel = float(np.sqrt(np.mean(np.square(rel_errs)))) \
            if rel_errs else None

    # --- degeneracy diagnostics: waist position / Rayleigh range -----
    degeneracy = None
    geometry = None
    if result_fit is not None:
        w0_T, z0_T, z_R_T, w0_S, z0_S, z_R_S = _output_beam_geometry(
            data, result_fit, output_label, lam_eff)
        if plane == "T":
            w0, z0, z_R = w0_T, z0_T, z_R_T
        else:
            w0, z0, z_R = w0_S, z0_S, z_R_S
        geometry = {"w0_mm": w0, "z0_mm": z0, "z_R_mm": z_R}
        ratios = [abs(p["z_mm"] - z0) / z_R for p in points]
        same_side = all((p["z_mm"] - z0) > 0 for p in points) or \
            all((p["z_mm"] - z0) < 0 for p in points)
        all_far = all(r > FAR_FIELD_FACTOR for r in ratios)
        degeneracy = {"z0_mm": z0, "z_R_mm": z_R,
                      "z_over_zR": ratios,
                      "all_far_field_one_side": bool(all_far and same_side)}
        if all_far and same_side:
            warnings.append(
                "degeneracy risk: all %d point(s) are in the far field "
                "(|z - z0| > %.0f * z_R) on the same side of the waist "
                "(z0 = %.1f mm, z_R = %.1f mm); they measure almost "
                "only the divergence angle, so a different D_th (even "
                "in another stability zone) can give nearly the same "
                "spots -- add points near the waist" %
                (len(points), FAR_FIELD_FACTOR, z0, z_R))

    # --- substrate error estimate (when the data is missing) ---------
    substrate_error = None
    if substrate is None and result_fit is not None:
        nominal = {"thickness_mm": NOMINAL_SUBSTRATE_MM,
                   "n": NOMINAL_SUBSTRATE_N}
        diffs = []
        for p in points:
            w_no = model_spot(data, result_fit, output_label,
                              p["z_mm"], plane, lam_eff, substrate=None)
            w_sub = model_spot(data, result_fit, output_label,
                               p["z_mm"], plane, lam_eff,
                               substrate=nominal)
            diffs.append(abs(w_sub - w_no) / max(abs(w_no), 1e-12))
        substrate_error = {
            "max_rel_diff": float(max(diffs)) if diffs else None,
            "assumed_substrate": nominal,
            "note": "estimate only: spots recomputed with a nominal "
                    "6.35 mm / n=1.45 substrate; the fit itself used "
                    "no substrate",
        }

    # --- M^2 bias estimate (when M^2 is unknown) ---------------------
    m2_bias = None
    if m2 is None and result_fit is not None:
        h = 1e-3 * max(abs(d_fit), 1.0)
        derivs = []
        for p in points:
            r_hi = evaluator(d_fit + h)
            r_lo = evaluator(d_fit - h)
            if r_hi is None or r_lo is None:
                continue
            w_hi = model_spot(data, r_hi, output_label, p["z_mm"],
                              plane, lam_eff, substrate=substrate)
            w_lo = model_spot(data, r_lo, output_label, p["z_mm"],
                              plane, lam_eff, substrate=substrate)
            derivs.append((w_hi - w_lo) / (2.0 * h))
        if derivs:
            derivs = np.array(derivs)
            med_deriv = float(np.median(derivs))
            med_w = float(np.median([p["w_mm"] for p in points]))
            if med_deriv != 0:
                d_shift = ((M2_BIAS_ILLUSTRATION - 1.0) * med_w
                           / abs(med_deriv))
                direction = ("increasing D_th (toward D=%.4f /m, the "
                             "%s boundary of the working zone)"
                             % (hi_b, "upper") if med_deriv > 0 else
                             "decreasing D_th (toward D=%.4f /m, the "
                             "%s boundary of the working zone)"
                             % (lo_b, "lower"))
                m2_bias = {
                    "dw_dD_median_mm_per_inv_m": med_deriv,
                    "m2_assumed": M2_BIAS_ILLUSTRATION,
                    "delta_D_th_per_m": float(d_shift),
                    "direction": direction,
                    "note": "illustration only: an unmodelled M^2 of "
                            "%.1f shifts the fitted D_th by roughly "
                            "this much; the sign follows dw/dD_th at "
                            "the solution" % M2_BIAS_ILLUSTRATION,
                }

    return {
        "plane": plane,
        "lens": {"label": label, "alias": alias},
        "output_label": output_label,
        "zone": zone_id,
        "zone_bounds_D_per_m": [lo, hi],
        "D_rez_per_m": d_rez,
        "D_th_fit_per_m": d_fit,
        "F_fit_mm": f_fit_mm,
        "points": point_report,
        "rms_rel": rms_rel,
        "converged": bool(rms_rel is not None and rms_rel < RMS_CONVERGED),
        "nfev": int(sol.nfev),
        "cost": float(sol.cost),
        "evaluations": evaluator.evaluations,
        "cli_calls": evaluator.cli_calls,
        "geometry": geometry,
        "degeneracy": degeneracy,
        "substrate_error_estimate": substrate_error,
        "m2_bias_estimate": m2_bias,
        "m2_used": m2,
        "substrate_used": substrate,
        "warnings": warnings,
    }


def fit_thermal_lens(data, points_T, points_S, lens=("TL1", "F"),
                     output_label="M4", eng=None, m2_T=None, m2_S=None,
                     substrate=None, zone_bounds=None, binary=None,
                     timeout=None, max_nfev=200):
    """Fit ``D_th`` for both planes. ``points_T`` / ``points_S`` are
    measurement lists (see :func:`fit_plane`); ``m2_T`` / ``m2_S``
    are the measured ``M^2`` per plane. Returns
    ``{"T": <fit_plane report>, "S": <fit_plane report>}``. The zone
    bounds are computed once and shared by both planes.
    """
    if zone_bounds is None:
        lo, hi, zone_id = working_zone_bounds(
            data, lens=lens, binary=binary, timeout=timeout)
        zone_bounds = (lo, hi)
    out = {}
    for plane, points, m2 in (("T", points_T, m2_T),
                              ("S", points_S, m2_S)):
        report = fit_plane(data, points, plane, lens=lens,
                           output_label=output_label, eng=eng, m2=m2,
                           substrate=substrate,
                           zone_bounds=zone_bounds, binary=binary,
                           timeout=timeout, max_nfev=max_nfev)
        out[plane] = report
    return out


def synthetic_measurements(data, D_true_per_m, z_list_mm, plane,
                           noise_frac=0.0, seed=0, m2=1.0,
                           substrate=None, lens=("TL1", "F"),
                           output_label="M4", binary=None, timeout=None):
    """Generate synthetic measurements at ``D_true_per_m``.

    Evaluates the model once at the true ``D_th`` (one CLI call) and
    returns ``[{"z_mm", "w_mm"}]`` with optional relative Gaussian
    noise (``noise_frac`` of the model value, fixed ``seed``). Used
    to validate the fitter: the fit must recover ``D_true_per_m``.
    ``m2`` is the M^2 of the synthetic beam (default 1.0).
    """
    if D_true_per_m <= 0:
        raise ReverseError("D_true_per_m must be positive, got %r"
                           % (D_true_per_m,))
    lam_m = wavelength_nm(data) * 1e-9
    lam_eff = float(m2) * lam_m if m2 is not None else lam_m
    evaluator = _ModelEvaluator(data, lens=lens, binary=binary,
                                timeout=timeout)
    result = evaluator(D_true_per_m)
    if result is None:
        raise ReverseError("model evaluation at D_th=%.4f /m is "
                           "unstable/failed; pick a D_th inside a "
                           "stable zone" % (D_true_per_m,))
    rng = np.random.default_rng(seed)
    points = []
    for z_mm in z_list_mm:
        w = model_spot(data, result, output_label, float(z_mm), plane,
                       lam_eff, substrate=substrate)
        if noise_frac:
            w = w * (1.0 + float(rng.normal(0.0, noise_frac)))
        points.append({"z_mm": float(z_mm), "w_mm": float(w)})
    return points
