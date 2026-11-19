#include "EngineeringHubDialog.h"

#include "EngineeringBackend.h"

#include <QDesktopServices>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QPushButton>
#include <QTabWidget>
#include <QTextEdit>
#include <QUrl>
#include <QVBoxLayout>
#include <QHBoxLayout>

namespace {

QWidget* tabPage(QTextEdit*& output, QPushButton*& runButton,
                 const QString& description, const QString& buttonText)
{
    auto* page = new QWidget;
    auto* layout = new QVBoxLayout(page);
    auto* label = new QLabel(description);
    label->setWordWrap(true);
    layout->addWidget(label);
    runButton = new QPushButton(buttonText);
    layout->addWidget(runButton);
    output = new QTextEdit;
    output->setReadOnly(true);
    output->setPlaceholderText(QObject::tr("尚未运行"));
    layout->addWidget(output, 1);
    return page;
}

QString jsonPretty(const QJsonObject& obj)
{
    return QString::fromUtf8(
        QJsonDocument(obj).toJson(QJsonDocument::Indented));
}

} // namespace

EngineeringHubDialog::EngineeringHubDialog(const QString& rezFilePath,
                                           QWidget* parent)
    : RezonatorDialog(RezonatorDialog::OmitButtonsPanel
                          | RezonatorDialog::UseHelpButton
                          | RezonatorDialog::DontDeleteOnClose, parent),
      _rezFilePath(rezFilePath)
{
    setTitleAndIcon(tr("工程中心"), ":/toolbar/python_framed");
    _engineeringDir = EngineeringBackend::locateEngineeringDir();
    buildUi();
    if (_engineeringDir.isEmpty())
        showBackendMissing();
    else if (_rezFilePath.isEmpty())
    {
        setAllRunEnabled(false);
        _foxliTab.output->setPlainText(
            tr("当前方案尚未保存到文件。请先保存方案（.she/.rez），"
               "工程后端需要一个文件路径才能计算。"));
    }
}

void EngineeringHubDialog::buildUi()
{
    auto* layout = mainLayout();

    auto* topRow = new QHBoxLayout;
    topRow->addWidget(new QLabel(tr("方案文件：")));
    auto* rezLabel = new QLabel(_rezFilePath.isEmpty()
                                    ? tr("（未保存）") : _rezFilePath);
    rezLabel->setWordWrap(true);
    topRow->addWidget(rezLabel, 1);
    layout->addLayout(topRow);

    auto* engRow = new QHBoxLayout;
    engRow->addWidget(new QLabel(tr("工程 side-car：")));
    _engFileEdit = new QLineEdit;
    if (!_rezFilePath.isEmpty())
    {
        const QString defEng = _rezFilePath + QStringLiteral(".eng.json");
        if (QFileInfo::exists(defEng))
            _engFileEdit->setText(defEng);
    }
    _engFileEdit->setPlaceholderText(
        tr("留空则使用 <方案>.rez.eng.json（若不存在则各工具自行处理）"));
    engRow->addWidget(_engFileEdit, 1);
    auto* browseEng = new QPushButton(tr("浏览…"));
    connect(browseEng, &QPushButton::clicked,
            this, &EngineeringHubDialog::browseEngFile);
    engRow->addWidget(browseEng);
    layout->addLayout(engRow);

    auto* outRow = new QHBoxLayout;
    outRow->addWidget(new QLabel(tr("导出目录：")));
    _outDirEdit = new QLineEdit;
    if (!_rezFilePath.isEmpty())
        _outDirEdit->setText(QFileInfo(_rezFilePath).absolutePath());
    outRow->addWidget(_outDirEdit, 1);
    auto* browseOut = new QPushButton(tr("浏览…"));
    connect(browseOut, &QPushButton::clicked,
            this, &EngineeringHubDialog::browseOutDir);
    outRow->addWidget(browseOut);
    layout->addLayout(outRow);

    _tabs = new QTabWidget;
    _tabs->addTab(tabPage(_foxliTab.output, _foxliTab.runButton,
        tr("Fox-Li 物理光学衍射引擎（Phase 4 M3）：混合传播子往返迭代，"
           "输出衍射损耗与 D4σ M²。"),
        tr("运行 Fox-Li…")), tr("Fox-Li"));
    _tabs->addTab(tabPage(_thermalTab.output, _thermalTab.runButton,
        tr("热传导与热断裂（Phase 4 M2）：2/5/10 W 三档泵浦下的最高温、"
           "端面鼓包、最大拉应力与断裂安全裕度。"),
        tr("运行热分析…")), tr("热分析"));
    _tabs->addTab(tabPage(_ghostsTab.output, _ghostsTab.runButton,
        tr("鬼像与标准具扫描（Phase 4 M1）：残余反射的寄生子腔与烧镜点。"),
        tr("运行鬼像扫描…")), tr("鬼像"));
    _tabs->addTab(tabPage(_redlightTab.output, _redlightTab.runButton,
        tr("632.8 nm 红光准直对照（Phase 4 M1）：冷腔与 1064 nm 工作腔"
           "的光斑与光轴偏移对照；冷腔失稳时自动切 HeNe 单程追迹。"),
        tr("运行红光对照…")), tr("红光"));
    _tabs->addTab(tabPage(_exportTab.output, _exportTab.runButton,
        tr("导出 ODR / CAD（Phase 4 M1+M4）：生成镀膜表、.zmx、.dxf，"
           "并汇总全部分析结果生成 ODR 评审报告（HTML）。"),
        tr("导出 ODR / CAD…")), tr("导出 / ODR"));
    layout->addWidget(_tabs, 1);

    auto* bottomRow = new QHBoxLayout;
    _openOdrButton = new QPushButton(tr("打开 ODR 报告…"));
    _openOdrButton->setEnabled(false);
    connect(_openOdrButton, &QPushButton::clicked,
            this, &EngineeringHubDialog::openOdrReport);
    bottomRow->addWidget(_openOdrButton);
    bottomRow->addStretch(1);
    auto* closeButton = new QPushButton(tr("关闭"));
    connect(closeButton, &QPushButton::clicked, this, &QDialog::accept);
    bottomRow->addWidget(closeButton);
    layout->addLayout(bottomRow);

    connect(_foxliTab.runButton, &QPushButton::clicked,
            this, &EngineeringHubDialog::runFoxLi);
    connect(_thermalTab.runButton, &QPushButton::clicked,
            this, &EngineeringHubDialog::runThermal);
    connect(_ghostsTab.runButton, &QPushButton::clicked,
            this, &EngineeringHubDialog::runGhosts);
    connect(_redlightTab.runButton, &QPushButton::clicked,
            this, &EngineeringHubDialog::runRedlight);
    connect(_exportTab.runButton, &QPushButton::clicked,
            this, &EngineeringHubDialog::runExportOdr);
}

