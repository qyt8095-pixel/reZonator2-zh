#include "OptimizerFunction.h"

#include "BeamCalculator.h"
#include "OptimizerSolver.h"
#include "../core/Element.h"
#include "../core/Schema.h"

#include <QApplication>

#include <algorithm>
#include <cmath>
#include <limits>

#include <QtMath>

//------------------------------------------------------------------------------
//                              Variable / Target
//------------------------------------------------------------------------------

QString OptimizerFunction::Variable::displayName() const
{
    if (!param)
        return QString();
    if (isGlobalParam)
        return QStringLiteral("全局.%1").arg(param->alias());
    if (element)
        return QStringLiteral("%1.%2").arg(element->label(), param->alias());
    return param->alias();
}

QString OptimizerFunction::Target::kindName(TargetKind kind)
{
    switch (kind)
    {
    case TargetKind::BeamRadiusT: return QStringLiteral("w_T");
    case TargetKind::BeamRadiusS: return QStringLiteral("w_S");
    case TargetKind::Astigmatism: return qApp->translate("Optimizer", "像散 |wT-wS|");
    case TargetKind::StabilityCenter: return qApp->translate("Optimizer", "稳区中心 |g|");
    }
    return QString();
}

QString OptimizerFunction::Target::displayName() const
{
    if (kind == TargetKind::StabilityCenter)
        return kindName(kind);
    if (element)
        return QStringLiteral("%1: %2").arg(element->label(), kindName(kind));
    return kindName(kind);
}

//------------------------------------------------------------------------------
//                              Length group
//------------------------------------------------------------------------------

int OptimizerFunction::dependentVarIndex(const LengthGroup& group) const
{
    // Members are kept in variable-table order, so the last enabled member
    // encountered is the dependent variable.
    int dep = -1;
    for (int mi : group.members)
    {
        if (mi < 0 || mi >= _vars.size())
            continue;
        const auto& v = _vars.at(mi);
        if (v.enabled && v.param)
            dep = mi;
    }
    return dep;
}

bool OptimizerFunction::isGroupDependent(int varIndex) const
{
    for (const auto& g : _groups)
    {
        if (!g.enabled)
            continue;
        if (dependentVarIndex(g) == varIndex)
            return true;
    }
    return false;
}

bool OptimizerFunction::isLengthGroupEligible(const Variable& v)
{
    // Only additive lengths belong in a total-length group: curvature R
    // and focal length F share the linear dimension but are not cavity
    // lengths. Discrete variables cannot be group members either: their
    // values come from a fixed candidate list, not from the total.
    return v.param
        && v.mode == VarMode::Continuous
        && v.param->dim() == Z::Dims::linear()
        && v.param->alias() != QStringLiteral("R")
        && v.param->alias() != QStringLiteral("F");
}

void OptimizerFunction::onVariableRemoved(int index)
{
    for (int gi = _groups.size() - 1; gi >= 0; gi--)
    {
        auto& g = _groups[gi];
        if (g.members.contains(index))
        {
            // The group lost a member: drop the whole group rather than
            // keeping a broken constraint behind the user's back.
            _groups.removeAt(gi);
            continue;
        }
        for (int& mi : g.members)
            if (mi > index)
                mi--;
    }
}

