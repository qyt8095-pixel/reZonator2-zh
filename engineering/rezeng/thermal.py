"""Phase 4 block 2: steady-state thermal conduction in a laser crystal.

Solves the steady-state Poisson heat equation ``div(k grad T) + Q = 0``
for an end-pumped rod in cylindrical ``(r, z)`` coordinates (finite
differences, ``scipy.sparse.linalg.spsolve``) and for a slab in 2D
Cartesian ``(x, y)`` coordinates.  From the temperature field it derives
the thermal-lens OPD (fitted ``OPD(r) = c0 + c2 r^2 + c4 r^4 + c6 r^6``,
``f_th = -1/(2 c2)``) and the end-face bulge, which feed the Phase 4
Fox-Li phase plate; the stress/fracture evaluation lives in
:mod:`rezeng.fracture`.

Heat-source normalisation (a correction to the Gemini review)
------------------------------------------------------------
The review wrote the Gaussian pump heat source as
``Q = eta_h*alpha*P / (2*pi*w_p^2) * exp(-2 r^2/w_p^2)``.  That
integrates over the cross-section to ``eta_h*P_abs/4``, not
``eta_h*P_abs``: ``int_0^inf exp(-2r^2/w^2) 2*pi*r dr = pi*w^2/2``.
The correct Gaussian (1/e^2 radius ``w_p``) normalisation is the
standard beam-intensity one,

    Q(r,z) = eta_h * alpha(z) * P_inc(z) * (2/(pi*w_p(z)^2))
             * exp(-2 r^2/w_p(z)^2),
    P_inc(z) = P_pump * exp(-int_0^z alpha dz'),

so that ``int Q dV = eta_h * P_abs`` exactly.  A test locks the
energy balance; the review's prefactor is off by 4x.

Thermal-lens factor: Gaussian vs top-hat pump
---------------------------------------------
For a Gaussian pump the on-axis OPD curvature is (adiabatic end
faces, ``dn/dT`` term only; the axial second derivative integrates
to zero over the rod, see :func:`analytic_f_th_gaussian`)

    1/f = eta_h * P_abs * (dn/dT) / (pi * K * w_p^2).

The Phase 2 physics estimate ``kappa = eta_h*(dn/dT)/(2*pi*K*w_p^2)``
is the *top-hat* result (uniform pump of radius ``w_p`` gives half
the on-axis curvature).  The two differ by exactly 2x; the
closed-loop test in ``tests/test_phase4_block2.py`` compares the FEA
``f_th`` against the Gaussian analytic value, and the demo reports
the Phase 2 linear-model comparison separately with this caveat.

Discretisation
--------------
Node-centred finite differences on ``r_i = i*dr`` (``i = 0..Nr-1``,
``r = R0`` on the last node) and ``z_j = j*dz``.  The radial operator
is written in conservative form; at ``r = 0`` L'Hopital gives
``(d2T/dr2 + (1/r) dT/dr)|_0 = 2 d2T/dr2 ~ 4 (T_1 - T_0)/dr^2``.
Axial conductivity uses the harmonic mean at ``z`` faces, which is
what makes end-cap (undoped/doped) interfaces correct.  Boundary
conditions are imposed by ghost-node elimination (Robin) or by
identity rows (Dirichlet); end faces default to adiabatic.

No invented defaults: the material library holds typical literature
values, applied only when the side-car names the material (the same
pattern as ``rezeng.shg.MATERIALS`` + ``fill_typical``); the pump
power, heat fraction, absorption, pump radius and the contact
conductance ``h`` must come from the side-car.
"""

import math

import numpy as np
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve

from .power import pump_radius

__all__ = [
    "ThermalError", "MATERIALS_THERMAL", "THERMAL_MATERIAL_ALIASES",
    "material_thermal",
    "fill_thermal_typical", "heat_source", "heat_source_power_W",
    "solve_poisson_cyl", "solve_poisson_slab", "solve_rod",
    "bulge_displacement", "opd_from_field", "fit_opd",
    "analytic_f_th_gaussian", "phase_plate", "resolve_thermal",
    "thermal_report",
]

#: Margin thresholds are defined in rezeng.fracture; kept here only as
#: documentation of the interface (fracture.py owns the verdict).


class ThermalError(ValueError):
    """Raised when a thermal calculation cannot be set up."""


# --- Material library --------------------------------------------------------
# Typical literature values at ~300 K.  These are reference numbers for
# a material the user names explicitly; they are NOT measured values for
# the user's crystal.  Sources: Koechner, "Solid-State Laser
# Engineering"; Innocenzi et al., J. Appl. Phys. (YVO4 dn/dT,
# expansion); Castech/YVO4 data sheets; YAG handbook values.
# Nd:YVO4 is strongly anisotropic: alpha_c is ~2.6x alpha_a, and
# dn/dT differs between the o- and e-ray.  The solver is isotropic in
# k and dn/dT (e-ray for pi-polarised 1064 nm) and brackets the stress
# with alpha_a / alpha_c (see rezeng.fracture).
MATERIALS_THERMAL = {
    "Nd:YVO4": {
        "k_W_per_mK": 5.2, "dn_dT_e_per_K": 3.9e-6,
        "dn_dT_o_per_K": 8.5e-6, "alpha_a_per_K": 4.4e-6,
        "alpha_c_per_K": 11.4e-6, "E_GPa": 133.0, "nu": 0.33,
        "sigma_fracture_MPa": 53.0, "n_e_1064": 2.165,
        "source": "Koechner; Innocenzi et al.; Castech data sheet",
    },
    "Yb:YVO4": {
        "k_W_per_mK": 5.2, "dn_dT_e_per_K": 3.9e-6,
        "dn_dT_o_per_K": 8.5e-6, "alpha_a_per_K": 4.4e-6,
        "alpha_c_per_K": 11.4e-6, "E_GPa": 133.0, "nu": 0.33,
        "sigma_fracture_MPa": 53.0, "n_e_1064": 2.165,
        "source": "YVO4 host values (same as Nd:YVO4)",
    },
    "Nd:YAG": {
        "k_W_per_mK": 11.0, "dn_dT_e_per_K": 7.3e-6,
        "dn_dT_o_per_K": 7.3e-6, "alpha_a_per_K": 7.5e-6,
        "alpha_c_per_K": 7.5e-6, "E_GPa": 310.0, "nu": 0.25,
        "sigma_fracture_MPa": 200.0, "n_e_1064": 1.82,
        "source": "Koechner; YAG handbook values",
    },
    "Yb:YAG": {
        "k_W_per_mK": 11.0, "dn_dT_e_per_K": 7.3e-6,
        "dn_dT_o_per_K": 7.3e-6, "alpha_a_per_K": 7.5e-6,
        "alpha_c_per_K": 7.5e-6, "E_GPa": 310.0, "nu": 0.25,
        "sigma_fracture_MPa": 200.0, "n_e_1064": 1.82,
        "source": "YAG host values (same as Nd:YAG)",
    },
    "Ti:sapphire": {
        "k_W_per_mK": 33.0, "dn_dT_e_per_K": 13.0e-6,
        "dn_dT_o_per_K": 13.0e-6, "alpha_a_per_K": 5.0e-6,
        "alpha_c_per_K": 5.0e-6, "E_GPa": 345.0, "nu": 0.25,
        "sigma_fracture_MPa": 400.0, "n_e_1064": 1.76,
        "source": "Sapphire handbook values",
    },
}

