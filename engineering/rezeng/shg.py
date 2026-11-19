"""Second-harmonic generation (SHG): intracavity / extracavity.

Physics (spec section 4.2.1 module 2 / appendix ``nonlinear_shg``;
Gemini Phase 2 review section 5; milestone 2):

- Single-pass conversion (Boyd-Kleinman, focused Gaussian)::

      P_2w = K * P_w^2,   eta_small = K * P_w,
      K = 16*pi^2 * d_eff^2 * L_eff / (eps0 * c * n_w^2 * n_2w * lam_w^3)
          * h(0, xi) * sinc^2(Delta k * L / 2)          [1/W]
      xi = L_eff * lam_w / (2*pi*w0^2)                    (focusing)
      h(0, xi) = arctan(xi)^2 / xi                       (B = 0)
      L_eff = min(L_cryst, L_a),  L_a = pi * w0 / rho     (walk-off)

  The prefactor is verified two independent ways (see
  ``tests/test_shg.py``): in the collimated limit (xi -> 0, h -> xi)
  it reproduces exactly the plane-wave result
  ``P_2w = (8*pi*d^2*L^2/(eps0*c*n^2*n_2w*lam^2*w^2)) * P_w^2``
  derived from
  ``I_2w = (2*w^2*d^2*L^2/(eps0*c^3*n^2*n_2w)) * I_w^2``.
  ``h(0, xi)`` peaks at ~0.65 for xi ~ 1.4 (L ~ 2.8 * z_R, waist
  centred in the crystal). (The often-quoted 1.068 belongs to a
  different normalisation of h -- h' = 2*h with half the prefactor;
  the product K is what matters, and it is the plane-wave limit that
  pins it down.)
- Depletion: ``eta_1pass(P) = tanh^2(sqrt(K * P))`` (exact plane-wave
  depleted solution; reduces to K*P for K*P << 1, saturates at 1).
- Intracavity (SW cavity, two passes per round trip)::

      delta_SHG(P_circ) = 2 * eta_1pass(P_circ)
      P_2w = 2 * P_circ * eta_1pass(P_circ)   (green, both directions)

  Self-consistent equation -- a nested single-variable root solver,
  never relaxation iteration (which oscillates at high conversion)::

      F(P) = Gamma(P) - [delta_linear + delta_SHG(P)] = 0
      Gamma(P) = (2*sigma*tau_f*P_abs/(h*nu_p)) * O(P)   (mode B)

  ``Gamma`` decreases with P and the loss increases with P, so the
  root is unique; ``scipy.optimize.brentq`` finds it in ~10
  evaluations. Below threshold ``P_circ = 0`` (not an error).
- Extracavity: the fundamental is solved first (mode B, no SHG
  feedback), then one pass: ``P_2w = P_out * eta_1pass(P_out)``.
- The SHG crystal must be an ``ElemPlate`` in the .rez (a real
  dielectric slab: C++ matrix ``[[1, L/n], [0, 1]]``). reZonator's
  ``ElemMediumRange`` ignores ``n`` in its matrix (it behaves like
  empty space), so it is rejected with an explicit error -- see
  :func:`resolve_shg`. The beam inside the crystal comes from the
  q(z) evolver (:mod:`rezeng.qevolve`); the focusing parameter uses
  the waist of the crystal's beam segment (or the mean radius when
  the waist lies outside the crystal).
- Walk-off ellipticity is diagnostic only (never feeds back into the
  fundamental ABCD): ``w_2w,|| ~ sqrt((w_w/2)^2 + (rho*L/2)^2)``.
- Green noise (Green Problem): heuristic risk bands on eta_1pass,
  see :func:`green_noise_assessment` -- qualitative, not sharp
  thresholds.

Scope of this block: SW oscillator cavities only (the mode B solver
is a standing-wave solver). RR/SP topologies are deferred to the
MOPA block.

All powers are watts, all lengths SI (metres) inside this module.
"""

import copy
import math

import numpy as np
from scipy.optimize import brentq

from .power import (H_PLANCK, C_LIGHT, DEFAULT_N_GH, DEFAULT_N_R,
                    DEFAULT_N_THETA, DEFAULT_N_Z, PowerError,
                    overlap_integral, resolve_params, solve_p_circ,
                    mode_a_output, mean_mode_radius, thermal_focal_lengths,
                    thermal_kappa, _cli_batch, _slices_for,
                    _z_nodes_weights)
from .qevolve import (QevolveError, crystal_slices, element_grin_params,
                      entrance_entry, q_from_wr, waist_from_q)
from .rez import (check_overridable, element_index, elements,
                  param_unit, param_value_si, set_param_value)
from .solves import wavelength_nm
from .units import from_si

EPS0 = 8.8541878128e-12    # F/m (vacuum permittivity)

#: Focusing function h(0, xi) peaks here (L ~ 2.8 * z_R).
XI_OPT = 1.39