QString OptimizerFunction::validateGroup(const LengthGroup& group, int skipGroupIndex) const
{
    if (!group.enabled)
        return QString();
    if (group.members.size() < 2)
        return qApp->translate("Optimizer", "总长固定组至少需要 2 个成员。");

    for (int i = 0; i < group.members.size(); i++)
    {
        int mi = group.members.at(i);
        if (mi < 0 || mi >= _vars.size())
            return qApp->translate("Optimizer", "总长固定组包含无效的变量。");
        for (int j = i + 1; j < group.members.size(); j++)
            if (group.members.at(j) == mi)
                return qApp->translate("Optimizer", "变量 %1 在总长固定组中重复。")
                    .arg(_vars.at(mi).displayName());
    }
    for (int gi = 0; gi < _groups.size(); gi++)
    {
        if (gi == skipGroupIndex || !_groups.at(gi).enabled)
            continue;
        for (int mi : group.members)
            if (_groups.at(gi).members.contains(mi))
                return qApp->translate("Optimizer", "变量 %1 已在另一个总长固定组中。")
                    .arg(_vars.at(mi).displayName());
    }

    int enabledCount = 0;
    double fixedSum = 0.0;  // Disabled members count at their current values.
    double minSum = 0.0, maxSum = 0.0;
    for (int mi : group.members)
    {
        const auto& v = _vars.at(mi);
        if (!v.param || !v.element)
            return qApp->translate("Optimizer", "总长固定组包含无效的变量。");
        if (v.mode != VarMode::Continuous)
            return qApp->translate("Optimizer", "变量 %1 是离散模式，不能加入总长固定组。")
                .arg(v.displayName());
        // Only additive lengths belong here: curvature R and focal length F
        // share the linear dimension but are not cavity lengths.
        if (v.param->dim() != Z::Dims::linear()
            || v.param->alias() == QStringLiteral("R")
            || v.param->alias() == QStringLiteral("F"))
            return qApp->translate("Optimizer", "变量 %1 不是长度参数，不能加入总长固定组。")
                .arg(v.displayName());
        if (v.enabled)
        {
            enabledCount++;
            minSum += v.minSi;
            maxSum += v.maxSi;
        }
        else
            fixedSum += v.param->value().toSi();
    }
    if (enabledCount < 2)
        return qApp->translate("Optimizer", "总长固定组至少需要 2 个启用的成员（一个自由变量和一个从属变量）。");
    if (!(group.totalSi > 0))
        return qApp->translate("Optimizer", "固定总长必须大于 0。");

    // Feasibility: the free part of the total must leave room for the
    // dependent variable strictly inside its [min, max]. At either
    // boundary the group degenerates to a single point (no freedom left),
    // so the boundary itself is rejected as well.
    double freeTotal = group.totalSi - fixedSum;
    auto fmtMm = [](double v) { return QString::number(v * 1e3, 'g', 6); };
    if (freeTotal <= minSum)
        return qApp->translate("Optimizer", "固定总长（%1 mm）必须大于各成员下限之和（%2 mm），否则从属变量没有取值空间。")
            .arg(fmtMm(group.totalSi)).arg(fmtMm(fixedSum + minSum));
    if (freeTotal >= maxSum)
        return qApp->translate("Optimizer", "固定总长（%1 mm）必须小于各成员上限之和（%2 mm），否则从属变量没有取值空间。")
            .arg(fmtMm(group.totalSi)).arg(fmtMm(fixedSum + maxSum));
    return QString();
}

bool OptimizerFunction::resolveGroupDependents(QVector<double>& valuesSi, double& penalty) const
{
    penalty = 0.0;
    bool ok = true;
    for (const auto& g : _groups)
    {
        if (!g.enabled)
            continue;
        int dep = dependentVarIndex(g);
        if (dep < 0 || dep >= valuesSi.size())
            continue;
        const auto& depVar = _vars.at(dep);
        if (!depVar.param || depVar.mode != VarMode::Continuous)
            continue;
        double sum = 0.0;
        bool usable = true;
        for (int mi : g.members)
        {
            if (mi < 0 || mi >= _vars.size())
            {
                usable = false;
                break;
            }
            const auto& v = _vars.at(mi);
            if (!v.param)
            {
                usable = false;
                break;
            }
            if (mi == dep)
                continue;
            if (v.enabled && v.mode == VarMode::Continuous)
            {
                if (mi >= valuesSi.size())
                {
                    usable = false;
                    break;
                }
                sum += valuesSi.at(mi);
            }
            else if (v.enabled)
            {
                // A discrete enabled member: rejected by validateGroup(),
                // skipped defensively here (the group is not applied).
                usable = false;
                break;
            }
            else
                sum += v.param->value().toSi();
        }
        if (!usable)
            continue;
        double depValue = g.totalSi - sum;
        valuesSi[dep] = depValue;
        double span = depVar.maxSi - depVar.minSi;
        if (span <= 0)
            continue;
        double over = 0.0;
        if (depValue < depVar.minSi)
            over = (depVar.minSi - depValue) / span;
        else if (depValue > depVar.maxSi)
            over = (depValue - depVar.maxSi) / span;
        if (over > 0)
        {
            ok = false;
            double p = GROUP_PENALTY_BASE + GROUP_PENALTY_SLOPE * over * over;
            if (p > penalty)
                penalty = p;
        }
    }
    return ok;
}

//------------------------------------------------------------------------------
//                              EvalSession
//------------------------------------------------------------------------------

struct OptimizerFunction::TargetCalc
{
    Element* element = nullptr;
    std::unique_ptr<BeamCalculator> calc;
};

