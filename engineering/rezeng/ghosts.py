"""Ghost / parasitic-etalon scan (Phase 4 block 1).

Scans every optical surface's residual reflection for two hazards:

* **parasitic etalons**: pairs of near-parallel surfaces whose
  reflections form a sub-cavity (free spectral range + modulation
  depth; a large modulation depth warns of mode-hopping risk);
* **focused ghost burn points**: a reflection off a surface creates
  a ghost beam; its waist is located by ABCD tracing, and when the
  waist lands inside an element (crystal / coating) the ghost peak
  fluence is compared with that element's LIDT.

Conventions (verified against the C++ sources and the CLI):

* **Alpha is the angle of incidence (AOI)** -- see
  ``src/core/Elements.cpp`` ``ElemCurveMirror``: the ``Alpha``
  parameter is documented (in Chinese) as "入射角" ("angle of
  incidence", "zero angle is normal incidence") and the matrix is
  ``T: C = -2/(R*cos(alpha))``, ``S: C = -2*cos(alpha)/R`` -- the
  standard oblique-incidence mirror matrix. The full fold angle of
  the beam is ``2*Alpha``. Phase 0's astigmatism analysis used the
  same definition. This matters for the coating table and the .zmx
  export (a factor-2 error if Alpha were mistaken for the fold
  angle); see ``rezeng.export``.
* The ghost is traced in the *unfolded* frame, exactly as the C++
  round-trip list does (``RoundTripCalculator::calcRoundTripSW``):
  the ghost starts at the generating surface and walks the
  round-trip list backwards (cyclically, at most one full round
  trip). At each list item it applies the matrix for the *opposite*
  traversal orientation to the list's (the forward matrix for
  return-pass items, the reverse-traversal matrix
  ``[[D, B], [C, A]]`` for forward-pass items -- identical to the
  forward matrix for every symmetric element, which is why the
  C++ ``SAME_INV`` macro sets them equal; only asymmetric elements
  such as tilted plates differ). The walk wraps around the cyclic
  list, so a ghost that reaches an end mirror keeps circulating
  into the next round trip.
* Ghost ``q`` at generation: the ghost is the *reflected* beam, so
  in its own propagation frame ``q_ghost = M_face . (-conj(q_main))``
  where ``M_face`` is the reflecting face's matrix (identity for a
  flat face, ``[[1, 0], [C, 1]]`` for a curved face). Check: for a
  flat face the ghost is the exact time reversal of the main beam,
  so a ghost generated at the (flat) output mirror retraces the
  main beam and its ``w`` must match the CLI beam entries at every
  plane -- this is locked by a test.
* The ghost centre ray is traced with 3x3 augmented ABCD matrices
  (the Phase 3 formalism, protocol SS12): a wedged face gives the
  ghost ray an initial angle ``2*wedge``; a tilted parallel plate
  gives a lateral offset ``2*Delta`` with
  ``Delta = L*sin(alpha-beta)/cos(beta)``,
  ``sin(beta) = sin(alpha)/n``. A ghost whose ray centre leaves an
  element's clear aperture is excluded (it cannot burn that optic).
  A pure 2x2 co-axial trace would miss this -- the off-axis test
  locks a case where 2x2 flags a burn and 3x3 excludes it.

Side-car data (``<file>.rez.eng.json``, section ``surfaces``)::

    "surfaces": {
      "TL1": {"faces": [
        {"face": "front", "R_1064": 0.002, "R_808": 0.003,
         "wedge_mrad": 0.0, "role": "AR"},
        {"face": "back",  "R_1064": 0.002, "role": "AR"}]},
      "M4":  {"faces": [
        {"face": "back", "R_1064": 0.002, "role": "AR"}]}
    }

Every field is optional; a missing reflectivity is reported as
``nodata`` -- never silently defaulted. Mirror *front* faces do not
generate separate ghosts (their reflection *is* the main beam);
their substrate *back* faces do. ``role`` (``HR`` / ``AR`` / ``OC`` /
``SESAM``) is used by the coating table (``rezeng.export``).
A curved face may carry ``R_face_mm`` (mirror-convention radius:
positive = concave toward the incident beam); for ``ElemThickLens``
the face radii are taken from the element's R1/R2 parameters
(front face ``C = +2/R1``, back face ``C = -2/R2``, from the C++
``ElemThickLens`` convention "positive R1/R2 bulges to the left").

Pruning (Gemini Phase 4 review, adopted):

* etalon pairs: ``R_i * R_j > 1e-6`` and the relative normal angle
  ``< theta_div`` (the beam divergence angle);
* first-order ghost focusing: single ``R_i > 1e-3``.
"""

import json
import math
import sys

import numpy as np
from scipy.optimize import brentq

from .checks import LIDT_FAIL_RATIO, LIDT_WARN_RATIO, lidt_fluence_J_per_cm2
from .cli import DEFAULT_BINARY, run_headless
from .eng import eng_path as eng_path_for, load_eng, validate_eng
from .jacobian import JacobianError, roundtrip_list
from .qevolve import (QevolveError, element_grin_params, element_matrix,
                      q_from_wr, wr_from_q)
from .rez import elements, load_rez, param_value_si
from .solves import element_plane_position_mm, total_length_mm

#: Speed of light (m/s), for the etalon free spectral range.
C_LIGHT = 299792458.0

#: Pruning: etalon pairs need R_i * R_j above this.
ETALON_MIN_RR = 1e-6

#: Pruning: a single surface reflection below this is not traced
#: for ghost focusing (it can still take part in an etalon pair).
GHOST_MIN_R = 1e-3

#: Etalon modulation-depth warning threshold (mode-hopping risk).
MODULATION_WARN = 0.05

#: How far a ghost waist may sit from an element plane and still
#: count as "inside" it (in units of the ghost Rayleigh range).
WAIST_TOL_ZR = 2.0

