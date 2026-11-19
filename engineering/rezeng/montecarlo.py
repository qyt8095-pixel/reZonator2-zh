"""Monte Carlo tolerance simulation (Phase 3 block 2).

``N`` perturbed copies of a cavity are evaluated in chunked headless-CLI
batch requests (200--500 points per chunk, 2--5 CLI calls for N=1000)
and summarised statistically:

* instability probability with a **Wilson score interval** (95%) --
  even with zero unstable samples the upper bound is ~0.38% for
  N=1000, where a normal approximation would wrongly report [0, 0];
* 95% confidence intervals of spot sizes / output power from **non-
  parametric quantiles** (2.5% / 97.5%) -- the distributions are
  left-skewed near the stability edge, so ``mean +/- 1.96 sigma`` is
  wrong;
* sensitivity ranking by **Spearman rank correlation + PRCC**
  (partial rank correlation), reusing the same N samples -- no Sobol
  run (Sobol needs ``N(k+2)`` evaluations and is distorted by the
  unstable-sample truncation).

Tolerance model (side-car ``tolerances``, a list of entries)::

    {"label": "d1", "alias": "L", "kind": "length",
     "distribution": "normal", "sigma": 0.0005}        # +/-0.5 mm (SI, m)
    {"label": "M2", "alias": "R", "kind": "relative",
     "distribution": "uniform", "half_width": 0.01}   # +/-1 %
    {"label": "M2", "alias": "Alpha", "kind": "angle",
     "distribution": "rayleigh", "sigma": 0.0005}     # cone sigma 0.5 mrad
    {"label": "TL1", "alias": "F", "kind": "dioptric",
     "distribution": "normal", "sigma": 0.05}         # D_th +/-5 %

``kind`` selects how the sampled perturbation is applied:

* ``length`` -- absolute perturbation of the parameter in SI units
  (metres for ``L``, radians for angles); the base value is the
  current .rez value.
* ``relative`` -- fractional perturbation ``delta``: the parameter
  becomes ``value * (1 + delta)``. Used for curvatures ``R``.
* ``dioptric`` -- the perturbation is applied to the dioptric power
  ``D = 1/F`` (``F`` becomes ``1 / (D0 * (1 + delta))``). Sampling
  ``D`` instead of ``F`` avoids the ``F -> infinity`` singularity.
* ``angle`` -- a two-dimensional misalignment cone: the cone angle
  ``theta`` is sampled from a Rayleigh distribution with parameter
  ``sigma`` and the azimuth uniformly, giving ``(theta_x, theta_y)``
  jointly. The headless CLI only exposes one tilt parameter per
  element (``Alpha``, the in-plane tilt), so the in-plane component
  ``theta_x = theta * cos(phi)`` is applied to ``Alpha`` and the
  out-of-plane component is recorded in the sample but not applied:
  there is no S-plane tilt parameter in the .rez format, and to
  first order a mirror tilt changes the beam *position/pointing*,
  not the spot size ``w`` (which is why the block-3 Jacobian needs
  the C++ misalignment-axis mode). The marginal distribution of the
  applied component is exactly ``N(0, sigma^2)``.

Distribution defaults (when ``distribution`` is omitted) and why:

* ``relative`` / ``dioptric`` (curvatures, focal lengths) default to
  **uniform**: a procured curvature is specified as a symmetric ``+/-``
  band with no central clustering, and a plain normal would put
  unphysical weight in the tails and could flip the sign of ``R``/``F``.
  ``truncated_normal`` is the alternative when the vendor bins/centres
  the parts.
* ``length`` / ``angle`` default to **normal**: machining/assembly
  errors cluster around the nominal value.

Every tolerance variable is checked with
:func:`rezeng.rez.check_overridable` at setup (the same check the
optimizer uses): a linked/driven parameter fails fast with a clear
error instead of silently producing 1e9-style penalties for every
sample. The random seed is fixed by default (``seed=0``), so a run
is reproducible; chunking only regroups the same draws, never
re-samples them.
"""

import math

import numpy as np
from scipy.stats import rankdata, spearmanr

from .cli import DEFAULT_BINARY, HeadlessError, run_headless
from .power import (DEFAULT_N_Z, PowerError, _slices_for,
                    mean_mode_radius, mode_a_output, resolve_params)
from .qevolve import QevolveError
from .rez import check_overridable, param_unit, param_value_si
from .units import from_si

