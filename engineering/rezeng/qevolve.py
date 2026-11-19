"""q(z) evolution inside range elements (GRIN / thermal lens / free space).

Convention -- verified against ``src/core/Elements.cpp``
(``ElemThermoLens`` / ``ElemGrinLens`` / ``GrinCalculator::solve_n2``) and
against the headless CLI on the user's real cavity (exit ``(w, R)`` matched
to ~1e-15 relative; see the verification in ``tests/test_power.py``):

- The ray vector is geometric ``(r, theta)``; element matrices are
  air-to-air. The CLI ``beam`` entry of an element is its ``(w, R)`` at
  the element's *exit* plane, air side. The entrance ``q`` of a range
  element is therefore the *previous* element's exit ``(w, R)``.
- A GRIN / thermal lens of length ``L``, index ``n0`` and gradient
  ``n2`` has gradient constant ``gamma = sqrt(n2/n0)`` (``n2`` from the
  focal length ``F`` by the exact ``solve_n2`` bisection, *not* the
  thin-lens approximation ``gamma = 1/sqrt(n*F*L)`` -- that is 0.9% off
  for the user's crystal). The submatrix from the entrance face to depth
  ``z`` is the C++ ``calcSubmatrices`` ``TS1_``::

      M1(z) = M_grin(z) . R_in,
      M_grin(z) = [[cos gz, sin gz/g], [-g sin gz, cos gz]]   (n2 > 0)
      R_in      = [[1, 0], [0, 1/n0]]                          (air -> medium)

  (``cosh`` / ``sinh`` for ``n2 < 0``; ``[[1, z/n0], [0, 1/n0]]`` for
  ``n2 = 0``, i.e. a plain dielectric slab.)
- ``q`` evolves by the ABCD law with the *local* wavelength::

      1/q = 1/R - i*lam/(pi*w^2),   lam = lam0/n inside the medium.

  At the exit face the refraction ``R_out = [[1, 0], [0, n0]]`` maps the
  medium-side ``q`` back to the air side (``q_air = q_med / n0``).

All lengths are SI (metres) inside this module; the CLI boundary
converts mm <-> m. ``R = None`` means a flat wavefront (``R`` infinite).
"""

import math

import numpy as np

from .rez import element_index, elements, param_obj, param_value_si


class QevolveError(ValueError):
    """Raised when a q(z) evolution cannot be set up."""


# --- GRIN constants ------------------------------------------------------

def solve_n2(L_m, n0, F_m):
    """Mirror of ``GrinCalculator::solve_n2``: solve ``n2`` from ``F``.

    ``F = 1 / (tan(g*L) * n0 * g)`` with ``g = sqrt(n2/n0)`` (``F > 0``);
    ``tanh`` for ``F < 0``. Bisection on ``x = g*L`` exactly as in C++
    (step 0.1 until the equation turns positive, then bisect to
    ``|y| <= 1e-8``). Returns ``n2`` in 1/m^2.
    """
    if L_m <= 0:
        raise QevolveError("crystal length must be positive: %r" % (L_m,))
    if n0 <= 0:
        raise QevolveError("refractive index must be positive: %r" % (n0,))
    if F_m == 0:
        raise QevolveError("focal length F must not be zero")
    if F_m > 0:
        eq = lambda x: x * F_m * n0 * math.tan(x) - L_m
        sign = 1.0
    else:
        eq = lambda x: x * -F_m * n0 * math.tanh(x) - L_m
        sign = -1.0
    x_next, x_prev = 0.0, 0.0
    y_next = eq(x_next)
    while y_next < 0:
        x_prev, x_next = x_next, x_next + 0.1
        y_next = eq(x_next)
    x_mid, y_mid = x_next, y_next
    for _ in range(1000):
        if abs(y_mid) <= 1e-8:
            break
        x_mid = (x_prev + x_next) / 2.0
        y_mid = eq(x_mid)
        if y_next > 0 and y_mid < 0:
            x_prev = x_mid
        else:
            x_next, y_next = x_mid, y_mid
    else:
        raise QevolveError("solve_n2 did not converge for L=%r, n0=%r, "
                           "F=%r" % (L_m, n0, F_m))
    return n0 * (x_mid / L_m) ** 2 * sign


