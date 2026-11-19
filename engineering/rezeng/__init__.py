"""reZonator engineering layer (Phase 1): .rez parsing, units, headless CLI.

Only the standard library is used (numpy/scipy are not needed here).
The .rez format is JSON; this package reads/writes it while preserving
everything it does not understand: unknown top-level keys, unknown element
fields, ``schema_version`` and every parameter's ``unit``.
"""

from .rez import load_rez, save_rez, check_overridable, param_unit
from .units import to_si, from_si, UnitError
from .eng import load_eng, save_eng, new_eng, eng_path, validate_eng
from .cli import run_headless, run_headless_file, HeadlessError
from .checks import (run_checks, lidt_fluence_J_per_cm2,
                     aperture_loss_fraction, combined_loss,
                     LIDT_WARN_RATIO, LIDT_FAIL_RATIO,
                     APERTURE_WARN_SINGLE, APERTURE_WARN_TOTAL,
                     BOARD_GRID_TOL_MM)
from .solves import (PickupError, SolveError, apply_pickup, find_pickup,
                     verify_pickup, solve_waist_size, solve_waist_position,
                     apply_solution, waist_from_wr,
                     element_plane_position_mm, total_length_mm,
                     wavelength_nm)
from .qevolve import (QevolveError, solve_n2, grin_gamma, calc_focus,
                      q_from_wr, wr_from_q, waist_from_q,
                      element_grin_params, find_gain_element, beam_entry,
                      entrance_entry, element_matrix, evolve_element,
                      crystal_slices)
from .power import (PowerError, resolve_params, param_F_current,
                    overlap_eta_mode, mean_mode_radius, mode_a_threshold,
                    mode_a_output, pump_radius, overlap_integral,
                    solve_p_circ, small_signal_gain, analytic_overlap,
                    higher_order_gains, two_mode_m2, multimode_threshold,
                    thermal_kappa, thermal_focal_lengths, pump_scan,
                    toc_scan, H_PLANCK, C_LIGHT)

__all__ = [
    "load_rez", "save_rez", "check_overridable", "param_unit",
    "to_si", "from_si", "UnitError",
    "load_eng", "save_eng", "new_eng", "eng_path", "validate_eng",
    "run_headless", "run_headless_file", "HeadlessError",
    "run_checks", "lidt_fluence_J_per_cm2", "aperture_loss_fraction",
    "combined_loss", "LIDT_WARN_RATIO", "LIDT_FAIL_RATIO",
    "APERTURE_WARN_SINGLE", "APERTURE_WARN_TOTAL", "BOARD_GRID_TOL_MM",
    "PickupError", "SolveError", "apply_pickup", "find_pickup",
    "verify_pickup", "solve_waist_size", "solve_waist_position",
    "apply_solution", "waist_from_wr",
    "element_plane_position_mm", "total_length_mm",
    "wavelength_nm",
    "QevolveError", "solve_n2", "grin_gamma", "calc_focus",
    "q_from_wr", "wr_from_q", "waist_from_q",
    "element_grin_params", "find_gain_element", "beam_entry",
    "entrance_entry", "element_matrix", "evolve_element",
    "crystal_slices",
    "PowerError", "resolve_params", "param_F_current",
    "overlap_eta_mode", "mean_mode_radius", "mode_a_threshold",
    "mode_a_output", "pump_radius", "overlap_integral",
    "solve_p_circ", "small_signal_gain", "analytic_overlap",
    "higher_order_gains", "two_mode_m2", "multimode_threshold",
    "thermal_kappa", "thermal_focal_lengths", "pump_scan",
    "toc_scan", "H_PLANCK", "C_LIGHT", "ETA_Q_MAX",
]
