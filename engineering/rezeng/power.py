"""Power solver: mode A (Rigrod), mode B (3D overlap integral),
thermal-lens closed loop, P_out-P_pump / T_opt scans, higher-order-mode
criterion.

Physics (spec section 4.2.1; Gemini Phase 2 review, milestones 1-2):

- Saturation intensity ``I_sat = h*nu_l / (sigma_em * tau_f)`` (laser
  frequency). In a standing-wave cavity the saturation denominator is
  ``1 + (I_+ + I_-) / I_sat = 1 + 2*P_circ*phi_0 / I_sat`` -- the
  factor 2 is essential; dropping it doubles the slope efficiency.
- Mode A (Rigrod, engineering fast model)::

      P_th = pi*h*nu_p*(w_p^2 + w_l^2) / (4*sigma*tau_f*eta_p*eta_abs)
             * (T_oc + L_i)                              [incident pump]
      P_out = T_oc/(T_oc+L_i) * eta_q*eta_abs*eta_mode*(P_pump - P_th)
      eta_q = lambda_p / lambda_l

  ``eta_mode`` defaults to the *derived* Gaussian overlap value
  ``w_l^2*(w_l^2 + 2*w_p^2) / (w_p^2 + w_l^2)^2`` (the differential
  slope at threshold of the distributed model); for a top-hat pump
  ``tanh(w_p^2/w_l^2) * w_l^2/w_p^2``. Passing an explicit ``eta_mode``
  in the side-car overrides it.
- Mode B solves the self-consistent round-trip equation for the
  one-way circulating power ``P_circ``::

      (2*sigma*tau_f*P_abs / (h*nu_p*delta)) * O(P_circ) = 1,
      O(P) = int int r_p(r,z)*phi_0(r,z) / (1 + 2*P*phi_0/I_sat) dV,
      P_out = T_oc * P_circ,   delta = T_oc + L_i.

  ``r_p`` is the normalised pump distribution (volume integral 1),
  ``phi_0`` the normalised elliptical-Gaussian mode (area integral 1
  per slice). ``w_T(z)`` / ``w_S(z)`` come from the q(z) evolver
  (:mod:`rezeng.qevolve`); the pump radius ``w_p(z)`` from its waist,
  position and ``M_p^2``. The radial integral uses 2D Gauss-Hermite
  quadrature (Gaussian pump) or polar Gauss-Legendre (top-hat pump);
  the axial integral uses Gauss-Legendre slices.
- Thermal lens: ``1/F_th(P) = 1/F_0 + kappa_th*eta_abs*P_pump`` with
  ``kappa_th`` from (in order) an explicit value, a calibration point
  (``F_ref`` @ ``P_ref``), reverse anchoring (current ``.rez`` ``F``
  assumed at ``P_nom``), or a physics estimate
  ``kappa ~ eta_h*(dn/dT) / (2*pi*K_c*w_p^2)``. The native element has
  a single ``F`` (T/S share it), so the CLI mutation uses the mean
  dioptric power when ``kappa_T != kappa_S``.
- Higher-order modes: after solving ``P_circ`` for TEM_00, the
  round-trip gain exponent of TEM_10 / TEM_01 in the *remaining*
  (TEM_00-saturated) inversion is evaluated; net gain > 0 marks the
  multimode threshold. ``M^2`` is estimated from a nested two-mode
  balance (each HOM solved against TEM_00 so both sit at threshold).

All powers are watts, all lengths SI (metres) inside this module.
"""

import math

import numpy as np
from scipy.optimize import brentq

from .cli import run_headless
from .eng import load_eng
from .qevolve import (QevolveError, crystal_slices, element_grin_params,
                      find_gain_element)
from .rez import (check_overridable, element_index, param_obj, param_unit,
                  set_param_value)
from .units import from_si, to_si

H_PLANCK = 6.62607015e-34      # J s
C_LIGHT = 299792458.0          # m/s

#: Default quadrature sizes (accuracy vs speed; see tests).
DEFAULT_N_Z = 24               # axial Gauss-Legendre slices
DEFAULT_N_GH = 12              # Gauss-Hermite nodes per transverse axis
DEFAULT_N_R = 20               # radial Gauss-Legendre nodes (top-hat)
DEFAULT_N_THETA = 16           # angular nodes (top-hat)

#: Quantum-defect limit for 808 nm -> 1064 nm (hard physical ceiling).
QUANTUM_LIMIT_808_1064 = 808.0 / 1064.0


class PowerError(ValueError):
    """Raised when a power computation cannot be set up."""


# --- Quadrature caches ----------------------------------------------------

_GH_CACHE = {}
_GL_CACHE = {}


def _gh_nodes(n):
    if n not in _GH_CACHE:
        x, w = np.polynomial.hermite.hermgauss(n)
        _GH_CACHE[n] = (x, w)
    return _GH_CACHE[n]


def _gl_nodes(n):
    if n not in _GL_CACHE:
        _GL_CACHE[n] = np.polynomial.legendre.leggauss(n)
    return _GL_CACHE[n]


def _z_nodes_weights(L_m, n_z):
    """Gauss-Legendre nodes/weights on ``[0, L]`` (metres)."""
    x, w = _gl_nodes(n_z)
    return 0.5 * L_m * (x + 1.0), 0.5 * L_m * w


# --- Parameter resolution ---------------------------------------------------

