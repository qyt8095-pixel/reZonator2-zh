"""Side-car engineering data (``<file>.rez.eng.json``).

Engineering data (LIDT, apertures, mounts, ...) lives *next to* the
.rez file, not inside it: the application's own writer drops unknown
top-level keys on save, so embedding it in the .rez would silently lose
it. This module only provides the read/write helpers and the file
format placeholder; the concrete per-section schemas (LIDT, aperture,
breadboard, ...) are defined by the later Phase 1 steps.
"""

import json


def eng_path(rez_path):
    """Side-car path for a .rez file: ``<file>.rez.eng.json``."""
    return rez_path + ".eng.json"


def load_eng(path):
    """Load a side-car file; returns ``{}`` when the file does not exist."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}
    if not isinstance(data, dict):
        raise ValueError("%s: top-level JSON value is not an object" % path)
    return data


def save_eng(path, data):
    """Write a side-car file (UTF-8, 4-space indent, keys in order)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.write("\n")


# Minimal format placeholder (versioned; sections are added by later steps).
FORMAT_VERSION = 1


def new_eng():
    """An empty side-car document."""
    return {"format_version": FORMAT_VERSION}