def grin_gamma(L_m, n0, F_m):
    """``(gamma, n2)`` for a thermal/GRIN lens from its focal length.

    ``gamma`` is signed: positive = focusing (cos/sin), negative =
    defocusing (cosh/sinh, ``F < 0``).
    """
    n2 = solve_n2(L_m, n0, F_m)
    return math.sqrt(abs(n2) / n0) * (1.0 if n2 >= 0 else -1.0), n2


def calc_focus(L_m, n0, n2):
    """Mirror of ``GrinCalculator::calc_focus``: ``F`` from ``n2``."""
    if n2 == 0:
        return float("inf")
    g = math.sqrt(abs(n2) / n0)
    tg = -math.tanh(g * L_m) if n2 < 0 else math.tan(g * L_m)
    return 1.0 / tg / n0 / g


# --- q <-> (w, R) ---------------------------------------------------------

def q_from_wr(w_m, R_m, lam_m):
    """Complex beam parameter from radius ``w`` and wavefront radius ``R``.

    ``R_m`` is ``None`` for a flat wavefront. ``lam_m`` is the *local*
    wavelength (``lam0/n`` inside a medium).
    """
    if w_m is None or not math.isfinite(w_m) or w_m <= 0:
        raise QevolveError("beam radius must be a positive number: %r"
                           % (w_m,))
    re = 0.0 if R_m is None else 1.0 / R_m
    if R_m is not None and (not math.isfinite(R_m) or R_m == 0):
        raise QevolveError("wavefront radius must be finite and non-zero: "
                           "%r" % (R_m,))
    return 1.0 / complex(re, -lam_m / (math.pi * w_m * w_m))


def wr_from_q(q, lam_m):
    """``(w_m, R_m)`` from a complex beam parameter (local wavelength)."""
    inv = 1.0 / q
    if inv.imag >= 0:
        raise QevolveError("non-positive Rayleigh range from q=%r" % (q,))
    w = math.sqrt(lam_m / (math.pi * abs(inv.imag)))
    R = float("inf") if inv.real == 0 else 1.0 / inv.real
    return w, R


def waist_from_q(q, lam_m):
    """``(w0_m, z_m)`` of the beam segment: waist radius and signed
    distance from the plane to the waist (``z > 0`` = waist upstream)."""
    if q.imag <= 0:
        raise QevolveError("non-positive Rayleigh range from q=%r" % (q,))
    return math.sqrt(lam_m * q.imag / math.pi), q.real


# --- Element GRIN parameters ----------------------------------------------

#: Element types that carry a length and can host the gain medium.
#: ElemPlate is included: its C++ matrix is [[1, L/n], [0, 1]] with
#: submatrices TS1_ = [[1, z/n], [0, 1/n]] -- exactly the gamma = 0
#: branch of the evolver (a real dielectric slab). ElemMediumRange
#: is NOT a slab in this sense: the C++ matrix ignores n entirely
#: ([[1, L], [0, 1]]), so it must not be used where refraction
#: matters (see rezeng.shg.resolve_shg).
_RANGE_TYPES = ("ElemEmptyRange", "ElemMediumRange", "ElemGrinLens",
                "ElemGrinMedium", "ElemThermoLens", "ElemThermoMedium",
                "ElemPlate")


def element_grin_params(data, label):
    """``(L_m, n0, gamma_T, gamma_S)`` for a range element.

    - ``ElemThermoLens`` / ``ElemThermoMedium``: ``gamma`` from ``F``
      via :func:`solve_n2` (T and S share one ``F``).
    - ``ElemGrinLens`` / ``ElemGrinMedium``: ``gamma`` from ``n2t`` /
      ``n2s`` directly.
    - Plain ranges: ``gamma = 0`` (free space in a medium of index
      ``n``, default 1).
    """
    idx = element_index(data, label)
    if idx is None:
        raise QevolveError("unknown element %r" % (label,))
    elem = elements(data)[idx]
    etype = elem.get("type")
    if etype not in _RANGE_TYPES:
        raise QevolveError("element %r is %s, not a range element"
                           % (label, etype))
    L_m = param_value_si(data, label, "L")
    if L_m is None or not math.isfinite(L_m) or L_m <= 0:
        raise QevolveError("element %r has no positive length" % (label,))
    n0 = param_value_si(data, label, "n")
    if n0 is None:
        n0 = 1.0
    if not math.isfinite(n0) or n0 <= 0:
        raise QevolveError("element %r has a bad refractive index: %r"
                           % (label, n0))
    if etype in ("ElemThermoLens", "ElemThermoMedium"):
        F_m = param_value_si(data, label, "F")
        if F_m is None or not math.isfinite(F_m) or F_m == 0:
            raise QevolveError("element %r has no usable focal length"
                               % (label,))
        gamma, _n2 = grin_gamma(L_m, n0, F_m)
        return L_m, n0, gamma, gamma
    if etype in ("ElemGrinLens", "ElemGrinMedium"):
        gammas = []
        for alias in ("n2t", "n2s"):
            n2 = param_value_si(data, label, alias)
            if n2 is None:
                raise QevolveError("element %r has no %s" % (label, alias))
            gammas.append(math.sqrt(abs(n2) / n0)
                          * (1.0 if n2 >= 0 else -1.0))
        # Signed gamma: negative means defocusing (cosh branch).
        return L_m, n0, gammas[0], gammas[1]
    return L_m, n0, 0.0, 0.0