#: Side-car gain_and_pump layout (see engineering/README.md).
_GAIN_DEFAULTS = {
    "pump": {"lambda_p_nm": None, "w_p0_um": None, "z_p0_mm": 0.0,
             "M2_p": 1.0, "eta_p": 1.0, "profile": "gaussian",
             "P_pump_W": None},
    "crystal": {"material": None, "sigma_em_cm2": None, "tau_f_us": None,
                "alpha_p_per_cm": None},
    "cavity": {"T_oc": None, "L_i": None, "eta_mode": None},
    "thermal": {"F0_mm": None, "kappa_th_per_W": None,
                "kappa_th_T_per_W": None, "kappa_th_S_per_W": None,
                "anchor_F_ref_mm": None, "anchor_P_ref_W": None,
                "P_nom_W": None, "eta_h": 0.24, "dn_dT_per_K": 3.0e-6,
                "K_c_W_per_mK": 5.1},
}


def _pos(value, what):
    if value is None or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) or float(value) <= 0:
        raise PowerError("%s must be a positive number, got %r"
                         % (what, value))
    return float(value)


def _nonneg(value, what):
    if value is None or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) or float(value) < 0:
        raise PowerError("%s must be a non-negative number, got %r"
                         % (what, value))
    return float(value)


def resolve_params(data, eng):
    """Resolve all power-solver parameters to SI, from ``.rez`` + side-car.

    Returns a dict with SI values, the gain element label, and a
    ``warnings`` list. Missing *essential* data raises :class:`PowerError`
    naming the missing field (nothing is invented); missing optional
    data is filled from the documented defaults and noted in warnings.
    """
    warnings = []
    gp = (eng or {}).get("gain_and_pump") or {}
    if not isinstance(gp, dict):
        raise PowerError("gain_and_pump section is not an object")
    pump = gp.get("pump") or {}
    crystal = gp.get("crystal") or {}
    cavity = gp.get("cavity") or {}
    thermal = gp.get("thermal") or {}
    for name, section in (("pump", pump), ("crystal", crystal),
                          ("cavity", cavity), ("thermal", thermal)):
        if not isinstance(section, dict):
            raise PowerError("gain_and_pump.%s is not an object" % name)

    from .solves import wavelength_nm
    lambda_l_m = wavelength_nm(data) * 1e-9
    gain_label = find_gain_element(data, eng)
    L_m, n0, _gT, _gS = element_grin_params(data, gain_label)

    lambda_p_nm = _pos(pump.get("lambda_p_nm"), "pump.lambda_p_nm")
    lambda_p_m = lambda_p_nm * 1e-9
    sigma_em = _pos(crystal.get("sigma_em_cm2"),
                    "crystal.sigma_em_cm2") * 1e-4
    tau_f = _pos(crystal.get("tau_f_us"), "crystal.tau_f_us") * 1e-6
    alpha_p = _pos(crystal.get("alpha_p_per_cm"),
                   "crystal.alpha_p_per_cm") * 100.0
    w_p0 = _pos(pump.get("w_p0_um"), "pump.w_p0_um") * 1e-6
    z_p0 = float(pump.get("z_p0_mm", 0.0) or 0.0) * 1e-3
    Mp2 = _pos(pump.get("M2_p", 1.0), "pump.M2_p")
    eta_p = _pos(pump.get("eta_p", 1.0), "pump.eta_p")
    profile = str(pump.get("profile", "gaussian")).lower()
    if profile not in ("gaussian", "tophat"):
        raise PowerError("pump.profile must be 'gaussian' or 'tophat', "
                         "got %r" % (profile,))
    T_oc = cavity.get("T_oc")
    if T_oc is None or not isinstance(T_oc, (int, float)) \
            or not (0 < float(T_oc) < 1):
        raise PowerError("cavity.T_oc must be a fraction in (0, 1), got %r"
                         % (T_oc,))
    L_i = cavity.get("L_i")
    if L_i is None or not isinstance(L_i, (int, float)) \
            or not (0 <= float(L_i) < 1):
        raise PowerError("cavity.L_i must be a fraction in [0, 1), got %r"
                         % (L_i,))
    eta_mode = cavity.get("eta_mode")
    if eta_mode is not None:
        eta_mode = _pos(eta_mode, "cavity.eta_mode")
        if eta_mode > 1.0:
            raise PowerError("cavity.eta_mode must be <= 1, got %r"
                             % (eta_mode,))

    eta_abs = 1.0 - math.exp(-alpha_p * L_m)
    nu_l = C_LIGHT / lambda_l_m
    nu_p = C_LIGHT / lambda_p_m
    I_sat = H_PLANCK * nu_l / (sigma_em * tau_f)
    params = {
        "gain_label": gain_label, "L_m": L_m, "n0": n0,
        "lambda_l_m": lambda_l_m, "lambda_p_m": lambda_p_m,
        "sigma_em": sigma_em, "tau_f": tau_f, "alpha_p": alpha_p,
        "w_p0": w_p0, "z_p0": z_p0, "Mp2": Mp2, "eta_p": eta_p,
        "profile": profile, "T_oc": float(T_oc), "L_i": float(L_i),
        "eta_mode": eta_mode, "eta_abs": eta_abs,
        "eta_q": lambda_p_m / lambda_l_m,
        "I_sat": I_sat,
        "thermal": dict(thermal),
        "warnings": warnings,
    }
    params["F_current_m"] = param_F_current(data, gain_label)
    return params


def param_F_current(data, gain_label):
    """Current focal length (m) of the gain element from the .rez file."""
    from .rez import param_value_si
    F_m = param_value_si(data, gain_label, "F")
    if F_m is None:
        raise PowerError("gain element %r has no F parameter"
                         % (gain_label,))
    return float(F_m)


# --- Mode A (Rigrod) --------------------------------------------------------

