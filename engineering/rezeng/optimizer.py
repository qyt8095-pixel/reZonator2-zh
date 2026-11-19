"""Two-stage cavity optimizer (Phase 3 block 1).

Stage 1: vectorized differential evolution
(``scipy.optimize.differential_evolution(vectorized=True,
updating='deferred')``) -- the whole population is packed into ONE
headless-CLI batch request per generation. Stage 2: Nelder-Mead
polish (same algorithm as the C++ OptimizerWindow), ``xatol=1e-4``,
``fatol=1e-5``, ``maxfev=300``. No basin-hopping, no SLSQP (both
break on the stability-boundary discontinuity, per the Phase 3
review).

Variables are bound to .rez parameters (``label`` + ``alias``) and
optimised in normalised [0, 1] space, exactly like the C++
OptimizerWindow (``normValue`` / ``denormValue`` clamp to [0, 1]).
Continuous variables give ``{"label", "alias", "min_si", "max_si"}``
(SI units); discrete variables give ``{"label", "alias",
"candidates_si": [...]}`` and are enumerated in an outer loop, as in
C++ (at most 2048 combinations when continuous variables are also
present, 50000 for pure-discrete runs).

Linear equality constraints are handled by *parameterisation*, not by
penalty terms: a ``fixed_total`` constraint lists length parameters
whose sum is fixed, e.g.::

    {"kind": "fixed_total",
     "members": [("d1", "L"), ("d2", "L"), ("d3", "L")],
     "total_si": 0.867}

The last member is derived (``L_n = L_total - sum(L_i)``) and is
never a free variable; the constraint is then satisfied exactly.
A derived value that is not finite or below ``MIN_LENGTH_SI`` makes
the point infeasible (merit 1e9) without a CLI call.

Degenerate optima (e.g. maximum stability margin, where merit 0 is
a whole g = 0 surface) are resolved with the same tie-break as the
C++ code and the Phase 0 prototype: among all evaluated points whose
merit is within ``TIE_TOL`` (1e-9) of the best, the one closest to the
start point in normalised space wins. When the best merit is
essentially zero and a stability-center target is present, the
tie-break is refined further by a penalty-form least-squares solve
(``[g_T, g_S, w * (x - x0)]``, ``w = 1e-3``) that crawls along the
g = 0 surface towards the start point -- the cache-only tie-break
can only pick among points the search happened to visit, which may
be far from the closest surface point. (Note: the prototype's grid
search reported (L=90, R1=45, R2=60) as the closest optimum, but
that was grid-limited: the continuous refinement finds a closer
surface point near (L=84, R1=R2=49); both have margin 1.00.)
"""

import math

import numpy as np
from scipy.optimize import (differential_evolution, least_squares,
                             minimize)

from .cli import DEFAULT_BINARY, HeadlessError, run_headless
from .merit import (PENALTY_UNSTABLE, evaluate_batch, evaluate_result,
                    validate_targets)
from .rez import (check_overridable, param_unit, param_value_si)
from .units import from_si

#: CLI guards, copied from ``OptimizerFunction::validate`` (protocol
#: section 5) and ``rezeng.solves``: a length below this (SI) is
#: rejected, R/F must not be 0.
MIN_LENGTH_SI = 1e-6

#: Aliases of curvature / focal-length parameters (must not cross 0).
_CURVATURE_ALIASES = ("R", "R1", "R2", "F", "Fs", "Ft")

#: Tie-break tolerance on merit (absolute). Mirrors the Phase 0
#: prototype's 1e-9 margin tie-break.
TIE_TOL = 1e-9

#: Discrete-combination caps, copied from C++ OptimizerFunction.
MAX_DISCRETE_COMBINATIONS_PURE = 50000
MAX_DISCRETE_COMBINATIONS_MIXED = 2048


class OptimizerError(ValueError):
    """Raised when an optimization cannot be set up."""


def _is_curvature_alias(alias):
    return alias in _CURVATURE_ALIASES


