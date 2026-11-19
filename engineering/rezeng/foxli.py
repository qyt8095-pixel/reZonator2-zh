"""FFT Fox-Li physical-optics diffraction engine (Phase 4 M3).

A round-trip operator is built from the ``.rez`` schema itself (no
single equivalent round-trip ABCD): free-space legs are propagated
element by element, curved mirrors apply their phase factor, and the
thermal-lens crystal is a split-step stack of glass propagation +
thermal-OPD phase plates, so aperture truncation and thermal spherical
aberration keep their spatial coupling to the cavity (Gemini review
SS1: never compress the cavity into one ABCD operator).

Conventions (locked by the tests in ``test_phase4_block3.py``):

* Propagation uses the ``exp(+ikz)`` convention: the angular-spectrum
  transfer function is ``exp(+i*k*z*sqrt(1-(lam*f)^2))`` and the
  Fresnel kernel is ``exp(+i*k*(x2-x1)^2/(2z))``.  A converging lens
  of focal length ``f`` multiplies the field by
  ``exp(-i*k*r^2/(2f))``; a mirror with ABCD ``C`` element multiplies
  by ``exp(+i*k*C*r^2/2)`` (``C = -1/f`` for a thin lens).
* The thermal OPD is an *optical path difference* (more path at the
  hot centre), so the crystal phase plate is ``exp(+i*k0*OPD(r))``
  with ``OPD(r) = -r^2/(2*f_th) + c4*r^4 + c6*r^6``.  The review
  writes ``exp(-i*k*OPD)`` under the opposite (``exp(-ikz)``)
  convention; the sign here is locked by the split-step-vs-GRIN
  test and by the CLI cross-validation -- a flipped sign defocuses
  the crystal and both fail.
* Fields are stored in FFT order (index 0 is ``x = 0``; coordinates
  ``x = fftfreq(N, d=dx)*(N*dx)``).  All propagators keep the grid
  spacing ``dx`` except the single-FFT Fresnel form, whose output
  spacing is ``lam*z/(N*dx)`` (see :func:`single_fft_fresnel_step`).
* The reference plane is the first element's exit face (M1 for the
  user's cavity).  The round trip is: forward leg, end-mirror
  reflection, return leg, first-mirror reflection.

Propagator choice (Gemini review SS1, hand-verified in the tests):
``z_c = N*dx^2/lam`` is the critical sampling distance (58.7 mm for
N=256, 4 mm window, 1064 nm).  Below ``z_c`` the band-limited angular
spectrum method (BL-ASM, 2x zero padding + frequency band-limit)
is used; above it the two-step Fresnel method (equal split, input
and output grids identical).  The single-FFT Fresnel form is *not*
used for long legs: at z=400 mm its output step would be 106 um,
about half the 0.2 mm beam -- only two pixels across the spot.
"""

import math

import numpy as np

from .qevolve import (QevolveError, beam_entry, element_grin_params,
                      element_matrix)
from .rez import element_index, elements, param_value_si


class FoxLiError(ValueError):
    """Raised for bad Fox-Li input (unsupported element, bad grid, ...)."""


# --- Sampling ---------------------------------------------------------------

def critical_distance(n, dx_m, lam_m):
    """Critical sampling distance ``z_c = N*dx^2/lam`` [m].

    Below ``z_c`` the angular-spectrum transfer function is sampled
    without aliasing; above it the two-step Fresnel form is used.
    Hand check: N=256, dx=15.625 um, lam=1064 nm -> 58.74 mm.
    """
    if n <= 0 or dx_m <= 0 or lam_m <= 0:
        raise FoxLiError("critical_distance needs positive N/dx/lambda")
    return n * dx_m * dx_m / lam_m


def single_fft_fresnel_step(n, dx_m, z_m, lam_m):
    """Output grid step ``lam*z/(N*dx)`` [m] of one single-FFT Fresnel
    propagation.  Hand check: z=400 mm, N=256, dx=15.625 um,
    lam=1064 nm -> 106.4 um (about half the 0.2 mm beam)."""
    if n <= 0 or dx_m <= 0 or lam_m <= 0:
        raise FoxLiError("single_fft_fresnel_step needs positive N/dx/lambda")
    return lam_m * z_m / (n * dx_m)


def _fft_coords(n, dx_m):
    """1D coordinates [m] in FFT order (index 0 is x = 0).

    ``fftfreq(n)`` is ``k/n``; times ``n*dx`` that is ``k*dx``.
    """
    return np.fft.fftfreq(n) * (n * dx_m)


def _grid2d(n, dx_m):
    """``(X, Y)`` coordinate grids [m] in FFT order."""
    x = _fft_coords(n, dx_m)
    return np.meshgrid(x, x, indexing="ij")


# --- Propagators ------------------------------------------------------------

def asm_propagate(E, z_m, lam_m, dx_m, pad=2):
    """Band-limited angular-spectrum propagation over ``z_m`` [m].

    The field is zero-padded ``pad``x (default 2x), Fourier
    transformed, multiplied by ``exp(+i*k*z*sqrt(1-(lam*f)^2))``
    (evanescent components zeroed), band-limited to
    ``f_lim = 1/(lam*sqrt(1+(2*z*df)^2))`` with ``df = 1/(Np*dx)``
    (Matsushima & Shimobaba: the transfer-function phase must not
    move by more than pi per frequency sample), and cropped back.
    Works for negative ``z`` (back-propagation) as well.
    """
    E = np.asarray(E, dtype=complex)
    if E.ndim != 2 or E.shape[0] != E.shape[1]:
        raise FoxLiError("asm_propagate needs a square 2D field")
    if z_m == 0.0:
        return E.copy()
    n = E.shape[0]
    n_p = pad * n
    off = (n_p - n) // 2
    # Pad in centred order (FFT-order arrays cannot be padded by
    # slicing: index 0 is x = 0, not the window centre).
    E_p = np.zeros((n_p, n_p), dtype=complex)
    E_p[off:off + n, off:off + n] = np.fft.fftshift(E)
    F = np.fft.fft2(np.fft.ifftshift(E_p))
    fx = np.fft.fftfreq(n_p, d=dx_m)
    FX, FY = np.meshgrid(fx, fx, indexing="ij")
    k = 2.0 * np.pi / lam_m
    s2 = (lam_m * FX) ** 2 + (lam_m * FY) ** 2
    H = np.exp(1j * k * z_m * np.sqrt(np.maximum(0.0, 1.0 - s2)))
    H[s2 >= 1.0] = 0.0
    df = 1.0 / (n_p * dx_m)
    f_lim = 1.0 / (lam_m * math.sqrt(1.0 + (2.0 * z_m * df) ** 2))
    H[np.abs(FX) > f_lim] = 0.0
    H[np.abs(FY) > f_lim] = 0.0
    out = np.fft.ifft2(F * H)
    crop = np.fft.fftshift(out)[off:off + n, off:off + n]
    return np.fft.ifftshift(crop)