#: Element types whose two faces are optical surfaces.
PLATE_TYPES = ("ElemPlate", "ElemThermoLens", "ElemGrinLens",
               "ElemThermoMedium", "ElemGrinMedium", "ElemTiltedPlate",
               "ElemTiltedCrystal", "ElemBrewsterPlate",
               "ElemBrewsterCrystal", "ElemThickLens")

#: Element types with one reflecting (front) surface.
MIRROR_TYPES = ("ElemFlatMirror", "ElemCurveMirror")

#: Element types with material / coating that a ghost waist can
#: damage. Free-space ranges (air) are never burn candidates: a
#: waist in air is harmless.
MATERIAL_TYPES = MIRROR_TYPES + PLATE_TYPES

#: Reflectivity keys per wavelength (nm) in the side-car.
R_KEYS = {1064.0: "R_1064", 808.0: "R_808", 532.0: "R_532"}


class GhostError(ValueError):
    """Raised when a ghost scan cannot be set up."""


# --- Small helpers ---------------------------------------------------------

def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _pos_number(value):
    return _is_number(value) and float(value) > 0


def _frac01(value):
    return _is_number(value) and 0.0 <= float(value) <= 1.0


def etalon_fsr_Hz(n, L_m):
    """Free spectral range ``c / (2*n*L)`` in Hz."""
    if n is None or L_m is None or n <= 0 or L_m <= 0:
        raise GhostError("etalon FSR needs positive n and L, got %r, %r"
                         % (n, L_m))
    return C_LIGHT / (2.0 * n * L_m)


def etalon_modulation(R1, R2):
    """Peak-to-valley etalon modulation depth.

    ``M = 4*sqrt(R1*R2) / (1 + sqrt(R1*R2))^2``.
    """
    if R1 is None or R2 is None or R1 < 0 or R2 < 0:
        raise GhostError("etalon modulation needs non-negative "
                         "reflectivities, got %r, %r" % (R1, R2))
    s = math.sqrt(R1 * R2)
    return 4.0 * s / (1.0 + s) ** 2


def reflect_q(q_main, C_per_m):
    """``q`` of the beam reflected off a surface of power ``C``.

    ``q_main`` is the incident beam's ``q`` in its own frame; the
    reflected beam's ``q`` (own frame) is ``M . (-conj(q_main))``
    with ``M = [[1, 0], [C, 1]]``: the incident beam seen from the
    reflected beam's frame is its time reversal ``-conj(q)``. For a
    flat face (``C = 0``) this is exactly the time-reversed beam.
    ``C`` is in 1/m.
    """
    q_inc = -q_main.conjugate()
    return q_inc / (C_per_m * q_inc + 1.0)


def plate_lateral_offset_mm(L_mm, alpha_rad, n):
    """Lateral displacement of a ray through a tilted parallel plate.

    ``Delta = L*sin(alpha-beta)/cos(beta)`` with
    ``sin(beta) = sin(alpha)/n`` (``alpha`` the incidence angle,
    ``beta`` the angle inside). The ghost (double pass) is offset
    by ``2*Delta``. Returns 0 for ``alpha == 0``.
    """
    if alpha_rad == 0 or n is None or n <= 0:
        return 0.0
    sin_beta = math.sin(alpha_rad) / n
    if abs(sin_beta) >= 1.0:
        raise GhostError("total internal reflection in a tilted plate: "
                         "sin(alpha)/n = %r" % (sin_beta,))
    beta = math.asin(sin_beta)
    return L_mm * math.sin(alpha_rad - beta) / math.cos(beta)


def divergence_mrad(w_mm, lambda_nm):
    """Far-field half-angle divergence ``lambda/(pi*w)`` in mrad."""
    if w_mm is None or w_mm <= 0:
        raise GhostError("divergence needs a positive beam radius")
    return lambda_nm * 1e-6 / (math.pi * w_mm)


def _reverse_matrix(M):
    """Reverse-traversal matrix of a 2x2 ABCD matrix: ``[[D, B], [C, A]]``."""
    return np.array([[M[1, 1], M[0, 1]], [M[1, 0], M[0, 0]]], dtype=float)


def _propagate_q(q, M):
    """``q`` through a 2x2 ABCD matrix."""
    A, B = M[0]
    C, D = M[1]
    return (A * q + B) / (C * q + D)


def _wr_mm(q_T, q_S, lam_m):
    """``(w_T_mm, w_S_mm)`` from two complex beam parameters."""
    w_T, _R_T = wr_from_q(q_T, lam_m)
    w_S, _R_S = wr_from_q(q_S, lam_m)
    return w_T * 1e3, w_S * 1e3


# --- Chain and surfaces ------------------------------------------------------

