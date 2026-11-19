"""Engineering checks (Phase 1 block 2): LIDT, aperture clipping, breadboard.

All beam radii come from the headless CLI (``rezeng.cli``) -- this
module never recomputes optics itself. Engineering data comes from
the side-car file (``rezeng.eng``); the .rez itself carries no LIDT,
aperture or mount data, and nothing here writes to the .rez.

Three checks, one entry per element per check (plus a total entry for
aperture and one per mount pair for overlap)::

    {"id", "element", "kind", "status", "value", "limit", "unit", "message"}

``status`` is ``ok`` / ``warn`` / ``fail`` / ``nodata``. Missing data
is reported as ``nodata`` -- never silently defaulted to a pass.

Formulas, thresholds and geometry assumptions are documented in
``engineering/README.md``; the tunable constants live below.
"""

import argparse
import json
import math
import os
import sys

from .cli import DEFAULT_BINARY, HeadlessError, run_headless_file
from .eng import eng_path as eng_path_for, load_eng, validate_eng
from .rez import elements, load_rez

# --- Tunable thresholds -------------------------------------------------
#: LIDT: warn when the peak fluence exceeds this fraction of the
#: threshold; fail above a ratio of 1.0.
LIDT_WARN_RATIO = 0.8
LIDT_FAIL_RATIO = 1.0

#: Aperture clipping: warn when a single element clips more than 1%
#: of the power, or the combined loss of all apertures exceeds 2%.
APERTURE_WARN_SINGLE = 0.01
APERTURE_WARN_TOTAL = 0.02

#: Breadboard grid: a mount centre counts as "on grid" when it is
#: within this distance (mm) of a hole-grid point.
BOARD_GRID_TOL_MM = 1e-6

REPORT_VERSION = 1


# --- Pure helpers (unit-testable without the CLI) ------------------------

def _pos_number(value):
    """``float(value)`` when it is a finite positive number, else None."""
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) > 0):
        return float(value)
    return None


def _number(value):
    """``float(value)`` when it is a finite number, else None."""
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value))):
        return float(value)
    return None


def lidt_fluence_J_per_cm2(energy_J, w_T_mm, w_S_mm):
    """Peak fluence of an elliptical Gaussian beam, in J/cm^2.

    ``F = 2E / (pi * w_T * w_S)`` with the radii in cm. Raises
    :class:`ValueError` for a non-positive radius or negative energy.
    """
    if energy_J < 0:
        raise ValueError("pulse energy must not be negative: %r" % energy_J)
    if w_T_mm <= 0 or w_S_mm <= 0:
        raise ValueError("beam radii must be positive: %r, %r"
                         % (w_T_mm, w_S_mm))
    w_T_cm = w_T_mm / 10.0
    w_S_cm = w_S_mm / 10.0
    return 2.0 * energy_J / (math.pi * w_T_cm * w_S_cm)


def classify_lidt(ratio):
    """LIDT status from ``fluence / threshold``: ``> 1`` fails,
    ``> 0.8`` warns, otherwise ok."""
    if ratio > LIDT_FAIL_RATIO:
        return "fail"
    if ratio > LIDT_WARN_RATIO:
        return "warn"
    return "ok"


def aperture_loss_fraction(aperture_diameter_mm, w_mm):
    """Power fraction clipped by a circular aperture for a Gaussian beam.

    ``loss = exp(-2 * a^2 / w^2)`` with ``a`` the aperture radius and
    ``w`` the (larger) beam radius. Raises :class:`ValueError` for a
    non-positive beam radius or a negative aperture diameter.
    """
    if w_mm <= 0:
        raise ValueError("beam radius must be positive: %r" % w_mm)
    if aperture_diameter_mm < 0:
        raise ValueError("aperture diameter must not be negative: %r"
                         % aperture_diameter_mm)
    a = aperture_diameter_mm / 2.0
    return math.exp(-2.0 * (a / w_mm) ** 2)


def combined_loss(fractions):
    """Total loss of apertures in series: ``1 - prod(1 - f_i)``."""
    total = 1.0
    for f in fractions:
        total *= (1.0 - f)
    return 1.0 - total