def _fresnel_ft(E, z_m, lam_m, dx_m):
    """One single-FFT Fresnel step (Fourier-transform form).

    Returns ``(E_out, dx_out)``: the field on a grid of spacing
    ``dx_out = lam*z/(N*dx)`` -- *not* the input spacing.  Used
    only inside :func:`two_step_fresnel_propagate`, never directly
    for a cavity leg.
    """
    E = np.asarray(E, dtype=complex)
    n = E.shape[0]
    k = 2.0 * np.pi / lam_m
    X, Y = _grid2d(n, dx_m)
    Q = np.exp(1j * k * (X ** 2 + Y ** 2) / (2.0 * z_m))
    F = np.fft.fft2(E * Q)
    dx_out = lam_m * z_m / (n * dx_m)
    x2 = np.fft.fftfreq(n, d=dx_m) * (lam_m * z_m)
    X2, Y2 = np.meshgrid(x2, x2, indexing="ij")
    Q2 = np.exp(1j * k * (X2 ** 2 + Y2 ** 2) / (2.0 * z_m))
    pref = np.exp(1j * k * z_m) / (1j * lam_m * z_m) * dx_m * dx_m
    return pref * Q2 * F, dx_out


def two_step_fresnel_propagate(E, z_m, lam_m, dx_m):
    """Two-step Fresnel propagation over ``z_m`` [m] (equal split).

    Two single-FFT Fresnel steps of ``z/2`` each: the first maps the
    grid spacing ``dx -> lam*(z/2)/(N*dx)``, the second maps it back
    to ``dx``, so input and output grids are identical.  Only for
    ``z > 0`` (back-propagation goes through :func:`asm_propagate`).

    Limitation (test-locked): the intermediate grid is only
    ``lam*z/(2*dx)`` wide, so for short ``z`` it is *narrower* than
    the beam and clips it (at z=10 mm, w0=0.2 mm: +37% width error).
    Callers must use :func:`propagate`, which checks the
    intermediate window against the beam size before dispatching.
    """
    if z_m <= 0.0:
        raise FoxLiError("two-step Fresnel needs z > 0")
    z1 = 0.5 * z_m
    z2 = z_m - z1
    E1, dx1 = _fresnel_ft(E, z1, lam_m, dx_m)
    E2, dx2 = _fresnel_ft(E1, z2, lam_m, dx1)
    if abs(dx2 - dx_m) > 1e-9 * dx_m:
        raise FoxLiError("two-step Fresnel grid mismatch: dx_out %.3g "
                         "!= dx_in %.3g" % (dx2, dx_m))
    return E2


def _d4sigma_radius(E, dx_m):
    """D4-sigma radius [m] of the wider plane (for the TSF guard)."""
    n = E.shape[0]
    x = _fft_coords(n, dx_m)
    X, Y = np.meshgrid(x, x, indexing="ij")
    I = np.abs(E) ** 2
    tot = float(np.sum(I))
    if tot <= 0.0:
        return 0.0
    x_bar = float(np.sum(X * I)) / tot
    y_bar = float(np.sum(Y * I)) / tot
    sx2 = float(np.sum((X - x_bar) ** 2 * I)) / tot
    sy2 = float(np.sum((Y - y_bar) ** 2 * I)) / tot
    return 2.0 * max(math.sqrt(sx2), math.sqrt(sy2))


def propagate(E, z_m, lam_m, dx_m, pad=2):
    """Free-space propagation over ``z_m`` [m] on a ``dx_m`` grid.

    ``z <= z_c``: band-limited angular spectrum; ``z > z_c``:
    two-step Fresnel -- but only when the intermediate grid (half
    width ``lam*z/(4*dx)``) is at least 3x the beam radius at the
    intermediate plane (estimated as ``max(w_in, lam*z/(2*pi*w_in))``,
    the diffractive spread included); otherwise ASM, which has no
    such limitation.  Negative ``z`` always uses ASM (the two-step
    form cannot express a negative output step).
    """
    if z_m == 0.0:
        return np.asarray(E, dtype=complex).copy()
    if z_m < 0.0:
        return asm_propagate(E, z_m, lam_m, dx_m, pad=pad)
    z_c = critical_distance(E.shape[0], dx_m, lam_m)
    if z_m <= z_c:
        return asm_propagate(E, z_m, lam_m, dx_m, pad=pad)
    w_in = _d4sigma_radius(E, dx_m)
    if w_in > 0.0:
        w_mid = max(w_in, lam_m * z_m / (2.0 * np.pi * w_in))
        if lam_m * z_m / (4.0 * dx_m) >= 3.0 * w_mid:
            return two_step_fresnel_propagate(E, z_m, lam_m, dx_m)
    return asm_propagate(E, z_m, lam_m, dx_m, pad=pad)


# --- Phase factors, apertures, crystal --------------------------------------

