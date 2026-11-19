"""Jones polarisation matrices (Phase 2 block 3).

A complete 2x2 complex Jones matrix is carried along the optical
path, in parallel with (and independent of) the ABCD matrices. Element
data lives in the side-car ``elements_ext`` section, keyed by element
label::

    "elements_ext": {
      "WP1":  {"jones": {"type": "waveplate",
                         "retardance_rad": 1.5708,
                         "fast_axis_deg": 45.0}},
      "TFP1": {"jones": {"type": "polarizer", "Tp": 0.995, "Ts": 0.005,
                         "angle_deg": 0.0}},
      "FR1":  {"jones": {"type": "faraday", "rotation_deg": 45.0}},
      "TL1":  {"jones": {"type": "birefringent_crystal",
                         "retardance_rad": 0.15, "fast_axis_deg": 0.0}}
    }

Conventions (fixed for the whole module -- see the derivation below):

* Basis ``(T, S)`` = the lab frame: ``T`` is the in-plane direction
  (p-polarisation), ``S`` the out-of-plane direction (s-polarisation).
  The cavity is assumed planar: all folds share one plane of
  incidence, so the (T, S) basis is the same everywhere. Out-of-plane
  folds would need a 3-D basis rotation and are out of scope.
* A forward Jones matrix ``J`` is defined in the lab basis for a beam
  propagating in the +z direction.
* A mirror is ``diag(m_T, m_S)`` in the lab basis (default ``(-1, -1)``,
  i.e. an ideal mirror: a global phase only, no polarisation effect).
  In standard Fresnel notation ``m_T = -r_p`` and ``m_S = r_s`` (the
  minus sign is the p-axis flip on reflection); supplying ``r_p`` /
  ``r_s`` directly would give a spurious half-wave effect, so the
  side-car stores the lab-basis pair ``(m_T, m_S)``.

Coordinate flip on the return pass (the main risk point)
--------------------------------------------------------
After the end mirror the beam propagates in -z. The transverse basis
for the backward beam must stay right-handed with -z, so with the S
axis kept fixed the T axis flips: ``(x_b, y_b) = (-x, y)``. A physical
line at angle ``theta`` in the lab basis therefore sits at ``-theta``
in the backward basis, and the backward matrix of a waveplate, written
in its own (backward) basis, is ``J(-theta)``. Conjugating back to the
lab basis with ``M = diag(-1, 1)`` gives ``M J(-theta) M = J(theta)``.
For a *general* reciprocal element the same argument (Lorentz
reciprocity, in the lab basis) gives the compact rule used here:

    reciprocal element:  J_back = J_forward^T
    Faraday rotator:     J_back = J_forward   (no transpose)

For the symmetric matrices of waveplates, polarisers and birefringent
crystals ``J^T = J``, so the transpose is invisible there -- but it is
exactly what distinguishes a reciprocal rotator from a Faraday
rotator: a reciprocal rotator (optical activity) has
``J_back = R(-phi)`` and cancels on a round trip
(``R(-phi) R(phi) = I``), while a Faraday rotator keeps ``R(phi)`` and
doubles (``R(2 phi)``). Both behaviours are locked by tests
(``tests/test_block3.py``).

Round trip (SW cavity, element list ``[M1, ..., M4]``)::

    J_rt = J_M1 . B . J_M4 . F

where ``F`` is the product of the forward matrices of the interior
elements in path order (rightmost applied first) and ``B`` is the
product of the same elements in reverse order with the backward rule
above. The closed loop gives the self-consistent polarisation: the
eigenvector of the largest-|eigenvalue| mode is the cavity eigen
polarisation, and ``1 - |lambda_max|^2`` is the polarisation loss,
which :func:`rezeng.power` accepts as ``extra_loss``.

For ``SP`` files the product is the single-pass matrix; for ``RR``
(ring) it is the one-loop product (eigenvalues are invariant under the
arbitrary choice of starting point).
"""

import cmath
import math

import numpy as np

from .rez import elements

#: Round-trip kinds.
ROUND_TRIP = "round_trip"
SINGLE_PASS = "single_pass"

#: Jones spec types.
_RECIPROCAL_TYPES = ("waveplate", "birefringent_crystal", "polarizer",
                     "rotator", "matrix", "identity")
_ALL_TYPES = _RECIPROCAL_TYPES + ("faraday", "mirror")


class JonesError(ValueError):
    """Raised when a Jones computation cannot be set up."""


# --- Elementary matrices -------------------------------------------------

def rotation_matrix(phi_rad):
    """``R(phi)``: rotates the polarisation angle by ``+phi`` in the
    (T, S) plane (counter-clockwise as seen looking back toward the
    source, i.e. against the propagation direction)."""
    c, s = math.cos(phi_rad), math.sin(phi_rad)
    return np.array([[c, -s], [s, c]], dtype=complex)


