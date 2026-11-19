"""Read/write .rez files (JSON) with full round-trip fidelity.

The parser is deliberately dumb: it loads the whole file as a plain
``dict`` and writes it back unchanged except for the caller's edits.
That guarantees unknown top-level keys, unknown element fields,
``schema_version`` and every parameter's ``unit`` survive a round trip
-- the C++ writer, by contrast, rebuilds the JSON from scratch and
drops unknown keys, so Python must never route a file through it.

Units: values are stored in the parameter's own unit. Use
:func:`rezeng.units.to_si` / :func:`rezeng.units.from_si` to convert;
never assume ``mm``.
"""

import json

from .units import to_si, from_si


def load_rez(path):
    """Load a .rez file, returning the parsed JSON object (a dict).

    The file must be UTF-8 JSON; a ``ValueError`` is raised otherwise.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("%s: top-level JSON value is not an object" % path)
    return data


def save_rez(path, data):
    """Write a .rez file, preserving key order and all unknown fields.

    Numbers are written as-is; ``ensure_ascii=False`` keeps Chinese
    labels readable. The file uses 4-space indentation like the files
    the application itself writes.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        f.write("\n")


def elements(data):
    """The ``elements`` list of a loaded .rez (``[]`` when absent)."""
    elems = data.get("elements")
    return elems if isinstance(elems, list) else []


def element_index(data, label):
    """Index of the first element with the given label, or ``None``.

    Labels are the override key used by the headless CLI, which also
    resolves to the first match.
    """
    for i, elem in enumerate(elements(data)):
        if isinstance(elem, dict) and elem.get("label") == label:
            return i
    return None


def param_obj(data, label, alias):
    """The parameter dict ``{"value", "unit", "expr", "error"}`` for an
    element parameter, or ``None`` when the element/parameter is absent.
    """
    idx = element_index(data, label)
    if idx is None:
        return None
    params = elements(data)[idx].get("params")
    if not isinstance(params, dict):
        return None
    param = params.get(alias)
    return param if isinstance(param, dict) else None


def param_unit(data, label, alias):
    """The unit alias of an element parameter (``None`` when absent)."""
    param = param_obj(data, label, alias)
    return param.get("unit") if param else None


def param_value_si(data, label, alias):
    """An element parameter's value converted to SI (``None`` when absent)."""
    param = param_obj(data, label, alias)
    if param is None:
        return None
    return to_si(param.get("value"), param.get("unit"))


def set_param_value(data, label, alias, value, unit=None):
    """Set an element parameter's value, keeping its original unit.

    ``value`` is interpreted in ``unit`` (default: the parameter's own
    unit as stored in the file). The ``unit`` field itself is never
    changed, and neither are ``expr`` / ``error``.
    """
    param = param_obj(data, label, alias)
    if param is None:
        raise KeyError("no parameter %s.%s" % (label, alias))
    if unit is None:
        unit = param.get("unit")
    param["value"] = from_si(to_si(value, unit), param.get("unit"))


def check_overridable(data, label, alias):
    """Check whether an element parameter may be overridden externally.

    Returns ``None`` when it is freely overridable, otherwise a short
    conflict description. A parameter is *not* overridable when it is
    driven by the file's own machinery:

    * ``param_links``: an entry with matching ``target_elem`` (index) and
      ``target_param`` copies a global parameter into it on load;
    * ``formulas``: they drive *global* parameters only, so an element
      parameter is never directly formula-driven -- but a formula driving
      the global source of a link is still caught by the link check.

    Note: an element parameter's ``expr`` field is only the literal text
    the user typed in the editor (evaluated in the ParamEditor UI, never
    on load); it does not drive the value and is not checked here. The
    C++ CLI applies the same rule via ``Z::Parameter::valueDriver()``.
    """
    idx = element_index(data, label)
    if idx is None:
        return "unknown element %r" % (label,)
    if param_obj(data, label, alias) is None:
        return "unknown parameter %r on element %r" % (alias, label)
    for link in data.get("param_links") or []:
        if not isinstance(link, dict):
            continue
        if link.get("target_elem") == idx and link.get("target_param") == alias:
            return ("parameter %s.%s is driven by a link from global "
                    "parameter %r" % (label, alias, link.get("source_param")))
    return None
