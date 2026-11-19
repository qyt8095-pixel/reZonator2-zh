#ifndef MISALIGNMENT_CALCULATOR_H
#define MISALIGNMENT_CALCULATOR_H

#include "RoundTripCalculator.h"
#include "../core/CommonTypes.h"

#include <QMap>
#include <QString>

class Element;
class Schema;

/**
    Self-consistent optical axis of a resonator under small mirror tilts.

    For each reference element, builds the augmented 3x3 round-trip product
    from the same RoundTripCalculator list the beam uses (matrsT/matrsS in
    list order, product in list order), with a +2*delta kick at every
    mirror occurrence, and solves (I - M_rt) * v = E_rt per work plane.

    Conventions (see rezonator2-phase1-protocol.md, misalignment section):
      - delta_T > 0 moves the mirror normal toward +T of the unfolded beam
        (the T-axis of the forward-going beam at the mirror); delta_S > 0
        moves it toward +S. The S axis is the global +y (out of the fold
        plane); the T axis is T = S x z of the unfolded beam.
      - the kick on the unfolded ray angle is +2*delta in the same plane,
        on the first AND on the second (return) traversal of a mirror.
        (Verified against an independent folded 3D ray trace: the
        opposite sign on the second pass gives a wildly wrong axis.)
      - the axis is reported at the element's exit face, in the unfolded
        frame: transverse offset x (m) and angle theta (rad) per plane.
      - the axis exists whenever the solve is non-singular, even for
        unstable cavities (no eigenmode is needed); at g = +/-1 there is
        no unique axis and the result is marked singular.
      - only flat and curved mirrors accept a delta tilt; a tilt on any
        other element is rejected by the caller.
*/
class MisalignmentCalculator
{
public:
    /// Delta tilt of one mirror, radians, in the unfolded frame.
    struct Tilt
    {
        double dT = 0.0;
        double dS = 0.0;
    };

    /// Result of one axis evaluation at the reference element.
    struct AxisResult
    {
        bool ok = false;        // false: cannot compute (see error)
        bool singular = false;  // true: solve singular (g = +/-1), no unique axis
        double xT = 0.0;        // m, unfolded frame, at the reference exit face
        double thT = 0.0;       // rad
        double xS = 0.0;        // m
        double thS = 0.0;       // rad
        QString error;
    };

    MisalignmentCalculator(Schema* schema, Element* ref);
    ~MisalignmentCalculator();

    bool ok() const { return _error.isEmpty(); }
    QString error() const { return _error; }
    Element* reference() const { return _ref; }

    /// Re-multiply the round-trip matrices from the current element values.
    /// Call once per mutation, like BeamCalculator::multMatrix().
    void multMatrix(const char* reason);

    /// Axis at the reference element for the given mirror tilts.
    /// `tilts` maps a mirror element to its delta tilt (radians);
    /// elements not in the map are untilted.
    AxisResult calcAxis(const QMap<Element*, Tilt>& tilts);

    /// True when the element is a mirror that accepts a delta tilt
    /// (flat or curved mirror; axicon mirrors have a dynamic matrix
    /// and are not supported).
    static bool isMirror(Element* elem);

private:
    Schema* _schema = nullptr;
    Element* _ref = nullptr;
    RoundTripCalculator* _rt = nullptr;
    QString _error;
};

#endif // MISALIGNMENT_CALCULATOR_H
