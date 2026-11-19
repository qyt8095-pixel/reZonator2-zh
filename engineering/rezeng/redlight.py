"""632.8 nm red-light collimation mode (Phase 4 block 1).

A visible HeNe beam is used to align the (invisible) 1064 nm
cavity. This module builds the *cold* cavity (thermal lens
removed, indices at 632.8 nm), re-evaluates it with the CLI, and
compares the red beam with the hot 1064 nm eigenmode at every
reference aperture (each element's exit plane).

**Fallback (implemented, and the normal case):** with the thermal
lens removed the cold cavity is usually unstable, so the CLI
reports ``stable: false`` and there is no red eigenmode. The
module then switches automatically to an *external* HeNe beam
(collimated, default ``w0 = 0.5 mm``) injected from the output
mirror and traced single- or double-pass with the Python-side
ABCD evolver (``qevolve.element_matrix``, the same matrices the
CLI uses). The output is explicitly labelled ``fallback`` so a
red-light table is never mistaken for a cold-cavity eigenmode.

Sellmeier library
-----------------
Coefficients are published literature values (single-oscillator
Sellmeier form ``n^2 - 1 = B1*lam^2/(lam^2 - C1)`` with
``lam`` in um, or the three-term form where noted):

* fused silica: Malitson 1965 (J. Opt. Soc. Am. 55, 1205).
* BK7: Schott data sheet (three-term Sellmeier).
* Nd:YVO4 ``n_o`` / ``n_e``: the standard YVO4 Sellmeier (e.g.
  Zelmon et al. / Castech data, two-term form with a ``- B*lam^2``
  infrared term). Check: at 1064 nm ``n_o = 1.957``,
  ``n_e = 2.165`` (the user's .rez stores TL1 ``n = 2.16``);
  at 632.8 nm ``n_o = 1.993``, ``n_e = 2.215``.
* LBO ``n_x`` / ``n_y`` / ``n_z``: Kato 1991 / standard LBO
  Sellmeier. Check: at 1064 nm ``n_x = 1.565``.

The side-car (``<file>.rez.eng.json``, section ``materials``)
stores only a material ID per element plus optional overrides::

    "materials": {
      "TL1": {"material": "Nd:YVO4:e", "n_1064": 2.16,
              "n_633": 2.2154},
      "M4":  {"material": "fused_silica"}
    }

An element with no material entry keeps its .rez index and is
reported with a warning (no index is ever invented).

Conventions
-----------
* **Alpha is the angle of incidence (AOI)** -- see
  ``src/core/Elements.cpp`` ``ElemCurveMirror`` ("入射角").
  The full fold angle is ``2*Alpha``.
* The injected beam is traced in the *unfolded* frame: travelling
  from the output mirror toward the first element it crosses each
  element with the reverse-traversal matrix ``[[D, B], [C, A]]``
  (identical to the forward matrix for every symmetric element);
  on the double-pass return it uses the forward matrices. At the
  turnaround mirror the reflected beam is
  ``q' = M . (-conj(q))`` (time reversal through the mirror matrix)
  and the ray angle picks up the mirror kick ``theta' = theta + C*x``.
  A tilted plate displaces the ray laterally by
  ``Delta = L*sin(alpha-beta)/cos(beta)`` (forward ``+Delta``,
  backward ``-Delta``); a wedged plate deflects the transmitted
  beam by ``(n-1)*wedge``.
"""

import copy
import json
import math
import sys

import numpy as np

from .cli import DEFAULT_BINARY, run_headless
from .eng import eng_path as eng_path_for, load_eng, validate_eng
from .ghosts import (build_chain, plate_lateral_offset_mm,
                     _reverse_matrix)
from .qevolve import (QevolveError, element_matrix, q_from_wr,
                      waist_from_q, wr_from_q)
from .rez import elements, load_rez, param_value_si, set_param_value
from .solves import wavelength_nm

#: Default red wavelength (HeNe) in nm.
RED_NM = 632.8