#: Green-noise risk bands on the single-pass conversion efficiency
#: (heuristic rules of thumb -- see green_noise_assessment()).
GREEN_NOISE_ELEVATED = 0.05
GREEN_NOISE_HIGH = 0.15

#: Temperature-mismatch shape: sinc^2(x) = 0.5 at x = 1.3916 (the
#: FWHM point of the temperature tuning curve).
SINC_HALF = 1.391557982


class SHGError(ValueError):
    """Raised when an SHG computation cannot be set up."""


# --- Material reference data -------------------------------------------------
# Typical literature values at 1064 nm -> 532 nm. These are REFERENCE
# numbers only: resolve_shg() never applies them silently. A side-car
# that omits d_eff / n_omega / n_2omega / walk-off reports an error
# naming the missing field; use fill_typical() explicitly (demo/tests)
# to build an example section from this table. Verify every value
# against the crystal's datasheet before using it for a real design.

MATERIALS = {
    "LBO": {"n_omega": 1.60, "n_2omega": 1.61, "d_eff_pm_V": 0.85,
            "walkoff_mrad": 7.2, "temp_acceptance_C_cm": 4.0,
            "notes": "type I CPM walk-off 7.2 mrad (spec appendix); "
                     "NCPM (90 deg, ~150 C) temperature acceptance "
                     "~4 degC*cm (typical)"},
    "BBO": {"n_omega": 1.66, "n_2omega": 1.67, "d_eff_pm_V": 2.0,
            "walkoff_mrad": 55.0, "temp_acceptance_C_cm": None,
            "notes": "type I, large walk-off (typical ~55 mrad); "
                     "NCPM is not practical for BBO"},
    "KTP": {"n_omega": 1.85, "n_2omega": 1.86, "d_eff_pm_V": 3.5,
            "walkoff_mrad": 4.5, "temp_acceptance_C_cm": 25.0,
            "notes": "type II, small walk-off (typical ~4.5 mrad); "
                     "large temperature acceptance (typical)"},
    "PPLN": {"n_omega": 2.16, "n_2omega": 2.23, "d_eff_pm_V": 14.0,
             "walkoff_mrad": 0.0, "temp_acceptance_C_cm": 1.0,
             "notes": "quasi-phase-matched (periodically poled): "
                     "no walk-off by construction; narrow temperature "
                     "acceptance (typical ~1 degC*cm)"},
}


def material_reference(material):
    """Typical values for ``material`` (a copy of the table entry).

    Reference data only -- never applied silently by the solver.
    Raises :class:`SHGError` for an unknown material.
    """
    entry = MATERIALS.get(str(material))
    if entry is None:
        raise SHGError("unknown SHG material %r (known: %s)"
                       % (material, sorted(MATERIALS)))
    return dict(entry)


def fill_typical(shg):
    """Return ``shg`` with missing material fields filled from the
    reference table (explicit, visible -- for demos and quick starts).

    Only fills fields that are absent; never overrides a value the
    user gave. ``walkoff_mrad`` is filled only for CPM (NCPM keeps
    rho = 0). Raises :class:`SHGError` for an unknown material.
    """
    out = dict(shg or {})
    material = out.get("material")
    if material is None:
        return out
    ref = material_reference(material)
    for key in ("n_omega", "n_2omega", "d_eff_pm_V"):
        if out.get(key) is None:
            out[key] = ref[key]
    if out.get("phase_matching") == "CPM" \
            and out.get("walkoff_mrad") is None:
        out["walkoff_mrad"] = ref["walkoff_mrad"]
    if out.get("phase_matching") == "NCPM" \
            and out.get("temp_acceptance_C_cm") is None:
        out["temp_acceptance_C_cm"] = ref["temp_acceptance_C_cm"]
    return out


# --- Side-car resolution -------------------------------------------------------

#: Element types whose in-medium propagation the q(z) evolver models
#: exactly (real refraction at the faces). ElemMediumRange /
#: ElemEmptyRange are excluded on purpose: the C++ matrix of
#: ElemMediumRange is [[1, L], [0, 1]] -- it ignores n entirely.
_SHG_ELEMENT_TYPES = ("ElemPlate", "ElemGrinLens", "ElemGrinMedium",
                      "ElemThermoLens", "ElemThermoMedium")


def _pos(value, what):
    if value is None or not isinstance(value, (int, float)) \
            or not math.isfinite(float(value)) or float(value) <= 0:
        raise SHGError("%s must be a positive number, got %r"
                       % (what, value))
    return float(value)


def _sinc(x):
    """sin(x)/x with sinc(0) = 1."""
    if x == 0:
        return 1.0
    return math.sin(x) / x


