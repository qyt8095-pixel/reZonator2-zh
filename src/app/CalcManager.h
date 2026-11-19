#ifndef CALC_MANAGER_H
#define CALC_MANAGER_H

#include <QObject>
#include <QProcess>

QT_BEGIN_NAMESPACE
class QWidget;
QT_END_NAMESPACE

class BeamParamsAtElemsWindow;
class Schema;
class InfoFunction;
struct RedlightReport;

class CalcManager : public QObject
{
    Q_OBJECT

public:
    explicit CalcManager(Schema *schema, QWidget *parent = nullptr);

    Schema* schema() const { return _schema; }

    /// Red-light mode (Phase 4 follow-up) is available when the
    /// schema is saved (the backend runs on the .rez file) and the
    /// Python engineering backend can be located.
    bool redlightAvailable() const;
    bool redlightMode() const { return _redlightOn; }

public slots:
    void funcSummary();
    void funcRoundTrip();
    void funcMatrixMult();
    void funcStabMap();
    void funcStabMap2d();
    void funcRepRate();
    void funcCaustic();
    void funcMultirangeCaustic();
    void funcMultibeamCaustic();
    void funcShowMatrices();
    void funcShowAllMatrices();
    void funcBeamVariation();
    void funcBeamParamsAtElems();
    void funcOptimizer();
    void funcEngineeringHub();
    void funcCustomTable();
    void funcCustomPlot();

    /// One-click red-light toggle (main-window toolbar button +
    /// menu item). Turning on runs ``run_redlight.py`` on the saved
    /// .rez file and swaps the beam-data window to the 632.8 nm
    /// values; turning off restores the 1064 nm display.
    void funcRedlightToggle(bool checked);

signals:
    /// Emitted whenever the red-light mode actually changes
    /// (including rollbacks when the backend run fails and
    /// automatic exits when the overlay goes stale).
    void redlightModeChanged(bool on);

private slots:
    void onRedlightFinished(int exitCode, QProcess::ExitStatus status);
    void onRedlightError(QProcess::ProcessError error);
    void onRedlightCleared();
    void onBeamParamsDestroyed();

private:
    QWidget* _parent;
    Schema* _schema;

    bool _redlightOn = false;
    QProcess* _redlightProcess = nullptr;

    BeamParamsAtElemsWindow* beamParamsWindow() const;
    BeamParamsAtElemsWindow* openBeamParamsWindow();
    void applyRedlightMode(const RedlightReport& report);
    void dropRedlightProcess();

    void showInfoFunc(InfoFunction* func);
    template <class TWindow> void showPlotFunc();
    template <class TWindow> void showPlotFuncV2();
    template <class TFunction> void showTableFunc();
};

#endif // CALC_MANAGER_H