#: Thermal lens focal length in the cold cavity (mm) -- effectively infinite.
COLD_F_MM = 1e9

#: Default injected HeNe waist radius (mm).
DEFAULT_W0_MM = 0.5

#: Sellmeier coefficients. Form A (three-term):
#:   n^2 = 1 + B1*lam^2/(lam^2-C1) + B2*lam^2/(lam^2-C2)
#:         + B3*lam^2/(lam^2-C3), lam in um, C in um^2.
#: Form B (two-term + IR term):
#:   n^2 = A + B/(lam^2-C) - D*lam^2.
SELLMEIER = {
    "fused_silica": {
        "form": "A", "source": "Malitson 1965, JOSA 55, 1205",
        "B": (0.6961663, 0.4079426, 0.8974794),
        "C": (0.0684043 ** 2, 0.1162414 ** 2, 9.896161 ** 2)},
    "BK7": {
        "form": "A", "source": "Schott data sheet",
        "B": (1.03961212, 0.231792344, 1.01046945),
        "C": (0.00600069867, 0.0200179144, 103.560653)},
    "Nd:YVO4:o": {
        "form": "B", "source": "YVO4 Sellmeier (Zelmon et al. / Castech)",
        "A": 3.77834, "B": 0.069736, "C": 0.04724, "D": 0.010813},
    "Nd:YVO4:e": {
        "form": "B", "source": "YVO4 Sellmeier (Zelmon et al. / Castech)",
        "A": 4.59944, "B": 0.110534, "C": 0.04813, "D": 0.012267},
    "LBO:x": {
        "form": "B", "source": "LBO Sellmeier (Kato 1991)",
        "A": 2.4542, "B": 0.01125, "C": 0.01135, "D": 0.01388},
    "LBO:y": {
        "form": "B", "source": "LBO Sellmeier (Kato 1991)",
        "A": 2.5390, "B": 0.01277, "C": 0.01189, "D": 0.01849},
    "LBO:z": {
        "form": "B", "source": "LBO Sellmeier (Kato 1991)",
        "A": 2.5865, "B": 0.01310, "C": 0.01223, "D": 0.01861},
}

#: Aliases for the material IDs.
MATERIAL_ALIASES = {
    "YVO4:o": "Nd:YVO4:o", "YVO4:e": "Nd:YVO4:e",
    "Nd:YVO4": "Nd:YVO4:e", "YVO4": "Nd:YVO4:e",
    "silica": "fused_silica", "SiO2": "fused_silica",
    "LBO": "LBO:x",
}


class RedlightError(ValueError):
    """Raised when the red-light comparison cannot be set up."""


# --- Sellmeier ---------------------------------------------------------------

def material_index(material, lambda_nm):
    """Refractive index of a library material at ``lambda_nm``.

    ``material`` is a library ID (``Nd:YVO4:e``, ``fused_silica``,
    ``BK7``, ``LBO:x`` ...) or an alias (``YVO4``, ``silica``).
    Raises :class:`RedlightError` for an unknown material.
    """
    key = MATERIAL_ALIASES.get(material, material)
    spec = SELLMEIER.get(key)
    if spec is None:
        raise RedlightError("unknown material %r (library: %s)"
                            % (material, ", ".join(sorted(SELLMEIER))))
    lam_um = float(lambda_nm) * 1e-3
    lam2 = lam_um * lam_um
    if spec["form"] == "A":
        n2 = 1.0
        for B, C in zip(spec["B"], spec["C"]):
            n2 += B * lam2 / (lam2 - C)
    else:
        n2 = spec["A"] + spec["B"] / (lam2 - spec["C"]) \
            - spec["D"] * lam2
    if n2 <= 0:
        raise RedlightError("Sellmeier gives n^2 <= 0 for %r at %r nm"
                            % (material, lambda_nm))
    return math.sqrt(n2)


