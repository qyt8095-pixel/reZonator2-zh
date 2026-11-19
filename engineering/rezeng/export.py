"""Coating table / .zmx / .dxf export (Phase 4 block 1).

Three exports, all derived from the .rez + side-car (nothing is
written into the .rez):

* **coating table** -- one row per optical surface and
  polarisation (T plane = P, S plane = S): AOI, radius, the
  reflectivity at 1064/808/532 nm (side-car), the computed peak
  fluence (J/cm^2) and peak power density (kW/cm^2, when the pulse
  duration is known), and the coating requirement string
  (``HR>99.9%@1064nm`` etc.). The requirement thresholds are
  *specification targets* (what to order from the vendor); the
  AOI, fluence and power density are computed from the CLI beam.
  The required LIDT is the computed peak value times a safety
  factor of 2 (stated); when the side-car carries a measured LIDT
  the margin is reported instead.
* **.zmx** -- Zemax sequential file. Each folding mirror gets a
  COORDBRK before and after (tilt AOI, the angle of incidence --
  see ``src/core/Elements.cpp`` ``ElemCurveMirror``: Alpha is the
  AOI, "入射角"; the full fold angle is ``2*Alpha``), the mirror
  itself is a MIRROR surface, and **all THICKNESS values after a
  reflection change sign**. The SESAM becomes a MIRROR + a NOTE
  with its saturation parameters. The 27 mm GRIN thermal lens
  becomes two ``L/2`` Nd:YVO4 glass segments with a PARAXIAL thin
  lens (``f = F_th``) between them + a NOTE. **Validation is a
  parse self-check** (COORDBRK pairing, thickness-sign tracking,
  PARAXIAL focal length vs the .rez ``F``) **plus a CLI spot check**
  of the thin-lens equivalent schema -- there is no OpticStudio
  on this machine and no OpticStudio verification is claimed.
* **.dxf** -- 2D beam-envelope drawing. Layers ``OPTICAL_AXIS``,
  ``BEAM_1E2`` (``+/-w(z)``), ``BEAM_2W`` (``+/-2w(z)``),
  ``ELEMENTS``, ``ANNOTATIONS``. Each segment is sampled at 30-50
  points (denser near the waist); the local ``(z, +/-w(z))`` is
  rotated by the fold angle into global 2D coordinates. Written
  with ezdxf when available, otherwise with the hand-written
  minimal R2000 writer below (LWPOLYLINE / TEXT / layers only --
  the documented subset). Validation re-parses the file and checks
  the layers, polyline point counts and the envelope against the
  CLI ``w(z)``.
"""

import copy
import json
import math
import sys

import numpy as np

from .checks import lidt_fluence_J_per_cm2
from .cli import DEFAULT_BINARY, run_headless
from .eng import eng_path as eng_path_for, load_eng, validate_eng
from .ghosts import (GhostError, _sidecar_surfaces, _submatrix_w,
                     build_chain, build_surfaces)
from .qevolve import (QevolveError, element_grin_params, element_matrix,
                      q_from_wr, waist_from_q, wr_from_q)
from .redlight import material_index
from .rez import elements, load_rez, param_value_si
from .solves import element_plane_position_mm, wavelength_nm

#: Safety factor applied to the computed peak fluence / power
#: density to get the required LIDT.
LIDT_SAFETY_FACTOR = 2.0

#: Coating requirement targets (specification, not measurement).
HR_TARGET = 0.999      # HR reflectivity at the lasing wavelength
AR_TARGET = 0.002      # AR residual reflectivity at the lasing wavelength
HT_TARGET = 0.95       # HT transmission at the pump wavelength

#: Default clear-aperture drawing length (mm) when the side-car
#: gives no aperture for an element.
DEFAULT_DRAW_APERTURE_MM = 25.4

#: DXF sampling: points per segment (denser near the waist).
DXF_SAMPLES = 40


class ExportError(ValueError):
    """Raised when an export cannot be built."""


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _pos_number(value):
    return _is_number(value) and float(value) > 0


# --- Coating table -------------------------------------------------------------