#: Aliases accepted for thermal material IDs.
THERMAL_MATERIAL_ALIASES = {
    "YVO4": "Nd:YVO4", "YAG": "Nd:YAG",
}


def material_thermal(material):
    """Reference thermal properties for a library material (a copy).

    Raises :class:`ThermalError` for an unknown material.
    """
    key = THERMAL_MATERIAL_ALIASES.get(material, material)
    spec = MATERIALS_THERMAL.get(key)
    if spec is None:
        raise ThermalError(
            "unknown thermal material %r (library: %s)"
            % (material, ", ".join(sorted(MATERIALS_THERMAL))))
    return dict(spec)


def fill_thermal_typical(thermal):
    """Fill a side-car ``thermal`` dict's missing material numbers.

    Only fields absent from ``thermal["material_overrides"]`` (or the
    top level) are filled, from the named material's library entry.
    Returns a new dict; the input is not modified.
    """
    out = dict(thermal)
    material = out.get("material")
    if material is None:
        return out
    ref = material_thermal(material)
    overrides = dict(out.get("material_overrides") or {})
    mapping = {
        "k_W_per_mK": ref["k_W_per_mK"],
        "dn_dT_per_K": ref["dn_dT_e_per_K"],
        "alpha_a_per_K": ref["alpha_a_per_K"],
        "alpha_c_per_K": ref["alpha_c_per_K"],
        "E_GPa": ref["E_GPa"], "nu": ref["nu"],
        "sigma_fracture_MPa": ref["sigma_fracture_MPa"],
        "n_1064": ref["n_e_1064"],
    }
    for key, value in mapping.items():
        if key not in overrides:
            overrides[key] = value
    out["material_overrides"] = overrides
    out["_material_source"] = ref["source"]
    return out


# --- Heat source ---------------------------------------------------------------

def heat_source(r_m, z_m, P_pump_W, alpha_per_m, w_p_m, eta_h,
                profile="gaussian"):
    """Volumetric heat source ``Q`` [W/m^3], shape ``(len(r), len(z))``.

    ``alpha_per_m`` and ``w_p_m`` are per-``z`` arrays (absorption and
    pump 1/e^2 radius at each depth).  ``P_pump_W`` is the pump power
    entering the crystal.  Gaussian profile (the default) is
    ``Q = eta_h*alpha*P_inc(z)*(2/(pi*w_p^2))*exp(-2r^2/w_p^2)`` with
    ``P_inc(z) = P_pump*exp(-int_0^z alpha dz')``; top-hat is uniform
    inside ``r <= w_p``.  Both integrate (over an unbounded radius)
    to ``eta_h * P_abs`` exactly.
    """
    r = np.asarray(r_m, dtype=float)
    z = np.asarray(z_m, dtype=float)
    alpha = np.asarray(alpha_per_m, dtype=float)
    w_p = np.asarray(w_p_m, dtype=float)
    if r.ndim != 1 or z.ndim != 1:
        raise ThermalError("heat_source needs 1-D r and z grids")
    if alpha.shape != z.shape or w_p.shape != z.shape:
        raise ThermalError("alpha_per_m / w_p_m must match the z grid")
    if np.any(alpha < 0) or np.any(w_p <= 0):
        raise ThermalError("alpha_per_m must be >= 0 and w_p_m > 0")
    if not (0.0 < eta_h <= 1.0):
        raise ThermalError("eta_h must be in (0, 1], got %r" % (eta_h,))
    # Cumulative absorption: P_inc(z)/P_pump = exp(-int_0^z alpha dz').
    dz = np.diff(z)
    cum = np.zeros_like(z)
    cum[1:] = np.cumsum(0.5 * (alpha[:-1] + alpha[1:]) * dz)
    p_inc = float(P_pump_W) * np.exp(-cum)          # [Nz]
    rate = eta_h * alpha * p_inc                    # heat per unit length
    if profile == "gaussian":
        g = (2.0 / (math.pi * w_p ** 2)) \
            * np.exp(-2.0 * (r[:, None] ** 2) / (w_p[None, :] ** 2))
    elif profile == "tophat":
        g = np.where(r[:, None] <= w_p[None, :],
                     1.0 / (math.pi * w_p[None, :] ** 2), 0.0)
    else:
        raise ThermalError("unknown pump profile %r (gaussian/tophat)"
                           % (profile,))
    return rate[None, :] * g


def heat_source_power_W(Q, r_m, z_m):
    """Total heat power [W] in a ``Q`` array (trapezoid in r and z)."""
    r = np.asarray(r_m, dtype=float)
    z = np.asarray(z_m, dtype=float)
    return float(np.trapz(np.trapz(Q * 2.0 * math.pi * r[:, None],
                                           r, axis=0), z))


# --- Cylindrical (r, z) Poisson solver -----------------------------------------

