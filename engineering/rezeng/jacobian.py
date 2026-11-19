"""Alignment Jacobian and screw-turn guide (Phase 3 block 3).

The optical axis is an *exactly* linear function of the mirror delta
tilts: the round-trip matrices do not depend on the tilts (a tilt adds
only a kick, it does not change Alpha), only the augmented displacement
column does. So the Jacobian is exact, not an approximation. Two
independent routes compute it and must agree:

* analytic: differentiate the augmented 3x3 round-trip system
  ``(I - M_rt) v = E_rt`` with respect to each mirror tilt. For a unit
  tilt of mirror ``k``, ``dE_rt/d(delta_k)`` is the sum over that
  mirror's occurrences in the C++ round-trip list of (product of the
  matrices *before* the occurrence) ``. (0, 2)``; the Jacobian column is
  ``(I - M_rt)^-1 . dE/d(delta_k)``.
* finite difference: one CLI batch request with one mutation per tilt
  (``delta = 1e-4 rad``), differencing the CLI axis output. This
  exercises the C++ kick implementation directly, including the
  second-pass sign.

Coordinate and sign conventions (protocol §12, the single source of
truth; the C++ side implements the same):
* ``T = S x z`` of the *unfolded* beam; ``S`` is the global +y (out of
  the fold plane). The axis output is ``(x_T, th_T, x_S, th_S)`` at the
  element's exit face, in the unfolded frame, mm / mrad.
* ``delta_T > 0`` moves the mirror normal toward +T; ``delta_S > 0``
  toward +S. The unfolded ray angle gets a ``+2*delta`` kick in the
  same plane, on every traversal (first and return pass alike).
* ``theta`` in the Jacobian is the mirror MECHANICAL tilt. The beam
  deflection is 2x that (reflection). Screw turns use the mechanical
  tilt: ``N = theta * L_arm / p``.

Jacobian layout: rows ``[x_T, th_T, x_S, th_S]`` (mm per mrad, mrad per
mrad, mm per mrad, mrad per mrad -- numerically equal to m/rad and
rad/rad); columns ``[dT(M1), dS(M1), dT(M2), dS(M2), ...]`` in the
order :func:`mirror_labels` returns. The T and S planes are decoupled,
so each ``dT`` column has zeros in the S rows and vice versa.
"""

import math

import numpy as np

from .cli import DEFAULT_BINARY, run_headless
from .qevolve import element_matrix
from .rez import elements

#: Finite-difference step for the cross-check (rad). The axis is exactly
#: linear in the tilts, so this only needs to be small enough for float
#: noise; 1e-4 rad is the value the Phase 3 review specified.
FD_STEP_RAD = 1e-4

#: Agreement required between the analytic and finite-difference
#: Jacobians (max absolute entry difference, same units as the Jacobian).
JACOBIAN_TOL = 1e-6

#: Thread pitch (mm per turn) for common kinematic-mount screws.
TPI_PITCH_MM = {100: 25.4 / 100.0, 80: 25.4 / 80.0}

#: Mirror element types that accept a delta tilt.
MIRROR_TYPES = ("ElemFlatMirror", "ElemCurveMirror")

#: Jacobian row labels.
ROW_LABELS = ("x_T", "th_T", "x_S", "th_S")

#: Tolerance for the stability-edge check (|g| within this of +/-1).
EDGE_EPS = 1e-9


class JacobianError(ValueError):
    """Raised when no Jacobian exists (singular solve, SP schema, ...)."""


def mirror_labels(data):
    """Labels of the mirrors (flat/curved) in element order."""
    return [e.get("label") for e in elements(data)
            if e.get("type") in MIRROR_TYPES and not e.get("is_disabled")]


def roundtrip_list(labels, ref_label, trip_type):
    """Element labels of the C++ round trip, in list order.

    An exact port of ``RoundTripCalculator::calcRoundTripSW`` /
    ``calcRoundTripRR`` (``src/math/RoundTripCalculator.cpp``): the
    product of these matrices in list order is the round-trip matrix
    the beam (and the axis) is computed from. Raises
    :class:`JacobianError` for single-pass schemas (no round trip).
    """
    if trip_type not in ("SW", "RR"):
        raise JacobianError(
            "misalignment axis needs a resonator (SW or RR), not %r"
            % (trip_type,))
    n = len(labels)
    ref = labels.index(ref_label)
    trip = []
    if trip_type == "SW":
        i = ref
        while i > 0:
            trip.append(i)
            i -= 1
        c = n
        if ref == c - 1:
            c -= 1
        i = 0
        while i < c:
            trip.append(i)
            i += 1
        i -= 2
        while i > ref:
            trip.append(i)
            i -= 1
    else:  # RR: each element exactly once, ring order from the reference
        i = ref
        while i >= 0:
            trip.append(i)
            i -= 1
        i = n - 1
        while i > ref:
            trip.append(i)
            i -= 1
    return [labels[k] for k in trip]