def overlap_eta_mode(w_p_m, w_l_m, profile="gaussian"):
    """Differential-slope overlap efficiency ``eta_mode``.

    Closed form for the distributed Gaussian model (exact tangent at
    threshold); for a top-hat pump the corresponding area-ratio form.
    Both are 1 when the mode is much larger than the pump and fall as
    the pump overfills the mode.
    """
    if w_p_m <= 0 or w_l_m <= 0:
        raise PowerError("waists must be positive: w_p=%r, w_l=%r"
                         % (w_p_m, w_l_m))
    if profile == "tophat":
        rho2 = (w_p_m / w_l_m) ** 2
        return math.tanh(rho2) * (w_l_m / w_p_m) ** 2
    return (w_l_m ** 2 * (w_l_m ** 2 + 2.0 * w_p_m ** 2)
            / (w_p_m ** 2 + w_l_m ** 2) ** 2)


def mean_mode_radius(slices):
    """Effective circular mode radius in the crystal (m): z-average of
    ``sqrt(w_T * w_S)`` over the slices."""
    w = np.sqrt(np.asarray(slices["w_T_m"]) * np.asarray(slices["w_S_m"]))
    return float(np.mean(w))


def mode_a_threshold(params, w_p_m, w_l_m):
    """Rigrod threshold, *incident* pump power (W)."""
    eta_abs = params["eta_abs"]
    return (math.pi * H_PLANCK * (C_LIGHT / params["lambda_p_m"])
            * (w_p_m ** 2 + w_l_m ** 2)
            * (params["T_oc"] + params["L_i"])
            / (4.0 * params["sigma_em"] * params["tau_f"]
               * params["eta_p"] * eta_abs))


def mode_a_output(params, P_pump_inc_W, w_p_m, w_l_m):
    """Mode A output. Returns ``{P_out, P_th, slope, eta_mode}`` (W)."""
    eta_mode = params["eta_mode"]
    if eta_mode is None:
        eta_mode = overlap_eta_mode(w_p_m, w_l_m, params["profile"])
    P_th = mode_a_threshold(params, w_p_m, w_l_m)
    slope = (params["T_oc"] / (params["T_oc"] + params["L_i"])
             * params["eta_q"] * params["eta_abs"] * eta_mode)
    P_out = slope * (P_pump_inc_W - P_th) if P_pump_inc_W > P_th else 0.0
    return {"P_out": P_out, "P_th": P_th, "slope": slope,
            "eta_mode": eta_mode,
            "below_threshold": P_pump_inc_W <= P_th}


# --- Overlap integral (mode B core) -----------------------------------------

def pump_radius(params, z_m):
    """Pump 1/e^2 radius (m) at crystal depth ``z_m`` (numpy array)."""
    z_Rp = math.pi * params["w_p0"] ** 2 / (params["Mp2"]
                                            * params["lambda_p_m"])
    return params["w_p0"] * np.sqrt(1.0 + ((z_m - params["z_p0"]) / z_Rp) ** 2)


def _phi0_grid(w_T, w_S, u, v):
    """Normalised TEM_00 intensity on the Gauss-Hermite grid.

    ``u = sqrt(2)*x/w_T``, ``v = sqrt(2)*y/w_S``; returns
    ``phi_0`` (1/m^2) with the Gaussian factor kept explicit so the
    caller can use it as the quadrature weight.
    """
    return (2.0 / (math.pi * w_T * w_S)) * np.exp(-u ** 2 - v ** 2)


def overlap_integral(params, slices, P_circ, mode=(0, 0), sat_modes=None,
                     n_gh=DEFAULT_N_GH, n_r=DEFAULT_N_R,
                     n_theta=DEFAULT_N_THETA):
    """``O = int r_p * phi_mode / (1 + sum 2*P_k*phi_k / I_sat) dV``.

    ``slices`` is a :func:`qevolve.crystal_slices` dict; ``mode`` is the
    numerator Hermite-Gaussian ``(m, n)`` (only ``(0,0)``, ``(1,0)``,
    ``(0,1)`` supported); ``sat_modes`` is the list of ``(mode, P_W)``
    saturating the gain (default ``[(mode, P_circ)]`` for the
    single-mode equation). Returns ``O`` in 1/m^2.
    """
    if sat_modes is None:
        sat_modes = [(mode, P_circ)]
    z = np.asarray(slices["z_m"], dtype=float)
    w_T = np.asarray(slices["w_T_m"], dtype=float)
    w_S = np.asarray(slices["w_S_m"], dtype=float)
    L_m = slices["L_m"]
    alpha = params["alpha_p"]
    I_sat = params["I_sat"]
    w_p = pump_radius(params, z)
    if alpha * L_m > 1e-12:
        zp = alpha * np.exp(-alpha * z) / (1.0 - math.exp(-alpha * L_m))
    else:
        zp = np.full_like(z, 1.0 / L_m)
    # Axial weights: Gauss-Legendre when the caller passed GL nodes
    # (``slices["w_z"]``), else midpoint weights from the node spacing.
    w_z = slices.get("w_z")
    if w_z is None:
        w_z = np.gradient(z)
        w_z[0] = z[1] - z[0] if len(z) > 1 else L_m
        w_z[-1] = z[-1] - z[-2] if len(z) > 1 else L_m
    total = 0.0
    if params["profile"] == "gaussian":
        u, gu = _gh_nodes(n_gh)
        U, V = np.meshgrid(u, u, indexing="ij")
        GW = np.outer(gu, gu)
        for k in range(len(z)):
            wT, wS, wp = w_T[k], w_S[k], w_p[k]
            # phi_0 on the grid (without the Gaussian factor, which is
            # the quadrature weight): phi_0 = C * exp(-u^2-v^2).
            C0 = 2.0 / (math.pi * wT * wS)
            denom = np.ones_like(U)
            for (sm, sP) in sat_modes:
                if sP == 0:
                    continue
                poly = _poly_factor(sm, U, V)
                denom = denom + (2.0 * sP / I_sat) * C0 * poly \
                    * np.exp(-U ** 2 - V ** 2)
            poly_num = _poly_factor(mode, U, V)
            # r_p * phi_mode / (1+...) integrated over (x, y):
            # dx dy = (wT*wS/2) du dv; the exp(-u^2-v^2) of phi is the
            # GH weight, so the summand keeps only the pump Gaussian.
            pump_gauss = np.exp(-(wT ** 2 * U ** 2
                                  + wS ** 2 * V ** 2) / wp ** 2)
            summand = GW * pump_gauss * poly_num / denom
            # int r_p phi dA = [2*zp/(pi^2*wp^2)] * sum  (the
            # exp(-u^2-v^2) of phi_0 is the Gauss-Hermite weight).
            total += (w_z[k] * zp[k] * 2.0 / (math.pi ** 2 * wp ** 2)
                      * np.sum(summand))
    else:  # top-hat pump: polar Gauss-Legendre in r, uniform in theta
        r_x, r_w = _gl_nodes(n_r)
        thetas = (np.arange(n_theta) + 0.5) * (2.0 * math.pi / n_theta)
        dtheta = 2.0 * math.pi / n_theta
        for k in range(len(z)):
            wT, wS, wp = w_T[k], w_S[k], w_p[k]
            r = 0.5 * wp * (r_x + 1.0)
            rw = 0.5 * wp * r_w
            X = r[:, None] * np.cos(thetas)[None, :]
            Y = r[:, None] * np.sin(thetas)[None, :]
            phi0 = (2.0 / (math.pi * wT * wS)) * np.exp(
                -2.0 * X ** 2 / wT ** 2 - 2.0 * Y ** 2 / wS ** 2)
            denom = np.ones_like(phi0)
            for (sm, sP) in sat_modes:
                if sP == 0:
                    continue
                denom = denom + (2.0 * sP / I_sat) \
                    * _phi_mode(sm, phi0, X, Y, wT, wS)
            phi_num = _phi_mode(mode, phi0, X, Y, wT, wS)
            # r_p = 1/(pi wp^2) * zp inside r < wp
            integrand = (phi_num / denom) * r[:, None]
            total += (w_z[k] * zp[k] / (math.pi * wp ** 2)
                      * np.sum(rw[:, None] * integrand) * dtheta)
    return float(total)


