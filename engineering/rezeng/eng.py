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
computing a pass from an invented number.
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
            "laser": {}, "board": {}, "elements": {}}


def _is_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)))


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
        if key not in ("format_version", "laser", "board", "elements"):
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
    return problems
