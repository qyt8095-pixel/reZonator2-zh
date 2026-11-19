#include "LidtCheckRunner.h"

#include "EngineeringBackend.h"

LidtCheckRunner::LidtCheckRunner(QObject* parent) : QObject(parent)
{
}

void LidtCheckRunner::run(const QString& rezPath, const QString& engPath)
{
    dropProcess();
    _rezPath = rezPath;

    const QString engDir = EngineeringBackend::locateEngineeringDir();
    const QString script = EngineeringBackend::resolveScript(
        engDir, QStringLiteral("run_checks.py"));
    if (script.isEmpty())
    {
        emit failed(tr("找不到工程后端（已查找：%1)")
                        .arg(EngineeringBackend::searchedLocationsText()));
        return;
    }

    auto* process = new QProcess(this);
    _process = process;
    connect(process,
            QOverload<int, QProcess::ExitStatus>::of(&QProcess::finished),
            this, &LidtCheckRunner::onProcessFinished);
    connect(process, &QProcess::errorOccurred,
            this, &LidtCheckRunner::onProcessError);
    const QStringList args = QStringList() << script << rezPath << engPath;
    process->start(EngineeringBackend::pythonExecutable(), args);
}

void LidtCheckRunner::dropProcess()
{
    if (!_process)
        return;
    auto* process = _process;
    _process = nullptr;
    disconnect(process, nullptr, this, nullptr);
    process->kill();
    process->deleteLater();
}

void LidtCheckRunner::onProcessFinished(int exitCode, QProcess::ExitStatus status)
{
    auto* process = qobject_cast<QProcess*>(sender());
    if (!process || process != _process)
        return;
    _process = nullptr;
    const QByteArray stdoutData = process->readAllStandardOutput();
    process->deleteLater();

    if (status != QProcess::NormalExit || exitCode != 0)
    {
        emit failed(tr("LIDT 检查退出异常（%1）").arg(exitCode));
        return;
    }
    const auto parsed = EngineeringBackend::parseReport(stdoutData);
    if (!parsed.ok)
    {
        emit failed(tr("LIDT 检查输出无法解析：%1").arg(parsed.error));
        return;
    }
    emit finished(parseLidtReport(parsed.object));
}

void LidtCheckRunner::onProcessError(QProcess::ProcessError error)
{
    auto* process = qobject_cast<QProcess*>(sender());
    if (!process || process != _process)
        return;
    _process = nullptr;
    const QString message = process->errorString();
    process->deleteLater();
    emit failed(tr("无法启动 LIDT 检查：%1").arg(message));
    Q_UNUSED(error)
}
