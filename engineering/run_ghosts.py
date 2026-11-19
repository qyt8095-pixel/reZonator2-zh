#!/usr/bin/env python3
"""Run the ghost / parasitic-etalon scan on a .rez file.

Usage:
    python3 run_ghosts.py <file.rez> [side-car.eng.json]
        [--wavelength NM]

Prints the JSON report to stdout. Exit code 0 whenever a report was
produced (even with "fail" entries -- those are data, not errors);
non-zero only on hard failures (missing file, headless CLI error).
The side-car defaults to ``<file>.rez.eng.json``. See README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng.ghosts import main

if __name__ == "__main__":
    sys.exit(main())