def _solve_axis(M, E):
    """Solve ``(I - M) v = E`` for a 2x2 ``M``; ``None`` when singular."""
    I2 = np.eye(2)
    if abs(np.linalg.det(I2 - M)) < 1e-12:
        return None
    try:
        v = np.linalg.solve(I2 - M, E)
    except np.linalg.LinAlgError:
        return None
    if not np.all(np.isfinite(v)):
        return None
    return v


def jacobian_analytic(data, ref_label, mirrors=None):
    """Analytic Jacobian of the axis at ``ref_label``.

    Returns ``{\"jacobian\": (4, 2*n) ndarray, \"columns\": [...],
    \"rows\": [...], \"g_T\": float, \"g_S\": float}``. The Jacobian is in
    SI units (m/rad for the x rows, rad/rad for the theta rows), which
    read as mm/mrad and mrad/mrad. Raises :class:`JacobianError` when
    the solve is singular (cavity at g = +/-1) or the schema is SP.
    """
    labels = [e.get("label") for e in elements(data)
              if not e.get("is_disabled")]
    if ref_label not in labels:
        raise JacobianError("unknown element %r" % (ref_label,))
    mirrors = mirrors if mirrors is not None else mirror_labels(data)
    trip_type = data.get("trip_type", "SW")
    lst = roundtrip_list(labels, ref_label, trip_type)
    mats = {}
    for lab in labels:
        mats[lab] = element_matrix(data, lab)  # (M_T, M_S)

    J = np.zeros((4, 2 * len(mirrors)))
    g = {}
    for plane, (r0, r1) in (("T", (0, 1)), ("S", (2, 3))):
        # Accumulate M_rt and, per mirror, dE/d(delta) for a unit tilt.
        Mrt = np.eye(2)
        dE = {m: np.zeros(2) for m in mirrors}
        P = np.eye(2)  # product of the matrices before the current one
        for lab in lst:
            m = mats[lab][0] if plane == "T" else mats[lab][1]
            if lab in dE:
                dE[lab] = dE[lab] + P @ np.array([0.0, 2.0])
            P = P @ m
        Mrt = P
        g[plane] = 0.5 * (Mrt[0, 0] + Mrt[1, 1])
        if abs(abs(g[plane]) - 1.0) <= EDGE_EPS:
            raise JacobianError(
                "cavity at g_%s = %.12g (+/-1): no unique axis"
                % (plane, g[plane]))
        for k, m in enumerate(mirrors):
            v = _solve_axis(Mrt, dE[m])
            if v is None:
                raise JacobianError(
                    "singular axis solve at %r (plane %s)" % (ref_label, plane))
            # T-plane tilt -> dT column (2k), S-plane tilt -> dS column (2k+1).
            col = 2 * k if plane == "T" else 2 * k + 1
            J[r0, col] = v[0]
            J[r1, col] = v[1]
    return {"jacobian": J,
            "columns": [c for m in mirrors
                        for c in ("dT(%s)" % m, "dS(%s)" % m)],
            "rows": list(ROW_LABELS),
            "g_T": float(g["T"]), "g_S": float(g["S"])}


def _axis_at(ref_label, result):
    """Axis entry for ``ref_label`` from one CLI result (mm, mrad)."""
    axis = result.get("axis")
    if not axis:
        raise JacobianError(
            "CLI returned no axis for mutation id=%r (singular? %s)"
            % (result.get("id"), result.get("error")))
    for entry in axis:
        if entry.get("label") == ref_label:
            return np.array([entry["x_T_mm"], entry["th_T_mrad"],
                             entry["x_S_mm"], entry["th_S_mrad"]], dtype=float)
    raise JacobianError("CLI axis has no entry for %r" % (ref_label,))


