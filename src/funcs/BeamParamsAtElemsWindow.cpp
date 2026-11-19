#include "BeamParamsAtElemsWindow.h"

BeamParamsAtElemsWindow::BeamParamsAtElemsWindow(Schema* schema) :
    TableFuncWindow(new BeamParamsAtElemsFunction(schema))
{
    _baseTitle = windowTitle();
}

void BeamParamsAtElemsWindow::setRedlightMode(const RedlightReport& report)
{
    auto* func = function();
    if (!func)
        return;
    const bool wasOn = func->redlightMode();
    if (report.ok)
    {
        func->setRedlightData(report);
        setWindowTitle(_baseTitle + QStringLiteral(" — ")
                       + report.modeLabel());
    }
    else
    {
        func->clearRedlightData();
        setWindowTitle(_baseTitle);
    }
    update();
    if (wasOn && !func->redlightMode())
        emit redlightModeCleared();
}

bool BeamParamsAtElemsWindow::redlightMode() const
{
    auto* func = function();
    return func && func->redlightMode();
}

void BeamParamsAtElemsWindow::recalcRequired(Schema* schema)
{
    // The overlay describes the saved file; any schema edit makes
    // it stale, so drop back to the normal display first.
    if (redlightMode())
    {
        RedlightReport empty;
        setRedlightMode(empty);
    }
    TableFuncWindow::recalcRequired(schema);
}
