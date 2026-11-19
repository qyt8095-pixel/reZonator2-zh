#!/usr/bin/env python3
"""Export the coating table, .zmx and .dxf for a .rez file.

Usage:
    python3 run_export.py <file.rez> [side-car.eng.json]
        [--coating] [--zmx OUT.zmx] [--dxf OUT.dxf]
        [--thin-lens-check] [--no-ezdxf]

The side-car defaults to ``<file>.rez.eng.json``. See README.md.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng.export import main

if __name__ == "__main__":
    sys.exit(main())