void EngineeringHubDialog::setAllRunEnabled(bool enabled)
{
    _foxliTab.runButton->setEnabled(enabled);
    _thermalTab.runButton->setEnabled(enabled);
    _ghostsTab.runButton->setEnabled(enabled);
    _redlightTab.runButton->setEnabled(enabled);
    _exportTab.runButton->setEnabled(enabled);
}

void EngineeringHubDialog::showBackendMissing()
{
    setAllRunEnabled(false);
    const QString msg = tr(
        "找不到 Python 工程后端。已按以下顺序查找，均未发现 engineering/ 目录：\n%1\n\n"
        "请将 engineering/ 目录放到程序目录旁，或设置环境变量 "
        "REZONATOR_ENGINEERING_DIR，或在设置中填写 "
        "EngineeringHub/engineeringDir，然后重新打开本对话框。")
        .arg(EngineeringBackend::searchedLocationsText());
    for (QTextEdit* output : {_foxliTab.output, _thermalTab.output,
                              _ghostsTab.output, _redlightTab.output,
                              _exportTab.output})
        output->setPlainText(msg);
}

QString EngineeringHubDialog::engFileArg() const
{
    return _engFileEdit->text().trimmed();
}

QStringList EngineeringHubDialog::engArgsFor(const QString& scriptName) const
{
    // run_ghosts.py / run_redlight.py / run_export.py take the side-car
    // as an optional positional argument; the --eng scripts take --eng.
    const QString eng = engFileArg();
    if (eng.isEmpty())
        return QStringList();
    if (scriptName == QLatin1String("run_ghosts.py")
            || scriptName == QLatin1String("run_redlight.py")
            || scriptName == QLatin1String("run_export.py"))
        return QStringList() << eng;
    return QStringList() << QStringLiteral("--eng") << eng;
}

void EngineeringHubDialog::startRun(RunKind kind, const QString& script,
                                     const QStringList& args, bool jsonMode)
{
    if (_process && _process->state() != QProcess::NotRunning)
        return;
    const QString scriptPath = EngineeringBackend::resolveScript(
        _engineeringDir, script);
    if (scriptPath.isEmpty())
    {
        _currentOutput->setPlainText(
            tr("后端脚本 %1 不存在于 %2").arg(script, _engineeringDir));
        return;
    }
    if (!_process)
    {
        _process = new QProcess(this);
        connect(_process, QOverload<int, QProcess::ExitStatus>::of(
                              &QProcess::finished),
                this, &EngineeringHubDialog::onProcessFinished);
        connect(_process, &QProcess::errorOccurred,
                this, &EngineeringHubDialog::onProcessError);
    }
    _currentKind = kind;
    _currentJsonMode = jsonMode;
    setAllRunEnabled(false);
    _currentOutput->setPlainText(tr("运行中…"));
    _process->start(EngineeringBackend::pythonExecutable(),
                    QStringList() << scriptPath << args);
}