def _poly_factor(mode, U, V):
    """Polynomial factor of a Hermite-Gaussian mode on the GH grid
    (``phi_mn = phi_00 * poly``): (0,0)->1, (1,0)->2u^2, (0,1)->2v^2.

    The factor is ``(1/2) * H_1(u)^2`` with ``H_1(u) = 2u`` and
    ``u = sqrt(2)*x/w``: ``phi_10 = phi_00 * 4*x^2/w^2 = phi_00 * 2u^2``.
    (An earlier version used 4u^2, which double-counts the mode power:
    ``int phi_10 dA`` would be 2 instead of 1. Caught by the
    small-signal HOM threshold check.)"""
    if mode == (0, 0):
        return np.ones_like(U)
    if mode == (1, 0):
        return 2.0 * U ** 2
    if mode == (0, 1):
        return 2.0 * V ** 2
    raise PowerError("unsupported mode %r (only (0,0), (1,0), (0,1))"
                     % (mode,))


def _phi_mode(mode, phi0, X, Y, w_T, w_S):
    """Hermite-Gaussian intensity ``phi_mn`` from ``phi_00`` on a grid.

    ``phi_10 = phi_00 * 4*x^2/w_T^2`` (see :func:`_poly_factor`)."""
    if mode == (0, 0):
        return phi0
    if mode == (1, 0):
        return phi0 * (4.0 * X ** 2 / w_T ** 2)
    if mode == (0, 1):
        return phi0 * (4.0 * Y ** 2 / w_S ** 2)
    raise PowerError("unsupported mode %r (only (0,0), (1,0), (0,1))"
                     % (mode,))


# --- Mode B solve -------------------------------------------------------------

def solve_p_circ(params, slices, P_abs_W, delta, n_gh=DEFAULT_N_GH,
                 n_r=DEFAULT_N_R, n_theta=DEFAULT_N_THETA):
    """Self-consistent one-way circulating power (W) for mode B.

    Solves ``(2*sigma*tau_f*P_abs / (h*nu_p*delta)) * O(P) = 1`` by
    Brent. Returns ``{P_circ, P_out, P_th_abs, converged, evaluations,
    below_threshold}``. Below threshold ``P_circ = 0`` (not an error).
    """
    K = (2.0 * params["sigma_em"] * params["tau_f"] * P_abs_W
         / (H_PLANCK * (C_LIGHT / params["lambda_p_m"]) * delta))

    def O(P):
        return overlap_integral(params, slices, P, n_gh=n_gh, n_r=n_r,
                                n_theta=n_theta)

    evals = [0]

    def F(P):
        evals[0] += 1
        return K * O(P) - 1.0

    O0 = O(0.0)
    evals[0] += 1
    P_th_abs = delta * H_PLANCK * (C_LIGHT / params["lambda_p_m"]) \
        / (2.0 * params["sigma_em"] * params["tau_f"] * O0) \
        if O0 > 0 else float("inf")
    if F(0.0) <= 0:
        return {"P_circ": 0.0, "P_out": 0.0, "P_th_abs": P_th_abs,
                "converged": True, "evaluations": evals[0],
                "below_threshold": True}
    lo, hi = 0.0, max(P_abs_W, 1.0)
    while F(hi) > 0:
        hi *= 2.0
        if hi > 1e7:
            raise PowerError("mode B solve did not bracket a root below "
                             "1e7 W (P_abs=%r)" % (P_abs_W,))
    P_circ = brentq(F, lo, hi, xtol=1e-9, rtol=1e-12, maxiter=100)
    return {"P_circ": float(P_circ),
            "P_out": float(params["T_oc"] * P_circ),
            "P_th_abs": P_th_abs, "converged": True,
            "evaluations": evals[0], "below_threshold": False}