class BatchEvaluator(object):
    """Batch merit evaluation of normalised points through the CLI.

    ``points01`` is an array of shape (D,) or (D, N) (the
    vectorized-DE convention: one column per population member) or
    (N, D). Returns merit(s) in the same order. Every new point costs
    one CLI mutation; repeated points are served from the cache, and
    one population is always a single CLI batch request.
    """

    def __init__(self, data, variables, targets, constraints=None,
                 binary=None, timeout=None, power=None):
        self.data = data
        self.targets = validate_targets(targets)
        self.binary = binary if binary is not None else DEFAULT_BINARY
        self.timeout = timeout
        self.power = power
        self.constraints = list(constraints or [])
        self.cache = {}  # key (normalised point) -> (merit, raw result)
        self.evaluations = 0
        self.cli_calls = 0
        self.n_infeasible = 0

        self.variables = []
        self.derived = []  # (label, alias, members, total_si)
        derived_labels = set()
        for c in self.constraints:
            if not isinstance(c, dict) or c.get("kind") != "fixed_total":
                raise OptimizerError("unsupported constraint %r" % (c,))
            members = c.get("members") or []
            total = c.get("total_si")
            if len(members) < 2 or total is None \
                    or not math.isfinite(total) or total <= 0:
                raise OptimizerError(
                    "fixed_total needs >= 2 members and a positive "
                    "total_si: %r" % (c,))
            last = tuple(members[-1])
            derived_labels.add(last)
            self.derived.append((last, [tuple(m) for m in members],
                                 float(total)))
        for v in variables:
            if not isinstance(v, dict):
                raise OptimizerError("variable is not an object: %r" % (v,))
            label = v.get("label")
            alias = v.get("alias")
            if not label or not alias:
                raise OptimizerError("variable needs label and alias: %r"
                                     % (v,))
            if (label, alias) in derived_labels:
                raise OptimizerError(
                    "variable %s.%s is the derived member of a "
                    "fixed_total constraint and cannot be free"
                    % (label, alias))
            conflict = check_overridable(data, label, alias)
            if conflict is not None:
                raise OptimizerError(
                    "variable %s.%s cannot be overridden: %s"
                    % (label, alias, conflict))
            unit = param_unit(data, label, alias)
            start = param_value_si(data, label, alias)
            if start is None or not math.isfinite(start):
                raise OptimizerError("variable %s.%s has no finite value "
                                     "in the schema" % (label, alias))
            if "candidates_si" in v:
                cands = [float(c) for c in v["candidates_si"]]
                if len(cands) < 2 or any(not math.isfinite(c)
                                         for c in cands):
                    raise OptimizerError(
                        "variable %s.%s needs >= 2 finite candidates"
                        % (label, alias))
                self.variables.append({
                    "label": label, "alias": alias, "unit": unit,
                    "start_si": start, "discrete": True,
                    "candidates_si": cands})
            else:
                lo = float(v["min_si"])
                hi = float(v["max_si"])
                if not (math.isfinite(lo) and math.isfinite(hi)
                        and hi > lo):
                    raise OptimizerError(
                        "variable %s.%s needs min_si < max_si"
                        % (label, alias))
                if not (lo <= start <= hi):
                    raise OptimizerError(
                        "variable %s.%s start value %.9g (SI) is outside "
                        "[%.9g, %.9g]" % (label, alias, start, lo, hi))
                self.variables.append({
                    "label": label, "alias": alias, "unit": unit,
                    "start_si": start, "discrete": False,
                    "min_si": lo, "max_si": hi})
        # Element existence for beam/astigmatism/waist targets.
        labels = {e["label"] for e in data.get("elements", [])}
        for t in self.targets:
            if t.get("element") and t["element"] not in labels:
                raise OptimizerError("target element %r is not in the "
                                     "schema" % (t["element"],))
        self.continuous = [v for v in self.variables if not v["discrete"]]
        self.discrete = [v for v in self.variables if v["discrete"]]
        self.dim = len(self.continuous)
        self.start01 = np.array([self._normalize(i, v["start_si"])
                                 for i, v in enumerate(self.continuous)],
                                dtype=float)

    # -- normalisation (mirrors C++ normValue / denormValue) ---------
    def _normalize(self, i, value_si):
        v = self.continuous[i]
        span = v["max_si"] - v["min_si"]
        return min(1.0, max(0.0, (value_si - v["min_si"]) / span))

    def _denormalize(self, i, x01):
        v = self.continuous[i]
        x = min(1.0, max(0.0, float(x01)))
        return v["min_si"] + x * (v["max_si"] - v["min_si"])

    def start_values_si(self):
        """Current .rez values of the free continuous variables (SI)."""
        return [v["start_si"] for v in self.continuous]

    # -- overrides -----------------------------------------------------
    def _overrides_for_point(self, values_si):
        """``({label: {alias: value_in_original_unit}}, feasible)``.

        ``values_si`` maps (label, alias) -> SI value for every free
        continuous variable. Derived members are computed here.
        """
        vals = dict(values_si)
        for last, members, total in self.derived:
            rest = sum(vals[m] for m in members[:-1])
            derived = total - rest
            if not math.isfinite(derived) or derived < MIN_LENGTH_SI:
                return None, False
            vals[last] = derived
        for (label, alias), v in vals.items():
            if _is_curvature_alias(alias) and v == 0.0:
                return None, False
            if alias == "L" and v < MIN_LENGTH_SI:
                return None, False
        overrides = {}
        for (label, alias), v in vals.items():
            unit = param_unit(self.data, label, alias)
            overrides.setdefault(label, {})[alias] = float(
                from_si(v, unit))
        return overrides, True

    def _points_to_array(self, points01):
        arr = np.asarray(points01, dtype=float)
        if arr.ndim == 1:
            return arr.reshape(-1, 1)  # (D, 1)
        if arr.ndim != 2:
            raise OptimizerError("points must be 1-D or 2-D, got shape %r"
                                 % (arr.shape,))
        if arr.shape[0] == self.dim:
            return arr  # (D, N): vectorized-DE convention
        if arr.shape[1] == self.dim:
            return arr.T  # (N, D) -> (D, N)
        raise OptimizerError("points have wrong dimension: shape %r for "
                             "D=%d" % (arr.shape, self.dim))

    def __call__(self, points01):
        """Merit(s) for normalised point(s). Accepts a single (D,)
        vector (returns a float) or a (D, N)/(N, D) population
        (returns a (N,) array)."""
        single = False
        arr = np.asarray(points01, dtype=float)
        if arr.ndim == 1:
            single = True
        pop = self._points_to_array(arr)
        # Clip to [0, 1] up front (mirrors the C++ denormValue clamp):
        # Nelder-Mead may step outside the box, and the merit must be
        # a function of the *evaluated* (clipped) point, not of the
        # raw simplex vertex -- otherwise the cache keys, the
        # tie-break distance and the reported values disagree.
        pop = np.clip(pop, 0.0, 1.0)
        n = pop.shape[1]
        merits = [None] * n
        todo_idx = []
        todo_points = []
        for j in range(n):
            key = tuple(float(x) for x in pop[:, j])
            if key in self.cache:
                merits[j] = self.cache[key][0]
            else:
                todo_idx.append(j)
                todo_points.append(key)
        if todo_points:
            values_list = []
            feasible = []
            for key in todo_points:
                values_si = {(v["label"], v["alias"]):
                             self._denormalize(i, x)
                             for i, (v, x) in
                             enumerate(zip(self.continuous, key))}
                overrides, ok = self._overrides_for_point(values_si)
                feasible.append(ok)
                values_list.append((key, overrides))
            batch = [(idx, key, ov) for idx, (key, ov), ok
                     in zip(todo_idx, values_list, feasible) if ok]
            if batch:
                mutations = [{"id": k, "overrides": ov}
                             for k, (_idx, _key, ov) in enumerate(batch)]
                try:
                    out = run_headless(
                        {"base_schema": self.data, "mutations": mutations},
                        binary=self.binary, timeout=self.timeout)
                except HeadlessError as e:
                    raise OptimizerError("headless evaluation failed: %s"
                                         % (e,))
                results = out.get("results") or []
                if len(results) != len(batch):
                    raise OptimizerError(
                        "headless CLI returned %d results for %d "
                        "mutations" % (len(results), len(batch)))
                self.cli_calls += 1
                scored = evaluate_batch(results, self.targets,
                                        data=self.data, power=self.power)
                for (idx, key, _ov), (merit, _br), result in zip(
                        batch, scored, results):
                    self.cache[key] = (float(merit), result)
                    merits[idx] = float(merit)
                    self.evaluations += 1
            for idx, key, ok in zip(todo_idx, todo_points, feasible):
                if not ok:
                    self.cache[key] = (PENALTY_UNSTABLE, None)
                    merits[idx] = PENALTY_UNSTABLE
                    self.evaluations += 1
                    self.n_infeasible += 1
        out = np.array(merits, dtype=float)
        return float(out[0]) if single else out

    def result_at(self, x01):
        """Raw CLI result dict for a normalised point (from the cache
        when present, otherwise one batch evaluation). Returns ``None``
        for infeasible points."""
        key = tuple(float(x) for x in np.asarray(x01, dtype=float).ravel())
        if key not in self.cache:
            self(np.array(key))
        return self.cache[key][1]

    def history(self):
        """All evaluated (normalised point, merit) pairs, in
        evaluation order (dict preserves insertion order)."""
        return [{"x01": list(k), "merit": m}
                for k, (m, _r) in self.cache.items()]

    def tie_break(self, best_merit):
        """Closest-to-start point among cached points within TIE_TOL
        of ``best_merit``. Returns ``(x01, merit, distance)`` or
        ``None`` when the cache is empty."""
        if not self.cache:
            return None
        tol = max(TIE_TOL, TIE_TOL * abs(best_merit))
        best = None
        for key, (merit, _r) in self.cache.items():
            if merit <= best_merit + tol:
                d = float(np.linalg.norm(
                    np.array(key) - self.start01)) if self.dim else 0.0
                if best is None or d < best[2]:
                    best = (np.array(key), merit, d)
        return best