def build_chain(data, result, eng=None):
    """The unfolded element chain with positions, matrices and beam.

    One segment per active element, in list order::

        {"label", "type", "s_in_mm", "s_out_mm", "L_mm",
         "M_T", "M_S",            # 2x2 ABCD matrices (SI, numpy)
         "alpha_rad",             # incidence angle (AOI), 0 when none
         "R_m",                   # curvature radius (m), None when flat
         "n",                     # refractive index, 1 when none
         "aperture_mm",           # clear aperture diameter (side-car)
         "w_T_mm", "w_S_mm", "R_T_mm", "R_S_mm"}  # CLI exit beam

    ``s = 0`` at the first element's plane; an element's plane is
    its exit plane (the CLI convention). ``result`` is one CLI
    result dict with a beam list.
    """
    eng = eng or {}
    eng_elements = eng.get("elements")
    eng_elements = eng_elements if isinstance(eng_elements, dict) else {}
    beam = {}
    beam_list = result.get("beam") if isinstance(result, dict) else None
    if beam_list:
        for entry in beam_list:
            if isinstance(entry, dict) and entry.get("label") is not None:
                beam[entry["label"]] = entry
    chain = []
    for elem in elements(data):
        if not isinstance(elem, dict) or elem.get("is_disabled"):
            continue
        label = elem.get("label")
        etype = elem.get("type")
        try:
            s_out = element_plane_position_mm(data, label)
        except Exception as e:
            raise GhostError("cannot locate element %r: %s" % (label, e))
        L_m = param_value_si(data, label, "L")
        L_mm = 0.0 if L_m is None else L_m * 1e3
        try:
            M_T, M_S = element_matrix(data, label)
        except QevolveError:
            # Element types without an ABCD matrix (e.g. apertures,
            # pumps) do not take part in the ghost trace.
            M_T = M_S = None
        alpha = param_value_si(data, label, "Alpha")
        alpha = 0.0 if alpha is None else float(alpha)
        R_m = param_value_si(data, label, "R")
        n = param_value_si(data, label, "n")
        n = 1.0 if n is None else float(n)
        entry = eng_elements.get(label)
        entry = entry if isinstance(entry, dict) else {}
        aperture = entry.get("aperture_diameter_mm")
        aperture = float(aperture) if _pos_number(aperture) else None
        b = beam.get(label)
        chain.append({
            "label": label, "type": etype,
            "s_in_mm": s_out - L_mm, "s_out_mm": s_out, "L_mm": L_mm,
            "M_T": M_T, "M_S": M_S,
            "alpha_rad": alpha, "R_m": R_m, "n": n,
            "aperture_mm": aperture,
            "w_T_mm": (None if b is None else b.get("w_T_mm")),
            "w_S_mm": (None if b is None else b.get("w_S_mm")),
            "R_T_mm": (None if b is None else b.get("R_T_mm")),
            "R_S_mm": (None if b is None else b.get("R_S_mm")),
        })
    return chain


def _sidecar_surfaces(eng):
    data = (eng or {}).get("surfaces")
    return data if isinstance(data, dict) else {}


def _face_reflectivity_power(data, seg, face, spec):
    """Reflection power ``C`` (1/m) of a surface face.

    Flat faces: 0. A side-car ``R_face_mm`` (mirror convention:
    positive = concave toward the incident beam) gives
    ``C = -2/R_face``. For ``ElemThickLens`` the radii come from the
    element's R1/R2 parameters (C++ convention "positive R1/R2
    bulges to the left"): front face ``C = +2/R1``, back face
    ``C = -2/R2``.
    """
    spec = spec if isinstance(spec, dict) else {}
    R_face = spec.get("R_face_mm")
    if _is_number(R_face) and float(R_face) != 0.0:
        return -2.0 / (float(R_face) * 1e-3)
    if seg["type"] == "ElemThickLens":
        R1 = param_value_si(data, seg["label"], "R1")
        R2 = param_value_si(data, seg["label"], "R2")
        if face == "front" and R1 is not None and R1 != 0 \
                and math.isfinite(R1):
            return 2.0 / R1
        if face == "back" and R2 is not None and R2 != 0 \
                and math.isfinite(R2):
            return -2.0 / R2
    return 0.0


def build_surfaces(data, eng=None):
    """Optical surfaces of the chain, with side-car reflectivities.

    One entry per surface::

        {"element", "face", "s_mm", "R": {1064: .., 808: .., 532: ..},
         "wedge_mrad", "wedge_plane", "role", "C_per_m",
         "alpha_rad", "n", "L_mm"}

    ``face`` is ``"front"`` (entrance plane) or ``"back"`` (exit
    plane). Mirror front faces are *not* listed: their reflection
    is the main beam, not a ghost; a mirror's substrate back face
    is listed when the side-car gives it. Reflectivities absent
    from the side-car are ``None`` (nodata, never defaulted).
    """
    chain = build_chain(data, {"beam": []}, eng)
    surfaces = _sidecar_surfaces(eng)
    out = []
    for seg in chain:
        label = seg["label"]
        etype = seg["type"]
        spec = surfaces.get(label)
        spec = spec if isinstance(spec, dict) else {}
        faces = spec.get("faces")
        faces = faces if isinstance(faces, list) else []
        by_face = {}
        for face in faces:
            if isinstance(face, dict) and face.get("face") in ("front",
                                                              "back"):
                by_face[face["face"]] = face
        if etype in MIRROR_TYPES:
            face = by_face.get("back")
            if face is not None:
                out.append(_surface(data, seg, "back", face))
        elif etype in PLATE_TYPES:
            for name, s_mm in (("front", seg["s_in_mm"]),
                               ("back", seg["s_out_mm"])):
                out.append(_surface(data, seg, name,
                                    by_face.get(name)))
    return out


def _surface(data, seg, face, spec):
    spec = spec if isinstance(spec, dict) else {}
    R = {}
    for lam, key in R_KEYS.items():
        value = spec.get(key)
        R[lam] = float(value) if _frac01(value) else None
    wedge = spec.get("wedge_mrad")
    wedge = float(wedge) if _is_number(wedge) else 0.0
    plane = str(spec.get("wedge_plane", "T")).upper()
    plane = plane if plane in ("T", "S") else "T"
    return {"element": seg["label"], "face": face,
            "s_mm": seg["s_in_mm"] if face == "front" else seg["s_out_mm"],
            "R": R, "wedge_mrad": wedge, "wedge_plane": plane,
            "role": spec.get("role"),
            "C_per_m": _face_reflectivity_power(data, seg, face, spec),
            "alpha_rad": seg["alpha_rad"], "n": seg["n"],
            "L_mm": seg["L_mm"]}


def surface_angle_mrad(a, b):
    """Relative normal angle (mrad) of two surfaces, unfolded frame.

    ``|alpha_a - alpha_b| + wedge`` -- the same-sense fold gives the
    smallest possible relative angle, so this estimate is
    conservative for etalon detection (it can only over-flag pairs).
    """
    return abs(a["alpha_rad"] - b["alpha_rad"]) * 1e3 \
        + abs(a["wedge_mrad"]) + abs(b["wedge_mrad"])


def _surf_id(surface):
    return "%s:%s" % (surface["element"], surface["face"])


# --- Round-trip items ----------------------------------------------------------