def mount_rect(mount):
    """Axis-aligned footprint rectangle ``(x0, y0, x1, y1)`` in mm.

    ``mount`` is ``{"footprint_mm": [w, d], "board_x_mm": x,
    "board_y_mm": y}`` with (x, y) the footprint *centre* in board
    coordinates (board origin at one corner). Returns ``None`` when
    the mount data is incomplete.
    """
    if not isinstance(mount, dict):
        return None
    footprint = mount.get("footprint_mm")
    x = _number(mount.get("board_x_mm"))
    y = _number(mount.get("board_y_mm"))
    if (not isinstance(footprint, (list, tuple)) or len(footprint) != 2
            or x is None or y is None):
        return None
    w = _pos_number(footprint[0])
    d = _pos_number(footprint[1])
    if w is None or d is None:
        return None
    return (x - w / 2.0, y - d / 2.0, x + w / 2.0, y + d / 2.0)


def rects_overlap(a, b):
    """True when two ``(x0, y0, x1, y1)`` rectangles overlap with
    positive area. Rectangles that merely touch along an edge do not
    overlap."""
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def rect_overlap_area(a, b):
    """Overlap area in mm^2 (0 when the rectangles do not overlap)."""
    if not rects_overlap(a, b):
        return 0.0
    return (min(a[2], b[2]) - max(a[0], b[0])) * \
           (min(a[3], b[3]) - max(a[1], b[1]))


def rect_overhang(rect, board_mm):
    """How far a rectangle sticks out past a ``[width, depth]`` board,
    in mm (0 when fully inside)."""
    w, d = board_mm
    return max(0.0, -rect[0], rect[2] - w, -rect[1], rect[3] - d)


def grid_offset(value, pitch):
    """Distance from ``value`` to the nearest multiple of ``pitch``."""
    return abs(value - round(value / pitch) * pitch)


# --- Check builders ------------------------------------------------------

def _entry(check_id, element, kind, status, value=None, limit=None,
           unit=None, message=""):
    return {"id": check_id, "element": element, "kind": kind,
            "status": status, "value": value, "limit": limit,
            "unit": unit, "message": message}


def _eng_elements(eng):
    data = eng.get("elements")
    return data if isinstance(data, dict) else {}


def _eng_section(eng, name):
    data = eng.get(name)
    return data if isinstance(data, dict) else {}


def check_lidt(labels, beam, eng):
    """One ``lidt`` entry per element.

    ``beam`` maps label -> ``{"w_T_mm", "w_S_mm"}`` from the headless
    CLI (empty when the cavity is unstable or uses a ray-vector pump).
    ``pulse_energy_J`` is the per-pulse energy *incident on that
    element* (see README -- the user fills it per element when the
    circulating energy differs from the output).
    """
    laser = _eng_section(eng, "laser")
    energy = _pos_number(laser.get("pulse_energy_J"))
    eng_elements = _eng_elements(eng)
    checks = []
    for label in labels:
        entry = eng_elements.get(label)
        entry = entry if isinstance(entry, dict) else {}
        lidt = _pos_number(entry.get("lidt_J_per_cm2"))
        spot = beam.get(label) if beam else None
        if energy is None:
            checks.append(_entry(
                "lidt:%s" % label, label, "lidt", "nodata",
                message="no pulse_energy_J in the side-car laser section"))
        elif lidt is None:
            checks.append(_entry(
                "lidt:%s" % label, label, "lidt", "nodata",
                message="no lidt_J_per_cm2 for this element in the side-car"))
        elif spot is None:
            checks.append(_entry(
                "lidt:%s" % label, label, "lidt", "nodata",
                message="no beam radius from the headless CLI for this "
                        "element (inactive element, unstable cavity, or "
                        "ray-vector pump)"))
        else:
            try:
                fluence = lidt_fluence_J_per_cm2(
                    energy, spot["w_T_mm"], spot["w_S_mm"])
            except ValueError as e:
                checks.append(_entry(
                    "lidt:%s" % label, label, "lidt", "nodata",
                    message="invalid beam radius: %s" % e))
                continue
            ratio = fluence / lidt
            checks.append(_entry(
                "lidt:%s" % label, label, "lidt", classify_lidt(ratio),
                value=fluence, limit=lidt, unit="J/cm^2",
                message="peak fluence %.4g J/cm^2, %.1f%% of LIDT %.4g "
                        "J/cm^2 (w_T=%.4g mm, w_S=%.4g mm)"
                        % (fluence, 100.0 * ratio, lidt,
                           spot["w_T_mm"], spot["w_S_mm"])))
    return checks