def opd_profile(X, Y, f_th_m, c4_per_m3, c6_per_m5, r_max_m=None):
    """Thermal OPD [m]: ``-r^2/(2*f_th) + c4*r^4 + c6*r^6``.

    ``f_th_m`` is a focal length [m], or a ``(f_T, f_S)`` pair for
    an astigmatic quadratic ``-x^2/(2*f_T) - y^2/(2*f_S)`` (the
    ``c4``/``c6`` terms stay radial).  A component may be ``inf``
    (no quadratic term in that plane).

    The quadratic is the paraxial lens: it extends over the whole
    grid (a physical lens does not stop at the fit radius).  Only
    the fitted higher-order terms (``c4``/``c6``) are clamped:
    ``r_max_m`` is the radius the fitted polynomial is valid to
    (``fit_opd`` fits only ``r <= 1.5*w_L``); beyond it the
    ``c4``/``c6`` contribution is held at its value on the circle
    ``r = r_max_m`` (the raw polynomial diverges outside the fit
    region and would alias catastrophically on the grid).  ``None``
    means no clamp (the anchor GRIN quadratic, valid everywhere).

    Clamping the quadratic as well would truncate the lens at
    ``r_max_m`` (a hard-edged lens): a quadratic-only control run
    then converges to a non-Gaussian mode (M2 = 1.42 at 5 W) instead
    of the CLI Gaussian, so the clamp must not touch it.
    """
    r2 = X ** 2 + Y ** 2
    if isinstance(f_th_m, (tuple, list)):
        f_T, f_S = f_th_m
        opd = np.zeros_like(r2)
        if math.isfinite(f_T):
            opd = opd - X ** 2 / (2.0 * f_T)
        if math.isfinite(f_S):
            opd = opd - Y ** 2 / (2.0 * f_S)
    else:
        opd = -r2 / (2.0 * f_th_m) if math.isfinite(f_th_m) \
            else np.zeros_like(r2)
    if r_max_m is not None:
        r = np.sqrt(r2)
        scale = np.where(r > r_max_m, r_max_m / np.maximum(r, 1e-300),
                         1.0)
        r2_fit = (X * scale) ** 2 + (Y * scale) ** 2
    else:
        r2_fit = r2
    return opd + c4_per_m3 * r2_fit ** 2 + c6_per_m5 * r2_fit ** 3


def mirror_phase(E, X, Y, c_T, c_S, lam_m):
    """Multiply by a mirror/lens phase ``exp(+i*k*(C_T*x^2+C_S*y^2)/2)``."""
    k = 2.0 * np.pi / lam_m
    return E * np.exp(1j * k * (c_T * X ** 2 + c_S * Y ** 2) / 2.0)


def circular_aperture(X, Y, radius_m):
    """Boolean mask: 1 inside the circular aperture, 0 outside."""
    return (X ** 2 + Y ** 2) <= radius_m * radius_m


def crystal_pass(E, L_m, n, f_th_m, c4_per_m3, c6_per_m5, lam0_m,
                 dx_m, n_slices=4, r_max_m=None):
    """Split-step pass through a thermal-lens (GRIN) crystal.

    Symmetric Strang splitting with ``n_slices`` phase plates: half
    a glass slice, then per slice one OPD plate carrying ``1/n_slices``
    of the total ``OPD(r)`` and one glass slice (the last slice is a
    half slice).  Glass propagation uses ``lam/n``; the plates use
    ``exp(+i*k0*OPD)`` (see the module docstring for the sign).

    ``f_th_m`` is the **OPD-equivalent** focal length: the quadratic
    coefficient of the physical OPD, ``OPD = -r^2/(2*f_th)``
    (+ ``c4 r^4 + c6 r^6``), i.e. ``f_th = 1/(n2*L)`` for a GRIN
    anchor with ``n2 = n0*gamma^2``.  It is NOT the ``.rez`` ``F``
    (the C++ ``calc_focus`` definition ``F = 1/(tan(gL)*n*g)``) and
    NOT the matrix focal length ``-1/C = 1/(n*g*sin(gL))``: for the
    user's TL1 (g*L = 0.231) the three are 230 / 234.2 / 236.3 mm,
    and only the OPD-equivalent one is the faithful split-step
    discretisation of the parabolic index profile (verified
    against the exact GRIN: exit R within 0.08% at 4 slices,
    0.02% at 8; the ``.rez`` F gives -2.7%, the matrix F
    converges to the wrong continuous limit, +1.3% at 8 slices).
    ``f_th_m`` may be a ``(f_T, f_S)`` pair (astigmatic quadratic)
    or ``inf`` (no quadratic term, e.g. a plain plate).

    ``r_max_m`` clamps a *fitted* OPD polynomial to its fit radius
    (see :func:`opd_profile`); ``None`` (the anchor) means the
    quadratic is used unclamped.
    """
    if n_slices < 1:
        raise FoxLiError("crystal_pass needs n_slices >= 1")
    lam_med = lam0_m / n
    k0 = 2.0 * np.pi / lam0_m
    n_grid = E.shape[0]
    X, Y = _grid2d(n_grid, dx_m)
    opd = opd_profile(X, Y, f_th_m, c4_per_m3, c6_per_m5,
                      r_max_m=r_max_m)
    plate = np.exp(1j * k0 * opd / n_slices)
    ell = L_m / n_slices
    E = asm_propagate(E, ell / 2.0, lam_med, dx_m)
    for i in range(n_slices):
        E = E * plate
        step = ell if i < n_slices - 1 else ell / 2.0
        E = asm_propagate(E, step, lam_med, dx_m)
    return E


# --- Initial field and second moments ---------------------------------------

