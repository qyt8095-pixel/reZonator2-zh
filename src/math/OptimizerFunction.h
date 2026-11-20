#ifndef OPTIMIZER_FUNCTION_H
#define OPTIMIZER_FUNCTION_H

#include "FunctionBase.h"

#include <functional>
#include <memory>

class BeamCalculator;
class ElementEventsLocker;

/**
    One-click cavity optimizer: searches for the values of chosen schema
    parameters that minimize a weighted merit function built from beam
    radius targets, astigmatism and stability centering.

    The search itself is done by a derivative-free Nelder-Mead simplex
    (see OptimizerSolver) in a normalized [0,1] space; discrete variables
    (e.g. stock mirror radii) are enumerated in an outer loop.

    During the search, parameter values are changed under
    ElementEventsLocker + Z::ParamValueBackup, so the schema UI is not
    refreshed on every iteration; the original values are restored when
    the run finishes. The user then reviews the result and explicitly
    applies it (apply()) or reverts to the pre-run values (revert()).
*/
class OptimizerFunction : public FunctionBase
{
public:
    FUNC_ALIAS("Optimizer")
    FUNC_NAME(QT_TRANSLATE_NOOP("Function Name", "谐振腔优化"))
    FUNC_ICON(":/toolbar/func_optimizer")
    FUNC_HELP(help_topic())
    static QString help_topic() { return "func_optimizer.html"; }

    /// Merit returned when a merit value is not finite (NaN/Inf guard).
    /// Unstable cavities get a smaller, continuous penalty instead (see
    /// OptimizerFunction.cpp), so the simplex can climb back into the
    /// stability region instead of going blind on a flat plateau.
    static constexpr double PENALTY_UNSTABLE = 1e9;

    /// Merit at the stability boundary: unstable points return
    /// UNSTABLE_BASE + UNSTABLE_SLOPE * (overshoot)^2, always above any
    /// merit reachable inside the stability region.
    static constexpr double UNSTABLE_BASE = 1e4;
    static constexpr double UNSTABLE_SLOPE = 1e5;

    /// Penalty for a fixed-total-length group whose dependent variable is
    /// pushed out of its [min, max] range: same constants and same shape
    /// as the instability penalty (a constant plus a slope times the
    /// squared overshoot), so it sits on the same merit scale -- above any
    /// merit reachable with the constraint satisfied. The overshoot is
    /// normalized by the dependent variable's range span (dimensionless,
    /// like |g| - 1 for the instability penalty), otherwise a length
    /// overshoot in meters would square to a negligible number.
    static constexpr double GROUP_PENALTY_BASE = UNSTABLE_BASE;
    static constexpr double GROUP_PENALTY_SLOPE = UNSTABLE_SLOPE;

    /// Max number of discrete candidate combinations in the outer loop.
    static constexpr int MAX_DISCRETE_COMBINATIONS_PURE = 50000;
    static constexpr int MAX_DISCRETE_COMBINATIONS_MIXED = 2048;

    /// Max total merit evaluations per run() (all discrete combinations
    /// and Nelder-Mead runs together).
    static constexpr int MAX_TOTAL_EVALUATIONS = 50000;

    enum class VarMode { Continuous, Discrete };

    struct Variable
    {
        Element* element = nullptr;     ///< Owning element (or global params element).
        Z::Parameter* param = nullptr;  ///< Optimized parameter (not owned).
        bool enabled = true;
        bool isGlobalParam = false;     ///< True when param belongs to schema global parameters.
        VarMode mode = VarMode::Continuous;
        double minSi = 0;               ///< Continuous mode: lower bound (SI).
        double maxSi = 0;               ///< Continuous mode: upper bound (SI).
        QVector<double> candidatesSi;   ///< Discrete mode: candidate values (SI).
        double startSi = 0;             ///< Value before the run (SI), for Revert.

        QString displayName() const;
    };

    enum class TargetKind { BeamRadiusT, BeamRadiusS, Astigmatism, StabilityCenter };

    /**
        Fixed-total-length group: a set of length variables whose sum is
        held constant while the individual lengths are optimized.

        The LAST enabled member (in variable-table order) is the dependent
        variable: it is not a free search dimension, its value is always
        computed as totalSi minus the other members (enabled members take
        their current search values, disabled members keep their current
        schema values). The Nelder-Mead vector therefore contains only the
        remaining enabled members. If the computed dependent value falls
        outside its [minSi, maxSi] range, the evaluation returns the group
        penalty (see GROUP_PENALTY_BASE), so the search steers away from
        the infeasible region instead of going blind on a flat plateau.

        Members must be continuous-mode length variables (linear
        dimension, not a curvature R or focal length F); the same variable
        may belong to at most one group. See validateGroup().
    */
    struct LengthGroup
    {
        QVector<int> members;   ///< Indices into _vars, in table order.
        double totalSi = 0;     ///< Fixed total length (SI, meters).
        bool enabled = true;
    };

    struct Target
    {
        TargetKind kind = TargetKind::StabilityCenter;
        Element* element = nullptr;     ///< Beam targets: element to measure at; null for StabilityCenter.
        double targetSi = 0;            ///< Beam radius target (SI, meters); unused for Astigmatism/StabilityCenter.
        double weight = 1.0;
        double currentSi = 0;           ///< Value measured at the last evaluation (display only).
        double contribution = 0;        ///< Merit contribution of the last evaluation (display only).

        static QString kindName(TargetKind kind);
        QString displayName() const;
    };

