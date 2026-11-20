#include "../core/Schema.h"
#include "../core/Elements.h"
#include "../funcs/OptimizerWindow.h"
#include "../math/OptimizerFunction.h"
#include "../tests/TestUtils.h"

#include "testing/OriTestBase.h"

#include <QJsonObject>
#include <QtMath>

//------------------------------------------------------------------------------
//  Tests for the fixed-total-length group of the one-click optimizer
//  (OptimizerFunction::LengthGroup).
//
//  Fixture: the repository example `bin/examples/spherical_symm.rez`
//  (symmetric two-mirror cavity, L = 80 mm, R1 = R2 = 50 mm) with its
//  single length element split into two ranges in series -- M1, d1, d2,
//  M2 -- which is optically identical to the original (two consecutive
//  translations multiply to one translation of the sum), so g = 1 - L/R
//  with L = d1 + d2. The group {d1, d2} with total 80 mm therefore pins
//  the cavity length while the split between the arms is free.
//
//  Covered here:
//  (a) a run keeps d1 + d2 == total (to < 1e-9 mm);
//  (b) the dependent value is computed from the total, and the slot of
//      the dependent variable in the values vector is ignored;
//  (c) a dependent value pushed out of its range returns the group
//      penalty (same shape as the instability penalty) and the search
//      steers away from it;
//  (d) the group survives a .she save/load round-trip (and old files
//      without the group load as "no group");
//  (e) without a group the behaviour is unchanged, including the
//      regression that a disabled variable in the middle of the table
//      must not shift the values of the variables after it;
//  (f) validateGroup() rejects invalid groups with a clear message.
//------------------------------------------------------------------------------