def resolve_shg(data, eng):
    """Resolve the ``nonlinear_shg`` side-car section to SI.

    Returns ``None`` when the section is absent or ``enabled`` is
    false (the caller reports ``nodata`` / ``disabled``). When it is
    enabled, every essential field is required: a missing ``d_eff``,
    refractive index, crystal element or (for CPM) walk-off angle
    raises :class:`SHGError` naming the field -- nothing is invented.
    ``phase_matching`` is inferred from the walk-off angle when absent
    (walk-off > 0 -> CPM, else NCPM) and the inference is warned
    about; CPM and NCPM are kept strictly separate afterwards
    (NCPM forces rho = 0 and keeps the sinc^2(Delta k L/2) temperature
    factor; CPM requires a walk-off angle).
    """
    warnings = []
    shg = (eng or {}).get("nonlinear_shg") or {}
    if not isinstance(shg, dict):
        raise SHGError("nonlinear_shg section is not an object")
    if not shg.get("enabled", False):
        return None

    label = shg.get("crystal_element_id")
    if not label or not isinstance(label, str):
        raise SHGError("nonlinear_shg.crystal_element_id is required "
                       "(label of the crystal element in the .rez file)")
    idx = element_index(data, label)
    if idx is None:
        raise SHGError("nonlinear_shg.crystal_element_id %r is not in "
                       "the .rez file" % (label,))
    etype = elements(data)[idx].get("type")
    if etype not in _SHG_ELEMENT_TYPES:
        if etype in ("ElemMediumRange", "ElemEmptyRange"):
            raise SHGError(
                "SHG crystal element %r is %s: reZonator ignores the "
                "refractive index in that element's matrix, so the "
                "beam inside it would be wrong. Use an ElemPlate "
                "(a real dielectric slab, matrix [[1, L/n], [0, 1]])"
                % (label, etype))
        raise SHGError("SHG crystal element %r is %s, not a crystal "
                       "range/plate element" % (label, etype))

    material = shg.get("material")
    if material is not None and not isinstance(material, str):
        raise SHGError("nonlinear_shg.material must be a string, got %r"
                       % (material,))
    L_rez = param_value_si(data, label, "L")
    L_mm = shg.get("length_mm")
    if L_mm is not None:
        L_m = _pos(L_mm, "nonlinear_shg.length_mm") * 1e-3
        if L_rez is not None and abs(L_m - L_rez) / max(L_rez, 1e-12) > 0.01:
            warnings.append("nonlinear_shg.length_mm (%.4g mm) differs "
                            "from the .rez element length (%.4g mm); "
                            "using the side-car value"
                            % (L_mm, L_rez * 1e3))
    elif L_rez is not None:
        L_m = float(L_rez)
    else:
        raise SHGError("nonlinear_shg.length_mm is required (the .rez "
                       "element %r has no length either)" % (label,))
    d_eff = _pos(shg.get("d_eff_pm_V"),
                 "nonlinear_shg.d_eff_pm_V") * 1e-12
    n_w = _pos(shg.get("n_omega"), "nonlinear_shg.n_omega")
    n_2w = _pos(shg.get("n_2omega"), "nonlinear_shg.n_2omega")

    phase = shg.get("phase_matching")
    walkoff = shg.get("walkoff_mrad")
    if phase is not None:
        phase = str(phase).upper()
        if phase not in ("CPM", "NCPM"):
            raise SHGError("nonlinear_shg.phase_matching must be 'CPM' "
                           "or 'NCPM', got %r" % (phase,))
    if phase == "NCPM":
        if walkoff is not None and float(walkoff) > 0:
            raise SHGError("nonlinear_shg is NCPM but walkoff_mrad "
                           "(%r) is given: NCPM has zero walk-off by "
                           "definition -- remove walkoff_mrad or switch "
                           "to CPM" % (walkoff,))
        rho = 0.0
    elif phase == "CPM":
        if walkoff is None:
            raise SHGError("nonlinear_shg is CPM but walkoff_mrad is "
                           "missing: critical phase matching needs the "
                           "walk-off angle")
        rho = _pos(walkoff, "nonlinear_shg.walkoff_mrad") * 1e-3
    else:
        # Inferred from the walk-off angle (warned about).
        if walkoff is not None and float(walkoff) > 0:
            phase = "CPM"
            rho = _pos(walkoff, "nonlinear_shg.walkoff_mrad") * 1e-3
            warnings.append("nonlinear_shg.phase_matching not given; "
                            "inferred CPM from walkoff_mrad > 0")
        else:
            phase = "NCPM"
            rho = 0.0
            warnings.append("nonlinear_shg.phase_matching not given; "
                            "inferred NCPM (no walk-off angle)")
    walkoff_plane = str(shg.get("walkoff_plane", "T")).upper()
    if walkoff_plane not in ("T", "S"):
        raise SHGError("nonlinear_shg.walkoff_plane must be 'T' or 'S', "
                       "got %r" % (walkoff_plane,))

    mode = str(shg.get("mode", "intracavity")).lower()
    if mode not in ("intracavity", "extracavity"):
        raise SHGError("nonlinear_shg.mode must be 'intracavity' or "
                       "'extracavity', got %r" % (mode,))

    # Phase mismatch: explicit Delta k wins; otherwise NCPM derives it
    # from the temperature detuning and the FWHM acceptance product.
    delta_k = shg.get("delta_k_per_m")
    if delta_k is not None:
        if not isinstance(delta_k, (int, float)) \
                or not math.isfinite(float(delta_k)):
            raise SHGError("nonlinear_shg.delta_k_per_m must be a number, "
                           "got %r" % (delta_k,))
        delta_k = float(delta_k)
    elif phase == "NCPM":
        dT = shg.get("delta_T_C")
        acc = shg.get("temp_acceptance_C_cm")
        if dT is None:
            delta_k = 0.0
            warnings.append("NCPM with no delta_T_C: assumed perfectly "
                            "temperature-tuned (mismatch factor 1)")
        elif acc is None:
            delta_k = 0.0
            warnings.append("NCPM delta_T_C given but no "
                            "temp_acceptance_C_cm: the mismatch cannot be "
                            "quantified, assumed perfectly phase-matched")
        else:
            dT = float(dT)
            acc_m = _pos(acc, "nonlinear_shg.temp_acceptance_C_cm") * 1e-2
            # Delta k * L / 2 = SINC_HALF * dT * L / (acceptance product):
            # at dT * L = acceptance product the curve is at half maximum.
            delta_k = 2.0 * SINC_HALF * dT / acc_m
    else:  # CPM, angle-tuned
        delta_k = 0.0
    mismatch = _sinc(delta_k * L_m / 2.0) ** 2

    lam_w_m = wavelength_nm(data) * 1e-9
    lam_2w_nm = shg.get("wavelength_2omega_nm")
    lam_2w_m = lam_w_m / 2.0 if lam_2w_nm is None \
        else _pos(lam_2w_nm, "nonlinear_shg.wavelength_2omega_nm") * 1e-9
    return {"mode": mode, "crystal_label": label, "material": material,
            "phase_matching": phase, "L_m": L_m, "d_eff": d_eff,
            "n_omega": n_w, "n_2omega": n_2w, "rho": rho,
            "walkoff_plane": walkoff_plane, "delta_k_per_m": delta_k,
            "mismatch": mismatch, "lambda_w_m": lam_w_m,
            "lambda_2w_m": lam_2w_m,
            "single_frequency": bool(shg.get("single_frequency", False)),
            "warnings": warnings}