def small_signal_gain(params, slices, P_abs_W, n_gh=DEFAULT_N_GH,
                      n_r=DEFAULT_N_R, n_theta=DEFAULT_N_THETA):
    """Round-trip small-signal gain exponent ``Gamma_0`` (dimensionless)
    at ``P_circ = 0``: ``Gamma_0 = (2*sigma*tau_f*P_abs/(h*nu_p)) * O(0)``.
    Threshold is ``Gamma_0 = delta``.
    """
    K0 = (2.0 * params["sigma_em"] * params["tau_f"] * P_abs_W
          / (H_PLANCK * (C_LIGHT / params["lambda_p_m"])))
    return K0 * overlap_integral(params, slices, 0.0, n_gh=n_gh, n_r=n_r,
                                 n_theta=n_theta)


def analytic_overlap(w_p_m, w_l_m):
    """Small-signal overlap ``O_0`` (1/m^2) for uniform Gaussian pump and
    mode along z: ``2 / (pi*(w_p^2 + w_l^2))``."""
    return 2.0 / (math.pi * (w_p_m ** 2 + w_l_m ** 2))


# --- Higher-order modes ---------------------------------------------------------

def higher_order_gains(params, slices, P_abs_W, P_circ, delta,
                       n_gh=DEFAULT_N_GH, n_r=DEFAULT_N_R,
                       n_theta=DEFAULT_N_THETA):
    """Round-trip gain exponents of TEM_10 / TEM_01 in the TEM_00-
    saturated inversion, and their net gains vs the round-trip loss.

    Returns ``{G10, G01, net10, net01}`` (dimensionless exponents).
    """
    K0 = (2.0 * params["sigma_em"] * params["tau_f"] * P_abs_W
          / (H_PLANCK * (C_LIGHT / params["lambda_p_m"])))
    out = {}
    for mode, key in (((1, 0), "10"), ((0, 1), "01")):
        O_mn = overlap_integral(params, slices, P_circ, mode=mode,
                                sat_modes=[((0, 0), P_circ)],
                                n_gh=n_gh, n_r=n_r, n_theta=n_theta)
        G = K0 * O_mn
        out["G" + key] = G
        out["net" + key] = G - delta
    return out


def two_mode_m2(params, slices, P_abs_W, delta, P_00,
                n_gh=DEFAULT_N_GH, n_r=DEFAULT_N_R, n_theta=DEFAULT_N_THETA):
    """Estimate ``M^2`` from a nested two-mode balance.

    For each HOM separately, solve the HOM power ``P_mn`` such that
    both TEM_00 and the HOM sit at threshold (``Gamma = delta``) with
    the shared saturation ``1 + (2*P_00*phi_00 + 2*P_mn*phi_mn)/I_sat``.
    Returns ``{M2_x, M2_y, P_10, P_01, method, warnings}``. Falls back
    to the gain-margin heuristic when the nested solve fails.
    """
    K0 = (2.0 * params["sigma_em"] * params["tau_f"] * P_abs_W
          / (H_PLANCK * (C_LIGHT / params["lambda_p_m"])))

    def gamma(mode, sat_modes):
        O = overlap_integral(params, slices, 0.0, mode=mode,
                             sat_modes=sat_modes, n_gh=n_gh, n_r=n_r,
                             n_theta=n_theta)
        return K0 * O

    warnings = []
    powers = {}
    for mode, key in (((1, 0), "10"), ((0, 1), "01")):
        net = gamma(mode, [((0, 0), P_00)]) - delta
        if net <= 0:
            powers[key] = 0.0
            continue
        # Inner: P_00(P_mn) from Gamma_00 = delta.
        def p00_for(p_mn):
            def f00(p00):
                return gamma((0, 0), [((0, 0), p00), (mode, p_mn)]) - delta
            if f00(0.0) <= 0:
                return None
            hi = max(P_00, 1.0)
            while f00(hi) > 0:
                hi *= 2.0
                if hi > 1e7:
                    return None
            return brentq(f00, 0.0, hi, xtol=1e-9, rtol=1e-12,
                          maxiter=100)

        def outer(p_mn):
            p00 = p00_for(p_mn)
            if p00 is None:
                return None
            return gamma(mode, [((0, 0), p00), (mode, p_mn)]) - delta

        try:
            if outer(0.0) is None or outer(0.0) <= 0:
                raise ValueError("HOM already below threshold")
            hi = max(P_00, 1.0)
            while True:
                val = outer(hi)
                if val is None or val < 0:
                    break
                hi *= 2.0
                if hi > 1e7:
                    raise ValueError("no bracket for HOM power")
            p_mn = brentq(outer, 0.0, hi, xtol=1e-9, rtol=1e-12,
                          maxiter=60)
            powers[key] = float(p_mn)
        except (ValueError, RuntimeError) as e:
            warnings.append("two-mode solve for TEM_%s failed (%s); "
                            "using gain-margin heuristic" % (key, e))
            # Heuristic: HOM fraction from the gain margin.
            frac = net / (net + delta)
            powers[key] = frac * P_00 / max(1.0 - frac, 1e-9)
    p10, p01 = powers.get("10", 0.0), powers.get("01", 0.0)
    total = P_00 + p10 + p01
    f10 = p10 / total if total > 0 else 0.0
    f01 = p01 / total if total > 0 else 0.0
    return {"M2_x": 1.0 + 2.0 * f10, "M2_y": 1.0 + 2.0 * f01,
            "P_10": p10, "P_01": p01, "P_00": P_00,
            "method": "two-mode balance" if not warnings else "heuristic",
            "warnings": warnings}


