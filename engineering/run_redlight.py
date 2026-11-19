#!/usr/bin/env python3
"""Run the 632.8 nm red-light comparison on a .rez file.

Usage:
    python3 run_redlight.py <file.rez> [side-car.eng.json]
        [--red-nm NM] [--w0 MM] [--double-pass]

Prints the JSON report to stdout. Exit code 0 whenever a report was
produced; non-zero only on hard failures (missing file, headless
CLI error). The side-car defaults to ``<file>.rez.eng.json``.
See README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng.redlight import main

if __name__ == "__main__":
    sys.exit(main())