def _discrete_combos(discrete_vars):
    """Cartesian product of discrete candidate lists (each combo is a
    list of SI values, one per discrete variable)."""
    combos = [[]]
    for v in discrete_vars:
        combos = [c + [cand] for c in combos
                  for cand in v["candidates_si"]]
    return combos


def optimize(data, variables, targets, constraints=None,
             de_maxiter=40, de_popsize=10, de_seed=0,
             nm_maxfev=300, nm_xatol=1e-4, nm_fatol=1e-5,
             binary=None, timeout=None, power=None,
             fixed_overrides=None):
    """Two-stage optimisation. Returns a result dict::

        {"best_values_si": {(label, alias): value_si, ...},
         "best_merit": float, "breakdown": [...],
         "start_merit": float, "start_values_si": {...},
         "evaluations": int, "cli_calls": int,
         "de": {"best_merit", "nfev", "nit"},
         "nm": {"best_merit", "nfev", "nit", "success"},
         "tie_break": {"applied": bool, "distance": float},
         "discrete_combo": [values_si] | None}

    ``fixed_overrides`` maps (label, alias) -> SI value for variables
    held fixed during this call (used by the discrete outer loop and
    by Snap re-optimisation). The start point is evaluated first, so
    ``start_merit`` is always available for comparison.
    """
    evaluator = BatchEvaluator(data, variables, targets,
                               constraints=constraints, binary=binary,
                               timeout=timeout, power=power)
    fixed_overrides = fixed_overrides or {}
    start01 = evaluator.start01

    # The evaluator's _overrides_for_point only knows free continuous
    # variables; fixed (discrete / snapped) values are merged in by
    # wrapping the batch call. Simplest correct approach: bake them
    # into a per-call subclass-free shim -- monkey-patch the instance
    # method so the fixed values are added to every point.
    if fixed_overrides:
        base_overrides = evaluator._overrides_for_point

        def _with_fixed(values_si):
            merged = dict(values_si)
            merged.update(fixed_overrides)
            return base_overrides(merged)

        evaluator._overrides_for_point = _with_fixed

    start_merit = float(evaluator(start01))
    best_merit = start_merit
    best_x01 = np.array(start01, dtype=float)
    de_info = {"best_merit": start_merit, "nfev": 0, "nit": 0}
    nm_info = {"best_merit": start_merit, "nfev": 0, "nit": 0,
               "success": False}

    if evaluator.dim:
        de = differential_evolution(
            evaluator, bounds=[(0.0, 1.0)] * evaluator.dim,
            vectorized=True, updating="deferred",
            popsize=de_popsize, maxiter=de_maxiter, seed=de_seed,
            polish=False, init="latinhypercube", tol=0.0,
            mutation=(0.5, 1.0), recombination=0.7)
        de_info = {"best_merit": float(de.fun), "nfev": int(de.nfev),
                   "nit": int(de.nit)}
        if de.fun < best_merit:
            best_merit = float(de.fun)
            best_x01 = np.clip(np.array(de.x, dtype=float), 0.0, 1.0)
        nm = minimize(evaluator, best_x01, method="Nelder-Mead",
                      options={"xatol": nm_xatol, "fatol": nm_fatol,
                               "maxfev": nm_maxfev, "adaptive": True})
        nm_info = {"best_merit": float(nm.fun), "nfev": int(nm.nfev),
                   "nit": int(nm.nit), "success": bool(nm.success)}
        if nm.fun < best_merit:
            best_merit = float(nm.fun)
            best_x01 = np.clip(np.array(nm.x, dtype=float), 0.0, 1.0)

    # Tie-break on the degenerate-optimum surface.
    tie = evaluator.tie_break(best_merit)
    tie_applied = False
    tie_method = "cache"
    tie_distance = None
    if tie is not None:
        tie_x01, tie_merit, tie_distance = tie
        if float(np.linalg.norm(tie_x01 - best_x01)) > 0.0:
            best_x01 = tie_x01
            best_merit = float(tie_merit)
            tie_applied = True

    # Refined tie-break: when the optimum is degenerate with an
    # essentially-zero merit and a stability-center target is present,
    # crawl along the g = 0 surface towards the start point. The
    # crawl is local, so it is tried from the start point itself
    # (which lands on the nearest surface point) and from the best
    # point found (a fallback basin); the closest accepted point
    # wins.
    if best_merit <= 1e-6 and any(
            t["kind"] == "stability_center" for t in targets):
        for init in (evaluator.start01, best_x01):
            refined = _refine_on_g_surface(evaluator, init, best_merit)
            if refined is None:
                continue
            ref_x01, ref_merit, ref_distance = refined
            if ref_merit <= best_merit + TIE_TOL and (
                    tie_distance is None or ref_distance < tie_distance):
                best_x01 = ref_x01
                best_merit = float(ref_merit)
                tie_applied = True
                tie_method = "least_squares"
                tie_distance = ref_distance

    best_values_si = {}
    for i, v in enumerate(evaluator.continuous):
        best_values_si[(v["label"], v["alias"])] = evaluator._denormalize(
            i, best_x01[i])
    for (label, alias), value in fixed_overrides.items():
        best_values_si[(label, alias)] = float(value)
    # Derived members at the best point.
    if evaluator.derived:
        vals = {(v["label"], v["alias"]): best_values_si[(v["label"],
                                                          v["alias"])]
                for v in evaluator.continuous}
        vals.update(fixed_overrides)
        _ov, ok = evaluator._overrides_for_point(vals)
        if ok:
            for last, members, total in evaluator.derived:
                best_values_si[last] = total - sum(
                    vals[m] for m in members[:-1])

    # Final breakdown at the best point (from the cached raw result).
    breakdown = _breakdown_at(evaluator, best_x01, targets, data, power)
    return {
        "best_values_si": best_values_si,
        "best_merit": best_merit,
        "breakdown": breakdown,
        "start_merit": start_merit,
        "start_values_si": {
            (v["label"], v["alias"]): v["start_si"]
            for v in evaluator.variables},
        "evaluations": evaluator.evaluations,
        "cli_calls": evaluator.cli_calls,
        "n_infeasible": evaluator.n_infeasible,
        "de": de_info,
        "nm": nm_info,
        "tie_break": {"applied": tie_applied, "method": tie_method,
                      "distance": tie_distance},
        "discrete_combo": None,
    }