def initial_field(n, dx_m, w_T_m, w_S_m, R_T_m, R_S_m, lam_m,
                  noise_frac=0.05, seed=0):
    """Gaussian eigenmode guess at the reference plane + noise.

    ``E0 = exp(-x^2/w_T^2 - y^2/w_S^2) * exp(+i*k*(x^2/(2R_T) +
    y^2/(2R_S)))`` (curvature term skipped when ``R`` is None/inf),
    unit power, then multiplied by ``(1 + noise_frac * M)`` with ``M``
    unit-variance complex white noise (fixed ``seed``).  The noise
    power fraction is ``noise_frac**2``; a pure Gaussian locks onto
    the symmetric mode and misses lower-loss asymmetric modes, while
    pure noise converges too slowly (Gemini review SS2).
    """
    if w_T_m <= 0 or w_S_m <= 0:
        raise FoxLiError("initial_field needs positive beam radii")
    X, Y = _grid2d(n, dx_m)
    k = 2.0 * np.pi / lam_m
    phase = np.zeros_like(X)
    if R_T_m is not None and math.isfinite(R_T_m):
        phase = phase + X ** 2 / (2.0 * R_T_m)
    if R_S_m is not None and math.isfinite(R_S_m):
        phase = phase + Y ** 2 / (2.0 * R_S_m)
    E = np.exp(-X ** 2 / w_T_m ** 2 - Y ** 2 / w_S_m ** 2) \
        * np.exp(1j * k * phase)
    E = E / math.sqrt(float(np.sum(np.abs(E) ** 2)) * dx_m * dx_m)
    if noise_frac:
        rng = np.random.default_rng(seed)
        noise = (rng.standard_normal((n, n))
                 + 1j * rng.standard_normal((n, n))) / math.sqrt(2.0)
        E = E * (1.0 + noise_frac * noise)
        E = E / math.sqrt(float(np.sum(np.abs(E) ** 2)) * dx_m * dx_m)
    return E


def second_moments(E, dx_m, lam_m):
    """D4-sigma beam parameters of a field at its own plane.

    Returns ``{"w_T_mm", "w_S_mm", "M2_T", "M2_S", "R_T_mm",
    "R_S_mm", ...}``.  ``w`` is the D4-sigma radius ``2*sigma``
    (equal to the 1/e^2 radius for a Gaussian).  ``M^2`` uses the
    position-angle covariance (Gemini review SS2)::

        M_x^2 = 4*pi*sqrt(sigma_x^2*sigma_fx^2 - sigma_{x,fx}^2)

    with ``sigma_fx`` in cycles/m and
    ``sigma_{x,fx} = Im[int E* x dE/dx] / (2*pi*int|E|^2)``
    (centroid-subtracted).  At a non-waist plane the naive
    ``4*pi*sigma_x*sigma_theta/lam`` overestimates M^2 badly
    (the test locks a curved-wavefront case); propagating to the
    waist first gives the same value, which the test cross-checks.
    ``R`` comes from the moments (``R = sigma_x^2/sigma_{x,theta}``,
    None at a waist).
    """
    E = np.asarray(E, dtype=complex)
    n = E.shape[0]
    x = _fft_coords(n, dx_m)
    X, Y = np.meshgrid(x, x, indexing="ij")
    I = np.abs(E) ** 2
    tot = float(np.sum(I))
    if tot <= 0.0:
        raise FoxLiError("second_moments needs a non-empty field")
    x_bar = float(np.sum(X * I)) / tot
    y_bar = float(np.sum(Y * I)) / tot
    sx2 = float(np.sum((X - x_bar) ** 2 * I)) / tot
    sy2 = float(np.sum((Y - y_bar) ** 2 * I)) / tot
    F = np.fft.fft2(E)
    fx = np.fft.fftfreq(n, d=dx_m)
    FX, FY = np.meshgrid(fx, fx, indexing="ij")
    IF = np.abs(F) ** 2
    tot_f = float(np.sum(IF))
    fx_bar = float(np.sum(FX * IF)) / tot_f
    fy_bar = float(np.sum(FY * IF)) / tot_f
    sfx2 = float(np.sum((FX - fx_bar) ** 2 * IF)) / tot_f
    sfy2 = float(np.sum((FY - fy_bar) ** 2 * IF)) / tot_f
    dEdx = np.fft.ifft2(2j * np.pi * FX * F)
    dEdy = np.fft.ifft2(2j * np.pi * FY * F)
    # <(x-xbar)*fx> straight from the operator identity
    # <g(x)*fx> = Im[int E* g(x) dE/dx] / (2*pi*int|E|^2); with
    # g(x) = x - xbar the <x-xbar> factor already centres it, so no
    # extra -xbar*fxbar term (that would double-subtract).
    cov_x = float(np.imag(np.sum(np.conj(E) * (X - x_bar) * dEdx))) \
        / (2.0 * np.pi * tot)
    cov_y = float(np.imag(np.sum(np.conj(E) * (Y - y_bar) * dEdy))) \
        / (2.0 * np.pi * tot)
    M2_T = 4.0 * np.pi * math.sqrt(max(sx2 * sfx2 - cov_x ** 2, 0.0))
    M2_S = 4.0 * np.pi * math.sqrt(max(sy2 * sfy2 - cov_y ** 2, 0.0))
    # Wavefront curvature from the moments (R = sigma_x^2/sigma_{x,theta}).
    sig_xtheta_T = lam_m * cov_x
    sig_xtheta_S = lam_m * cov_y
    R_T = sx2 / sig_xtheta_T if abs(sig_xtheta_T) > 0.0 else None
    R_S = sy2 / sig_xtheta_S if abs(sig_xtheta_S) > 0.0 else None
    return {
        "w_T_mm": 2.0 * math.sqrt(sx2) * 1e3,
        "w_S_mm": 2.0 * math.sqrt(sy2) * 1e3,
        "M2_T": float(M2_T),
        "M2_S": float(M2_S),
        "R_T_mm": (R_T * 1e3 if R_T is not None else None),
        "R_S_mm": (R_S * 1e3 if R_S is not None else None),
        "sigma_x_um": math.sqrt(sx2) * 1e6,
        "sigma_y_um": math.sqrt(sy2) * 1e6,
        "x_bar_um": x_bar * 1e6,
        "y_bar_um": y_bar * 1e6,
        # Raw second moments (SI) for waist_m2 and diagnostics.
        "sigma_x_m": math.sqrt(sx2),
        "sigma_y_m": math.sqrt(sy2),
        "sigma_fx_per_m": math.sqrt(sfx2),
        "sigma_fy_per_m": math.sqrt(sfy2),
        "cov_x": cov_x,
        "cov_y": cov_y,
    }


