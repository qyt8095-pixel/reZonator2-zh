#include "CalcManager.h"

#include "../core/Protocol.h"
#include "../funcs/BeamVariationWindow.h"
#include "../funcs/CausticWindow.h"
#include "../funcs/CustomPlotFuncWindow.h"
#include "../funcs/CustomTableFuncWindow.h"
#include "../funcs/EngineeringBackend.h"
#include "../funcs/InfoFuncWindow.h"
#include "../funcs/PlotFuncWindow.h"
#include "../funcs/PlotFuncWindowV2.h"
#include "../funcs/MultibeamCausticWindow.h"
#include "../funcs/MultirangeCausticWindow.h"
#include "../funcs/OptimizerWindow.h"
#include "../funcs/EngineeringHubDialog.h"
#include "../funcs/RedlightData.h"
#include "../funcs/StabilityMapWindow.h"
#include "../funcs/StabilityMap2DWindow.h"
#include "../funcs/BeamParamsAtElemsWindow.h"
#include "../math/BeamVariationFunction.h"
#include "../math/CausticFunction.h"
#include "../math/CustomPlotFunction.h"
#include "../math/CustomTableFunction.h"
#include "../math/InfoFunctions.h"
#include "../math/BeamParamsAtElemsFunction.h"
#include "../math/MultibeamCausticFunction.h"
#include "../math/MultirangeCausticFunction.h"
#include "../math/OptimizerFunction.h"
#include "../math/StabilityMapFunction.h"
#include "../math/StabilityMap2DFunction.h"
#include "../math/BeamParamsAtElemsFunction.h"
#include "../windows/WindowsManager.h"

#include "widgets/OriPopupMessage.h"

#include <QProcess>

template <class TWindow> SchemaWindow* windowConstructor(Schema* schema)
{
    return new TWindow(schema);
}

template <class TWindow, class TFunction> void registerWindowConstructor()
{
    WindowsManager::registerConstructor(TFunction::_alias_(), windowConstructor<TWindow>);
}

#define RETURN_IF_SCHEMA_EMPTY \
    if (schema()->activeCount() == 0) \
    { \
        Ori::Gui::PopupMessage::hint(tr("光路图为空")); \
        Z_INFO("There are no active elements in the schema"); \
        return; \
    }

CalcManager::CalcManager(Schema *schema, QWidget *parent) :
    QObject(parent), _parent(parent), _schema(schema)
{
    registerWindowConstructor<StabilityMapWindow, StabilityMapFunction>();
    registerWindowConstructor<StabilityMap2DWindow, StabilityMap2DFunction>();
    registerWindowConstructor<CausticWindow, CausticFunction>();
    registerWindowConstructor<MultirangeCausticWindow, MultirangeCausticFunction>();
    registerWindowConstructor<MultibeamCausticWindow, MultibeamCausticFunction>();
    registerWindowConstructor<BeamVariationWindow, BeamVariationFunction>();
    registerWindowConstructor<BeamParamsAtElemsWindow, BeamParamsAtElemsFunction>();
    registerWindowConstructor<OptimizerWindow, OptimizerFunction>();
    registerWindowConstructor<CustomTableFuncWindow, CustomTableFunction>();
    registerWindowConstructor<CustomPlotFuncWindow, CustomPlotFunction>();
}

void CalcManager::funcSummary()
{
    showInfoFunc(new InfoFuncSummary(schema()));
}

void CalcManager::funcRoundTrip()
{
    RETURN_IF_SCHEMA_EMPTY
    showInfoFunc(new InfoFuncMatrixRT(schema(), schema()->selectedElement()));
}

void CalcManager::funcMatrixMult()
{
    RETURN_IF_SCHEMA_EMPTY
    showInfoFunc(new InfoFuncMatrixMult(schema(), schema()->selectedElements()));
}

void CalcManager::funcStabMap()
{
    showPlotFunc<StabilityMapFunction>();
}

void CalcManager::funcStabMap2d()
{
    showPlotFunc<StabilityMap2DFunction>();
}

void CalcManager::funcRepRate()
{
    RETURN_IF_SCHEMA_EMPTY
    showInfoFunc(new InfoFuncRepetitionRate(schema()));
}

void CalcManager::funcCaustic()
{
    showPlotFunc<CausticFunction>();
}

void CalcManager::funcMultirangeCaustic()
{
    showPlotFunc<MultirangeCausticFunction>();
}

void CalcManager::funcMultibeamCaustic()
{
    showPlotFunc<MultibeamCausticFunction>();
}

void CalcManager::funcBeamVariation()
{
    showPlotFunc<BeamVariationFunction>();
}

void CalcManager::funcBeamParamsAtElems()
{
    showTableFunc<BeamParamsAtElemsFunction>();
}