def _refine_on_g_surface(evaluator, x_init, best_merit):
    """Closest point on the g = 0 surface near ``x_init``.

    Minimises ``[g_T, g_S, w * (x - x0)]`` (``w = 1e-3``) with
    ``scipy.optimize.least_squares`` (bounds [0, 1], starting from
    ``x_init``). The small weight keeps the solver on the g = 0
    surface while pulling towards the start point ``x0``. Returns
    ``(x01, merit, distance)`` or ``None`` when the refinement fails
    or leaves the stable region. The caller only accepts the result
    when its merit stays within TIE_TOL of ``best_merit``.
    """
    if evaluator.dim == 0:
        return None
    x0 = np.array(evaluator.start01, dtype=float)
    x_start = np.array(x_init, dtype=float)
    weight = 1e-3

    def residuals(x):
        result = evaluator.result_at(x)
        if result is None or not result.get("ok"):
            return [10.0, 10.0] + [weight * (xi - x0i) for xi, x0i in
                                   zip(x, x0)]
        g_T = result.get("g_T")
        g_S = result.get("g_S")
        if g_T is None or g_S is None \
                or not (math.isfinite(g_T) and math.isfinite(g_S)):
            return [10.0, 10.0] + [weight * (xi - x0i) for xi, x0i in
                                   zip(x, x0)]
        return [g_T, g_S] + [weight * (xi - x0i) for xi, x0i in
                             zip(x, x0)]

    try:
        sol = least_squares(residuals, x_start,
                            bounds=(np.zeros(evaluator.dim),
                                    np.ones(evaluator.dim)),
                            xtol=1e-12, ftol=1e-12, gtol=1e-12,
                            max_nfev=200)
    except Exception:
        return None
    x_ref = np.array(sol.x, dtype=float)
    result = evaluator.result_at(x_ref)
    if result is None or not result.get("ok"):
        return None
    g_T = result.get("g_T")
    g_S = result.get("g_S")
    if g_T is None or g_S is None \
            or not (math.isfinite(g_T) and math.isfinite(g_S)):
        return None
    if abs(g_T) >= 1.0 or abs(g_S) >= 1.0:
        return None
    merit = float(evaluator(x_ref))
    distance = float(np.linalg.norm(x_ref - x0))
    return x_ref, merit, distance