void EngineeringHubDialog::onProcessError(QProcess::ProcessError error)
{
    Q_UNUSED(error)
    setAllRunEnabled(true);
    if (_currentOutput)
        _currentOutput->setPlainText(
            tr("无法启动 Python 解释器 %1：%2")
                .arg(EngineeringBackend::pythonExecutable(),
                     _process ? _process->errorString() : QString()));
}

void EngineeringHubDialog::onProcessFinished(
    int exitCode, QProcess::ExitStatus status)
{
    const QString stdoutText = _process
        ? QString::fromUtf8(_process->readAllStandardOutput()) : QString();
    const QString stderrText = _process
        ? QString::fromUtf8(_process->readAllStandardError()) : QString();
    Q_UNUSED(status)
    setAllRunEnabled(true);
    finishRun(stdoutText, stderrText, exitCode);
}

void EngineeringHubDialog::finishRun(const QString& stdoutText,
                                     const QString& stderrText,
                                     int exitCode)
{
    if (!_currentOutput)
        return;
    if (exitCode != 0)
    {
        _currentOutput->setPlainText(
            tr("后端退出码 %1\n%2\n%3").arg(exitCode).arg(stderrText, stdoutText));
        _pendingOdr = false;
        return;
    }
    if (!_currentJsonMode)
    {
        _currentOutput->setPlainText(stdoutText);
        if (_currentKind == RunExport)
        {
            // Export done: chain the ODR report generation.
            _pendingOdr = true;
            runExportOdr();
        }
        return;
    }
    const auto parsed = EngineeringBackend::parseReport(
        stdoutText.toUtf8());
    if (!parsed.ok)
    {
        _currentOutput->setPlainText(
            tr("后端输出解析失败：%1\n原始输出：\n%2\n标准错误：\n%3")
                .arg(parsed.error, stdoutText, stderrText));
        _pendingOdr = false;
        return;
    }
    QString text = summarizeReport(_currentKind, parsed.object);
    text += QStringLiteral("\n\n--- JSON ---\n");
    text += jsonPretty(parsed.object);
    _currentOutput->setPlainText(text);
    if (_currentKind == RunOdr)
    {
        _odrHtmlPath = parsed.object.value(QStringLiteral("out_html"))
                           .toString();
        _openOdrButton->setEnabled(!_odrHtmlPath.isEmpty());
    }
    _pendingOdr = false;
}

QString EngineeringHubDialog::summarizeReport(
    RunKind kind, const QJsonObject& obj) const
{
    switch (kind)
    {
    case RunFoxLi:
    {
        const QJsonObject beam0 = obj.value(QStringLiteral("beam"))
                                      .toArray().isEmpty()
            ? QJsonObject()
            : obj.value(QStringLiteral("beam")).toArray().first().toObject();
        return tr("Fox-Li：收敛=%1，%2 圈，衍射损耗 L_diff=%3，M1 处 M²_T=%4")
            .arg(obj.value(QStringLiteral("converged")).toBool() ? tr("是") : tr("否"))
            .arg(obj.value(QStringLiteral("rounds")).toInt())
            .arg(obj.value(QStringLiteral("L_diff")).toDouble(), 0, 'g', 4)
            .arg(beam0.value(QStringLiteral("M2_T")).toDouble(), 0, 'g', 4);
    }
    case RunThermal:
    {
        QStringList lines;
        const QJsonArray reports = obj.value(QStringLiteral("reports")).toArray();
        for (const QJsonValue& value : reports)
        {
            const QJsonObject rep = value.toObject();
            const QJsonObject frac = rep.value(QStringLiteral("fracture")).toObject();
            const QJsonObject prim = frac.value(QStringLiteral("primary")).toObject();
            lines << tr("泵浦 %1 W：T_max=%2 °C，鼓包=%3 µm，σ_c=%4 MPa，裕度=%5")
                       .arg(rep.value(QStringLiteral("P_pump_W")).toDouble())
                       .arg(rep.value(QStringLiteral("T_max_C")).toDouble(), 0, 'f', 1)
                       .arg(rep.value(QStringLiteral("bulge_max_um")).toDouble(), 0, 'f', 3)
                       .arg(prim.value(QStringLiteral("sigma_c_MPa")).toDouble(), 0, 'f', 2)
                       .arg(prim.value(QStringLiteral("margin_c")).toDouble(), 0, 'f', 3);
        }
        return lines.join(QStringLiteral("\n"));
    }
    case RunGhosts:
    {
        const QJsonObject summary = obj.value(QStringLiteral("summary")).toObject();
        return tr("鬼像扫描：ok=%1，warn=%2，fail=%3，nodata=%4；标准具 %5 个")
            .arg(summary.value(QStringLiteral("ok")).toInt())
            .arg(summary.value(QStringLiteral("warn")).toInt())
            .arg(summary.value(QStringLiteral("fail")).toInt())
            .arg(summary.value(QStringLiteral("nodata")).toInt())
            .arg(obj.value(QStringLiteral("etalons")).toArray().size());
    }
    case RunRedlight:
    {
        const QJsonObject cold = obj.value(QStringLiteral("cold")).toObject();
        return tr("红光对照：路径=%1，冷腔 g_T=%2，g_S=%3")
            .arg(obj.value(QStringLiteral("path")).toString())
            .arg(cold.value(QStringLiteral("g_T")).toDouble(), 0, 'g', 4)
            .arg(cold.value(QStringLiteral("g_S")).toDouble(), 0, 'g', 4);
    }
    case RunOdr:
        return tr("ODR 报告：%1/%2 节完成 → %3")
            .arg(obj.value(QStringLiteral("n_ok")).toInt())
            .arg(obj.value(QStringLiteral("n_sections")).toInt())
            .arg(obj.value(QStringLiteral("out_html")).toString());
    case RunExport:
        return QString();
    }
    return QString();
}