def solve_poisson_cyl(Q, r_m, z_m, k_z, side=("robin", 5000.0, 20.0),
                      ends=("adiabatic",), T_ref_C=20.0):
    """Steady ``div(k grad T) + Q = 0`` on a rod, node-centred FD.

    ``Q`` is ``(Nr, Nz)`` [W/m^3]; ``r_m`` / ``z_m`` are the 1-D
    grids (``r[0] = 0``, ``r[-1] = R0``; ``z[0] = 0``, ``z[-1] = L``);
    ``k_z`` is the conductivity [W/m/K] per ``z`` slice (scalar ok).
    ``side`` is ``("dirichlet", T)``, ``("robin", h, T_cool)`` or
    ``("adiabatic",)``; ``ends`` is ``("adiabatic",)``,
    ``("dirichlet", T)`` or ``("robin", h, T_cool)`` (same both ends).
    Returns ``T`` [degC], shape ``(Nr, Nz)``.

    ``T_ref_C`` is only used as the fallback coolant temperature
    when a Robin condition is given without one (never happens: the
    tuple carries it); it is not a hidden default for ``h``.
    """
    Q = np.asarray(Q, dtype=float)
    r = np.asarray(r_m, dtype=float)
    z = np.asarray(z_m, dtype=float)
    Nr, Nz = len(r), len(z)
    if Q.shape != (Nr, Nz):
        raise ThermalError("Q shape %s does not match grids (%d, %d)"
                           % (Q.shape, Nr, Nz))
    dr = float(r[1] - r[0]) if Nr > 1 else 0.0
    dz = float(z[1] - z[0]) if Nz > 1 else 0.0
    if Nr < 3 or Nz < 2 or dr <= 0 or dz <= 0:
        raise ThermalError("need Nr >= 3, Nz >= 2 with uniform grids")
    if not np.allclose(np.diff(r), dr) or not np.allclose(np.diff(z), dz):
        raise ThermalError("solve_poisson_cyl needs uniform r/z grids")
    k = np.full(Nz, float(k_z)) if np.isscalar(k_z) \
        else np.asarray(k_z, dtype=float)
    if k.shape != (Nz,) or np.any(k <= 0):
        raise ThermalError("k_z must be a positive scalar or per-z array")

    # Typical diagonal magnitude, used to scale Dirichlet rows: an
    # identity row (scale 1) next to interior rows (scale ~k/dr^2,
    # here ~1e10) wrecks the direct solver's accuracy.
    k_mean = float(np.mean(k))
    diag_scale = 4.0 * k_mean / dr ** 2 + 2.0 * k_mean / dz ** 2

    def idx(i, j):
        return j * Nr + i

    # Harmonic-mean conductivity at z faces: k_half[j] is between
    # nodes j and j+1 (length Nz-1); end faces reuse the edge value.
    k_half = np.empty(max(Nz - 1, 1))
    for j in range(Nz - 1):
        k_half[j] = 2.0 * k[j] * k[j + 1] / (k[j] + k[j + 1])

    n = Nr * Nz
    A = lil_matrix((n, n), dtype=float)
    b = np.zeros(n)

    def side_kind():
        return side[0] if side else "adiabatic"

    def ends_kind():
        return ends[0] if ends else "adiabatic"

    for j in range(Nz):
        kj = k[j]
        for i in range(Nr):
            row = idx(i, j)
            ri = r[i]
            # Dirichlet nodes: identity row, no stencil (clearing a
            # lil_matrix row by hand corrupts its parallel data list,
            # so Dirichlet is handled by skipping the stencil here).
            if i == Nr - 1 and side_kind() == "dirichlet":
                A[row, row] = diag_scale
                b[row] = diag_scale * float(side[1])
                continue
            if (j == 0 or j == Nz - 1) and ends_kind() == "dirichlet":
                A[row, row] = diag_scale
                b[row] = diag_scale * float(ends[1])
                continue
            # -- axial operator (same for every i) --
            # Coefficients for T[j-1], T[j], T[j+1] at fixed i.
            if Nz == 1:
                a_zm = a_z0 = a_zp = 0.0
                z_rhs = 0.0
            elif j == 0:
                kind = ends_kind()
                if kind == "adiabatic":
                    a_zm = 0.0
                    a_zp = (k_half[0] + kj) / dz ** 2
                    a_z0 = -a_zp
                    z_rhs = 0.0
                elif kind == "dirichlet":
                    a_zm = a_zp = a_z0 = 0.0
                    z_rhs = 0.0
                elif kind == "robin":
                    h, tc = float(ends[1]), float(ends[2])
                    a_zp = (k_half[0] + kj) / dz ** 2
                    a_z0 = -a_zp - 2.0 * h / dz
                    a_zm = 0.0
                    z_rhs = -2.0 * h * tc / dz
                else:
                    raise ThermalError("unknown ends BC %r" % (kind,))
            elif j == Nz - 1:
                kind = ends_kind()
                if kind == "adiabatic":
                    a_zm = (k_half[Nz - 2] + kj) / dz ** 2
                    a_zp = 0.0
                    a_z0 = -a_zm
                    z_rhs = 0.0
                elif kind == "dirichlet":
                    a_zm = a_zp = a_z0 = 0.0
                    z_rhs = 0.0
                elif kind == "robin":
                    h, tc = float(ends[1]), float(ends[2])
                    a_zm = (k_half[Nz - 2] + kj) / dz ** 2
                    a_z0 = -a_zm - 2.0 * h / dz
                    a_zp = 0.0
                    z_rhs = -2.0 * h * tc / dz
                else:
                    raise ThermalError("unknown ends BC %r" % (kind,))
            else:
                a_zm = k_half[j - 1] / dz ** 2
                a_zp = k_half[j] / dz ** 2
                a_z0 = -(a_zm + a_zp)
                z_rhs = 0.0
            # -- radial operator --
            if i == 0:
                # L'Hopital: 2 d2T/dr2 ~ 4 (T_1 - T_0)/dr^2.
                a_rm = 0.0
                a_rp = 4.0 * kj / dr ** 2
                a_r0 = -a_rp
                r_rhs = 0.0
            elif i == Nr - 1:
                kind = side_kind()
                if kind == "dirichlet":
                    a_rm = a_rp = a_r0 = 0.0
                    r_rhs = 0.0
                elif kind == "adiabatic":
                    a_rm = 2.0 * kj / dr ** 2
                    a_rp = 0.0
                    a_r0 = -a_rm
                    r_rhs = 0.0
                elif kind == "robin":
                    h, tc = float(side[1]), float(side[2])
                    a_rm = 2.0 * kj / dr ** 2
                    a_rp = 0.0
                    a_r0 = -a_rm - 2.0 * h / dr - h / ri
                    r_rhs = -(2.0 * h / dr + h / ri) * tc
                else:
                    raise ThermalError("unknown side BC %r" % (kind,))
            else:
                a_rp = (r[i] + 0.5 * dr) * kj / (ri * dr ** 2)
                a_rm = (r[i] - 0.5 * dr) * kj / (ri * dr ** 2)
                a_r0 = -(a_rp + a_rm)
                r_rhs = 0.0
            A[row, row] = a_r0 + a_z0
            if a_rm:
                A[row, idx(i - 1, j)] += a_rm
            if a_rp:
                A[row, idx(i + 1, j)] += a_rp
            if a_zm:
                A[row, idx(i, j - 1)] += a_zm
            if a_zp:
                A[row, idx(i, j + 1)] += a_zp
            b[row] = -Q[i, j] + r_rhs + z_rhs
    T = spsolve(A.tocsc(), b)
    if np.any(~np.isfinite(T)):
        raise ThermalError("temperature solve produced non-finite values")
    return T.reshape((Nz, Nr)).T