namespace Z {
namespace Tests {
namespace OptimizerLengthGroupTests {

namespace {

/// M1 (R = 50 mm), d1 (40 mm), d2 (40 mm), M2 (R = 50 mm), SW.
/// Optically the spherical_symm example with L split into two arms.
Schema* makeSplitCavity()
{
    Schema* schema = new Schema;
    schema->setTripType(TripType::SW);
    auto* m1 = new ElemCurveMirror;
    m1->setLabel("M1");
    Z::Param::setSi(m1->param("R"), 50e-3);
    Z::Param::setSi(m1->param("Alpha"), 0.0);
    auto* d1 = new ElemEmptyRange;
    d1->setLabel("d1");
    Z::Param::setSi(d1->paramLength(), 40e-3);
    auto* d2 = new ElemEmptyRange;
    d2->setLabel("d2");
    Z::Param::setSi(d2->paramLength(), 40e-3);
    auto* m2 = new ElemCurveMirror;
    m2->setLabel("M2");
    Z::Param::setSi(m2->param("R"), 50e-3);
    Z::Param::setSi(m2->param("Alpha"), 0.0);
    schema->insertElements({m1, d1, d2, m2}, -1, Arg::RaiseEvents(false));
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

/// Variables d1, d2 in [1, 200] mm (d2 upper bound overridable),
/// R1, R2 in [1, 100] mm.
void addSplitVariables(OptimizerFunction& func, Schema* schema, double d2maxSi = 0.2)
{
    func.variables() << makeVariable(schema->element("d1"), "L", 0.001, 0.2);
    func.variables() << makeVariable(schema->element("d2"), "L", 0.001, d2maxSi);
    func.variables() << makeVariable(schema->element("M1"), "R", 0.001, 0.1);
    func.variables() << makeVariable(schema->element("M2"), "R", 0.001, 0.1);
}

void addStabilityTarget(OptimizerFunction& func)
{
    OptimizerFunction::Target target;
    target.kind = OptimizerFunction::TargetKind::StabilityCenter;
    target.weight = 1.0;
    func.targets() << target;
}

OptimizerFunction::LengthGroup makeGroup(QVector<int> members, double totalSi)
{
    OptimizerFunction::LengthGroup g;
    g.members = members;
    g.totalSi = totalSi;
    g.enabled = true;
    return g;
}

} // namespace

//------------------------------------------------------------------------------
//                        (a) run keeps the total fixed
//------------------------------------------------------------------------------

namespace TotalFixed {

TEST_METHOD(run_keeps_total_length_fixed)
{
    Schema* schema = makeSplitCavity();
    OptimizerFunction func(schema);
    addSplitVariables(func, schema);
    addStabilityTarget(func);
    func.lengthGroups() << makeGroup({0, 1}, 0.08);

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
    TEST_LOG_DOUBLE(res.bestValuesSi.at(0))
    TEST_LOG_DOUBLE(res.bestValuesSi.at(1))
    TEST_LOG_DOUBLE(res.bestValuesSi.at(2))
    TEST_LOG_DOUBLE(res.bestValuesSi.at(3))
    // The stability-center target drives the ROUND-TRIP parameter
    // (A+D)/2 = 2*g1*g2 - 1 to zero, i.e. the optimum lies on the
    // g1*g2 = 0.5 surface (g = 1 - L/R per mirror), not on g1 = g2 = 0.
    ASSERT_IS_TRUE(res.bestMerit < 1e-9)
    double L = res.bestValuesSi.at(0) + res.bestValuesSi.at(1);
    double g1 = 1.0 - L / res.bestValuesSi.at(2);
    double g2 = 1.0 - L / res.bestValuesSi.at(3);
    ASSERT_NEAR_DBL(g1 * g2, 0.5, 1e-5)
    // The total is preserved to < 1e-9 mm (1e-12 m), and the dependent
    // value is exactly total minus the free one.
    double d1 = res.bestValuesSi.at(0);
    double d2 = res.bestValuesSi.at(1);
    ASSERT_NEAR_DBL(d1 + d2, 0.08, 1e-12)
    ASSERT_NEAR_DBL(d2, 0.08 - d1, 1e-12)

    delete schema;
}

TEST_GROUP("OptimizerLengthGroupTotalFixed",
           ADD_TEST(run_keeps_total_length_fixed),
           )
} // namespace TotalFixed

//------------------------------------------------------------------------------
//                        (b) dependent value is computed
//------------------------------------------------------------------------------

namespace DependentValue {

TEST_METHOD(dependent_value_is_computed_from_total)
{
    // With the group, the d2 slot of the values vector is ignored: the
    // dependent is always total - d1. At d1 = 30 mm the dependent is
    // 50 mm, so the merit must equal the merit of the same cavity
    // evaluated without a group at (d1, d2) = (30, 50) mm -- and must NOT
    // be the merit of the (unstable) cavity with d2 = 999 mm.
    Schema* schemaA = makeSplitCavity();
    OptimizerFunction funcA(schemaA);
    addSplitVariables(funcA, schemaA);
    addStabilityTarget(funcA);
    funcA.lengthGroups() << makeGroup({0, 1}, 0.08);

    Schema* schemaB = makeSplitCavity();
    OptimizerFunction funcB(schemaB);
    addSplitVariables(funcB, schemaB);
    addStabilityTarget(funcB);

    // The stability-center merit uses the ROUND-TRIP parameter
    // (A+D)/2 = 2*g1*g2 - 1 with g = 1 - L/R: here g = 1 - 0.08/0.05
    // = -0.6 on both planes, so (A+D)/2 = 2*0.36 - 1 = -0.28 and the
    // merit is 2 * 0.28^2 = 0.1568.
    double meritA = funcA.evaluate({0.03, 0.999, 0.05, 0.05});
    double meritB = funcB.evaluate({0.03, 0.05, 0.05, 0.05});
    TEST_LOG_DOUBLE(meritA)
    TEST_LOG_DOUBLE(meritB)
    ASSERT_NEAR_DBL(meritA, 0.1568, 1e-9)
    ASSERT_NEAR_DBL(meritA, meritB, 1e-12)

    delete schemaA;
    delete schemaB;
}

TEST_GROUP("OptimizerLengthGroupDependentValue",
           ADD_TEST(dependent_value_is_computed_from_total),
           )
} // namespace DependentValue

//------------------------------------------------------------------------------
//                        (c) out-of-range dependent is penalized
//------------------------------------------------------------------------------

namespace OutOfRange {

TEST_METHOD(out_of_range_dependent_returns_group_penalty)
{
    Schema* schema = makeSplitCavity();
    OptimizerFunction func(schema);
    // d2 in [1, 45] mm: the dependent is allowed at most 45 mm.
    addSplitVariables(func, schema, 0.045);
    addStabilityTarget(func);
    func.lengthGroups() << makeGroup({0, 1}, 0.08);

    // d1 = 30 mm pushes the dependent to 50 mm, 5 mm above its max.
    // Overshoot normalized by the span (45 - 1 = 44 mm):
    // penalty = 1e4 + 1e5 * (5/44)^2 = 11291.3223...
    double merit = func.evaluate({0.03, 0.0, 0.05, 0.05});
    double over = 0.005 / 0.044;
    double expected = 1e4 + 1e5 * over * over;
    TEST_LOG_DOUBLE(merit)
    TEST_LOG_DOUBLE(expected)
    ASSERT_NEAR_DBL(merit, expected, 1e-6)

    // d1 = 79.5 mm pushes the dependent to 0.5 mm, below its 1 mm min.
    // penalty = 1e4 + 1e5 * (0.5/44)^2 = 10012.9132...
    merit = func.evaluate({0.0795, 0.0, 0.05, 0.05});
    over = 0.0005 / 0.044;
    expected = 1e4 + 1e5 * over * over;
    TEST_LOG_DOUBLE(merit)
    TEST_LOG_DOUBLE(expected)
    ASSERT_NEAR_DBL(merit, expected, 1e-6)

    delete schema;
}

TEST_METHOD(run_steers_away_from_out_of_range_dependent)
{
    Schema* schema = makeSplitCavity();
    OptimizerFunction func(schema);
    addSplitVariables(func, schema, 0.045);
    addStabilityTarget(func);
    func.lengthGroups() << makeGroup({0, 1}, 0.08);
    // Start with d1 = 20 mm: the dependent would be 60 mm, above its
    // 45 mm max, so the start point itself is penalized and the search
    // must move d1 to >= 35 mm.
    Z::Param::setSi(schema->element("d1")->param("L"), 0.02);

    ASSERT_IS_TRUE(func.validate().isEmpty())
    func.run(500, nullptr, nullptr);
    ASSERT_IS_TRUE(func.ok())
    ASSERT_IS_TRUE(func.hasResult())
    const auto& res = func.lastResult();
    TEST_LOG_DOUBLE(res.bestMerit)
    TEST_LOG_DOUBLE(res.bestValuesSi.at(0))
    TEST_LOG_DOUBLE(res.bestValuesSi.at(1))
    ASSERT_IS_TRUE(res.bestMerit < 1e-9)
    ASSERT_IS_TRUE(res.bestValuesSi.at(1) <= 0.045 + 1e-12)
    ASSERT_NEAR_DBL(res.bestValuesSi.at(0) + res.bestValuesSi.at(1), 0.08, 1e-12)

    delete schema;
}

TEST_GROUP("OptimizerLengthGroupOutOfRange",
           ADD_TEST(out_of_range_dependent_returns_group_penalty),
           ADD_TEST(run_steers_away_from_out_of_range_dependent),
           )
} // namespace OutOfRange

//------------------------------------------------------------------------------
//                        (d) save/load round-trip
//------------------------------------------------------------------------------

namespace Storable {

TEST_METHOD(group_survives_storable_round_trip)
{
    Schema schema;
    schema.setTripType(TripType::SW);
    auto* m1 = new ElemCurveMirror;
    m1->setLabel("M1");
    Z::Param::setSi(m1->param("R"), 50e-3);
    Z::Param::setSi(m1->param("Alpha"), 0.0);
    auto* d1 = new ElemEmptyRange;
    d1->setLabel("d1");
    Z::Param::setSi(d1->paramLength(), 40e-3);
    auto* d2 = new ElemEmptyRange;
    d2->setLabel("d2");
    Z::Param::setSi(d2->paramLength(), 40e-3);
    auto* m2 = new ElemCurveMirror;
    m2->setLabel("M2");
    Z::Param::setSi(m2->param("R"), 50e-3);
    Z::Param::setSi(m2->param("Alpha"), 0.0);
    schema.insertElements({m1, d1, d2, m2}, -1, Arg::RaiseEvents(false));

    OptimizerWindow win1(&schema);
    auto* func1 = win1.function();
    func1->variables() << makeVariable(schema.element("d1"), "L", 0.001, 0.2);
    func1->variables() << makeVariable(schema.element("d2"), "L", 0.001, 0.2);
    func1->variables() << makeVariable(schema.element("M1"), "R", 0.001, 0.1);
    func1->variables() << makeVariable(schema.element("M2"), "R", 0.001, 0.1);
    func1->lengthGroups() << makeGroup({0, 1}, 0.08);

    QJsonObject root;
    ASSERT_IS_TRUE(win1.storableWrite(root, nullptr))

    // A fresh window on an identical schema reads the group back.
    Schema schema2;
    schema2.setTripType(TripType::SW);
    auto* n1 = new ElemCurveMirror;
    n1->setLabel("M1");
    Z::Param::setSi(n1->param("R"), 50e-3);
    Z::Param::setSi(n1->param("Alpha"), 0.0);
    auto* e1 = new ElemEmptyRange;
    e1->setLabel("d1");
    Z::Param::setSi(e1->paramLength(), 40e-3);
    auto* e2 = new ElemEmptyRange;
    e2->setLabel("d2");
    Z::Param::setSi(e2->paramLength(), 40e-3);
    auto* n2 = new ElemCurveMirror;
    n2->setLabel("M2");
    Z::Param::setSi(n2->param("R"), 50e-3);
    Z::Param::setSi(n2->param("Alpha"), 0.0);
    schema2.insertElements({n1, e1, e2, n2}, -1, Arg::RaiseEvents(false));

    OptimizerWindow win2(&schema2);
    ASSERT_IS_TRUE(win2.storableRead(root, nullptr))
    const auto& groups = win2.function()->lengthGroups();
    ASSERT_EQ_INT(groups.size(), 1)
    ASSERT_EQ_INT(groups.at(0).members.size(), 2)
    ASSERT_EQ_INT(groups.at(0).members.at(0), 0)
    ASSERT_EQ_INT(groups.at(0).members.at(1), 1)
    ASSERT_NEAR_DBL(groups.at(0).totalSi, 0.08, 1e-12)
    ASSERT_IS_TRUE(groups.at(0).enabled)

    // Old files have no "lengthGroups" key: they load as "no group".
    QJsonObject oldRoot = root;
    auto funcJson = oldRoot["function"].toObject();
    funcJson.remove("lengthGroups");
    oldRoot["function"] = funcJson;
    Schema schema3;
    schema3.setTripType(TripType::SW);
    auto* o1 = new ElemCurveMirror;
    o1->setLabel("M1");
    Z::Param::setSi(o1->param("R"), 50e-3);
    Z::Param::setSi(o1->param("Alpha"), 0.0);
    auto* f1 = new ElemEmptyRange;
    f1->setLabel("d1");
    Z::Param::setSi(f1->paramLength(), 40e-3);
    auto* f2 = new ElemEmptyRange;
    f2->setLabel("d2");
    Z::Param::setSi(f2->paramLength(), 40e-3);
    auto* o2 = new ElemCurveMirror;
    o2->setLabel("M2");
    Z::Param::setSi(o2->param("R"), 50e-3);
    Z::Param::setSi(o2->param("Alpha"), 0.0);
    schema3.insertElements({o1, f1, f2, o2}, -1, Arg::RaiseEvents(false));
    OptimizerWindow win3(&schema3);
    ASSERT_IS_TRUE(win3.storableRead(oldRoot, nullptr))
    ASSERT_IS_TRUE(win3.function()->lengthGroups().isEmpty())
}

TEST_GROUP("OptimizerLengthGroupStorable",
           ADD_TEST(group_survives_storable_round_trip),
           )
} // namespace Storable

//------------------------------------------------------------------------------
//                        (e) no group: behaviour unchanged
//------------------------------------------------------------------------------

namespace NoGroup {

TEST_METHOD(disabled_middle_variable_does_not_shift_values)
{
    // Regression for the evaluation indexing: values are read by
    // variable-table index, so a disabled variable in the middle of the
    // table must not shift the values of the variables after it. With
    // the old sequential read, R1 would have received the d2 slot
    // (0.999) and the merit would come out different.
    Schema* schemaA = makeSplitCavity();
    OptimizerFunction funcA(schemaA);
    addSplitVariables(funcA, schemaA);
    addStabilityTarget(funcA);
    funcA.variables()[1].enabled = false;  // d2 stays at 40 mm.

    Schema* schemaB = makeSplitCavity();
    OptimizerFunction funcB(schemaB);
    addSplitVariables(funcB, schemaB);
    addStabilityTarget(funcB);

    // Both evaluate the cavity (d1, d2, R1, R2) = (40, 40, 50, 50) mm:
    // round-trip (A+D)/2 = 2*(1-0.08/0.05)^2 - 1 = -0.28 on both planes,
    // merit = 2 * 0.28^2 = 0.1568.
    double meritA = funcA.evaluate({0.04, 0.999, 0.05, 0.05});
    double meritB = funcB.evaluate({0.04, 0.04, 0.05, 0.05});
    TEST_LOG_DOUBLE(meritA)
    TEST_LOG_DOUBLE(meritB)
    ASSERT_NEAR_DBL(meritA, 0.1568, 1e-9)
    ASSERT_NEAR_DBL(meritA, meritB, 1e-12)

    delete schemaA;
    delete schemaB;
}

TEST_METHOD(run_without_group_is_unchanged)
{
    // Same setup as the pre-group test: the unconstrained run must still
    // find the g = 0 surface close to the start.
    Schema* schema = makeSplitCavity();
    OptimizerFunction func(schema);
    addSplitVariables(func, schema);
    addStabilityTarget(func);
    ASSERT_IS_TRUE(func.validate().isEmpty())
    func.run(500, nullptr, nullptr);
    ASSERT_IS_TRUE(func.ok())
    ASSERT_IS_TRUE(func.hasResult())
    const auto& res = func.lastResult();
    TEST_LOG_DOUBLE(res.bestMerit)
    ASSERT_IS_TRUE(res.bestMerit < 1e-9)
    // Without the group the total length is free to move (it does: the
    // optimum is near L = 86.7 mm, R1 = 53.9, R2 = 47.6 mm, as in the
    // original spherical_symm test).
    double L = res.bestValuesSi.at(0) + res.bestValuesSi.at(1);
    TEST_LOG_DOUBLE(L)
    ASSERT_IS_TRUE(L > 0.075 && L < 0.100)

    delete schema;
}

TEST_GROUP("OptimizerLengthGroupNoGroup",
           ADD_TEST(disabled_middle_variable_does_not_shift_values),
           ADD_TEST(run_without_group_is_unchanged),
           )
} // namespace NoGroup

//------------------------------------------------------------------------------
//                        (f) invalid groups are rejected
//------------------------------------------------------------------------------

namespace Validation {

OptimizerFunction* freshFunc(Schema*& schemaOut)
{
    Schema* schema = makeSplitCavity();
    schemaOut = schema;
    auto* func = new OptimizerFunction(schema);
    addSplitVariables(*func, schema);
    addStabilityTarget(*func);
    return func;
}

TEST_METHOD(rejects_too_few_enabled_members)
{
    Schema* schema = nullptr;
    auto* func = freshFunc(schema);
    func->lengthGroups() << makeGroup({0}, 0.08);
    QString err = func->validate();
    TEST_LOG(err)
    ASSERT_IS_FALSE(err.isEmpty())
    ASSERT_IS_TRUE(err.contains(QStringLiteral("2")))
    delete func;
    delete schema;
}

TEST_METHOD(rejects_total_not_above_min_sum)
{
    Schema* schema = nullptr;
    auto* func = freshFunc(schema);
    // Total 2 mm equals the sum of the members' minima (1 + 1 mm).
    func->lengthGroups() << makeGroup({0, 1}, 0.002);
    QString err = func->validate();
    TEST_LOG(err)
    ASSERT_IS_FALSE(err.isEmpty())
    ASSERT_IS_TRUE(err.contains(QStringLiteral("下限")))
    delete func;
    delete schema;
}

TEST_METHOD(rejects_total_not_below_max_sum)
{
    Schema* schema = nullptr;
    auto* func = freshFunc(schema);
    // Total 400 mm equals the sum of the members' maxima (200 + 200 mm).
    func->lengthGroups() << makeGroup({0, 1}, 0.4);
    QString err = func->validate();
    TEST_LOG(err)
    ASSERT_IS_FALSE(err.isEmpty())
    ASSERT_IS_TRUE(err.contains(QStringLiteral("上限")))
    delete func;
    delete schema;
}

TEST_METHOD(rejects_discrete_member)
{
    Schema* schema = nullptr;
    auto* func = freshFunc(schema);
    func->variables()[0].mode = OptimizerFunction::VarMode::Discrete;
    func->variables()[0].candidatesSi = {0.02, 0.04, 0.06};
    func->lengthGroups() << makeGroup({0, 1}, 0.08);
    QString err = func->validate();
    TEST_LOG(err)
    ASSERT_IS_FALSE(err.isEmpty())
    ASSERT_IS_TRUE(err.contains(QStringLiteral("离散")))
    delete func;
    delete schema;
}

TEST_METHOD(rejects_non_length_member)
{
    Schema* schema = nullptr;
    auto* func = freshFunc(schema);
    // Member 2 is M1.R (a curvature, not a length).
    func->lengthGroups() << makeGroup({0, 2}, 0.08);
    QString err = func->validate();
    TEST_LOG(err)
    ASSERT_IS_FALSE(err.isEmpty())
    ASSERT_IS_TRUE(err.contains(QStringLiteral("长度")))
    delete func;
    delete schema;
}

TEST_METHOD(rejects_duplicate_member)
{
    Schema* schema = nullptr;
    auto* func = freshFunc(schema);
    func->lengthGroups() << makeGroup({0, 0, 1}, 0.08);
    QString err = func->validate();
    TEST_LOG(err)
    ASSERT_IS_FALSE(err.isEmpty())
    ASSERT_IS_TRUE(err.contains(QStringLiteral("重复")))
    delete func;
    delete schema;
}

TEST_METHOD(rejects_member_in_two_groups)
{
    Schema* schema = nullptr;
    auto* func = freshFunc(schema);
    func->lengthGroups() << makeGroup({0, 1}, 0.08);
    func->lengthGroups() << makeGroup({1, 2}, 0.08);
    QString err = func->validate();
    TEST_LOG(err)
    ASSERT_IS_FALSE(err.isEmpty())
    ASSERT_IS_TRUE(err.contains(QStringLiteral("另一个")))
    delete func;
    delete schema;
}

TEST_GROUP("OptimizerLengthGroupValidation",
           ADD_TEST(rejects_too_few_enabled_members),
           ADD_TEST(rejects_total_not_above_min_sum),
           ADD_TEST(rejects_total_not_below_max_sum),
           ADD_TEST(rejects_discrete_member),
           ADD_TEST(rejects_non_length_member),
           ADD_TEST(rejects_duplicate_member),
           ADD_TEST(rejects_member_in_two_groups),
           )
} // namespace Validation

//------------------------------------------------------------------------------

TEST_GROUP("OptimizerLengthGroup",
           ADD_GROUP(TotalFixed),
           ADD_GROUP(DependentValue),
           ADD_GROUP(OutOfRange),
           ADD_GROUP(Storable),
           ADD_GROUP(NoGroup),
           ADD_GROUP(Validation),
           )

} // namespace OptimizerLengthGroupTests
} // namespace Tests
} // namespace Z
