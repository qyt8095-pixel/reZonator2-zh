#include "BeamParamsAtElemsFunction.h"

#include "BeamCalculator.h"

#include <QApplication>
#include <QtMath>

BeamParamsAtElemsFunction::BeamParamsAtElemsFunction(Schema *schema) : TableFunction(schema)
{
    _columns = {
        ColumnDef {
            .label = "W",
            .title = qApp->tr("光束半径", "Table function column"),
            .dim = Z::Dims::linear(),
            .hint = ColumnDef::hintBeamsize,
        },
        ColumnDef {
            .label = "R",
            .title = qApp->tr("波前曲率半径", "Table function column"),
            .dim = Z::Dims::linear(),
        },
        ColumnDef {
            .label = "V",
            .title = qApp->tr("半发散角", "Table function column"),
            .dim = Z::Dims::angular(),
        },
        ColumnDef {
            .label = "X",
            .title = qApp->tr("光轴偏移", "Table function column"),
            .dim = Z::Dims::linear(),
        }
    };
}

void BeamParamsAtElemsFunction::setRedlightData(const RedlightReport& report)
{
    _redlightMode = report.ok;
    _redlightNm = report.redNm;
    _hotlightNm = report.hotNm;
    _redlightPath = report.path;
    _redlightRows = report.rows;
}

void BeamParamsAtElemsFunction::clearRedlightData()
{
    _redlightMode = false;
    _redlightPath.clear();
    _redlightRows.clear();
}

QVector<Z::PointTS> BeamParamsAtElemsFunction::redlightValues(const ResultElem& resultElem) const
{
    const double nan = qQNaN();
    const QVector<Z::PointTS> na = {
        Z::PointTS(nan, nan),
        Z::PointTS(nan, nan),
        Z::PointTS(nan, nan),
        Z::PointTS(nan, nan),
    };
    // The red-light report holds one exit-plane value per element.
    // Only exit-side result rows carry it; entrance-side rows and
    // sub-positions inside a range/medium have no red value.
    switch (resultElem.pos)
    {
    case ResultPosition::ELEMENT:
    case ResultPosition::RIGHT:
    case ResultPosition::IFACE_RIGHT:
    case ResultPosition::RIGHT_INSIDE:
        break;
    default:
        return na;
    }
    const auto it = _redlightRows.find(resultElem.elem->label());
    if (it == _redlightRows.end())
        return na;
    return {
        Z::PointTS(it->w633T, it->w633S),
        Z::PointTS(nan, nan),
        Z::PointTS(nan, nan),
        Z::PointTS(it->x633T, it->x633S),
    };
}

QVector<Z::PointTS> BeamParamsAtElemsFunction::calculatePumpBeforeSchema()
{
    if (_redlightMode)
    {
        // The pump row is the input beam before the schema; the
        // red-light report has no value for it.
        const double nan = qQNaN();
        return {
            Z::PointTS(nan, nan),
            Z::PointTS(nan, nan),
            Z::PointTS(nan, nan),
            Z::PointTS(nan, nan),
        };
    }
    Z::Matrix unity;
    BeamResult beamT = _beamCalc->pumpCalc()->calcT(unity, 1);
    BeamResult beamS = _beamCalc->pumpCalc()->calcS(unity, 1);
    return {
        Z::PointTS(beamT.beamRadius, beamS.beamRadius),
        Z::PointTS(beamT.frontRadius, beamS.frontRadius),
        Z::PointTS(beamT.halfAngle, beamS.halfAngle),
        Z::PointTS(0.0, 0.0),
    };
}

QVector<Z::PointTS> BeamParamsAtElemsFunction::calculateInternal(const ResultElem &resultElem)
{
    if (_redlightMode)
        return redlightValues(resultElem);

    _beamCalc->setPlane(Z::T);
    BeamResult beamT = _beamCalc->calc();

    _beamCalc->setPlane(Z::S);
    BeamResult beamS = _beamCalc->calc();

    return {
        Z::PointTS(beamT.beamRadius, beamS.beamRadius),
        Z::PointTS(beamT.frontRadius, beamS.frontRadius),
        Z::PointTS(beamT.halfAngle, beamS.halfAngle),
        // The hot eigenmode axis is the reference: offset is zero
        // for an aligned cavity.
        Z::PointTS(0.0, 0.0),
    };
}