# --- Boyd-Kleinman focusing / walk-off ----------------------------------------

def boyd_kleinman_h(xi):
    """Focusing factor ``h(0, xi) = arctan(xi)^2 / xi`` (B = 0).

    ``h -> xi`` for xi -> 0 (collimated / plane-wave limit),
    peaks at ~0.65 for xi ~ 1.4, and falls as ~1/xi for tight focus.
    """
    xi = float(xi)
    if xi < 0:
        raise SHGError("focusing parameter xi must be >= 0, got %r" % (xi,))
    if xi == 0:
        return 0.0
    return math.atan(xi) ** 2 / xi


def aperture_length(w0_m, rho):
    """Walk-off aperture length ``L_a = pi * w0 / rho`` (m).

    ``inf`` for rho = 0 (NCPM / no walk-off). Beyond ``L_a`` the
    fundamental and harmonic beams have separated by ~one beam
    radius, so a longer crystal adds almost no conversion.
    """
    if rho <= 0:
        return float("inf")
    return math.pi * float(w0_m) / float(rho)


def focusing_parameter(L_eff_m, lambda_w_m, w0_m):
    """``xi = L_eff * lam_w / (2 * pi * w0^2)``."""
    return float(L_eff_m) * float(lambda_w_m) \
        / (2.0 * math.pi * float(w0_m) ** 2)


def shg_coefficient_K(d_eff, L_eff_m, xi, n_w, n_2w, lambda_w_m,
                      mismatch=1.0):
    """Small-signal single-pass coefficient ``K`` [1/W].

    ``eta_small = K * P_w``; see the module docstring for the
    derivation and the plane-wave-limit verification.
    """
    K0 = (16.0 * math.pi ** 2 * float(d_eff) ** 2 * float(L_eff_m)
          / (EPS0 * C_LIGHT * float(n_w) ** 2 * float(n_2w)
             * float(lambda_w_m) ** 3))
    return K0 * boyd_kleinman_h(xi) * float(mismatch)


def single_pass_eta(K_per_W, P_w):
    """Depleted single-pass efficiency ``tanh^2(sqrt(K * P))``.

    Reduces to ``K * P`` for ``K * P << 1`` and saturates at 1.
    """
    if K_per_W < 0 or P_w < 0:
        raise SHGError("K and P must be >= 0, got %r, %r"
                       % (K_per_W, P_w))
    return math.tanh(math.sqrt(float(K_per_W) * float(P_w))) ** 2


# --- Beam inside the SHG crystal -----------------------------------------------