# --- 2D slab (x, y) Poisson solver ---------------------------------------------

def solve_poisson_slab(Q, x_m, y_m, k_W_per_mK,
                       top_bottom=("robin", 5000.0, 20.0),
                       sides=("adiabatic",)):
    """Steady ``k lap(T) + Q = 0`` on a slab cross-section.

    ``Q`` is ``(Nx, Ny)`` [W/m^3]; ``x_m`` spans the slab width,
    ``y_m`` the thickness.  The large faces (``y``) are cooled
    (``("robin", h, T_cool)`` / ``("dirichlet", T)``), the side faces
    (``x``) are adiabatic by default.  Returns ``T`` [degC],
    shape ``(Nx, Ny)``.
    """
    Q = np.asarray(Q, dtype=float)
    x = np.asarray(x_m, dtype=float)
    y = np.asarray(y_m, dtype=float)
    Nx, Ny = len(x), len(y)
    if Q.shape != (Nx, Ny):
        raise ThermalError("Q shape %s does not match grids (%d, %d)"
                           % (Q.shape, Nx, Ny))
    dx = float(x[1] - x[0]) if Nx > 1 else 0.0
    dy = float(y[1] - y[0]) if Ny > 1 else 0.0
    if Nx < 3 or Ny < 3 or dx <= 0 or dy <= 0:
        raise ThermalError("need Nx, Ny >= 3 with uniform grids")
    if not np.allclose(np.diff(x), dx) or not np.allclose(np.diff(y), dy):
        raise ThermalError("solve_poisson_slab needs uniform x/y grids")
    k = float(k_W_per_mK)
    if k <= 0:
        raise ThermalError("k must be positive")
    # Typical diagonal magnitude for Dirichlet-row scaling (see the
    # cylindrical solver).
    diag_scale = 2.0 * k / dx ** 2 + 2.0 * k / dy ** 2

    def idx(i, j):
        return j * Nx + i

    n = Nx * Ny
    A = lil_matrix((n, n), dtype=float)
    b = np.zeros(n)

    def face_coeffs(coord, d, kind, h, tc):
        """``(inner, self, rhs)`` for a boundary node on one axis.

        ``coord`` is the node's coordinate on that axis (only used
        for the Robin 1/r-style term -- none here, Cartesian), ``d``
        the grid step.
        """
        if kind == "dirichlet":
            return None  # identity row, handled by caller
        if kind == "adiabatic":
            return (2.0 * k / d ** 2, -2.0 * k / d ** 2, 0.0)
        if kind == "robin":
            return (2.0 * k / d ** 2, -2.0 * k / d ** 2 - 2.0 * h / d,
                    -2.0 * h * tc / d)
        raise ThermalError("unknown slab BC %r" % (kind,))

    for j in range(Ny):
        for i in range(Nx):
            row = idx(i, j)
            # Dirichlet nodes: identity row, no stencil (see the
            # cylindrical solver note on lil_matrix row clearing).
            if (i == 0 or i == Nx - 1) and sides[0] == "dirichlet":
                A[row, row] = diag_scale
                b[row] = diag_scale * float(sides[1])
                continue
            if (j == 0 or j == Ny - 1) and top_bottom[0] == "dirichlet":
                A[row, row] = diag_scale
                b[row] = diag_scale * float(top_bottom[1])
                continue
            # x direction
            if i == 0 or i == Nx - 1:
                kind = sides[0]
                h = float(sides[1]) if kind == "robin" else 0.0
                tc = float(sides[2]) if kind == "robin" else 0.0
                c_in, c_self, c_rhs = face_coeffs(x[i], dx, kind, h, tc)
                a_xm = a_xp = 0.0
                a_x0 = c_self
                x_rhs = c_rhs
                nb = idx(1, j) if i == 0 else idx(Nx - 2, j)
                A[row, nb] += c_in
            else:
                a_xm = a_xp = k / dx ** 2
                a_x0 = -2.0 * k / dx ** 2
                x_rhs = 0.0
                A[row, idx(i - 1, j)] += a_xm
                A[row, idx(i + 1, j)] += a_xp
            # y direction
            if j == 0 or j == Ny - 1:
                kind = top_bottom[0]
                h = float(top_bottom[1]) if kind == "robin" else 0.0
                tc = float(top_bottom[2]) if kind == "robin" else 0.0
                c_in, c_self, c_rhs = face_coeffs(y[j], dy, kind, h, tc)
                a_y0 = c_self
                y_rhs = c_rhs
                nb = idx(i, 1) if j == 0 else idx(i, Ny - 2)
                A[row, nb] += c_in
            else:
                a_y0 = -2.0 * k / dy ** 2
                y_rhs = 0.0
                A[row, idx(i, j - 1)] += k / dy ** 2
                A[row, idx(i, j + 1)] += k / dy ** 2
            A[row, row] = a_x0 + a_y0
            b[row] = -Q[i, j] + x_rhs + y_rhs
    T = spsolve(A.tocsc(), b)
    if np.any(~np.isfinite(T)):
        raise ThermalError("slab solve produced non-finite values")
    return T.reshape((Ny, Nx)).T


# --- Rod driver (segments, pump, solve) -----------------------------------------

