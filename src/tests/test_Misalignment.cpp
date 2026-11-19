#include "../core/Schema.h"
#include "../core/Elements.h"
#include "../math/MisalignmentCalculator.h"
#include "../math/RoundTripCalculator.h"
#include "../tests/TestUtils.h"

#include "testing/OriTestBase.h"

#include <cmath>

//------------------------------------------------------------------------------
//  Tests for MisalignmentCalculator (Phase 3 block 3): the self-consistent
//  optical axis of a resonator under small mirror tilts.
//
//  Ground truth used here (all verified against an independent folded 3D
//  ray trace in engineering/tests/folded_axis.py, which uses explicit
//  3D vectors and the exact reflection law, no ABCD at all):
//
//  * Plano-concave cavity M1 flat, d = 800 mm, M2 R = 500 mm, Alpha = 0.
//    Round-trip g = 1 - 2L/R = -2.2 (unstable, but the axis solve is
//    non-singular). With M2 tilted by dT = +1 mrad (normal toward +T),
//    the axis is x = +0.5 mm, theta = 0 at every element: the
//    self-retracing ray is the line through M2's centre of curvature
//    (R*dT, L-R) parallel to M1's normal.
//  * Folded cavity (M2 Alpha = 5 deg, M3 Alpha = 3 deg) with
//    M2 dT = +0.2 mrad, M3 dS = -0.1 mrad: expected axis values are the
//    augmented-3x3 model values, which the folded ray trace confirms
//    (after converting its folded-frame values to the unfolded frame).
//------------------------------------------------------------------------------