void CalcManager::funcOptimizer()
{
    // OptimizerWindow is not a PlotFuncWindow, so it needs its own opener
    // (showPlotFunc casts to PlotFuncWindow).
    RETURN_IF_SCHEMA_EMPTY

    auto ctor = WindowsManager::getConstructor(OptimizerFunction::_alias_());
    if (!ctor) return;

    auto wnd = ctor(schema());
    if (!wnd) return;

    auto optWnd = dynamic_cast<OptimizerWindow*>(wnd);
    if (!optWnd)
    {
        qWarning() << "Bad window class for function" << OptimizerFunction::_alias_();
        delete wnd;
        return;
    }

    if (!optWnd->configure())
    {
        delete wnd;
        return;
    }

    WindowsManager::instance().show(wnd);
    optWnd->update();
}

void CalcManager::funcEngineeringHub()
{
    // The Engineering Hub is a modal dialog (not an MDI window): it
    // drives the Python backend for the currently open schema file.
    RETURN_IF_SCHEMA_EMPTY

    auto* dlg = new EngineeringHubDialog(schema()->fileName(), _parent);
    dlg->run();
    delete dlg;
}

//------------------------------------------------------------------------------
//                             Red-light toggle
//------------------------------------------------------------------------------

bool CalcManager::redlightAvailable() const
{
    if (schema()->fileName().isEmpty())
        return false;
    return !EngineeringBackend::locateEngineeringDir().isEmpty();
}

BeamParamsAtElemsWindow* CalcManager::beamParamsWindow() const
{
    for (auto* wnd : WindowsManager::instance().schemaWindows(_schema))
        if (auto* bp = dynamic_cast<BeamParamsAtElemsWindow*>(wnd))
            return bp;
    return nullptr;
}

BeamParamsAtElemsWindow* CalcManager::openBeamParamsWindow()
{
    if (auto* wnd = beamParamsWindow())
    {
        WindowsManager::instance().show(wnd);
        return wnd;
    }
    // Same as showTableFunc<BeamParamsAtElemsFunction>(), but the
    // caller needs the window pointer to drive the overlay.
    if (schema()->activeCount() == 0)
        return nullptr;
    auto ctor = WindowsManager::getConstructor(BeamParamsAtElemsFunction::_alias_());
    if (!ctor) return nullptr;
    auto wnd = ctor(schema());
    if (!wnd) return nullptr;
    auto* tableWnd = dynamic_cast<BeamParamsAtElemsWindow*>(wnd);
    if (!tableWnd || !tableWnd->configure())
    {
        delete wnd;
        return nullptr;
    }
    WindowsManager::instance().show(wnd);
    tableWnd->update();
    return tableWnd;
}

void CalcManager::applyRedlightMode(const RedlightReport& report)
{
    auto* wnd = openBeamParamsWindow();
    if (!wnd)
    {
        _redlightOn = false;
        emit redlightModeChanged(false);
        return;
    }
    connect(wnd, &BeamParamsAtElemsWindow::redlightModeCleared,
            this, &CalcManager::onRedlightCleared, Qt::UniqueConnection);
    connect(wnd, &QObject::destroyed,
            this, &CalcManager::onBeamParamsDestroyed, Qt::UniqueConnection);
    wnd->setRedlightMode(report);
}

void CalcManager::dropRedlightProcess()
{
    if (!_redlightProcess)
        return;
    auto* process = _redlightProcess;
    _redlightProcess = nullptr;
    disconnect(process, nullptr, this, nullptr);
    process->kill();
    process->deleteLater();
}

void CalcManager::funcRedlightToggle(bool checked)
{
    if (checked == _redlightOn && !_redlightProcess)
        return;

    if (!checked)
    {
        // Turning off: cancel a run in flight and restore the
        // normal 1064 nm display. The window's redlightModeCleared
        // signal resets the state when the overlay actually drops.
        dropRedlightProcess();
        if (_redlightOn)
        {
            if (auto* wnd = beamParamsWindow())
                wnd->setRedlightMode(RedlightReport{});
            else
            {
                _redlightOn = false;
                emit redlightModeChanged(false);
            }
        }
        return;
    }

    // Turning on: the backend runs on the saved .rez file, so an
    // unsaved schema or a missing backend rolls the toggle back.
    if (schema()->activeCount() == 0)
    {
        emit redlightModeChanged(false);
        return;
    }
    const QString rezPath = schema()->fileName();
    const QString engDir = EngineeringBackend::locateEngineeringDir();
    const QString script = EngineeringBackend::resolveScript(
        engDir, QStringLiteral("run_redlight.py"));
    if (rezPath.isEmpty() || script.isEmpty())
    {
        emit redlightModeChanged(false);
        return;
    }
    dropRedlightProcess();
    auto* process = new QProcess(this);
    _redlightProcess = process;
    connect(process,
            QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, &CalcManager::onRedlightFinished);
    connect(process, &QProcess::errorOccurred,
            this, &CalcManager::onRedlightError);
    // No side-car argument: run_redlight.py defaults to
    // <file>.rez.eng.json, and a missing side-car is fine --
    // the material library is built in.
    process->start(EngineeringBackend::pythonExecutable(),
                   QStringList() << script << rezPath);
}