def build_roundtrip_items(data, chain):
    """Round-trip list items with s-intervals (C++ order).

    One entry per list item::

        {"label", "type", "s_in_mm", "s_out_mm", "L_mm",
         "M_T", "M_S", "seg", "forward"}   # forward: first half

    ``s`` is the unfolded coordinate (0 at the reference element's
    plane, increasing along the forward pass, decreasing on the
    return pass). The reference is the first element. Sanity: the
    walk must return to s = 0 and its maximum must be the total
    length. Only SW trip types are supported (SP has no round trip;
    RR needs a different wrap-around rule).
    """
    trip = str(data.get("trip_type") or "SW").upper()
    if trip != "SW":
        raise GhostError("ghost tracing needs a standing-wave cavity, "
                         "not trip_type %r" % (trip,))
    labels = [seg["label"] for seg in chain]
    if not labels:
        raise GhostError("empty chain")
    try:
        trip_idx = roundtrip_list(labels, labels[0], trip)
    except JacobianError as e:
        raise GhostError(str(e))
    n = len(labels)
    total = total_length_mm(data)
    by_label = {seg["label"]: seg for seg in chain}
    items = []
    s_mm = 0.0
    for j, label in enumerate(trip_idx):
        seg = by_label[label]
        forward = j < n
        direction = 1.0 if forward else -1.0
        s_in = s_mm
        s_out = s_mm + direction * seg["L_mm"]
        items.append({"label": seg["label"], "type": seg["type"],
                      "s_in_mm": s_in, "s_out_mm": s_out,
                      "L_mm": seg["L_mm"], "M_T": seg["M_T"],
                      "M_S": seg["M_S"], "seg": seg,
                      "forward": forward})
        s_mm = s_out
    if abs(s_mm) > 1e-6:
        raise GhostError("round-trip walk does not close: ends at s=%r mm"
                         % (s_mm,))
    if abs(max(it["s_in_mm"] for it in items) - total) > 1e-6 \
            and abs(max(it["s_out_mm"] for it in items) - total) > 1e-6:
        raise GhostError("round-trip walk does not reach the total "
                         "length %r mm" % (total,))
    return items


# --- Etalon scan --------------------------------------------------------------

def scan_etalons(data, eng=None, wavelength_nm=1064.0, chain=None):
    """Parasitic-etalon pairs: FSR + modulation depth + verdict.

    ``chain`` (built by :func:`build_chain` with a CLI result) is
    used for the beam radii; when omitted the CLI is run here.
    Returns a list of dicts (one per surviving pair)::

        {"surface_a", "surface_b", "R1", "R2", "L_mm", "n",
         "FSR_GHz", "modulation", "angle_mrad", "theta_div_mrad",
         "status"}   # "ok" / "warn" / "nodata"

    Pairs are pruned by ``R_i*R_j > 1e-6`` and by the near-parallel
    condition (relative normal angle < beam divergence). A pair with
    a missing reflectivity is reported as ``nodata`` only when the
    *other* surface's reflectivity is large enough that the pair
    could matter (``R_other > 1e-6``); fully unknown pairs are
    skipped silently.
    """
    lam_nm = float(wavelength_nm)
    key = R_KEYS.get(lam_nm)
    if key is None:
        raise GhostError("etalon scan supports 1064/808/532 nm, got %r"
                         % (lam_nm,))
    if chain is None:
        chain = build_chain(data, {"beam": []}, eng)
    surfaces = build_surfaces(data, eng)
    beam_by_label = {seg["label"]: seg for seg in chain}
    results = []
    for i, a in enumerate(surfaces):
        for b in surfaces[i + 1:]:
            Ra, Rb = a["R"].get(lam_nm), b["R"].get(lam_nm)
            if Ra is None and Rb is None:
                continue
            if Ra is None or Rb is None:
                known = Rb if Ra is None else Ra
                if known is None or known <= ETALON_MIN_RR:
                    continue
                results.append({
                    "surface_a": _surf_id(a), "surface_b": _surf_id(b),
                    "R1": Ra, "R2": Rb, "L_mm": None, "n": None,
                    "FSR_GHz": None, "modulation": None,
                    "angle_mrad": surface_angle_mrad(a, b),
                    "theta_div_mrad": None, "status": "nodata",
                    "message": "missing reflectivity for %s"
                               % _surf_id(a if Ra is None else b)})
                continue
            if Ra * Rb <= ETALON_MIN_RR:
                continue
            seg = beam_by_label.get(a["element"]) or {}
            w_mm = seg.get("w_T_mm") or seg.get("w_S_mm")
            if w_mm is None:
                continue
            theta_div = divergence_mrad(w_mm, lam_nm)
            angle = surface_angle_mrad(a, b)
            if angle >= theta_div:
                continue
            L_mm = abs(b["s_mm"] - a["s_mm"])
            n = a["n"] if a["element"] == b["element"] else 1.0
            fsr = etalon_fsr_Hz(n, L_mm * 1e-3) / 1e9
            mod = etalon_modulation(Ra, Rb)
            results.append({
                "surface_a": _surf_id(a), "surface_b": _surf_id(b),
                "R1": Ra, "R2": Rb, "L_mm": L_mm, "n": n,
                "FSR_GHz": fsr, "modulation": mod,
                "angle_mrad": angle, "theta_div_mrad": theta_div,
                "status": "warn" if mod > MODULATION_WARN else "ok",
                "message": ("modulation %.3g%% %s 5%% threshold"
                            % (100.0 * mod,
                               "exceeds" if mod > MODULATION_WARN
                               else "below"))})
    return results


# --- Ghost tracing --------------------------------------------------------------