struct OptimizerFunction::OptimizationSession
{
    std::vector<std::unique_ptr<ElementEventsLocker>> locks;
    std::vector<std::unique_ptr<Z::ParamValueBackup>> backups;
    std::unique_ptr<BeamCalculator> stabCalc;
    std::vector<TargetCalc> targetCalcs;
    Element* refElem = nullptr;

    // Destruction order is reverse declaration order: target calcs and the
    // stability calc are destroyed first, then backups restore the original
    // parameter values (while events are still locked, so no UI refresh
    // happens), then locks release.
};

//------------------------------------------------------------------------------
//                              OptimizerFunction
//------------------------------------------------------------------------------

OptimizerFunction::OptimizerFunction(Schema* schema) : FunctionBase(schema)
{
}

OptimizerFunction::~OptimizerFunction()
{
    endSession();
}

QString OptimizerFunction::validate() const
{
    if (!_schema->isResonator())
        return qApp->translate("Optimizer", "谐振腔优化仅适用于谐振腔。");

    if (_schema->activeCount() == 0)
        return qApp->translate("Optimizer", "光路图为空。");

    bool hasEnabledVar = false;
    bool hasContinuous = false;
    for (const auto& v : _vars)
        if (v.enabled)
        {
            hasEnabledVar = true;
            if (v.mode == VarMode::Continuous)
                hasContinuous = true;
        }
    if (!hasEnabledVar)
        return qApp->translate("Optimizer", "请至少启用一个优化变量。");

    if (_targets.isEmpty())
        return qApp->translate("Optimizer", "请至少添加一个优化目标。");

    // Defensive checks at run entry: pointers must be alive, variables must
    // be free parameters, target elements must still belong to the schema
    // (the user may have deleted an element after configuring the window).
    const auto& schemaElems = _schema->elements();
    for (const auto& v : _vars)
    {
        if (!v.enabled)
            continue;
        if (!v.param || !v.element)
            return qApp->translate("Optimizer", "存在无效的优化变量。");
        if (v.element != _schema->globalParamsAsElem() && !schemaElems.contains(v.element))
            return qApp->translate("Optimizer", "变量 %1 的元件已不在光路图中。").arg(v.displayName());
        if (v.param->valueDriver() != Z::ParamValueDriver::None)
            return qApp->translate("Optimizer", "参数 %1 由公式或链接驱动，不能作为优化变量。").arg(v.displayName());
    }
    for (const auto& t : _targets)
    {
        if (t.element && !schemaElems.contains(t.element))
            return qApp->translate("Optimizer", "目标元件 %1 已不在光路图中。").arg(t.element->label());
    }

    int discreteCombos = 1;
    for (const auto& v : _vars)
    {
        if (!v.enabled)
            continue;
        if (v.mode == VarMode::Continuous)
        {
            if (!(v.minSi < v.maxSi))
                return qApp->translate("Optimizer", "变量 %1 的下限必须小于上限。").arg(v.displayName());
            // Length-like parameters must stay positive: zero or negative
            // lengths are physically meaningless and can produce NaNs
            // inside some element matrices (sqrt of a negative, tan poles).
            if (v.param->dim() == Z::Dims::linear() && v.minSi < 1e-6)
                return qApp->translate("Optimizer", "变量 %1 的下限必须不小于 1 微米。").arg(v.displayName());
            // Curvature radius and focal length are divided by in element
            // matrices; the interval must not cross zero (negative values
            // themselves are valid: convex mirrors have R < 0).
            if ((v.param->alias() == "R" || v.param->alias() == "F") && v.minSi * v.maxSi <= 0)
                return qApp->translate("Optimizer", "变量 %1 的区间不能跨越 0。").arg(v.displayName());
        }
        else
        {
            if (v.candidatesSi.isEmpty())
                return qApp->translate("Optimizer", "变量 %1 的候选列表为空。").arg(v.displayName());
            if (v.param->dim() == Z::Dims::linear())
                for (double c : v.candidatesSi)
                    if (c < 1e-6)
                        return qApp->translate("Optimizer", "变量 %1 的候选值必须不小于 1 微米。").arg(v.displayName());
            if (v.param->alias() == "R" || v.param->alias() == "F")
                for (double c : v.candidatesSi)
                    if (c == 0)
                        return qApp->translate("Optimizer", "变量 %1 的候选值不能为 0。").arg(v.displayName());
            discreteCombos *= v.candidatesSi.size();
        }
    }
    int comboLimit = hasContinuous ? MAX_DISCRETE_COMBINATIONS_MIXED : MAX_DISCRETE_COMBINATIONS_PURE;
    if (discreteCombos > comboLimit)
        return qApp->translate("Optimizer", "离散变量的候选组合数（%1）超过上限 %2，请减少候选值。")
            .arg(discreteCombos).arg(comboLimit);

    for (int gi = 0; gi < _groups.size(); gi++)
    {
        QString gerr = validateGroup(_groups.at(gi), gi);
        if (!gerr.isEmpty())
            return gerr;
    }

    for (const auto& t : _targets)
    {
        if (t.kind == TargetKind::BeamRadiusT || t.kind == TargetKind::BeamRadiusS)
        {
            if (!t.element)
                return qApp->translate("Optimizer", "光斑目标未指定元件。");
            if (!(t.targetSi > 0))
                return qApp->translate("Optimizer", "光斑目标值必须大于 0。");
        }
        else if (t.kind == TargetKind::Astigmatism)
        {
            if (!t.element)
                return qApp->translate("Optimizer", "像散目标未指定元件。");
        }
    }
    return QString();
}