def element_material(eng, label):
    """``(material_id, n_1064, n_633)`` for an element from the side-car.

    ``n_1064`` / ``n_633`` are the side-car overrides (``None`` when
    absent). Returns ``(None, None, None)`` when the element has no
    material entry.
    """
    materials = (eng or {}).get("materials")
    materials = materials if isinstance(materials, dict) else {}
    spec = materials.get(label)
    if not isinstance(spec, dict):
        return None, None, None
    material = spec.get("material")
    n_1064 = spec.get("n_1064")
    n_633 = spec.get("n_633")
    n_1064 = float(n_1064) if isinstance(n_1064, (int, float)) \
        and math.isfinite(float(n_1064)) and float(n_1064) > 0 else None
    n_633 = float(n_633) if isinstance(n_633, (int, float)) \
        and math.isfinite(float(n_633)) and float(n_633) > 0 else None
    return material, n_1064, n_633


# --- Cold cavity ---------------------------------------------------------------

def cold_schema(data, eng=None, red_nm=RED_NM):
    """Cold-cavity copy of a schema: thermal lens off, indices at red.

    Returns ``(cold_data, changes, warnings)`` where ``changes`` is
    a list of ``{"element", "param", "from", "to"}`` records. The
    thermal lens of every ``ElemThermoLens`` / ``ElemThermoMedium``
    is set to ``F = 1e9 mm``; every element carrying an ``n``
    parameter and a material entry (or an ``n_633`` override) gets
    its index replaced by ``n(red_nm)``; the schema wavelength is
    set to ``red_nm``. Elements without a material entry keep their
    .rez index and are listed in ``warnings``.
    """
    cold = copy.deepcopy(data)
    changes = []
    warnings = []
    lam_hot = wavelength_nm(data)
    # Wavelength.
    builtin = cold.get("builtin_params") or {}
    lam_param = builtin.get("lambda") if isinstance(builtin, dict) else None
    if isinstance(lam_param, dict):
        lam_param["value"] = float(red_nm)
        changes.append({"element": None, "param": "lambda",
                        "from": lam_hot, "to": float(red_nm)})
    # Thermal lens off + indices.
    for elem in elements(cold):
        if not isinstance(elem, dict) or elem.get("is_disabled"):
            continue
        label = elem.get("label")
        etype = elem.get("type")
        if etype in ("ElemThermoLens", "ElemThermoMedium"):
            F_old = param_value_si(cold, label, "F")
            if F_old is not None:
                set_param_value(cold, label, "F", COLD_F_MM, unit="mm")
                changes.append({"element": label, "param": "F",
                                "from": F_old * 1e3, "to": COLD_F_MM})
        if param_value_si(cold, label, "n") is None:
            continue
        # Air ranges (n == 1) need no red index: the air dispersion
        # between 1064 nm and 632.8 nm is ~1e-6, far below any other
        # term here.
        if abs(param_value_si(cold, label, "n") - 1.0) < 1e-9:
            continue
        material, n_1064, n_633 = element_material(eng, label)
        n_new = None
        source = None
        if n_633 is not None:
            n_new, source = n_633, "side-car override"
        elif material is not None:
            n_new = material_index(material, red_nm)
            source = "Sellmeier %s" % material
        if n_new is None:
            warnings.append("element %s: no material entry, index kept "
                            "at its .rez value (no red index available)"
                            % (label,))
            continue
        n_old = param_value_si(cold, label, "n")
        set_param_value(cold, label, "n", n_new)
        changes.append({"element": label, "param": "n",
                        "from": n_old, "to": n_new, "source": source})
    return cold, changes, warnings


# --- Injected-beam tracing -------------------------------------------------------

def _ray_step(x_mm, theta, M):
    """Ray ``(x_mm, theta)`` through a 2x2 ABCD matrix (SI).

    ``x`` is kept in mm and ``theta`` in radians; the matrix
    entries are SI (``B`` in m, ``C`` in 1/m), so the products are
    converted: ``B*1e3*theta`` (mm) and ``C*x*1e-3`` (rad).
    """
    A, B = M[0]
    C, D = M[1]
    return A * x_mm + B * 1e3 * theta, C * x_mm * 1e-3 + D * theta


