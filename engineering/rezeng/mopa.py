"""MOPA / regenerative amplifier chain (Phase 2 block 3).

Data model (side-car ``mopa_chain`` on the oscillator file; per the
Gemini Phase 2 review, section 6)::

    "mopa_chain": {
      "seed_source": {"type": "oscillator_ref",
                      "pulse_energy_J": 5e-5,
                      "pulse_duration_s": 40e-12,
                      "rep_rate_Hz": 120000},
      "stages": [
        {"stage_id": "amp_1", "rez_file": "amp1_sp.rez", "passes": 2,
         "gain_element": "CRY",
         "gain_medium": {"material": "Nd:YVO4",
                         "J_sat_J_per_cm2": 0.12,
                         "small_signal_gain_G0": 4.5,
                         "recovery_time_us": 90,
                         "n2_m2_per_W": 1.0e-19},
         "loss_per_pass": 0.0},
        {"stage_id": "regen_1", "rez_file": "regen_sw.rez", "passes": 10,
         "gain_element": "CRY",
         "gain_medium": {"material": "Nd:YAG",
                         "J_sat_J_per_cm2": 0.66,
                         "initial_stored_energy_J": 0.005},
         "round_trip_loss": 0.04}
      ]
    }

Zero C++ changes: each stage is an existing .rez file (SP for a
single-pass amplifier, SW for a regenerative amplifier); the beam
radii at the gain element come from one ``--headless`` call per stage.

Per transit the pulse energy is converted to a radial fluence
profile ``J_in(r) = [2 E_in / (pi w_eff^2)] exp(-2 r^2 / w_eff^2)``
with the area-equivalent radius ``w_eff = sqrt(w_T w_S)``, and the
Frantz-Nodvik equation is applied per radial ring::

    J_out(r) = J_sat ln[1 + G_0(r) (exp(J_in(r)/J_sat) - 1)]

Stored-energy bookkeeping is done **per ring**: each ring carries its
own small-signal gain exponent ``gamma_i = ln G_0(r_i)``, depleted
locally by the extracted fluence,
``gamma_i <- gamma_i - (J_out,i - J_in,i) / J_sat`` (clamped at 0).
Since ``0 <= J_out - J_in <= J_sat * gamma`` per ring (the
Frantz-Nodvik extraction is monotone in ``J_in`` and saturates at
``J_sat * gamma``), the remaining stored energy never goes negative
and the chain can never output more than seed + stored energy --
no perpetual-motion machine. A scalar mode-area bookkeeping would
leak energy for intense Gaussian beams (the extraction region grows
logarithmically with peak fluence), so the ring-local rule is used
instead. The reported ``stored_J`` is the ring-integrated total
(``sum J_sat * gamma_i * A_ring``) over the modelled aperture
(``r <= 3 w_eff``); the mode-area value ``J_sat * pi * w_T * w_S *
ln G_0`` is reported alongside for comparison. Rings are
Gauss-Legendre nodes in ``u = r^2`` (see :func:`ring_grid`).

Transit accounting: an SP stage makes one transit per pass; an SW
(regenerative) stage makes **two** transits per round trip, with
``round_trip_loss`` applied between round trips (not after the last
one). ``loss_per_pass`` (SP stages) is applied between passes.
Intra-pulse repumping is neglected (pass spacing << tau_f);
``recovery_time_us`` is recorded for the inter-pulse budget and does
not affect a single-pulse chain.

B integral: after each transit, ``B = (2 pi / lambda) n_2 I_pk L``
with the Gaussian-temporal-profile peak power ``P_pk =
sqrt(4 ln 2 / pi) E_out / tau`` and the spatial peak intensity
``I_pk = 2 P_pk / (pi w_T w_S)`` (``E_out`` of the transit,
conservative). ``B > 3`` rad cumulated warns of self-focusing /
spectral distortion. ``n_2`` comes from the gain medium; without it
(or without a pulse duration) ``B`` is skipped, not invented.

Each transit exit is checked against the gain element's LIDT from
the *stage* side-car (``<stage>.rez.eng.json``), reusing
:func:`rezeng.checks.lidt_fluence_J_per_cm2` at the transit's output
energy (conservative); missing LIDT data reports ``nodata``.
"""

import math
import os

import numpy as np

