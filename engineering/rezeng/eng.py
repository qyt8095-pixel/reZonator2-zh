"""Side-car engineering data (``<file>.rez.eng.json``).

Engineering data (LIDT, apertures, mounts, ...) lives *next to* the
.rez file, not inside it: the application's own writer drops unknown
top-level keys on save, so embedding it in the .rez would silently lose
it. Nothing in this module touches the .rez itself.

Format (version 1; see ``engineering/README.md`` for the full spec)::

    {
      "format_version": 1,
      "laser": {                       // cavity-level laser parameters
        "pulse_energy_J": 0.001,       // per-pulse energy (optional)
        "pulse_duration_s": 1e-8,      // (optional, recorded as a condition)
        "rep_rate_Hz": 1000,           // (optional, recorded for reference)
        "notes": "..."
      },
      "board": {                       // optical breadboard (optional)
        "board_mm": [600, 600],        // [width, depth] in mm
        "hole_pitch_mm": 25
      },
      "elements": {                    // keyed by element label
        "M1": {
          "aperture_diameter_mm": 25.4,
          "lidt_J_per_cm2": 2.0,       // damage threshold at the stated
          "lidt_conditions": {         // conditions (optional notes)
            "wavelength_nm": 1064, "pulse_duration_s": 1e-8},
          "mount": {
            "footprint_mm": [50, 50],  // [width, depth] in mm
            "board_x_mm": 100,         // footprint centre, board coords
            "board_y_mm": 100
          }
        }
      }
    }

Every field except ``format_version`` is optional. Missing data never
gets a default: the checks report ``nodata`` for it instead of
computing a pass from an invented number. The same rule holds for
the Phase 2 sections (``gain_and_pump``, ``nonlinear_shg``): a
missing essential field raises an error naming the field.
"""

import json
import math

# Current side-car format version.
FORMAT_VERSION = 1


def eng_path(rez_path):
    """Side-car path for a .rez file: ``<file>.rez.eng.json``."""
    return rez_path + ".eng.json"


def load_eng(path):
    """Load a side-car file; returns ``{}`` when the file does not exist."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("%s: top-level JSON value is not an object" % path)
    return data


def save_eng(path, data):
    """Write a side-car file (UTF-8, 4-space indent, keys in order)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.write("\n")


def new_eng():
    """An empty side-car document with the documented sections."""
    return {"format_version": FORMAT_VERSION,
            "laser": {}, "board": {}, "elements": {},
            "elements_ext": {}, "gain_and_pump": {}, "nonlinear_shg": {},
            "mopa_chain": {}, "tolerances": [], "output_mirror": {}}


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


def _pos(problems, section, key, value, allow_zero=False):
    """Append a problem unless ``value`` is a (strictly) positive number.
    ``None`` (absent) is fine."""
    if value is None:
        return
    ok = _is_number(value) and (float(value) >= 0 if allow_zero
                                else float(value) > 0)
    if not ok:
        problems.append("%s.%s must be a %s number, got %r"
                        % (section, key,
                           "non-negative" if allow_zero else "positive",
                           value))


def _frac(problems, section, key, value, lo=0.0, hi=1.0,
          lo_ok=True, hi_ok=True):
    """Append a problem unless ``value`` lies in the [lo, hi] interval
    (endpoints included when ``lo_ok``/``hi_ok``). ``None`` is fine."""
    if value is None:
        return
    if not _is_number(value):
        problems.append("%s.%s must be a number in [%s, %s], got %r"
                        % (section, key, lo, hi, value))
        return
    v = float(value)
    if v < lo or (v == lo and not lo_ok) or v > hi or (v == hi and not hi_ok):
        problems.append("%s.%s must be in [%s, %s], got %r"
                        % (section, key, lo, hi, value))


def _sub(problems, data, key, known):
    """Return ``data[key]`` when it is an object (else append a problem
    and return ``None``); report unknown keys inside it."""
    section = data.get(key)
    if section is None:
        return None
    if not isinstance(section, dict):
        problems.append("%s section is not an object" % key)
        return None
    for field in section:
        if field not in known:
            problems.append("unknown key %s.%s (ignored)" % (key, field))
    return section