def shg_beam_in_crystal(data, result, label, n_z=DEFAULT_N_Z):
    """Mode radii and segment waist inside the SHG crystal.

    Uses :func:`qevolve.crystal_slices` (the exit check against the
    CLI guards the refraction convention). Returns ``{slices, w0_T_m,
    w0_S_m, waist_depth_T_m, waist_depth_S_m, w_mean_m, w_eff_m,
    waist_inside, exit_rel_err}``. ``w_eff_m`` is the circular
    equivalent waist ``sqrt(w0_T * w0_S)`` when the waist lies inside
    the crystal, else the mean mode radius in the crystal (the beam is
    then quasi-collimated there).
    """
    L_m, n0, _gT, _gS = element_grin_params(data, label)
    z, w = _z_nodes_weights(L_m, n_z)
    slices = crystal_slices(data, result, label, z)
    slices["w_z"] = w
    lam_m = wavelength_nm(data) * 1e-9
    wT_in, wS_in, RT_in, RS_in = entrance_entry(data, result, label)
    qT = q_from_wr(wT_in * 1e-3,
                   None if RT_in is None else RT_in * 1e-3, lam_m)
    qS = q_from_wr(wS_in * 1e-3,
                   None if RS_in is None else RS_in * 1e-3, lam_m)
    w0_T, z_T = waist_from_q(qT, lam_m)
    w0_S, z_S = waist_from_q(qS, lam_m)
    # waist_from_q: z > 0 means the waist is upstream of the entrance
    # plane, so the waist depth inside the crystal is -z.
    depth_T, depth_S = -float(z_T), -float(z_S)
    w_mean = float(np.mean(np.sqrt(np.asarray(slices["w_T_m"])
                                   * np.asarray(slices["w_S_m"]))))
    inside = (0.0 <= depth_T <= L_m) and (0.0 <= depth_S <= L_m)
    w_eff = math.sqrt(w0_T * w0_S) if inside else w_mean
    return {"slices": slices, "w0_T_m": float(w0_T),
            "w0_S_m": float(w0_S),
            "waist_depth_T_m": depth_T, "waist_depth_S_m": depth_S,
            "w_mean_m": w_mean, "w_eff_m": float(w_eff),
            "waist_inside": bool(inside),
            "exit_rel_err": slices["exit_rel_err"]}


def shg_K_for_point(shg, beam):
    """``(K, L_eff, xi, L_a)`` for one scan point.

    ``beam`` is a :func:`shg_beam_in_crystal` result; ``shg`` a
    :func:`resolve_shg` dict.
    """
    w0 = beam["w_eff_m"]
    L_a = aperture_length(w0, shg["rho"])
    L_eff = min(shg["L_m"], L_a)
    xi = focusing_parameter(L_eff, shg["lambda_w_m"], w0)
    K = shg_coefficient_K(shg["d_eff"], L_eff, xi, shg["n_omega"],
                          shg["n_2omega"], shg["lambda_w_m"],
                          shg["mismatch"])
    return K, L_eff, xi, L_a


def shg_output_beam(beam, shg):
    """Green output beam diagnostics (never fed back into the ABCD).

    ``w_2w,|| ~ sqrt((w_w/2)^2 + (rho*L/2)^2)`` in the walk-off plane,
    ``w_2w,perp ~ w_perp/2`` in the other plane; ellipticity is the
    ratio. ``M2_parallel`` is a heuristic walk-off degradation
    estimate ``sqrt(1 + (rho*L/(2*w_w))^2)`` (= 1 for NCPM).
    """
    slices = beam["slices"]
    w_T = float(np.mean(np.asarray(slices["w_T_m"])))
    w_S = float(np.mean(np.asarray(slices["w_S_m"])))
    if shg["walkoff_plane"] == "T":
        w_par, w_perp = w_T, w_S
    else:
        w_par, w_perp = w_S, w_T
    rho, L = shg["rho"], shg["L_m"]
    w_par_2w = math.sqrt((w_par / 2.0) ** 2 + (rho * L / 2.0) ** 2)
    w_perp_2w = w_perp / 2.0
    ellipticity = w_par_2w / w_perp_2w if w_perp_2w > 0 else float("inf")
    m2_par = math.sqrt(1.0 + (rho * L / (2.0 * w_par)) ** 2) \
        if w_par > 0 else float("inf")
    return {"w_2w_parallel_um": w_par_2w * 1e6,
            "w_2w_perp_um": w_perp_2w * 1e6,
            "ellipticity": ellipticity, "M2_parallel": m2_par,
            "M2_perp": 1.0,
            "w_fund_mean_um": float(np.mean([w_T, w_S])) * 1e6}


# --- Green noise -----------------------------------------------------------------

