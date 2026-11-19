#ifndef LIDT_CHECK_RUNNER_H
#define LIDT_CHECK_RUNNER_H

#include "LidtMarks.h"

#include <QMap>
#include <QObject>
#include <QProcess>
#include <QString>

/// Runs ``run_checks.py`` asynchronously (through QProcess) for the
/// currently open .rez file and emits the per-element LIDT marks
/// for the main element list (Phase 4 follow-up).
///
/// The runner never blocks the UI and never shows a dialog: when
/// the backend is missing, the side-car is missing, or the run
/// fails, it emits ``failed()`` and the caller silently leaves
/// the element list unmarked. A check run is only meaningful for
/// a saved .rez file; the caller checks that before calling run().
class LidtCheckRunner : public QObject
{
    Q_OBJECT

public:
    explicit LidtCheckRunner(QObject* parent = nullptr);

    bool isRunning() const { return _process != nullptr; }

    /// Start ``run_checks.py <rez> <eng>``. Any run already in
    /// flight is dropped first (only the latest result is used).
    void run(const QString& rezPath, const QString& engPath);

signals:
    /// Emitted when the check finished and the report parsed:
    /// per-element marks keyed by element label (only warn/fail).
    void finished(const QMap<QString, LidtMark>& marks);
    /// Emitted when nothing usable came back (backend missing,
    /// script failed, bad JSON). The message is for logging only;
    /// the caller must not pop it up.
    void failed(const QString& error);

private slots:
    void onProcessFinished(int exitCode, QProcess::ExitStatus status);
    void onProcessError(QProcess::ProcessError error);

private:
    void dropProcess();

    QProcess* _process = nullptr;
    QString _rezPath;
};

#endif // LIDT_CHECK_RUNNER_H