def retarder_matrix(gamma_rad, theta_rad):
    """Waveplate / birefringent crystal: retardance ``gamma`` (fast
    axis advanced by ``+gamma/2``, slow by ``-gamma/2``), fast axis at
    ``theta`` from T. ``R(theta) diag(e^{i gamma/2}, e^{-i gamma/2})
    R(-theta)``; the matrix is symmetric. A half-wave plate reflects
    the polarisation about its fast-axis line (angle ``alpha`` maps
    to ``2*theta - alpha``)."""
    d = np.diag([cmath.exp(0.5j * gamma_rad),
                 cmath.exp(-0.5j * gamma_rad)])
    r = rotation_matrix(theta_rad)
    return r @ d @ r.T


def half_wave_plate(theta_deg):
    """Half-wave plate (retardance pi) with fast axis at ``theta``."""
    return retarder_matrix(math.pi, math.radians(theta_deg))


def quarter_wave_plate(theta_deg):
    """Quarter-wave plate (retardance pi/2) with fast axis at ``theta``."""
    return retarder_matrix(math.pi / 2.0, math.radians(theta_deg))


def polarizer_matrix(Tp, Ts, theta_deg=0.0):
    """Polariser: intensity transmittances ``Tp`` (transmission axis)
    and ``Ts``, transmission axis at ``theta`` from T.

    Amplitude coefficients are ``sqrt(T)``. The matrix is symmetric.
    """
    if not (0.0 <= Tp <= 1.0 and 0.0 <= Ts <= 1.0):
        raise JonesError("polariser transmittances must be in [0, 1], "
                         "got Tp=%r, Ts=%r" % (Tp, Ts))
    d = np.diag([math.sqrt(Tp), math.sqrt(Ts)]).astype(complex)
    r = rotation_matrix(math.radians(theta_deg))
    return r @ d @ r.T


def mirror_matrix(m_T=-1.0, m_S=-1.0):
    """Mirror in the lab basis: ``diag(m_T, m_S)``. The default
    ``(-1, -1)`` is an ideal mirror (global phase only)."""
    return np.diag([_to_complex(m_T, "m_T"), _to_complex(m_S, "m_S")])