def green_noise_assessment(eta_1pass, single_frequency=False,
                           mode="intracavity"):
    """Green-Problem risk from the single-pass conversion efficiency.

    Mechanism (Baer 1986): in an intracavity-doubled laser the
    sum-frequency mixing between longitudinal modes couples them, so
    a multimode cavity with high conversion shows large green
    amplitude noise. The bands below are heuristic rules of thumb --
    green noise is typically reported once intracavity conversion
    exceeds ~10% -- not sharp thresholds, and the assessment says so.
    Returns ``{risk, eta_1pass, reasons, note}`` with risk in
    ``low`` / ``elevated`` / ``high``.
    """
    eta = float(eta_1pass)
    if mode != "intracavity":
        return {"risk": "low", "eta_1pass": eta,
                "reasons": ["extracavity SHG does not feed back into "
                            "the cavity: no inter-mode coupling"],
                "note": "heuristic assessment, not a measurement"}
    if single_frequency:
        return {"risk": "low", "eta_1pass": eta,
                "reasons": ["single longitudinal mode: no inter-mode "
                            "sum-frequency coupling"],
                "note": "heuristic assessment, not a measurement"}
    if eta < GREEN_NOISE_ELEVATED:
        return {"risk": "low", "eta_1pass": eta,
                "reasons": ["single-pass conversion %.1f%% is below the "
                            "~5%% band where green noise is reported"
                            % (100.0 * eta,)],
                "note": "heuristic assessment, not a measurement"}
    if eta < GREEN_NOISE_HIGH:
        return {"risk": "elevated", "eta_1pass": eta,
                "reasons": ["single-pass conversion %.1f%% with multiple "
                            "longitudinal modes: sum-frequency coupling "
                            "between modes can produce green amplitude "
                            "noise" % (100.0 * eta,)],
                "note": "heuristic bands (5%% / 15%%), not sharp "
                        "thresholds; single-frequency operation removes "
                        "the mechanism"}
    return {"risk": "high", "eta_1pass": eta,
            "reasons": ["single-pass conversion %.1f%% with multiple "
                        "longitudinal modes: strong sum-frequency "
                        "coupling, expect large green amplitude noise"
                        % (100.0 * eta,)],
            "note": "heuristic bands (5%% / 15%%), not sharp "
                    "thresholds; single-frequency operation removes "
                    "the mechanism"}


# --- Self-consistent solves ---------------------------------------------------------

def gamma_round_trip(params, slices, P_abs_W, P_circ, n_gh=DEFAULT_N_GH,
                     n_r=DEFAULT_N_R, n_theta=DEFAULT_N_THETA):
    """Round-trip gain exponent ``Gamma(P)`` (mode B overlap)."""
    K0 = (2.0 * params["sigma_em"] * params["tau_f"] * P_abs_W
          / (H_PLANCK * (C_LIGHT / params["lambda_p_m"])))
    return K0 * overlap_integral(params, slices, P_circ, n_gh=n_gh,
                                 n_r=n_r, n_theta=n_theta)


def solve_shg_intracavity(params, slices, P_abs_W, delta_linear, k_shg,
                          passes=2, n_gh=DEFAULT_N_GH, n_r=DEFAULT_N_R,
                          n_theta=DEFAULT_N_THETA):
    """Self-consistent intracavity SHG solve (nested brentq).

    Solves ``F(P) = Gamma(P) - [delta_linear + passes *
    eta_1pass(P)] = 0`` for the one-way circulating power. ``Gamma``
    falls with P (gain saturation) and the SHG loss rises with P, so
    the root is unique. Returns ``{P_circ, P_out_fund, P_2w,
    eta_1pass, delta_shg, converged, evaluations, below_threshold}``.
    Below threshold ``P_circ = 0`` (not an error).
    """
    if k_shg < 0:
        raise SHGError("SHG coefficient K must be >= 0, got %r" % (k_shg,))
    evals = [0]

    def F(P):
        evals[0] += 1
        return (gamma_round_trip(params, slices, P_abs_W, P,
                                 n_gh=n_gh, n_r=n_r, n_theta=n_theta)
                - delta_linear - passes * single_pass_eta(k_shg, P))

    if F(0.0) <= 0:
        return {"P_circ": 0.0, "P_out_fund": 0.0, "P_2w": 0.0,
                "eta_1pass": 0.0, "delta_shg": 0.0, "converged": True,
                "evaluations": evals[0], "below_threshold": True}
    lo, hi = 0.0, max(P_abs_W, 1.0)
    while F(hi) > 0:
        hi *= 2.0
        if hi > 1e7:
            raise SHGError("intracavity SHG solve did not bracket a root "
                           "below 1e7 W (P_abs=%r, K=%r)"
                           % (P_abs_W, k_shg))
    P_circ = brentq(F, lo, hi, xtol=1e-9, rtol=1e-12, maxiter=100)
    eta = single_pass_eta(k_shg, P_circ)
    return {"P_circ": float(P_circ),
            "P_out_fund": float(params["T_oc"] * P_circ),
            "P_2w": float(passes * P_circ * eta),
            "eta_1pass": float(eta),
            "delta_shg": float(passes * eta),
            "converged": True, "evaluations": evals[0],
            "below_threshold": False}


