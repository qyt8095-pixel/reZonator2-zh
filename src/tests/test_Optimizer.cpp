#include "../core/Schema.h"
#include "../io/SchemaReaderJson.h"
#include "../math/OptimizerFunction.h"
#include "../tests/TestUtils.h"

#include "testing/OriTestBase.h"

#include <QDir>
#include <QFile>
#include <QtMath>

//------------------------------------------------------------------------------
//  End-to-end tests for the Optimizer module.
//
//  The main case loads the repository example
//  `bin/examples/spherical_symm.rez` (symmetric two-mirror cavity,
//  L = 80 mm, R1 = R2 = 50 mm) and runs OptimizerFunction::run() on it,
//  cross-checking against the Python prototype
//  `calc/optimizer_prototype.py`.
//
//  Two facts about the example file matter here:
//
//  1. The file links both mirror radii to the single global parameter R0
//     (param_links: R0 -> M1.R and R0 -> M2.R), so M1.R and M2.R are NOT
//     free parameters on load. The test removes those links first, which
//     makes R1 and R2 independent variables, exactly like the prototype's
//     model (the link is a symmetry convenience of the example, not a
//     property of the cavity being optimized).
//
//  2. The prototype's optimum (L = 90, R1 = 45, R2 = 60) is the closest
//     point on the g = 0 surface *on its coarse grid* (L step 2 mm,
//     R step 5 mm). The continuous Nelder-Mead solver finds a point on the
//     same surface that is *closer* to the start (about L = 86.7, R1 = 53.9,
//     R2 = 47.6 in simulation, normalized distance 0.057 vs 0.122 for the
//     grid point). Both have g = 0 and merit = 0: the maximum-stability
//     optimum is a whole surface, not an isolated point, so the test
//     asserts merit ~= 0, g ~= 0 and "closer to the start than the grid
//     point", and separately verifies that the prototype point itself
//     evaluates to merit ~= 0.
//------------------------------------------------------------------------------