    struct RunResult
    {
        QVector<double> bestValuesSi;   ///< Best parameter values (SI, one per variable).
        double bestMerit = 0;
        int iterations = 0;
        int evaluations = 0;
        bool converged = false;
        bool stopped = false;
        bool budgetExceeded = false;    ///< Stopped early: evaluation budget exhausted.
    };

public:
    explicit OptimizerFunction(Schema* schema);
    ~OptimizerFunction() override;

    QVector<Variable>& variables() { return _vars; }
    const QVector<Variable>& variables() const { return _vars; }
    QVector<Target>& targets() { return _targets; }
    const QVector<Target>& targets() const { return _targets; }
    QVector<LengthGroup>& lengthGroups() { return _groups; }
    const QVector<LengthGroup>& lengthGroups() const { return _groups; }

    /// Validates one length group; returns an error message or empty string.
    /// The same rules are enforced by the UI when a group is created and by
    /// validate() at run entry. `skipGroupIndex` excludes one stored group
    /// from the overlap check (used when the UI validates an edited
    /// replacement for the group at that index); -1 checks against all.
    QString validateGroup(const LengthGroup& group, int skipGroupIndex = -1) const;

    /// True when the variable is the dependent of some enabled group
    /// (i.e. it is not a free search dimension).
    bool isGroupDependent(int varIndex) const;

    /// Index of the group's dependent variable (last enabled member), or -1
    /// when the group has no enabled member. Defensive: returns -1 for
    /// out-of-range member indices or null parameters.
    int dependentVarIndex(const LengthGroup& group) const;

    /// True when the variable may join a length group: continuous mode,
    /// linear dimension, and not a curvature R or focal length F.
    static bool isLengthGroupEligible(const Variable& v);

    /// Drops every group containing the variable at `index` and shifts
    /// member indices above it down by one. Must be called when a variable
    /// is removed from the table, otherwise group member indices dangle.
    void onVariableRemoved(int index);

    bool hasResult() const { return _hasResult; }
    const RunResult& lastResult() const { return _last; }

    /// Validates the current variables/targets; returns an error message or empty string.
    QString validate() const;

    /// Evaluates the merit function for the given parameter values (SI, one
    /// per variable, in variable-table order). The slot of a
    /// group-dependent variable is ignored: its value is recomputed from
    /// the group's fixed total. Safe to call outside run(): a temporary
    /// evaluation session is created if needed.
    double evaluate(const QVector<double>& valuesSi);

    /// Runs the optimization. On return, schema parameters are restored to
    /// their pre-run values; use apply() to keep the result or revert() to
    /// restore them explicitly (e.g. after apply()).
    /// onProgress(merit) is called after every evaluation, if given.
    RunResult run(int maxIter, const bool* stopFlag, std::function<void(double)> onProgress = {});

    /// Writes the best values found by run() into the schema parameters.
    void apply();

    /// Restores the parameter values from before the run().
    void revert();

private:
    struct OptimizationSession;
    struct TargetCalc;

    QVector<Variable> _vars;
    QVector<Target> _targets;
    QVector<LengthGroup> _groups;
    RunResult _last;
    bool _hasResult = false;
    std::unique_ptr<OptimizationSession> _session;

    void beginSession();
    void endSession();
    double evaluateInternal(const QVector<double>& valuesSi);
    /// Writes the dependent values of all enabled groups into `valuesSi`
    /// (one entry per variable, in variable-table order). Returns false
    /// when some dependent value falls outside its [minSi, maxSi] range,
    /// setting `penalty` to the group penalty (largest violation wins).
    /// Disabled group members are read from their current schema values,
    /// not from `valuesSi`. Invalid groups (bad indices, null parameters,
    /// discrete members) are skipped defensively; validateGroup() is the
    /// user-facing gate that rejects them at run entry.
    bool resolveGroupDependents(QVector<double>& valuesSi, double& penalty) const;
    double beamRadiusAt(Element* elem, Z::WorkPlane plane);
    void resetTargetCurrents();
    double normValue(int varIndex, double valueSi) const;
    double denormValue(int varIndex, double x01) const;
    /// Normalized Euclidean distance of a parameter set from the pre-run
    /// values (one unit per variable range). Used as a tie-break: among
    /// points with (nearly) equal merit, the closest to the start wins,
    /// i.e. the optimizer changes the cavity as little as possible.
    double distanceFromStart(const QVector<double>& valuesSi) const;
    QVector<QVector<double>> discreteCombos() const;
    /// Coarse deterministic prescreen of the continuous space (12 Halton
    /// points). Returns the best normalized point found and its merit;
    /// returns empty when every sampled point is unstable.
    std::vector<double> prescreenStableStart(const QVector<double>& baseValuesSi,
                                             const QVector<int>& contIdx, int& evals,
                                             double& bestMerit);
    RunResult solveCombo(const QVector<double>& baseValuesSi, const QVector<int>& contIdx,
                         int maxIter, const bool* stopFlag,
                         const std::function<void(double)>& onProgress,
                         int& totalEvals, int& totalIters,
                         std::vector<double>& prescreenBestX, double& prescreenBestMerit);
    RunResult runNelderMead(const QVector<double>& baseValuesSi, const QVector<int>& contIdx,
                            const std::vector<double>& x0,
                            int maxIter, const bool* stopFlag,
                            const std::function<void(double)>& onProgress,
                            int& totalEvals, int& totalIters);
};

#endif // OPTIMIZER_FUNCTION_H
