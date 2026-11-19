"""Demo: full ODR report on the user's real cavity.

Merges the example side-car sections of Phases 1-4 into one demo
side-car (ALL parameters are EXAMPLES, labelled in each source file),
then builds the complete ODR report -- envelope, zones, Monte Carlo,
thermal + fracture, Fox-Li, ghosts, red light, coating BOM, CAD/Zemax
export checks -- and writes it to /tmp/demo-phase4-odr.html.

Fox-Li is included (slow: tens of seconds); Monte Carlo uses N=250 to
keep the demo quick (the ODR default is N=1000).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))

from rezeng.odr import build_odr_report

USER_REZ = "/home/hatch/workspace/user/files/upload.rez"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_ENG = "/tmp/demo-phase4-odr.eng.json"
OUT_HTML = "/tmp/demo-phase4-odr.html"

SOURCES = [
    "tests/data/example-phase4.eng.json",
    "tests/data/example-thermal.eng.json",
    "tests/data/example-mc.eng.json",
    "tests/data/example-foxli.eng.json",
]


def _deep_merge(dst, src):
    for key, value in src.items():
        if (key in dst and isinstance(dst[key], dict)
                and isinstance(value, dict)):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value
    return dst


def main():
    eng = {}
    for name in SOURCES:
        with open(os.path.join(HERE, name), encoding="utf-8") as fh:
            _deep_merge(eng, json.load(fh))
    eng["notes"] = (
        "ODR demo side-car: merged EXAMPLE sections from Phases 1-4. "
        "All laser/crystal/pump/tolerance/coating numbers are INVENTED "
        "for the demo, NOT the user's real parameters.")
    with open(OUT_ENG, "w", encoding="utf-8") as fh:
        json.dump(eng, fh, indent=2, ensure_ascii=False)
    print("merged demo side-car: %s" % OUT_ENG)
    report = build_odr_report(
        USER_REZ, eng=eng, include_foxli=True, mc_n=250,
        pump_powers=(2.0, 5.0, 10.0), example_params=True,
        out_html=OUT_HTML)
    print("ODR: %d/%d sections ok -> %s"
          % (report["n_ok"], report["n_sections"], OUT_HTML))
    for sec in report["sections"]:
        print("  %-10s %-5s %s" % (sec["id"], sec["status"], sec["note"]))
    if report["validation_problems"]:
        print("side-car validation problems:")
        for problem in report["validation_problems"]:
            print("  - %s" % problem)
    return 0


if __name__ == "__main__":
    sys.exit(main())