namespace Z {
namespace Tests {
namespace OptimizerTests {

namespace {

QString findExampleFile()
{
    QString appDir = qApp->applicationDirPath();
    for (const QString& candidate : QStringList{
        appDir + "/examples/spherical_symm.rez",
        appDir + "/../bin/examples/spherical_symm.rez",
        appDir + "/../../bin/examples/spherical_symm.rez",
        appDir + "/../examples/spherical_symm.rez",
    })
        if (QFile::exists(candidate))
            return QDir::cleanPath(candidate);
    return QString();
}

Schema* loadExampleSchema()
{
    QString fileName = findExampleFile();
    if (fileName.isEmpty())
        return nullptr;
    Schema* schema = new Schema;
    SchemaReaderJson reader(schema);
    reader.skipFuncWindows = true;
    reader.readFromFile(fileName);
    if (reader.report().hasErrors())
    {
        delete schema;
        return nullptr;
    }
    return schema;
}

/// Removes all parameter links touching the element's parameters.
/// Schema::removeParamLinks() does exactly this but is private, so the
/// test replicates it via the public paramLinks() list. Deleting a link
/// resets the target parameter's driver back to None.
void unlinkParams(Schema* schema, Element* elem)
{
    for (auto* param : elem->params())
        while (auto* link = schema->paramLinks()->byTarget(param))
        {
            schema->paramLinks()->removeOne(link);
            delete link;
        }
}

/// Loads the example and unlinks the two mirror radii from the global R0,
/// so that L, R1 and R2 are three independent free variables.
Schema* loadUnlinkedExampleSchema()
{
    Schema* schema = loadExampleSchema();
    if (!schema)
        return nullptr;
    auto* m1 = schema->element("M1");
    auto* m2 = schema->element("M2");
    if (!m1 || !m2)
    {
        delete schema;
        return nullptr;
    }
    unlinkParams(schema, m1);
    unlinkParams(schema, m2);
    return schema;
}

OptimizerFunction::Variable makeVariable(Element* elem, const QString& paramAlias,
                                         double minSi, double maxSi)
{
    OptimizerFunction::Variable var;
    var.element = elem;
    var.param = elem->param(paramAlias);
    var.isGlobalParam = false;
    var.mode = OptimizerFunction::VarMode::Continuous;
    var.minSi = minSi;
    var.maxSi = maxSi;
    var.startSi = var.param->value().toSi();
    return var;
}

/// Variables L in [1 mm, 200 mm], R1/R2 in [1 mm, 100 mm].
/// The 1 mm lower bounds stand in for 0: the validator rejects 0 because
/// R = 0 is unphysical (division by zero) and L = 0 is degenerate.
void addExampleVariables(OptimizerFunction& func, Schema* schema)
{
    func.variables() << makeVariable(schema->element("L"), "L", 0.001, 0.2);
    func.variables() << makeVariable(schema->element("M1"), "R", 0.001, 0.1);
    func.variables() << makeVariable(schema->element("M2"), "R", 0.001, 0.1);
}

double normalizedDistance(double L, double R1, double R2)
{
    double dL = (L - 0.080) / 0.2;
    double dR1 = (R1 - 0.050) / 0.1;
    double dR2 = (R2 - 0.050) / 0.1;
    return qSqrt(dL * dL + dR1 * dR1 + dR2 * dR2);
}

} // namespace

//------------------------------------------------------------------------------
//                        Stability center (prototype cross-check)
//------------------------------------------------------------------------------

namespace StabilityCenter {

TEST_METHOD(run_converges_to_max_stability)
{
    Schema* schema = loadUnlinkedExampleSchema();
    ASSERT_IS_NOT_NULL(schema)
    // The links are gone: both radii are free parameters now.
    ASSERT_IS_TRUE(schema->element("M1")->param("R")->valueDriver() == Z::ParamValueDriver::None)
    ASSERT_IS_TRUE(schema->element("M2")->param("R")->valueDriver() == Z::ParamValueDriver::None)

    OptimizerFunction func(schema);
    addExampleVariables(func, schema);

    OptimizerFunction::Target target;
    target.kind = OptimizerFunction::TargetKind::StabilityCenter;
    target.element = nullptr;
    target.weight = 1.0;
    func.targets() << target;

    TEST_LOG(QStringLiteral("validate: '%1'").arg(func.validate()))
    ASSERT_IS_TRUE(func.validate().isEmpty())

    func.run(500, nullptr, nullptr);

    TEST_LOG(QStringLiteral("ok=%1 hasResult=%2 err='%3'")
        .arg(func.ok()).arg(func.hasResult()).arg(func.errorText()))
    ASSERT_IS_TRUE(func.ok())
    ASSERT_IS_TRUE(func.hasResult())
    ASSERT_IS_TRUE(func.lastResult().converged)

    const auto& res = func.lastResult();
    TEST_LOG_DOUBLE(res.bestMerit)
    TEST_LOG_DOUBLE(res.iterations)
    TEST_LOG_DOUBLE(res.evaluations)
    TEST_LOG_DOUBLE(func.targets().at(0).currentSi)
    TEST_LOG_DOUBLE(res.bestValuesSi.at(0))
    TEST_LOG_DOUBLE(res.bestValuesSi.at(1))
    TEST_LOG_DOUBLE(res.bestValuesSi.at(2))
    TEST_LOG_DOUBLE(normalizedDistance(res.bestValuesSi.at(0), res.bestValuesSi.at(1), res.bestValuesSi.at(2)))
    // Merit ~= 0 means |g| ~= 0 on both planes (weight 1).
    ASSERT_IS_TRUE(res.bestMerit < 1e-9)
    // |g| at the optimum, recorded by the evaluator.
    ASSERT_IS_TRUE(func.targets().at(0).currentSi < 1e-4)

    double L = res.bestValuesSi.at(0);
    double R1 = res.bestValuesSi.at(1);
    double R2 = res.bestValuesSi.at(2);
    // Continuous optimum, simulated in advance (about 86.7 / 53.9 / 47.6 mm);
    // generous boxes guard against small path differences of the simplex.
    ASSERT_IS_TRUE(L > 0.075 && L < 0.100)
    ASSERT_IS_TRUE(R1 > 0.040 && R1 < 0.065)
    ASSERT_IS_TRUE(R2 > 0.035 && R2 < 0.060)
    // Closer to the start than the prototype's grid point (distance 0.1225).
    ASSERT_IS_TRUE(normalizedDistance(L, R1, R2) < 0.10)

    // Cross-check with the Python prototype: its grid optimum
    // (L = 90, R1 = 45, R2 = 60) lies on the same g = 0 surface,
    // so it must also evaluate to (almost) zero merit.
    double protoMerit = func.evaluate({0.09, 0.045, 0.06});
    TEST_LOG_DOUBLE(protoMerit)
    ASSERT_IS_TRUE(protoMerit < 1e-9)

    delete schema;
}

TEST_METHOD(apply_and_revert)
{
    Schema* schema = loadUnlinkedExampleSchema();
    ASSERT_IS_NOT_NULL(schema)

    OptimizerFunction func(schema);
    addExampleVariables(func, schema);

    OptimizerFunction::Target target;
    target.kind = OptimizerFunction::TargetKind::StabilityCenter;
    target.weight = 1.0;
    func.targets() << target;

    func.run(500, nullptr, nullptr);
    ASSERT_IS_TRUE(func.ok())
    ASSERT_IS_TRUE(func.hasResult())

    const auto& best = func.lastResult().bestValuesSi;

    func.apply();
    ASSERT_NEAR_DBL(schema->element("L")->param("L")->value().toSi(), best.at(0), 1e-12)
    ASSERT_NEAR_DBL(schema->element("M1")->param("R")->value().toSi(), best.at(1), 1e-12)
    ASSERT_NEAR_DBL(schema->element("M2")->param("R")->value().toSi(), best.at(2), 1e-12)

    func.revert();
    ASSERT_NEAR_DBL(schema->element("L")->param("L")->value().toSi(), 0.080, 1e-12)
    ASSERT_NEAR_DBL(schema->element("M1")->param("R")->value().toSi(), 0.050, 1e-12)
    ASSERT_NEAR_DBL(schema->element("M2")->param("R")->value().toSi(), 0.050, 1e-12)

    delete schema;
}

TEST_GROUP("OptimizerStabilityCenter",
           ADD_TEST(run_converges_to_max_stability),
           ADD_TEST(apply_and_revert),
           )
} // namespace StabilityCenter

//------------------------------------------------------------------------------
//                        Beam radius target / unstable penalty
//------------------------------------------------------------------------------

namespace BeamTarget {

TEST_METHOD(run_beam_radius_target)
{
    Schema* schema = loadUnlinkedExampleSchema();
    ASSERT_IS_NOT_NULL(schema)

    OptimizerFunction func(schema);
    addExampleVariables(func, schema);

    // Beam radius at M1: 0.18 mm at the start (analytic value for this
    // cavity), target 0.20 mm.
    // NOTE: the Python prototype quoted 4.51 mm for the "waist at M1",
    // but the round-trip eigenmode gives 0.18 mm at the mirror (verified
    // analytically: w^2 = (lambda*L/pi) * sqrt(g2/(g1*(1-g1*g2))) with
    // g1 = g2 = -0.6, lambda = 1026 nm); the test uses the correct value.
    OptimizerFunction::Target target;
    target.kind = OptimizerFunction::TargetKind::BeamRadiusT;
    target.element = schema->element("M1");
    target.targetSi = 0.0002;
    target.weight = 1.0;
    func.targets() << target;

    ASSERT_IS_TRUE(func.validate().isEmpty())

    // The beam branch must produce a non-trivial merit at the start
    // (relative error (0.18-0.20)/0.20 -> merit ~0.01), not the penalty.
    double startMerit = func.evaluate({0.08, 0.05, 0.05});
    TEST_LOG_DOUBLE(startMerit)
    ASSERT_IS_TRUE(startMerit > 0.002 && startMerit < 0.05)

    func.run(500, nullptr, nullptr);

    ASSERT_IS_TRUE(func.ok())
    ASSERT_IS_TRUE(func.hasResult())
    const auto& res = func.lastResult();
    TEST_LOG_DOUBLE(res.bestMerit)
    // w within 1% of the 0.20 mm target.
    ASSERT_IS_TRUE(res.bestMerit < 1e-4)
    double w = func.targets().at(0).currentSi;
    TEST_LOG_DOUBLE(w)
    ASSERT_IS_TRUE(qAbs(w - 0.0002) / 0.0002 < 0.01)

    delete schema;
}

TEST_METHOD(all_unstable_range_reports_error)
{
    Schema* schema = loadUnlinkedExampleSchema();
    ASSERT_IS_NOT_NULL(schema)

    OptimizerFunction func(schema);
    // L in [190, 200] mm, R1/R2 in [40, 60] mm: g is between 8 and 31
    // everywhere in this box, so no stable cavity exists here.
    func.variables() << makeVariable(schema->element("L"), "L", 0.19, 0.2);
    func.variables() << makeVariable(schema->element("M1"), "R", 0.04, 0.06);
    func.variables() << makeVariable(schema->element("M2"), "R", 0.04, 0.06);

    OptimizerFunction::Target target;
    target.kind = OptimizerFunction::TargetKind::StabilityCenter;
    target.weight = 1.0;
    func.targets() << target;

    ASSERT_IS_TRUE(func.validate().isEmpty())

    // The unstable-penalty branch: every sampled point returns the
    // continuous penalty (>= 1e4), the prescreen finds no stable start,
    // and the run reports that no stable combination exists.
    double startMerit = func.evaluate({0.19, 0.04, 0.04});
    TEST_LOG_DOUBLE(startMerit)
    ASSERT_IS_TRUE(startMerit >= 1e4)

    func.run(500, nullptr, nullptr);
    ASSERT_IS_FALSE(func.ok())
    ASSERT_IS_FALSE(func.hasResult())
    TEST_LOG(func.errorText())
    ASSERT_IS_TRUE(func.errorText().contains(QStringLiteral("稳定")))

    delete schema;
}

TEST_GROUP("OptimizerBeamTarget",
           ADD_TEST(run_beam_radius_target),
           ADD_TEST(all_unstable_range_reports_error),
           )
} // namespace BeamTarget

//------------------------------------------------------------------------------

TEST_GROUP("Optimizer",
           ADD_GROUP(StabilityCenter),
           ADD_GROUP(BeamTarget),
           )

} // namespace OptimizerTests
} // namespace Tests
} // namespace Z