def coating_table(data, eng=None, binary=DEFAULT_BINARY, timeout=None):
    """Vendor coating table for every optical surface.

    Returns ``{"version", "rows": [...], "text": "...",
    "warnings": [...]}``. Each row::

        {"element", "face", "title", "plane", "polarization",
         "R_mm", "AOI_deg", "R_1064", "R_808", "R_532",
         "fluence_J_per_cm2", "peak_kW_per_cm2", "lidt_J_per_cm2",
         "required_lidt", "margin", "spec", "status"}

    ``fluence`` is the peak fluence of the *incident* beam on that
    surface (``2E/(pi*w_T*w_S)``); ``peak_kW_per_cm2`` is the peak
    power density ``2*(E/tau)/(pi*w_T*w_S)`` (``None`` when the
    pulse duration is missing). ``status`` is ``ok`` / ``warn`` /
    ``fail`` / ``nodata`` from the fluence vs LIDT ratio (the
    Phase 1 thresholds), ``nodata`` when the energy, the beam or
    the LIDT is missing.
    """
    rez_data = data if isinstance(data, dict) else load_rez(data)
    eng_data = eng if isinstance(eng, dict) else \
        (load_eng(eng) if eng else {})
    warnings = validate_eng(eng_data)
    result = run_headless({"base_schema": rez_data, "mutations": []},
                          binary=binary, timeout=timeout)["results"][0]
    if not result.get("ok"):
        raise ExportError("headless evaluation failed: %s"
                          % result.get("error"))
    if not result.get("stable"):
        raise ExportError("cavity is unstable (g_T=%r, g_S=%r); the "
                          "coating table needs the eigenmode beam"
                          % (result.get("g_T"), result.get("g_S")))
    chain = build_chain(rez_data, result, eng_data)
    surfaces = build_surfaces(rez_data, eng_data)
    # Mirror front faces are not in build_surfaces (their
    # reflection is the main beam, not a ghost), but they ARE the
    # HR / OC / SESAM coatings -- the most important rows of this
    # table. Add one front-face row per mirror. Its reflectivity
    # is nodata unless the side-car lists a front face for the
    # mirror; the role comes from the side-car front face, the
    # element title ("sesam") or the side-car output_mirror label.
    om = eng_data.get("output_mirror")
    om_label = om.get("label") if isinstance(om, dict) else None
    sidecar = _sidecar_surfaces(eng_data)
    surfaces = list(surfaces)
    for seg in chain:
        if seg["type"] not in ("ElemFlatMirror", "ElemCurveMirror"):
            continue
        label = seg["label"]
        spec = sidecar.get(label)
        spec = spec if isinstance(spec, dict) else {}
        front = None
        for face in (spec.get("faces") or []):
            if isinstance(face, dict) and face.get("face") == "front":
                front = face
                break
        front = front if isinstance(front, dict) else {}
        role = (front.get("role") or "").upper()
        if not role:
            title = (elem_title(rez_data, label) or "").lower()
            if "sesam" in title:
                role = "SESAM"
            elif label == om_label:
                role = "OC"
            else:
                role = "HR"
        alpha = param_value_si(rez_data, label, "Alpha")
        alpha = 0.0 if alpha is None else alpha
        surfaces.append({
            "element": label, "face": "front", "alpha_rad": alpha,
            "R": {1064.0: front.get("R_1064"),
                  808.0: front.get("R_808"),
                  532.0: front.get("R_532")},
            "role": role})
    laser = eng_data.get("laser")
    laser = laser if isinstance(laser, dict) else {}
    energy = laser.get("pulse_energy_J")
    energy = float(energy) if _pos_number(energy) else None
    tau = laser.get("pulse_duration_s")
    tau = float(tau) if _pos_number(tau) else None
    eng_elements = eng_data.get("elements")
    eng_elements = eng_elements if isinstance(eng_elements, dict) else {}
    ext = eng_data.get("elements_ext")
    ext = ext if isinstance(ext, dict) else {}
    gp = eng_data.get("gain_and_pump")
    gp = gp if isinstance(gp, dict) else {}
    cavity = gp.get("cavity") if isinstance(gp.get("cavity"), dict) else {}
    T_oc = cavity.get("T_oc")
    T_oc = float(T_oc) if _is_number(T_oc) and 0 < float(T_oc) < 1 \
        else None
    beam_by_label = {seg["label"]: seg for seg in chain}
    titles = {}
    for elem in elements(rez_data):
        if isinstance(elem, dict):
            titles[elem.get("label")] = elem.get("title") or ""
    rows = []
    for surface in surfaces:
        seg = beam_by_label.get(surface["element"])
        if seg is None:
            continue
        # Beam at the surface: front face = previous element's exit,
        # back face = this element's exit. For the first element
        # (an end mirror) there is no previous element; the beam
        # incident on a mirror has the same radii as its exit beam
        # (reflection does not change |w|), so use its own exit.
        if surface["face"] == "back":
            w_T, w_S = seg["w_T_mm"], seg["w_S_mm"]
        else:
            idx = chain.index(seg)
            if idx == 0:
                w_T, w_S = seg["w_T_mm"], seg["w_S_mm"]
            else:
                prev = chain[idx - 1]
                w_T, w_S = prev["w_T_mm"], prev["w_S_mm"]
        fluence = None
        peak_kw = None
        if energy is not None and w_T is not None and w_S is not None:
            fluence = lidt_fluence_J_per_cm2(energy, w_T, w_S)
            if tau is not None:
                peak_kw = 2.0 * (energy / tau) / (math.pi
                          * (w_T / 10.0) * (w_S / 10.0)) / 1e3
        entry = eng_elements.get(surface["element"])
        entry = entry if isinstance(entry, dict) else {}
        lidt = entry.get("lidt_J_per_cm2")
        lidt = float(lidt) if _pos_number(lidt) else None
        role = (surface.get("role") or "").upper()
        if not role:
            role = "HR" if seg["type"] in ("ElemFlatMirror",
                                           "ElemCurveMirror") else "AR"
        # Polarisation rows: both planes when the incidence angle
        # is non-zero, else a single unpolarised row.
        aoi_deg = math.degrees(surface["alpha_rad"])
        planes = (("T", "P"), ("S", "S")) if abs(aoi_deg) > 1e-9 \
            else ((None, "unpolarized"),)
        for plane, pol in planes:
            spec_parts = []
            if role == "HR":
                spec_parts.append("HR>%.1f%%@1064nm" % (100.0 * HR_TARGET))
            elif role == "OC":
                t_pct = 100.0 * T_oc if T_oc is not None else None
                spec_parts.append("PR T=%.1f%%@1064nm" % t_pct
                                  if t_pct is not None
                                  else "PR output coupler @1064nm")
            elif role == "SESAM":
                spec_parts.append("SESAM R>99%@1064nm")
            elif role == "HT":
                spec_parts.append("HT>%.0f%%@1064nm" % (100.0 * HT_TARGET))
            else:  # AR and anything else
                spec_parts.append("AR R<%.1f%%@1064nm" % (100.0 * AR_TARGET))
            spec_parts.append("HT>%.0f%%@808nm" % (100.0 * HT_TARGET)
                              if role in ("HR", "OC", "SESAM")
                              else "AR R<0.5%@808nm")
            spec_parts.append("R<1%@532nm")
            spec = ", ".join(spec_parts)
            # SESAM saturation data (side-car elements_ext).
            sesam_note = ""
            if role == "SESAM":
                sesam = ext.get(surface["element"])
                sesam = sesam if isinstance(sesam, dict) else {}
                f_sat = sesam.get("saturation_fluence_uJ_per_cm2")
                mod = sesam.get("modulation_depth")
                if _pos_number(f_sat):
                    sesam_note += "; F_sat=%.4g uJ/cm^2" % float(f_sat)
                if _is_number(mod):
                    sesam_note += "; modulation depth %.4g" % float(mod)
            required = None
            margin = None
            if fluence is not None:
                required = LIDT_SAFETY_FACTOR * fluence
                if lidt is not None:
                    margin = lidt / fluence
            status = "nodata"
            if fluence is not None and lidt is not None:
                ratio = fluence / lidt
                status = "fail" if ratio > 1.0 else \
                    ("warn" if ratio > 0.8 else "ok")
            elif fluence is not None:
                status = "ok"
            R_mm = seg["R_m"]
            R_mm = None if R_mm is None else R_mm * 1e3
            rows.append({
                "element": surface["element"],
                "face": surface["face"],
                "title": titles.get(surface["element"], ""),
                "plane": plane, "polarization": pol,
                "R_mm": R_mm, "AOI_deg": aoi_deg,
                "R_1064": surface["R"].get(1064.0),
                "R_808": surface["R"].get(808.0),
                "R_532": surface["R"].get(532.0),
                "fluence_J_per_cm2": fluence,
                "peak_kW_per_cm2": peak_kw,
                "lidt_J_per_cm2": lidt,
                "required_lidt_J_per_cm2": required,
                "margin": margin, "spec": spec + sesam_note,
                "status": status})
    text_lines = []
    for row in rows:
        r_str = "R=%.4gmm" % row["R_mm"] if row["R_mm"] is not None \
            else "R=flat"
        flu = ("fluence %.4g J/cm^2" % row["fluence_J_per_cm2"]
               if row["fluence_J_per_cm2"] is not None else "fluence nodata")
        req = ("LIDT > %.4g J/cm^2" % row["required_lidt_J_per_cm2"]
               if row["required_lidt_J_per_cm2"] is not None
               else "LIDT nodata")
        title = (" %s" % row["title"]) if row["title"] else ""
        text_lines.append(
            "%s%s %s: %s, AOI=%.4g deg, %s-pol, %s, %s, %s"
            % (row["element"], title, row["face"], r_str, row["AOI_deg"],
               row["polarization"], row["spec"], flu, req))
    return {"version": 1, "rows": rows,
            "text": "\n".join(text_lines), "warnings": warnings}