def validate_eng(data):
    """Check a side-car document; return a list of problem strings.

    An empty list means the document is structurally sound (it may
    still contain no data at all -- that is valid, the checks then
    report ``nodata``). Problems are warnings, not errors: the checks
    skip malformed values instead of crashing on them.
    """
    problems = []
    if not isinstance(data, dict):
        return ["side-car top-level value is not an object"]
    version = data.get("format_version")
    if version is not None and version != FORMAT_VERSION:
        problems.append("unsupported format_version %r (expected %d)"
                        % (version, FORMAT_VERSION))
    for key in data:
        if key not in ("format_version", "laser", "board", "elements",
                       "elements_ext", "gain_and_pump", "nonlinear_shg",
                       "mopa_chain", "tolerances", "output_mirror",
                       "notes"):
            problems.append("unknown top-level key %r (ignored)" % (key,))

    laser = data.get("laser")
    if laser is not None:
        if not isinstance(laser, dict):
            problems.append("laser section is not an object")
        else:
            for key, name in (("pulse_energy_J", "pulse energy"),
                              ("pulse_duration_s", "pulse duration"),
                              ("rep_rate_Hz", "repetition rate")):
                value = laser.get(key)
                if value is not None and (not _is_number(value)
                                          or float(value) <= 0):
                    problems.append("laser.%s must be a positive number, "
                                    "got %r" % (key, value))

    board = data.get("board")
    if board is not None:
        if not isinstance(board, dict):
            problems.append("board section is not an object")
        else:
            size = board.get("board_mm")
            if size is not None:
                if (not isinstance(size, (list, tuple)) or len(size) != 2
                        or not all(_is_number(v) and float(v) > 0
                                   for v in size)):
                    problems.append("board.board_mm must be [width, depth] "
                                    "of positive numbers, got %r" % (size,))
            pitch = board.get("hole_pitch_mm")
            if pitch is not None and (not _is_number(pitch)
                                      or float(pitch) <= 0):
                problems.append("board.hole_pitch_mm must be a positive "
                                "number, got %r" % (pitch,))

    elements = data.get("elements")
    if elements is not None:
        if not isinstance(elements, dict):
            problems.append("elements section is not an object")
        else:
            for label, entry in elements.items():
                if not isinstance(entry, dict):
                    problems.append("elements.%s is not an object" % label)
                    continue
                lidt = entry.get("lidt_J_per_cm2")
                if lidt is not None and (not _is_number(lidt)
                                         or float(lidt) <= 0):
                    problems.append("elements.%s.lidt_J_per_cm2 must be a "
                                    "positive number, got %r" % (label, lidt))
                aperture = entry.get("aperture_diameter_mm")
                if aperture is not None and (not _is_number(aperture)
                                             or float(aperture) <= 0):
                    problems.append("elements.%s.aperture_diameter_mm must "
                                    "be a positive number, got %r"
                                    % (label, aperture))
                mount = entry.get("mount")
                if mount is not None:
                    if not isinstance(mount, dict):
                        problems.append("elements.%s.mount is not an object"
                                        % label)
                    else:
                        footprint = mount.get("footprint_mm")
                        if footprint is not None:
                            if (not isinstance(footprint, (list, tuple))
                                    or len(footprint) != 2
                                    or not all(_is_number(v)
                                               and float(v) > 0
                                               for v in footprint)):
                                problems.append(
                                    "elements.%s.mount.footprint_mm must be "
                                    "[width, depth] of positive numbers, "
                                    "got %r" % (label, footprint))
                        for axis in ("board_x_mm", "board_y_mm"):
                            value = mount.get(axis)
                            if value is not None and not _is_number(value):
                                problems.append("elements.%s.mount.%s must "
                                                "be a number, got %r"
                                                % (label, axis, value))

    # -- gain_and_pump (Phase 2 power solver) -------------------------
    # All fields are optional; missing ones are reported as nodata by
    # rezeng.power.resolve_params, never filled with invented defaults.
    gp = _sub(problems, data, "gain_and_pump",
              {"gain_element", "crystal", "pump", "cavity", "thermal"})
    if gp is not None:
        label = gp.get("gain_element")
        if label is not None and not isinstance(label, str):
            problems.append("gain_and_pump.gain_element must be a string, "
                            "got %r" % (label,))
        crystal = _sub(problems, gp, "crystal",
                       {"material", "sigma_em_cm2", "tau_f_us",
                        "alpha_p_per_cm"})
        if crystal is not None:
            if (crystal.get("material") is not None
                    and not isinstance(crystal["material"], str)):
                problems.append("gain_and_pump.crystal.material must be a "
                                "string, got %r" % (crystal["material"],))
            _pos(problems, "gain_and_pump.crystal", "sigma_em_cm2",
                 crystal.get("sigma_em_cm2"))
            _pos(problems, "gain_and_pump.crystal", "tau_f_us",
                 crystal.get("tau_f_us"))
            _pos(problems, "gain_and_pump.crystal", "alpha_p_per_cm",
                 crystal.get("alpha_p_per_cm"), allow_zero=True)
        pump = _sub(problems, gp, "pump",
                    {"lambda_p_nm", "P_pump_W", "w_p0_um", "z_p0_mm",
                     "Mp2", "eta_p", "profile"})
        if pump is not None:
            _pos(problems, "gain_and_pump.pump", "lambda_p_nm",
                 pump.get("lambda_p_nm"))
            _pos(problems, "gain_and_pump.pump", "P_pump_W",
                 pump.get("P_pump_W"), allow_zero=True)
            _pos(problems, "gain_and_pump.pump", "w_p0_um",
                 pump.get("w_p0_um"))
            _pos(problems, "gain_and_pump.pump", "z_p0_mm",
                 pump.get("z_p0_mm"), allow_zero=True)
            mp2 = pump.get("Mp2")
            if mp2 is not None and (not _is_number(mp2)
                                    or float(mp2) < 1.0):
                problems.append("gain_and_pump.pump.Mp2 must be >= 1, "
                                "got %r" % (mp2,))
            _frac(problems, "gain_and_pump.pump", "eta_p",
                  pump.get("eta_p"), lo=0.0, hi=1.0,
                  lo_ok=False, hi_ok=True)
            profile = pump.get("profile")
            if profile is not None and profile not in ("gaussian",
                                                       "tophat"):
                problems.append("gain_and_pump.pump.profile must be "
                                "'gaussian' or 'tophat', got %r"
                                % (profile,))
        cavity = _sub(problems, gp, "cavity",
                      {"T_oc", "L_i", "eta_mode"})
        if cavity is not None:
            _frac(problems, "gain_and_pump.cavity", "T_oc",
                  cavity.get("T_oc"), lo=0.0, hi=1.0,
                  lo_ok=True, hi_ok=False)
            _frac(problems, "gain_and_pump.cavity", "L_i",
                  cavity.get("L_i"), lo=0.0, hi=1.0,
                  lo_ok=True, hi_ok=False)
            _frac(problems, "gain_and_pump.cavity", "eta_mode",
                  cavity.get("eta_mode"), lo=0.0, hi=1.0,
                  lo_ok=False, hi_ok=True)
        thermal = _sub(problems, gp, "thermal",
                       {"F0_mm", "kappa_th_per_W", "kappa_th_T_per_W",
                        "kappa_th_S_per_W", "anchor_F_ref_mm",
                        "anchor_P_ref_W", "P_nom_W", "eta_h",
                        "dn_dT_per_K", "K_c_W_per_mK"})
        if thermal is not None:
            _pos(problems, "gain_and_pump.thermal", "F0_mm",
                 thermal.get("F0_mm"))
            for key in ("kappa_th_per_W", "kappa_th_T_per_W",
                        "kappa_th_S_per_W"):
                _pos(problems, "gain_and_pump.thermal", key,
                     thermal.get(key), allow_zero=True)
            _pos(problems, "gain_and_pump.thermal", "anchor_F_ref_mm",
                 thermal.get("anchor_F_ref_mm"))
            _pos(problems, "gain_and_pump.thermal", "anchor_P_ref_W",
                 thermal.get("anchor_P_ref_W"))
            _pos(problems, "gain_and_pump.thermal", "P_nom_W",
                 thermal.get("P_nom_W"))
            _frac(problems, "gain_and_pump.thermal", "eta_h",
                  thermal.get("eta_h"), lo=0.0, hi=1.0,
                  lo_ok=False, hi_ok=True)
            _pos(problems, "gain_and_pump.thermal", "dn_dT_per_K",
                 thermal.get("dn_dT_per_K"))
            _pos(problems, "gain_and_pump.thermal", "K_c_W_per_mK",
                 thermal.get("K_c_W_per_mK"))
    # -- nonlinear_shg (Phase 2 SHG module) -------------------------
    # All fields are optional; missing ones are reported as nodata by
    # rezeng.shg.resolve_shg, never filled with invented defaults.
    # The MATERIALS table in rezeng.shg holds typical literature
    # values, but it is only applied through the explicit
    # fill_typical() helper, never silently.
    shg = _sub(problems, data, "nonlinear_shg",
               {"enabled", "mode", "crystal_element_id", "material",
                "length_mm", "d_eff_pm_V", "n_omega", "n_2omega",
                "phase_matching", "walkoff_mrad", "walkoff_plane",
                "delta_T_C", "temp_acceptance_C_cm", "delta_k_per_m",
                "single_frequency", "wavelength_2omega_nm", "notes"})
    if shg is not None:
        if shg.get("enabled") is not None \
                and not isinstance(shg.get("enabled"), bool):
            problems.append("nonlinear_shg.enabled must be a boolean, "
                            "got %r" % (shg.get("enabled"),))
        if shg.get("mode") is not None \
                and shg.get("mode") not in ("intracavity", "extracavity"):
            problems.append("nonlinear_shg.mode must be 'intracavity' "
                            "or 'extracavity', got %r" % (shg.get("mode"),))
        if shg.get("crystal_element_id") is not None \
                and not isinstance(shg.get("crystal_element_id"), str):
            problems.append("nonlinear_shg.crystal_element_id must be a "
                            "string, got %r"
                            % (shg.get("crystal_element_id"),))
        if shg.get("material") is not None \
                and not isinstance(shg.get("material"), str):
            problems.append("nonlinear_shg.material must be a string, "
                            "got %r" % (shg.get("material"),))
        for key in ("length_mm", "d_eff_pm_V", "n_omega", "n_2omega",
                    "wavelength_2omega_nm"):
            _pos(problems, "nonlinear_shg", key, shg.get(key))
        if shg.get("phase_matching") is not None \
                and str(shg.get("phase_matching")).upper() \
                not in ("CPM", "NCPM"):
            problems.append("nonlinear_shg.phase_matching must be 'CPM' "
                            "or 'NCPM', got %r"
                            % (shg.get("phase_matching"),))
        _pos(problems, "nonlinear_shg", "walkoff_mrad",
             shg.get("walkoff_mrad"), allow_zero=True)
        if shg.get("walkoff_plane") is not None \
                and str(shg.get("walkoff_plane")).upper() not in ("T", "S"):
            problems.append("nonlinear_shg.walkoff_plane must be 'T' or "
                            "'S', got %r" % (shg.get("walkoff_plane"),))
        if shg.get("delta_T_C") is not None \
                and not _is_number(shg.get("delta_T_C")):
            problems.append("nonlinear_shg.delta_T_C must be a number, "
                            "got %r" % (shg.get("delta_T_C"),))
        _pos(problems, "nonlinear_shg", "temp_acceptance_C_cm",
             shg.get("temp_acceptance_C_cm"))
        if shg.get("delta_k_per_m") is not None \
                and not _is_number(shg.get("delta_k_per_m")):
            problems.append("nonlinear_shg.delta_k_per_m must be a "
                            "number, got %r" % (shg.get("delta_k_per_m"),))
        if shg.get("single_frequency") is not None \
                and not isinstance(shg.get("single_frequency"), bool):
            problems.append("nonlinear_shg.single_frequency must be a "
                            "boolean, got %r"
                            % (shg.get("single_frequency"),))
    # -- elements_ext (Phase 2 block 3: Jones / dispersion / SESAM) --
    # Per-label extra element data (keys are element labels, so the
    # section is checked by hand, not with _sub). All fields optional;
    # unknown keys inside an entry are reported (the jones /
    # dispersion modules validate the values they actually use).
    from .dispersion import EXT_KEYS as _EXT_KEYS
    from .jones import _ALL_TYPES as _JONES_TYPES
    ext = data.get("elements_ext")
    if ext is not None:
        if not isinstance(ext, dict):
            problems.append("elements_ext section is not an object")
        else:
            for label, entry in ext.items():
                if not isinstance(entry, dict):
                    problems.append("elements_ext.%s is not an object"
                                    % label)
                    continue
                for field in entry:
                    if field not in _EXT_KEYS:
                        problems.append("unknown key elements_ext.%s.%s "
                                        "(ignored)" % (label, field))
                jones = entry.get("jones")
                if jones is not None:
                    if not isinstance(jones, dict):
                        problems.append("elements_ext.%s.jones is not an "
                                        "object" % label)
                    elif jones.get("type") not in _JONES_TYPES:
                        problems.append("elements_ext.%s.jones.type must "
                                        "be one of %s, got %r"
                                        % (label, ", ".join(_JONES_TYPES),
                                           jones.get("type")))
                    elif jones.get("type") == "polarizer":
                        for k in ("Tp", "Ts"):
                            _frac(problems,
                                  "elements_ext.%s.jones" % label,
                                  k, jones.get(k), lo=0.0, hi=1.0,
                                  lo_ok=True, hi_ok=True)
                for k in ("gvd_fs2_per_mm", "tod_fs3_per_mm",
                          "gdd_fs2", "tod_fs3"):
                    v = entry.get(k)
                    if v is not None and not _is_number(v):
                        problems.append("elements_ext.%s.%s must be a "
                                        "number, got %r" % (label, k, v))
                _frac(problems, "elements_ext.%s" % label,
                      "modulation_depth", entry.get("modulation_depth"),
                      lo=0.0, hi=1.0, lo_ok=True, hi_ok=True)
                _pos(problems, "elements_ext.%s" % label,
                     "saturation_fluence_uJ_per_cm2",
                     entry.get("saturation_fluence_uJ_per_cm2"))
    # -- mopa_chain (Phase 2 block 3: MOPA / regenerative chain) -----
    # Deep validation lives in rezeng.mopa.resolve_chain; here only
    # the section shape is checked so validate_eng stays a warning
    # pass, never a hard failure.
    chain = _sub(problems, data, "mopa_chain",
                 {"seed_source", "stages"})
    if chain is not None:
        seed = chain.get("seed_source")
        if seed is not None and not isinstance(seed, dict):
            problems.append("mopa_chain.seed_source is not an object")
        stages = chain.get("stages")
        if stages is not None:
            if not isinstance(stages, list):
                problems.append("mopa_chain.stages must be a list")
            else:
                for i, stage in enumerate(stages):
                    if not isinstance(stage, dict):
                        problems.append("mopa_chain.stages[%d] is not an "
                                        "object" % i)
                        continue
                    for field in stage:
                        if field not in ("stage_id", "rez_file", "passes",
                                         "gain_element", "gain_medium",
                                         "round_trip_loss", "loss_per_pass"):
                            problems.append(
                                "unknown key mopa_chain.stages[%d].%s "
                                "(ignored)" % (i, field))
    # -- tolerances (Phase 3 block 2: Monte Carlo) -------------------
    # Deep validation lives in rezeng.montecarlo._validate_tolerances;
    # here only the section shape is checked so validate_eng stays a
    # warning pass, never a hard failure.
    tolerances = data.get("tolerances")
    if tolerances is not None:
        if not isinstance(tolerances, list):
            problems.append("tolerances section must be a list")
        else:
            for i, entry in enumerate(tolerances):
                if not isinstance(entry, dict):
                    problems.append("tolerances[%d] is not an object" % i)
                    continue
                for field in entry:
                    if field not in ("label", "alias", "kind",
                                     "distribution", "sigma", "half_width",
                                     "notes"):
                        problems.append("unknown key tolerances[%d].%s "
                                        "(ignored)" % (i, field))
                if entry.get("kind") not in (None, "length", "relative",
                                             "dioptric", "angle"):
                    problems.append("tolerances[%d].kind must be "
                                    "'length', 'relative', 'dioptric' or "
                                    "'angle', got %r" % (i, entry.get("kind")))
                if entry.get("distribution") not in (
                        None, "normal", "uniform", "truncated_normal",
                        "rayleigh"):
                    problems.append("tolerances[%d].distribution must be "
                                    "'normal', 'uniform', "
                                    "'truncated_normal' or 'rayleigh', "
                                    "got %r"
                                    % (i, entry.get("distribution")))
    # -- output_mirror (Phase 3 block 2: reverse fitting) ------------
    # The output-mirror substrate plate for the cavity-external
    # propagation: {"label", "thickness_mm", "n"}. All fields
    # optional; missing data means the plate is omitted (with a
    # warning and an error estimate in the fit report).
    mirror = _sub(problems, data, "output_mirror",
                  {"label", "thickness_mm", "n", "notes"})
    if mirror is not None:
        if mirror.get("label") is not None \
                and not isinstance(mirror.get("label"), str):
            problems.append("output_mirror.label must be a string, got %r"
                            % (mirror.get("label"),))
        _pos(problems, "output_mirror", "thickness_mm",
             mirror.get("thickness_mm"))
        _pos(problems, "output_mirror", "n", mirror.get("n"))
    return problems