def waist_m2(E, dx_m, lam_m):
    """M^2 by propagating the field to its generalised waist first.

    Waist offset per plane ``z0 = -sigma_{x,theta}/sigma_theta^2``
    with ``sigma_{x,theta} = lam*cov_x`` and
    ``sigma_theta^2 = lam^2*sigma_fx^2``; at the waist the
    covariance vanishes, so ``M^2 = 4*pi*sigma_x(z0)*sigma_fx``.
    Must agree with :func:`second_moments` (test-locked).
    """
    mom = second_moments(E, dx_m, lam_m)
    out = {}
    for plane in ("T", "S"):
        sig_x = mom["sigma_x_m" if plane == "T" else "sigma_y_m"]
        cov = mom["cov_x" if plane == "T" else "cov_y"]
        sfx = mom["sigma_fx_per_m" if plane == "T"
                  else "sigma_fy_per_m"]
        sig_xtheta = lam_m * cov
        sig_theta2 = lam_m * lam_m * sfx * sfx
        z0 = -sig_xtheta / sig_theta2 if sig_theta2 > 0 else 0.0
        E_w = propagate(E, z0, lam_m, dx_m) if z0 != 0.0 else E
        mom_w = second_moments(E_w, dx_m, lam_m)
        out["M2_" + plane] = mom_w["M2_" + plane]
        out["z0_" + plane + "_mm"] = z0 * 1e3
    return out