#: Default chunk size (points per CLI batch request) for N=1000.
DEFAULT_CHUNK_SIZE = 250

#: Z value for a 95% Wilson score interval.
WILSON_Z = 1.96

#: Quantiles of the 95% non-parametric confidence interval.
CI_LOW_Q = 0.025
CI_HIGH_Q = 0.975


class MonteCarloError(ValueError):
    """Raised when a Monte Carlo run cannot be set up."""


#: Valid tolerance kinds and distributions.
_KINDS = ("length", "relative", "dioptric", "angle")
_DISTRIBUTIONS = ("normal", "uniform", "truncated_normal", "rayleigh")


def wilson_interval(k, n, z=WILSON_Z):
    """Wilson score interval for ``k`` successes in ``n`` trials.

    Returns ``(lo, hi)``. For ``k = 0, n = 1000`` the upper bound is
    ~0.0038 (0.38%); a normal approximation would report [0, 0].
    For ``k = n`` the interval is symmetric to the ``k = 0`` case.
    """
    if n <= 0:
        raise MonteCarloError("wilson_interval needs n > 0, got %r" % (n,))
    if not (0 <= k <= n):
        raise MonteCarloError("wilson_interval needs 0 <= k <= n, got "
                              "k=%r, n=%r" % (k, n))
    p = float(k) / float(n)
    denom = 1.0 + z * z / n
    centre = p + z * z / (2.0 * n)
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    lo = max(0.0, (centre - margin) / denom)
    hi = min(1.0, (centre + margin) / denom)
    return lo, hi


def _is_pos_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) > 0)


def _validate_tolerances(data, tolerances):
    """Normalise tolerance entries; returns a list of variable dicts.

    Each variable is ``{"label", "alias", "kind", "distribution",
    "sigma", "half_width", "base_si", "unit"}``. ``sigma`` /
    ``half_width`` are in the perturbation's natural units: SI for
    ``length``/``angle``, fractions for ``relative``/``dioptric``.
    """
    if not isinstance(tolerances, (list, tuple)) or not tolerances:
        raise MonteCarloError("tolerances must be a non-empty list, got "
                              "%r" % (tolerances,))
    variables = []
    for i, entry in enumerate(tolerances):
        if not isinstance(entry, dict):
            raise MonteCarloError("tolerances[%d] is not an object: %r"
                                  % (i, entry))
        label = entry.get("label")
        alias = entry.get("alias")
        kind = entry.get("kind")
        if not label or not alias:
            raise MonteCarloError("tolerances[%d] needs label and alias: "
                                  "%r" % (i, entry))
        if kind not in _KINDS:
            raise MonteCarloError("tolerances[%d] kind must be one of %s, "
                                  "got %r" % (i, ", ".join(_KINDS), kind))
        conflict = check_overridable(data, label, alias)
        if conflict is not None:
            raise MonteCarloError(
                "tolerance variable %s.%s cannot be overridden: %s"
                % (label, alias, conflict))
        base_si = param_value_si(data, label, alias)
        if base_si is None or not math.isfinite(base_si):
            raise MonteCarloError("tolerance variable %s.%s has no finite "
                                  "value in the schema" % (label, alias))
        if kind == "dioptric" and base_si == 0:
            raise MonteCarloError("dioptric tolerance on %s.%s needs a "
                                  "non-zero focal length" % (label, alias))
        if kind == "angle" and alias != "Alpha":
            raise MonteCarloError("angle tolerance must target the Alpha "
                                  "parameter, got %s.%s" % (label, alias))
        distribution = entry.get("distribution")
        if distribution is None:
            distribution = ("uniform" if kind in ("relative", "dioptric")
                            else "normal")
        if distribution not in _DISTRIBUTIONS:
            raise MonteCarloError(
                "tolerances[%d] distribution must be one of %s, got %r"
                % (i, ", ".join(_DISTRIBUTIONS), distribution))
        if distribution == "rayleigh" and kind != "angle":
            raise MonteCarloError(
                "rayleigh distribution only applies to kind 'angle', "
                "got kind %r" % (kind,))
        if kind == "angle" and distribution not in ("rayleigh", "normal"):
            raise MonteCarloError(
                "angle tolerances use 'rayleigh' (2D cone) or 'normal' "
                "(in-plane only), got %r" % (distribution,))
        sigma = entry.get("sigma")
        half_width = entry.get("half_width")
        if distribution in ("normal", "truncated_normal", "rayleigh"):
            if sigma is None or not _is_pos_number(sigma):
                raise MonteCarloError(
                    "tolerances[%d] (%s) needs a positive sigma, got %r"
                    % (i, distribution, sigma))
        if distribution in ("uniform", "truncated_normal"):
            if half_width is None or not _is_pos_number(half_width):
                raise MonteCarloError(
                    "tolerances[%d] (%s) needs a positive half_width, "
                    "got %r" % (i, distribution, half_width))
        variables.append({
            "label": label, "alias": alias, "kind": kind,
            "distribution": distribution,
            "sigma": float(sigma) if sigma is not None else None,
            "half_width": float(half_width)
            if half_width is not None else None,
            "base_si": float(base_si),
            "unit": param_unit(data, label, alias),
        })
    return variables