from .checks import classify_lidt, lidt_fluence_J_per_cm2
from .cli import DEFAULT_BINARY, run_headless_file
from .qevolve import QevolveError, beam_entry
from .rez import element_index, load_rez, param_value_si

#: Warn when the cumulated B integral exceeds this (rad).
B_WARN_RAD = 3.0

#: Radial rings are uniform in ``u = r^2`` out to this multiple of w.
R_MAX_W = 3.0

#: Default number of equal-area radial rings.
DEFAULT_N_RINGS = 64

#: Gaussian temporal profile: P_pk = sqrt(4 ln 2 / pi) * E / tau_FWHM.
GAUSS_PEAK_FACTOR = math.sqrt(4.0 * math.log(2.0) / math.pi)


class MOPAError(ValueError):
    """Raised when a MOPA chain cannot be set up."""


# --- Frantz-Nodvik on rings ---------------------------------------------------

def fn_pass(J_in, G0, J_sat):
    """Frantz-Nodvik output fluence for input fluence array ``J_in``.

    ``J_out = J_sat * ln[1 + G0 (exp(J_in/J_sat) - 1)]``, evaluated
    stably: ``log1p(G0 * expm1(x))`` for ``x <= 50``, else the
    asymptote ``x + ln G0``. ``G0 = 1`` returns ``J_in`` exactly (up
    to round-off); ``J_in >> J_sat`` gives ``J_out -> J_in + J_sat ln
    G0`` per point.
    """
    J_in = np.asarray(J_in, dtype=float)
    if not np.all(np.isfinite(J_in)) or np.any(J_in < 0):
        raise MOPAError("input fluence must be finite and non-negative")
    if G0 < 1.0 or not math.isfinite(G0):
        raise MOPAError("small-signal gain G0 must be >= 1, got %r"
                        % (G0,))
    if J_sat <= 0 or not math.isfinite(J_sat):
        raise MOPAError("J_sat must be positive, got %r" % (J_sat,))
    x = J_in / J_sat
    # np.where evaluates both branches, so clip the expm1 argument to
    # avoid an overflow warning on the discarded branch.
    y = np.where(x > 50.0, x + math.log(G0),
                 np.log1p(G0 * np.expm1(np.minimum(x, 50.0))))
    return J_sat * y


def ring_grid(w_eff_m, n_rings=DEFAULT_N_RINGS):
    """Radial rings on ``u = r^2`` out to ``3 w_eff``.

    Gauss-Legendre nodes/weights on ``[0, (3 w_eff)^2]``; the ring
    area is ``pi * weight``. The grid reconstructs the input Gaussian
    energy to ~1.5e-8 with the default 64 rings (the floor is the
    Gaussian tail beyond 3 w, not quadrature error; a midpoint grid
    would need ~500 rings for the same accuracy on the steep
    ``exp(-2u/w^2)`` profile).
    """
    if w_eff_m <= 0:
        raise MOPAError("effective beam radius must be positive, got %r"
                        % (w_eff_m,))
    x, w = np.polynomial.legendre.leggauss(n_rings)
    u_max = (R_MAX_W * w_eff_m) ** 2
    u_c = 0.5 * u_max * (x + 1.0)
    areas = math.pi * 0.5 * u_max * w
    return u_c, areas


def fluence_profile(E_J, w_eff_m, u_centres_m2):
    """``J_in(r) = [2 E / (pi w^2)] exp(-2 u / w^2)`` on the rings."""
    return (2.0 * E_J / (math.pi * w_eff_m ** 2)) * np.exp(
        -2.0 * u_centres_m2 / w_eff_m ** 2)


# --- Side-car parsing -----------------------------------------------------------

def _pos(value, what):
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) > 0):
        return float(value)
    raise MOPAError("%s must be a positive number, got %r" % (what, value))


def _nonneg(value, what):
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and float(value) >= 0):
        return float(value)
    raise MOPAError("%s must be a non-negative number, got %r"
                    % (what, value))


def _frac(value, what):
    if (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(float(value)) and 0.0 <= float(value) < 1.0):
        return float(value)
    raise MOPAError("%s must be a fraction in [0, 1), got %r"
                    % (what, value))


def _wavelength_nm(data):
    builtin = data.get("builtin_params") or {}
    lam = builtin.get("lambda") if isinstance(builtin, dict) else None
    if isinstance(lam, dict):
        from .units import to_si
        try:
            return to_si(lam.get("value"), lam.get("unit")) * 1e9
        except (TypeError, ValueError):
            pass
    return None