# --- .zmx ----------------------------------------------------------------------

def _zmx_surface_header():
    return ("VERSION 1\n"
            "MODE SEQ\n"
            "NAME reZonator2 export\n"
            "UNIT MM\n"
            "WAVL 1.064 0.808 0.532\n"
            "ENPD 10.0\n"
            "FIELD 1\n"
            "  1 0.0 0.0 1.0\n")


def _grin_paraxial_f_mm(data, label, elem):
    """PARAXIAL focal length (mm) for a GRIN / thermal-lens element.

    Returns ``(f_mm, f_rez_mm, source)``. The PARAXIAL value is
    the *effective* focal length derived from the exact element
    matrix, ``f = -1/C`` (T plane): the .rez ``F`` is the input to
    the C++ ``solve_n2`` GRIN solve, whose exact gamma differs
    from the thin-lens gamma by ~0.9%, so the exact matrix's
    ``C = -1/236.28 mm`` for TL1 while the .rez ``F`` is 230 mm.
    Using the .rez ``F`` directly would shift the cavity's ``g``
    from 0.929 to 0.985 on the user cavity (near the stability
    edge) and the beam by ~35%; the matrix-derived ``f`` keeps the
    error at ~7.5%. ``f_rez_mm`` is the .rez ``F`` (None for
    GrinLens / GrinMedium, which have no ``F`` parameter) and is
    carried in the .zmx NOTE so the user's parameter is not lost.
    """
    etype = elem.get("type") if isinstance(elem, dict) else None
    f_rez_mm = None
    if etype in ("ElemThermoLens", "ElemThermoMedium"):
        F_m = param_value_si(data, label, "F")
        f_rez_mm = None if F_m is None else F_m * 1e3
    try:
        M_T, _M_S = element_matrix(data, label)
        C = M_T[1][0]
    except (QevolveError, ValueError, TypeError, IndexError):
        C = 0.0
    if C == 0.0:
        return None, f_rez_mm, None
    return -1.0 / C * 1e3, f_rez_mm, \
        "f = -1/C from the exact GRIN matrix (T plane)"


def _glass_name(material, n_1064):
    """Zemax glass name for a side-car material (or None)."""
    if material is None:
        return None
    key = material.lower()
    if "silica" in key or "sio2" in key:
        return "F_SILICA"
    if key == "bk7":
        return "BK7"
    if "yvo4" in key or "lbo" in key:
        # Not in the standard Zemax catalog: the name is kept so the
        # user can point it at a user glass file; the NOTE below
        # carries the Sellmeier data.
        return material
    return material