namespace Z {
namespace Tests {
namespace MisalignmentTests {

namespace {

/// Plano-concave SW cavity: M1 flat, range d, M2 curved R, Alpha = 0.
Schema* makePlanoConcave(double lengthMm = 800.0, double radiusMm = 500.0)
{
    Schema* schema = new Schema;
    schema->setTripType(TripType::SW);
    auto* m1 = new ElemFlatMirror;
    m1->setLabel("M1");
    auto* d = new ElemEmptyRange;
    d->setLabel("d");
    Z::Param::setSi(d->paramLength(), lengthMm * 1e-3);
    auto* m2 = new ElemCurveMirror;
    m2->setLabel("M2");
    Z::Param::setSi(m2->param("R"), radiusMm * 1e-3);
    Z::Param::setSi(m2->param("Alpha"), 0.0);
    schema->insertElements({m1, d, m2}, -1, Arg::RaiseEvents(false));
    return schema;
}

/// Folded SW cavity: M1 flat, d1, M2 R=500 Alpha=5deg, d2, M3 R=-600
/// Alpha=3deg, d3, M4 R=100000 Alpha=0.
Schema* makeFolded()
{
    Schema* schema = new Schema;
    schema->setTripType(TripType::SW);
    auto* m1 = new ElemFlatMirror;
    m1->setLabel("M1");
    auto* d1 = new ElemEmptyRange;
    d1->setLabel("d1");
    Z::Param::setSi(d1->paramLength(), 300e-3);
    auto* m2 = new ElemCurveMirror;
    m2->setLabel("M2");
    Z::Param::setSi(m2->param("R"), 500e-3);
    Z::Param::setSi(m2->param("Alpha"), 5.0 * M_PI / 180.0);
    auto* d2 = new ElemEmptyRange;
    d2->setLabel("d2");
    Z::Param::setSi(d2->paramLength(), 400e-3);
    auto* m3 = new ElemCurveMirror;
    m3->setLabel("M3");
    Z::Param::setSi(m3->param("R"), -600e-3);
    Z::Param::setSi(m3->param("Alpha"), 3.0 * M_PI / 180.0);
    auto* d3 = new ElemEmptyRange;
    d3->setLabel("d3");
    Z::Param::setSi(d3->paramLength(), 200e-3);
    auto* m4 = new ElemCurveMirror;
    m4->setLabel("M4");
    Z::Param::setSi(m4->param("R"), 100000e-3);
    Z::Param::setSi(m4->param("Alpha"), 0.0);
    schema->insertElements({m1, d1, m2, d2, m3, d3, m4}, -1, Arg::RaiseEvents(false));
    return schema;
}

/// Axis at `refLabel` for the given tilts (radians), in mm / mrad.
MisalignmentCalculator::AxisResult axisAt(Schema* schema, const QString& refLabel,
    const QMap<Element*, MisalignmentCalculator::Tilt>& tilts)
{
    MisalignmentCalculator calc(schema, schema->element(refLabel));
    if (!calc.ok())
    {
        MisalignmentCalculator::AxisResult r;
        r.error = calc.error();
        return r;
    }
    calc.multMatrix("test");
    return calc.calcAxis(tilts);
}

/// Independent fixed-point check: propagate the axis vector through the
/// round trip (plain 2x2 matrices from a fresh RoundTripCalculator, in
/// reverse list order, adding the +2*delta kick after each mirror) and
/// return the largest deviation from the starting vector, in SI units.
/// This does not use MisalignmentCalculator's accumulation at all.
double roundTripResidual(Schema* schema, Element* ref,
    const QMap<Element*, MisalignmentCalculator::Tilt>& tilts,
    const MisalignmentCalculator::AxisResult& axis)
{
    RoundTripCalculator rt(schema, ref);
    rt.calcRoundTrip(false);
    rt.multMatrix("test");
    const auto& matrsT = rt.matrsT();
    const auto& matrsS = rt.matrsS();
    const auto& trip = rt.rawRoundTrip();
    double worst = 0.0;
    for (int plane = 0; plane < 2; plane++)
    {
        const auto& matrs = (plane == 0) ? matrsT : matrsS;
        double x = (plane == 0) ? axis.xT : axis.xS;
        double th = (plane == 0) ? axis.thT : axis.thS;
        double x0 = x, th0 = th;
        // The ray passes the list in reverse order: the product in list
        // order means the last matrix acts first.
        for (int i = matrs.size() - 1; i >= 0; i--)
        {
            const Z::Matrix* m = matrs.at(i);
            double nx = m->A.real() * x + m->B.real() * th;
            double nth = m->C.real() * x + m->D.real() * th;
            x = nx; th = nth;
            Element* elem = trip.at(i).element;
            if (elem && tilts.contains(elem))
            {
                const auto& t = tilts.value(elem);
                th += 2.0 * ((plane == 0) ? t.dT : t.dS);
            }
        }
        worst = std::max(worst, std::fabs(x - x0));
        worst = std::max(worst, std::fabs(th - th0));
    }
    return worst;
}

} // namespace

//------------------------------------------------------------------------------

TEST_METHOD(zero_tilt_gives_zero_axis)
{
    QScopedPointer<Schema> schema(makePlanoConcave());
    QMap<Element*, MisalignmentCalculator::Tilt> noTilts;
    for (Element* elem : schema->activeElements())
    {
        auto res = axisAt(schema.data(), elem->label(), noTilts);
        ASSERT_IS_TRUE(res.ok)
        ASSERT_IS_FALSE(res.singular)
        ASSERT_NEAR_DBL(res.xT, 0.0, 1e-12)
        ASSERT_NEAR_DBL(res.thT, 0.0, 1e-12)
        ASSERT_NEAR_DBL(res.xS, 0.0, 1e-12)
        ASSERT_NEAR_DBL(res.thS, 0.0, 1e-12)
    }
}

TEST_METHOD(single_mirror_tilt_linear_response)
{
    QScopedPointer<Schema> schema(makePlanoConcave());
    Element* m2 = schema->element("M2");

    // dT = +1 mrad: geometric ground truth x = +0.5 mm, theta = 0.
    QMap<Element*, MisalignmentCalculator::Tilt> tilt1;
    tilt1.insert(m2, {1e-3, 0.0});
    auto r1 = axisAt(schema.data(), "M1", tilt1);
    ASSERT_IS_TRUE(r1.ok)
    ASSERT_NEAR_DBL(r1.xT * 1e3, 0.5, 1e-9)
    ASSERT_NEAR_DBL(r1.thT * 1e3, 0.0, 1e-9)
    ASSERT_NEAR_DBL(r1.xS, 0.0, 1e-12)
    ASSERT_NEAR_DBL(r1.thS, 0.0, 1e-12)
    auto r1m2 = axisAt(schema.data(), "M2", tilt1);
    ASSERT_IS_TRUE(r1m2.ok)
    ASSERT_NEAR_DBL(r1m2.xT * 1e3, 0.5, 1e-9)
    ASSERT_NEAR_DBL(r1m2.thT * 1e3, 0.0, 1e-9)

    // Linearity: doubling the tilt doubles the axis, halving halves it.
    QMap<Element*, MisalignmentCalculator::Tilt> tilt2;
    tilt2.insert(m2, {2e-3, 0.0});
    auto r2 = axisAt(schema.data(), "M1", tilt2);
    ASSERT_IS_TRUE(r2.ok)
    ASSERT_NEAR_DBL(r2.xT * 1e3, 1.0, 1e-9)
    ASSERT_NEAR_DBL(r2.thT * 1e3, 0.0, 1e-9)
    QMap<Element*, MisalignmentCalculator::Tilt> tiltHalf;
    tiltHalf.insert(m2, {0.5e-3, 0.0});
    auto rh = axisAt(schema.data(), "M1", tiltHalf);
    ASSERT_IS_TRUE(rh.ok)
    ASSERT_NEAR_DBL(rh.xT * 1e3, 0.25, 1e-9)

    // S-plane tilt acts on the S-plane only, with the same +2*delta kick.
    QMap<Element*, MisalignmentCalculator::Tilt> tiltS;
    tiltS.insert(m2, {0.0, 1e-3});
    auto rs = axisAt(schema.data(), "M1", tiltS);
    ASSERT_IS_TRUE(rs.ok)
    ASSERT_NEAR_DBL(rs.xT, 0.0, 1e-12)
    ASSERT_NEAR_DBL(rs.thT, 0.0, 1e-12)
    ASSERT_NEAR_DBL(rs.xS * 1e3, 0.5, 1e-9)
    ASSERT_NEAR_DBL(rs.thS * 1e3, 0.0, 1e-9)
}

TEST_METHOD(folded_cavity_axis_matches_model)
{
    // Expected values (mm / mrad) from the augmented-3x3 model, confirmed
    // by the independent folded 3D ray trace (see the file header).
    // Tilts: M2 dT = +0.2 mrad, M3 dS = -0.1 mrad.
    struct Expected { const char* label; double xT, thT, xS, thS; };
    const Expected expected[] = {
        {"M1",  0.154577,  0.000000, -0.033581, -0.000000},
        {"d1",  0.154577, -0.000000, -0.033581,  0.000000},
        {"M2",  0.154577, -0.220669, -0.033581,  0.133811},
        {"d2",  0.066309, -0.220669,  0.019944,  0.133811},
        {"M3",  0.066309,  0.000664,  0.019944,  0.000200},
        {"d3",  0.066442,  0.000664,  0.019984,  0.000200},
        {"M4",  0.066442, -0.000664,  0.019984, -0.000200},
    };
    QScopedPointer<Schema> schema(makeFolded());
    QMap<Element*, MisalignmentCalculator::Tilt> tilts;
    tilts.insert(schema->element("M2"), {0.2e-3, 0.0});
    tilts.insert(schema->element("M3"), {0.0, -0.1e-3});
    for (const auto& e : expected)
    {
        auto res = axisAt(schema.data(), QString::fromLatin1(e.label), tilts);
        TEST_LOG(QStringLiteral("%1: xT=%2 thT=%3 xS=%4 thS=%5")
            .arg(e.label).arg(res.xT * 1e3).arg(res.thT * 1e3)
            .arg(res.xS * 1e3).arg(res.thS * 1e3))
        ASSERT_IS_TRUE(res.ok)
        ASSERT_NEAR_DBL(res.xT * 1e3, e.xT, 1e-4)
        ASSERT_NEAR_DBL(res.thT * 1e3, e.thT, 1e-4)
        ASSERT_NEAR_DBL(res.xS * 1e3, e.xS, 1e-4)
        ASSERT_NEAR_DBL(res.thS * 1e3, e.thS, 1e-4)
    }
}

TEST_METHOD(round_trip_self_consistency_residual)
{
    // The axis must be a fixed point of the round trip: propagating it
    // once around (with the kicks) returns it, to float precision.
    {
        QScopedPointer<Schema> schema(makePlanoConcave());
        QMap<Element*, MisalignmentCalculator::Tilt> tilts;
        tilts.insert(schema->element("M2"), {1e-3, 0.5e-3});
        for (Element* elem : schema->activeElements())
        {
            auto res = axisAt(schema.data(), elem->label(), tilts);
            ASSERT_IS_TRUE(res.ok)
            double resid = roundTripResidual(schema.data(), elem, tilts, res);
            TEST_LOG(QStringLiteral("residual at %1: %2").arg(elem->label()).arg(resid))
            ASSERT_NEAR_DBL(resid, 0.0, 1e-9)
        }
    }
    {
        QScopedPointer<Schema> schema(makeFolded());
        QMap<Element*, MisalignmentCalculator::Tilt> tilts;
        tilts.insert(schema->element("M2"), {0.2e-3, 0.0});
        tilts.insert(schema->element("M3"), {0.0, -0.1e-3});
        for (Element* elem : schema->activeElements())
        {
            auto res = axisAt(schema.data(), elem->label(), tilts);
            ASSERT_IS_TRUE(res.ok)
            double resid = roundTripResidual(schema.data(), elem, tilts, res);
            TEST_LOG(QStringLiteral("residual at %1: %2").arg(elem->label()).arg(resid))
            ASSERT_NEAR_DBL(resid, 0.0, 1e-9)
        }
    }
}

TEST_METHOD(singular_at_stability_edge)
{
    // Flat-flat cavity: round-trip g = +1, (I - M) is singular.
    {
        QScopedPointer<Schema> schema(new Schema);
        schema->setTripType(TripType::SW);
        auto* m1 = new ElemFlatMirror;
        m1->setLabel("M1");
        auto* d = new ElemEmptyRange;
        d->setLabel("d");
        Z::Param::setSi(d->paramLength(), 800e-3);
        auto* m2 = new ElemFlatMirror;
        m2->setLabel("M2");
        schema->insertElements({m1, d, m2}, -1, Arg::RaiseEvents(false));
        MisalignmentCalculator calc(schema.data(), schema->element("M1"));
        ASSERT_IS_TRUE(calc.ok())
        auto res = calc.calcAxis({});
        ASSERT_IS_FALSE(res.ok)
        ASSERT_IS_TRUE(res.singular)
    }
    // Plano-concave with L = R: round-trip g = 1 - 2L/R = -1, the other edge.
    {
        QScopedPointer<Schema> schema(makePlanoConcave(500.0, 500.0));
        MisalignmentCalculator calc(schema.data(), schema->element("M1"));
        ASSERT_IS_TRUE(calc.ok())
        auto res = calc.calcAxis({});
        ASSERT_IS_FALSE(res.ok)
        ASSERT_IS_TRUE(res.singular)
    }
    // Unstable but away from the edge (g = -2.2) still has an axis.
    {
        QScopedPointer<Schema> schema(makePlanoConcave());
        auto res = axisAt(schema.data(), "M1", {});
        ASSERT_IS_TRUE(res.ok)
        ASSERT_IS_FALSE(res.singular)
    }
}

TEST_METHOD(single_pass_has_no_axis)
{
    Schema schema;
    schema.setTripType(TripType::SP);
    schema.insertElements({new ElemEmptyRange}, -1, Arg::RaiseEvents(true));
    MisalignmentCalculator calc(&schema, schema.element(0));
    ASSERT_IS_FALSE(calc.ok())
}

TEST_METHOD(is_mirror)
{
    QScopedPointer<Element> flat(new ElemFlatMirror);
    QScopedPointer<Element> curved(new ElemCurveMirror);
    QScopedPointer<Element> range(new ElemEmptyRange);
    QScopedPointer<Element> lens(new ElemThinLens);
    ASSERT_IS_TRUE(MisalignmentCalculator::isMirror(flat.data()))
    ASSERT_IS_TRUE(MisalignmentCalculator::isMirror(curved.data()))
    ASSERT_IS_FALSE(MisalignmentCalculator::isMirror(range.data()))
    ASSERT_IS_FALSE(MisalignmentCalculator::isMirror(lens.data()))
    ASSERT_IS_FALSE(MisalignmentCalculator::isMirror(nullptr))
}

//------------------------------------------------------------------------------

TEST_GROUP("Misalignment",
    ADD_TEST(zero_tilt_gives_zero_axis),
    ADD_TEST(single_mirror_tilt_linear_response),
    ADD_TEST(folded_cavity_axis_matches_model),
    ADD_TEST(round_trip_self_consistency_residual),
    ADD_TEST(singular_at_stability_edge),
    ADD_TEST(single_pass_has_no_axis),
    ADD_TEST(is_mirror),
)
} // namespace MisalignmentTests
} // namespace Tests
} // namespace Z