def jacobian_finite_difference(data, ref_label, mirrors=None,
                               dtheta=FD_STEP_RAD, binary=DEFAULT_BINARY,
                               timeout=None):
    """Jacobian by finite differences on the CLI axis output.

    One batch request: a base mutation plus one mutation per tilt
    (``delta = dtheta``). Returns ``{\"jacobian\": ndarray,
    \"columns\": [...], \"rows\": [...], \"base_axis\": ndarray}`` with the
    base axis in (mm, mrad). The Jacobian is in the same units as
    :func:`jacobian_analytic` (mm/mrad for x rows, mrad/mrad for theta
    rows). Raises :class:`JacobianError` on any CLI failure or null axis.
    """
    mirrors = mirrors if mirrors is not None else mirror_labels(data)
    mutations = [{"id": "base", "misalign": {}}]
    for m in mirrors:
        mutations.append({"id": "dT(%s)" % m,
                          "misalign": {m: {"dT_mrad": dtheta * 1e3}}})
        mutations.append({"id": "dS(%s)" % m,
                          "misalign": {m: {"dS_mrad": dtheta * 1e3}}})
    resp = run_headless({"base_schema": data, "mutations": mutations},
                        binary=binary, timeout=timeout)
    by_id = {}
    for res in resp.get("results", []):
        if not res.get("ok"):
            raise JacobianError("CLI mutation id=%r failed: %s"
                                % (res.get("id"), res.get("error")))
        by_id[res.get("id")] = res
    base = _axis_at(ref_label, by_id["base"])
    J = np.zeros((4, 2 * len(mirrors)))
    for k, m in enumerate(mirrors):
        for plane, col in (("T", 2 * k), ("S", 2 * k + 1)):
            key = "d%s(%s)" % (plane, m)
            ax = _axis_at(ref_label, by_id[key])
            # Axis is in mm/mrad and dtheta is in rad: divide by the
            # step in mrad so the Jacobian reads mm/mrad and mrad/mrad
            # (numerically equal to m/rad and rad/rad).
            J[:, col] = (ax - base) / (dtheta * 1e3)
    return {"jacobian": J,
            "columns": [c for m in mirrors for c in ("dT(%s)" % m, "dS(%s)" % m)],
            "rows": list(ROW_LABELS),
            "base_axis": base}


def compare_jacobians(J_analytic, J_fd, tol=JACOBIAN_TOL):
    """Max absolute entry difference between two Jacobians.

    Returns ``(max_abs_diff, ok)`` with ``ok`` true when the difference
    is below ``tol`` (default 1e-6).
    """
    diff = np.max(np.abs(np.asarray(J_analytic) - np.asarray(J_fd)))
    return float(diff), bool(diff <= tol)


# ---------------------------------------------------------------------------
# Screw-turn guide
# ---------------------------------------------------------------------------

def screw_turns(theta_rad, arm_mm, tpi):
    """Turns of one screw for a mirror tilt ``theta_rad`` (mechanical).

    ``N = theta * L_arm / p`` with ``p`` the thread pitch (mm/turn).
    ``arm_mm`` is the distance from the pivot to the screw. Returns a
    signed turn count: positive means the screw advances (see
    :func:`direction_table` for which way that turns the mirror).
    """
    if tpi not in TPI_PITCH_MM:
        raise JacobianError("unsupported thread pitch %r TPI (use 80 or 100)"
                            % (tpi,))
    if arm_mm <= 0:
        raise JacobianError("screw arm length must be positive")
    return theta_rad * arm_mm / TPI_PITCH_MM[tpi]


def direction_table():
    """Clockwise / counter-clockwise mapping (back view).

    Standard kinematic-mount layout, right-hand thread, viewed from
    BEHIND the mount (from the side the screws are on, looking toward
    the mirror face):

    * clockwise (as seen from behind) = the screw advances (moves
      toward the mirror, pushing that edge forward);
    * screw A (pitch) sits on the +T side of the pivot: advancing it
      pushes the +T edge forward, so the normal rotates toward -T,
      i.e. ``delta_T`` DECREASES. Counter-clockwise INCREASES ``delta_T``.
    * screw B (yaw) sits on the +S side of the pivot: advancing it
      pushes the +S edge forward, so ``delta_S`` DECREASES.
      Counter-clockwise INCREASES ``delta_S``.

    The table maps a desired tilt sign to the screw direction. The
    physical layout (which side each screw is on, thread handedness)
    varies between mounts; the mapping must be confirmed by one
    single-mirror trim calibration (see the README: turn one screw a
    known number of turns and check the spot moves the predicted way).
    Returns ``{\"dT+\": ..., \"dT-\": ..., \"dS+\": ..., \"dS-\": ...}``
    with values ``\"CW\"`` / ``\"CCW\"`` (as seen from behind).
    """
    return {"dT+": "CCW", "dT-": "CW",
            "dS+": "CCW", "dS-": "CW"}


