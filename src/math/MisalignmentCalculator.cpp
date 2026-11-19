#include "MisalignmentCalculator.h"

#include "../core/Element.h"
#include "../core/Schema.h"

#include <cmath>

namespace {

// Determinant threshold for the (I - M) solve. The matrix entries are
// O(1..10); a determinant below this is exact singularity in practice
// (at g = +1 the determinant is 2*(1-g) = 0 up to float noise).
constexpr double DET_EPS = 1e-12;

// A stability parameter this close to +/-1 means the cavity sits on the
// stability edge: the axis is not unique (g = +1) or is meaningless
// (g = -1, the solve is ill-conditioned). Report singular instead.
constexpr double EDGE_EPS = 1e-9;

/// One plane of the augmented round-trip product.
///
/// Accumulates P = A_1 * A_2 * ... * A_n in list order (the same order
/// RoundTripCalculator::multMatrix uses), where each augmented matrix is
///     A_i = | m_i  e_i |   m_i: 2x2 ABCD matrix, e_i = (0, kick)
///           | 0    1   |
/// so P = | M  E | with M the 2x2 round-trip matrix and E the 2-vector of
///      | 0  1 |    accumulated kicks. Multiplying on the right by the
/// next A gives M' = M*m and E' = M*e + E.
struct AugmentedPlane
{
    // 2x2 round-trip matrix (real parts only; see calcAxis).
    double a = 1.0, b = 0.0, c = 0.0, d = 1.0;
    // Accumulated displacement column.
    double ex = 0.0, eth = 0.0;

    void apply(double ma, double mb, double mc, double md, double kick)
    {
        // E' = M * (0, kick) + E = (b*kick + ex, d*kick + eth)
        // M' = M * m
        double nex = b * kick + ex;
        double neth = d * kick + eth;
        double na = a * ma + b * mc;
        double nb = a * mb + b * md;
        double nc = c * ma + d * mc;
        double nd = c * mb + d * md;
        ex = nex; eth = neth;
        a = na; b = nb; c = nc; d = nd;
    }

    double g() const { return 0.5 * (a + d); }

    /// Solve (I - M) * v = E. Returns false when singular.
    bool solve(double& x, double& th) const
    {
        double ia = 1.0 - a, ib = -b, ic = -c, id = 1.0 - d;
        double det = ia * id - ib * ic;
        if (std::fabs(det) < DET_EPS)
            return false;
        x = (id * ex - ib * eth) / det;
        th = (-ic * ex + ia * eth) / det;
        return std::isfinite(x) && std::isfinite(th);
    }
};

} // namespace

//------------------------------------------------------------------------------
//                             MisalignmentCalculator
//------------------------------------------------------------------------------

MisalignmentCalculator::MisalignmentCalculator(Schema* schema, Element* ref)
    : _schema(schema), _ref(ref)
{
    if (!schema || !ref)
    {
        _error = QStringLiteral("misalignment: no schema or reference element");
        return;
    }
    if (schema->isSP())
    {
        // A single-pass schema has no round trip, so there is no
        // self-consistent axis at all.
        _error = QStringLiteral("misalignment: single-pass schemas have no round-trip axis");
        return;
    }
    _rt = new RoundTripCalculator(schema, ref);
    _rt->calcRoundTrip(false);
    if (_rt->isEmpty())
    {
        _error = QStringLiteral("misalignment: empty round-trip for element '%1'")
            .arg(ref->label());
        return;
    }
    _rt->multMatrix("MisalignmentCalculator");
}

MisalignmentCalculator::~MisalignmentCalculator()
{
    delete _rt;
}

void MisalignmentCalculator::multMatrix(const char* reason)
{
    if (_rt)
        _rt->multMatrix(reason);
}

bool MisalignmentCalculator::isMirror(Element* elem)
{
    if (!elem)
        return false;
    const QString t = elem->type();
    return t == QLatin1String("ElemFlatMirror")
        || t == QLatin1String("ElemCurveMirror");
}

MisalignmentCalculator::AxisResult MisalignmentCalculator::calcAxis(
    const QMap<Element*, Tilt>& tilts)
{
    AxisResult res;
    if (!_rt || !_rt->matrsT().size())
    {
        res.error = _error.isEmpty()
            ? QStringLiteral("misalignment: round-trip is not calculated")
            : _error;
        return res;
    }
    const auto& matrsT = _rt->matrsT();
    const auto& matrsS = _rt->matrsS();
    const auto& trip = _rt->rawRoundTrip();
    if (matrsT.size() != matrsS.size()
        || matrsT.size() != trip.size())
    {
        res.error = QStringLiteral(
            "misalignment: round-trip matrix list is inconsistent (%1/%2/%3)")
            .arg(matrsT.size()).arg(matrsS.size()).arg(trip.size());
        return res;
    }

    AugmentedPlane planeT, planeS;
    for (int i = 0; i < matrsT.size(); i++)
    {
        const Z::Matrix* mT = matrsT.at(i);
        const Z::Matrix* mS = matrsS.at(i);
        if (!mT || !mS || !mT->isReal() || !mS->isReal())
        {
            res.error = QStringLiteral(
                "misalignment: element '%1' has a complex round-trip matrix, "
                "no real axis is defined")
                .arg(trip.at(i).element
                    ? trip.at(i).element->label() : QStringLiteral("?"));
            return res;
        }
        Element* elem = trip.at(i).element;
        double kickT = 0.0, kickS = 0.0;
        if (elem && tilts.contains(elem))
        {
            const Tilt& t = tilts.value(elem);
            // Mirror tilt: the unfolded ray angle gets +2*delta in the
            // same plane, on every traversal (first and return pass).
            kickT = 2.0 * t.dT;
            kickS = 2.0 * t.dS;
        }
        planeT.apply(mT->A.real(), mT->B.real(), mT->C.real(), mT->D.real(), kickT);
        planeS.apply(mS->A.real(), mS->B.real(), mS->C.real(), mS->D.real(), kickS);
    }

    // Stability edge: no unique axis. g = +1 makes (I - M) singular
    // (det = 2*(1-g) = 0); g = -1 is the other edge of the stable
    // interval, where the axis is not meaningful either. Unstable
    // cavities (|g| > 1) still have a well-defined axis, so only the
    // neighbourhood of +/-1 is singular, not the whole |g| >= 1 range.
    if (std::fabs(std::fabs(planeT.g()) - 1.0) <= EDGE_EPS
        || std::fabs(std::fabs(planeS.g()) - 1.0) <= EDGE_EPS)
    {
        res.singular = true;
        return res;
    }
    double xT = 0, thT = 0, xS = 0, thS = 0;
    if (!planeT.solve(xT, thT) || !planeS.solve(xS, thS))
    {
        res.singular = true;
        return res;
    }
    res.ok = true;
    res.xT = xT; res.thT = thT;
    res.xS = xS; res.thS = thS;
    return res;
}