void OptimizerFunction::beginSession()
{
    endSession();
    // All BeamCalculators are built once here, before the evaluation loop;
    // inside the loop only multMatrix() is called, never new.
    _session = std::make_unique<OptimizationSession>();

    for (auto& v : _vars)
    {
        if (!v.enabled || !v.param)
            continue;
        _session->locks.emplace_back(new ElementEventsLocker(v.param, "OptimizerFunction::run"));
        _session->backups.emplace_back(new Z::ParamValueBackup(v.param, "OptimizerFunction::run"));
    }

    auto elems = _schema->activeElements();
    if (elems.isEmpty())
        return;
    _session->refElem = elems.first();

    _session->stabCalc = std::make_unique<BeamCalculator>(_schema);
    _session->stabCalc->calcRoundTrip(_session->refElem, false, "OptimizerFunction::run");

    for (auto& t : _targets)
    {
        if (t.kind == TargetKind::StabilityCenter || !t.element)
            continue;
        bool exists = false;
        for (auto& tc : _session->targetCalcs)
            if (tc.element == t.element)
            {
                exists = true;
                break;
            }
        if (exists)
            continue;
        TargetCalc tc;
        tc.element = t.element;
        tc.calc = std::make_unique<BeamCalculator>(_schema);
        tc.calc->calcRoundTrip(t.element, false, "OptimizerFunction::run");
        _session->targetCalcs.push_back(std::move(tc));
    }
}

void OptimizerFunction::endSession()
{
    _session.reset();
}

void OptimizerFunction::resetTargetCurrents()
{
    for (auto& t : _targets)
    {
        t.currentSi = qQNaN();
        t.contribution = qQNaN();
    }
}

double OptimizerFunction::beamRadiusAt(Element* elem, Z::WorkPlane plane)
{
    if (!_session)
        return qQNaN();
    for (auto& tc : _session->targetCalcs)
        if (tc.element == elem && tc.calc && tc.calc->ok())
        {
            tc.calc->multMatrix("OptimizerFunction::evaluate");
            tc.calc->setPlane(plane);
            return tc.calc->beamRadius();
        }
    return qQNaN();
}

double OptimizerFunction::evaluate(const QVector<double>& valuesSi)
{
    bool tempSession = !_session;
    if (tempSession)
        beginSession();
    double merit = evaluateInternal(valuesSi);
    if (tempSession)
        endSession();
    return merit;
}