def _breakdown_at(evaluator, x01, targets, data, power):
    """Breakdown at a normalised point, from the evaluator's cached
    raw CLI result (no extra CLI call)."""
    result = evaluator.result_at(x01)
    if result is None:
        return [{"kind": "penalty", "element": None, "value": None,
                 "target": None, "weight": None,
                 "contribution": PENALTY_UNSTABLE}]
    _m, breakdown = evaluate_result(result, targets, data=data,
                                    power=power)
    return breakdown


def optimize_with_discrete(data, variables, targets, constraints=None,
                           **kwargs):
    """Like :func:`optimize`, but discrete variables are enumerated in
    an outer loop (C++ behaviour). Each combination runs the full
    two-stage optimisation on the continuous subset; the best
    combination wins (ties broken by distance from the start point).
    Returns the same dict as :func:`optimize`, with
    ``discrete_combo`` set to the winning combination's SI values."""
    discrete = [v for v in variables if "candidates_si" in v]
    continuous = [v for v in variables if "candidates_si" not in v]
    if not discrete:
        return optimize(data, variables, targets,
                        constraints=constraints, **kwargs)
    combos = _discrete_combos(discrete)
    cap = (MAX_DISCRETE_COMBINATIONS_PURE if not continuous
           else MAX_DISCRETE_COMBINATIONS_MIXED)
    if len(combos) > cap:
        raise OptimizerError(
            "discrete combinations %d exceed the cap %d"
            % (len(combos), cap))
    best = None
    total_evals = 0
    total_calls = 0
    for combo in combos:
        fixed = {(v["label"], v["alias"]): value
                 for v, value in zip(discrete, combo)}
        res = optimize(data, continuous, targets,
                       constraints=constraints, fixed_overrides=fixed,
                       **kwargs)
        total_evals += res["evaluations"]
        total_calls += res["cli_calls"]
        if best is None or res["best_merit"] < best["best_merit"] - 1e-12:
            res["discrete_combo"] = list(combo)
            best = res
    best["evaluations"] = total_evals
    best["cli_calls"] = total_calls
    return best