def multimode_threshold(points):
    """Pump power (W) where a HOM net gain first crosses zero, from a
    pump-scan point list (linear interpolation between bracketing
    points). Returns ``(P_mm_W, mode)`` or ``(None, None)``."""
    for key in ("net10", "net01"):
        prev = None
        for pt in points:
            if pt.get("status") != "ok":
                prev = None
                continue
            net = pt.get(key)
            if net is None:
                prev = None
                continue
            if prev is not None and prev[1] <= 0 < net:
                p0, n0 = prev
                p1 = pt["P_pump_W"]
                frac = (0.0 - n0) / (net - n0) if net != n0 else 0.0
                return p0 + frac * (p1 - p0), key
            prev = (pt["P_pump_W"], net)
    return None, None


# --- Thermal lens ---------------------------------------------------------------

def thermal_kappa(params):
    """``(kappa_T, kappa_S, source, warnings, F0_m)`` in 1/(m*W).

    Resolution order: explicit kappa -> calibration anchor
    (``F_ref`` @ ``P_ref``) -> reverse anchoring (current ``.rez`` ``F``
    assumed at ``P_nom``) -> physics estimate
    ``eta_h*(dn/dT)/(2*pi*K_c*w_p^2)`` -> no thermal model (kappa 0).
    ``F0_m`` is the cold focal length (``inf`` when unset).
    """
    thermal = params["thermal"]
    warnings = []
    eta_abs = params["eta_abs"]
    F0 = thermal.get("F0_mm")
    F0_m = float("inf") if F0 is None else float(F0) * 1e-3
    kappa = thermal.get("kappa_th_per_W")
    kappa_T = thermal.get("kappa_th_T_per_W")
    kappa_S = thermal.get("kappa_th_S_per_W")
    if kappa_T is not None or kappa_S is not None:
        base = float(kappa) if kappa is not None else None
        kT = float(kappa_T) if kappa_T is not None else base
        kS = float(kappa_S) if kappa_S is not None else base
        if kT is None or kS is None:
            raise PowerError("thermal kappa_T/kappa_S need a value or "
                             "kappa_th_per_W")
        return kT, kS, "explicit kappa_th", warnings, F0_m
    if kappa is not None:
        return float(kappa), float(kappa), "explicit kappa_th", warnings, \
            F0_m
    F_ref = thermal.get("anchor_F_ref_mm")
    P_ref = thermal.get("anchor_P_ref_W")
    if F_ref is not None and P_ref is not None:
        F_ref_m = float(F_ref) * 1e-3
        k = (1.0 / F_ref_m - (0.0 if math.isinf(F0_m) else 1.0 / F0_m)) \
            / (eta_abs * float(P_ref))
        return k, k, "calibration anchor F_ref=%.4g mm @ P_ref=%.4g W" \
            % (F_ref, P_ref), warnings, F0_m
    P_nom = thermal.get("P_nom_W")
    if P_nom is not None:
        F_cur = params["F_current_m"]
        k = (1.0 / F_cur - (0.0 if math.isinf(F0_m) else 1.0 / F0_m)) \
            / (eta_abs * float(P_nom))
        warnings.append("thermal lens reverse-anchored: assumes the "
                        "current .rez F=%.4g mm corresponds to "
                        "P_pump=%.4g W (no calibration point given)"
                        % (F_cur * 1e3, P_nom))
        return k, k, "reverse anchor at P_nom=%.4g W" % (P_nom,), \
            warnings, F0_m
    # Physics estimate only when the user actually supplied all three
    # material numbers -- no invented defaults (missing fields mean
    # "no thermal model", not a silent Nd:YVO4 guess).
    eta_h = thermal.get("eta_h")
    dn_dT = thermal.get("dn_dT_per_K")
    K_c = thermal.get("K_c_W_per_mK")
    if eta_h is not None and dn_dT is not None and K_c is not None:
        k = float(eta_h) * float(dn_dT) \
            / (2.0 * math.pi * float(K_c) * params["w_p0"] ** 2)
        warnings.append("thermal kappa from physics estimate "
                        "(eta_h*dn/dT/(2*pi*K_c*w_p^2)); treat as "
                        "order-of-magnitude")
        return k, k, "physics estimate", warnings, F0_m
    warnings.append("no thermal model data: focal length held fixed at "
                    "the .rez value")
    return 0.0, 0.0, "fixed F", warnings, F0_m


def thermal_focal_lengths(params, P_pump_inc_W):
    """``(F_T_m, F_S_m, F_cli_m, source, warnings)`` at a pump power.

    ``F_cli_m`` is the single focal length for the CLI mutation (mean
    dioptric power when T and S differ -- the native element has one
    ``F``). With no thermal model (source ``"fixed F"``) the focal
    length is held at the current ``.rez`` value at every pump power.
    At zero dioptric power (e.g. zero pump with ``F0 = inf``) the
    true ``F`` is infinite, which JSON cannot carry, so ``1e6`` m is
    used (optically negligible).
    """
    kT, kS, source, warnings, F0_m = thermal_kappa(params)
    eta_abs = params["eta_abs"]
    if source == "fixed F":
        # No thermal model: hold the focal length at the .rez value
        # at every pump power (the warning in thermal_kappa says so).
        F_cur = params["F_current_m"]
        return F_cur, F_cur, F_cur, source, warnings
    inv_F0 = 0.0 if math.isinf(F0_m) else 1.0 / F0_m

    def _F(k):
        D = inv_F0 + k * eta_abs * P_pump_inc_W
        if D == 0:
            # No dioptric power (e.g. zero pump with F0 = inf): the
            # true F is infinite, which JSON cannot carry, so use a
            # focal length so long it is optically negligible.
            warnings.append("no thermal lens at P_pump=%.4g W; using "
                            "F=1e6 m (effectively infinite)"
                            % (P_pump_inc_W,))
            return 1e6
        return 1.0 / D

    F_T = _F(kT)
    F_S = _F(kS)
    if math.isfinite(F_T) and math.isfinite(F_S) and F_T != F_S:
        d = abs(F_T - F_S) / max(abs(F_T), abs(F_S))
        if d > 0.01:
            warnings.append("thermal lens is astigmatic (F_T=%.4g mm, "
                            "F_S=%.4g mm); CLI mutation uses the mean "
                            "dioptric power" % (F_T * 1e3, F_S * 1e3))
    inv_cli = 0.5 * ((0.0 if math.isinf(F_T) else 1.0 / F_T)
                     + (0.0 if math.isinf(F_S) else 1.0 / F_S))
    F_cli = float("inf") if inv_cli == 0 else 1.0 / inv_cli
    return F_T, F_S, F_cli, source, warnings


