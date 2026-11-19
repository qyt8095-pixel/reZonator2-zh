#!/usr/bin/env python3
"""Run engineering checks (LIDT / aperture / breadboard) on a .rez file.

Usage:
    python3 run_checks.py <file.rez> [side-car.eng.json]

Prints the JSON report to stdout. Exit code 0 whenever a report was
produced (even with "fail" entries -- those are data, not errors);
non-zero only on hard failures (missing file, headless CLI error).
The side-car defaults to ``<file>.rez.eng.json``. See README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng.checks import main

if __name__ == "__main__":
    sys.exit(main())
