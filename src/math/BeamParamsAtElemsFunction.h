#ifndef BEAM_PARAMS_AT_ELEMS_FUNCTION_H
#define BEAM_PARAMS_AT_ELEMS_FUNCTION_H

#include "TableFunction.h"

class BeamParamsAtElemsFunction : public TableFunction
{
public:
    FUNC_ALIAS("BeamParamsAtElems")
    FUNC_NAME(QT_TRANSLATE_NOOP("Function Name", "元件处光束参数"))
    FUNC_ICON(":/toolbar/func_beamdata")
    FUNC_HELP(help_topic())
    static QString help_topic() { return "func_beamdata.html"; }

    BeamParamsAtElemsFunction(Schema *schema);

protected:
    QVector<Z::PointTS> calculatePumpBeforeSchema() override;
    QVector<Z::PointTS> calculateInternal(const ResultElem &resultElem) override;
};

#endif // BEAM_PARAMS_AT_ELEMS_FUNCTION_H