# --- Scans -----------------------------------------------------------------------

def _cli_batch(data, mutations, binary, timeout):
    """One headless call for a list of ``{id, overrides}`` mutations."""
    from .cli import DEFAULT_BINARY
    out = run_headless({"base_schema": data, "mutations": mutations},
                       binary=binary or DEFAULT_BINARY, timeout=timeout)
    results = out.get("results") or []
    if len(results) != len(mutations):
        raise PowerError("headless CLI returned %d results for %d "
                         "mutations" % (len(results), len(mutations)))
    return results


def _slices_for(data, result, params, n_z, F_m=None):
    """Crystal slices for one CLI result.

    ``F_m`` is the thermal focal length the CLI actually used for this
    result (the mutated value in a scan) -- the evolver must use it,
    not the base ``.rez`` value, or the exit check fails whenever the
    scan moves F away from the file value. When ``F_m`` is ``None``
    the base value is used.
    """
    import copy
    z, w = _z_nodes_weights(params["L_m"], n_z)
    if F_m is not None and param_obj(data, params["gain_label"],
                                     "F") is not None:
        data = copy.deepcopy(data)
        set_param_value(data, params["gain_label"], "F", F_m, "m")
    slices = crystal_slices(data, result, params["gain_label"], z)
    slices["w_z"] = w
    return slices


def _point_common(P_pump, F_T, F_S, F_cli):
    return {"P_pump_W": float(P_pump), "F_T_mm": F_T * 1e3,
            "F_S_mm": F_S * 1e3, "F_cli_mm": F_cli * 1e3}


def pump_scan(data, eng, pump_powers_W, T_oc=None, n_z=DEFAULT_N_Z,
              n_gh=DEFAULT_N_GH, binary=None, timeout=None,
              with_m2=False):
    """``P_out`` vs ``P_pump`` at fixed ``T_oc`` (side-car default).

    One CLI batch call evaluates all thermal-lens focal lengths; each
    point then runs the q(z) evolver + mode A + mode B + HOM gains.
    Unstable points (``stable: false``) get ``P_out = 0`` and the
    ``thermal_instability`` flag -- the scan never aborts on them.
    Returns ``{points, summary, params, warnings}``.
    """
    params = resolve_params(data, eng)
    if T_oc is not None:
        if not (0 < float(T_oc) < 1):
            raise PowerError("T_oc must be a fraction in (0, 1)")
        params["T_oc"] = float(T_oc)
    delta = params["T_oc"] + params["L_i"]
    label = params["gain_label"]
    conflict = check_overridable(data, label, "F")
    if conflict:
        raise PowerError("cannot update thermal focal length: %s" % conflict)
    F_unit = param_unit(data, label, "F")
    warnings = list(params["warnings"])
    # --- Thermal focal lengths + one batch CLI call ---
    focals = []
    for P in pump_powers_W:
        F_T, F_S, F_cli, source, w = thermal_focal_lengths(params, P)
        focals.append((F_T, F_S, F_cli))
        for msg in w:
            if msg not in warnings:
                warnings.append(msg)
    mutations = [{"id": i, "overrides": {label: {"F": from_si(F_cli, F_unit)}}}
                 for i, (_T, _S, F_cli) in enumerate(focals)]
    results = _cli_batch(data, mutations, binary, timeout)
    # --- Per-point power solve ---
    points = []
    for P, (F_T, F_S, F_cli), result in zip(pump_powers_W, focals, results):
        point = _point_common(P, F_T, F_S, F_cli)
        if not result.get("ok"):
            point.update({"status": "failed",
                          "error": result.get("error")})
            points.append(point)
            continue
        if not result.get("stable"):
            point.update({"status": "unstable", "P_out_B": 0.0,
                          "P_out_A": 0.0, "P_circ": 0.0,
                          "flag": "thermal_instability"})
            points.append(point)
            continue
        try:
            slices = _slices_for(data, result, params, n_z, F_m=F_cli)
        except (QevolveError, ValueError) as e:
            point.update({"status": "failed", "error": str(e)})
            points.append(point)
            continue
        if slices["exit_rel_err"] > 1e-6:
            warnings.append("q(z) evolver exit disagrees with CLI by "
                            "%.3g at P_pump=%.4g W (gain element %s)"
                            % (slices["exit_rel_err"], P, label))
        w_l = mean_mode_radius(slices)
        w_p = params["w_p0"]  # mode A uses the pump waist
        P_abs = params["eta_abs"] * P
        mode_a = mode_a_output(params, P, w_p, w_l)
        try:
            mode_b = solve_p_circ(params, slices, P_abs, delta, n_gh=n_gh)
        except PowerError as e:
            point.update({"status": "failed", "error": str(e)})
            points.append(point)
            continue
        hom = higher_order_gains(params, slices, P_abs,
                                 mode_b["P_circ"], delta, n_gh=n_gh)
        point.update({"status": "ok", "w_l_um": w_l * 1e6,
                      "w_p_um": w_p * 1e6,
                      "P_th_A_W": mode_a["P_th"],
                      "P_out_A": mode_a["P_out"],
                      "slope_A": mode_a["slope"],
                      "eta_mode": mode_a["eta_mode"],
                      "P_th_B_W": mode_b["P_th_abs"] / params["eta_abs"],
                      "P_circ": mode_b["P_circ"],
                      "P_out_B": mode_b["P_out"],
                      "below_threshold": mode_b["below_threshold"],
                      "evaluations": mode_b["evaluations"],
                      "exit_rel_err": slices["exit_rel_err"]})
        point.update(hom)
        points.append(point)
    summary = {"n_points": len(points),
               "n_ok": sum(1 for p in points if p.get("status") == "ok"),
               "n_unstable": sum(1 for p in points
                                 if p.get("status") == "unstable"),
               "n_failed": sum(1 for p in points
                               if p.get("status") == "failed"),
               "thermal_source": thermal_kappa(params)[2]}
    P_mm, mode_mm = multimode_threshold(points)
    summary["multimode_threshold_W"] = P_mm
    summary["multimode_mode"] = mode_mm
    if with_m2 and P_mm is not None:
        # M^2 at the highest ok pump power above the multimode threshold.
        top = [p for p in points
               if p.get("status") == "ok" and p.get("P_circ", 0) > 0]
        if top:
            pt = top[-1]
            # Re-solve slices for that point (cheap: reuse the stored
            # result is not possible here, so recompute via CLI once).
            F_cli = pt["F_cli_mm"] * 1e-3
            res = _cli_batch(data, [{"id": 0, "overrides": {
                label: {"F": from_si(F_cli, F_unit)}}}], binary, timeout)[0]
            if res.get("ok") and res.get("stable"):
                slices = _slices_for(data, res, params, n_z, F_m=F_cli)
                m2 = two_mode_m2(params, slices,
                                 params["eta_abs"] * pt["P_pump_W"],
                                 delta, pt["P_circ"], n_gh=n_gh)
                summary["M2_at_max_pump"] = m2
                summary["M2_pump_W"] = pt["P_pump_W"]
    return {"points": points, "summary": summary,
            "params": _public_params(params), "warnings": warnings}