def _segments_to_arrays(segments, z_m, default_alpha_per_m, default_k):
    """``(alpha_per_m, k_W_per_mK)`` per z node from end-cap segments.

    ``segments`` is a list of ``{"z0_mm", "z1_mm", "alpha_per_cm",
    "k_W_per_mK"}`` (either absorption may be omitted, meaning the
    default).  Nodes outside every segment take the defaults.
    """
    Nz = len(z_m)
    alpha = np.full(Nz, float(default_alpha_per_m))
    k = np.full(Nz, float(default_k))
    for seg in segments or []:
        z0 = float(seg.get("z0_mm", 0.0)) * 1e-3
        z1 = float(seg.get("z1_mm", 0.0)) * 1e-3
        mask = (z_m >= z0) & (z_m <= z1)
        if "alpha_per_cm" in seg and seg["alpha_per_cm"] is not None:
            alpha[mask] = float(seg["alpha_per_cm"]) * 100.0
        if "k_W_per_mK" in seg and seg["k_W_per_mK"] is not None:
            k[mask] = float(seg["k_W_per_mK"])
    return alpha, k


def solve_rod(spec):
    """Solve the temperature field of an end-pumped rod.

    ``spec`` (all SI except where noted)::

        {"R0_m", "L_m", "material" (or explicit "k_W_per_mK" etc.),
         "P_pump_W", "eta_p", "eta_h", "alpha_per_m" (or "segments"),
         "w_p0_m", "Mp2", "lambda_p_m", "z_p0_m", "profile",
         "h_W_per_m2K", "T_cool_C", "end_faces" ("adiabatic"/"robin"/"dirichlet"),
         "Nr", "Nz"}

    Missing material numbers are taken from the named material's
    library entry (``fill_thermal_typical`` semantics); the pump
    power, ``eta_h``, absorption and ``h`` have no defaults and raise
    :class:`ThermalError` when absent.  Returns a dict with the
    ``T`` field [degC] ``(Nr, Nz)``, the ``r``/``z`` grids [m],
    ``P_abs_W``, ``P_heat_W``, ``Q`` and the resolved material dict.
    """
    for key in ("P_pump_W", "eta_h", "h_W_per_m2K"):
        if spec.get(key) is None:
            raise ThermalError("thermal spec needs %r (no default)"
                               % (key,))
    mat = {}
    if spec.get("material"):
        mat = material_thermal(spec["material"])
    for key in ("k_W_per_mK", "dn_dT_per_K", "alpha_a_per_K",
                "alpha_c_per_K", "E_GPa", "nu", "sigma_fracture_MPa",
                "n_1064"):
        if spec.get(key) is not None:
            mat[key] = float(spec[key])
    if "dn_dT_per_K" not in mat and "dn_dT_e_per_K" in mat:
        mat["dn_dT_per_K"] = mat["dn_dT_e_per_K"]
    if "n_1064" not in mat and "n_e_1064" in mat:
        mat["n_1064"] = mat["n_e_1064"]
    if spec.get("alpha_per_m") is None and not spec.get("segments"):
        raise ThermalError("thermal spec needs alpha_per_m or segments")
    R0 = float(spec["R0_m"])
    L = float(spec["L_m"])
    Nr = int(spec.get("Nr", 60))
    Nz = int(spec.get("Nz", 150))
    r = np.linspace(0.0, R0, Nr)
    z = np.linspace(0.0, L, Nz)
    if "k_W_per_mK" not in mat:
        raise ThermalError("thermal spec needs a material (library) or "
                           "an explicit k_W_per_mK")
    alpha, k = _segments_to_arrays(
        spec.get("segments"),
        z, float(spec.get("alpha_per_m", 0.0)) if spec.get("alpha_per_m")
        is not None else 0.0,
        mat["k_W_per_mK"])
    if spec.get("alpha_per_m") is not None:
        base = float(spec["alpha_per_m"])
        if not spec.get("segments"):
            alpha[:] = base
    # Pump radius vs depth (Phase 2 pump model, same w_p0/Mp2/z_p0).
    pump_params = {
        "w_p0": float(spec["w_p0_m"]), "Mp2": float(spec.get("Mp2", 1.0)),
        "lambda_p_m": float(spec.get("lambda_p_m", 808e-9)),
        "z_p0": float(spec.get("z_p0_m", 0.5 * L)),
    }
    w_p = pump_radius(pump_params, z)
    P_in = float(spec["P_pump_W"]) * float(spec.get("eta_p", 1.0))
    Q = heat_source(r, z, P_in, alpha, w_p, float(spec["eta_h"]),
                    profile=spec.get("profile", "gaussian"))
    P_abs = P_in * (1.0 - math.exp(-float(np.trapz(alpha, z))))
    # Conserve energy exactly on the discrete grid: the trapezoid
    # integral of a narrow Gaussian (w_p ~ 200 um on dr ~ 83 um) or
    # of a top-hat edge underestimates the heat by a few percent.
    # Rescale Q (shape preserved) so its discrete integral equals
    # eta_h * P_abs.  Assumes the pump is contained in the rod
    # (R0 >> w_p); a pump spilling past R0 would need the radial
    # truncation factor in the target as well.
    P_heat_discrete = heat_source_power_W(Q, r, z)
    target_heat = float(spec["eta_h"]) * P_abs
    if P_heat_discrete > 0 and target_heat > 0:
        Q = Q * (target_heat / P_heat_discrete)
    P_heat = heat_source_power_W(Q, r, z)
    h = float(spec["h_W_per_m2K"])
    T_cool = float(spec.get("T_cool_C", 20.0))
    ends = spec.get("end_faces", "adiabatic")
    if ends == "adiabatic":
        ends_bc = ("adiabatic",)
    elif ends == "robin":
        ends_bc = ("robin", h, T_cool)
    elif ends == "dirichlet":
        ends_bc = ("dirichlet", T_cool)
    else:
        raise ThermalError("unknown end_faces %r" % (ends,))
    T = solve_poisson_cyl(Q, r, z, k, side=("robin", h, T_cool),
                          ends=ends_bc)
    return {"T_C": T, "r_m": r, "z_m": z, "Q_W_per_m3": Q,
            "alpha_per_m": alpha, "k_W_per_mK": k,
            "P_abs_W": P_abs, "P_heat_W": P_heat,
            "P_pump_inc_W": P_in, "w_p_m": w_p, "material": mat,
            "T_cool_C": T_cool, "R0_m": R0, "L_m": L}