def _draw_delta(rng, variable, n):
    """``(applied, extra)`` for one variable: ``n`` perturbations.

    ``applied`` is the value added to (length/angle, SI) or multiplied
    into (relative/dioptric, fraction) the base value. ``extra`` is a
    dict of per-sample diagnostics (cone angle / out-of-plane tilt
    for ``kind == 'angle'``), or ``None``.
    """
    dist = variable["distribution"]
    sigma = variable["sigma"]
    half = variable["half_width"]
    if dist == "normal":
        return rng.normal(0.0, sigma, size=n), None
    if dist == "uniform":
        return rng.uniform(-half, half, size=n), None
    if dist == "truncated_normal":
        out = np.empty(n)
        filled = 0
        while filled < n:
            batch = rng.normal(0.0, sigma, size=(n - filled) * 2 + 10)
            keep = batch[np.abs(batch) <= half]
            take = min(len(keep), n - filled)
            out[filled:filled + take] = keep[:take]
            filled += take
        return out, None
    # rayleigh: 2D cone, azimuth uniform.
    theta = rng.rayleigh(sigma, size=n)
    phi = rng.uniform(0.0, 2.0 * math.pi, size=n)
    applied = theta * np.cos(phi)
    extra = {"cone_rad": theta, "theta_y_rad": theta * np.sin(phi)}
    return applied, extra


def sample_perturbations(variables, n, seed=0):
    """Draw ``n`` perturbations for normalised ``variables``.

    Returns ``(samples, draws)``: ``samples`` is a list of ``n``
    dicts ``{"overrides": {label: {alias: value_in_original_unit}},
    "values_si": {(label, alias): value_si}, "extra": {...},
    "feasible": bool}``; ``draws`` is the ``(n, k)`` array of applied
    perturbations in natural units (SI for length/angle, fractions
    for relative/dioptric), one column per variable. Samples whose
    perturbed value violates the CLI guards (``L < 1e-6 m``,
    ``R/F == 0``, ``D_th <= 0``) are marked ``"feasible": False``
    and carry no overrides; the caller skips the CLI call for them.
    """
    from .optimizer import MIN_LENGTH_SI
    rng = np.random.default_rng(seed)
    k = len(variables)
    draws = np.zeros((n, k))
    extras = [None] * k
    for j, var in enumerate(variables):
        applied, extra = _draw_delta(rng, var, n)
        draws[:, j] = applied
        extras[j] = extra
    samples = []
    for i in range(n):
        values_si = {}
        extra = {}
        feasible = True
        for j, var in enumerate(variables):
            base = var["base_si"]
            delta = float(draws[i, j])
            if var["kind"] == "length":
                value = base + delta
            elif var["kind"] == "relative":
                value = base * (1.0 + delta)
            elif var["kind"] == "dioptric":
                d_new = (1.0 / base) * (1.0 + delta)
                if d_new <= 0:
                    feasible = False
                    value = base
                else:
                    value = 1.0 / d_new
            else:  # angle
                value = base + delta
                if extras[j] is not None:
                    key = "%s.%s" % (var["label"], var["alias"])
                    extra[key + "_cone_rad"] = float(
                        extras[j]["cone_rad"][i])
                    extra[key + "_theta_y_rad"] = float(
                        extras[j]["theta_y_rad"][i])
            if var["alias"] == "L" and value < MIN_LENGTH_SI:
                feasible = False
            if var["alias"] in ("R", "F") and value == 0.0:
                feasible = False
            values_si[(var["label"], var["alias"])] = float(value)
        overrides = {}
        if feasible:
            for (label, alias), value in values_si.items():
                unit = next(v["unit"] for v in variables
                            if v["label"] == label and v["alias"] == alias)
                overrides.setdefault(label, {})[alias] = float(
                    from_si(value, unit))
        samples.append({"overrides": overrides, "values_si": values_si,
                        "extra": extra, "feasible": feasible})
    return samples, draws