def toc_scan(data, eng, P_pump_W, toc_values, n_z=DEFAULT_N_Z,
             n_gh=DEFAULT_N_GH, binary=None, timeout=None):
    """``P_out`` vs ``T_oc`` at fixed pump power; finds ``T_opt``.

    The cavity optics depend only on the thermal focal length at this
    pump power, so one CLI call suffices; only the loss ``delta``
    changes across the scan.
    """
    params = resolve_params(data, eng)
    label = params["gain_label"]
    conflict = check_overridable(data, label, "F")
    if conflict:
        raise PowerError("cannot update thermal focal length: %s" % conflict)
    F_unit = param_unit(data, label, "F")
    F_T, F_S, F_cli, source, warnings = thermal_focal_lengths(
        params, P_pump_W)
    warnings = list(params["warnings"]) + warnings
    results = _cli_batch(data, [{"id": 0, "overrides": {
        label: {"F": from_si(F_cli, F_unit)}}}], binary, timeout)
    result = results[0]
    points = []
    if not result.get("ok"):
        return {"points": points,
                "summary": {"status": "failed",
                            "error": result.get("error")},
                "params": _public_params(params), "warnings": warnings}
    if not result.get("stable"):
        return {"points": points,
                "summary": {"status": "unstable",
                            "flag": "thermal_instability",
                            "P_pump_W": P_pump_W},
                "params": _public_params(params), "warnings": warnings}
    slices = _slices_for(data, result, params, n_z, F_m=F_cli)
    if slices["exit_rel_err"] > 1e-6:
        warnings.append("q(z) evolver exit disagrees with CLI by %.3g "
                        "(gain element %s)"
                        % (slices["exit_rel_err"], label))
    w_l = mean_mode_radius(slices)
    w_p = params["w_p0"]  # mode A uses the pump waist
    P_abs = params["eta_abs"] * P_pump_W
    best = None
    for T_oc in toc_values:
        delta = float(T_oc) + params["L_i"]
        params_T = dict(params)
        params_T["T_oc"] = float(T_oc)
        mode_a = mode_a_output(params_T, P_pump_W, w_p, w_l)
        mode_b = solve_p_circ(params_T, slices, P_abs, delta, n_gh=n_gh)
        point = {"T_oc": float(T_oc), "delta": delta,
                 "P_th_A_W": mode_a["P_th"], "P_out_A": mode_a["P_out"],
                 "P_th_B_W": mode_b["P_th_abs"] / params["eta_abs"],
                 "P_circ": mode_b["P_circ"], "P_out_B": mode_b["P_out"],
                 "below_threshold": mode_b["below_threshold"]}
        points.append(point)
        if best is None or point["P_out_B"] > best["P_out_B"]:
            best = point
    return {"points": points,
            "summary": {"T_opt": best["T_oc"] if best else None,
                        "P_out_max_B": best["P_out_B"] if best else 0.0,
                        "P_pump_W": P_pump_W,
                        "F_cli_mm": F_cli * 1e3,
                        "thermal_source": source},
            "params": _public_params(params), "warnings": warnings}


def _public_params(params):
    """JSON-safe subset of resolved parameters (no internals)."""
    keep = ("gain_label", "L_m", "n0", "lambda_l_m", "lambda_p_m",
            "sigma_em", "tau_f", "alpha_p", "w_p0", "z_p0", "Mp2",
            "eta_p", "profile", "T_oc", "L_i", "eta_mode", "eta_abs",
            "eta_q", "I_sat", "F_current_m")
    return {k: params[k] for k in keep if k in params}
