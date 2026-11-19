"""Phase 4 block 2: thermal stress and fracture safety margin.

Plane-strain radial/tangential/axial stress from a temperature field
(Koechner's long-rod formulas), the maximum tensile stress against
the material fracture strength, and the safety margin
``1 - sigma_max/sigma_fracture``.

Formulas (``C = alpha_T*E/(1-nu)``, ``I(r) = int_0^r T(r') r' dr'``,
``I_tot = I(R0)``)::

    sigma_r(r)     = C * (I_tot/R0^2 - I(r)/r^2)
    sigma_theta(r) = C * (I_tot/R0^2 + I(r)/r^2 - T(r))
    sigma_z(r)     = C * (2*I_tot/R0^2 - T(r))

with ``I(r)/r^2 -> T(0)/2`` at ``r = 0``.  Only tensile (positive)
stress counts: brittle crystals fail in tension, not compression.
The primary stress uses the z-averaged temperature profile (the
regime the formulas were derived for); a per-slice maximum is
reported as a conservative local-peak estimate for the hot pumped
face.

Limitations (from the Phase 4 design review -- read before trusting
a margin)
--------------------------------------------
* The plane-strain formulas ignore the axial gradient ``dT/dz`` and
  underestimate the peak tensile stress at the pumped end face by
  roughly 20-40%.
* Polished-surface micro-cracks can halve the effective
  ``sigma_fracture`` versus the handbook value.
* Nd:YVO4 is anisotropic (``alpha_c ~ 2.6x alpha_a``).  The solver
  brackets the stress with ``alpha_a`` (primary) and ``alpha_c``
  (conservative bound); the verdict never relies on the optimistic
  end alone: a conservative margin below the red line caps the
  overall status at ``warn`` even when the primary value is fine.
"""

import math

import numpy as np

__all__ = [
    "FractureError", "MARGIN_FAIL", "MARGIN_WARN", "stress_from_profile",
    "stress_field", "fracture_margin", "fracture_report",
]

#: Safety margin red line (safety factor 2) and warn band.
MARGIN_FAIL = 0.50
MARGIN_WARN = 0.70


class FractureError(ValueError):
    """Raised when a fracture evaluation cannot be set up."""


def stress_from_profile(r_m, T_profile_C, alpha_T_per_K, E_Pa, nu):
    """``(sigma_r, sigma_theta, sigma_z)`` [Pa] for a radial profile.

    ``T_profile_C`` is the temperature vs radius (any consistent
    reference: only differences matter, the formulas are linear in
    ``T`` up to an additive constant that cancels -- check:
    shifting ``T`` by ``T0`` shifts ``I_tot/R0^2`` and ``I(r)/r^2``
    by ``T0/2`` and ``T(r)`` by ``T0``, so all three stresses are
    unchanged).
    """
    r = np.asarray(r_m, dtype=float)
    T = np.asarray(T_profile_C, dtype=float)
    if r.shape != T.shape or len(r) < 2:
        raise FractureError("stress_from_profile needs matching r/T "
                            "arrays with >= 2 points")
    if np.any(r < 0) or r[0] != 0.0:
        raise FractureError("radial grid must start at r = 0")
    C = float(alpha_T_per_K) * float(E_Pa) / (1.0 - float(nu))
    # Cumulative integral I(r) = int_0^r T r' dr' (trapezoid).
    rr = r
    integrand = T * rr
    I = np.zeros_like(r)
    I[1:] = np.cumsum(0.5 * (integrand[:-1] + integrand[1:])
                      * np.diff(rr))
    I_tot = I[-1]
    R0 = r[-1]
    # I(r)/r^2 with the r -> 0 limit T(0)/2.
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(r > 0, I / np.where(r > 0, r ** 2, 1.0),
                         0.5 * T[0])
    mean = I_tot / R0 ** 2
    sigma_r = C * (mean - ratio)
    sigma_theta = C * (mean + ratio - T)
    sigma_z = C * (2.0 * mean - T)
    return sigma_r, sigma_theta, sigma_z