def _prcc(X, y):
    """Partial rank correlation coefficients of columns of ``X`` vs ``y``.

    Rank-transforms ``X`` and ``y``, then for each column regresses
    both the column's ranks and ``y``'s ranks on all *other* columns'
    ranks (least squares with an intercept) and correlates the
    residuals. Returns an array of PRCC values (``nan`` where the
    residuals are degenerate, e.g. a constant column).
    """
    X = np.asarray(X, dtype=float)
    y = np.asarray(y, dtype=float)
    n, k = X.shape
    Xr = np.apply_along_axis(rankdata, 0, X)
    yr = rankdata(y)
    ones = np.ones((n, 1))
    out = np.full(k, np.nan)
    for j in range(k):
        # A constant input column carries no information: PRCC is
        # undefined (the rank regression would otherwise return a
        # meaningless finite value from fitting a constant).
        if np.std(X[:, j]) == 0:
            continue
        others = np.delete(Xr, j, axis=1)
        design = np.hstack([ones, others])
        try:
            beta_x, _r, _rk, _sv = np.linalg.lstsq(design, Xr[:, j],
                                                  rcond=None)
            beta_y, _r, _rk, _sv = np.linalg.lstsq(design, yr, rcond=None)
        except np.linalg.LinAlgError:
            continue
        res_x = Xr[:, j] - design @ beta_x
        res_y = yr - design @ beta_y
        if np.std(res_x) == 0 or np.std(res_y) == 0:
            continue
        out[j] = float(np.corrcoef(res_x, res_y)[0, 1])
    return out


def _spearman(x, y):
    """Spearman rho, or ``None`` when either side is constant."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return None
    if not (np.isfinite(x).all() and np.isfinite(y).all()):
        return None
    rho = spearmanr(x, y).statistic
    return None if rho is None or not math.isfinite(rho) else float(rho)


def _clean(value):
    """``None`` for nan/non-finite values, else the float."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _quantile_ci(values):
    """``(median, lo, hi)`` non-parametric 95% interval of ``values``."""
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return None, None, None
    return (float(np.median(arr)),
            float(np.quantile(arr, CI_LOW_Q)),
            float(np.quantile(arr, CI_HIGH_Q)))


def _mode_a_for_sample(data, result, params, p_pump_W, sample):
    """Mode A output (W) for one stable MC sample, or ``None``."""
    gain_label = params["gain_label"]
    f_m = sample["values_si"].get((gain_label, "F"))
    try:
        slices = _slices_for(data, result, params, DEFAULT_N_Z,
                             F_m=f_m)
    except (QevolveError, ValueError, KeyError):
        return None
    if slices.get("exit_rel_err", 0.0) > 1e-3:
        return None
    w_l = mean_mode_radius(slices)
    try:
        return float(mode_a_output(params, p_pump_W, params["w_p0"],
                                   w_l)["P_out"])
    except (PowerError, ValueError):
        return None