def check_aperture(labels, beam, eng):
    """One ``aperture`` entry per element plus an ``aperture_total`` entry.

    Clipping loss uses the conservative radius ``w = max(w_T, w_S)``.
    The total is the series loss over all elements that have both an
    aperture and a beam radius.
    """
    eng_elements = _eng_elements(eng)
    checks = []
    losses = []
    for label in labels:
        entry = eng_elements.get(label)
        entry = entry if isinstance(entry, dict) else {}
        diameter = _pos_number(entry.get("aperture_diameter_mm"))
        spot = beam.get(label) if beam else None
        if diameter is None:
            checks.append(_entry(
                "aperture:%s" % label, label, "aperture", "nodata",
                message="no aperture_diameter_mm for this element in the "
                        "side-car"))
        elif spot is None:
            checks.append(_entry(
                "aperture:%s" % label, label, "aperture", "nodata",
                message="no beam radius from the headless CLI for this "
                        "element (inactive element, unstable cavity, or "
                        "ray-vector pump)"))
        else:
            w = max(spot["w_T_mm"], spot["w_S_mm"])
            try:
                loss = aperture_loss_fraction(diameter, w)
            except ValueError as e:
                checks.append(_entry(
                    "aperture:%s" % label, label, "aperture", "nodata",
                    message="invalid beam radius: %s" % e))
                continue
            losses.append(loss)
            checks.append(_entry(
                "aperture:%s" % label, label, "aperture",
                "warn" if loss > APERTURE_WARN_SINGLE else "ok",
                value=loss, limit=APERTURE_WARN_SINGLE, unit="fraction",
                message="clipping loss %.4g%% (aperture %.4g mm, "
                        "w=max(w_T, w_S)=%.4g mm)"
                        % (100.0 * loss, diameter, w)))
    if losses:
        total = combined_loss(losses)
        checks.append(_entry(
            "aperture_total", None, "aperture_total",
            "warn" if total > APERTURE_WARN_TOTAL else "ok",
            value=total, limit=APERTURE_WARN_TOTAL, unit="fraction",
            message="combined clipping loss %.4g%% over %d aperture(s)"
                    % (100.0 * total, len(losses))))
    else:
        checks.append(_entry(
            "aperture_total", None, "aperture_total", "nodata",
            message="no element has both an aperture and a beam radius"))
    return checks


def check_board(labels, eng):
    """Breadboard checks: bounds, pairwise overlap, hole-grid alignment.

    Geometry is 2-D axis-aligned rectangles only: the footprint centre
    (``board_x_mm``, ``board_y_mm``) in board coordinates, board origin
    at one corner, board spanning ``[0, W] x [0, D]``. Height
    interference and beam-path obstruction are *not* modelled.
    """
    board = _eng_section(eng, "board")
    size = board.get("board_mm")
    size = (float(size[0]), float(size[1])) \
        if (isinstance(size, (list, tuple)) and len(size) == 2
            and _pos_number(size[0]) is not None
            and _pos_number(size[1]) is not None) else None
    pitch = _pos_number(board.get("hole_pitch_mm"))
    eng_elements = _eng_elements(eng)

    rects = {}
    for label in labels:
        entry = eng_elements.get(label)
        entry = entry if isinstance(entry, dict) else {}
        rect = mount_rect(entry.get("mount"))
        if rect is not None:
            rects[label] = rect

    checks = []
    for label in labels:
        rect = rects.get(label)
        if rect is None:
            checks.append(_entry(
                "board_bounds:%s" % label, label, "board_bounds", "nodata",
                message="no mount data for this element in the side-car"))
            checks.append(_entry(
                "board_grid:%s" % label, label, "board_grid", "nodata",
                message="no mount data for this element in the side-car"))
            continue
        if size is None:
            checks.append(_entry(
                "board_bounds:%s" % label, label, "board_bounds", "nodata",
                message="no board_mm in the side-car board section"))
        else:
            overhang = rect_overhang(rect, size)
            checks.append(_entry(
                "board_bounds:%s" % label, label, "board_bounds",
                "fail" if overhang > 0 else "ok",
                value=overhang, limit=0.0, unit="mm",
                message="footprint x [%.4g, %.4g] mm, y [%.4g, %.4g] mm "
                        "on a %.4g x %.4g mm board%s"
                        % (rect[0], rect[2], rect[1], rect[3], size[0],
                           size[1], "" if overhang == 0
                           else "; overhang %.4g mm" % overhang)))
        if pitch is None:
            checks.append(_entry(
                "board_grid:%s" % label, label, "board_grid", "nodata",
                message="no hole_pitch_mm in the side-car board section"))
        else:
            entry = eng_elements[label]
            offset = max(grid_offset(entry["mount"]["board_x_mm"], pitch),
                         grid_offset(entry["mount"]["board_y_mm"], pitch))
            checks.append(_entry(
                "board_grid:%s" % label, label, "board_grid",
                "warn" if offset > BOARD_GRID_TOL_MM else "ok",
                value=offset, limit=BOARD_GRID_TOL_MM, unit="mm",
                message="mount centre offset %.4g mm from the %.4g mm "
                        "hole grid" % (offset, pitch)))

    placed = [label for label in labels if label in rects]
    if len(placed) < 2:
        checks.append(_entry(
            "board_overlap", None, "board_overlap", "nodata",
            message="fewer than two mounts have complete position data"))
    else:
        for i, a in enumerate(placed):
            for b in placed[i + 1:]:
                area = rect_overlap_area(rects[a], rects[b])
                checks.append(_entry(
                    "board_overlap:%s/%s" % (a, b), "%s / %s" % (a, b),
                    "board_overlap", "fail" if area > 0 else "ok",
                    value=area, limit=0.0, unit="mm^2",
                    message=("mount footprints overlap by %.4g mm^2"
                             % area) if area > 0
                            else "mount footprints do not overlap"))
    return checks