# --- Bulge, OPD, thermal-lens fit ----------------------------------------------

def bulge_displacement(T_C, r_m, z_m, alpha_T_per_K, nu, z_eff_m=None,
                       T_ref_C=None):
    """End-face axial displacement ``u_z(r)`` [m].

    ``u_z(r) = (1+nu)*alpha_T*int_0^{z_eff} (T - T_ref) dz`` with
    ``z_eff ~ R0`` by default (the heated zone that can push the face
    out; the rest of the rod is constrained radially).  ``T_ref`` is
    the cold-crystal temperature (default: the field minimum).
    """
    T = np.asarray(T_C, dtype=float)
    r = np.asarray(r_m, dtype=float)
    z = np.asarray(z_m, dtype=float)
    if T_ref_C is None:
        T_ref_C = float(np.min(T))
    if z_eff_m is None:
        z_eff_m = float(r[-1])
    # Integrate up to exactly z_eff (interpolating the last partial
    # interval); truncating at the last node below z_eff would lose
    # up to half a grid step of heated length.
    z_eff = float(z_eff_m)
    if z_eff <= z[0]:
        integ = np.zeros(T.shape[0])
    elif z_eff >= z[-1]:
        integ = np.trapz(T - T_ref_C, z, axis=1)
    else:
        mask = z <= z_eff
        z_int = np.concatenate([z[mask], [z_eff]])
        t_eff = np.array([np.interp(z_eff, z, T[i, :])
                          for i in range(T.shape[0])])
        T_int = np.concatenate([T[:, mask], t_eff[:, None]], axis=1)
        integ = np.trapz(T_int - T_ref_C, z_int, axis=1)
    return (1.0 + float(nu)) * float(alpha_T_per_K) * integ


def opd_from_field(T_C, r_m, z_m, dn_dT_per_K, n_1064,
                   T_ref_C=None, bulge_m=None):
    """``OPD(r)`` [m] = ``int (dn/dT) dT dz + (n-1) u_z(r)``.

    ``bulge_m`` is the ``u_z(r)`` array (or ``None`` to omit the
    bulge term); pass the dn/dT-only result when comparing against
    the analytic thermal-lens value.
    """
    T = np.asarray(T_C, dtype=float)
    r = np.asarray(r_m, dtype=float)
    z = np.asarray(z_m, dtype=float)
    if T_ref_C is None:
        T_ref_C = float(np.min(T))
    opd = float(dn_dT_per_K) * np.trapz(T - T_ref_C, z, axis=1)
    if bulge_m is not None:
        opd = opd + (float(n_1064) - 1.0) * np.asarray(bulge_m, dtype=float)
    return opd


def fit_opd(r_m, opd_m, w_L_m, r_max_factor=1.5):
    """Fit ``OPD(r) = c0 + c2 r^2 + c4 r^4 + c6 r^6`` for ``r <= 1.5 w_L``.

    Returns ``{"f_th_m", "c2_per_m", "c4_per_m3", "c6_per_m5",
    "c0_m", "rms_m", "r_fit_max_m", "n_points"}``.  ``f_th`` is
    ``-1/(2 c2)``; a non-negative ``c2`` (defocusing lens) gives
    ``f_th_m = inf`` with a warning flag.
    """
    r = np.asarray(r_m, dtype=float)
    opd = np.asarray(opd_m, dtype=float)
    w_L = float(w_L_m)
    if w_L <= 0:
        raise ThermalError("w_L_m must be positive")
    r_max = r_max_factor * w_L
    mask = r <= r_max
    if np.count_nonzero(mask) < 5:
        raise ThermalError("OPD fit needs >= 5 radial points inside "
                           "r <= %.3g*w_L (have %d)"
                           % (r_max_factor, np.count_nonzero(mask)))
    rho = r[mask] / w_L
    y = opd[mask]
    design = np.column_stack([np.ones_like(rho), rho ** 2, rho ** 4,
                              rho ** 6])
    coeff, *_ = np.linalg.lstsq(design, y, rcond=None)
    c0, c2s, c4s, c6s = (float(v) for v in coeff)
    resid = y - design @ coeff
    rms = float(np.sqrt(np.mean(resid ** 2)))
    c2 = c2s / w_L ** 2
    c4 = c4s / w_L ** 4
    c6 = c6s / w_L ** 6
    if c2 < 0:
        f_th = -1.0 / (2.0 * c2)
        focusing = True
    else:
        f_th = float("inf")
        focusing = False
    return {"f_th_m": f_th, "focusing": focusing, "c2_per_m": c2,
            "c4_per_m3": c4, "c6_per_m5": c6, "c0_m": c0,
            "rms_m": rms, "r_fit_max_m": float(r_max),
            "n_points": int(np.count_nonzero(mask))}


def on_axis_curvature_c2(T_C, r_m, z_m):
    """``int T''(0,z) dz`` [K/m] from the first two radial nodes.

    ``T''(0,z) ~ 2(T1-T0)/dr^2`` (axis symmetry, second order).
    The PDE identity ``2*int T''(0,z) dz = -int Q(0,z)/k dz``
    (adiabatic end faces) makes this an exact check of the solver
    when combined with the heat-source array.
    """
    T = np.asarray(T_C, dtype=float)
    r = np.asarray(r_m, dtype=float)
    z = np.asarray(z_m, dtype=float)
    dr = r[1] - r[0]
    tpp0 = 2.0 * (T[1, :] - T[0, :]) / dr ** 2
    return float(np.trapz(tpp0, z))


def analytic_f_th_gaussian(P_heat_W, dn_dT_per_K, k_W_per_mK, w_p_m):
    """Analytic ``f_th`` [m] for a Gaussian pump, dn/dT term only.

    ``1/f = eta_h*P_abs*(dn/dT) / (pi*K*w_p^2)`` where ``P_heat_W``
    is ``eta_h*P_abs``.  Exact for adiabatic end faces and
    ``R0 >> w_p`` (the axial second derivative integrates to zero
    over the rod); the FEA closed-loop test compares against this.
    """
    denom = math.pi * float(k_W_per_mK) * float(w_p_m) ** 2
    return denom / (float(P_heat_W) * float(dn_dT_per_K))