def run_montecarlo(data, tolerances, n=1000, chunk_size=DEFAULT_CHUNK_SIZE,
                   seed=0, watch=("M1", "M4"), eng=None,
                   progress=None, binary=None, timeout=None):
    """Run a Monte Carlo tolerance simulation. Returns a report dict::

        {"n": int, "n_completed": int, "n_failed": int,
         "n_unstable": int, "n_stable": int,
         "p_unstable": float, "wilson_95": [lo, hi],
         "variables": [...], "seed": int, "chunk_size": int,
         "n_cli_calls": int, "interrupted": bool,
         "watch": {"M1": {"w_T_mm": {"median", "ci95": [lo, hi],
                                     "n": int}, ...}},
         "power": {"status": "ok"/"nodata", "P_out_W": {...},
                   "P_out_stable_W": {...}, "P_pump_W": float,
                   "reason": str},
         "sensitivity": [{"variable", "kind", "distribution",
                          "spearman_w", "prcc_w", "spearman_P_out",
                          "prcc_P_out", "spearman_stable",
                          "prcc_stable"}],
         "warnings": [...]}

    ``watch`` spot statistics cover stable samples only (unstable
    samples have no beam). ``power.P_out_W`` covers *all* completed,
    non-failed samples with unstable samples counted as 0 (per the
    review); ``P_out_stable_W`` covers stable samples only.
    Sensitivity is ranked by ``|PRCC|`` against the watched spot size
    (first watch element, T plane); every output's coefficients are
    reported. ``progress(done, total)`` is called after each chunk
    and may return ``False`` to stop early (the report then has
    ``interrupted: True`` and covers only the completed chunks).
    """
    if n <= 0:
        raise MonteCarloError("n must be positive, got %r" % (n,))
    if not (1 <= chunk_size <= 1000):
        raise MonteCarloError("chunk_size must be in [1, 1000], got %r"
                              % (chunk_size,))
    variables = _validate_tolerances(data, tolerances)
    samples, draws = sample_perturbations(variables, n, seed=seed)
    labels = {e.get("label") for e in data.get("elements", [])}
    for label in watch:
        if label not in labels:
            raise MonteCarloError("watch element %r is not in the schema"
                                  % (label,))

    # --- optional Mode A power (resolved once; nodata on any gap) ----
    power_params = None
    p_pump_W = None
    power_reason = None
    if eng is not None:
        pump = (eng.get("gain_and_pump") or {}).get("pump") or {}
        if pump.get("P_pump_W") is not None:
            try:
                power_params = resolve_params(data, eng)
                p_pump_W = float(pump["P_pump_W"])
            except PowerError as e:
                power_reason = str(e)
        else:
            power_reason = ("gain_and_pump.pump.P_pump_W is missing, so "
                            "no output power is computed")
    else:
        power_reason = "no side-car given, so no output power is computed"

    results = [None] * n
    n_cli_calls = 0
    interrupted = False
    for start in range(0, n, chunk_size):
        chunk = samples[start:start + chunk_size]
        batch = [(i, s) for i, s in enumerate(chunk, start=start)
                 if s["feasible"]]
        if batch:
            mutations = [{"id": k, "overrides": s["overrides"]}
                         for k, (_i, s) in enumerate(batch)]
            try:
                out = run_headless(
                    {"base_schema": data, "mutations": mutations},
                    binary=binary or DEFAULT_BINARY, timeout=timeout)
            except HeadlessError as e:
                raise MonteCarloError("headless evaluation failed: %s"
                                      % (e,))
            returned = out.get("results") or []
            if len(returned) != len(batch):
                raise MonteCarloError(
                    "headless CLI returned %d results for %d mutations"
                    % (len(returned), len(batch)))
            n_cli_calls += 1
            for (_i, _s), result in zip(batch, returned):
                results[_i] = result
        if progress is not None:
            try:
                keep_going = progress(start + len(chunk), n)
            except Exception:
                keep_going = False
            if keep_going is False:
                interrupted = True
                break

    # --- per-sample summary ------------------------------------------
    n_completed = sum(1 for r in results if r is not None)
    n_failed = 0
    n_unstable = 0
    stable_idx = []
    watch_values = {label: {"w_T": [], "w_S": []} for label in watch}
    p_out_by_index = {}
    warnings = []
    for i, result in enumerate(results):
        if result is None:
            continue  # interrupted before this chunk
        if not result.get("ok"):
            n_failed += 1
            continue
        if not result.get("stable"):
            n_unstable += 1
            p_out_by_index[i] = 0.0
            continue
        stable_idx.append(i)
        beam = result.get("beam") or []
        by_label = {e.get("label"): e for e in beam
                    if isinstance(e, dict)}
        for label in watch:
            entry = by_label.get(label)
            if entry is None:
                warnings.append("sample %d: no beam entry for %s"
                                % (i, label))
                continue
            watch_values[label]["w_T"].append(entry.get("w_T_mm"))
            watch_values[label]["w_S"].append(entry.get("w_S_mm"))
        if power_params is not None:
            p_out = _mode_a_for_sample(data, result, power_params,
                                       p_pump_W, samples[i])
            if p_out is None:
                warnings.append("sample %d: power solve failed" % (i,))
                p_out_by_index[i] = 0.0
            else:
                p_out_by_index[i] = p_out
    n_stable = len(stable_idx)
    n_ok = n_completed - n_failed
    p_unstable = (n_unstable / n_ok) if n_ok else 0.0
    wilson = wilson_interval(n_unstable, n_ok) if n_ok else (0.0, 1.0)

    watch_report = {}
    for label in watch:
        entry = {}
        for plane in ("w_T", "w_S"):
            values = [v for v in watch_values[label][plane]
                      if v is not None and math.isfinite(v)]
            median, lo, hi = _quantile_ci(values)
            entry[plane + "_mm"] = {"median": median,
                                    "ci95": [lo, hi], "n": len(values)}
        watch_report[label] = entry

    if power_params is not None:
        p_all = [p_out_by_index[i] for i in sorted(p_out_by_index)]
        p_stable = [p_out_by_index[i] for i in stable_idx
                    if i in p_out_by_index]
        p_med, p_lo, p_hi = _quantile_ci(p_all)
        s_med, s_lo, s_hi = _quantile_ci(p_stable)
        power_report = {
            "status": "ok",
            "P_pump_W": p_pump_W,
            "P_out_W": {"median": p_med, "ci95": [p_lo, p_hi],
                        "n": len(p_all)},
            "P_out_stable_W": {"median": s_med, "ci95": [s_lo, s_hi],
                               "n": len(p_stable)},
        }
    else:
        power_report = {"status": "nodata", "reason": power_reason}

    # --- sensitivity (Spearman + PRCC) -------------------------------
    # w-sensitivity uses stable samples only (unstable samples have
    # no beam); P_out and stability use all completed, non-failed
    # samples (unstable P_out = 0).
    sensitivity = []
    done_idx = [i for i, r in enumerate(results)
                if r is not None and r.get("ok")]
    if done_idx:
        X_all = draws[done_idx, :]
        stable_flag = np.array([1.0 if results[i].get("stable") else 0.0
                                for i in done_idx])
        y_p = np.array([p_out_by_index.get(i, 0.0) for i in done_idx],
                       dtype=float)
        X_s = draws[stable_idx, :] if stable_idx else np.zeros((0, len(variables)))
        y_w = None
        if stable_idx and watch:
            first_label = watch[0]
            y_w = np.array([
                next((e.get("w_T_mm") for e in (results[i].get("beam") or [])
                      if isinstance(e, dict)
                      and e.get("label") == first_label), np.nan)
                for i in stable_idx], dtype=float)
            if not np.isfinite(y_w).all():
                y_w = None
        prcc_w = _prcc(X_s, y_w) if y_w is not None \
            and len(y_w) >= 3 and np.std(y_w) > 0 else None
        prcc_p = _prcc(X_all, y_p) if np.std(y_p) > 0 else None
        prcc_s = _prcc(X_all, stable_flag) \
            if 0.0 < float(np.mean(stable_flag)) < 1.0 else None
        for j, var in enumerate(variables):
            sensitivity.append({
                "variable": "%s.%s" % (var["label"], var["alias"]),
                "kind": var["kind"],
                "distribution": var["distribution"],
                "spearman_w": _spearman(X_s[:, j], y_w)
                if y_w is not None else None,
                "prcc_w": None if prcc_w is None else _clean(prcc_w[j]),
                "spearman_P_out": _spearman(X_all[:, j], y_p),
                "prcc_P_out": None if prcc_p is None else _clean(prcc_p[j]),
                "spearman_stable": _spearman(X_all[:, j], stable_flag),
                "prcc_stable": None if prcc_s is None else _clean(prcc_s[j]),
            })
        sensitivity.sort(key=lambda s: (
            -abs(s["prcc_w"]) if s["prcc_w"] is not None else 0.0))

    return {
        "n": n, "n_completed": n_completed, "n_failed": n_failed,
        "n_unstable": n_unstable, "n_stable": n_stable,
        "p_unstable": p_unstable, "wilson_95": list(wilson),
        "variables": [{"label": v["label"], "alias": v["alias"],
                       "kind": v["kind"],
                       "distribution": v["distribution"],
                       "sigma": v["sigma"],
                       "half_width": v["half_width"],
                       "base_si": v["base_si"]}
                      for v in variables],
        "seed": seed, "chunk_size": chunk_size,
        "n_cli_calls": n_cli_calls, "interrupted": interrupted,
        "watch": watch_report, "power": power_report,
        "sensitivity": sensitivity,
        "warnings": sorted(set(warnings)),
    }
