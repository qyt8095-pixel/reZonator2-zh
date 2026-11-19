#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Command-line entry for the Phase 3 optimizer / Snap.

    python3 run_optimizer.py --config config.json

Config file (JSON)::

    {"rez": "path/to/cavity.rez",
     "variables": [{"label": "d1", "alias": "L",
                    "min_si": 0.30, "max_si": 0.45}],
     "targets": [{"kind": "waist", "element": "M1",
                  "target_mm": 0.12, "weight": 1.0}],
     "constraints": [{"kind": "fixed_total",
                      "members": [["d1", "L"], ["d2", "L"]],
                      "total_si": 0.8417}],
     "de": {"maxiter": 40, "popsize": 10, "seed": 0},
     "nm": {"maxfev": 300},
     "snap": [{"label": "M3", "alias": "R"}],
     "snap_free_lengths": [["d2", "L"], ["d3", "L"]]}

With ``"snap"`` present, the run is a Snap + re-optimisation
instead of a full optimisation. Prints the result as JSON.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng import (load_rez, optimize, snap_and_reoptimize)


def _jsonable(obj):
    if isinstance(obj, dict):
        return {("%s.%s" % k if isinstance(k, tuple) else k): _jsonable(v)
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    return obj


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", required=True, help="JSON config file")
    args = ap.parse_args()
    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    data = load_rez(cfg["rez"])
    variables = cfg["variables"]
    targets = cfg["targets"]
    constraints = None
    if cfg.get("constraints"):
        constraints = []
        for c in cfg["constraints"]:
            c = dict(c)
            if c.get("members"):
                c["members"] = [tuple(m) for m in c["members"]]
            constraints.append(c)
    de = cfg.get("de") or {}
    nm = cfg.get("nm") or {}
    if cfg.get("snap"):
        free_lengths = [tuple(v) for v in
                        cfg.get("snap_free_lengths") or []]
        res = snap_and_reoptimize(
            data, cfg["snap"], variables, targets, free_lengths,
            constraints=constraints,
            nm_maxfev=nm.get("maxfev", 150))
    else:
        res = optimize(
            data, variables, targets, constraints=constraints,
            de_maxiter=de.get("maxiter", 40),
            de_popsize=de.get("popsize", 10),
            de_seed=de.get("seed", 0),
            nm_maxfev=nm.get("maxfev", 300))
    print(json.dumps(_jsonable(res), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