def resolve_chain(eng):
    """Validate ``mopa_chain`` from a side-car dict; return the
    normalised chain (SI units). Raises :class:`MOPAError` naming the
    missing/invalid field -- nothing is invented."""
    chain = (eng or {}).get("mopa_chain")
    if not isinstance(chain, dict):
        raise MOPAError("side-car has no 'mopa_chain' section")
    seed = chain.get("seed_source")
    if not isinstance(seed, dict):
        raise MOPAError("mopa_chain.seed_source is not an object")
    seed_E = _pos(seed.get("pulse_energy_J"),
                  "mopa_chain.seed_source.pulse_energy_J")
    seed_tau = seed.get("pulse_duration_s")
    if seed_tau is not None:
        seed_tau = _pos(seed_tau,
                        "mopa_chain.seed_source.pulse_duration_s")
    rep_rate = seed.get("rep_rate_Hz")
    if rep_rate is not None:
        rep_rate = _pos(rep_rate, "mopa_chain.seed_source.rep_rate_Hz")
    stages = chain.get("stages")
    if not isinstance(stages, list) or not stages:
        raise MOPAError("mopa_chain.stages must be a non-empty list")
    out_stages = []
    for i, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise MOPAError("mopa_chain.stages[%d] is not an object" % i)
        stage_id = stage.get("stage_id")
        if not isinstance(stage_id, str) or not stage_id:
            raise MOPAError("mopa_chain.stages[%d].stage_id must be a "
                            "non-empty string" % i)
        rez_file = stage.get("rez_file")
        if not isinstance(rez_file, str) or not rez_file:
            raise MOPAError("stage %r: rez_file must be a non-empty "
                            "string" % stage_id)
        passes = stage.get("passes")
        if (not isinstance(passes, int) or isinstance(passes, bool)
                or passes < 1):
            raise MOPAError("stage %r: passes must be a positive "
                            "integer, got %r" % (stage_id, passes))
        medium = stage.get("gain_medium")
        if not isinstance(medium, dict):
            raise MOPAError("stage %r: gain_medium is not an object"
                            % stage_id)
        J_sat_cm2 = _pos(medium.get("J_sat_J_per_cm2"),
                         "stage %r gain_medium.J_sat_J_per_cm2" % stage_id)
        G0 = medium.get("small_signal_gain_G0")
        if G0 is not None:
            if (not isinstance(G0, (int, float))
                    or isinstance(G0, bool) or not math.isfinite(float(G0))
                    or float(G0) < 1.0):
                raise MOPAError(
                    "stage %r: small_signal_gain_G0 must be >= 1, got %r"
                    % (stage_id, G0))
            G0 = float(G0)
        E_stored = medium.get("initial_stored_energy_J")
        if E_stored is not None:
            E_stored = _nonneg(
                E_stored,
                "stage %r gain_medium.initial_stored_energy_J" % stage_id)
        if G0 is None and E_stored is None:
            raise MOPAError(
                "stage %r: gain_medium needs small_signal_gain_G0 or "
                "initial_stored_energy_J" % stage_id)
        n2 = medium.get("n2_m2_per_W")
        if n2 is not None:
            n2 = _nonneg(n2, "stage %r gain_medium.n2_m2_per_W" % stage_id)
        tau_rec = medium.get("recovery_time_us")
        if tau_rec is not None:
            tau_rec = _pos(
                tau_rec,
                "stage %r gain_medium.recovery_time_us" % stage_id)
        rt_loss = stage.get("round_trip_loss")
        rt_loss = 0.0 if rt_loss is None else _frac(
            rt_loss, "stage %r round_trip_loss" % stage_id)
        pp_loss = stage.get("loss_per_pass")
        pp_loss = 0.0 if pp_loss is None else _frac(
            pp_loss, "stage %r loss_per_pass" % stage_id)
        out_stages.append({
            "stage_id": stage_id, "rez_file": rez_file,
            "passes": passes,
            "gain_element": stage.get("gain_element"),
            "material": medium.get("material"),
            "J_sat_J_per_cm2": J_sat_cm2,
            "small_signal_gain_G0": G0,
            "initial_stored_energy_J": E_stored,
            "recovery_time_us": tau_rec,
            "n2_m2_per_W": n2,
            "round_trip_loss": rt_loss,
            "loss_per_pass": pp_loss,
        })
    return {"seed": {"type": seed.get("type", "energy"),
                     "pulse_energy_J": seed_E,
                     "pulse_duration_s": seed_tau,
                     "rep_rate_Hz": rep_rate},
            "stages": out_stages}