double OptimizerFunction::evaluateInternal(const QVector<double>& valuesSi)
{
    if (!_session || !_session->stabCalc || !_session->stabCalc->ok())
        return PENALTY_UNSTABLE;

    // Fixed-total-length groups first: dependent values are algebraic
    // functions of the free values, recomputed on every evaluation (never
    // iterated). An out-of-range dependent returns the group penalty
    // before any parameter is touched, so the beam calculation never sees
    // an invalid length.
    QVector<double> resolved = valuesSi;
    double groupPenalty = 0.0;
    if (!resolveGroupDependents(resolved, groupPenalty))
    {
        resetTargetCurrents();
        return std::isfinite(groupPenalty) ? groupPenalty : PENALTY_UNSTABLE;
    }

    // Values are read by variable-table index, NOT sequentially: disabled
    // variables keep their schema values, so the i-th entry of `resolved`
    // always belongs to the i-th variable. A sequential read would
    // misassign values whenever a disabled variable precedes an enabled
    // one (the i-th enabled variable would read the slot of the i-th
    // variable overall).
    for (int i = 0; i < _vars.size(); i++)
    {
        const auto& v = _vars.at(i);
        if (!v.enabled || !v.param)
            continue;
        if (i >= resolved.size())
            return PENALTY_UNSTABLE;
        Z::Param::setSi(v.param, resolved.at(i));
    }

    auto* stab = _session->stabCalc.get();
    stab->multMatrix("OptimizerFunction::evaluate");
    stab->setPlane(Z::T);
    double gT = stab->stability_normal();
    stab->setPlane(Z::S);
    double gS = stab->stability_normal();

    // Continuous out-of-stability penalty: a constant penalty would blind
    // the simplex on a flat plateau (all samples equal, no search direction).
    // This one is always above any merit reachable inside the stability
    // region, and its slope points back towards |g| < 1.
    if (!std::isfinite(gT) || !std::isfinite(gS))
    {
        resetTargetCurrents();
        return PENALTY_UNSTABLE;
    }
    if (qAbs(gT) >= 1.0 || qAbs(gS) >= 1.0)
    {
        double overT = qMax(0.0, qAbs(gT) - 1.0);
        double overS = qMax(0.0, qAbs(gS) - 1.0);
        double penalty = UNSTABLE_BASE + UNSTABLE_SLOPE * (overT * overT + overS * overS);
        resetTargetCurrents();
        return std::isfinite(penalty) ? penalty : PENALTY_UNSTABLE;
    }

    double merit = 0.0;
    for (auto& t : _targets)
    {
        double term = 0.0;
        switch (t.kind)
        {
        case TargetKind::BeamRadiusT:
        case TargetKind::BeamRadiusS:
        {
            double w = beamRadiusAt(t.element, t.kind == TargetKind::BeamRadiusT ? Z::T : Z::S);
            t.currentSi = w;
            if (!std::isfinite(w))
                return PENALTY_UNSTABLE;
            double rel = (w - t.targetSi) / t.targetSi;
            term = t.weight * rel * rel;
            break;
        }
        case TargetKind::Astigmatism:
        {
            double wT = beamRadiusAt(t.element, Z::T);
            double wS = beamRadiusAt(t.element, Z::S);
            if (!std::isfinite(wT) || !std::isfinite(wS))
                return PENALTY_UNSTABLE;
            double d = qAbs(wT - wS);
            t.currentSi = d;
            double ref = qMax(qMax(wT, wS), 1e-12);
            double rel = d / ref;
            term = t.weight * rel * rel;
            break;
        }
        case TargetKind::StabilityCenter:
        {
            double g = qSqrt(gT * gT + gS * gS);
            t.currentSi = g;
            term = t.weight * (gT * gT + gS * gS);
            break;
        }
        }
        t.contribution = term;
        merit += term;
    }
    // Last-resort guard: a NaN merit would poison the simplex ordering
    // (NaN comparisons are always false), so never let one escape.
    if (!std::isfinite(merit))
        return PENALTY_UNSTABLE;
    return merit;
}

double OptimizerFunction::normValue(int varIndex, double valueSi) const
{
    const auto& v = _vars.at(varIndex);
    double span = v.maxSi - v.minSi;
    if (span <= 0)
        return 0.0;
    return qBound(0.0, (valueSi - v.minSi) / span, 1.0);
}

double OptimizerFunction::denormValue(int varIndex, double x01) const
{
    const auto& v = _vars.at(varIndex);
    return v.minSi + qBound(0.0, x01, 1.0) * (v.maxSi - v.minSi);
}

double OptimizerFunction::distanceFromStart(const QVector<double>& valuesSi) const
{
    double d2 = 0.0;
    for (int i = 0; i < _vars.size(); i++)
    {
        const auto& v = _vars.at(i);
        if (!v.enabled || i >= valuesSi.size())
            continue;
        double scale = 1.0;
        if (v.mode == VarMode::Continuous)
            scale = v.maxSi - v.minSi;
        else if (!v.candidatesSi.isEmpty())
            scale = *std::max_element(v.candidatesSi.begin(), v.candidatesSi.end())
                  - *std::min_element(v.candidatesSi.begin(), v.candidatesSi.end());
        if (scale <= 0)
            scale = 1.0;
        double d = (valuesSi.at(i) - v.startSi) / scale;
        d2 += d * d;
    }
    return qSqrt(d2);
}

QVector<QVector<double>> OptimizerFunction::discreteCombos() const
{
    QVector<QVector<double>> combos = { QVector<double>() };
    for (const auto& v : _vars)
    {
        if (!v.enabled || v.mode != VarMode::Discrete)
            continue;
        QVector<QVector<double>> next;
        for (const auto& c : combos)
            for (double cand : v.candidatesSi)
            {
                auto nc = c;
                nc << cand;
                next << nc;
            }
        combos = next;
    }
    return combos;
}