def find_gain_element(data, eng=None):
    """Label of the gain crystal element.

    From ``gain_and_pump.gain_element`` in the side-car when given;
    otherwise the unique ``ElemThermoLens`` / ``ElemGrinLens`` element.
    """
    if eng:
        gp = eng.get("gain_and_pump") or {}
        label = gp.get("gain_element")
        if label:
            if element_index(data, label) is None:
                raise QevolveError("gain_element %r is not in the .rez "
                                   "file" % (label,))
            return label
    candidates = [e.get("label") for e in elements(data)
                  if isinstance(e, dict)
                  and e.get("type") in ("ElemThermoLens", "ElemGrinLens")
                  and not e.get("is_disabled")]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise QevolveError("no ElemThermoLens/ElemGrinLens element in the "
                           ".rez file; set gain_and_pump.gain_element")
    raise QevolveError("ambiguous gain element %r; set "
                       "gain_and_pump.gain_element" % (candidates,))


def element_matrix(data, label):
    """Full air-to-air ABCD matrix ``(M_T, M_S)`` of one element.

    Mirrors the C++ ``Element::calcMatrixInternal`` definitions exactly
    (``src/core/Elements.cpp``):

    * ``ElemEmptyRange`` / ``ElemMediumRange``: ``[[1, L], [0, 1]]``
      (geometric length; the ray vector is geometric, so no ``/n``).
    * ``ElemPlate``: ``[[1, L/n], [0, 1]]`` (a real dielectric slab;
      the refraction is in the matrix, unlike ElemMediumRange).
    * ``ElemFlatMirror``: identity.
    * ``ElemCurveMirror``: ``[[1, 0], [C, 1]]`` with
      ``C_T = -2/(R*cos(alpha))``, ``C_S = -2*cos(alpha)/R``.
    * ``ElemThermoLens`` / ``ElemGrinLens``: the GRIN matrix
      ``[[cos(gL), sin(gL)/(n*g)], [-n*g*sin(gL), cos(gL)]]``
      with ``g = sqrt(n2/n0)`` (``cosh``/``sinh`` for ``n2 < 0``),
      i.e. ``R_out . M1(L)`` where ``M1`` is :func:`_m1_matrices`.

    Used by the chain-consistency test (propagate one CLI beam entry
    through the next element's matrix and compare with the next CLI
    entry) and by callers that need a single element's matrix.
    """
    idx = element_index(data, label)
    if idx is None:
        raise QevolveError("unknown element %r" % (label,))
    elem = elements(data)[idx]
    etype = elem.get("type")
    I = np.eye(2)
    if etype in ("ElemEmptyRange", "ElemMediumRange"):
        L_m = param_value_si(data, label, "L")
        if L_m is None or not math.isfinite(L_m):
            raise QevolveError("element %r has no length" % (label,))
        M = np.array([[1.0, L_m], [0.0, 1.0]])
        return M, M.copy()
    if etype == "ElemPlate":
        L_m = param_value_si(data, label, "L")
        n0 = param_value_si(data, label, "n")
        if L_m is None or not math.isfinite(L_m):
            raise QevolveError("element %r has no length" % (label,))
        if n0 is None or not math.isfinite(n0) or n0 <= 0:
            raise QevolveError("element %r has no usable n" % (label,))
        M = np.array([[1.0, L_m / n0], [0.0, 1.0]])
        return M, M.copy()
    if etype == "ElemFlatMirror":
        return I, I.copy()
    if etype == "ElemCurveMirror":
        R_m = param_value_si(data, label, "R")
        # param_value_si already converts "deg" -> radians.
        alpha = param_value_si(data, label, "Alpha") or 0.0
        if R_m is None or not math.isfinite(R_m) or R_m == 0:
            raise QevolveError("element %r has no usable R" % (label,))
        c = math.cos(alpha)
        M_T = np.array([[1.0, 0.0], [-2.0 / R_m / c, 1.0]])
        M_S = np.array([[1.0, 0.0], [-2.0 / R_m * c, 1.0]])
        return M_T, M_S
    if etype in ("ElemThermoLens", "ElemGrinLens", "ElemThermoMedium",
                 "ElemGrinMedium"):
        L_m, n0, g_T, g_S = element_grin_params(data, label)
        out = []
        for g in (g_T, g_S):
            A, B, C, D = _m1_matrices(np.array([L_m]), n0, g)
            # Full matrix = R_out . M1(L): [[A, B], [n0*C, n0*D]].
            out.append(np.array([[float(A[0]), float(B[0])],
                                 [n0 * float(C[0]), n0 * float(D[0])]]))
        return out[0], out[1]
    raise QevolveError("element_matrix: unsupported element type %r "
                       "for %r" % (etype, label))