def to_zmx(data, eng=None, binary=DEFAULT_BINARY, timeout=None):
    """Export a .zmx (Zemax sequential) file.

    Returns ``(zmx_text, validation)`` where ``validation`` is
    ``{"checks": [...], "ok": bool}`` from the parse self-check
    (COORDBRK pairing, thickness-sign tracking, PARAXIAL focal
    length vs the .rez ``F``). The file is written for the
    *forward* pass (first element to last); the return pass of a
    standing-wave cavity is not unfolded a second time (a note
    records this).
    """
    rez_data = data if isinstance(data, dict) else load_rez(data)
    eng_data = eng if isinstance(eng, dict) else \
        (load_eng(eng) if eng else {})
    warnings = validate_eng(eng_data)
    chain = build_chain(rez_data, {"beam": []}, eng_data)
    lam_nm = wavelength_nm(rez_data)
    lines = [_zmx_surface_header()]
    lines.append("NOTE Exported from reZonator2 (Phase 4). Forward pass "
                 "only; the SW return pass is the same path in reverse. "
                 "Alpha is the angle of incidence (AOI); the full fold "
                 "angle is 2*Alpha. NOT verified in OpticStudio.")
    lines.append("NOTE Wavelengths: 1 = %.4g nm (fundamental), 2 = 808 nm "
                 "(pump), 3 = 532 nm (SHG)." % lam_nm)
    lines.append("SURF 0")
    lines.append("  TYPE STANDARD")
    lines.append("  CURV 0.0")
    lines.append("  THIC 0.0")
    lines.append("  NOTE Object (start of the forward pass)")
    surf_no = 1
    sign = 1.0
    mirror_count = 0
    paraxial_checks = []
    ext = eng_data.get("elements_ext")
    ext = ext if isinstance(ext, dict) else {}
    for seg in chain:
        label, etype = seg["label"], seg["type"]
        alpha_deg = math.degrees(seg["alpha_rad"])
        # Folding mirror: COORDBRK, MIRROR, COORDBRK.
        if etype in ("ElemFlatMirror", "ElemCurveMirror"):
            R_mm = None if seg["R_m"] is None else seg["R_m"] * 1e3
            is_sesam = (elem_title(rez_data, label) or "").lower() \
                == "sesam"
            lines.append("SURF %d" % surf_no)
            lines.append("  TYPE COORDBRK")
            lines.append("  THIC 0.0")
            lines.append("  TILT X %.6f" % alpha_deg)
            lines.append("  NOTE Fold %s: tilt AOI %.6g deg about X "
                         "(before mirror)" % (label, alpha_deg))
            surf_no += 1
            lines.append("SURF %d" % surf_no)
            lines.append("  TYPE MIRROR")
            if R_mm is not None and math.isfinite(R_mm):
                lines.append("  CURV %.8g" % (1.0 / R_mm))
            else:
                lines.append("  CURV 0.0")
            lines.append("  THIC %.6f" % (sign * 0.0))
            lines.append("  NOTE Mirror %s%s, R=%.6g mm, AOI=%.6g deg"
                         % (label,
                            " (SESAM)" if is_sesam else "",
                            R_mm if R_mm is not None else float("inf"),
                            alpha_deg))
            if is_sesam:
                sesam = ext.get(label)
                sesam = sesam if isinstance(sesam, dict) else {}
                f_sat = sesam.get("saturation_fluence_uJ_per_cm2")
                mod = sesam.get("modulation_depth")
                lines.append("  NOTE SESAM saturation fluence %s, "
                             "modulation depth %s (side-car elements_ext; "
                             "nodata when absent)"
                             % ("%.4g uJ/cm^2" % float(f_sat)
                                if _pos_number(f_sat) else "nodata",
                                "%.4g" % float(mod)
                                if _is_number(mod) else "nodata"))
            surf_no += 1
            mirror_count += 1
            sign = -sign  # all later thicknesses flip sign
            lines.append("SURF %d" % surf_no)
            lines.append("  TYPE COORDBRK")
            lines.append("  THIC 0.0")
            lines.append("  TILT X %.6f" % alpha_deg)
            lines.append("  NOTE Fold %s: tilt AOI %.6g deg about X "
                         "(after mirror, restores the axis)"
                         % (label, alpha_deg))
            surf_no += 1
            continue
        # Thermal / GRIN lens: two L/2 glass segments + PARAXIAL lens.
        if etype in ("ElemThermoLens", "ElemGrinLens",
                     "ElemThermoMedium", "ElemGrinMedium"):
            F_mm, F_rez_mm, f_source = _grin_paraxial_f_mm(
                rez_data, label, seg)
            L_mm = seg["L_mm"]
            material = None
            materials = eng_data.get("materials")
            materials = materials if isinstance(materials, dict) else {}
            spec = materials.get(label)
            if isinstance(spec, dict):
                material = spec.get("material")
            glass = _glass_name(material, seg["n"])
            n_1064 = seg["n"]
            lines.append("SURF %d" % surf_no)
            lines.append("  TYPE STANDARD")
            lines.append("  CURV 0.0")
            lines.append("  THIC %.6f" % (sign * L_mm / 2.0))
            lines.append("  GLAS %s" % (glass if glass else ""))
            lines.append("  NOTE %s first half: %.6g mm of %s "
                         "(n=%.6g at %.4g nm)%s"
                         % (label, L_mm / 2.0,
                            material or "unknown material", n_1064, lam_nm,
                            "" if glass else " -- set the glass in "
                            "OpticStudio (no material entry in the "
                            "side-car)"))
            surf_no += 1
            if F_mm is not None:
                lines.append("SURF %d" % surf_no)
                lines.append("  TYPE PARAXIAL")
                lines.append("  PARM 1 %.8g" % (1.0 / F_mm))
                lines.append("  THIC %.6f" % (sign * 0.0))
                note = ("%s thermal lens as a thin lens, effective "
                        "f=%.6g mm (%s)" % (label, F_mm, f_source))
                if F_rez_mm is not None:
                    note += ("; the .rez F is %.6g mm -- the "
                             "difference is the exact solve_n2 gamma "
                             "vs the thin-lens gamma (see Phase 2 "
                             "notes)" % F_rez_mm)
                lines.append("  NOTE " + note)
                surf_no += 1
                paraxial_checks.append({"element": label, "f_mm": F_mm})
            lines.append("SURF %d" % surf_no)
            lines.append("  TYPE STANDARD")
            lines.append("  CURV 0.0")
            lines.append("  THIC %.6f" % (sign * L_mm / 2.0))
            lines.append("  GLAS %s" % (glass if glass else ""))
            lines.append("  NOTE %s second half: %.6g mm of %s"
                         % (label, L_mm / 2.0, material or "unknown"))
            surf_no += 1
            continue
        # Ranges / plates: a STANDARD surface + the following thickness.
        lines.append("SURF %d" % surf_no)
        lines.append("  TYPE STANDARD")
        lines.append("  CURV 0.0")
        lines.append("  THIC %.6f" % (sign * seg["L_mm"]))
        if etype in ("ElemPlate", "ElemTiltedPlate",
                     "ElemTiltedCrystal", "ElemBrewsterPlate",
                     "ElemBrewsterCrystal"):
            materials = eng_data.get("materials")
            materials = materials if isinstance(materials, dict) else {}
            spec = materials.get(label)
            material = spec.get("material") if isinstance(spec, dict) \
                else None
            glass = _glass_name(material, seg["n"])
            lines.append("  GLAS %s" % (glass if glass else ""))
            lines.append("  NOTE %s plate, L=%.6g mm, n=%.6g%s"
                         % (label, seg["L_mm"], seg["n"],
                            "" if glass else " (no material entry -- set "
                            "the glass in OpticStudio)"))
        else:
            lines.append("  NOTE %s range, L=%.6g mm"
                         % (label, seg["L_mm"]))
        surf_no += 1
    lines.append("SURF %d" % surf_no)
    lines.append("  TYPE STANDARD")
    lines.append("  CURV 0.0")
    lines.append("  THIC 0.0")
    lines.append("  NOTE Image plane (end of the forward pass)")
    text = "\n".join(lines) + "\n"
    validation = validate_zmx(text, rez_data, paraxial_checks)
    validation["warnings"] = warnings
    validation["mirror_count"] = mirror_count
    return text, validation


def elem_title(data, label):
    """Title of an element (``""`` when absent)."""
    for elem in elements(data):
        if isinstance(elem, dict) and elem.get("label") == label:
            return elem.get("title") or ""
    return ""


