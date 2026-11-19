#ifndef BEAM_PARAMS_AT_ELEMS_FUNCTION_H
#define BEAM_PARAMS_AT_ELEMS_FUNCTION_H

#include "TableFunction.h"
#include "../funcs/RedlightData.h"

#include <QMap>

class BeamParamsAtElemsFunction : public TableFunction
{
public:
    FUNC_ALIAS("BeamParamsAtElems")
    FUNC_NAME(QT_TRANSLATE_NOOP("Function Name", "元件处光束参数"))
    FUNC_ICON(":/toolbar/func_beamdata")
    FUNC_HELP(help_topic())
    static QString help_topic() { return "func_beamdata.html"; }

    BeamParamsAtElemsFunction(Schema *schema);

    /// Red-light overlay (Phase 4 follow-up): when on, the W column
    /// shows the 632.8 nm beam radius from a ``run_redlight.py``
    /// report and the X column its axis offset, instead of the
    /// 1064 nm eigenmode values. R and V have no red-light values
    /// and render as "N/A". The overlay is a pure display swap:
    /// it never changes the schema, and it is cleared as soon as
    /// the schema is recalculated (the report describes the saved
    /// file, so any edit makes it stale).
    void setRedlightData(const RedlightReport& report);
    void clearRedlightData();
    bool redlightMode() const { return _redlightMode; }
    QString redlightPath() const { return _redlightPath; }
    double redlightNm() const { return _redlightNm; }
    double hotlightNm() const { return _hotlightNm; }

protected:
    QVector<Z::PointTS> calculatePumpBeforeSchema() override;
    QVector<Z::PointTS> calculateInternal(const ResultElem &resultElem) override;

private:
    bool _redlightMode = false;
    double _redlightNm = 632.8;
    double _hotlightNm = 1064.0;
    QString _redlightPath;
    QMap<QString, RedlightRow> _redlightRows;

    QVector<Z::PointTS> redlightValues(const ResultElem& resultElem) const;
};

#endif // BEAM_PARAMS_AT_ELEMS_FUNCTION_H