def solve_shg_extracavity(P_out_fund_W, k_shg):
    """One-pass conversion of an already-solved fundamental output."""
    if P_out_fund_W < 0:
        raise SHGError("fundamental output must be >= 0, got %r"
                       % (P_out_fund_W,))
    eta = single_pass_eta(k_shg, P_out_fund_W)
    return {"P_in_fund": float(P_out_fund_W),
            "P_2w": float(P_out_fund_W * eta),
            "eta_1pass": float(eta)}


# --- Scan ---------------------------------------------------------------------------

def shg_pump_scan(data, eng, pump_powers_W, T_oc=None, n_z=DEFAULT_N_Z,
                  n_gh=DEFAULT_N_GH, binary=None, timeout=None):
    """``P_2w`` vs ``P_pump`` for an SW oscillator with SHG.

    Mirrors :func:`power.pump_scan` (one CLI batch call for all
    thermal focal lengths), but each point additionally solves the
    nested SHG equation. Returns ``{points, summary, params,
    shg, warnings}``. When the side-car has no enabled SHG section,
    ``points`` is empty and ``summary["shg_status"]`` is
    ``"disabled"``; a non-SW cavity raises :class:`SHGError`.
    Unstable points get ``P_out = P_2w = 0`` and the
    ``thermal_instability`` flag -- the scan never aborts on them.
    """
    params = resolve_params(data, eng)
    shg = resolve_shg(data, eng)
    if shg is None:
        return {"points": [],
                "summary": {"shg_status": "disabled",
                            "note": "nonlinear_shg is absent or not "
                                  "enabled in the side-car"},
                "params": None, "shg": None,
                "warnings": list(params["warnings"])}
    if (data.get("trip_type") or "").upper() != "SW":
        raise SHGError("SHG scan needs a standing-wave (SW) cavity; "
                       "the mode B solver is an SW solver (got trip_type "
                       "%r)" % (data.get("trip_type"),))
    if T_oc is not None:
        if not (0 < float(T_oc) < 1):
            raise SHGError("T_oc must be a fraction in (0, 1)")
        params["T_oc"] = float(T_oc)
    delta_linear = params["T_oc"] + params["L_i"]
    label = params["gain_label"]
    conflict = check_overridable(data, label, "F")
    if conflict:
        raise SHGError("cannot update thermal focal length: %s" % conflict)
    F_unit = param_unit(data, label, "F")
    warnings = list(params["warnings"]) + list(shg["warnings"])
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
    # --- Per-point SHG solve ---
    points = []
    for P, (F_T, F_S, F_cli), result in zip(pump_powers_W, focals, results):
        point = {"P_pump_W": float(P), "F_T_mm": F_T * 1e3,
                 "F_S_mm": F_S * 1e3, "F_cli_mm": F_cli * 1e3}
        if not result.get("ok"):
            point.update({"status": "failed",
                          "error": result.get("error")})
            points.append(point)
            continue
        if not result.get("stable"):
            point.update({"status": "unstable", "P_out_B": 0.0,
                          "P_out_A": 0.0, "P_circ": 0.0, "P_2w": 0.0,
                          "flag": "thermal_instability"})
            points.append(point)
            continue
        try:
            slices = _slices_for(data, result, params, n_z, F_m=F_cli)
            beam = shg_beam_in_crystal(data, result,
                                       shg["crystal_label"], n_z=n_z)
        except (QevolveError, ValueError) as e:
            point.update({"status": "failed", "error": str(e)})
            points.append(point)
            continue
        if slices["exit_rel_err"] > 1e-6:
            warnings.append("q(z) evolver exit disagrees with CLI by "
                            "%.3g at P_pump=%.4g W (gain element %s)"
                            % (slices["exit_rel_err"], P, label))
        if beam["exit_rel_err"] > 1e-6:
            warnings.append("q(z) evolver exit disagrees with CLI by "
                            "%.3g at P_pump=%.4g W (SHG crystal %s)"
                            % (beam["exit_rel_err"], P,
                               shg["crystal_label"]))
        w_l = mean_mode_radius(slices)
        P_abs = params["eta_abs"] * P
        mode_a = mode_a_output(params, P, params["w_p0"], w_l)
        K, L_eff, xi, L_a = shg_K_for_point(shg, beam)
        out_beam = shg_output_beam(beam, shg)
        try:
            if shg["mode"] == "intracavity":
                sol = solve_shg_intracavity(params, slices, P_abs,
                                            delta_linear, K, passes=2,
                                            n_gh=n_gh)
                p_circ = sol["P_circ"]
                p_out = sol["P_out_fund"]
                p_2w = sol["P_2w"]
                eta = sol["eta_1pass"]
                delta_shg = sol["delta_shg"]
                evals = sol["evaluations"]
                below = sol["below_threshold"]
            else:
                base = solve_p_circ(params, slices, P_abs, delta_linear,
                                    n_gh=n_gh)
                ext = solve_shg_extracavity(base["P_out"], K)
                p_circ = base["P_circ"]
                p_out = base["P_out"]
                p_2w = ext["P_2w"]
                eta = ext["eta_1pass"]
                delta_shg = 0.0
                evals = base["evaluations"]
                below = base["below_threshold"]
        except (PowerError, SHGError) as e:
            point.update({"status": "failed", "error": str(e)})
            points.append(point)
            continue
        green = green_noise_assessment(eta, shg["single_frequency"],
                                       shg["mode"])
        point.update({"status": "ok", "w_l_um": w_l * 1e6,
                      "w_crystal_um": beam["w_eff_m"] * 1e6,
                      "K_per_W": K, "L_eff_mm": L_eff * 1e3,
                      "xi": xi, "L_a_mm": (None if math.isinf(L_a)
                                           else L_a * 1e3),
                      "P_th_A_W": mode_a["P_th"],
                      "P_out_A": mode_a["P_out"],
                      "P_circ": p_circ, "P_out_B": p_out,
                      "P_2w": p_2w, "eta_1pass": eta,
                      "delta_shg": delta_shg,
                      "below_threshold": below,
                      "evaluations": evals,
                      "exit_rel_err": slices["exit_rel_err"],
                      "exit_rel_err_shg": beam["exit_rel_err"],
                      "green_risk": green["risk"]})
        point.update(out_beam)
        points.append(point)
    ok_points = [p for p in points if p.get("status") == "ok"]
    best = max(ok_points, key=lambda p: p.get("P_2w", 0.0),
               default=None)
    summary = {"n_points": len(points),
               "n_ok": sum(1 for p in points if p.get("status") == "ok"),
               "n_unstable": sum(1 for p in points
                                 if p.get("status") == "unstable"),
               "n_failed": sum(1 for p in points
                               if p.get("status") == "failed"),
               "shg_status": "ok", "mode": shg["mode"],
               "phase_matching": shg["phase_matching"],
               "material": shg["material"],
               "crystal": shg["crystal_label"],
               "thermal_source": thermal_kappa(params)[2],
               "P_2w_max_W": best["P_2w"] if best else 0.0,
               "P_2w_max_pump_W": best["P_pump_W"] if best else None}
    return {"points": points, "summary": summary,
            "params": {k: params[k] for k in
                       ("gain_label", "L_m", "n0", "lambda_l_m",
                        "lambda_p_m", "sigma_em", "tau_f", "alpha_p",
                        "w_p0", "z_p0", "Mp2", "eta_p", "profile",
                        "T_oc", "L_i", "eta_mode", "eta_abs", "eta_q",
                        "I_sat", "F_current_m") if k in params},
            "shg": {k: v for k, v in shg.items() if k != "warnings"},
            "warnings": warnings}