def stress_field(T_C, r_m, z_m, alpha_T_per_K, E_Pa, nu):
    """Stress summary for a full ``T(r, z)`` field.

    Returns ``{"primary": {...}, "local_peak": {...}}`` where the
    primary value comes from the z-averaged profile and the local
    peak is the maximum over all z slices (each slice run through
    the same formulas).  Each entry holds ``sigma_max_Pa``,
    ``r_max_m``, ``z_max_m`` (``None`` for the primary value) and
    the three component maxima.
    """
    T = np.asarray(T_C, dtype=float)
    r = np.asarray(r_m, dtype=float)
    z = np.asarray(z_m, dtype=float)
    T_bar = np.trapz(T, z, axis=1) / (z[-1] - z[0])
    s_r, s_t, s_z = stress_from_profile(r, T_bar, alpha_T_per_K,
                                        E_Pa, nu)
    stack = np.vstack([s_r, s_t, s_z])
    primary = {
        "sigma_max_Pa": float(np.max(stack)),
        "r_max_m": float(r[np.unravel_index(np.argmax(stack),
                                            stack.shape)[1]]),
        "z_max_m": None,
        "sigma_r_max_Pa": float(np.max(s_r)),
        "sigma_theta_max_Pa": float(np.max(s_t)),
        "sigma_z_max_Pa": float(np.max(s_z)),
    }
    peak = {"sigma_max_Pa": -float("inf"), "r_max_m": None,
            "z_max_m": None, "sigma_r_max_Pa": -float("inf"),
            "sigma_theta_max_Pa": -float("inf"),
            "sigma_z_max_Pa": -float("inf")}
    for j in range(len(z)):
        a_r, a_t, a_z = stress_from_profile(r, T[:, j], alpha_T_per_K,
                                            E_Pa, nu)
        local = np.vstack([a_r, a_t, a_z])
        m = float(np.max(local))
        if m > peak["sigma_max_Pa"]:
            peak["sigma_max_Pa"] = m
            peak["r_max_m"] = float(
                r[np.unravel_index(np.argmax(local), local.shape)[1]])
            peak["z_max_m"] = float(z[j])
        peak["sigma_r_max_Pa"] = max(peak["sigma_r_max_Pa"],
                                     float(np.max(a_r)))
        peak["sigma_theta_max_Pa"] = max(peak["sigma_theta_max_Pa"],
                                         float(np.max(a_t)))
        peak["sigma_z_max_Pa"] = max(peak["sigma_z_max_Pa"],
                                     float(np.max(a_z)))
    return {"primary": primary, "local_peak": peak}


def fracture_margin(sigma_max_Pa, sigma_fracture_MPa):
    """``(margin, status)`` for a peak tensile stress.

    ``margin = 1 - sigma_max/sigma_fracture``; ``"fail"`` below the
    50% red line, ``"warn"`` in the 50-70% band, ``"ok"`` above.
    """
    if sigma_fracture_MPa is None or float(sigma_fracture_MPa) <= 0:
        raise FractureError("need a positive sigma_fracture_MPa")
    margin = 1.0 - float(sigma_max_Pa) / (float(sigma_fracture_MPa) * 1e6)
    if margin < MARGIN_FAIL:
        status = "fail"
    elif margin < MARGIN_WARN:
        status = "warn"
    else:
        status = "ok"
    return margin, status


def fracture_report(rod_result, material):
    """Fracture verdict for a :func:`thermal.solve_rod` result.

    ``material`` is the resolved material dict (``alpha_a_per_K`` /
    ``alpha_c_per_K``, ``E_GPa``, ``nu``, ``sigma_fracture_MPa``).
    Returns the primary (alpha_a) and conservative (alpha_c) stress
    summaries, their margins, and the overall status: ``"fail"`` when
    the primary margin is below the red line; ``"warn"`` when the
    primary is fine but the conservative bound is below the red
    line (or the primary is in the warn band); ``"ok"`` otherwise.
    """
    T = rod_result["T_C"]
    r, z = rod_result["r_m"], rod_result["z_m"]
    E_Pa = float(material["E_GPa"]) * 1e9
    nu = float(material["nu"])
    sig_f = material.get("sigma_fracture_MPa")
    if sig_f is None:
        raise FractureError("material has no sigma_fracture_MPa")
    alpha_a = material.get("alpha_a_per_K")
    alpha_c = material.get("alpha_c_per_K", alpha_a)
    if alpha_a is None:
        raise FractureError("material has no alpha_a_per_K")
    out = {}
    for name, alpha in (("alpha_a", alpha_a), ("alpha_c", alpha_c)):
        field = stress_field(T, r, z, alpha, E_Pa, nu)
        prim = field["primary"]["sigma_max_Pa"]
        peak = field["local_peak"]["sigma_max_Pa"]
        worst = max(prim, peak)
        margin, status = fracture_margin(worst, sig_f)
        out[name] = {
            "stress": field,
            "sigma_max_Pa": worst,
            "sigma_max_MPa": worst * 1e-6,
            "sigma_primary_MPa": prim * 1e-6,
            "sigma_local_peak_MPa": peak * 1e-6,
            "margin": margin,
            "status": status,
        }
    primary_status = out["alpha_a"]["status"]
    conservative_status = out["alpha_c"]["status"]
    if primary_status == "fail" or conservative_status == "fail":
        # A conservative failure does not by itself fail the design
        # (the isotropic bound is pessimistic), but it caps the
        # verdict at "warn" unless the primary value also fails.
        overall = "fail" if primary_status == "fail" else "warn"
    elif primary_status == "warn" or conservative_status == "warn":
        overall = "warn"
    else:
        overall = "ok"
    out["status"] = overall
    out["sigma_fracture_MPa"] = float(sig_f)
    out["note"] = (
        "each direction reports the z-averaged primary value and the "
        "per-slice local peak; the verdict uses the larger of the "
        "two. alpha_a is the optimistic direction, alpha_c the "
        "conservative bound. Plane strain underestimates the "
        "pumped-face peak by ~20-40%% and surface micro-cracks can "
        "halve sigma_fracture; keep margin above the 50%% red line.")
    return out