namespace {

// Halton sequence: deterministic low-discrepancy sampling of [0,1].
double halton(int index, int base)
{
    double f = 1.0, r = 0.0;
    while (index > 0)
    {
        f /= base;
        r += f * (index % base);
        index /= base;
    }
    return r;
}

} // namespace

std::vector<double> OptimizerFunction::prescreenStableStart(
    const QVector<double>& baseValuesSi, const QVector<int>& contIdx, int& evals,
    double& bestMerit)
{
    int n = contIdx.size();
    static const int bases[] = {2, 3, 5, 7, 11, 13};
    const int haltonPoints = 12;

    std::vector<double> bestX;
    bestMerit = std::numeric_limits<double>::infinity();

    auto tryPoint = [&](const std::vector<double>& x) {
        QVector<double> values = baseValuesSi;
        for (int i = 0; i < n; i++)
            values[contIdx[i]] = denormValue(contIdx[i], x[i]);
        double merit = evaluateInternal(values);
        evals++;
        if (merit < bestMerit)
        {
            bestMerit = merit;
            bestX = x;
        }
    };

    // 12 deterministic Halton points spread over the whole space.
    for (int p = 1; p <= haltonPoints; p++)
    {
        std::vector<double> x(n);
        for (int i = 0; i < n; i++)
            x[i] = halton(p, bases[i % 6]);
        tryPoint(x);
    }
    if (bestMerit < UNSTABLE_BASE)
        return bestX;
    return {};
}

OptimizerFunction::RunResult OptimizerFunction::runNelderMead(
    const QVector<double>& baseValuesSi, const QVector<int>& contIdx,
    const std::vector<double>& x0,
    int maxIter, const bool* stopFlag,
    const std::function<void(double)>& onProgress,
    int& totalEvals, int& totalIters)
{
    RunResult res;
    res.bestValuesSi = baseValuesSi;

    // The solver stops on this flag; it is set when the user presses Stop
    // or when the global evaluation budget is exhausted.
    bool combinedStop = false;
    int evalsBefore = 0;
    auto meritFunc = [&](const std::vector<double>& x) -> double {
        QVector<double> values = baseValuesSi;
        for (size_t i = 0; i < contIdx.size(); i++)
            values[contIdx[i]] = denormValue(contIdx[i], x[i]);
        double merit = evaluateInternal(values);
        evalsBefore++;
        totalEvals++;
        if (onProgress)
            onProgress(merit);
        // Full event processing is required here: ExcludeUserInputEvents
        // would also block the Stop button. Re-entrancy is guarded by the
        // window, which disables every control except Stop while running.
        if (evalsBefore % 16 == 0)
            qApp->processEvents();
        if ((stopFlag && *stopFlag) || totalEvals >= MAX_TOTAL_EVALUATIONS)
            combinedStop = true;
        return merit;
    };

    auto nm = Optimizer::nelderMead(meritFunc, x0, maxIter, &combinedStop);
    totalIters += nm.iterations;

    res.bestMerit = nm.merit;
    res.iterations = nm.iterations;
    res.evaluations = nm.evaluations;
    res.converged = nm.converged;
    // The solver stops on the combined flag; only a user Stop counts as
    // "stopped" here (budget exhaustion is reported separately by run()).
    res.stopped = nm.stopped && stopFlag && *stopFlag;
    for (size_t i = 0; i < contIdx.size(); i++)
        res.bestValuesSi[contIdx[i]] = denormValue(contIdx[i], nm.x[i]);
    // The search never wrote the group-dependent slots (they are not free
    // dimensions); recompute them from the free values so that apply(),
    // the result table and the tie-break distance see the true optimum.
    double dummyPenalty = 0.0;
    resolveGroupDependents(res.bestValuesSi, dummyPenalty);
    return res;
}