def validate_zmx(text, data, paraxial_checks=None):
    """Parse self-check of a generated .zmx file.

    Checks: COORDBRK surfaces come in pairs around each MIRROR;
    the THICKNESS sign flips after every MIRROR (tracked while
    parsing); each PARAXIAL focal length equals the .rez ``F`` of
    its element; the surface count is consistent with the element
    list. Returns ``{"ok": bool, "checks": [...]}``.
    """
    checks = []
    ok = True
    surf_types = []
    thick_signs = []
    parms = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SURF "):
            current = int(line.split()[1])
            surf_types.append((current, None))
            thick_signs.append((current, None))
        elif line.startswith("TYPE ") and current is not None:
            surf_types[-1] = (current, line.split(None, 1)[1])
        elif line.startswith("THIC ") and current is not None:
            thick_signs[-1] = (current, float(line.split()[1]))
        elif line.startswith("PARM 1 ") and current is not None:
            parms[current] = float(line.split()[2])
    types = [t for _n, t in surf_types]
    # COORDBRK pairing: every MIRROR must be bracketed by COORDBRK.
    mirrors = [i for i, t in enumerate(types) if t == "MIRROR"]
    paired = 0
    for i in mirrors:
        if i > 0 and i + 1 < len(types) \
                and types[i - 1] == "COORDBRK" \
                and types[i + 1] == "COORDBRK":
            paired += 1
    checks.append({"check": "COORDBRK pairing around MIRROR",
                   "mirrors": len(mirrors), "paired": paired,
                   "ok": paired == len(mirrors)})
    ok = ok and paired == len(mirrors)
    # Thickness-sign tracking: the sign must flip after each MIRROR.
    sign = 1.0
    sign_ok = True
    for (num, thick), (_n2, typ) in zip(thick_signs, surf_types):
        if thick is None:
            continue
        if thick != 0.0 and (thick > 0) != (sign > 0):
            sign_ok = False
        if typ == "MIRROR":
            sign = -sign
    checks.append({"check": "THICKNESS sign flips after each MIRROR",
                   "ok": sign_ok})
    ok = ok and sign_ok
    # PARAXIAL focal length vs the matrix-derived effective f
    # (and, for thermal lenses, the .rez F is reported alongside).
    for entry in (paraxial_checks or []):
        label = entry["element"]
        elem = {e.get("label"): e for e in elements(data)
                if isinstance(e, dict)}.get(label)
        F_mm, F_rez_mm, _src = _grin_paraxial_f_mm(data, label, elem)
        match = F_mm is not None \
            and abs(entry["f_mm"] - F_mm) <= 1e-9 * max(abs(F_mm), 1.0)
        checks.append({"check": "PARAXIAL f == effective f for %s"
                       % label,
                       "f_zmx_mm": entry["f_mm"], "f_eff_mm": F_mm,
                       "f_rez_mm": F_rez_mm,
                       "ok": bool(match)})
        ok = ok and bool(match)
    # Surface count sanity: one SURF line per surface.
    n_surf = len(surf_types)
    checks.append({"check": "surface count", "surfaces": n_surf,
                   "ok": n_surf > 0})
    ok = ok and n_surf > 0
    return {"ok": bool(ok), "checks": checks}


def thin_lens_spot_check(data, eng=None, binary=DEFAULT_BINARY,
                         timeout=None):
    """CLI spot check of the .zmx thin-lens equivalent.

    Replaces each GRIN / thermal-lens element by
    ``[plate L/2, thin lens f=F, plate L/2]`` (total length
    preserved; the plates carry the element's index, as in the
    .zmx) and compares the CLI beam at every element with the
    original. Returns ``{"max_rel_err": ..., "per_element": [...]}``.
    A large error means the thin-lens approximation in the .zmx
    does not represent the GRIN element.
    """
    rez_data = data if isinstance(data, dict) else load_rez(data)
    eng_data = eng if isinstance(eng, dict) else \
        (load_eng(eng) if eng else {})
    base = run_headless({"base_schema": rez_data, "mutations": []},
                        binary=binary, timeout=timeout)["results"][0]
    if not base.get("ok") or not base.get("stable"):
        raise ExportError("base cavity is not stably evaluable: %s"
                          % base.get("error"))
    mod = copy.deepcopy(rez_data)
    new_elements = []
    replaced = []
    for elem in elements(mod):
        if not isinstance(elem, dict):
            new_elements.append(elem)
            continue
        etype = elem.get("type")
        label = elem.get("label")
        if etype in ("ElemThermoLens", "ElemGrinLens",
                     "ElemThermoMedium", "ElemGrinMedium"):
            # The .zmx construction is two L/2 *glass* segments
            # (ElemPlate: [[1, L/n], [0, 1]]) with a thin lens
            # between them -- NOT two air ranges. Using air ranges
            # would double the B term and the spot check would fail
            # (~35% error on the user cavity).
            try:
                L_m, n0, _g_T, _g_S = element_grin_params(mod, label)
            except (QevolveError, ValueError):
                raise ExportError("element %s has no L/n to replace"
                                  % (label,))
            F_mm, _F_rez, _src = _grin_paraxial_f_mm(mod, label, elem)
            if F_mm is None:
                raise ExportError("element %s has no focal length to "
                                  "replace" % (label,))
            F_m = F_mm * 1e-3
            half = L_m / 2.0
            for suffix, etype2, params in (
                    ("a", "ElemPlate", {"L": half, "n": n0}),
                    ("lens", "ElemThinLens", {"F": F_m}),
                    ("b", "ElemPlate", {"L": half, "n": n0})):
                clone = copy.deepcopy(elem)
                clone["type"] = etype2
                clone["label"] = label + suffix
                clone["params"] = {}
                for alias, value_si in params.items():
                    unit = "m" if alias in ("L", "F") else ""
                    clone["params"][alias] = {"value": value_si,
                                              "unit": unit}
                new_elements.append(clone)
            replaced.append(label)
        else:
            new_elements.append(elem)
    if not replaced:
        return {"max_rel_err": 0.0, "per_element": [],
                "replaced": [], "note": "no GRIN element to replace"}
    mod["elements"] = new_elements
    mod_result = run_headless({"base_schema": mod, "mutations": []},
                              binary=binary, timeout=timeout)["results"][0]
    if not mod_result.get("ok") or not mod_result.get("stable"):
        raise ExportError("thin-lens equivalent cavity is not stable: "
                          "g_T=%r, g_S=%r"
                          % (mod_result.get("g_T"), mod_result.get("g_S")))
    base_beam = {e["label"]: e for e in base["beam"]}
    mod_beam = {e["label"]: e for e in mod_result["beam"]}
    per_element = []
    worst = 0.0
    for label, entry in base_beam.items():
        if label in replaced:
            continue
        m = mod_beam.get(label)
        if m is None:
            continue
        errs = []
        for key in ("w_T_mm", "w_S_mm"):
            if entry.get(key) and m.get(key):
                errs.append(abs(m[key] - entry[key]) / entry[key])
        err = max(errs) if errs else None
        if err is not None:
            worst = max(worst, err)
        per_element.append({"element": label, "max_rel_err": err})
    return {"max_rel_err": worst, "per_element": per_element,
            "replaced": replaced}