def tilt_to_screws(dT_rad, dS_rad, tpi, arm_T_mm, arm_S_mm,
                   azimuth_deg=0.0):
    """Screw turns for a desired mirror tilt ``(dT_rad, dS_rad)``.

    ``azimuth_deg`` is the rotation of the mount's screw axes relative
    to the cavity T/S axes (``phi``): the tilt in the mount frame is
    ``R(-phi) . (dT, dS)``. Returns ``{\"screw_A\": {\"turns\": float,
    \"direction\": \"CW\"/\"CCW\"}, \"screw_B\": {...}, \"phi_deg\": float}``
    with turns >= 0 (magnitude) and the direction as seen from behind
    the mount (see :func:`direction_table`). Screw A is the pitch screw
    (mount x axis), screw B the yaw screw (mount y axis).
    """
    phi = math.radians(azimuth_deg)
    c, s = math.cos(phi), math.sin(phi)
    # Mount-frame tilts: R(-phi) . (dT, dS).
    th_a = c * dT_rad + s * dS_rad
    th_b = -s * dT_rad + c * dS_rad
    table = direction_table()
    out = {}
    for name, th, arm in (("screw_A", th_a, arm_T_mm),
                          ("screw_B", th_b, arm_S_mm)):
        turns = abs(screw_turns(th, arm, tpi))
        # Positive tilt (in the mount frame) needs CCW; negative needs
        # CW; no tilt needs no turn at all.
        direction = ("-" if turns == 0.0 else
                     table["dT+"] if th >= 0 else table["dT-"])
        out[name] = {"turns": turns, "direction": direction,
                     "tilt_rad": th}
    out["phi_deg"] = azimuth_deg
    return out


def solve_correction(J, delta_axis, columns=None):
    """Mirror tilt correction for a measured axis offset.

    ``J`` is a Jacobian (4, 2*n) as returned by
    :func:`jacobian_analytic`; ``delta_axis`` is the measured axis
    offset at the output element, ``(dx_T, dth_T, dx_S, dth_S)`` in
    (mm, mrad). ``columns`` selects the tilt columns to use (default:
    all). Solves ``J_sub . delta = -delta_axis`` in the least-squares
    sense and returns ``{\"tilt\": {column: mrad}, \"residual\":
    ndarray}`` with the residual axis offset left after the correction.
    The tilt is in mrad because the Jacobian is in mm/mrad (x rows) and
    mrad/mrad (theta rows) and the offset is in (mm, mrad).
    """
    J = np.asarray(J, dtype=float)
    if columns is None:
        columns = list(range(J.shape[1]))
    Jsub = J[:, columns]
    delta = np.asarray(delta_axis, dtype=float)
    sol, *_ = np.linalg.lstsq(Jsub, -delta, rcond=None)
    resid = Jsub @ sol + delta
    return {"tilt": {columns[i]: float(sol[i]) for i in range(len(columns))},
            "residual": resid}


def recenter_guide(data, ref_label, mirror_label, measured_axis,
                   tpi, arm_T_mm, arm_S_mm, azimuth_deg=0.0,
                   binary=DEFAULT_BINARY, timeout=None):
    """Guide to bring the output spot back to centre with one mirror.

    ``measured_axis`` is the measured axis offset at ``ref_label``,
    ``(x_T_mm, th_T_mrad, x_S_mm, th_S_mrad)``. Uses the analytic
    Jacobian for ``mirror_label`` and corrects the spot POSITION
    (``x_T``, ``x_S``) with that mirror's ``(dT, dS)``; the pointing
    residual is reported, not corrected (one mirror cannot zero all
    four outputs). Returns a dict with the correction tilt, the screw
    turns + directions, the predicted residual axis, and the Jacobian
    rows used. All mount numbers are EXAMPLE values unless the caller
    passes the real ones.
    """
    ja = jacobian_analytic(data, ref_label, [mirror_label])
    J = ja["jacobian"]
    # Position-only correction: rows x_T (0) and x_S (2), columns dT (0)
    # and dS (1) of the single mirror. The planes are decoupled, so this
    # is two independent 1D solves.
    rows = [0, 2]
    cols = [0, 1]
    sol = solve_correction(J[rows][:, cols],
                           np.asarray(measured_axis, dtype=float)[rows],
                           columns=[0, 1])
    dT_mrad = sol["tilt"][0]
    dS_mrad = sol["tilt"][1]
    full_resid = (J @ np.array([dT_mrad, dS_mrad])
                  + np.asarray(measured_axis, dtype=float))
    screws = tilt_to_screws(dT_mrad * 1e-3, dS_mrad * 1e-3,
                            tpi, arm_T_mm, arm_S_mm,
                            azimuth_deg=azimuth_deg)
    return {"mirror": mirror_label, "output_element": ref_label,
            "correction_mrad": {"dT": dT_mrad, "dS": dS_mrad},
            "screws": screws,
            "residual_axis": {"x_T_mm": float(full_resid[0]),
                              "th_T_mrad": float(full_resid[1]),
                              "x_S_mm": float(full_resid[2]),
                              "th_S_mrad": float(full_resid[3])},
            "jacobian": J}