OptimizerFunction::RunResult OptimizerFunction::solveCombo(
    const QVector<double>& baseValuesSi, const QVector<int>& contIdx,
    int maxIter, const bool* stopFlag,
    const std::function<void(double)>& onProgress,
    int& totalEvals, int& totalIters,
    std::vector<double>& prescreenBestX, double& prescreenBestMerit)
{
    RunResult res;
    res.bestValuesSi = baseValuesSi;
    prescreenBestX.clear();
    prescreenBestMerit = std::numeric_limits<double>::infinity();

    if (contIdx.isEmpty())
    {
        // Pure discrete: the enumeration itself is the search.
        res.bestMerit = evaluateInternal(baseValuesSi);
        res.evaluations = 1;
        res.converged = true;
        totalEvals += 1;
        if (onProgress)
            onProgress(res.bestMerit);
        return res;
    }

    // Evaluate the current point first.
    double startMerit = evaluateInternal(baseValuesSi);
    totalEvals += 1;
    if (onProgress)
        onProgress(startMerit);

    std::vector<double> x0;
    if (startMerit < UNSTABLE_BASE)
    {
        // The current point is stable: start Nelder-Mead from it, so the
        // optimizer changes the cavity as little as possible.
        for (int i : contIdx)
            x0.push_back(normValue(i, baseValuesSi.at(i)));
        prescreenBestX = x0;
        prescreenBestMerit = startMerit;
    }
    else
    {
        // The current point is unstable: prescreen for a stable start.
        // If no sampled point is stable, this discrete combination cannot
        // form a stable cavity and the expensive refinement is skipped.
        int prescreenEvals = 0;
        prescreenBestX = prescreenStableStart(baseValuesSi, contIdx, prescreenEvals, prescreenBestMerit);
        totalEvals += prescreenEvals;
        if (prescreenBestX.empty())
        {
            res.bestMerit = prescreenBestMerit;  // >= UNSTABLE_BASE
            res.evaluations = 1 + prescreenEvals;
            res.converged = false;
            return res;
        }
        x0 = prescreenBestX;
    }
    return runNelderMead(baseValuesSi, contIdx, x0, maxIter,
                         stopFlag, onProgress, totalEvals, totalIters);
}