# --- .dxf ----------------------------------------------------------------------

def _segment_samples(data, chain, seg, n_points=DXF_SAMPLES):
    """``(z_mm, w_T_mm, w_S_mm)`` samples along one segment.

    ``z`` is measured from the segment entrance (``s_in``). The
    waist is located from the entrance ``(w, R)`` and the radius
    is evaluated with the GRIN submatrix (exact for ranges and
    GRIN elements); samples are denser near the waist.
    """
    lam_nm = wavelength_nm(data)
    lam_m = lam_nm * 1e-9
    L_mm = seg["L_mm"]
    if L_mm <= 0:
        return [], [], []
    w_in_T = w_in_S = None
    R_in_T = R_in_S = None
    # Entrance beam: previous element's exit (or the element's own
    # exit for the first element -- a mirror, no segment).
    idx = chain.index(seg)
    if idx == 0:
        return [], [], []
    prev = chain[idx - 1]
    w_in_T, w_in_S = prev["w_T_mm"], prev["w_S_mm"]
    R_in_T, R_in_S = prev["R_T_mm"], prev["R_S_mm"]
    if w_in_T is None or w_in_S is None:
        return [], [], []
    q_T = q_from_wr(w_in_T * 1e-3,
                    None if R_in_T is None else R_in_T * 1e-3, lam_m)
    q_S = q_from_wr(w_in_S * 1e-3,
                    None if R_in_S is None else R_in_S * 1e-3, lam_m)
    # Waist positions (for denser sampling).
    w0_T, z_T = waist_from_q(q_T, lam_m)
    w0_S, z_S = waist_from_q(q_S, lam_m)
    # Sample points: uniform + extra points near each waist.
    zs = sorted(set([i * L_mm / (n_points - 1)
                     for i in range(n_points)]))
    for z_w in (z_T * 1e3, z_S * 1e3):
        # z_w is the signed distance plane -> waist (positive =
        # upstream, i.e. behind the entrance); the waist inside the
        # segment is at u = -z_w from the entrance.
        u_w = -z_w
        if 0.0 <= u_w <= L_mm:
            for du in (-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0):
                u = u_w + du
                if 0.0 <= u <= L_mm:
                    zs.append(u)
    zs = sorted(set(round(z, 9) for z in zs))
    # Radii at each sample via the submatrix (GRIN/range exact).
    try:
        _L, n0, g_T, g_S = element_grin_params(data, seg["label"])
    except (QevolveError, ValueError):
        n0, g_T, g_S = seg["n"], 0.0, 0.0
    w_Ts, w_Ss = [], []
    for z in zs:
        u_m = z * 1e-3
        w_Ts.append(_submatrix_w(q_T, u_m, n0, g_T, lam_m) * 1e3)
        w_Ss.append(_submatrix_w(q_S, u_m, n0, g_S, lam_m) * 1e3)
    return zs, w_Ts, w_Ss


def _fold_walk(chain):
    """Global 2D pose of each element: ``{label: (x_mm, y_mm, phi_rad)}``.

    The beam starts at the first element heading along +x; at each
    mirror the direction rotates by ``2*Alpha`` (the full fold
    angle; Alpha is the AOI). ``phi`` is the beam direction after
    the element.
    """
    poses = {}
    x = y = 0.0
    phi = 0.0
    for seg in chain:
        poses[seg["label"]] = (x, y, phi)
        if seg["type"] in ("ElemFlatMirror", "ElemCurveMirror"):
            phi += 2.0 * seg["alpha_rad"]
        else:
            dx = seg["L_mm"] * math.cos(phi)
            dy = seg["L_mm"] * math.sin(phi)
            x += dx
            y += dy
    return poses


def to_dxf(data, eng=None, binary=DEFAULT_BINARY, timeout=None,
           use_ezdxf=None):
    """Export a 2D beam-envelope .dxf.

    Returns ``(dxf_text, validation)``. ``use_ezdxf`` forces the
    writer (``True``: ezdxf, ``False``: the hand-written minimal
    R2000 writer); ``None`` (default) uses ezdxf when installed.
    Validation re-parses the file and checks the layers, the
    polyline point counts and the envelope against the CLI ``w(z)``.
    """
    rez_data = data if isinstance(data, dict) else load_rez(data)
    eng_data = eng if isinstance(eng, dict) else \
        (load_eng(eng) if eng else {})
    warnings = validate_eng(eng_data)
    result = run_headless({"base_schema": rez_data, "mutations": []},
                          binary=binary, timeout=timeout)["results"][0]
    if not result.get("ok"):
        raise ExportError("headless evaluation failed: %s"
                          % result.get("error"))
    if not result.get("stable"):
        raise ExportError("cavity is unstable (g_T=%r, g_S=%r); the "
                          ".dxf needs the eigenmode beam"
                          % (result.get("g_T"), result.get("g_S")))
    chain = build_chain(rez_data, result, eng_data)
    poses = _fold_walk(chain)
    layout = eng_data.get("layout")
    layout = layout if isinstance(layout, dict) else {}
    layout_elems = layout.get("elements")
    layout_elems = layout_elems if isinstance(layout_elems, dict) else {}
    # Override poses from the side-car layout section.
    for label, spec in layout_elems.items():
        if not isinstance(spec, dict) or label not in poses:
            continue
        x = spec.get("x_mm")
        y = spec.get("y_mm")
        ang = spec.get("angle_deg")
        ox, oy, ophi = poses[label]
        poses[label] = (float(x) if _is_number(x) else ox,
                        float(y) if _is_number(y) else oy,
                        math.radians(float(ang)) if _is_number(ang)
                        else ophi)
    # Build the polylines: axis + upper/lower envelopes per segment.
    axis_pts = []
    env1_pts = []   # +w (1/e^2), upper
    env1m_pts = []  # -w, lower
    env2_pts = []   # +2w
    env2m_pts = []  # -2w
    max_w = {}
    for seg in chain:
        if seg["L_mm"] <= 0:
            continue
        x0, y0, phi = poses[seg["label"]]
        zs, w_Ts, w_Ss = _segment_samples(rez_data, chain, seg)
        if not zs:
            continue
        # Envelope: the larger of the two planes (conservative).
        ws = [max(t, s) for t, s in zip(w_Ts, w_Ss)]
        max_w[seg["label"]] = max(ws) if ws else 0.0
        cos_p, sin_p = math.cos(phi), math.sin(phi)
        for z, w in zip(zs, ws):
            gx = x0 + z * cos_p
            gy = y0 + z * sin_p
            # Transverse unit vector (-sin, cos).
            tx, ty = -sin_p, cos_p
            axis_pts.append((gx, gy))
            env1_pts.append((gx + w * tx, gy + w * ty))
            env1m_pts.append((gx - w * tx, gy - w * ty))
            env2_pts.append((gx + 2.0 * w * tx, gy + 2.0 * w * ty))
            env2m_pts.append((gx - 2.0 * w * tx, gy - 2.0 * w * ty))
    # Element markers: a short line across the beam at each element.
    elements_draw = []
    for seg in chain:
        x0, y0, phi = poses[seg["label"]]
        ap = seg["aperture_mm"] or DEFAULT_DRAW_APERTURE_MM
        half = ap / 2.0
        tx, ty = -math.sin(phi), math.cos(phi)
        elements_draw.append({
            "label": seg["label"],
            "p1": (x0 - half * tx, y0 - half * ty),
            "p2": (x0 + half * tx, y0 + half * ty),
            "centre": (x0, y0)})
    annotations = []
    for seg in chain:
        x0, y0, phi = poses[seg["label"]]
        annotations.append({"label": seg["label"],
                            "pos": (x0 + 2.0, y0 + 2.0),
                            "text": "%s  w=%.3f mm" % (
                                seg["label"],
                                seg["w_T_mm"]
                                if seg["w_T_mm"] is not None else -1)})
    doc = {"axis": axis_pts, "env1": env1_pts, "env1m": env1m_pts,
           "env2": env2_pts, "env2m": env2m_pts,
           "elements": elements_draw, "annotations": annotations}
    if use_ezdxf is None:
        try:
            import ezdxf  # noqa: F401
            use_ezdxf = True
        except ImportError:
            use_ezdxf = False
    if use_ezdxf:
        text = _write_dxf_ezdxf(doc)
        writer = "ezdxf"
    else:
        text = _write_dxf_minimal(doc)
        writer = "minimal R2000 (hand-written, LWPOLYLINE/TEXT only)"
    validation = validate_dxf(text, doc, max_w, chain)
    validation["writer"] = writer
    validation["warnings"] = warnings
    return text, validation


