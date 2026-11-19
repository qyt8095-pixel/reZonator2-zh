#ifndef ENGINEERING_HUB_DIALOG_H
#define ENGINEERING_HUB_DIALOG_H

#include "../windows/RezonatorDialog.h"

#include <QJsonObject>
#include <QProcess>

QT_BEGIN_NAMESPACE
class QLineEdit;
class QPushButton;
class QTabWidget;
class QTextEdit;
QT_END_NAMESPACE

/**
    Engineering Hub (Phase 4 M4, MVP): one dialog that drives the Python
    engineering backend (engineering/rezeng) through QProcess and shows
    the JSON results as text.

    Tabs: Fox-Li diffraction, thermal conduction + fracture, ghost scan
    and red-light comparison, export / ODR report. The heavy calculation
    stays in Python; C++ only locates the backend, runs it and renders
    the result. The Solves live-slider linkage is deferred to Phase 4.5.

    Backend location follows EngineeringBackend::locateEngineeringDir()
    (app-dir engineering/ -> REZONATOR_ENGINEERING_DIR -> user setting).
    When the backend is not found, or the schema has never been saved,
    the run buttons are disabled and the dialog explains what is missing
    instead of crashing or failing silently.
*/
class EngineeringHubDialog : public RezonatorDialog
{
    Q_OBJECT

public:
    explicit EngineeringHubDialog(const QString& rezFilePath,
                                  QWidget* parent = nullptr);

    QString helpTopic() const override
    { return QStringLiteral("func_engineering_hub.html"); }

    QSize prefferedSize() const override { return QSize(920, 640); }

private slots:
    void runFoxLi();
    void runThermal();
    void runGhosts();
    void runRedlight();
    void runExportOdr();
    void openOdrReport();
    void browseEngFile();
    void browseOutDir();
    void onProcessFinished(int exitCode, QProcess::ExitStatus status);
    void onProcessError(QProcess::ProcessError error);

private:
    enum RunKind
    {
        RunFoxLi,
        RunThermal,
        RunGhosts,
        RunRedlight,
        RunExport,
        RunOdr
    };

    struct TabWidgets
    {
        QTextEdit* output = nullptr;
        QPushButton* runButton = nullptr;
    };

    void buildUi();
    QTextEdit* makeOutput();
    void setAllRunEnabled(bool enabled);
    QString engFileArg() const;
    QStringList engArgsFor(const QString& scriptName) const;
    void startRun(RunKind kind, const QString& script,
                  const QStringList& args, bool jsonMode);
    void finishRun(const QString& stdoutText, const QString& stderrText,
                   int exitCode);
    QString summarizeReport(RunKind kind, const QJsonObject& obj) const;
    void showBackendMissing();

    QString _rezFilePath;
    QString _engineeringDir;
    QString _odrHtmlPath;

    QLineEdit* _engFileEdit = nullptr;
    QLineEdit* _outDirEdit = nullptr;
    QPushButton* _openOdrButton = nullptr;
    QTabWidget* _tabs = nullptr;

    TabWidgets _foxliTab;
    TabWidgets _thermalTab;
    TabWidgets _ghostsTab;
    TabWidgets _redlightTab;
    TabWidgets _exportTab;

    QProcess* _process = nullptr;
    RunKind _currentKind = RunFoxLi;
    QTextEdit* _currentOutput = nullptr;
    bool _currentJsonMode = true;
    bool _pendingOdr = false;
};

#endif // ENGINEERING_HUB_DIALOG_H