def spot_ascii(E, width=64, height=24):
    """ASCII rendering of the spot intensity (log scale, centred).

    The field is in FFT order (index 0 is x = 0); the map is
    centred (fftshift) and downsampled by block maximum so the
    peak stays visible.  Returns a multi-line string; the peak
    is ``@``, the background is a space.
    """
    I = np.abs(np.asarray(E, dtype=complex)) ** 2
    I = np.fft.fftshift(I)
    n = I.shape[0]
    peak = float(np.max(I))
    if peak <= 0:
        return "(empty field)"
    # Block-max downsample to (height, width).
    bh = max(1, n // height)
    bw = max(1, n // width)
    h = n // bh
    w = n // bw
    small = I[:h * bh, :w * bw].reshape(h, bh, w, bw).max(axis=(1, 3))
    chars = " .:-=+*#%@"
    log = np.log10(np.maximum(small, peak * 1e-6) / peak)
    # -6 .. 0 dex maps to the 10 characters.
    idx = np.clip(((log + 6.0) / 6.0 * (len(chars) - 1)).astype(int),
                  0, len(chars) - 1)
    lines = ["".join(chars[i] for i in row) for row in idx]
    return "\n".join(lines)


def spot_png(E, dx_m, path, title="Fox-Li spot"):
    """Save the spot intensity as a PNG (matplotlib); False if
    matplotlib is unavailable (no install is attempted)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    I = np.abs(np.asarray(E, dtype=complex)) ** 2
    I = np.fft.fftshift(I)
    n = I.shape[0]
    half = n * dx_m * 1e3 / 2.0
    plt.figure(figsize=(5, 5))
    plt.imshow(I, extent=[-half, half, -half, half],
               origin="lower", cmap="inferno")
    plt.colorbar(label="intensity (arb.)")
    plt.xlabel("x [mm]")
    plt.ylabel("y [mm]")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    return True


# --- Cavity operator --------------------------------------------------------

# Element types the operator knows how to propagate.
_SUPPORTED = ("ElemEmptyRange", "ElemMediumRange", "ElemPlate",
              "ElemFlatMirror", "ElemCurveMirror", "ElemThermoLens",
              "ElemGrinLens")


def wavelength_nm(data, foxli=None):
    """Laser wavelength [nm]: foxli section override, else the .rez
    ``builtin_params.lambda``, else 1064 nm."""
    if foxli and foxli.get("wavelength_nm"):
        return float(foxli["wavelength_nm"])
    lam = (data.get("builtin_params") or {}).get("lambda") or {}
    value = lam.get("value")
    if value:
        unit = lam.get("unit") or "nm"
        if unit == "nm":
            return float(value)
        if unit == "um":
            return float(value) * 1e3
        if unit == "m":
            return float(value) * 1e9
    return 1064.0


class CavityOperator:
    """Round-trip Fox-Li operator built from one ``.rez`` schema.

    ``apertures`` maps element labels to aperture *radii* [mm]
    (from the side-car ``elements`` ``aperture_diameter_mm`` or the
    ``foxli.apertures`` override).  Elements without aperture data
    are not truncated and are listed in ``aperture_notes``.
    ``opd`` is ``{"f_th_mm", "c4_per_m3", "c6_per_m5"}`` for the
    thermo-lens element(s), optionally with ``"r_fit_max_mm"`` --
    the radius the fitted polynomial is valid to (beyond it the
    OPD is held constant; without it the polynomial is used
    unclamped).  Without an ``opd`` the crystal uses the GRIN
    anchor OPD (``f_th = 1/(n2*L)`` from the element's gamma).
    """

    def __init__(self, data, lam_nm=1064.0, grid_size=256,
                 window_mm=8.0, apertures=None, opd=None,
                 n_slices=4, pad=2):
        self.data = data
        self.lam_m = float(lam_nm) * 1e-9
        self.n = int(grid_size)
        self.window_m = float(window_mm) * 1e-3
        self.dx_m = self.window_m / self.n
        self.apertures = dict(apertures or {})
        self.opd = opd
        self.n_slices = int(n_slices)
        self.pad = int(pad)
        self.X, self.Y = _grid2d(self.n, self.dx_m)
        self.z_c_m = critical_distance(self.n, self.dx_m, self.lam_m)
        self.aperture_notes = []
        self._build()

    def _aperture_radius_m(self, label):
        radius = self.apertures.get(label)
        if radius is None:
            return None
        return float(radius) * 1e-3

    def _element_steps(self, elem):
        """Action list for one element (in traversal order)."""
        label = elem.get("label")
        etype = elem.get("type")
        if etype not in _SUPPORTED:
            raise FoxLiError("Fox-Li cannot propagate element %r of "
                             "type %r" % (label, etype))
        if etype == "ElemEmptyRange":
            L = param_value_si(self.data, label, "L")
            return [("free", L, self.lam_m)]
        if etype == "ElemMediumRange":
            # C++ matrix [[1, L], [0, 1]] ignores n: a vacuum gap.
            L = param_value_si(self.data, label, "L")
            return [("free", L, self.lam_m)]
        if etype == "ElemPlate":
            L = param_value_si(self.data, label, "L")
            n = param_value_si(self.data, label, "n")
            return [("free", L, self.lam_m / n)]
        if etype in ("ElemFlatMirror", "ElemCurveMirror"):
            M_T, M_S = element_matrix(self.data, label)
            radius = self._aperture_radius_m(label)
            return [("mirror", float(M_T[1, 0]), float(M_S[1, 0]), radius)]
        if etype in ("ElemThermoLens", "ElemGrinLens"):
            L = param_value_si(self.data, label, "L")
            n = param_value_si(self.data, label, "n")
            if self.opd:
                f_th = float(self.opd["f_th_mm"]) * 1e-3
                c4 = float(self.opd.get("c4_per_m3") or 0.0)
                c6 = float(self.opd.get("c6_per_m5") or 0.0)
                r_max = self.opd.get("r_fit_max_mm")
                r_max_m = float(r_max) * 1e-3 if r_max is not None \
                    else None
            else:
                # Anchor OPD from the GRIN gamma, NOT the .rez F:
                # f_th = 1/(n2*L) with n2 = n0*gamma*|gamma|
                # (signed gamma: negative = defocusing).  The .rez F
                # is the C++ calc_focus definition 1/(tan(gL)*n*g)
                # (230 mm for TL1); the OPD-equivalent focal length
                # is 234.2 mm, the matrix -1/C is 236.3 mm.  Using
                # the .rez F here shifts the round-trip g by ~0.06
                # and the mode radius by ~35% (M1 finding).
                _L, _n0, gamma_T, gamma_S = element_grin_params(
                    self.data, label)

                def _f_split(gamma):
                    if gamma == 0.0:
                        return float("inf")
                    return 1.0 / (_n0 * gamma * abs(gamma) * _L)

                f_th = (_f_split(gamma_T), _f_split(gamma_S))
                c4 = 0.0
                c6 = 0.0
                r_max_m = None
            return [("crystal", L, n, f_th, c4, c6, r_max_m)]
        raise FoxLiError("unreachable element type %r" % (etype,))

    def _build(self):
        elems = [e for e in elements(self.data)
                 if not (isinstance(e, dict) and e.get("is_disabled"))]
        if len(elems) < 3:
            raise FoxLiError("Fox-Li needs >= 3 elements, got %d"
                             % len(elems))
        self.ref_label = elems[0].get("label")
        self.end_label = elems[-1].get("label")
        for elem in elems:
            label = elem.get("label")
            if label not in self.apertures:
                self.aperture_notes.append(
                    "no aperture data for %r: not truncated" % (label,))
        middle = elems[1:-1]
        self.forward_steps = []
        for elem in middle:
            self.forward_steps.append(
                (elem.get("label"), self._element_steps(elem)))
        self.forward_steps.append(
            (self.end_label, self._element_steps(elems[-1])))
        self.return_steps = [
            (label, steps)
            for label, steps in reversed(self.forward_steps[:-1])]
        self.first_steps = self._element_steps(elems[0])

    def _apply(self, E, steps):
        for kind, *args in steps:
            if kind == "free":
                z_m, lam_m = args
                E = propagate(E, z_m, lam_m, self.dx_m, pad=self.pad)
            elif kind == "mirror":
                c_T, c_S, radius = args
                E = mirror_phase(E, self.X, self.Y, c_T, c_S, self.lam_m)
                if radius is not None:
                    E = E * circular_aperture(self.X, self.Y, radius)
            elif kind == "crystal":
                L_m, n, f_th, c4, c6 = args[:5]
                r_max_m = args[5] if len(args) > 5 else None
                E = crystal_pass(E, L_m, n, f_th, c4, c6, self.lam_m,
                                 self.dx_m, n_slices=self.n_slices,
                                 r_max_m=r_max_m)
            else:  # pragma: no cover - _element_steps guards this
                raise FoxLiError("unknown step kind %r" % (kind,))
        return E

    def round_trip(self, E):
        """One round trip from the reference plane back to it."""
        for _label, steps in self.forward_steps:
            E = self._apply(E, steps)
        for _label, steps in self.return_steps:
            E = self._apply(E, steps)
        E = self._apply(E, self.first_steps)
        return E

    def propagate_to(self, E, label):
        """Field at the exit face of ``label`` (forward leg only)."""
        for leg_label, steps in self.forward_steps:
            E = self._apply(E, steps)
            if leg_label == label:
                return E
        raise FoxLiError("element %r is not on the forward leg" % (label,))

    def element_labels(self):
        """Labels on the forward leg, in order."""
        return [label for label, _ in self.forward_steps]


# --- Iteration --------------------------------------------------------------

def _inner(A, B):
    return complex(np.sum(np.conj(A) * B))


def foxli_iterate(operator, E0, max_rounds=1000, tol=1e-5,
                  check_every=1, plateau_rounds=50):
    """Iterate the round-trip operator to the self-reproducing mode.

    Dual convergence criterion (Gemini review SS2): both
    ``|gamma_n - gamma_{n-1}|/|gamma_n| < tol`` and the field-overlap
    defect ``1 - |<E_n, E_{n-1}>|/(||E_n|| ||E_{n-1}||) < tol``,
    with ``gamma_n = <E_{n-1}, E_n>/||E_{n-1}||^2`` (before
    renormalisation) and the round-trip diffraction loss
    ``L_diff = 1 - |gamma|^2``.  ``max_rounds`` caps the loop at
    1000.  If two modes with nearly equal loss beat against each
    other the overlap defect plateaus instead of converging: when
    it has not improved by more than 1% (relative) for
    ``plateau_rounds`` consecutive rounds *and* gamma is stable,
    the run stops early and reports ``converged=False`` with
    ``plateau=True`` -- the field is still returned, nothing is
    faked into a convergence.
    """
    E = np.asarray(E0, dtype=complex).copy()
    E = E / math.sqrt(float(np.sum(np.abs(E) ** 2)))
    gamma_prev = None
    defect_prev = None
    flat = 0
    history = []
    result = {"converged": False, "plateau": False, "rounds": 0,
              "gamma": None, "L_diff": None, "overlap_defect": None,
              "power_ratio": None, "history": history}
    for n in range(1, int(max_rounds) + 1):
        E_new = operator.round_trip(E)
        norm_old = float(np.sum(np.abs(E) ** 2))
        norm_new = float(np.sum(np.abs(E_new) ** 2))
        gamma = _inner(E, E_new) / norm_old
        overlap = abs(_inner(E, E_new)) / math.sqrt(norm_old * norm_new)
        defect = 1.0 - overlap
        dgamma = (abs(gamma - gamma_prev) / abs(gamma)
                  if gamma_prev is not None and abs(gamma) > 0 else None)
        power_ratio = norm_new / norm_old if norm_old > 0 else 0.0
        if n % check_every == 0 or n == int(max_rounds):
            history.append({"round": n, "gamma_re": gamma.real,
                            "gamma_im": gamma.imag,
                            "gamma_abs": abs(gamma),
                            "overlap_defect": defect,
                            "dgamma": dgamma,
                            "power_ratio": power_ratio})
        result.update({"rounds": n, "gamma": gamma,
                       "L_diff": 1.0 - abs(gamma) ** 2,
                       "overlap_defect": defect,
                       "power_ratio": power_ratio})
        if dgamma is not None and dgamma < tol and defect < tol:
            result["converged"] = True
            E = E_new / math.sqrt(norm_new)
            break
        # Plateau detection: gamma stable, overlap defect stuck.
        if dgamma is not None and dgamma < tol and defect_prev is not None:
            if defect >= 0.99 * defect_prev:
                flat += 1
            else:
                flat = 0
            if flat >= plateau_rounds:
                result["plateau"] = True
                E = E_new / math.sqrt(norm_new)
                break
        else:
            flat = 0
        gamma_prev = gamma
        defect_prev = defect
        E = E_new / math.sqrt(norm_new)
    result["field"] = E
    return result


# --- High-level report ------------------------------------------------------

def opd_f_th_to_cli_F(f_th_mm, data, label):
    """Convert an OPD-equivalent ``f_th`` [mm] to the CLI ``.rez`` F [mm].

    The OPD quadratic ``-r^2/(2*f_th)`` is the physical thermal
    lens (``f_th = 1/(n2*L)``, ``n2 = n0*gamma^2``); the ``.rez``
    ``F`` is the C++ ``calc_focus`` definition
    ``F = 1/(tan(gamma*L)*n*gamma)``.  The two differ by ~1% for
    the user's TL1 (f_th 234.2 mm vs F 230 mm at the anchor), so
    the initial Fox-Li field for an ``opd`` run must come from a
    CLI evaluation with the crystal's ``F`` overridden to this
    value -- starting from the anchor cavity's Gaussian instead
    leaves the iteration a superposition of the thermal cavity's
    modes, and a lossless round-trip operator has no differential
    loss to select one (power iteration on a unitary operator does
    not converge).  Negative ``f_th`` (defocusing) gives a
    negative ``F``; ``inf`` gives ``inf``.
    """
    f_th = float(f_th_mm) * 1e-3
    if not math.isfinite(f_th):
        return float("inf")
    n0 = param_value_si(data, label, "n")
    L = param_value_si(data, label, "L")
    if f_th > 0.0:
        gamma = 1.0 / math.sqrt(n0 * f_th * L)
        F = 1.0 / (math.tan(gamma * L) * n0 * gamma)
    else:
        kappa = 1.0 / math.sqrt(n0 * abs(f_th) * L)
        F = -1.0 / (math.tanh(kappa * L) * n0 * kappa)
    return F * 1e3


def resolve_foxli(data, eng, binary=None):
    """Build a :class:`CavityOperator` + initial field from .rez data.

    Returns ``(operator, E0, info)``.  The initial Gaussian uses the
    CLI beam at the reference element; apertures come from the
    side-car ``elements`` ``aperture_diameter_mm`` (overridden by
    ``foxli.apertures`` in mm radius); the crystal OPD comes from
    ``foxli.opd`` when present, else the GRIN anchor OPD
    (``f_th = 1/(n2*L)`` from the element's gamma, not the
    ``.rez`` ``F`` -- see :func:`crystal_pass`).  When an ``opd``
    is present the initial Gaussian is the CLI beam of the cavity
    with the crystal's ``F`` overridden to the value equivalent
    to the OPD's ``f_th`` (see :func:`opd_f_th_to_cli_F`): the
    anchor cavity's Gaussian is not the thermal cavity's
    eigenmode.  ``binary`` selects the headless binary (default
    build).
    """
    from .cli import DEFAULT_BINARY, run_headless_file  # deferred: avoids a cycle
    foxli = (eng or {}).get("foxli") or {}
    if not isinstance(foxli, dict):
        raise FoxLiError("foxli section is not an object")
    lam = wavelength_nm(data, foxli)
    grid_size = int(foxli.get("grid_size") or 256)
    window_mm = float(foxli.get("window_mm") or 8.0)
    apertures = {}
    for label, spec in ((eng or {}).get("elements") or {}).items():
        if isinstance(spec, dict) and spec.get("aperture_diameter_mm"):
            apertures[label] = float(spec["aperture_diameter_mm"]) / 2.0
    for label, radius in (foxli.get("apertures") or {}).items():
        apertures[label] = float(radius)
    opd_in = foxli.get("opd")
    opd = None
    if opd_in is not None:
        opd = {"f_th_mm": float(opd_in["f_th_mm"]),
               "c4_per_m3": float(opd_in.get("c4_per_m3") or 0.0),
               "c6_per_m5": float(opd_in.get("c6_per_m5") or 0.0)}
        if opd_in.get("r_fit_max_mm") is not None:
            opd["r_fit_max_mm"] = float(opd_in["r_fit_max_mm"])
    operator = CavityOperator(
        data, lam_nm=lam, grid_size=grid_size, window_mm=window_mm,
        apertures=apertures, opd=opd,
        n_slices=int(foxli.get("n_slices") or 4))
    # Initial field from the CLI Gaussian solution at the reference plane.
    binary = binary if binary is not None else DEFAULT_BINARY
    mutations = None
    if opd is not None:
        # The operator's crystal carries the OPD's f_th, not the
        # .rez F: override the crystal F to the equivalent value so
        # the initial Gaussian is this cavity's eigenmode.
        overrides = {}
        for elem in elements(data):
            if elem.get("type") in ("ElemThermoLens", "ElemGrinLens"):
                F_cli = opd_f_th_to_cli_F(opd["f_th_mm"], data,
                                          elem.get("label"))
                if math.isfinite(F_cli):
                    overrides[elem.get("label")] = {"F": F_cli}
        if overrides:
            mutations = [{"id": 0, "overrides": overrides}]
    result = run_headless_file(
        data.get("_rez_path"), mutations=mutations, binary=binary
        )["results"][0] if data.get("_rez_path") else None
    if result is None:
        raise FoxLiError("resolve_foxli needs data['_rez_path'] to run "
                         "the CLI for the initial Gaussian")
    if not result.get("ok") or not result.get("stable"):
        raise FoxLiError("CLI reports the cavity unstable: Fox-Li has "
                         "no confined eigenmode")
    w_T_mm, w_S_mm, R_T_mm, R_S_mm = beam_entry(result, operator.ref_label)
    E0 = initial_field(
        operator.n, operator.dx_m,
        w_T_mm * 1e-3, w_S_mm * 1e-3,
        R_T_mm * 1e-3 if R_T_mm is not None else None,
        R_S_mm * 1e-3 if R_S_mm is not None else None,
        operator.lam_m,
        noise_frac=float(foxli.get("noise_frac", 0.05)),
        seed=int(foxli.get("seed", 0)))
    info = {"wavelength_nm": lam, "grid_size": grid_size,
            "window_mm": window_mm, "dx_um": operator.dx_m * 1e6,
            "z_c_mm": operator.z_c_m * 1e3,
            "cli_w_T_mm": w_T_mm, "cli_w_S_mm": w_S_mm,
            "cli_R_T_mm": R_T_mm, "cli_R_S_mm": R_S_mm,
            "apertures_mm": apertures, "opd": opd,
            "aperture_notes": operator.aperture_notes}
    return operator, E0, info


def foxli_report(data, eng, binary=None, max_rounds=None, tol=None):
    """Run Fox-Li on one cavity; returns a JSON-able report dict.

    ``data`` must carry ``"_rez_path"`` (see :func:`resolve_foxli`).
    ``max_rounds``/``tol`` override the side-car values.  The
    converged (or plateau) field is propagated along the forward leg
    and second moments are reported at every element exit, so the
    Fox-Li beam can be compared with the CLI Gaussian beam element
    by element.
    """
    from .cli import DEFAULT_BINARY, run_headless_file  # deferred: avoids a cycle
    foxli = (eng or {}).get("foxli") or {}
    operator, E0, info = resolve_foxli(data, eng, binary=binary)
    rounds = int(max_rounds if max_rounds is not None
                 else foxli.get("max_rounds") or 1000)
    tolerance = float(tol if tol is not None
                      else foxli.get("tol") or 1e-5)
    run = foxli_iterate(operator, E0, max_rounds=rounds, tol=tolerance)
    E = run["field"]
    mom = second_moments(E, operator.dx_m, operator.lam_m)
    # Per-element beam on the forward leg (CLI comparison).  Each
    # propagate_to replays the leg from the reference plane.
    binary = binary if binary is not None else DEFAULT_BINARY
    result = run_headless_file(
        data["_rez_path"], binary=binary)["results"][0]
    beam = []
    for label in operator.element_labels():
        E_at = operator.propagate_to(E, label)
        m_at = second_moments(E_at, operator.dx_m, operator.lam_m)
        try:
            cw_T, cw_S, _, _ = beam_entry(result, label)
        except (QevolveError, KeyError, TypeError):
            cw_T = cw_S = None
        beam.append({"label": label, "w_T_mm": m_at["w_T_mm"],
                     "w_S_mm": m_at["w_S_mm"],
                     "M2_T": m_at["M2_T"], "M2_S": m_at["M2_S"],
                     "R_T_mm": m_at["R_T_mm"], "R_S_mm": m_at["R_S_mm"],
                     "cli_w_T_mm": cw_T, "cli_w_S_mm": cw_S})
    gamma = run["gamma"]
    return {
        "reference_element": operator.ref_label,
        "wavelength_nm": info["wavelength_nm"],
        "grid": {"N": operator.n, "window_mm": info["window_mm"],
                 "dx_um": info["dx_um"], "z_c_mm": info["z_c_mm"]},
        "converged": run["converged"],
        "plateau": run["plateau"],
        "rounds": run["rounds"],
        "max_rounds": rounds,
        "tol": tolerance,
        "gamma": {"re": gamma.real, "im": gamma.imag,
                  "abs": abs(gamma)} if gamma is not None else None,
        "L_diff": run["L_diff"],
        "power_ratio": run["power_ratio"],
        "overlap_defect": run["overlap_defect"],
        "w_T_mm": mom["w_T_mm"],
        "w_S_mm": mom["w_S_mm"],
        "M2_T": mom["M2_T"],
        "M2_S": mom["M2_S"],
        "R_T_mm": mom["R_T_mm"],
        "R_S_mm": mom["R_S_mm"],
        "cli_w_T_mm": info["cli_w_T_mm"],
        "cli_w_S_mm": info["cli_w_S_mm"],
        "beam": beam,
        "apertures_mm": info["apertures_mm"],
        "aperture_notes": info["aperture_notes"],
        "opd": info["opd"],
        "field": E,
        "history": run["history"],
    }