def _propagate_q(q, M):
    A, B = M[0]
    C, D = M[1]
    return (A * q + B) / (C * q + D)


def _reverse_matrix(M):
    return np.array([[M[1, 1], M[0, 1]], [M[1, 0], M[0, 0]]], dtype=float)


def _element_wedge(eng, label):
    """``(wedge_mrad, wedge_plane)`` of an element from the side-car.

    The wedge is one physical angle (the angle between the two
    faces); the side-car stores it per face, so the first face
    that carries it wins. Returns ``(0.0, "T")`` when absent.
    """
    surfaces = (eng or {}).get("surfaces")
    surfaces = surfaces if isinstance(surfaces, dict) else {}
    spec = surfaces.get(label)
    spec = spec if isinstance(spec, dict) else {}
    faces = spec.get("faces")
    faces = faces if isinstance(faces, list) else []
    for face in faces:
        if not isinstance(face, dict):
            continue
        wedge = face.get("wedge_mrad")
        if isinstance(wedge, (int, float)) and math.isfinite(float(wedge)):
            plane = str(face.get("wedge_plane", "T")).upper()
            return float(wedge), plane if plane in ("T", "S") else "T"
    return 0.0, "T"


def trace_injected(data, chain, w0_mm, inject_label=None,
                   double_pass=False, x0_mm=0.0, theta0_mrad=0.0,
                   lambda_nm=RED_NM, eng=None):
    """Trace an externally injected collimated beam through the cavity.

    The beam starts at ``inject_label`` (default: the last element,
    the output mirror) with waist ``w0_mm`` and a flat wavefront,
    travelling toward the first element (single pass). With
    ``double_pass`` it reflects off the first element and returns.
    Returns ``{"path": [...], "injected": {...}}`` where each path
    entry is ``{"label", "s_mm", "plane", "w_T_mm", "w_S_mm",
    "x_T_mm", "x_S_mm"}`` with ``plane`` ``"exit"`` (the element's
    exit plane, facing the injection side) or ``"entrance"``.
    ``x`` / ``theta`` are the ray centre in the beam's own frame.
    """
    lam_m = float(lambda_nm) * 1e-9
    if w0_mm is None or w0_mm <= 0:
        raise RedlightError("injected waist must be positive, got %r"
                            % (w0_mm,))
    labels = [seg["label"] for seg in chain]
    if not labels:
        raise RedlightError("empty chain")
    inject = inject_label or labels[-1]
    if inject not in labels:
        raise RedlightError("injection element %r is not in the chain"
                            % (inject,))
    seg_by_label = {seg["label"]: seg for seg in chain}
    # q of a collimated beam: R = inf.
    q_T = q_from_wr(w0_mm * 1e-3, None, lam_m)
    q_S = q_from_wr(w0_mm * 1e-3, None, lam_m)
    x_T, x_S = float(x0_mm), 0.0
    th_T = th_S = float(theta0_mrad) * 1e-3
    path = []
    start = seg_by_label[inject]
    w_T, _ = wr_from_q(q_T, lam_m)
    w_S, _ = wr_from_q(q_S, lam_m)
    path.append({"label": inject, "s_mm": start["s_out_mm"],
                 "plane": "exit", "w_T_mm": w_T * 1e3,
                 "w_S_mm": w_S * 1e3, "x_T_mm": x_T, "x_S_mm": x_S})
    # Single pass: walk the chain backwards (decreasing s).
    order = labels[:labels.index(inject)][::-1]
    for label in order:
        seg = seg_by_label[label]
        M_T, M_S = seg["M_T"], seg["M_S"]
        if M_T is None:
            continue
        # Reverse-traversal matrices (beam travels opposite to the
        # element's forward orientation).
        M_T = _reverse_matrix(M_T)
        M_S = _reverse_matrix(M_S)
        # Beam at the element's exit plane (entry, going backwards).
        w_T, _ = wr_from_q(q_T, lam_m)
        w_S, _ = wr_from_q(q_S, lam_m)
        path.append({"label": label, "s_mm": seg["s_out_mm"],
                     "plane": "exit", "w_T_mm": w_T * 1e3,
                     "w_S_mm": w_S * 1e3, "x_T_mm": x_T, "x_S_mm": x_S})
        q_T = _propagate_q(q_T, M_T)
        q_S = _propagate_q(q_S, M_S)
        x_T, th_T = _ray_step(x_T, th_T, M_T)
        x_S, th_S = _ray_step(x_S, th_S, M_S)
        # Tilted-plate lateral displacement (backward: -Delta) and
        # wedge deflection of the transmitted beam ((n-1)*wedge).
        wedge_mrad, wedge_plane = _element_wedge(eng, label)
        if seg["type"] in (
                "ElemPlate", "ElemThermoLens", "ElemGrinLens",
                "ElemThermoMedium", "ElemGrinMedium", "ElemTiltedPlate",
                "ElemTiltedCrystal", "ElemBrewsterPlate",
                "ElemBrewsterCrystal", "ElemThickLens"):
            delta = plate_lateral_offset_mm(seg["L_mm"],
                                            seg["alpha_rad"], seg["n"])
            if wedge_plane == "T":
                x_T -= delta
                th_T -= (seg["n"] - 1.0) * wedge_mrad * 1e-3
            else:
                x_S -= delta
                th_S -= (seg["n"] - 1.0) * wedge_mrad * 1e-3
        w_T, _ = wr_from_q(q_T, lam_m)
        w_S, _ = wr_from_q(q_S, lam_m)
        path.append({"label": label, "s_mm": seg["s_in_mm"],
                     "plane": "entrance", "w_T_mm": w_T * 1e3,
                     "w_S_mm": w_S * 1e3, "x_T_mm": x_T, "x_S_mm": x_S})
    if not double_pass:
        return {"path": path,
                "injected": {"element": inject, "w0_mm": w0_mm,
                             "x0_mm": x0_mm, "theta0_mrad": theta0_mrad,
                             "double_pass": False}}
    # Turnaround at the first element: reflection.
    first = seg_by_label[labels[0]]
    if first["M_T"] is not None:
        C_T = float(first["M_T"][1, 0])
        C_S = float(first["M_S"][1, 0])
        q_T = (q_T.conjugate() * -1.0) / (C_T * (-q_T.conjugate()) + 1.0)
        q_S = (q_S.conjugate() * -1.0) / (C_S * (-q_S.conjugate()) + 1.0)
        th_T = th_T + C_T * x_T * 1e-3
        th_S = th_S + C_S * x_S * 1e-3
    # Return pass: walk the chain forwards.
    for label in labels[1:]:
        seg = seg_by_label[label]
        M_T, M_S = seg["M_T"], seg["M_S"]
        if M_T is None:
            continue
        w_T, _ = wr_from_q(q_T, lam_m)
        w_S, _ = wr_from_q(q_S, lam_m)
        path.append({"label": label, "s_mm": seg["s_in_mm"],
                     "plane": "entrance", "w_T_mm": w_T * 1e3,
                     "w_S_mm": w_S * 1e3, "x_T_mm": x_T, "x_S_mm": x_S})
        q_T = _propagate_q(q_T, M_T)
        q_S = _propagate_q(q_S, M_S)
        x_T, th_T = _ray_step(x_T, th_T, M_T)
        x_S, th_S = _ray_step(x_S, th_S, M_S)
        surf = None
        wedge_mrad, wedge_plane = _element_wedge(eng, label)
        if seg["type"] in (
                "ElemPlate", "ElemThermoLens", "ElemGrinLens",
                "ElemThermoMedium", "ElemGrinMedium", "ElemTiltedPlate",
                "ElemTiltedCrystal", "ElemBrewsterPlate",
                "ElemBrewsterCrystal", "ElemThickLens"):
            delta = plate_lateral_offset_mm(seg["L_mm"],
                                            seg["alpha_rad"], seg["n"])
            if wedge_plane == "T":
                x_T += delta
                th_T += (seg["n"] - 1.0) * wedge_mrad * 1e-3
            else:
                x_S += delta
                th_S += (seg["n"] - 1.0) * wedge_mrad * 1e-3
        w_T, _ = wr_from_q(q_T, lam_m)
        w_S, _ = wr_from_q(q_S, lam_m)
        path.append({"label": label, "s_mm": seg["s_out_mm"],
                     "plane": "exit", "w_T_mm": w_T * 1e3,
                     "w_S_mm": w_S * 1e3, "x_T_mm": x_T, "x_S_mm": x_S})
    return {"path": path,
            "injected": {"element": inject, "w0_mm": w0_mm,
                         "x0_mm": x0_mm, "theta0_mrad": theta0_mrad,
                         "double_pass": True}}