def phase_plate(fit):
    """Fox-Li phase-plate coefficients from an OPD fit.

    ``{"f_th_mm", "c4_per_m3", "c6_per_m5", "rms_m"}`` for
    ``OPD(r) = -r^2/(2 f_th) + c4 r^4 + c6 r^6`` (M3 input).
    """
    return {"f_th_mm": float(fit["f_th_m"]) * 1e3,
            "c4_per_m3": fit["c4_per_m3"],
            "c6_per_m5": fit["c6_per_m5"],
            "rms_m": fit["rms_m"]}


# --- Side-car resolution + report ----------------------------------------------

def _need(thermal, key):
    if thermal.get(key) is None:
        raise ThermalError("thermal side-car needs %r" % (key,))
    return thermal[key]


def resolve_thermal(data, eng, binary=None):
    """Resolve a ``thermal`` side-car section into a rod ``spec``.

    ``data`` is the loaded ``.rez`` dict, ``eng`` the side-car dict.
    The gain element comes from ``gain_and_pump.gain_element`` when
    present, else ``thermal.element``.  Length defaults to the
    element's ``L`` param, radius to ``aperture_diameter_mm/2`` from
    ``elements``; everything else with no default raises
    :class:`ThermalError` naming the field.
    """
    from .rez import param_value_si, element_index
    thermal = (eng or {}).get("thermal") or {}
    if not isinstance(thermal, dict):
        raise ThermalError("thermal section is not an object")
    gp = (eng or {}).get("gain_and_pump") or {}
    label = gp.get("gain_element") or thermal.get("element")
    if not label:
        raise ThermalError("thermal needs gain_and_pump.gain_element "
                           "or thermal.element")
    if element_index(data, label) is None:
        raise ThermalError("thermal element %r not found in .rez" % (label,))
    length_m = None
    if thermal.get("length_mm") is not None:
        length_m = float(thermal["length_mm"]) * 1e-3
    else:
        try:
            length_m = param_value_si(data, label, "L")
        except Exception:
            length_m = None
    if length_m is None or length_m <= 0:
        raise ThermalError("thermal needs length_mm or element %r L"
                           % (label,))
    radius_m = None
    if thermal.get("radius_mm") is not None:
        radius_m = float(thermal["radius_mm"]) * 1e-3
    else:
        entry = ((eng or {}).get("elements") or {}).get(label) or {}
        ap = entry.get("aperture_diameter_mm")
        if ap is not None:
            radius_m = float(ap) * 1e-3 / 2.0
    if radius_m is None or radius_m <= 0:
        raise ThermalError("thermal needs radius_mm or elements.%s"
                           ".aperture_diameter_mm" % (label,))
    cooling = thermal.get("cooling")
    if not isinstance(cooling, dict):
        raise ThermalError("thermal.cooling must be an object with "
                           "h_W_per_m2K")
    if cooling.get("h_W_per_m2K") is None:
        raise ThermalError("thermal.cooling needs h_W_per_m2K "
                           "(no default: it sets the absolute temperature)")
    filled = fill_thermal_typical(thermal)
    overrides = filled.get("material_overrides") or {}
    pump = thermal.get("pump") or {}
    if not isinstance(pump, dict):
        raise ThermalError("thermal.pump is not an object")
    spec = {
        "R0_m": radius_m, "L_m": length_m, "material": thermal.get("material"),
        "P_pump_W": _need(pump, "P_pump_W"),
        "eta_p": float(pump.get("eta_p", 1.0)),
        "eta_h": _need(pump, "eta_h"),
        "w_p0_m": float(_need(pump, "w_p0_um")) * 1e-6,
        "Mp2": float(pump.get("Mp2", 1.0)),
        "lambda_p_m": float(pump.get("lambda_p_nm", 808.0)) * 1e-9,
        "z_p0_m": float(pump.get("z_p0_mm", length_m * 1e3 / 2.0)) * 1e-3,
        "profile": pump.get("profile", "gaussian"),
        "h_W_per_m2K": float(cooling["h_W_per_m2K"]),
        "T_cool_C": float(cooling.get("T_cool_C", 20.0)),
        "end_faces": cooling.get("end_faces", "adiabatic"),
        "Nr": int((thermal.get("grid") or {}).get("Nr", 60)),
        "Nz": int((thermal.get("grid") or {}).get("Nz", 150)),
        "segments": thermal.get("end_caps"),
        "w_L_um": thermal.get("w_L_um"),
    }
    if pump.get("alpha_p_per_cm") is not None:
        spec["alpha_per_m"] = float(pump["alpha_p_per_cm"]) * 100.0
    elif thermal.get("end_caps"):
        spec["alpha_per_m"] = None
    else:
        raise ThermalError("thermal.pump needs alpha_p_per_cm (or "
                           "thermal.end_caps with per-segment alpha)")
    for key in ("k_W_per_mK", "dn_dT_per_K", "alpha_a_per_K",
                "alpha_c_per_K", "E_GPa", "nu", "sigma_fracture_MPa",
                "n_1064"):
        if key in overrides:
            spec[key] = overrides[key]
    spec["_material_source"] = filled.get("_material_source")
    spec["_element"] = label
    return spec