# --- CLI beam entries ------------------------------------------------------

def beam_entry(result, label):
    """``(w_T, w_S, R_T, R_S)`` in mm from one CLI result's beam list.

    ``R`` is ``None`` for a flat wavefront (CLI JSON ``null``).
    """
    beam = result.get("beam")
    if not isinstance(beam, list):
        raise QevolveError("CLI result has no beam list (unstable or "
                           "single-pass ray pump?)")
    for entry in beam:
        if isinstance(entry, dict) and entry.get("label") == label:
            return (float(entry["w_T_mm"]), float(entry["w_S_mm"]),
                    entry.get("R_T_mm"), entry.get("R_S_mm"))
    raise QevolveError("CLI beam list has no element %r" % (label,))


def entrance_entry(data, result, label):
    """Beam entry at the *entrance* of ``label``: the previous element's
    exit entry (the CLI reports exit planes)."""
    idx = element_index(data, label)
    if idx is None:
        raise QevolveError("unknown element %r" % (label,))
    if idx == 0:
        raise QevolveError("element %r is first in the schema; its "
                           "entrance beam is not reported by the CLI"
                           % (label,))
    prev = elements(data)[idx - 1]
    if not isinstance(prev, dict) or prev.get("is_disabled"):
        raise QevolveError("element before %r is missing or disabled"
                           % (label,))
    return beam_entry(result, prev.get("label"))


# --- Evolution --------------------------------------------------------------

def _m1_matrices(z_m, n0, gamma):
    """Submatrix ``M1(z)`` (entrance -> depth ``z``) per plane.

    ``gamma`` is signed: positive = focusing (cos/sin), negative =
    defocusing (cosh/sinh), zero = plain medium. Returns ``(A, B, C, D)``
    as numpy arrays over ``z_m``. This is the C++ ``calcSubmatrices``
    ``TS1_``.
    """
    z = np.asarray(z_m, dtype=float)
    if gamma > 0:
        gz = gamma * z
        return (np.cos(gz), np.sin(gz) / (n0 * gamma),
                -gamma * np.sin(gz), np.cos(gz) / n0)
    if gamma < 0:
        g = -gamma
        gz = g * z
        return (np.cosh(gz), np.sinh(gz) / (n0 * g),
                g * np.sinh(gz), np.cosh(gz) / n0)
    return (np.ones_like(z), z / n0,
            np.zeros_like(z), np.full_like(z, 1.0 / n0))


