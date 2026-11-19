"""Command-line entry for the Solves (Phase 1 block 3).

Usage::

    python3 run_solves.py pickup <file.rez> --driven d4:L --source d1:L \\
        --k 0.5 --b 10 [--b-unit mm] [--out OUT | --in-place]
    python3 run_solves.py waist-size <file.rez> --variable d1:L \\
        --element M1 --target 0.12 [--plane T] [--bounds 300:380] \\
        [--apply | --out OUT]
    python3 run_solves.py waist-position <file.rez> --variable d1:L \\
        --element M4 --target 1100 | --target-ref M4:0 [--plane T] \\
        [--bounds 300:380] [--apply | --out OUT]

``--driven`` / ``--source`` / ``--variable`` are ``LABEL:ALIAS``.
``--b`` is in the driven parameter's unit; ``--bounds LO:HI`` is in
the variable's unit (``--bounds-unit`` overrides); ``--target`` for
waist-size is a waist radius in mm, for waist-position an absolute
axial ``s`` in mm (``--target-ref LABEL[:OFFSET]`` positions the
waist relative to an element's plane instead).

Without ``--apply`` / ``--out`` / ``--in-place`` nothing is written:
the result JSON is printed and the input file is untouched. A solve
that does not converge still exits 0 (``converged: false`` is data);
only hard errors (missing file, unknown parameter, CLI failure) exit
non-zero.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rezeng import load_rez, save_rez, to_si
from rezeng.solves import (PickupError, SolveError, apply_pickup,
                           apply_solution, solve_waist_position,
                           solve_waist_size)


def _parse_param(spec):
    if ":" not in spec:
        raise ValueError("parameter must be LABEL:ALIAS, got %r" % spec)
    label, alias = spec.split(":", 1)
    if not label or not alias:
        raise ValueError("parameter must be LABEL:ALIAS, got %r" % spec)
    return (label, alias)


def _parse_bounds(spec, data, variable, unit=None):
    from rezeng import param_unit
    try:
        lo_s, hi_s = spec.split(":", 1)
        lo, hi = float(lo_s), float(hi_s)
    except ValueError:
        raise ValueError("bounds must be LO:HI, got %r" % spec)
    if unit is None:
        unit = param_unit(data, variable[0], variable[1])
    return (to_si(lo, unit), to_si(hi, unit))


def _write(data, args, default_suffix):
    """Write ``data`` per --out/--in-place/--apply; return the path."""
    if getattr(args, "in_place", False) or getattr(args, "apply", False):
        path = args.rez_path
    elif getattr(args, "out", None):
        path = args.out
    else:
        return None
    save_rez(path, data)
    return path


def cmd_pickup(args):
    data = load_rez(args.rez_path)
    driven = _parse_param(args.driven)
    source = _parse_param(args.source)
    info = apply_pickup(data, driven, source, args.k, args.b,
                        b_unit=args.b_unit)
    info["kind"] = "pickup"
    info["driven"] = {"label": driven[0], "alias": driven[1]}
    info["source"] = {"label": source[0], "alias": source[1]}
    path = _write(data, args, ".pickup.rez")
    info["written_to"] = path
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def _cmd_waist(args, solver):
    data = load_rez(args.rez_path)
    variable = _parse_param(args.variable)
    bounds = None
    if args.bounds:
        bounds = _parse_bounds(args.bounds, data, variable,
                               unit=args.bounds_unit)
    kwargs = {"data": data, "variable": variable,
              "element": args.element, "plane": args.plane,
              "bounds_si": bounds}
    if solver is solve_waist_size:
        kwargs["target_w0_mm"] = args.target
    else:
        if args.target_ref is not None:
            parts = args.target_ref.split(":")
            label = parts[0]
            offset = float(parts[1]) if len(parts) > 1 else 0.0
            kwargs["target"] = ("ref", label, offset)
        else:
            kwargs["target"] = args.target
    result = solver(**kwargs)
    if (getattr(args, "apply", False) or getattr(args, "out", None)) \
            and result["converged"] and result["solved_value"] is not None:
        apply_solution(data, variable, result["solved_value"])
        result["written_to"] = _write(data, args, ".solved.rez")
    elif getattr(args, "apply", False) or getattr(args, "out", None):
        result["written_to"] = None
        result["warnings"] = result["warnings"] + [
            "not written: the solve did not converge"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Pickup / waist Solves on a .rez file.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("pickup", help="write a native Pickup into the file")
    p.add_argument("rez_path", help=".rez file")
    p.add_argument("--driven", required=True, help="LABEL:ALIAS (follower)")
    p.add_argument("--source", required=True, help="LABEL:ALIAS (leader)")
    p.add_argument("--k", required=True, type=float,
                   help="dimensionless factor: driven = k*source + b")
    p.add_argument("--b", required=True, type=float,
                   help="offset, in the driven parameter's unit")
    p.add_argument("--b-unit", default=None,
                   help="unit of --b (default: driven parameter's unit)")
    p.add_argument("--out", default=None, help="write result to this file")
    p.add_argument("--in-place", action="store_true",
                   help="modify the input file")
    p.set_defaults(func=cmd_pickup)

    for name, solver, target_help in (
            ("waist-size", solve_waist_size,
             "target waist radius in mm"),
            ("waist-position", solve_waist_position,
             "target absolute axial position s in mm")):
        w = sub.add_parser(name, help="solve a waist quantity")
        w.add_argument("rez_path", help=".rez file")
        w.add_argument("--variable", required=True,
                       help="LABEL:ALIAS to vary")
        w.add_argument("--element", required=True,
                       help="label of the element whose segment is solved")
        w.add_argument("--target", type=float, default=None, help=target_help)
        if name == "waist-position":
            w.add_argument("--target-ref", default=None,
                           help="LABEL[:OFFSET_MM]: waist relative to an "
                                "element's plane (offset > 0 downstream)")
        w.add_argument("--plane", default="T", choices=("T", "S"))
        w.add_argument("--bounds", default=None,
                       help="LO:HI search interval, in the variable's unit")
        w.add_argument("--bounds-unit", default=None,
                       help="unit of --bounds (default: variable's unit)")
        w.add_argument("--apply", action="store_true",
                       help="write the solution back into the input file")
        w.add_argument("--out", default=None,
                       help="write the solved file to this path")
        w.set_defaults(func=lambda args, s=solver: _cmd_waist(args, s))

    args = parser.parse_args(argv)
    if getattr(args, "command", None) == "waist-position" \
            and args.target is None and args.target_ref is None:
        parser.error("waist-position needs --target or --target-ref")
    if getattr(args, "command", None) == "waist-size" \
            and args.target is None:
        parser.error("waist-size needs --target")
    try:
        return args.func(args)
    except (OSError, ValueError, PickupError, SolveError) as e:
        print("run_solves: %s" % e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