void CalcManager::onRedlightFinished(int exitCode, QProcess::ExitStatus status)
{
    auto* process = qobject_cast<QProcess*>(sender());
    if (!process || process != _redlightProcess)
        return;
    _redlightProcess = nullptr;
    const QByteArray stdoutData = process->readAllStandardOutput();
    process->deleteLater();

    if (status != QProcess::NormalExit || exitCode != 0)
    {
        emit redlightModeChanged(false);
        return;
    }
    const auto parsed = EngineeringBackend::parseReport(stdoutData);
    if (!parsed.ok)
    {
        emit redlightModeChanged(false);
        return;
    }
    const RedlightReport report = parseRedlightReport(parsed.object);
    if (!report.ok)
    {
        emit redlightModeChanged(false);
        return;
    }
    _redlightOn = true;
    applyRedlightMode(report);
    emit redlightModeChanged(true);
}

void CalcManager::onRedlightError(QProcess::ProcessError)
{
    auto* process = qobject_cast<QProcess*>(sender());
    if (!process || process != _redlightProcess)
        return;
    _redlightProcess = nullptr;
    process->deleteLater();
    emit redlightModeChanged(false);
}

void CalcManager::onRedlightCleared()
{
    if (!_redlightOn)
        return;
    _redlightOn = false;
    emit redlightModeChanged(false);
}

void CalcManager::onBeamParamsDestroyed()
{
    if (!_redlightOn)
        return;
    _redlightOn = false;
    emit redlightModeChanged(false);
}

void CalcManager::funcCustomTable()
{
    showTableFunc<CustomTableFunction>();
}

void CalcManager::funcCustomPlot()
{
    showPlotFuncV2<CustomPlotFunction>();
}

void CalcManager::funcShowMatrices()
{
    RETURN_IF_SCHEMA_EMPTY
    auto elems = schema()->selectedElements();
    if (elems.isEmpty())
    {
        Z_INFO("No elements selected")
        return;
    }
    if (elems.size() == 1)
        showInfoFunc(new InfoFuncMatrix(schema(), elems.at(0)));
    else
        showInfoFunc(new InfoFuncMatrices(schema(), elems));
}

void CalcManager::funcShowAllMatrices()
{
    RETURN_IF_SCHEMA_EMPTY
    showInfoFunc(new InfoFuncMatrices(schema(), schema()->elements()));
}

void CalcManager::showInfoFunc(InfoFunction* func)
{
    InfoFuncWindow::open(func, _parent);
}

template <class TFunction> void CalcManager::showPlotFunc()
{
    RETURN_IF_SCHEMA_EMPTY

    auto ctor = WindowsManager::getConstructor(TFunction::_alias_());
    if (!ctor) return;

    auto wnd = ctor(schema());
    if (!wnd) return;

    auto plotWnd = dynamic_cast<PlotFuncWindow*>(wnd);
    if (!plotWnd)
    {
        qWarning() << "Bad window class for function" << TFunction::_alias_();
        delete wnd;
        return;
    }
    
    if (!plotWnd->configure())
    {
        delete wnd;
        return;
    }

    plotWnd->function()->loadPrefs();
    WindowsManager::instance().show(wnd);
    plotWnd->requestAutolimits();
    plotWnd->requestCenterCursor();
    plotWnd->update();
}

template <class TFunction> void CalcManager::showPlotFuncV2()
{
    RETURN_IF_SCHEMA_EMPTY

    auto ctor = WindowsManager::getConstructor(TFunction::_alias_());
    if (!ctor) return;

    auto wnd = ctor(schema());
    if (!wnd) return;

    auto plotWnd = dynamic_cast<PlotFuncWindowV2*>(wnd);
    if (!plotWnd)
    {
        qWarning() << "Bad window class for function" << TFunction::_alias_();
        delete wnd;
        return;
    }
    
    if (!plotWnd->configure())
    {
        delete wnd;
        return;
    }

    WindowsManager::instance().show(wnd);
    plotWnd->requestAutolimits();
    plotWnd->requestCenterCursor();
    plotWnd->update();
}

template <class TFunction> void CalcManager::showTableFunc()
{
    RETURN_IF_SCHEMA_EMPTY

    auto ctor = WindowsManager::getConstructor(TFunction::_alias_());
    if (!ctor) return;

    auto wnd = ctor(schema());
    if (!wnd) return;

    auto tableWnd = dynamic_cast<TableFuncWindow*>(wnd);
    if (!tableWnd->configure())
    {
        delete wnd;
        return;
    }

    WindowsManager::instance().show(wnd);
    tableWnd->update();
}