def _write_dxf_ezdxf(doc):
    """Write the drawing with ezdxf (R2010)."""
    import ezdxf
    drawing = ezdxf.new("R2010", setup=True)
    drawing.units = ezdxf.units.MM
    for layer in ("OPTICAL_AXIS", "BEAM_1E2", "BEAM_2W", "ELEMENTS",
                  "ANNOTATIONS"):
        drawing.layers.add(layer)
    msp = drawing.modelspace()
    msp.add_lwpolyline(doc["axis"], dxfattribs={"layer": "OPTICAL_AXIS"})
    for key in ("env1", "env1m"):
        msp.add_lwpolyline(doc[key],
                           dxfattribs={"layer": "BEAM_1E2"})
    for key in ("env2", "env2m"):
        msp.add_lwpolyline(doc[key],
                           dxfattribs={"layer": "BEAM_2W"})
    for elem in doc["elements"]:
        msp.add_line(elem["p1"], elem["p2"],
                     dxfattribs={"layer": "ELEMENTS"})
    for ann in doc["annotations"]:
        msp.add_text(ann["text"], dxfattribs={
            "layer": "ANNOTATIONS", "height": 2.5}).set_placement(
                ann["pos"])
    import io
    stream = io.StringIO()
    drawing.write(stream)
    return stream.getvalue()


def _write_dxf_minimal(doc):
    """Hand-written minimal DXF R2000 (AC1015).

    Subset: HEADER + TABLES (layers only) + ENTITIES with
    LWPOLYLINE (axis / envelopes), LINE (elements) and TEXT
    (annotations). No blocks, styles, or dimension objects.
    """
    out = []
    out.append("  0\nSECTION\n  2\nHEADER\n  9\n$ACADVER\n  1\nAC1015\n"
               "  9\n$INSUNITS\n 70\n4\n  0\nENDSEC")
    out.append("  0\nSECTION\n  2\nTABLES\n  0\nTABLE\n  2\nLAYER\n 70\n6")
    for layer in ("OPTICAL_AXIS", "BEAM_1E2", "BEAM_2W", "ELEMENTS",
                  "ANNOTATIONS"):
        out.append("  0\nLAYER\n  2\n%s\n 70\n0\n 62\n7\n  6\nContinuous"
                   % layer)
    out.append("  0\nENDTAB\n  0\nENDSEC")
    out.append("  0\nSECTION\n  2\nENTITIES")
    def lwpolyline(points, layer):
        s = ["  0\nLWPOLYLINE\n100\nAcDbEntity\n  8\n%s\n100\n"
             "AcDbPolyline\n 90\n%d\n 70\n0" % (layer, len(points))]
        for (x, y) in points:
            s.append(" 10\n%.6f\n 20\n%.6f" % (x, y))
        return "\n".join(s)
    out.append(lwpolyline(doc["axis"], "OPTICAL_AXIS"))
    for key in ("env1", "env1m"):
        out.append(lwpolyline(doc[key], "BEAM_1E2"))
    for key in ("env2", "env2m"):
        out.append(lwpolyline(doc[key], "BEAM_2W"))
    for elem in doc["elements"]:
        (x1, y1), (x2, y2) = elem["p1"], elem["p2"]
        out.append("  0\nLINE\n100\nAcDbEntity\n  8\nELEMENTS\n100\n"
                   "AcDbLine\n 10\n%.6f\n 20\n%.6f\n"
                   " 11\n%.6f\n 21\n%.6f" % (x1, y1, x2, y2))
    for ann in doc["annotations"]:
        x, y = ann["pos"]
        text = ann["text"].replace("\\", "\\\\")
        out.append("  0\nTEXT\n100\nAcDbEntity\n  8\nANNOTATIONS\n100\n"
                   "AcDbText\n 10\n%.6f\n 20\n%.6f\n"
                   " 40\n2.5\n  1\n%s" % (x, y, text))
    out.append("  0\nENDSEC\n  0\nEOF")
    return "\n".join(out) + "\n"