def _q_at_surface(chain, surface, lambda_nm):
    """Main-beam ``(q_T, q_S)`` incident on a surface (air side, SI).

    The ghost is generated by the beam *arriving* at the surface:
    for a plate face that is the previous element's exit (front) or
    the element's own exit (back -- the ``n`` factors of the
    internal reflection and the exit refraction cancel for a flat
    face, so the air-side exit ``q`` is the right incident ``q``).
    For a *mirror* back face the incident beam is the beam *before*
    the mirror (the CLI reports the beam after reflection), so the
    mirror matrix is inverted: ``q_inc = q_exit/(1 - C*q_exit)``
    per plane (``C = M[1, 0]``). For a flat mirror this is the
    identity; for M4 (R = 100000 mm) it removes a ~1e-3 waist error.
    """
    lam_m = lambda_nm * 1e-9
    seg = None
    for entry in chain:
        if entry["label"] == surface["element"]:
            seg = entry
            break
    if seg is None:
        raise GhostError("surface element %r is not in the chain"
                         % (surface["element"],))
    if surface["face"] == "back":
        w_T, w_S = seg["w_T_mm"], seg["w_S_mm"]
        R_T, R_S = seg["R_T_mm"], seg["R_S_mm"]
    else:
        idx = chain.index(seg)
        if idx == 0:
            raise GhostError("front face of the first element %r has no "
                             "reported entrance beam"
                             % (surface["element"],))
        prev = chain[idx - 1]
        w_T, w_S = prev["w_T_mm"], prev["w_S_mm"]
        R_T, R_S = prev["R_T_mm"], prev["R_S_mm"]
    if w_T is None or w_S is None:
        raise GhostError("no CLI beam radius at surface %s "
                         "(unstable cavity?)" % _surf_id(surface))
    q_T = q_from_wr(w_T * 1e-3,
                    None if R_T is None else R_T * 1e-3, lam_m)
    q_S = q_from_wr(w_S * 1e-3,
                    None if R_S is None else R_S * 1e-3, lam_m)
    if surface["face"] == "back" and seg["type"] in MIRROR_TYPES \
            and seg["M_T"] is not None:
        # Beam before the mirror (the CLI exit is after reflection).
        C_T = float(seg["M_T"][1, 0])
        C_S = float(seg["M_S"][1, 0])
        q_T = q_T / (1.0 - C_T * q_T)
        q_S = q_S / (1.0 - C_S * q_S)
    return q_T, q_S


def _submatrix_q(q, u_m, n0, gamma):
    """Medium-side ``q`` at depth ``u_m`` inside a GRIN/range element.

    The scalar form of ``qevolve._m1_matrices`` (the C++
    ``calcSubmatrices`` ``TS1_``): the submatrix maps the air-side
    ``q`` at the face to the medium-side ``q`` at depth ``u``.
    ``gamma > 0`` focusing (cos/sin), ``gamma < 0`` defocusing
    (cosh/sinh), ``gamma == 0`` plain medium.
    """
    if gamma > 0:
        gz = gamma * u_m
        A = math.cos(gz)
        B = math.sin(gz) / (n0 * gamma)
        C = -gamma * math.sin(gz)
        D = math.cos(gz) / n0
    elif gamma < 0:
        g = -gamma
        gz = g * u_m
        A = math.cosh(gz)
        B = math.sinh(gz) / (n0 * g)
        C = g * math.sinh(gz)
        D = math.cosh(gz) / n0
    else:
        A, B, C, D = 1.0, u_m / n0, 0.0, 1.0 / n0
    return (A * q + B) / (C * q + D)


def _submatrix_w(q, u_m, n0, gamma, lam0_m):
    """Beam radius (m) at depth ``u_m`` inside a GRIN/range element.

    The radius is taken from the medium-side ``q`` with the local
    wavelength ``lam0/n0``.
    """
    q_med = _submatrix_q(q, u_m, n0, gamma)
    w, _R = wr_from_q(q_med, lam0_m / n0)
    return w


def _radii_at_depth(data, item, q_T, q_S, u_m, lam0_m):
    """``(w_T_m, w_S_m)`` at ghost-path distance ``u_m`` inside an element.

    The ghost enters the element from its exit face; by the
    element's z-symmetry the submatrix from that face is the same
    form as from the entrance face. Non-range elements fall back
    to free space (``q + u``) -- the segment is short.
    """
    seg = item["seg"]
    try:
        _L, n0, g_T, g_S = element_grin_params(data, seg["label"])
    except (QevolveError, ValueError):
        return (wr_from_q(q_T + u_m, lam0_m)[0],
                wr_from_q(q_S + u_m, lam0_m)[0])
    w_T = _submatrix_w(q_T, u_m, n0, g_T, lam0_m)
    w_S = _submatrix_w(q_S, u_m, n0, g_S, lam0_m)
    return w_T, w_S


def _waist_depths(data, item, q, plane, lam0_m):
    """Depths ``u`` (m) inside a segment where the beam has a waist.

    The waist is where ``Re(q_med(u)) == 0`` with ``q_med`` the
    medium-side ``q`` at depth ``u``. Using the air-side ``Re(q)``
    would be wrong inside a refractive segment (``n > 1``): the
    physical waist is at ``u = -n*Re(q_air)`` for a plain plate,
    not ``-Re(q_air)``. Returns a list of ``(u_m, w0_m, z_R_m)``
    with ``w0`` the waist radius and ``z_R`` the Rayleigh range
    *in the medium* (``Im(q_med)``). Roots are found by sampling
    + Brent (the function is smooth over one segment).
    """
    seg = item["seg"]
    L_m = item["L_mm"] * 1e-3
    if L_m <= 0:
        return []
    try:
        _L, n0, g_T, g_S = element_grin_params(data, seg["label"])
        gamma = g_T if plane == "T" else g_S
    except (QevolveError, ValueError):
        n0, gamma = seg["n"], 0.0
    lam_med = lam0_m / n0

    def f(u):
        return _submatrix_q(q, u, n0, gamma).real

    n_samp = 60
    us = [i * L_m / n_samp for i in range(n_samp + 1)]
    vals = [f(u) for u in us]
    roots = []
    for i in range(n_samp):
        a, b = us[i], us[i + 1]
        fa, fb = vals[i], vals[i + 1]
        if fa == 0.0:
            roots.append(a)
        elif fa * fb < 0:
            roots.append(brentq(f, a, b, xtol=1e-12))
    if vals[-1] == 0.0:
        roots.append(us[-1])
    out = []
    for u in roots:
        q_med = _submatrix_q(q, u, n0, gamma)
        w0 = math.sqrt(lam_med * q_med.imag / math.pi)
        out.append((u, w0, q_med.imag))
    return out