# --- Full comparison -----------------------------------------------------------

def redlight_report(data, eng=None, red_nm=RED_NM, w0_mm=DEFAULT_W0_MM,
                    inject_label=None, double_pass=False, x0_mm=0.0,
                    theta0_mrad=0.0, binary=DEFAULT_BINARY, timeout=None):
    """Red-light vs hot-IR comparison table.

    Returns::

        {"version", "red_nm", "hot_nm", "path": "cold_eigenmode" |
         "fallback", "cold": {"stable", "g_T", "g_S", "changes",
         "warnings"}, "table": [{"element", "s_mm", "w_1064_T_mm",
         "w_1064_S_mm", "x_1064_T_mm", "x_1064_S_mm", "w_633_T_mm",
         "w_633_S_mm", "x_633_T_mm", "x_633_S_mm", "dw_T_mm",
         "dw_S_mm", "dw_T_pct", "dw_S_pct", "dx_T_mm", "dx_S_mm"}],
         "injected": {...} | None, "warnings": [...]}

    ``path`` is ``"cold_eigenmode"`` when the cold cavity is stable
    (the red beam is the cold eigenmode) and ``"fallback"`` when it
    is unstable (the red beam is the externally injected HeNe).
    ``x_1064`` is the hot eigenmode axis (0 for an aligned cavity);
    ``x_633`` is the injected beam's centre (cold eigenmode: 0).
    """
    rez_data = data if isinstance(data, dict) else load_rez(data)
    eng_data = eng if isinstance(eng, dict) else load_eng(eng)
    warnings = validate_eng(eng_data)
    lam_hot = wavelength_nm(rez_data)
    hot = run_headless({"base_schema": rez_data, "mutations": []},
                       binary=binary, timeout=timeout)["results"][0]
    if not hot.get("ok"):
        raise RedlightError("hot-cavity evaluation failed: %s"
                            % hot.get("error"))
    if not hot.get("stable"):
        raise RedlightError("hot cavity is unstable (g_T=%r, g_S=%r); "
                            "there is no 1064 nm eigenmode to compare "
                            "against" % (hot.get("g_T"), hot.get("g_S")))
    chain_hot = build_chain(rez_data, hot, eng_data)
    cold_data, changes, cold_warnings = cold_schema(rez_data, eng_data,
                                                    red_nm)
    warnings.extend(cold_warnings)
    cold = run_headless({"base_schema": cold_data, "mutations": []},
                        binary=binary, timeout=timeout)["results"][0]
    cold_info = {"stable": bool(cold.get("stable")),
                 "g_T": cold.get("g_T"), "g_S": cold.get("g_S"),
                 "changes": changes, "warnings": cold_warnings,
                 "ok": bool(cold.get("ok")), "error": cold.get("error")}
    # Red beam at each element's exit plane.
    red_at = {}
    injected = None
    if cold.get("ok") and cold.get("stable"):
        path = "cold_eigenmode"
        chain_cold = build_chain(cold_data, cold, eng_data)
        for seg in chain_cold:
            red_at[seg["label"]] = {
                "w_T_mm": seg["w_T_mm"], "w_S_mm": seg["w_S_mm"],
                "x_T_mm": 0.0, "x_S_mm": 0.0}
    else:
        path = "fallback"
        chain_cold = build_chain(cold_data, {"beam": []}, eng_data)
        trace = trace_injected(cold_data, chain_cold, w0_mm,
                               inject_label=inject_label,
                               double_pass=double_pass, x0_mm=x0_mm,
                               theta0_mrad=theta0_mrad,
                               lambda_nm=red_nm, eng=eng_data)
        injected = trace["injected"]
        for entry in trace["path"]:
            if entry["plane"] != "exit":
                continue
            red_at[entry["label"]] = {
                "w_T_mm": entry["w_T_mm"], "w_S_mm": entry["w_S_mm"],
                "x_T_mm": entry["x_T_mm"], "x_S_mm": entry["x_S_mm"]}
    table = []
    for seg in chain_hot:
        label = seg["label"]
        red = red_at.get(label)
        if red is None or red["w_T_mm"] is None:
            table.append({"element": label, "s_mm": seg["s_out_mm"],
                          "w_1064_T_mm": seg["w_T_mm"],
                          "w_1064_S_mm": seg["w_S_mm"],
                          "x_1064_T_mm": 0.0, "x_1064_S_mm": 0.0,
                          "w_633_T_mm": None, "w_633_S_mm": None,
                          "x_633_T_mm": None, "x_633_S_mm": None,
                          "dw_T_mm": None, "dw_S_mm": None,
                          "dw_T_pct": None, "dw_S_pct": None,
                          "dx_T_mm": None, "dx_S_mm": None,
                          "note": "no red beam value at this aperture"})
            continue
        dw_T = red["w_T_mm"] - seg["w_T_mm"]
        dw_S = red["w_S_mm"] - seg["w_S_mm"]
        table.append({
            "element": label, "s_mm": seg["s_out_mm"],
            "w_1064_T_mm": seg["w_T_mm"], "w_1064_S_mm": seg["w_S_mm"],
            "x_1064_T_mm": 0.0, "x_1064_S_mm": 0.0,
            "w_633_T_mm": red["w_T_mm"], "w_633_S_mm": red["w_S_mm"],
            "x_633_T_mm": red["x_T_mm"], "x_633_S_mm": red["x_S_mm"],
            "dw_T_mm": dw_T, "dw_S_mm": dw_S,
            "dw_T_pct": 100.0 * dw_T / seg["w_T_mm"],
            "dw_S_pct": 100.0 * dw_S / seg["w_S_mm"],
            "dx_T_mm": red["x_T_mm"] - 0.0,
            "dx_S_mm": red["x_S_mm"] - 0.0})
    return {"version": 1, "red_nm": float(red_nm), "hot_nm": lam_hot,
            "path": path, "cold": cold_info, "table": table,
            "injected": injected, "warnings": warnings}


def main(argv=None):
    """CLI entry: ``run_redlight.py <file.rez> [side-car]``."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Compare the 632.8 nm red alignment beam with the "
                    "1064 nm hot cavity mode.")
    parser.add_argument("rez_path", help=".rez file")
    parser.add_argument("eng_path", nargs="?",
                        help="side-car file (default: <file>.rez.eng.json)")
    parser.add_argument("--red-nm", type=float, default=RED_NM,
                        help="red wavelength in nm (default 632.8)")
    parser.add_argument("--w0", type=float, default=DEFAULT_W0_MM,
                        help="injected HeNe waist radius in mm "
                             "(default 0.5)")
    parser.add_argument("--double-pass", action="store_true",
                        help="trace the injected beam back as well")
    parser.add_argument("--binary", default=DEFAULT_BINARY,
                        help="path to the rezonator binary")
    args = parser.parse_args(argv)
    eng_path = args.eng_path or eng_path_for(args.rez_path)
    try:
        report = redlight_report(args.rez_path, eng_path, args.red_nm,
                                 args.w0, double_pass=args.double_pass,
                                 binary=args.binary)
    except (OSError, ValueError, RedlightError) as e:
        print("run_redlight: %s" % e, file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