def evolve_element(q_in_T, q_in_S, lam0_m, L_m, n0, gamma_T, gamma_S, z_m):
    """Evolve ``(q_T, q_S)`` from the entrance face to depths ``z_m``.

    ``q_in_*`` are air-side complex beam parameters at the entrance
    face. Returns a dict with ``w_T_m``, ``w_S_m``, ``R_T_m``, ``R_S_m``
    (numpy arrays, medium side, local wavelength ``lam0/n0``) and the
    air-side exit ``(w_T, w_S, R_T, R_S)`` in metres (``R`` infinite
    becomes ``float('inf')``).
    """
    z = np.asarray(z_m, dtype=float)
    if np.any(z < 0) or np.any(z > L_m):
        raise QevolveError("slice depths must lie in [0, L=%r]" % (L_m,))
    lam_med = lam0_m / n0
    out = {}
    for plane, q_in, gamma in (("T", q_in_T, gamma_T),
                               ("S", q_in_S, gamma_S)):
        A, B, C, D = _m1_matrices(z, n0, gamma)
        q = (A * q_in + B) / (C * q_in + D)
        inv = 1.0 / q
        if np.any(inv.imag >= 0):
            raise QevolveError("non-positive Rayleigh range inside the "
                               "element (plane %s)" % (plane,))
        out["w_%s_m" % plane] = np.sqrt(lam_med / (np.pi * np.abs(inv.imag)))
        out["R_%s_m" % plane] = np.where(
            inv.real == 0, np.inf, 1.0 / np.where(inv.real == 0, 1.0,
                                                  inv.real))
        # Exit face: refraction R_out = [[1,0],[0,n0]] -> q_air = q/n0.
        A1, B1, C1, D1 = _m1_matrices(np.array([L_m]), n0, gamma)
        q_med_exit = (A1[0] * q_in + B1[0]) / (C1[0] * q_in + D1[0])
        q_air_exit = q_med_exit / n0
        w_exit, R_exit = wr_from_q(q_air_exit, lam0_m)
        out["exit_w_%s_m" % plane] = w_exit
        out["exit_R_%s_m" % plane] = R_exit
    return out


def crystal_slices(data, result, gain_label, z_m, lambda_nm=None):
    """Mode radii inside the gain element at depths ``z_m`` (metres).

    ``result`` is one CLI result dict (its beam list supplies the
    entrance ``(w, R)`` from the previous element's exit and the exit
    ``(w, R)`` for a consistency check). Returns::

        {"label", "L_m", "n0", "gamma_T", "gamma_S", "z_m",
         "w_T_m", "w_S_m", "R_T_m", "R_S_m",
         "entrance": (w_T, w_S, R_T, R_S) in mm,
         "exit": (w_T, w_S, R_T, R_S) in mm (evolved),
         "exit_cli": (w_T, w_S, R_T, R_S) in mm (CLI),
         "exit_rel_err": max relative error of evolved vs CLI exit}

    The evolved exit must agree with the CLI exit to ~1e-6; anything
    larger means the convention drifted and must be investigated, not
    papered over.
    """
    from .solves import wavelength_nm
    lam_nm = lambda_nm if lambda_nm is not None else wavelength_nm(data)
    lam0_m = lam_nm * 1e-9
    L_m, n0, gamma_T, gamma_S = element_grin_params(data, gain_label)
    wT_in, wS_in, RT_in, RS_in = entrance_entry(data, result, gain_label)
    q_in_T = q_from_wr(wT_in * 1e-3,
                       None if RT_in is None else RT_in * 1e-3, lam0_m)
    q_in_S = q_from_wr(wS_in * 1e-3,
                       None if RS_in is None else RS_in * 1e-3, lam0_m)
    z = np.asarray(z_m, dtype=float)
    ev = evolve_element(q_in_T, q_in_S, lam0_m, L_m, n0,
                        gamma_T, gamma_S, z)
    wT_ex, wS_ex, RT_ex, RS_ex = beam_entry(result, gain_label)
    errs = []
    for plane, ev_w, ev_R, cli_w, cli_R in (
            ("T", ev["exit_w_T_m"], ev["exit_R_T_m"], wT_ex, RT_ex),
            ("S", ev["exit_w_S_m"], ev["exit_R_S_m"], wS_ex, RS_ex)):
        errs.append(abs(ev_w * 1e3 - cli_w) / max(abs(cli_w), 1e-12))
        if cli_R is not None and math.isfinite(ev_R):
            errs.append(abs(ev_R * 1e3 - cli_R) / max(abs(cli_R), 1e-12))
    return {"label": gain_label, "L_m": L_m, "n0": n0,
            "gamma_T": gamma_T, "gamma_S": gamma_S,
            "z_m": z, "w_T_m": ev["w_T_m"], "w_S_m": ev["w_S_m"],
            "R_T_m": ev["R_T_m"], "R_S_m": ev["R_S_m"],
            "entrance": (wT_in, wS_in, RT_in, RS_in),
            "exit": (ev["exit_w_T_m"] * 1e3, ev["exit_w_S_m"] * 1e3,
                     ev["exit_R_T_m"] * 1e3, ev["exit_R_S_m"] * 1e3),
            "exit_cli": (wT_ex, wS_ex, RT_ex, RS_ex),
            "exit_rel_err": max(errs) if errs else 0.0}