def trace_ghost(data, chain, surface, lambda_nm, q_start=None):
    """Trace one first-order ghost; return the path record.

    The ghost starts at ``surface`` (travelling opposite to the
    generating pass) and walks the round-trip list backwards for at
    most one full round trip. Returns::

        {"surface", "R_ghost",
         "path": [(label, s_mm, w_T_mm, w_S_mm, x_T_mm, x_S_mm)],
         "waists": [{"s_mm", "plane", "w0_mm", "z_R_mm",
                     "w_other_mm"}],
         "exited": None | {"element", "s_mm", "message"},
         "x_T_mm", "x_S_mm"}  # ray centre at the last visited plane

    ``q_start`` overrides the generated ``(q_T, q_S)`` (tests). The
    ray centre starts at ``(2*Delta, 2*wedge)`` in the wedge plane
    (``Delta`` the tilted-plate lateral offset, ``wedge`` the face
    non-parallelism); both are 0 for a flat un-wedged face.
    """
    lam_m = lambda_nm * 1e-9
    items = build_roundtrip_items(data, chain)
    n_items = len(items)
    n_labels = len(chain)
    # Forward occurrence of the generating element.
    j0 = None
    for j, item in enumerate(items):
        if j < n_labels and item["label"] == surface["element"]:
            j0 = j
            break
    if j0 is None:
        raise GhostError("surface element %r is not in the round trip"
                         % (surface["element"],))
    gen = items[j0]
    if q_start is None:
        q_T, q_S = _q_at_surface(chain, surface, lambda_nm)
        q_T = reflect_q(q_T, surface["C_per_m"])
        q_S = reflect_q(q_S, surface["C_per_m"])
    else:
        q_T, q_S = q_start
    # Ray centre at generation (ghost frame, mm / rad).
    delta = plate_lateral_offset_mm(gen["L_mm"], gen["seg"]["alpha_rad"],
                                    gen["seg"]["n"]) \
        if gen["type"] in PLATE_TYPES else 0.0
    wedge = surface["wedge_mrad"] * 1e-3
    if surface["wedge_plane"] == "T":
        x_T, x_S = 2.0 * delta, 0.0
        th_T, th_S = 2.0 * wedge, 0.0
    else:
        x_T, x_S = 0.0, 2.0 * delta
        th_T, th_S = 0.0, 2.0 * wedge
    # Start boundary: the ghost leaves the surface plane backwards.
    # Back face of a range: first crossed item is the element
    # itself; front face or mirror: the previous item.
    if surface["face"] == "back" and gen["type"] not in MIRROR_TYPES:
        b = (j0 + 1) % n_items
        s_mm = gen["s_out_mm"]
    else:
        b = j0 % n_items
        s_mm = gen["s_in_mm"]
    path = [(gen["label"], s_mm, *_wr_mm(q_T, q_S, lam_m), x_T, x_S)]
    waists = []
    exited = None
    steps = 0
    while steps < n_items:
        steps += 1
        j = (b - 1) % n_items
        item = items[j]
        seg = item["seg"]
        L_mm = item["L_mm"]
        L_m = L_mm * 1e-3
        s_entrance = item["s_out_mm"]  # ghost enters here
        sigma = 1.0 if item["s_in_mm"] > item["s_out_mm"] else -1.0
        # Waist inside this segment, per plane: the depths where
        # Re(q_med(u)) == 0 (see _waist_depths -- the air-side
        # Re(q) is wrong inside a refractive segment).
        if L_m > 0 and item["M_T"] is not None:
            for plane, q in (("T", q_T), ("S", q_S)):
                for (u_m, w0_m, z_R_m) in _waist_depths(
                        data, item, q, plane, lam_m):
                    s_waist = s_entrance + sigma * u_m * 1e3
                    wT_w, wS_w = _radii_at_depth(data, item, q_T, q_S,
                                                 u_m, lam_m)
                    w_other = wS_w if plane == "T" else wT_w
                    waists.append({"s_mm": s_waist, "plane": plane,
                                   "w0_mm": w0_m * 1e3,
                                   "z_R_mm": z_R_m * 1e3,
                                   "w_other_mm": w_other * 1e3})
        # Propagate q and the ray through the crossed item. The
        # ghost traverses it opposite to the list orientation:
        # reverse-traversal matrix for forward-pass items, forward
        # matrix for return-pass items.
        if item["M_T"] is not None:
            if item["forward"]:
                M_T = _reverse_matrix(item["M_T"])
                M_S = _reverse_matrix(item["M_S"])
            else:
                M_T, M_S = item["M_T"], item["M_S"]
            q_T = _propagate_q(q_T, M_T)
            q_S = _propagate_q(q_S, M_S)
            x_T, th_T = _ray_step(x_T, th_T, M_T)
            x_S, th_S = _ray_step(x_S, th_S, M_S)
        s_mm = item["s_in_mm"]
        b = j
        label = item["label"]
        w_T_mm, w_S_mm = _wr_mm(q_T, q_S, lam_m)
        path.append((label, s_mm, w_T_mm, w_S_mm, x_T, x_S))
        # Aperture check at this plane: the limiting aperture is
        # the smaller of the two elements sharing the plane (the
        # crossed item's entrance and the previous item's exit --
        # a mirror's aperture sits at exactly this plane).
        ap_label = None
        ap_r = None
        for cand in (item, items[(j - 1) % n_items]):
            ap = cand["seg"]["aperture_mm"]
            if ap is not None:
                r = ap / 2.0
                if ap_r is None or r < ap_r:
                    ap_r = r
                    ap_label = cand["label"]
        if ap_r is not None:
            if abs(x_T) > ap_r or abs(x_S) > ap_r:
                exited = {"element": ap_label, "s_mm": s_mm,
                          "message": "ray centre outside the %.4g mm "
                                     "clear aperture (x_T=%.4g mm, "
                                     "x_S=%.4g mm)"
                                     % (2.0 * ap_r, x_T, x_S)}
                break
    # Dedupe waists: the walk crosses each physical segment twice
    # (once per pass), so the same waist is found twice.
    seen = set()
    unique_waists = []
    for waist in waists:
        key = (waist["plane"], round(waist["s_mm"], 6))
        if key in seen:
            continue
        seen.add(key)
        unique_waists.append(waist)
    return {"surface": _surf_id(surface),
            "R_ghost": surface["R"].get(float(lambda_nm)),
            "path": path, "waists": unique_waists, "exited": exited,
            "x_T_mm": x_T, "x_S_mm": x_S}


