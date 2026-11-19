"""Unit conversion for .rez parameter values.

The .rez format stores each parameter's unit as the C++ unit *alias*
(see ``JsonUtils::writeValue``: ``json["unit"] = unit->alias()``), e.g.
``"mm"``, ``"mkm"`` (micrometre, displayed as µm), ``"deg"``.
All conversion here is to/from SI (metre, radian, ...).

Only the units seen in real files are guaranteed; unknown units raise
:class:`UnitError` instead of being silently guessed.
"""

# alias -> (dimension, factor to SI). "none" and inverse units have factor 1.
_FACTORS = {
    # length
    "nm": ("length", 1e-9),
    "mkm": ("length", 1e-6),   # micrometre, alias "mkm", name "µm"
    "µm": ("length", 1e-6),    # tolerated spelling
    "um": ("length", 1e-6),    # tolerated spelling
    "mm": ("length", 1e-3),
    "cm": ("length", 1e-2),
    "m": ("length", 1.0),
    # angle
    "mrad": ("angle", 1e-3),
    "rad": ("angle", 1.0),
    "deg": ("angle", 3.14159265358979323846 / 180.0),
    "amin": ("angle", 3.14159265358979323846 / 180.0 / 60.0),
    # dimensionless / already SI-like
    "none": ("none", 1.0),
    "percent": ("none", 0.01),
    "inv_m": ("inv_length", 1.0),
    "inv_m2": ("inv_area", 1.0),
    "inv_m3": ("inv_volume", 1.0),
    "Hz": ("frequency", 1.0),
}


class UnitError(ValueError):
    """Raised when a unit string is unknown or unusable."""


def dimension(unit):
    """Dimension name for a unit alias (``"length"``, ``"angle"``, ...)."""
    try:
        return _FACTORS[unit][0]
    except KeyError:
        raise UnitError("unknown unit %r" % (unit,))


def to_si(value, unit):
    """Convert ``value`` given in ``unit`` to SI."""
    try:
        return float(value) * _FACTORS[unit][1]
    except KeyError:
        raise UnitError("unknown unit %r" % (unit,))


def from_si(value_si, unit):
    """Convert an SI ``value_si`` to ``unit``."""
    try:
        return float(value_si) / _FACTORS[unit][1]
    except KeyError:
        raise UnitError("unknown unit %r" % (unit,))