void EngineeringHubDialog::runFoxLi()
{
    _currentOutput = _foxliTab.output;
    QStringList args;
    args << QStringLiteral("--rez") << _rezFilePath
         << engArgsFor(QStringLiteral("run_foxli.py"))
         << QStringLiteral("--max-rounds") << QStringLiteral("200");
    startRun(RunFoxLi, QStringLiteral("run_foxli.py"), args, true);
}

void EngineeringHubDialog::runThermal()
{
    _currentOutput = _thermalTab.output;
    QStringList args;
    args << QStringLiteral("--rez") << _rezFilePath
         << engArgsFor(QStringLiteral("run_thermal.py"))
         << QStringLiteral("--pump") << QStringLiteral("2,5,10");
    startRun(RunThermal, QStringLiteral("run_thermal.py"), args, true);
}

void EngineeringHubDialog::runGhosts()
{
    _currentOutput = _ghostsTab.output;
    QStringList args;
    args << _rezFilePath << engArgsFor(QStringLiteral("run_ghosts.py"));
    startRun(RunGhosts, QStringLiteral("run_ghosts.py"), args, true);
}

void EngineeringHubDialog::runRedlight()
{
    _currentOutput = _redlightTab.output;
    QStringList args;
    args << _rezFilePath << engArgsFor(QStringLiteral("run_redlight.py"));
    startRun(RunRedlight, QStringLiteral("run_redlight.py"), args, true);
}

void EngineeringHubDialog::runExportOdr()
{
    _currentOutput = _exportTab.output;
    const QString outDir = _outDirEdit->text().trimmed();
    const QString base = QFileInfo(_rezFilePath).completeBaseName();
    if (_pendingOdr)
    {
        // Second step of the chain: generate the ODR report.
        _pendingOdr = false;
        QStringList args;
        args << QStringLiteral("--rez") << _rezFilePath
             << engArgsFor(QStringLiteral("run_odr.py"))
             << QStringLiteral("--out")
             << QDir(outDir).filePath(base + QStringLiteral(".odr.html"))
             << QStringLiteral("--mc-n") << QStringLiteral("250");
        startRun(RunOdr, QStringLiteral("run_odr.py"), args, true);
        return;
    }
    // First step: coating + .zmx + .dxf (text-mode output).
    QStringList args;
    args << _rezFilePath << engArgsFor(QStringLiteral("run_export.py"))
         << QStringLiteral("--coating")
         << QStringLiteral("--zmx")
         << QDir(outDir).filePath(base + QStringLiteral(".zmx"))
         << QStringLiteral("--dxf")
         << QDir(outDir).filePath(base + QStringLiteral(".dxf"));
    startRun(RunExport, QStringLiteral("run_export.py"), args, false);
}

void EngineeringHubDialog::openOdrReport()
{
    if (!_odrHtmlPath.isEmpty())
        QDesktopServices::openUrl(QUrl::fromLocalFile(_odrHtmlPath));
}

void EngineeringHubDialog::browseEngFile()
{
    const QString path = QFileDialog::getOpenFileName(
        this, tr("选择工程 side-car 文件"), _engFileEdit->text(),
        tr("工程文件 (*.eng.json);;全部文件 (*)"));
    if (!path.isEmpty())
        _engFileEdit->setText(path);
}

void EngineeringHubDialog::browseOutDir()
{
    const QString path = QFileDialog::getExistingDirectory(
        this, tr("选择导出目录"), _outDirEdit->text());
    if (!path.isEmpty())
        _outDirEdit->setText(path);
}