def _ray_step(x_mm, theta, M):
    """Ray ``(x_mm, theta)`` through a 2x2 ABCD matrix (SI).

    ``x`` is kept in mm and ``theta`` in radians; the matrix
    entries are SI (``B`` in m, ``C`` in 1/m), so the products are
    converted: ``B*1e3*theta`` (mm) and ``C*x*1e-3`` (rad).
    """
    A, B = M[0]
    C, D = M[1]
    return A * x_mm + B * 1e3 * theta, C * x_mm * 1e-3 + D * theta


# --- Burn-point scan ----------------------------------------------------------

def _burn_for(elem, s_waist, w0_T, w0_S, energy, R, eng_elements):
    """Burn verdict for one candidate element at a ghost waist.

    ``energy`` is the pulse energy (J) at the scan wavelength,
    ``R`` the ghost reflectivity. Returns a burn dict with
    ``status`` in ok/warn/fail/nodata.
    """
    entry = eng_elements.get(elem["label"])
    entry = entry if isinstance(entry, dict) else {}
    lidt = entry.get("lidt_J_per_cm2")
    lidt = float(lidt) if _pos_number(lidt) else None
    where = "at" if elem["type"] in MIRROR_TYPES else "inside"
    if energy is None:
        return {"element": elem["label"], "s_mm": s_waist,
                "w0_T_mm": w0_T, "w0_S_mm": w0_S,
                "fluence_J_per_cm2": None, "lidt_J_per_cm2": lidt,
                "ratio": None, "status": "nodata",
                "message": "waist %s %s but no pulse_energy_J in the "
                           "side-car" % (where, elem["label"])}
    fluence = lidt_fluence_J_per_cm2(energy * R, w0_T, w0_S)
    if lidt is None:
        return {"element": elem["label"], "s_mm": s_waist,
                "w0_T_mm": w0_T, "w0_S_mm": w0_S,
                "fluence_J_per_cm2": fluence, "lidt_J_per_cm2": None,
                "ratio": None, "status": "nodata",
                "message": "waist %s %s, ghost fluence %.4g J/cm^2, "
                           "but no LIDT for this element"
                           % (where, elem["label"], fluence)}
    ratio = fluence / lidt
    bstatus = "fail" if ratio > LIDT_FAIL_RATIO else \
        ("warn" if ratio > LIDT_WARN_RATIO else "ok")
    return {"element": elem["label"], "s_mm": s_waist,
            "w0_T_mm": w0_T, "w0_S_mm": w0_S,
            "fluence_J_per_cm2": fluence, "lidt_J_per_cm2": lidt,
            "ratio": ratio, "status": bstatus,
            "message": "ghost waist %s %s: fluence %.4g J/cm^2, "
                       "%.1f%% of LIDT %.4g J/cm^2"
                       % (where, elem["label"], fluence,
                          100.0 * ratio, lidt)}


