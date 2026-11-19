"""GDD / TOD accumulator (Phase 2 block 3).

Element data lives in the side-car ``elements_ext`` section, keyed by
element label::

    "elements_ext": {
      "TL1": {"material": "Nd:YVO4_e",
              "gvd_fs2_per_mm": 245.0, "tod_fs3_per_mm": 310.0},
      "M1":  {"role": "SESAM", "gdd_fs2": -150.0, "tod_fs3": 500.0,
              "modulation_depth": 0.012,
              "saturation_fluence_uJ_per_cm2": 70.0},
      "M4":  {"role": "chirped_mirror", "gdd_fs2": -300.0,
              "tod_fs3": 1200.0}
    }

Counting rules (per round trip, or per pass for SP):

* SW cavity: the first and last elements (the end mirrors) count
  **once**; every interior element counts **twice** (folding mirrors
  reflect twice per round trip, transmissive elements are traversed
  twice). RR and SP: every element counts once.
* Transmissive contribution: ``gvd_fs2_per_mm * L_mm * count`` (and
  analogously TOD), with ``L`` the element's physical thickness from
  the .rez file (unit-aware). An element with dispersion coefficients
  but no ``L`` parameter is skipped with a warning.
* Reflective contribution: ``gdd_fs2 * count`` (``tod_fs3 * count``)
  per reflection; it may be combined with a transmissive contribution
  on the same element (e.g. a coated plate).

SESAM parameters (``modulation_depth``, ``saturation_fluence``) are
recorded and reported per element as input for later Q-switch /
mode-lock dynamics; this block implements no dynamics.
"""

import math

from .rez import elements, param_value_si

#: Side-car keys understood per element in ``elements_ext``.
EXT_KEYS = ("material", "role", "gvd_fs2_per_mm", "tod_fs3_per_mm",
            "gdd_fs2", "tod_fs3", "modulation_depth",
            "saturation_fluence_uJ_per_cm2", "jones", "notes")


class DispersionError(ValueError):
    """Raised when a dispersion computation cannot be set up."""


def _number(value):
    """``float(value)`` when it is a finite number, else ``None``."""
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value))):
        return float(value)
    return None


def _counts(data):
    """Per-element pass count for one round trip (or one pass for SP).

    SW: first and last elements 1, interior elements 2. RR / SP: 1.
    """
    elems = elements(data)
    trip = str(data.get("trip_type") or "SW").upper()
    if trip == "SW":
        return [1 if i in (0, len(elems) - 1) else 2
                for i in range(len(elems))]
    if trip in ("SP", "RR"):
        return [1] * len(elems)
    raise DispersionError("unknown trip_type %r" % (trip,))


def round_trip_dispersion(data, eng):
    """Round-trip (or single-pass) GDD / TOD accumulation.

    Returns ``{GDD_fs2, TOD_fs3, trip_type, per_element, warnings}``.
    ``per_element`` lists every element that carries dispersion data:
    ``{label, count, gdd_fs2, tod_fs3, role, modulation_depth,
    saturation_fluence_uJ_per_cm2}``. Elements without dispersion data
    contribute nothing and are not listed.
    """
    ext = (eng or {}).get("elements_ext")
    ext = ext if isinstance(ext, dict) else {}
    counts = _counts(data)
    per_element = []
    warnings = []
    total_gdd = 0.0
    total_tod = 0.0
    for elem, count in zip(elements(data), counts):
        if not isinstance(elem, dict):
            continue
        label = elem.get("label")
        entry = ext.get(label) if label is not None else None
        entry = entry if isinstance(entry, dict) else {}
        gvd = _number(entry.get("gvd_fs2_per_mm"))
        tod_c = _number(entry.get("tod_fs3_per_mm"))
        gdd = _number(entry.get("gdd_fs2"))
        tod_r = _number(entry.get("tod_fs3"))
        if gvd is None and tod_c is None and gdd is None and tod_r is None:
            continue
        gdd_total = 0.0
        tod_total = 0.0
        if gvd is not None or tod_c is not None:
            L_m = param_value_si(data, label, "L")
            if L_m is None:
                warnings.append(
                    "element %r has dispersion coefficients but no L "
                    "parameter; its transmissive contribution is skipped"
                    % (label,))
            else:
                L_mm = L_m * 1e3
                if gvd is not None:
                    gdd_total += gvd * L_mm * count
                if tod_c is not None:
                    tod_total += tod_c * L_mm * count
        if gdd is not None:
            gdd_total += gdd * count
        if tod_r is not None:
            tod_total += tod_r * count
        total_gdd += gdd_total
        total_tod += tod_total
        per_element.append({
            "label": label, "count": count,
            "gdd_fs2": gdd_total, "tod_fs3": tod_total,
            "role": entry.get("role"),
            "modulation_depth": _number(entry.get("modulation_depth")),
            "saturation_fluence_uJ_per_cm2": _number(
                entry.get("saturation_fluence_uJ_per_cm2")),
        })
    return {"GDD_fs2": total_gdd, "TOD_fs3": total_tod,
            "trip_type": str(data.get("trip_type") or "SW").upper(),
            "per_element": per_element, "warnings": warnings}


def dispersion_report(rez_path, eng_path=None):
    """GDD / TOD report for a .rez file (JSON-safe dict)."""
    from .eng import eng_path as eng_path_for, load_eng
    from .rez import load_rez

    if eng_path is None:
        eng_path = eng_path_for(rez_path)
    data = load_rez(rez_path)
    eng = load_eng(eng_path)
    result = round_trip_dispersion(data, eng)
    result["rez_path"] = rez_path
    result["eng_path"] = eng_path
    return result