def _to_complex(value, what):
    """A JSON number, ``[re, im]`` pair, or ``{"re", "im"}`` dict as a
    complex number."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return complex(float(value))
    if isinstance(value, (list, tuple)) and len(value) == 2 \
            and all(isinstance(v, (int, float))
                    and not isinstance(v, bool) for v in value):
        return complex(float(value[0]), float(value[1]))
    if isinstance(value, dict) and "re" in value and "im" in value \
            and isinstance(value["re"], (int, float)) \
            and isinstance(value["im"], (int, float)):
        return complex(float(value["re"]), float(value["im"]))
    raise JonesError("%s must be a number, [re, im] or {re, im}, got %r"
                     % (what, value))


def _finite_number(value, what):
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value))):
        return float(value)
    raise JonesError("%s must be a finite number, got %r" % (what, value))


# --- Specs -----------------------------------------------------------------

def matrix_from_spec(spec):
    """``(J, is_faraday)`` from a side-car ``jones`` spec dict.

    Types: ``waveplate`` / ``birefringent_crystal``
    (``retardance_rad``, ``fast_axis_deg``), ``polarizer`` (``Tp``,
    ``Ts``, ``angle_deg``), ``rotator`` / ``faraday`` (``rotation_deg``),
    ``mirror`` (``m_T``, ``m_S``), ``identity``, ``matrix`` (a raw 2x2
    matrix of numbers or ``[re, im]`` pairs). Only ``faraday`` is
    non-reciprocal.
    """
    if not isinstance(spec, dict):
        raise JonesError("jones spec must be an object, got %r" % (spec,))
    kind = spec.get("type")
    if kind not in _ALL_TYPES:
        raise JonesError("unknown jones type %r (expected one of %s)"
                         % (kind, ", ".join(_ALL_TYPES)))
    if kind in ("waveplate", "birefringent_crystal"):
        gamma = _finite_number(spec.get("retardance_rad"),
                               "retardance_rad")
        theta = _finite_number(spec.get("fast_axis_deg", 0.0),
                               "fast_axis_deg")
        return retarder_matrix(gamma, math.radians(theta)), False
    if kind == "polarizer":
        Tp = _finite_number(spec.get("Tp", 1.0), "Tp")
        Ts = _finite_number(spec.get("Ts", 0.0), "Ts")
        theta = _finite_number(spec.get("angle_deg", 0.0), "angle_deg")
        return polarizer_matrix(Tp, Ts, theta), False
    if kind == "rotator":
        phi = _finite_number(spec.get("rotation_deg"), "rotation_deg")
        return rotation_matrix(math.radians(phi)), False
    if kind == "faraday":
        phi = _finite_number(spec.get("rotation_deg"), "rotation_deg")
        return rotation_matrix(math.radians(phi)), True
    if kind == "mirror":
        return mirror_matrix(spec.get("m_T", -1.0),
                             spec.get("m_S", -1.0)), False
    if kind == "identity":
        return np.eye(2, dtype=complex), False
    # kind == "matrix": raw 2x2.
    raw = spec.get("matrix")
    if (not isinstance(raw, (list, tuple)) or len(raw) != 2
            or any(not isinstance(row, (list, tuple)) or len(row) != 2
                   for row in raw)):
        raise JonesError("matrix spec needs a 2x2 'matrix', got %r"
                         % (raw,))
    return np.array([[_to_complex(raw[i][j], "matrix[%d][%d]" % (i, j))
                      for j in range(2)] for i in range(2)]), False


def _is_mirror(elem):
    return isinstance(elem, dict) and "Mirror" in str(elem.get("type", ""))


def build_sequence(data, eng, insertions=None):
    """One-way element sequence: ``[{label, kind, J, faraday}]``.

    ``kind`` is ``mirror`` / ``element`` / ``inserted``. A mirror
    element takes a ``mirror`` spec from ``elements_ext`` (default
    ideal); any other spec on a mirror label is a configuration
    error, as is a ``mirror`` spec on a non-mirror element.
    ``insertions`` is a list of ``{"after": <label or index>,
    "jones": <spec>, "label": <optional>}`` -- a virtual element
    (e.g. a waveplate) placed at that point of the path without
    touching the .rez file.
    """
    ext = (eng or {}).get("elements_ext")
    ext = ext if isinstance(ext, dict) else {}
    seq = []
    for elem in elements(data):
        if not isinstance(elem, dict):
            continue
        label = elem.get("label")
        entry = ext.get(label) if label is not None else None
        entry = entry if isinstance(entry, dict) else {}
        spec = entry.get("jones")
        if spec is None:
            J = mirror_matrix() if _is_mirror(elem) else np.eye(2,
                                                                 dtype=complex)
            seq.append({"label": label,
                        "kind": "mirror" if _is_mirror(elem) else "element",
                        "J": J, "faraday": False})
            continue
        J, faraday = matrix_from_spec(spec)
        if _is_mirror(elem) and spec.get("type") != "mirror":
            raise JonesError(
                "element %r is a mirror but its jones spec is type %r "
                "(only a 'mirror' spec belongs on a mirror)" % (
                    label, spec.get("type")))
        if not _is_mirror(elem) and spec.get("type") == "mirror":
            raise JonesError(
                "element %r is not a mirror but its jones spec is type "
                "'mirror'" % (label,))
        seq.append({"label": label,
                    "kind": "mirror" if _is_mirror(elem) else "element",
                    "J": J, "faraday": faraday})
    for ins in insertions or []:
        if not isinstance(ins, dict) or "after" not in ins \
                or "jones" not in ins:
            raise JonesError("insertion needs 'after' and 'jones', got %r"
                             % (ins,))
        J, faraday = matrix_from_spec(ins["jones"])
        after = ins["after"]
        if isinstance(after, int):
            pos = after + 1
        else:
            pos = None
            for i, item in enumerate(seq):
                if item["label"] == after:
                    pos = i + 1
                    break
            if pos is None:
                raise JonesError("insertion 'after' label %r not found"
                                 % (after,))
        if pos < 0 or pos > len(seq):
            raise JonesError("insertion position %r out of range"
                             % (after,))
        seq.insert(pos, {"label": ins.get("label", "<inserted>"),
                         "kind": "inserted", "J": J, "faraday": faraday})
    return seq


def _product(items):
    """Product of a sequence's matrices in path order (the first item
    encountered is applied first, i.e. rightmost in the product)."""
    J = np.eye(2, dtype=complex)
    for item in items:
        J = item["J"] @ J
    return J


def _backward_product(items):
    """Product of the reversed sequence with the backward rule
    (reciprocal: transpose; Faraday: unchanged)."""
    J = np.eye(2, dtype=complex)
    for item in reversed(items):
        J = (item["J"] if item["faraday"] else item["J"].T) @ J
    return J


def round_trip_jones(data, eng, insertions=None):
    """Round-trip (SW/RR) or single-pass (SP) Jones matrix.

    Returns ``{J, kind, trip_type, sequence}`` where ``sequence`` is
    the one-way breakdown ``[{label, kind, faraday, J}]``. For SW the
    first and last elements are the end mirrors and
    ``J_rt = J_M1 . B . J_M4 . F``; for RR the loop product is taken
    once; for SP the single-pass product.
    """
    trip = str(data.get("trip_type") or "SW").upper()
    seq = build_sequence(data, eng, insertions)
    if trip == "SP":
        return {"J": _product(seq), "kind": SINGLE_PASS,
                "trip_type": trip, "sequence": seq}
    if trip == "RR":
        return {"J": _product(seq), "kind": ROUND_TRIP,
                "trip_type": trip, "sequence": seq}
    if trip != "SW":
        raise JonesError("unknown trip_type %r" % (trip,))
    if len(seq) < 2:
        raise JonesError("SW round trip needs at least two elements, "
                         "got %d" % len(seq))
    interior = seq[1:-1]
    F = _product(interior)
    B = _backward_product(interior)
    J_rt = seq[0]["J"] @ B @ seq[-1]["J"] @ F
    return {"J": J_rt, "kind": ROUND_TRIP, "trip_type": trip,
            "sequence": seq}


# --- Eigen-polarisation ------------------------------------------------------

def eigen_polarization(J):
    """Eigen-polarisation of a round-trip matrix.

    Returns ``{eigenvalues, lambda_max, eigenvector, loss,
    orientation_deg, ellipticity_deg}``: ``loss = 1 - |lambda_max|^2``
    is the polarisation loss of the self-consistent eigenstate; the
    eigenvector is normalised with its largest component real and
    positive.
    """
    J = np.asarray(J, dtype=complex)
    if J.shape != (2, 2):
        raise JonesError("Jones matrix must be 2x2, got shape %r"
                         % (J.shape,))
    values, vectors = np.linalg.eig(J)
    k = int(np.argmax(np.abs(values)))
    lam = complex(values[k])
    vec = np.array(vectors[:, k], dtype=complex)
    vec = vec / np.linalg.norm(vec)
    # Phase: largest component real and positive.
    j = int(np.argmax(np.abs(vec)))
    if abs(vec[j]) > 0:
        vec = vec * np.exp(-1j * np.angle(vec[j]))
    loss = 1.0 - abs(lam) ** 2
    loss = min(max(loss, 0.0), 1.0)
    ex, ey = vec
    s0 = abs(ex) ** 2 + abs(ey) ** 2
    s1 = abs(ex) ** 2 - abs(ey) ** 2
    s2 = 2.0 * (ex * ey.conjugate()).real
    s3 = 2.0 * (ex * ey.conjugate()).imag
    orientation = 0.5 * math.degrees(math.atan2(s2, s1))
    ellipticity = 0.5 * math.degrees(math.asin(
        max(-1.0, min(1.0, s3 / s0)))) if s0 > 0 else 0.0
    return {"eigenvalues": [complex(v) for v in values],
            "lambda_max": lam, "eigenvector": vec, "loss": loss,
            "orientation_deg": orientation,
            "ellipticity_deg": ellipticity}


def polarization_loss(J):
    """``1 - |lambda_max|^2`` of a round-trip Jones matrix."""
    return eigen_polarization(J)["loss"]


# --- JSON-safe report ---------------------------------------------------------

def _cplx(z):
    return [float(z.real), float(z.imag)]


def _cmat(J):
    return [[_cplx(J[i, j]) for j in range(2)] for i in range(2)]


def jones_report(rez, eng=None, insertions=None):
    """Round-trip Jones report for a .rez file (JSON-safe dict).

    ``rez`` is a .rez path or an already-loaded .rez dict; ``eng`` is
    a side-car path, an already-loaded side-car dict, or None (then
    the side-car next to the .rez file is used -- only when ``rez``
    is a path).
    """
    from .eng import eng_path as eng_path_for, load_eng
    from .rez import load_rez

    if isinstance(rez, dict):
        data = rez
        rez_path = None
    else:
        rez_path = rez
        data = load_rez(rez_path)
    if eng is None:
        eng_path = eng_path_for(rez_path) if rez_path is not None else None
        eng = load_eng(eng_path) if eng_path is not None else {}
    elif isinstance(eng, dict):
        eng_path = None
    else:
        eng_path = eng
        eng = load_eng(eng_path)
    result = round_trip_jones(data, eng, insertions)
    J = result["J"]
    eig = eigen_polarization(J)
    return {
        "rez_path": rez_path,
        "eng_path": eng_path,
        "trip_type": result["trip_type"],
        "kind": result["kind"],
        "J_rt": _cmat(J),
        "eigenvalues": [_cplx(v) for v in eig["eigenvalues"]],
        "lambda_max": _cplx(eig["lambda_max"]),
        "eigenvector": [_cplx(v) for v in eig["eigenvector"]],
        "polarization_loss": eig["loss"],
        "orientation_deg": eig["orientation_deg"],
        "ellipticity_deg": eig["ellipticity_deg"],
        "sequence": [{"label": item["label"], "kind": item["kind"],
                      "faraday": item["faraday"],
                      "J": _cmat(item["J"])}
                     for item in result["sequence"]],
    }