def scan_ghosts(data, eng=None, wavelength_nm=1064.0, binary=DEFAULT_BINARY,
                timeout=None):
    """First-order ghost scan: burn-point report.

    Returns::

        {"version", "wavelength_nm", "ghosts": [...], "etalons": [...],
         "summary": {"ok/warn/fail/nodata counts"}, "warnings": [...]}

    Each ghost entry::

        {"surface", "R_ghost", "status",
         "waists": [{"s_mm", "plane", "w0_mm", "z_R_mm", "w_other_mm"}],
         "burn": None | {"element", "s_mm", "w0_T_mm", "w0_S_mm",
                          "fluence_J_per_cm2", "lidt_J_per_cm2",
                          "ratio", "status", "message"},
         "exited": None | {...}, "message": ...}

    A ghost is ``fail`` when a waist inside an element exceeds that
    element's LIDT, ``warn`` above 80% of LIDT, ``ok`` otherwise;
    ``nodata`` when the reflectivity, the pulse energy or the LIDT
    is missing. A ghost that leaves every aperture is ``ok`` with a
    note (it cannot burn an optic). The ghost energy is
    ``E_p * R_ghost`` (conservative: transmission losses along the
    ghost path are ignored).
    """
    lam_nm = float(wavelength_nm)
    if lam_nm <= 0:
        raise GhostError("wavelength must be positive, got %r"
                         % (lam_nm,))
    rez_data = data if isinstance(data, dict) else load_rez(data)
    eng_data = eng if isinstance(eng, dict) else load_eng(eng)
    warnings = validate_eng(eng_data)
    result = run_headless({"base_schema": rez_data, "mutations": []},
                          binary=binary, timeout=timeout)["results"][0]
    if not result.get("ok"):
        raise GhostError("headless evaluation failed: %s"
                         % result.get("error"))
    if not result.get("stable"):
        raise GhostError("cavity is unstable (g_T=%r, g_S=%r); ghost "
                         "tracing needs the eigenmode beam"
                         % (result.get("g_T"), result.get("g_S")))
    chain = build_chain(rez_data, result, eng_data)
    surfaces = build_surfaces(rez_data, eng_data)
    key = R_KEYS.get(lam_nm)
    if key is None:
        raise GhostError("ghost scan supports 1064/808/532 nm, got %r"
                         % (lam_nm,))
    laser = eng_data.get("laser")
    laser = laser if isinstance(laser, dict) else {}
    energy = laser.get("pulse_energy_J")
    energy = float(energy) if _pos_number(energy) else None
    eng_elements = eng_data.get("elements")
    eng_elements = eng_elements if isinstance(eng_elements, dict) else {}

    ghosts = []
    for surface in surfaces:
        R = surface["R"].get(lam_nm)
        if R is None:
            ghosts.append({"surface": _surf_id(surface), "R_ghost": None,
                           "status": "nodata", "waists": [], "burn": None,
                           "exited": None,
                           "message": "no %s for this surface in the "
                                      "side-car" % key})
            continue
        if R < GHOST_MIN_R:
            ghosts.append({"surface": _surf_id(surface), "R_ghost": R,
                           "status": "ok", "waists": [], "burn": None,
                           "exited": None,
                           "message": "R=%.4g below the %.4g tracing "
                                      "threshold (etalon pairs still "
                                      "scanned)" % (R, GHOST_MIN_R)})
            continue
        trace = trace_ghost(rez_data, chain, surface, lam_nm)
        burn = None
        status = "ok"
        message = "no waist inside any element"
        if trace["exited"] is not None:
            message = ("ghost left the optics at %s (s=%.4g mm): %s"
                       % (trace["exited"]["element"],
                          trace["exited"]["s_mm"],
                          trace["exited"]["message"]))
        # Waist -> burn check. The *primary* candidate is the
        # material element (mirror / plate / crystal) whose span
        # contains the waist; its verdict is authoritative. A
        # nearby mirror (plane within two Rayleigh ranges) can
        # only *upgrade* the verdict to warn/fail (the beam is
        # still tight there); a nearby mirror with no LIDT data
        # is noted but does not override a definitive primary
        # verdict. If the waist is in free space there is no
        # primary and the nearby mirrors decide. Free-space ranges
        # are never candidates: a waist in air is harmless.
        rank = {"ok": 0, "nodata": 1, "warn": 2, "fail": 3}
        for waist in trace["waists"]:
            s_waist = waist["s_mm"]
            z_R = waist["z_R_mm"]
            w0 = waist["w0_mm"]
            w_other = waist["w_other_mm"]
            if waist["plane"] == "T":
                w0_T, w0_S = w0, w_other
            else:
                w0_T, w0_S = w_other, w0
            primary = None
            for elem in chain:
                if elem["type"] in MATERIAL_TYPES and \
                        elem["s_in_mm"] - 1e-9 <= s_waist \
                        <= elem["s_out_mm"] + 1e-9:
                    primary = elem
                    break
            mirrors = [elem for elem in chain
                       if elem["type"] in MIRROR_TYPES
                       and elem is not primary
                       and abs(s_waist - elem["s_out_mm"])
                       <= WAIST_TOL_ZR * z_R]
            if primary is not None:
                verdict = _burn_for(primary, s_waist, w0_T, w0_S,
                                    energy, R, eng_elements)
                for elem in mirrors:
                    mb = _burn_for(elem, s_waist, w0_T, w0_S,
                                   energy, R, eng_elements)
                    if mb["status"] in ("fail", "warn") and \
                            rank[mb["status"]] > rank[verdict["status"]]:
                        verdict = mb
                uneval = [elem["label"] for elem in mirrors
                          if _burn_for(elem, s_waist, w0_T, w0_S,
                                       energy, R,
                                       eng_elements)["status"] == "nodata"]
                if uneval and verdict["status"] == "ok":
                    verdict = dict(verdict)
                    verdict["message"] += (" (nearby mirror %s not "
                                           "evaluated: no LIDT in the "
                                           "side-car)"
                                           % ", ".join(uneval))
            elif mirrors:
                verdict = max((_burn_for(elem, s_waist, w0_T, w0_S,
                                         energy, R, eng_elements)
                               for elem in mirrors),
                              key=lambda c: rank[c["status"]])
            else:
                verdict = None
            if verdict is not None and (burn is None or
                    rank[verdict["status"]] > rank[burn["status"]]):
                burn = verdict
        if burn is not None:
            status = burn["status"]
            message = burn["message"]
        ghosts.append({"surface": _surf_id(surface), "R_ghost": R,
                       "status": status,
                       "waists": trace["waists"],
                       "burn": burn,
                       "exited": trace["exited"],
                       "message": message})
    etalons = scan_etalons(rez_data, eng_data, lam_nm, chain=chain)
    summary = {"ok": 0, "warn": 0, "fail": 0, "nodata": 0}
    for entry in ghosts + etalons:
        summary[entry["status"]] += 1
    summary["total"] = len(ghosts) + len(etalons)
    return {"version": 1, "wavelength_nm": lam_nm, "ghosts": ghosts,
            "etalons": etalons, "summary": summary, "warnings": warnings}


def main(argv=None):
    """CLI entry: ``run_ghosts.py <file.rez> [side-car] [--wavelength NM]``."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Scan a .rez cavity for ghost / etalon hazards.")
    parser.add_argument("rez_path", help=".rez file")
    parser.add_argument("eng_path", nargs="?",
                        help="side-car file (default: <file>.rez.eng.json)")
    parser.add_argument("--wavelength", type=float, default=1064.0,
                        help="scan wavelength in nm (default 1064)")
    parser.add_argument("--binary", default=DEFAULT_BINARY,
                        help="path to the rezonator binary")
    args = parser.parse_args(argv)
    eng_path = args.eng_path or eng_path_for(args.rez_path)
    try:
        report = scan_ghosts(args.rez_path, eng_path, args.wavelength,
                             binary=args.binary)
    except (OSError, ValueError, GhostError) as e:
        print("run_ghosts: %s" % e, file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
