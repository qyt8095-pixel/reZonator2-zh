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

__all__ = [
    "load_rez", "save_rez", "check_overridable", "param_unit",
    "to_si", "from_si", "UnitError",
    "load_eng", "save_eng", "new_eng", "eng_path", "validate_eng",
    "run_headless", "run_headless_file", "HeadlessError",
    "run_checks", "lidt_fluence_J_per_cm2", "aperture_loss_fraction",
    "combined_loss", "LIDT_WARN_RATIO", "LIDT_FAIL_RATIO",
    "APERTURE_WARN_SINGLE", "APERTURE_WARN_TOTAL", "BOARD_GRID_TOL_MM",
]