def thermal_report(data, eng, w_L_um=None, binary=None):
    """Full thermal + OPD report for the side-car ``thermal`` section.

    ``w_L_um`` overrides ``thermal.w_L_um`` (laser mode radius at the
    crystal, e.g. from the CLI beam).  Returns a JSON-able dict with
    the temperature summary, the OPD fit (dn/dT only and with the
    bulge term), the analytic Gaussian closed-loop value, the
    Phase 2 linear-model comparison, and the Fox-Li phase plate.
    Stress/fracture is added by :mod:`rezeng.fracture` via
    ``fracture_report``; :func:`run_thermal` merges both.
    """
    from .fracture import fracture_report as _fracture_report
    spec = resolve_thermal(data, eng, binary=binary)
    result = solve_rod(spec)
    T = result["T_C"]
    r, z = result["r_m"], result["z_m"]
    mat = result["material"]
    dn_dT = mat.get("dn_dT_per_K", mat.get("dn_dT_e_per_K"))
    n_1064 = mat.get("n_1064", mat.get("n_e_1064"))
    if dn_dT is None or n_1064 is None:
        raise ThermalError("material %r has no dn/dT / n_1064"
                           % (spec.get("material"),))
    T_cool = result["T_cool_C"]
    # Laser mode radius at the crystal for the OPD fit.
    w_L = None
    if w_L_um is not None:
        w_L = float(w_L_um) * 1e-6
    elif spec.get("w_L_um") is not None:
        w_L = float(spec["w_L_um"]) * 1e-6
    else:
        w_L = float(np.mean(result["w_p_m"]))
    opd_dn = opd_from_field(T, r, z, dn_dT, n_1064, T_ref_C=T_cool)
    fit_dn = fit_opd(r, opd_dn, w_L)
    alpha_a = mat.get("alpha_a_per_K")
    nu = mat.get("nu")
    bulge = None
    fit_bulge = None
    if alpha_a is not None and nu is not None:
        bulge = bulge_displacement(T, r, z, alpha_a, nu, T_ref_C=T_cool)
        opd_tot = opd_from_field(T, r, z, dn_dT, n_1064,
                                 T_ref_C=T_cool, bulge_m=bulge)
        fit_bulge = fit_opd(r, opd_tot, w_L)
    w_p_mean_m = float(np.mean(result["w_p_m"]))
    f_analytic = analytic_f_th_gaussian(result["P_heat_W"], dn_dT,
                                        mat.get("k_W_per_mK"), w_p_mean_m)
    # Paraxial closed loop (the solver validation): the direct
    # on-axis curvature against the exact value from the solver's
    # own Q(0,z).  This is the PDE identity 2*int T''(0,z) dz =
    # -int Q(0,z)/k dz and holds to <1% on any reasonable grid.
    q_axis = float(np.trapz(result["Q_W_per_m3"][0, :], z))
    c2_exact = -dn_dT * q_axis / (4.0 * mat["k_W_per_mK"])
    f_exact = -1.0 / (2.0 * c2_exact)
    c2_par = dn_dT * on_axis_curvature_c2(T, r, z) / 2.0
    f_par = -1.0 / (2.0 * c2_par) if c2_par < 0 else float("inf")
    par_dev = (f_par - f_exact) / f_exact if math.isfinite(f_par) else None
    # Mode-averaged fit deviation: the 1.5*w_L fit is the effective
    # lens over the mode, not the paraxial lens.  When w_L >> w_p
    # the mode samples the flat outer OPD and the fitted f_th runs
    # much longer than the paraxial value -- real physics, not a
    # solver error (see the README).
    f_fea = fit_dn["f_th_m"]
    fit_dev = None
    if math.isfinite(f_fea) and math.isfinite(f_analytic) \
            and f_analytic > 0:
        fit_dev = (f_fea - f_analytic) / f_analytic
    mode_vs_par = None
    if math.isfinite(f_fea) and math.isfinite(f_par) and f_par > 0:
        mode_vs_par = (f_fea - f_par) / f_par
    # Phase 2 linear-model comparison (anchor / physics estimate).
    linear = None
    try:
        from .power import resolve_params, thermal_focal_lengths
        params = resolve_params(data, eng)
        f_t, f_s, _f_cli, source, warnings = thermal_focal_lengths(
            params, float(spec["P_pump_W"]))
        linear = {"F_T_mm": f_t * 1e3, "F_S_mm": f_s * 1e3,
                  "source": source, "warnings": warnings}
    except Exception as exc:  # noqa: BLE001 - report, don't crash
        linear = {"error": str(exc)}
    fracture = _fracture_report(result, mat)
    out = {
        "element": spec["_element"],
        "material": spec.get("material"),
        "material_source": spec.get("_material_source"),
        "P_pump_W": float(spec["P_pump_W"]),
        "P_abs_W": result["P_abs_W"], "P_heat_W": result["P_heat_W"],
        "T_cool_C": T_cool,
        "T_max_C": float(np.max(T)),
        "T_max_rise_K": float(np.max(T) - T_cool),
        "T_axis_C": [float(v) for v in T[0, :]],
        "T_edge_C": [float(v) for v in T[-1, :]],
        "w_L_um": w_L * 1e6,
        "w_p_um": float(np.mean(result["w_p_m"])) * 1e6,
        "opd_fit_dndT": {k: v for k, v in fit_dn.items()},
        "opd_fit_with_bulge": fit_bulge,
        "bulge_max_um": (float(np.max(bulge)) * 1e6
                         if bulge is not None else None),
        "f_analytic_gaussian_mm": f_analytic * 1e3,
        "f_analytic_exact_mm": f_exact * 1e3,
        "f_paraxial_mm": f_par * 1e3 if math.isfinite(f_par) else None,
        "paraxial_dev": par_dev,
        "closed_loop_dev": par_dev,
        "fit_dev_vs_analytic": fit_dev,
        "mode_vs_paraxial_dev": mode_vs_par,
        "linear_model": linear,
        "phase_plate": phase_plate(fit_dn),
        "fracture": fracture,
        "warnings": [],
    }
    if mat.get("alpha_c_per_K") and mat.get("alpha_a_per_K") \
            and mat["alpha_c_per_K"] > 1.5 * mat["alpha_a_per_K"]:
        out["warnings"].append(
            "anisotropic material: alpha_c (%.3g/K) is %.2fx alpha_a "
            "(%.3g/K); the isotropic stress uses alpha_a for the "
            "primary value and alpha_c for the conservative bound"
            % (mat["alpha_c_per_K"],
               mat["alpha_c_per_K"] / mat["alpha_a_per_K"],
               mat["alpha_a_per_K"]))
    if par_dev is not None and abs(par_dev) > 0.10:
        out["warnings"].append(
            "paraxial closed-loop deviation %.1f%% exceeds 10%%: "
            "check the grid or the heat source" % (100.0 * par_dev,))
    if mode_vs_par is not None and abs(mode_vs_par) > 0.10:
        out["warnings"].append(
            "mode-averaged f_th differs from the paraxial value by "
            "%+.1f%% (w_L %.0f um vs w_p %.0f um): the mode samples "
            "the flat outer OPD, so the effective lens over the mode "
            "is weaker than the paraxial lens -- use the paraxial "
            "value for the linear-model comparison, the fitted value "
            "for the Fox-Li phase plate"
            % (100.0 * mode_vs_par, w_L * 1e6, w_p_mean_m * 1e6))
    return out