# --- Top level -----------------------------------------------------------

def run_checks(rez_path, eng_path=None, binary=DEFAULT_BINARY,
               timeout=None):
    """Run all checks on a .rez file; return the report dict.

    ``eng_path`` defaults to the side-car next to the .rez file. The
    headless CLI is run once (base schema, no mutations) to get the
    beam radii. Raises :class:`HeadlessError` when the CLI itself
    fails (unloadable schema, bad request); an unstable cavity is
    *not* an error -- its optical checks report ``nodata``.
    """
    if eng_path is None:
        eng_path = eng_path_for(rez_path)
    rez_data = load_rez(rez_path)
    eng_data = load_eng(eng_path)
    warnings = validate_eng(eng_data)

    labels = [e.get("label") for e in elements(rez_data)
              if isinstance(e, dict) and e.get("label") is not None]
    for label in _eng_elements(eng_data):
        if label not in labels:
            warnings.append("side-car lists unknown element %r (not in the "
                            ".rez file); its data was ignored" % (label,))

    out = run_headless_file(rez_path, binary=binary, timeout=timeout)
    result = out["results"][0]
    if not result.get("ok"):
        raise HeadlessError("headless evaluation failed: %s"
                            % result.get("error"))
    beam_list = result.get("beam")
    beam = {b["label"]: b for b in beam_list} if beam_list else {}
    if beam_list is None:
        warnings.append("no beam radii from the headless CLI (unstable "
                        "cavity or ray-vector pump); optical checks report "
                        "nodata")

    checks = (check_lidt(labels, beam, eng_data)
              + check_aperture(labels, beam, eng_data)
              + check_board(labels, eng_data))
    summary = {"ok": 0, "warn": 0, "fail": 0, "nodata": 0}
    for check in checks:
        summary[check["status"]] += 1
    summary["total"] = len(checks)
    return {"version": REPORT_VERSION,
            "rez_path": os.path.abspath(rez_path),
            "eng_path": os.path.abspath(eng_path),
            "checks": checks, "summary": summary, "warnings": warnings}


def main(argv=None):
    """CLI entry: ``run_checks.py <file.rez> [side-car]``.

    Prints the JSON report to stdout. Exit code is 0 whenever a report
    was produced (even with ``fail`` entries -- those are data, not
    errors); non-zero only on hard failures (missing file, CLI error).
    """
    parser = argparse.ArgumentParser(
        description="Run LIDT / aperture / breadboard checks on a .rez file.")
    parser.add_argument("rez_path", help=".rez file to check")
    parser.add_argument("eng_path", nargs="?",
                        help="side-car file (default: <file>.rez.eng.json)")
    parser.add_argument("--binary", default=DEFAULT_BINARY,
                        help="path to the rezonator binary")
    args = parser.parse_args(argv)
    try:
        report = run_checks(args.rez_path, args.eng_path,
                            binary=args.binary)
    except (OSError, ValueError, HeadlessError) as e:
        print("run_checks: %s" % e, file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
