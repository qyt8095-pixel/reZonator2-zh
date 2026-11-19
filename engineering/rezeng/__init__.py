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
from .shg import (SHGError, MATERIALS, material_reference, fill_typical,
                  resolve_shg, boyd_kleinman_h, aperture_length,
                  focusing_parameter, shg_coefficient_K, single_pass_eta,
                  shg_beam_in_crystal, shg_K_for_point, shg_output_beam,
                  green_noise_assessment, gamma_round_trip,
                  solve_shg_intracavity, solve_shg_extracavity,
                  shg_pump_scan, insert_crystal_element, EPS0)
from .jones import (JonesError, rotation_matrix, retarder_matrix,
                    half_wave_plate, quarter_wave_plate, polarizer_matrix,
                    mirror_matrix, matrix_from_spec, build_sequence,
                    round_trip_jones, eigen_polarization,
                    polarization_loss, jones_report)
from .dispersion import (DispersionError, round_trip_dispersion,
                         dispersion_report)
from .mopa import (MOPAError, B_WARN_RAD, fn_pass, ring_grid,
                   fluence_profile, resolve_chain, run_chain)
from .merit import (MeritError, PENALTY_UNSTABLE, PENALTY_BASE,
                    PENALTY_SLOPE, validate_targets, evaluate_result,
                    evaluate_batch)
from .optimizer import (OptimizerError, BatchEvaluator, optimize,
                        optimize_with_discrete, MIN_LENGTH_SI, TIE_TOL)
from .zones import ZoneError, scan_zones, BRENT_XTOL
from .catalog import (CatalogError, STOCK_CATALOG, load_catalog_csv,
                      dioptric, dioptric_distance, snap_radius,
                      snap_and_reoptimize)
from .montecarlo import (MonteCarloError, wilson_interval,
                         sample_perturbations, run_montecarlo,
                         DEFAULT_CHUNK_SIZE)
from .reverse import (ReverseError, output_mirror_q, model_spot,
                      working_zone_bounds, fit_plane, fit_thermal_lens,
                      synthetic_measurements)
from .jacobian import (JacobianError, mirror_labels, roundtrip_list,
                       jacobian_analytic, jacobian_finite_difference,
                       compare_jacobians, screw_turns, direction_table,
                       tilt_to_screws, solve_correction, recenter_guide,
                       FD_STEP_RAD, JACOBIAN_TOL, TPI_PITCH_MM)
from .ghosts import (GhostError, ETALON_MIN_RR, GHOST_MIN_R,
                     MODULATION_WARN, WAIST_TOL_ZR, etalon_fsr_Hz,
                     etalon_modulation, reflect_q,
                     plate_lateral_offset_mm, divergence_mrad,
                     build_chain, build_surfaces, surface_angle_mrad,
                     build_roundtrip_items, scan_etalons, trace_ghost,
                     scan_ghosts, MATERIAL_TYPES)
from .redlight import (RedlightError, RED_NM, COLD_F_MM,
                       DEFAULT_W0_MM, SELLMEIER, MATERIAL_ALIASES,
                       material_index, element_material, cold_schema,
                       trace_injected, redlight_report)
from .export import (ExportError, LIDT_SAFETY_FACTOR, coating_table,
                     to_zmx, validate_zmx, thin_lens_spot_check,
                     to_dxf, validate_dxf)

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
    "toc_scan", "H_PLANCK", "C_LIGHT",
    "SHGError", "MATERIALS", "material_reference", "fill_typical",
    "resolve_shg", "boyd_kleinman_h", "aperture_length",
    "focusing_parameter", "shg_coefficient_K", "single_pass_eta",
    "shg_beam_in_crystal", "shg_K_for_point", "shg_output_beam",
    "green_noise_assessment", "gamma_round_trip",
    "solve_shg_intracavity", "solve_shg_extracavity",
    "shg_pump_scan", "insert_crystal_element", "EPS0",
    "JonesError", "rotation_matrix", "retarder_matrix",
    "half_wave_plate", "quarter_wave_plate", "polarizer_matrix",
    "mirror_matrix", "matrix_from_spec", "build_sequence",
    "round_trip_jones", "eigen_polarization",
    "polarization_loss", "jones_report",
    "DispersionError", "round_trip_dispersion", "dispersion_report",
    "MOPAError", "B_WARN_RAD", "fn_pass", "ring_grid",
    "fluence_profile", "resolve_chain", "run_chain",
    "MeritError", "PENALTY_UNSTABLE", "PENALTY_BASE",
    "PENALTY_SLOPE", "validate_targets", "evaluate_result",
    "evaluate_batch",
    "OptimizerError", "BatchEvaluator", "optimize",
    "optimize_with_discrete", "MIN_LENGTH_SI", "TIE_TOL",
    "ZoneError", "scan_zones", "BRENT_XTOL",
    "CatalogError", "STOCK_CATALOG", "load_catalog_csv",
    "dioptric", "dioptric_distance", "snap_radius",
    "snap_and_reoptimize",
    "MonteCarloError", "wilson_interval",
    "sample_perturbations", "run_montecarlo",
    "DEFAULT_CHUNK_SIZE",
    "ReverseError", "output_mirror_q", "model_spot",
    "working_zone_bounds", "fit_plane", "fit_thermal_lens",
    "synthetic_measurements",
    "JacobianError", "mirror_labels", "roundtrip_list",
    "jacobian_analytic", "jacobian_finite_difference",
    "compare_jacobians", "screw_turns", "direction_table",
    "tilt_to_screws", "solve_correction", "recenter_guide",
    "FD_STEP_RAD", "JACOBIAN_TOL", "TPI_PITCH_MM",
    "GhostError", "ETALON_MIN_RR", "GHOST_MIN_R",
    "MODULATION_WARN", "WAIST_TOL_ZR", "etalon_fsr_Hz",
    "etalon_modulation", "reflect_q",
    "plate_lateral_offset_mm", "divergence_mrad",
    "build_chain", "build_surfaces", "surface_angle_mrad",
    "build_roundtrip_items", "scan_etalons", "trace_ghost",
    "scan_ghosts", "MATERIAL_TYPES",
    "RedlightError", "RED_NM", "COLD_F_MM",
    "DEFAULT_W0_MM", "SELLMEIER", "MATERIAL_ALIASES",
    "material_index", "element_material", "cold_schema",
    "trace_injected", "redlight_report",
    "ExportError", "LIDT_SAFETY_FACTOR", "coating_table",
    "to_zmx", "validate_zmx", "thin_lens_spot_check",
    "to_dxf", "validate_dxf",
]