def _stage_spot(stage_rez_path, gain_label, binary, timeout):
    """Beam radii at the gain element of a stage file, via one
    headless call. Returns ``(w_T_mm, w_S_mm, lambda_nm, L_mm, data)``
    with ``L_mm`` the gain element's physical length (``None`` when
    the element has no ``L`` parameter)."""
    data = load_rez(stage_rez_path)
    out = run_headless_file(stage_rez_path, binary=binary, timeout=timeout)
    result = out["results"][0]
    if not result.get("ok"):
        raise MOPAError("headless evaluation of stage file %r failed: %s"
                        % (stage_rez_path, result.get("error")))
    try:
        w_T, w_S, _RT, _RS = beam_entry(result, gain_label)
    except QevolveError as e:
        raise MOPAError("stage file %r: %s" % (stage_rez_path, e))
    lam_nm = _wavelength_nm(data)
    L_m = param_value_si(data, gain_label, "L")
    return w_T, w_S, lam_nm, (L_m * 1e3 if L_m is not None else None), data


def _find_gain_element(data, stage):
    """Gain element label: explicit ``gain_element`` first, else the
    first ElemPlate, else the first ElemThermoLens."""
    label = stage.get("gain_element")
    if label is not None:
        if element_index(data, label) is None:
            raise MOPAError("stage %r: gain_element %r not found in %r"
                            % (stage["stage_id"], label,
                               stage["rez_file"]))
        return label
    for want in ("ElemPlate", "ElemThermoLens"):
        for elem in data.get("elements") or []:
            if isinstance(elem, dict) and elem.get("type") == want:
                return elem.get("label")
    raise MOPAError("stage %r: no gain_element given and no ElemPlate / "
                    "ElemThermoLens found in %r"
                    % (stage["stage_id"], stage["rez_file"]))


# --- Chain run -------------------------------------------------------------------