# --- .rez helpers ------------------------------------------------------------------

def insert_crystal_element(data, label, length_mm, n, after_label,
                           shorten_label=None):
    """Return a copy of ``data`` with an ElemPlate crystal inserted.

    The plate (``length_mm``, refractive index ``n``) is inserted
    right after ``after_label``; when ``shorten_label`` is given, that
    range element's ``L`` is reduced by the crystal length, so the
    total geometric length of the cavity is unchanged. (The round-trip
    matrix still changes slightly: the plate propagates as ``L/n``,
    the empty range it replaces as ``L`` -- that is the real physics
    of inserting a slab.) Layout fields are copied from the element
    after which the crystal is inserted, so the file stays openable
    in the UI. The input dict is not modified.
    """
    out = copy.deepcopy(data)
    idx = element_index(out, after_label)
    if idx is None:
        raise SHGError("after_label %r is not in the .rez file"
                       % (after_label,))
    if element_index(out, label) is not None:
        raise SHGError("element %r already exists in the .rez file"
                       % (label,))
    anchor = copy.deepcopy(elements(out)[idx])
    plate = {"is_disabled": False, "label": label,
             "layout_draw_alt": anchor.get("layout_draw_alt", False),
             "layout_show_label": anchor.get("layout_show_label", True),
             "params": {
                 "L": {"error": "", "expr": "", "unit": "mm",
                       "value": float(length_mm)},
                 "n": {"error": "", "expr": "", "unit": "none",
                       "value": float(n)}},
             "title": "", "type": "ElemPlate"}
    for key in ("layout_x", "layout_y", "layout_angle"):
        if key in anchor:
            plate[key] = anchor[key]
    elements(out).insert(idx + 1, plate)
    if shorten_label is not None:
        cur = param_value_si(out, shorten_label, "L")
        if cur is None:
            raise SHGError("shorten element %r has no length"
                           % (shorten_label,))
        if cur * 1e3 <= float(length_mm):
            raise SHGError("shorten element %r (L=%.4g mm) is shorter "
                           "than the crystal (%.4g mm)"
                           % (shorten_label, cur * 1e3, length_mm))
        set_param_value(out, shorten_label, "L",
                        (cur * 1e3 - float(length_mm)), "mm")
    return out
