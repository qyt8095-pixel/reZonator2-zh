#include "EngineeringBackend.h"

#include "tools/OriSettings.h"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QProcess>

namespace {

/// The marker script: a directory counts as the engineering backend
/// only when it contains this file.
const char* MARKER_SCRIPT = "run_foxli.py";

QStringList candidateDirs()
{
    QStringList dirs;
    dirs << QCoreApplication::applicationDirPath()
                + QStringLiteral("/engineering");
    const QString env = qEnvironmentVariable("REZONATOR_ENGINEERING_DIR");
    if (!env.isEmpty())
        dirs << env;
    Ori::Settings settings;
    const QString userDir = settings.settings()->value(
        QStringLiteral("EngineeringHub/engineeringDir")).toString();
    if (!userDir.isEmpty())
        dirs << userDir;
    return dirs;
}

} // namespace

QString EngineeringBackend::locateEngineeringDir()
{
    for (const QString& dir : candidateDirs())
    {
        if (QFileInfo::exists(QDir(dir).filePath(
                QString::fromLatin1(MARKER_SCRIPT))))
            return QDir::cleanPath(dir);
    }
    return QString();
}

QString EngineeringBackend::resolveScript(const QString& engineeringDir,
                                         const QString& scriptName)
{
    if (engineeringDir.isEmpty() || scriptName.isEmpty())
        return QString();
    const QString path = QDir(engineeringDir).filePath(scriptName);
    return QFileInfo::exists(path) ? QDir::cleanPath(path) : QString();
}

QString EngineeringBackend::pythonExecutable()
{
    Ori::Settings settings;
    const QString configured = settings.settings()->value(
        QStringLiteral("EngineeringHub/pythonExecutable")).toString();
    return configured.isEmpty() ? QStringLiteral("python3") : configured;
}

QStringList EngineeringBackend::buildCommand(const QString& python,
                                            const QString& script,
                                            const QStringList& args)
{
    QStringList command;
    command << python << script << args;
    return command;
}

EngineeringBackend::ParseResult
EngineeringBackend::parseReport(const QByteArray& stdoutData)
{
    ParseResult result;
    const QByteArray trimmed = stdoutData.trimmed();
    if (trimmed.isEmpty())
    {
        result.error = QObject::tr("后端没有输出任何内容");
        return result;
    }
    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(trimmed, &parseError);
    if (parseError.error != QJsonParseError::NoError)
    {
        result.error = QObject::tr("后端输出不是合法 JSON：%1")
                           .arg(parseError.errorString());
        return result;
    }
    if (!doc.isObject())
    {
        result.error = QObject::tr("后端输出不是 JSON 对象");
        return result;
    }
    result.ok = true;
    result.object = doc.object();
    return result;
}

EngineeringBackend::RunResult
EngineeringBackend::runScript(const QString& python,
                              const QString& script,
                              const QStringList& args,
                              int timeoutMs)
{
    RunResult result;
    if (script.isEmpty())
    {
        result.error = QObject::tr("未指定后端脚本");
        return result;
    }
    QProcess process;
    process.start(python, QStringList() << script << args);
    if (!process.waitForStarted())
    {
        result.error = QObject::tr("无法启动 Python 解释器 %1：%2")
                           .arg(python, process.errorString());
        return result;
    }
    if (!process.waitForFinished(timeoutMs))
    {
        process.kill();
        process.waitForFinished();
        result.error = QObject::tr("后端运行超时（%1 ms）").arg(timeoutMs);
        return result;
    }
    result.exitCode = process.exitCode();
    result.stdoutData = process.readAllStandardOutput();
    result.stderrData = process.readAllStandardError();
    if (result.exitCode != 0)
        result.error = QObject::tr("后端退出码 %1：%2")
                           .arg(result.exitCode)
                           .arg(QString::fromUtf8(result.stderrData).trimmed());
    return result;
}

QString EngineeringBackend::searchedLocationsText()
{
    return candidateDirs().join(QStringLiteral("\n"));
}
