#ifndef ENGINEERING_BACKEND_H
#define ENGINEERING_BACKEND_H

#include <QByteArray>
#include <QJsonObject>
#include <QString>
#include <QStringList>

/// Locating and running the Python engineering backend (Phase 4 M4).
///
/// The heavy calculations (Fox-Li, thermal FEA, ghost scan, Monte Carlo,
/// ODR report) live in the Python package ``engineering/rezeng`` and are
/// driven through the ``run_*.py`` command-line entries, which print one
/// JSON document to stdout. This class holds the backend-location rules
/// and the JSON parsing, so the dialog stays thin and the logic is
/// unit-testable without a GUI.
///
/// Backend location order:
///   1. ``engineering/`` next to the application binary
///      (``QCoreApplication::applicationDirPath()/engineering``),
///   2. the ``REZONATOR_ENGINEERING_DIR`` environment variable,
///   3. the user setting ``EngineeringHub/engineeringDir`` (QSettings).
///
/// The first directory that contains ``run_foxli.py`` wins. If none is
/// found, the dialog must show the searched locations and refuse to run
/// (never crash, never fail silently). The Python interpreter is the
/// user setting ``EngineeringHub/pythonExecutable``, default ``python3``.
class EngineeringBackend
{
public:
    struct ParseResult
    {
        bool ok = false;
        QJsonObject object;
        QString error;
    };

    struct RunResult
    {
        int exitCode = -1;
        QByteArray stdoutData;
        QByteArray stderrData;
        QString error;
    };

    /// Find the engineering directory, or an empty string when none of
    /// the three locations holds the backend scripts.
    static QString locateEngineeringDir();

    /// Full path of a backend script inside ``engineeringDir``,
    /// or an empty string when the file does not exist.
    static QString resolveScript(const QString& engineeringDir,
                                 const QString& scriptName);

    /// Python interpreter to run the scripts with.
    static QString pythonExecutable();

    /// Command line (program + arguments) for one backend run.
    static QStringList buildCommand(const QString& python,
                                    const QString& script,
                                    const QStringList& args);

    /// Parse the stdout of a backend script: it must be a single JSON
    /// object (run_*.py scripts print exactly one JSON document).
    static ParseResult parseReport(const QByteArray& stdoutData);

    /// Run a backend script synchronously (used by tests and by the
    /// dialog's fallback path). ``timeoutMs`` < 0 waits forever.
    static RunResult runScript(const QString& python,
                               const QString& script,
                               const QStringList& args,
                               int timeoutMs = 300000);

    /// Human-readable description of where the backend was searched.
    static QString searchedLocationsText();
};

#endif // ENGINEERING_BACKEND_H