OptimizerFunction::RunResult OptimizerFunction::run(int maxIter, const bool* stopFlag,
                                                    std::function<void(double)> onProgress)
{
    _last = RunResult();
    _hasResult = false;
    _errorText.clear();

    QString err = validate();
    if (!err.isEmpty())
    {
        setError(err);
        return _last;
    }

    for (auto& v : _vars)
        if (v.enabled && v.param)
            v.startSi = v.param->value().toSi();

    beginSession();

    QVector<int> contIdx, discIdx;
    for (int i = 0; i < _vars.size(); i++)
    {
        if (!_vars[i].enabled)
            continue;
        // Group dependents are not free search dimensions: their values
        // are recomputed from the group total on every evaluation.
        if (_vars[i].mode == VarMode::Continuous && isGroupDependent(i))
            continue;
        if (_vars[i].mode == VarMode::Continuous)
            contIdx << i;
        else
            discIdx << i;
    }

    QVector<double> base(_vars.size(), 0.0);
    for (int i = 0; i < _vars.size(); i++)
        base[i] = _vars[i].enabled && _vars[i].param ? _vars[i].param->value().toSi() : 0.0;

    struct ComboOutcome
    {
        QVector<double> discCombo;
        RunResult result;
        std::vector<double> prescreenBestX;
        double prescreenBestMerit = std::numeric_limits<double>::infinity();
    };
    QVector<ComboOutcome> outcomes;

    RunResult best;
    best.bestValuesSi = base;
    best.bestMerit = std::numeric_limits<double>::infinity();
    int totalEvals = 0, totalIters = 0;
    bool anyConverged = true, anyStopped = false, budgetExceeded = false;

    // A strictly smaller merit always wins. When merits tie within
    // tolerance (the stability-center merit is zero on the whole g=0
    // surface), the point closest to the start wins, so the optimizer
    // changes the cavity as little as possible.
    auto isBetter = [&](const RunResult& a, const RunResult& b) {
        // Non-finite merit (no valid point found yet) always loses to a
        // finite one. This matters for the very first comparison, where
        // b is the initial best with merit = +inf: without this guard the
        // tolerance below becomes inf and inf - inf = NaN makes both
        // comparisons false, so the first result would be discarded.
        bool aFinite = std::isfinite(a.bestMerit);
        bool bFinite = std::isfinite(b.bestMerit);
        if (aFinite && !bFinite) return true;
        if (!aFinite) return false;
        double tol = 1e-9 * qMax(1.0, qMax(a.bestMerit, b.bestMerit));
        if (a.bestMerit < b.bestMerit - tol) return true;
        if (a.bestMerit > b.bestMerit + tol) return false;
        return distanceFromStart(a.bestValuesSi) < distanceFromStart(b.bestValuesSi);
    };

    for (const auto& combo : discreteCombos())
    {
        if (stopFlag && *stopFlag)
        {
            anyStopped = true;
            break;
        }
        if (totalEvals >= MAX_TOTAL_EVALUATIONS)
        {
            budgetExceeded = true;
            break;
        }
        QVector<double> comboBase = base;
        for (int k = 0; k < discIdx.size(); k++)
            comboBase[discIdx[k]] = combo.at(k);
        ComboOutcome oc;
        oc.discCombo = combo;
        oc.result = solveCombo(comboBase, contIdx, maxIter, stopFlag, onProgress,
                               totalEvals, totalIters, oc.prescreenBestX, oc.prescreenBestMerit);
        if (oc.result.stopped)
            anyStopped = true;
        if (!oc.result.converged)
            anyConverged = false;
        if (totalEvals >= MAX_TOTAL_EVALUATIONS)
            budgetExceeded = true;
        outcomes << oc;
        if (isBetter(oc.result, best))
            best = oc.result;
    }

    // Multi-start safety net: re-run Nelder-Mead from a perturbed start for
    // the best three discrete combinations, to avoid local minima in
    // non-convex stability regions.
    if (!contIdx.isEmpty() && !budgetExceeded && !(stopFlag && *stopFlag))
    {
        std::sort(outcomes.begin(), outcomes.end(), [](const ComboOutcome& a, const ComboOutcome& b) {
            return a.result.bestMerit < b.result.bestMerit;
        });
        int reruns = 0;
        for (const auto& oc : outcomes)
        {
            if (reruns >= 3)
                break;
            if (oc.result.bestMerit >= UNSTABLE_BASE || oc.prescreenBestX.empty())
                continue;
            if (totalEvals >= MAX_TOTAL_EVALUATIONS)
            {
                budgetExceeded = true;
                break;
            }
            if (stopFlag && *stopFlag)
            {
                anyStopped = true;
                break;
            }
            std::vector<double> x0alt = oc.prescreenBestX;
            for (auto& xi : x0alt)
                xi = xi > 0.5 ? xi - 0.5 : xi + 0.5;
            QVector<double> comboBase = base;
            for (int k = 0; k < discIdx.size(); k++)
                comboBase[discIdx[k]] = oc.discCombo.at(k);
            auto res2 = runNelderMead(comboBase, contIdx, x0alt, maxIter,
                                      stopFlag, onProgress, totalEvals, totalIters);
            reruns++;
            if (res2.stopped)
                anyStopped = true;
            if (!res2.converged)
                anyConverged = false;
            if (isBetter(res2, best))
                best = res2;
            if (totalEvals >= MAX_TOTAL_EVALUATIONS)
                budgetExceeded = true;
        }
    }

    // Re-evaluate at the best point so the displayed target currents
    // correspond to the result, not to the last simplex vertex.
    // UNSTABLE_BASE is the stable/unstable discriminator: the continuous
    // out-of-stability penalty is always >= UNSTABLE_BASE, while any
    // merit reached inside the stability region is below it.
    if (best.bestMerit < UNSTABLE_BASE)
        evaluateInternal(best.bestValuesSi);

    endSession();

    _last = best;
    _last.converged = anyConverged && !anyStopped && !budgetExceeded;
    _last.stopped = anyStopped;
    _last.budgetExceeded = budgetExceeded;
    _last.iterations = totalIters;
    _last.evaluations = totalEvals;
    _hasResult = true;

    if (_last.bestMerit >= UNSTABLE_BASE)
    {
        setError(qApp->translate("Optimizer", "在给定变量范围内未找到稳定的参数组合。"));
        _hasResult = false;
    }
    return _last;
}

void OptimizerFunction::apply()
{
    if (!_hasResult)
        return;
    for (int i = 0; i < _vars.size(); i++)
    {
        const auto& v = _vars.at(i);
        if (!v.enabled || !v.param)
            continue;
        Z::Param::setSi(v.param, _last.bestValuesSi.at(i));
    }
    _schema->markModified("OptimizerFunction::apply");
    _schema->events().raise(SchemaEvents::Changed, "OptimizerFunction::apply");
}

void OptimizerFunction::revert()
{
    if (!_hasResult)
        return;
    for (int i = 0; i < _vars.size(); i++)
    {
        const auto& v = _vars.at(i);
        if (!v.enabled || !v.param)
            continue;
        Z::Param::setSi(v.param, v.startSi);
    }
    _schema->markModified("OptimizerFunction::revert");
    _schema->events().raise(SchemaEvents::Changed, "OptimizerFunction::revert");
}