def validate_dxf(text, doc, max_w, chain):
    """Re-parse the exported .dxf and check it against the model.

    Checks (with ezdxf when available, else the minimal parser):
    all five layers exist; the polyline point counts match the
    model; the envelope half-width at the widest point matches the
    CLI ``w(z)`` maximum per segment. Returns
    ``{"ok": bool, "checks": [...]}``.
    """
    checks = []
    ok = True
    try:
        import ezdxf
        import io
        drawing = ezdxf.read(io.StringIO(text))
        layers = {layer.dxf.name for layer in drawing.layers}
        counts = {}
        for entity in drawing.modelspace():
            typ = entity.dxftype()
            layer = entity.dxf.layer
            if typ == "LWPOLYLINE":
                counts[layer] = counts.get(layer, 0) \
                    + len(list(entity.vertices()))
            elif typ in ("LINE", "TEXT"):
                counts[layer] = counts.get(layer, 0) + 1
    except ImportError:
        layers, counts = _parse_dxf_minimal(text)
    except Exception as e:
        return {"ok": False, "checks": [{
            "check": "re-parse the exported .dxf", "ok": False,
            "error": str(e)}]}
    for layer in ("OPTICAL_AXIS", "BEAM_1E2", "BEAM_2W", "ELEMENTS",
                  "ANNOTATIONS"):
        present = layer in layers
        checks.append({"check": "layer %s present" % layer,
                       "ok": bool(present)})
        ok = ok and present
    expected = {"OPTICAL_AXIS": len(doc["axis"]),
                "BEAM_1E2": len(doc["env1"]) + len(doc["env1m"]),
                "BEAM_2W": len(doc["env2"]) + len(doc["env2m"]),
                "ELEMENTS": len(doc["elements"]),
                "ANNOTATIONS": len(doc["annotations"])}
    for layer, want in expected.items():
        got = counts.get(layer, 0)
        match = got == want
        checks.append({"check": "point/entity count on %s" % layer,
                       "expected": want, "got": got, "ok": bool(match)})
        ok = ok and match
    # Envelope vs CLI: the sampled envelope maximum (over all
    # segments, the segment ends are sampled exactly) must match
    # the largest CLI exit radius.
    cli_max = 0.0
    for seg in chain:
        if seg["w_T_mm"]:
            cli_max = max(cli_max, seg["w_T_mm"])
        if seg["w_S_mm"]:
            cli_max = max(cli_max, seg["w_S_mm"])
    model_max = max(max_w.values()) if max_w else 0.0
    match = cli_max > 0 and abs(model_max - cli_max) <= 1e-6 * cli_max
    checks.append({"check": "envelope max vs CLI max w (mm)",
                   "model_max_mm": model_max, "cli_max_mm": cli_max,
                   "ok": bool(match)})
    ok = ok and match
    return {"ok": bool(ok), "checks": checks}


def _parse_dxf_minimal(text):
    """Minimal DXF parser for the hand-written writer (layers +
    LWPOLYLINE/LINE/TEXT counts). Returns ``(layers, counts)``."""
    layers = set()
    counts = {}
    lines = text.splitlines()
    i = 0
    current_layer = None
    current_type = None
    in_layer_table = False
    while i + 1 < len(lines):
        code = lines[i].strip()
        value = lines[i + 1].strip()
        i += 2
        if code == "0":
            current_type = value
            if value == "LAYER":
                in_layer_table = True
            elif value in ("LWPOLYLINE", "LINE", "TEXT"):
                in_layer_table = False
            elif value in ("ENDTAB", "ENDSEC", "EOF"):
                in_layer_table = False
                current_layer = None
        elif code == "2" and current_type == "LAYER":
            layers.add(value)
        elif code == "8" and current_type in ("LWPOLYLINE", "LINE",
                                              "TEXT"):
            current_layer = value
            layers.add(value)
            counts[current_layer] = counts.get(current_layer, 0)
            if current_type in ("LINE", "TEXT"):
                counts[current_layer] += 1
        elif code == "10" and current_type == "LWPOLYLINE":
            counts[current_layer] = counts.get(current_layer, 0) + 1
    return layers, counts


def main(argv=None):
    """CLI entry: ``run_export.py <file.rez> [side-car] [options]``."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Export the coating table, .zmx and .dxf for a "
                    ".rez cavity.")
    parser.add_argument("rez_path", help=".rez file")
    parser.add_argument("eng_path", nargs="?",
                        help="side-car file (default: <file>.rez.eng.json)")
    parser.add_argument("--coating", action="store_true",
                        help="print the coating table")
    parser.add_argument("--zmx", metavar="OUT",
                        help="write the .zmx file to OUT")
    parser.add_argument("--dxf", metavar="OUT",
                        help="write the .dxf file to OUT")
    parser.add_argument("--no-ezdxf", action="store_true",
                        help="force the hand-written minimal DXF writer")
    parser.add_argument("--thin-lens-check", action="store_true",
                        help="run the CLI thin-lens spot check for .zmx")
    parser.add_argument("--binary", default=DEFAULT_BINARY,
                        help="path to the rezonator binary")
    args = parser.parse_args(argv)
    eng_path = args.eng_path or eng_path_for(args.rez_path)
    try:
        if args.coating:
            table = coating_table(args.rez_path, eng_path,
                                  binary=args.binary)
            print(table["text"])
            for w in table["warnings"]:
                print("warning: %s" % w, file=sys.stderr)
        if args.zmx:
            text, validation = to_zmx(args.rez_path, eng_path,
                                      binary=args.binary)
            with open(args.zmx, "w", encoding="utf-8") as f:
                f.write(text)
            print(json.dumps(validation, ensure_ascii=False, indent=2))
        if args.thin_lens_check:
            check = thin_lens_spot_check(args.rez_path, eng_path,
                                         binary=args.binary)
            print(json.dumps(check, ensure_ascii=False, indent=2))
        if args.dxf:
            text, validation = to_dxf(args.rez_path, eng_path,
                                      binary=args.binary,
                                      use_ezdxf=not args.no_ezdxf)
            with open(args.dxf, "w", encoding="utf-8") as f:
                f.write(text)
            print(json.dumps(validation, ensure_ascii=False, indent=2))
        if not (args.coating or args.zmx or args.dxf
                or args.thin_lens_check):
            parser.print_help()
            return 2
    except (OSError, ValueError, ExportError) as e:
        print("run_export: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