def run_chain(osc_rez_path, eng=None, binary=DEFAULT_BINARY,
              timeout=None, n_rings=DEFAULT_N_RINGS, eng_file=None):
    """Run a MOPA chain; return the report dict.

    ``eng`` is a side-car path or an already-loaded side-car dict
    (default: the oscillator's side-car). Stage ``rez_file`` paths
    resolve relative to the side-car file's directory when one is
    known (``eng_file``, or the ``eng`` path itself), otherwise
    relative to the oscillator file's directory. The report carries
    per-transit records, per-stage summaries, chain totals and
    warnings. Raises :class:`MOPAError` on setup problems (missing
    data, unloadable stage file, unstable stage cavity); a chain that
    runs always produces a report, even when the gain is exhausted
    (``G0 = 1`` transits) or the B integral warns.
    """
    from .eng import eng_path as eng_path_for, load_eng

    if eng is None:
        eng = eng_path_for(osc_rez_path)
    if isinstance(eng, dict):
        eng_dict = eng
    else:
        eng_file = eng_file or eng
        eng_dict = load_eng(eng)
    osc_data = load_rez(osc_rez_path)
    chain = resolve_chain(eng_dict)
    if eng_file is not None:
        base_dir = os.path.dirname(os.path.abspath(eng_file))
    else:
        base_dir = os.path.dirname(os.path.abspath(osc_rez_path))
    osc_lam_nm = _wavelength_nm(osc_data)

    warnings = []
    E = chain["seed"]["pulse_energy_J"]
    tau_s = chain["seed"]["pulse_duration_s"]
    B_total = 0.0
    stages_out = []
    E_seed = E
    for stage in chain["stages"]:
        stage_path = stage["rez_file"]
        if not os.path.isabs(stage_path):
            stage_path = os.path.join(base_dir, stage_path)
        if not os.path.exists(stage_path):
            raise MOPAError("stage %r: file not found: %s"
                            % (stage["stage_id"], stage_path))
        stage_data = load_rez(stage_path)
        gain_label = _find_gain_element(stage_data, stage)
        trip = str(stage_data.get("trip_type") or "SP").upper()
        if trip not in ("SP", "SW"):
            raise MOPAError("stage %r: trip_type %r not supported for "
                            "MOPA stages (use SP or SW)" % (stage["stage_id"], trip))
        w_T_mm, w_S_mm, lam_nm, L_mm, _d = _stage_spot(
            stage_path, gain_label, binary, timeout)
        if lam_nm is None:
            lam_nm = osc_lam_nm
        if lam_nm is None:
            raise MOPAError("stage %r: no wavelength (neither the stage "
                            "nor the oscillator file states one)"
                            % stage["stage_id"])
        w_eff_m = math.sqrt(w_T_mm * w_S_mm) * 1e-3
        A_eff_m2 = math.pi * w_T_mm * w_S_mm * 1e-6
        J_sat = stage["J_sat_J_per_cm2"] * 1e4  # J/cm^2 -> J/m^2
        u_c, areas = ring_grid(w_eff_m, n_rings)
        # --- initial stored energy ---
        # Convention: initial_stored_energy_J is the energy stored in
        # the *mode volume* (J_sat * A_eff * ln G0); the ring model
        # spreads the same uniform gain exponent over the modelled
        # aperture (r <= 3 w), so the ring-integrated total is larger
        # (the pumped region is bigger than the mode) -- that is
        # physical, and the per-ring depletion keeps the bookkeeping
        # exact either way.
        G0 = stage["small_signal_gain_G0"]
        E_stored_given = stage["initial_stored_energy_J"]
        if G0 is not None:
            gamma0 = math.log(G0)
            E_stored_mode = J_sat * gamma0 * A_eff_m2
            if E_stored_given is not None:
                rel = abs(E_stored_given - E_stored_mode) \
                    / max(E_stored_mode, 1e-30)
                if rel > 0.05:
                    warnings.append(
                        "stage %r: initial_stored_energy_J (%.4g J) "
                        "disagrees with G0=%.4g (%.4g J in the mode "
                        "volume); using G0" % (stage["stage_id"],
                                               E_stored_given, G0,
                                               E_stored_mode))
        else:
            gamma0 = E_stored_given / (J_sat * A_eff_m2)
            G0 = math.exp(gamma0)
            E_stored_mode = E_stored_given
        gamma = np.full(n_rings, gamma0)
        E_stored0 = float(np.sum(J_sat * gamma * areas))
        # LIDT of the gain element, from the stage's own side-car.
        stage_eng = load_eng(eng_path_for(stage_path))
        lidt = None
        elements_sec = stage_eng.get("elements")
        if isinstance(elements_sec, dict):
            entry = elements_sec.get(gain_label)
            if isinstance(entry, dict):
                v = entry.get("lidt_J_per_cm2")
                if isinstance(v, (int, float)) and not isinstance(v, bool) \
                        and math.isfinite(float(v)) and float(v) > 0:
                    lidt = float(v)
        n2 = stage["n2_m2_per_W"]
        if n2 is not None and L_mm is None:
            warnings.append("stage %r: n2 given but the gain element has "
                            "no L parameter; B integral skipped"
                            % stage["stage_id"])
            n2 = None
        if n2 is not None and tau_s is None:
            warnings.append("stage %r: n2 given but the seed has no "
                            "pulse_duration_s; B integral skipped"
                            % stage["stage_id"])
            n2 = None
        # --- transits ---
        n_passes = stage["passes"]
        n_transits = n_passes if trip == "SP" else 2 * n_passes
        E_stage_in = E
        transits = []
        extracted_total = 0.0
        for t in range(n_transits):
            rt_index = (t // 2) + 1 if trip == "SW" else None
            gamma_used = gamma.copy()
            J_in = fluence_profile(E, w_eff_m, u_c)
            # Per-ring gain: J_out,i = J_sat ln[1 + exp(gamma_i)
            # (exp(J_in,i/J_sat) - 1)] -- the stable form of fn_pass
            # with a per-ring G0.
            x = J_in / J_sat
            # np.where evaluates both branches; clip the expm1
            # argument to avoid an overflow warning on the discarded
            # branch.
            y = np.where(x > 50.0, x + gamma_used,
                         np.log1p(np.exp(gamma_used)
                                  * np.expm1(np.minimum(x, 50.0))))
            J_out = J_sat * y
            E_out = float(np.sum(J_out * areas))
            extracted_total += E_out - E
            # Local depletion: gamma_i <- gamma_i - (J_out - J_in)/J_sat.
            gamma = np.maximum(0.0, gamma - (J_out - J_in) / J_sat)
            E_stored = float(np.sum(J_sat * gamma * areas))
            # LIDT at the transit exit (conservative: output energy).
            fluence = lidt_fluence_J_per_cm2(E_out, w_T_mm, w_S_mm)
            if lidt is None:
                lidt_status, lidt_ratio = "nodata", None
            else:
                lidt_ratio = fluence / lidt
                lidt_status = classify_lidt(lidt_ratio)
            # B integral for this transit.
            B_pass = 0.0
            if n2 is not None and tau_s is not None:
                P_pk = GAUSS_PEAK_FACTOR * E_out / tau_s
                I_pk = 2.0 * P_pk / (math.pi * w_T_mm * w_S_mm * 1e-6)
                B_pass = (2.0 * math.pi / (lam_nm * 1e-9)) * n2 * I_pk \
                    * (L_mm * 1e-3)
                B_total += B_pass
                if B_total > B_WARN_RAD and not any(
                        "B integral" in w for w in warnings):
                    warnings.append(
                        "cumulated B integral %.3g rad exceeds %.3g rad "
                        "(self-focusing / spectral distortion risk)"
                        % (B_total, B_WARN_RAD))
            transits.append({
                "stage_id": stage["stage_id"],
                "transit": t + 1,
                "round_trip": rt_index,
                "E_in_J": E, "E_out_J": E_out,
                "gain": E_out / E if E > 0 else float("inf"),
                "G0_on_axis": float(np.exp(gamma_used)[0]),
                "stored_J_after": E_stored,
                "fluence_J_per_cm2": fluence,
                "lidt_ratio": lidt_ratio,
                "lidt_status": lidt_status,
                "B_rad": B_pass,
                "B_cum_rad": B_total,
            })
            E = E_out
            # Inter-pass / inter-round-trip loss (not after the last).
            if trip == "SP":
                if t < n_transits - 1 and stage["loss_per_pass"] > 0:
                    E *= (1.0 - stage["loss_per_pass"])
            else:
                if (t % 2 == 1) and t < n_transits - 1 \
                        and stage["round_trip_loss"] > 0:
                    E *= (1.0 - stage["round_trip_loss"])
        # Safety net: the per-ring bound makes total extraction <=
        # initial stored energy a theorem; warn if round-off broke it.
        if extracted_total > E_stored0 * (1.0 + 1e-9) + 1e-30:
            warnings.append(
                "stage %r: extracted energy %.4g J exceeds the initial "
                "stored energy %.4g J (numerical)"
                % (stage["stage_id"], extracted_total, E_stored0))
        stages_out.append({
            "stage_id": stage["stage_id"],
            "rez_file": stage["rez_file"],
            "trip_type": trip,
            "gain_element": gain_label,
            "material": stage["material"],
            "J_sat_J_per_cm2": J_sat * 1e-4,
            "passes": n_passes,
            "transits": n_transits,
            "w_T_mm": w_T_mm, "w_S_mm": w_S_mm,
            "w_eff_um": w_eff_m * 1e6,
            "L_mm": L_mm,
            "lambda_nm": lam_nm,
            "E_in_J": E_stage_in, "E_out_J": E,
            "gain": E / E_stage_in if E_stage_in > 0 else float("inf"),
            "stored_J_initial": E_stored0,
            "stored_J_final": float(np.sum(J_sat * gamma * areas)),
            "stored_J_mode_area": E_stored_mode,
            "B_total_rad": B_total,
            "transits_detail": transits,
        })
    report = {
        "version": 1,
        "osc_rez_path": os.path.abspath(osc_rez_path),
        "eng_path": (os.path.abspath(eng_file)
                     if eng_file is not None else None),
        "seed_J": E_seed,
        "seed_tau_s": tau_s,
        "seed_rep_Hz": chain["seed"].get("rep_rate_Hz"),
        "E_out_J": E,
        "overall_gain": E / E_seed if E_seed > 0 else float("inf"),
        "B_total_rad": B_total,
        "stages": stages_out,
        "warnings": warnings,
    }
    return report
