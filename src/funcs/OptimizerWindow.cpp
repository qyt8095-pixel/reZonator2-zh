#include "OptimizerWindow.h"

#include "../app/Appearance.h"
#include "../core/Format.h"
#include "../core/Report.h"
#include "../core/Units.h"
#include "../funcs/FuncWindowHelpers.h"
#include "../widgets/ElemSelectorWidget.h"

#include "helpers/OriLayouts.h"
#include "helpers/OriWidgets.h"
#include "widgets/OriPopupMessage.h"
#include "widgets/OriStatusBar.h"

#include <QAction>
#include <QCloseEvent>
#include <QComboBox>
#include <QFormLayout>
#include <QGroupBox>
#include <QHeaderView>
#include <QJsonArray>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QListWidget>
#include <QMenu>
#include <QPushButton>
#include <QRegularExpression>
#include <QSet>
#include <QSignalBlocker>
#include <QSpinBox>
#include <QToolBar>

#include <algorithm>

using namespace Ori::Gui::V0;

namespace {

// Parses a comma/space/semicolon separated list of numbers in the given
// unit and returns them in SI. Returns false when any part is not a number.
bool parseCandidates(const QString& text, Z::Unit unit, QVector<double>& candidatesSi)
{
    candidatesSi.clear();
    for (const auto& part : text.split(QRegularExpression("[,;，\\s]+"), Qt::SkipEmptyParts))
    {
        bool ok = false;
        double v = part.trimmed().toDouble(&ok);
        if (!ok || !std::isfinite(v))
            return false;
        candidatesSi << unit->toSi(v);
    }
    return true;
}

} // namespace

//------------------------------------------------------------------------------
//                              OptimizerWindow
//------------------------------------------------------------------------------

OptimizerWindow::OptimizerWindow(Schema* schema) :
    SchemaMdiChild(schema), _function(new OptimizerFunction(schema))
{
    setTitleAndIcon(FuncWindowHelpers::makeWindowTitle(_function), _function->iconPath());

    createActions();
    createMenuBar();
    createToolBar();
    createContent();
    createStatusBar();

    rebuildVariableTable();
    rebuildTargetTable();
    refreshButtons();
}

OptimizerWindow::~OptimizerWindow()
{
    delete _function;
}

void OptimizerWindow::createActions()
{
    _actnStart = action(tr("开始优化"), this, SLOT(startOptimization()), ":/toolbar/start");
    _actnStop = action(tr("停止"), this, SLOT(stopOptimization()), ":/toolbar/stop");
    _actnApply = action(tr("应用结果"), this, SLOT(applyResult()), ":/toolbar/check");
    _actnRevert = action(tr("还原"), this, SLOT(revertResult()), ":/toolbar/undo");
}

void OptimizerWindow::createMenuBar()
{
    _menu = Ori::Gui::menu(tr("优化"), this, {
        _actnStart, _actnStop, nullptr, _actnApply, _actnRevert
    });
}

void OptimizerWindow::createToolBar()
{
    auto t = toolbar();
    t->addAction(_actnStart);
    t->addAction(_actnStop);
    t->addSeparator();
    t->addAction(_actnApply);
    t->addAction(_actnRevert);
}

void OptimizerWindow::createStatusBar()
{
    _statusBar = new Ori::Widgets::StatusBar(STATUS_PANELS_COUNT);
    setContent(_statusBar);
}

void OptimizerWindow::createContent()
{
    _varTable = new QTableWidget();
    _varTable->setColumnCount(VAR_COLS_COUNT);
    _varTable->setHorizontalHeaderLabels({
        tr("启用"), tr("参数"), tr("模式"), tr("下限 / 候选"), tr("上限"), tr("当前值"), tr("优化值")});
    _varTable->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);
    _varTable->horizontalHeader()->setSectionResizeMode(VAR_COL_ENABLED, QHeaderView::ResizeToContents);
    _varTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    connect(_varTable, &QTableWidget::cellChanged, this, &OptimizerWindow::onVariableCellChanged);

    _btnAddVar = new QPushButton(tr("添加变量"));
    connect(_btnAddVar, &QPushButton::clicked, this, &OptimizerWindow::addVariable);
    _btnRemoveVar = new QPushButton(tr("删除变量"));
    connect(_btnRemoveVar, &QPushButton::clicked, this, &OptimizerWindow::removeVariable);
    _btnLengthGroup = new QPushButton(tr("总长固定…"));
    _btnLengthGroup->setToolTip(tr("把几个臂长变量编成一组，总长固定不变、只调整臂长之间的分配"));
    connect(_btnLengthGroup, &QPushButton::clicked, this, &OptimizerWindow::editLengthGroup);
    _lengthGroupLabel = new QLabel();
    auto varButtons = new QWidget();
    Ori::Layouts::LayoutH({_btnAddVar, _btnRemoveVar, _btnLengthGroup, _lengthGroupLabel, Ori::Layouts::Stretch()}).useFor(varButtons);
    refreshLengthGroupLabel();

    _targetTable = new QTableWidget();
    _targetTable->setColumnCount(TGT_COLS_COUNT);
    _targetTable->setHorizontalHeaderLabels({
        tr("目标元件"), tr("指标"), tr("目标值 (%1)").arg(_lengthUnit->name()), tr("权重"), tr("实测值"), tr("误差贡献")});
    _targetTable->horizontalHeader()->setSectionResizeMode(QHeaderView::Stretch);
    _targetTable->setSelectionBehavior(QAbstractItemView::SelectRows);
    connect(_targetTable, &QTableWidget::cellChanged, this, &OptimizerWindow::onTargetCellChanged);

    _btnAddTarget = new QPushButton(tr("添加目标"));
    connect(_btnAddTarget, &QPushButton::clicked, this, &OptimizerWindow::addTarget);
    _btnRemoveTarget = new QPushButton(tr("删除目标"));
    connect(_btnRemoveTarget, &QPushButton::clicked, this, &OptimizerWindow::removeTarget);
    auto targetButtons = new QWidget();
    Ori::Layouts::LayoutH({_btnAddTarget, _btnRemoveTarget, Ori::Layouts::Stretch()}).useFor(targetButtons);

    _btnStart = new QPushButton(tr("开始"));
    connect(_btnStart, &QPushButton::clicked, this, &OptimizerWindow::startOptimization);
    _btnStop = new QPushButton(tr("停止"));
    connect(_btnStop, &QPushButton::clicked, this, &OptimizerWindow::stopOptimization);
    _btnApply = new QPushButton(tr("应用结果"));
    connect(_btnApply, &QPushButton::clicked, this, &OptimizerWindow::applyResult);
    _btnRevert = new QPushButton(tr("还原"));
    connect(_btnRevert, &QPushButton::clicked, this, &OptimizerWindow::revertResult);
    _maxIter = new QSpinBox();
    _maxIter->setRange(10, 10000);
    _maxIter->setValue(500);
    _maxIter->setToolTip(tr("Nelder-Mead 最大迭代次数（每个连续变量组合）"));
    _meritLabel = new QLabel(tr("Merit：—"));

    _lengthUnitCombo = new QComboBox();
    _lengthUnitCombo->addItem(Z::Units::mm()->name(), Z::Units::mm()->alias());
    _lengthUnitCombo->addItem(Z::Units::mkm()->name(), Z::Units::mkm()->alias());
    _lengthUnitCombo->setCurrentIndex(_lengthUnitCombo->findData(_lengthUnit->alias()));
    _lengthUnitCombo->setToolTip(tr("窗口内长度量（光斑目标值与实测值、长度类变量）的显示与输入单位"));
    connect(_lengthUnitCombo, QOverload<int>::of(&QComboBox::currentIndexChanged),
        this, &OptimizerWindow::onLengthUnitChanged);

    auto controlBar = new QWidget();
    Ori::Layouts::LayoutH({
        _btnStart, _btnStop,
        new QLabel(tr("最大迭代次数")), _maxIter,
        _meritLabel,
        new QLabel(tr("长度单位")), _lengthUnitCombo,
        Ori::Layouts::Stretch(),
        _btnApply, _btnRevert
    }).useFor(controlBar);

    auto varGroup = Ori::Gui::groupV(tr("变量"), {_varTable, varButtons});
    auto targetGroup = Ori::Gui::groupV(tr("目标"), {_targetTable, targetButtons});
    setContent(Ori::Layouts::LayoutV({varGroup, targetGroup, controlBar})
        .setMargin(4).setSpacing(4).makeWidget());

    refreshUnitLabels();
}

void OptimizerWindow::update()
{
    rebuildVariableTable();
    rebuildTargetTable();
    refreshLengthGroupLabel();
    refreshButtons();
}

void OptimizerWindow::closeEvent(QCloseEvent* event)
{
    if (_running)
    {
        // Do not destroy the window while run() holds Element* and
        // Z::Parameter* on its stack: ask the run to stop and close
        // after it returns (see startOptimization).
        _stopFlag = true;
        _closeRequested = true;
        event->ignore();
        return;
    }
    SchemaMdiChild::closeEvent(event);
}

ElemDeletionReaction OptimizerWindow::reactElemDeletion(const Elements& elems)
{
    if (_running)
        return ElemDeletionReaction::None;
    for (const auto& v : _function->variables())
        if (v.element && elems.contains(v.element))
            return ElemDeletionReaction::Close;
    for (const auto& t : _function->targets())
        if (t.element && elems.contains(t.element))
            return ElemDeletionReaction::Close;
    return ElemDeletionReaction::None;
}

void OptimizerWindow::setControlsEnabled(bool enabled)
{
    _varTable->setEnabled(enabled);
    _targetTable->setEnabled(enabled);
    _btnAddVar->setEnabled(enabled);
    _btnRemoveVar->setEnabled(enabled);
    _btnLengthGroup->setEnabled(enabled);
    _btnAddTarget->setEnabled(enabled);
    _btnRemoveTarget->setEnabled(enabled);
    _btnStart->setEnabled(enabled);
    _btnApply->setEnabled(enabled && _function->hasResult());
    _btnRevert->setEnabled(enabled && _function->hasResult());
    _maxIter->setEnabled(enabled);
    _actnStart->setEnabled(enabled);
    _actnApply->setEnabled(enabled && _function->hasResult());
    _actnRevert->setEnabled(enabled && _function->hasResult());
    _btnStop->setEnabled(!enabled);
    _actnStop->setEnabled(!enabled);
}

void OptimizerWindow::refreshButtons()
{
    setControlsEnabled(!_running);
}

Z::Unit OptimizerWindow::displayUnit(Z::Unit paramUnit) const
{
    return (paramUnit && Z::Units::guessDim(paramUnit) == Z::Dims::linear())
        ? _lengthUnit : paramUnit;
}

void OptimizerWindow::onLengthUnitChanged(int)
{
    if (_updatingTables || _running)
        return;
    _lengthUnit = Z::Units::findByAlias(_lengthUnitCombo->currentData().toString(),
        Z::Units::mm());
    refreshUnitLabels();
    rebuildVariableTable();
    rebuildTargetTable();
}

void OptimizerWindow::refreshUnitLabels()
{
    _targetTable->setHorizontalHeaderItem(TGT_COL_VALUE,
        new QTableWidgetItem(tr("目标值 (%1)").arg(_lengthUnit->name())));
    _targetTable->setToolTip(tr("光斑目标值以 %1 输入；稳区中心目标不需要指定元件")
        .arg(_lengthUnit->name()));
    _varTable->setToolTip(tr("长度类参数的下限、上限与候选值以 %1 输入，其他参数以自身的单位输入；优化值列在运行结束后显示最优参数")
        .arg(_lengthUnit->name()));
}

//------------------------------------------------------------------------------
//                              Variable table
//------------------------------------------------------------------------------

QString OptimizerWindow::formatSi(double valueSi, Z::Unit unit)
{
    return Z::format(unit->fromSi(valueSi));
}

QString OptimizerWindow::formatCandidates(const QVector<double>& candidatesSi, Z::Unit unit)
{
    QStringList parts;
    for (double c : candidatesSi)
        parts << Z::format(unit->fromSi(c));
    return parts.join(", ");
}

void OptimizerWindow::rebuildVariableTable()
{
    _updatingTables = true;
    const auto& vars = _function->variables();
    _varTable->setRowCount(vars.size());
    for (int row = 0; row < vars.size(); row++)
    {
        const auto& v = vars.at(row);

        auto* itEnabled = new QTableWidgetItem();
        itEnabled->setFlags(Qt::ItemIsEnabled | Qt::ItemIsUserCheckable | Qt::ItemIsSelectable);
        itEnabled->setCheckState(v.enabled ? Qt::Checked : Qt::Unchecked);
        _varTable->setItem(row, VAR_COL_ENABLED, itEnabled);

        auto* itParam = new QTableWidgetItem(v.displayName());
        itParam->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        _varTable->setItem(row, VAR_COL_PARAM, itParam);

        auto* modeCombo = new QComboBox();
        modeCombo->addItem(tr("连续"), int(OptimizerFunction::VarMode::Continuous));
        modeCombo->addItem(tr("离散"), int(OptimizerFunction::VarMode::Discrete));
        modeCombo->setCurrentIndex(v.mode == OptimizerFunction::VarMode::Continuous ? 0 : 1);
        connect(modeCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, modeCombo](int) {
            onVariableModeChanged(modeCombo);
        });
        _varTable->setCellWidget(row, VAR_COL_MODE, modeCombo);

        auto* itMin = new QTableWidgetItem();
        itMin->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable | Qt::ItemIsEditable);
        if (v.param)
        {
            auto unit = displayUnit(v.param->value().unit());
            itMin->setText(v.mode == OptimizerFunction::VarMode::Continuous
                ? Z::format(unit->fromSi(v.minSi))
                : formatCandidates(v.candidatesSi, unit));
        }
        _varTable->setItem(row, VAR_COL_MIN, itMin);

        auto* itMax = new QTableWidgetItem();
        if (v.mode == OptimizerFunction::VarMode::Continuous)
        {
            itMax->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable | Qt::ItemIsEditable);
            if (v.param)
                itMax->setText(Z::format(displayUnit(v.param->value().unit())->fromSi(v.maxSi)));
        }
        else
        {
            itMax->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
            itMax->setText(QStringLiteral("—"));
        }
        _varTable->setItem(row, VAR_COL_MAX, itMax);

        auto* itCurrent = new QTableWidgetItem();
        itCurrent->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        if (v.param)
            itCurrent->setText(formatSi(v.param->value().toSi(), displayUnit(v.param->value().unit())));
        _varTable->setItem(row, VAR_COL_CURRENT, itCurrent);

        auto* itResult = new QTableWidgetItem();
        itResult->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        _varTable->setItem(row, VAR_COL_RESULT, itResult);
    }
    _updatingTables = false;
    refreshResultValues();
}

void OptimizerWindow::refreshCurrentValues()
{
    if (_running)
        return;
    _updatingTables = true;
    const auto& vars = _function->variables();
    for (int row = 0; row < vars.size() && row < _varTable->rowCount(); row++)
    {
        const auto& v = vars.at(row);
        if (auto* it = _varTable->item(row, VAR_COL_CURRENT))
            it->setText(v.param ? formatSi(v.param->value().toSi(), displayUnit(v.param->value().unit())) : QString());
    }
    _updatingTables = false;
}

void OptimizerWindow::refreshResultValues()
{
    _updatingTables = true;
    const auto& vars = _function->variables();
    bool hasResult = _function->hasResult();
    const auto& best = _function->lastResult().bestValuesSi;
    for (int row = 0; row < vars.size() && row < _varTable->rowCount(); row++)
    {
        const auto& v = vars.at(row);
        if (auto* it = _varTable->item(row, VAR_COL_RESULT))
            it->setText(hasResult && row < best.size() && v.param
                ? formatSi(best.at(row), displayUnit(v.param->value().unit())) : QString());
    }
    _updatingTables = false;
}

int OptimizerWindow::rowOfCellWidget(QWidget* w, QTableWidget* table) const
{
    for (int row = 0; row < table->rowCount(); row++)
        for (int col = 0; col < table->columnCount(); col++)
            if (table->cellWidget(row, col) == w)
                return row;
    return -1;
}

void OptimizerWindow::onVariableModeChanged(QWidget* combo)
{
    if (_updatingTables || _running)
        return;
    int row = rowOfCellWidget(combo, _varTable);
    if (row < 0 || row >= _function->variables().size())
        return;
    auto* cb = qobject_cast<QComboBox*>(combo);
    if (!cb)
        return;
    _function->variables()[row].mode = OptimizerFunction::VarMode(cb->currentData().toInt());
    rebuildVariableTable();
}

void OptimizerWindow::onVariableCellChanged(int row, int col)
{
    if (_updatingTables || _running)
        return;
    if (row < 0 || row >= _function->variables().size())
        return;
    auto& v = _function->variables()[row];
    auto* item = _varTable->item(row, col);
    if (!item)
        return;

    if (col == VAR_COL_ENABLED)
    {
        v.enabled = item->checkState() == Qt::Checked;
        return;
    }
    if (!v.param)
        return;
    auto unit = displayUnit(v.param->value().unit());

    if (col == VAR_COL_MIN)
    {
        if (v.mode == OptimizerFunction::VarMode::Continuous)
        {
            bool ok = false;
            double val = item->text().toDouble(&ok);
            if (!ok)
            {
                Ori::Gui::PopupMessage::warning(tr("请输入有效的下限数值。"));
                _updatingTables = true;
                item->setText(Z::format(unit->fromSi(v.minSi)));
                _updatingTables = false;
                return;
            }
            v.minSi = unit->toSi(val);
        }
        else
        {
            QVector<double> candidates;
            if (!parseCandidates(item->text(), unit, candidates) || candidates.isEmpty())
            {
                Ori::Gui::PopupMessage::warning(tr("请输入至少一个候选值，用逗号分隔。"));
                _updatingTables = true;
                item->setText(formatCandidates(v.candidatesSi, unit));
                _updatingTables = false;
                return;
            }
            v.candidatesSi = candidates;
        }
        return;
    }
    if (col == VAR_COL_MAX && v.mode == OptimizerFunction::VarMode::Continuous)
    {
        bool ok = false;
        double val = item->text().toDouble(&ok);
        if (!ok)
        {
            Ori::Gui::PopupMessage::warning(tr("请输入有效的上限数值。"));
            _updatingTables = true;
            item->setText(Z::format(unit->fromSi(v.maxSi)));
            _updatingTables = false;
            return;
        }
        v.maxSi = unit->toSi(val);
        return;
    }
}

//------------------------------------------------------------------------------
//                              Target table
//------------------------------------------------------------------------------

void OptimizerWindow::rebuildTargetTable()
{
    _updatingTables = true;
    const auto& targets = _function->targets();
    _targetTable->setRowCount(targets.size());
    for (int row = 0; row < targets.size(); row++)
    {
        const auto& t = targets.at(row);

        auto* itElem = new QTableWidgetItem(
            t.kind == OptimizerFunction::TargetKind::StabilityCenter
                ? tr("全腔")
                : (t.element ? t.element->label() : QStringLiteral("—")));
        itElem->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        _targetTable->setItem(row, TGT_COL_ELEM, itElem);

        auto* kindCombo = new QComboBox();
        kindCombo->addItem(tr("子午光斑 w_T"), int(OptimizerFunction::TargetKind::BeamRadiusT));
        kindCombo->addItem(tr("弧矢光斑 w_S"), int(OptimizerFunction::TargetKind::BeamRadiusS));
        kindCombo->addItem(tr("像散 |wT-wS|"), int(OptimizerFunction::TargetKind::Astigmatism));
        kindCombo->addItem(tr("稳区中心 |g|"), int(OptimizerFunction::TargetKind::StabilityCenter));
        kindCombo->setCurrentIndex(int(t.kind));
        connect(kindCombo, QOverload<int>::of(&QComboBox::currentIndexChanged), this, [this, kindCombo](int) {
            onTargetKindChanged(kindCombo);
        });
        _targetTable->setCellWidget(row, TGT_COL_KIND, kindCombo);

        auto* itValue = new QTableWidgetItem();
        bool needValue = t.kind == OptimizerFunction::TargetKind::BeamRadiusT
                      || t.kind == OptimizerFunction::TargetKind::BeamRadiusS;
        if (needValue)
        {
            itValue->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable | Qt::ItemIsEditable);
            itValue->setText(Z::format(_lengthUnit->fromSi(t.targetSi)));
        }
        else
        {
            itValue->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
            itValue->setText(QStringLiteral("0"));
        }
        _targetTable->setItem(row, TGT_COL_VALUE, itValue);

        auto* itWeight = new QTableWidgetItem(Z::format(t.weight));
        itWeight->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable | Qt::ItemIsEditable);
        _targetTable->setItem(row, TGT_COL_WEIGHT, itWeight);

        auto* itCurrent = new QTableWidgetItem();
        itCurrent->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        _targetTable->setItem(row, TGT_COL_CURRENT, itCurrent);

        auto* itContrib = new QTableWidgetItem();
        itContrib->setFlags(Qt::ItemIsEnabled | Qt::ItemIsSelectable);
        _targetTable->setItem(row, TGT_COL_CONTRIB, itContrib);
    }
    _updatingTables = false;
    refreshTargetResults();
}

void OptimizerWindow::refreshTargetResults()
{
    _updatingTables = true;
    const auto& targets = _function->targets();
    for (int row = 0; row < targets.size() && row < _targetTable->rowCount(); row++)
    {
        const auto& t = targets.at(row);
        if (auto* it = _targetTable->item(row, TGT_COL_CURRENT))
        {
            if (std::isnan(t.currentSi))
                it->setText(QStringLiteral("—"));
            else if (t.kind == OptimizerFunction::TargetKind::StabilityCenter)
                it->setText(Z::format(t.currentSi));
            else
                it->setText(Z::format(_lengthUnit->fromSi(t.currentSi)));
        }
        if (auto* it = _targetTable->item(row, TGT_COL_CONTRIB))
            it->setText(std::isnan(t.contribution) ? QStringLiteral("—") : Z::format(t.contribution));
    }
    _updatingTables = false;
}

void OptimizerWindow::onTargetKindChanged(QWidget* combo)
{
    if (_updatingTables || _running)
        return;
    int row = rowOfCellWidget(combo, _targetTable);
    if (row < 0 || row >= _function->targets().size())
        return;
    auto* cb = qobject_cast<QComboBox*>(combo);
    if (!cb)
        return;
    auto& t = _function->targets()[row];
    auto newKind = OptimizerFunction::TargetKind(cb->currentData().toInt());
    bool needsElem = newKind != OptimizerFunction::TargetKind::StabilityCenter;
    if (needsElem && !t.element)
    {
        // A beam/astigmatism target needs an element; the table has no
        // element picker, so keep the old kind and ask for re-adding.
        Ori::Gui::PopupMessage::warning(tr("该目标需要指定元件，请删除后重新添加目标。"));
        _updatingTables = true;
        cb->setCurrentIndex(int(t.kind));
        _updatingTables = false;
        return;
    }
    if (newKind == OptimizerFunction::TargetKind::StabilityCenter)
        t.element = nullptr;
    t.kind = newKind;
    rebuildTargetTable();
}

void OptimizerWindow::onTargetCellChanged(int row, int col)
{
    if (_updatingTables || _running)
        return;
    if (row < 0 || row >= _function->targets().size())
        return;
    auto& t = _function->targets()[row];
    auto* item = _targetTable->item(row, col);
    if (!item)
        return;

    if (col == TGT_COL_VALUE
        && (t.kind == OptimizerFunction::TargetKind::BeamRadiusT
            || t.kind == OptimizerFunction::TargetKind::BeamRadiusS))
    {
        bool ok = false;
        double val = item->text().toDouble(&ok);
        if (!ok || !(val > 0))
        {
            Ori::Gui::PopupMessage::warning(tr("请输入大于 0 的目标值（%1）。").arg(_lengthUnit->name()));
            _updatingTables = true;
            item->setText(Z::format(_lengthUnit->fromSi(t.targetSi)));
            _updatingTables = false;
            return;
        }
        t.targetSi = _lengthUnit->toSi(val);
        return;
    }
    if (col == TGT_COL_WEIGHT)
    {
        bool ok = false;
        double val = item->text().toDouble(&ok);
        if (!ok || !(val > 0))
        {
            Ori::Gui::PopupMessage::warning(tr("请输入大于 0 的权重。"));
            _updatingTables = true;
            item->setText(Z::format(t.weight));
            _updatingTables = false;
            return;
        }
        t.weight = val;
        return;
    }
}

//------------------------------------------------------------------------------
//                              Add / remove rows
//------------------------------------------------------------------------------

void OptimizerWindow::addVariable()
{
    OptimizerVariableDlg dlg(schema(), _lengthUnit);
    if (!dlg.run())
        return;
    const auto& r = dlg.result();
    for (const auto& v : _function->variables())
        if (v.param == r.param)
        {
            Ori::Gui::PopupMessage::warning(tr("参数 %1 已在变量表中。").arg(r.param->alias()));
            return;
        }
    OptimizerFunction::Variable var;
    var.element = r.element;
    var.param = r.param;
    var.isGlobalParam = (r.element == schema()->globalParamsAsElem());
    var.mode = r.mode;
    var.minSi = r.minSi;
    var.maxSi = r.maxSi;
    var.candidatesSi = r.candidatesSi;
    var.startSi = r.param->value().toSi();
    _function->variables() << var;
    rebuildVariableTable();
    schema()->markModified("OptimizerWindow::addVariable");
}

void OptimizerWindow::removeVariable()
{
    int row = _varTable->currentRow();
    if (row < 0 || row >= _function->variables().size())
    {
        Ori::Gui::PopupMessage::hint(tr("请先在变量表中选择一行。"));
        return;
    }
    int groupsBefore = _function->lengthGroups().size();
    _function->onVariableRemoved(row);
    if (_function->lengthGroups().size() < groupsBefore)
        Ori::Gui::PopupMessage::hint(tr("已删除包含该变量的总长固定组。"));
    _function->variables().removeAt(row);
    rebuildVariableTable();
    refreshLengthGroupLabel();
    schema()->markModified("OptimizerWindow::removeVariable");
}

void OptimizerWindow::refreshLengthGroupLabel()
{
    if (_function->lengthGroups().isEmpty())
    {
        _lengthGroupLabel->setText(tr("未设置总长固定"));
        return;
    }
    const auto& g = _function->lengthGroups().first();
    QStringList names;
    for (int mi : g.members)
        if (mi >= 0 && mi < _function->variables().size())
            names << _function->variables().at(mi).displayName();
    int dep = _function->dependentVarIndex(g);
    QString depName = (dep >= 0 && dep < _function->variables().size())
        ? _function->variables().at(dep).displayName() : QStringLiteral("—");
    _lengthGroupLabel->setText(tr("总长固定：%1 = %2 %3（从属：%4）")
        .arg(names.join("+"))
        .arg(Z::format(_lengthUnit->fromSi(g.totalSi)))
        .arg(_lengthUnit->name())
        .arg(depName));
}

void OptimizerWindow::editLengthGroup()
{
    OptimizerLengthGroupDlg dlg(_function, _lengthUnit);
    if (!dlg.run())
        return;
    const auto& r = dlg.result();
    if (r.clear)
    {
        if (!_function->lengthGroups().isEmpty())
            _function->lengthGroups().removeFirst();
    }
    else
    {
        // This window edits only the first group; any further groups
        // (e.g. from a file) are preserved untouched.
        if (_function->lengthGroups().isEmpty())
            _function->lengthGroups() << r.group;
        else
            _function->lengthGroups()[0] = r.group;
    }
    refreshLengthGroupLabel();
    schema()->markModified("OptimizerWindow::editLengthGroup");
}

void OptimizerWindow::addTarget()
{
    OptimizerTargetDlg dlg(schema(), _lengthUnit);
    if (!dlg.run())
        return;
    const auto& r = dlg.result();
    OptimizerFunction::Target t;
    t.kind = r.kind;
    t.element = r.element;
    t.targetSi = r.targetSi;
    t.weight = r.weight;
    _function->targets() << t;
    rebuildTargetTable();
    schema()->markModified("OptimizerWindow::addTarget");
}

void OptimizerWindow::removeTarget()
{
    int row = _targetTable->currentRow();
    if (row < 0 || row >= _function->targets().size())
    {
        Ori::Gui::PopupMessage::hint(tr("请先在目标表中选择一行。"));
        return;
    }
    _function->targets().removeAt(row);
    rebuildTargetTable();
    schema()->markModified("OptimizerWindow::removeTarget");
}

//------------------------------------------------------------------------------
//                              Run / Apply / Revert
//------------------------------------------------------------------------------

void OptimizerWindow::startOptimization()
{
    if (_running)
        return;
    QString err = _function->validate();
    if (!err.isEmpty())
    {
        Ori::Gui::PopupMessage::warning(err);
        return;
    }
    _running = true;
    _stopFlag = false;
    _closeRequested = false;
    setControlsEnabled(false);
    _meritLabel->setText(tr("Merit：—"));
    _statusBar->setText(STATUS_INFO, tr("优化运行中…"));

    _function->run(_maxIter->value(), &_stopFlag, [this](double merit) {
        _meritLabel->setText(tr("Merit：%1").arg(Z::format(merit)));
    });

    _running = false;
    setControlsEnabled(true);
    refreshCurrentValues();
    refreshTargetResults();
    refreshResultValues();
    showResultSummary();

    if (_closeRequested)
        close();
}

void OptimizerWindow::stopOptimization()
{
    _stopFlag = true;
}

void OptimizerWindow::applyResult()
{
    if (!_function->hasResult())
        return;
    _function->apply();
    refreshCurrentValues();
    showResultSummary();
}

void OptimizerWindow::revertResult()
{
    if (!_function->hasResult())
        return;
    _function->revert();
    refreshCurrentValues();
    showResultSummary();
}

void OptimizerWindow::showResultSummary()
{
    QString summary;
    if (!_function->ok())
    {
        summary = _function->errorText();
    }
    else if (_function->hasResult())
    {
        const auto& r = _function->lastResult();
        QString state = r.stopped ? tr("已停止")
            : (r.budgetExceeded ? tr("已达评估预算")
            : (r.converged ? tr("已收敛") : tr("未收敛")));
        summary = tr("Merit：%1 | 迭代 %2 | 评估 %3 | %4")
            .arg(Z::format(r.bestMerit)).arg(r.iterations).arg(r.evaluations).arg(state);
        _meritLabel->setText(tr("Merit：%1").arg(Z::format(r.bestMerit)));
    }
    else
    {
        summary = tr("尚未运行优化。");
    }
    _statusBar->setText(STATUS_INFO, summary);
}

//------------------------------------------------------------------------------
//                              Storable
//------------------------------------------------------------------------------

bool OptimizerWindow::storableWrite(QJsonObject& root, Z::Report*)
{
    QJsonArray varsJson;
    for (const auto& v : _function->variables())
    {
        if (!v.param || !v.element)
            continue;
        QJsonObject varJson;
        varJson["global"] = v.isGlobalParam;
        varJson["elem"] = v.isGlobalParam ? QString() : v.element->label();
        varJson["param"] = v.param->alias();
        varJson["enabled"] = v.enabled;
        varJson["mode"] = v.mode == OptimizerFunction::VarMode::Continuous ? "cont" : "disc";
        varJson["min"] = v.minSi;
        varJson["max"] = v.maxSi;
        QJsonArray cands;
        for (double c : v.candidatesSi)
            cands << c;
        varJson["candidates"] = cands;
        varsJson << varJson;
    }
    QJsonArray targetsJson;
    for (const auto& t : _function->targets())
    {
        QJsonObject targetJson;
        targetJson["elem"] = t.element ? t.element->label() : QString();
        QString kindStr;
        switch (t.kind)
        {
        case OptimizerFunction::TargetKind::BeamRadiusT: kindStr = "wT"; break;
        case OptimizerFunction::TargetKind::BeamRadiusS: kindStr = "wS"; break;
        case OptimizerFunction::TargetKind::Astigmatism: kindStr = "astig"; break;
        case OptimizerFunction::TargetKind::StabilityCenter: kindStr = "stab"; break;
        }
        targetJson["kind"] = kindStr;
        targetJson["target"] = t.targetSi;
        targetJson["weight"] = t.weight;
        targetsJson << targetJson;
    }
    QJsonArray groupsJson;
    for (const auto& g : _function->lengthGroups())
    {
        QJsonObject groupJson;
        groupJson["total"] = g.totalSi;
        groupJson["enabled"] = g.enabled;
        QJsonArray membersJson;
        for (int mi : g.members)
        {
            if (mi < 0 || mi >= _function->variables().size())
                continue;
            const auto& v = _function->variables().at(mi);
            if (!v.param || !v.element)
                continue;
            QJsonObject memberJson;
            memberJson["global"] = v.isGlobalParam;
            memberJson["elem"] = v.isGlobalParam ? QString() : v.element->label();
            memberJson["param"] = v.param->alias();
            membersJson << memberJson;
        }
        groupJson["members"] = membersJson;
        groupsJson << groupJson;
    }
    root["function"] = QJsonObject({
        { "variables", varsJson },
        { "targets", targetsJson },
        { "lengthGroups", groupsJson },
        { "lengthUnit", _lengthUnit->alias() },
    });
    return true;
}

bool OptimizerWindow::storableRead(const QJsonObject& root, Z::Report* report)
{
    auto funcJson = root["function"].toObject();
    if (funcJson.isEmpty())
        return true;

    auto unitAlias = funcJson["lengthUnit"].toString();
    if (!unitAlias.isEmpty())
    {
        _lengthUnit = Z::Units::findByAlias(unitAlias, Z::Units::mm());
        QSignalBlocker blocker(_lengthUnitCombo);
        _lengthUnitCombo->setCurrentIndex(_lengthUnitCombo->findData(_lengthUnit->alias()));
        refreshUnitLabels();
    }

    auto varsJson = funcJson["variables"].toArray();
    for (const auto& varValue : varsJson)
    {
        auto varJson = varValue.toObject();
        bool isGlobal = varJson["global"].toBool(false);
        Element* elem = nullptr;
        if (isGlobal)
            elem = const_cast<Element*>(schema()->globalParamsAsElem());
        else
            elem = schema()->element(varJson["elem"].toString());
        if (!elem)
        {
            if (report)
                report->warning(tr("谐振腔优化：找不到元件 %1，已跳过该变量。").arg(varJson["elem"].toString()));
            continue;
        }
        auto* param = elem->param(varJson["param"].toString());
        if (!param)
        {
            if (report)
                report->warning(tr("谐振腔优化：元件 %1 没有参数 %2，已跳过该变量。")
                    .arg(elem->label(), varJson["param"].toString()));
            continue;
        }
        OptimizerFunction::Variable var;
        var.element = elem;
        var.param = param;
        var.isGlobalParam = isGlobal;
        var.enabled = varJson["enabled"].toBool(true);
        var.mode = varJson["mode"].toString() == "disc"
            ? OptimizerFunction::VarMode::Discrete : OptimizerFunction::VarMode::Continuous;
        var.minSi = varJson["min"].toDouble(0);
        var.maxSi = varJson["max"].toDouble(0);
        for (const auto& c : varJson["candidates"].toArray())
            var.candidatesSi << c.toDouble();
        var.startSi = param->value().toSi();
        _function->variables() << var;
    }

    auto groupsJson = funcJson["lengthGroups"].toArray();
    for (const auto& groupValue : groupsJson)
    {
        auto groupJson = groupValue.toObject();
        OptimizerFunction::LengthGroup g;
        g.totalSi = groupJson["total"].toDouble(0);
        g.enabled = groupJson["enabled"].toBool(true);
        for (const auto& memberValue : groupJson["members"].toArray())
        {
            auto memberJson = memberValue.toObject();
            bool isGlobal = memberJson["global"].toBool(false);
            Element* elem = nullptr;
            if (isGlobal)
                elem = const_cast<Element*>(schema()->globalParamsAsElem());
            else
                elem = schema()->element(memberJson["elem"].toString());
            if (!elem)
            {
                if (report)
                    report->warning(tr("谐振腔优化：总长固定组找不到元件 %1，已跳过该成员。").arg(memberJson["elem"].toString()));
                continue;
            }
            auto* param = elem->param(memberJson["param"].toString());
            if (!param)
            {
                if (report)
                    report->warning(tr("谐振腔优化：元件 %1 没有参数 %2，已跳过该总长固定组成员。")
                        .arg(elem->label(), memberJson["param"].toString()));
                continue;
            }
            int varIndex = -1;
            for (int i = 0; i < _function->variables().size(); i++)
            {
                const auto& v = _function->variables().at(i);
                if (v.element == elem && v.param == param)
                {
                    varIndex = i;
                    break;
                }
            }
            if (varIndex < 0)
            {
                if (report)
                    report->warning(tr("谐振腔优化：参数 %1.%2 不在变量表中，已跳过该总长固定组成员。")
                        .arg(elem->label(), param->alias()));
                continue;
            }
            g.members << varIndex;
        }
        // Old files have no "lengthGroups" key (empty array above), so
        // they simply load without a group. A stored group that no longer
        // validates (e.g. a member was deleted from the variable table)
        // is dropped with a warning instead of breaking the load.
        QString gerr = _function->validateGroup(g);
        if (!gerr.isEmpty())
        {
            if (report)
                report->warning(tr("谐振腔优化：总长固定组无效（%1），已跳过。").arg(gerr));
            continue;
        }
        _function->lengthGroups() << g;
    }

    auto targetsJson = funcJson["targets"].toArray();
    for (const auto& targetValue : targetsJson)
    {
        auto targetJson = targetValue.toObject();
        OptimizerFunction::Target t;
        auto kindStr = targetJson["kind"].toString();
        if (kindStr == "wT") t.kind = OptimizerFunction::TargetKind::BeamRadiusT;
        else if (kindStr == "wS") t.kind = OptimizerFunction::TargetKind::BeamRadiusS;
        else if (kindStr == "astig") t.kind = OptimizerFunction::TargetKind::Astigmatism;
        else t.kind = OptimizerFunction::TargetKind::StabilityCenter;
        if (t.kind != OptimizerFunction::TargetKind::StabilityCenter)
        {
            t.element = schema()->element(targetJson["elem"].toString());
            if (!t.element)
            {
                if (report)
                    report->warning(tr("谐振腔优化：找不到目标元件 %1，已跳过该目标。")
                        .arg(targetJson["elem"].toString()));
                continue;
            }
        }
        t.targetSi = targetJson["target"].toDouble(0);
        t.weight = targetJson["weight"].toDouble(1.0);
        _function->targets() << t;
    }

    rebuildVariableTable();
    rebuildTargetTable();
    refreshLengthGroupLabel();
    return true;
}

//------------------------------------------------------------------------------
//                              OptimizerVariableDlg
//------------------------------------------------------------------------------

OptimizerVariableDlg::OptimizerVariableDlg(Schema* schema, Z::Unit lengthUnit)
    : RezonatorDialog(DontDeleteOnClose | UseHelpButton), _schema(schema), _lengthUnit(lengthUnit)
{
    setWindowTitle(tr("添加变量"));
    setObjectName("OptimizerVariableDlg");

    _elemSelector = new ElemAndParamSelector(schema, {
        .elemFilter = ElementFilters::elemsWithVisibleParams(),
        .paramFilter = Z::Utils::defaultParamFilter(),
        .includeCustomParams = true,
    });
    connect(_elemSelector, SIGNAL(selectionChanged()), this, SLOT(guessBounds()));

    _mode = new QComboBox();
    _mode->addItem(tr("连续范围"), int(OptimizerFunction::VarMode::Continuous));
    _mode->addItem(tr("离散列表"), int(OptimizerFunction::VarMode::Discrete));
    connect(_mode, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &OptimizerVariableDlg::modeChanged);

    _minEdit = new QLineEdit();
    _maxEdit = new QLineEdit();
    _candidatesEdit = new QLineEdit();
    _candidatesEdit->setPlaceholderText(tr("候选值，用逗号分隔，如 100, 150, 200"));
    _unitLabel = new QLabel();

    auto form = new QFormLayout();
    form->addRow(tr("模式"), _mode);
    form->addRow(tr("下限"), _minEdit);
    form->addRow(tr("上限"), _maxEdit);
    form->addRow(tr("候选列表"), _candidatesEdit);
    form->addRow(tr("单位"), _unitLabel);

    mainLayout()->addLayout(_elemSelector);
    mainLayout()->addSpacing(8);
    mainLayout()->addLayout(form);
    mainLayout()->addStretch();

    modeChanged(0);
    guessBounds();
}

void OptimizerVariableDlg::populate()
{
    guessBounds();
}

void OptimizerVariableDlg::modeChanged(int index)
{
    bool continuous = index == 0;
    _minEdit->setEnabled(continuous);
    _maxEdit->setEnabled(continuous);
    _candidatesEdit->setEnabled(!continuous);
}

void OptimizerVariableDlg::guessBounds()
{
    auto* param = _elemSelector->selectedParameter();
    if (!param)
        return;
    auto unit = param->value().unit();
    // Length-dimension parameters are shown in the window's length unit;
    // other parameters keep their own unit.
    Z::Unit dispUnit = (Z::Units::guessDim(unit) == Z::Dims::linear()) ? _lengthUnit : unit;
    double current = dispUnit->fromSi(param->value().toSi());
    double minV = current > 0 ? current * 0.5 : (current < 0 ? current * 2 : -1);
    double maxV = current > 0 ? current * 2 : (current < 0 ? current * 0.5 : 1);
    _minEdit->setText(Z::format(minV));
    _maxEdit->setText(Z::format(maxV));
    _unitLabel->setText(dispUnit->name());
}

void OptimizerVariableDlg::collect()
{
    auto res = _elemSelector->verify();
    if (!res) return res.show(this);

    auto* param = _elemSelector->selectedParameter();
    if (!param)
        return WidgetResult::fail(_mode, tr("请选择参数。")).show(this);
    if (param->valueDriver() != Z::ParamValueDriver::None)
        return WidgetResult::fail(_mode, tr("参数 %1 由公式或链接驱动，不能作为优化变量。")
            .arg(param->alias())).show(this);

    _result.element = _elemSelector->selectedElement();
    _result.param = param;
    _result.mode = OptimizerFunction::VarMode(_mode->currentData().toInt());
    auto unit = param->value().unit();
    Z::Unit dispUnit = (Z::Units::guessDim(unit) == Z::Dims::linear()) ? _lengthUnit : unit;
    if (_result.mode == OptimizerFunction::VarMode::Continuous)
    {
        bool okMin = false, okMax = false;
        double minV = _minEdit->text().toDouble(&okMin);
        double maxV = _maxEdit->text().toDouble(&okMax);
        if (!okMin || !okMax)
            return WidgetResult::fail(_minEdit, tr("请输入有效的下限和上限。")).show(this);
        _result.minSi = dispUnit->toSi(minV);
        _result.maxSi = dispUnit->toSi(maxV);
        if (!(_result.minSi < _result.maxSi))
            return WidgetResult::fail(_minEdit, tr("下限必须小于上限。")).show(this);
    }
    else
    {
        if (!parseCandidates(_candidatesEdit->text(), dispUnit, _result.candidatesSi)
            || _result.candidatesSi.isEmpty())
            return WidgetResult::fail(_candidatesEdit, tr("请输入至少一个候选值，用逗号分隔。")).show(this);
    }
    accept();
}

//------------------------------------------------------------------------------
//                              OptimizerTargetDlg
//------------------------------------------------------------------------------

OptimizerTargetDlg::OptimizerTargetDlg(Schema* schema, Z::Unit lengthUnit)
    : RezonatorDialog(DontDeleteOnClose | UseHelpButton), _lengthUnit(lengthUnit)
{
    setWindowTitle(tr("添加目标"));
    setObjectName("OptimizerTargetDlg");

    _elemSelector = new ElemSelectorWidget(schema, {});
    _kind = new QComboBox();
    _kind->addItem(tr("子午光斑 w_T"), int(OptimizerFunction::TargetKind::BeamRadiusT));
    _kind->addItem(tr("弧矢光斑 w_S"), int(OptimizerFunction::TargetKind::BeamRadiusS));
    _kind->addItem(tr("像散 |wT-wS|"), int(OptimizerFunction::TargetKind::Astigmatism));
    _kind->addItem(tr("稳区中心 |g|"), int(OptimizerFunction::TargetKind::StabilityCenter));
    connect(_kind, QOverload<int>::of(&QComboBox::currentIndexChanged), this, &OptimizerTargetDlg::kindChanged);

    _targetEdit = new QLineEdit();
    _targetEdit->setPlaceholderText(tr("目标光斑半径，%1").arg(_lengthUnit->name()));
    _weightEdit = new QLineEdit(QStringLiteral("1"));

    auto form = new QFormLayout();
    form->addRow(tr("目标元件"), _elemSelector);
    form->addRow(tr("指标"), _kind);
    form->addRow(tr("目标值 (%1)").arg(_lengthUnit->name()), _targetEdit);
    form->addRow(tr("权重"), _weightEdit);

    mainLayout()->addLayout(form);
    mainLayout()->addStretch();

    kindChanged(0);
}

void OptimizerTargetDlg::kindChanged(int)
{
    auto kind = OptimizerFunction::TargetKind(_kind->currentData().toInt());
    _elemSelector->setEnabled(kind != OptimizerFunction::TargetKind::StabilityCenter);
    _targetEdit->setEnabled(kind == OptimizerFunction::TargetKind::BeamRadiusT
        || kind == OptimizerFunction::TargetKind::BeamRadiusS);
    // Stability-center targets use a smaller default weight: their merit
    // scale (g^2) otherwise dominates beam radius targets.
    _weightEdit->setText(kind == OptimizerFunction::TargetKind::StabilityCenter
        ? QStringLiteral("0.1") : QStringLiteral("1"));
}

void OptimizerTargetDlg::collect()
{
    auto kind = OptimizerFunction::TargetKind(_kind->currentData().toInt());
    _result.kind = kind;
    if (kind != OptimizerFunction::TargetKind::StabilityCenter)
    {
        auto res = _elemSelector->verify();
        if (!res) return res.show(this);
        _result.element = _elemSelector->selectedElement();
        if (!_result.element)
            return WidgetResult::fail(_elemSelector, tr("请选择目标元件。")).show(this);
    }
    if (kind == OptimizerFunction::TargetKind::BeamRadiusT
        || kind == OptimizerFunction::TargetKind::BeamRadiusS)
    {
        bool ok = false;
        double v = _targetEdit->text().toDouble(&ok);
        if (!ok || !(v > 0))
            return WidgetResult::fail(_targetEdit, tr("请输入大于 0 的目标光斑半径（%1）。").arg(_lengthUnit->name())).show(this);
        _result.targetSi = _lengthUnit->toSi(v);
    }
    bool okW = false;
    double w = _weightEdit->text().toDouble(&okW);
    if (!okW || !(w > 0))
        return WidgetResult::fail(_weightEdit, tr("请输入大于 0 的权重。")).show(this);
    _result.weight = w;
    accept();
}

//------------------------------------------------------------------------------
//                              OptimizerLengthGroupDlg
//------------------------------------------------------------------------------

OptimizerLengthGroupDlg::OptimizerLengthGroupDlg(OptimizerFunction* function, Z::Unit lengthUnit)
    : RezonatorDialog(DontDeleteOnClose | UseHelpButton), _function(function), _lengthUnit(lengthUnit)
{
    setWindowTitle(tr("总长固定"));
    setObjectName("OptimizerLengthGroupDlg");

    _memberList = new QListWidget();
    const auto& vars = _function->variables();
    const auto& groups = _function->lengthGroups();
    QSet<int> currentMembers;
    if (!groups.isEmpty())
        for (int mi : groups.first().members)
            currentMembers << mi;
    // Members of further groups (if any) cannot be picked here: this
    // dialog edits only the first group, and a variable may belong to at
    // most one group.
    QSet<int> otherGroupMembers;
    for (int gi = 1; gi < groups.size(); gi++)
        for (int mi : groups.at(gi).members)
            otherGroupMembers << mi;
    bool anyEligible = false;
    for (int i = 0; i < vars.size(); i++)
    {
        const auto& v = vars.at(i);
        if (!OptimizerFunction::isLengthGroupEligible(v) || otherGroupMembers.contains(i))
            continue;
        anyEligible = true;
        auto* item = new QListWidgetItem(v.displayName(), _memberList);
        item->setFlags(Qt::ItemIsEnabled | Qt::ItemIsUserCheckable | Qt::ItemIsSelectable);
        item->setData(Qt::UserRole, i);
        // No group yet: pre-check every eligible variable -- the common
        // case is "all arm lengths", and unchecking is cheaper than
        // checking one by one.
        bool checked = groups.isEmpty() ? true : currentMembers.contains(i);
        item->setCheckState(checked ? Qt::Checked : Qt::Unchecked);
    }
    connect(_memberList, &QListWidget::itemChanged, this, &OptimizerLengthGroupDlg::onSelectionChanged);

    _totalEdit = new QLineEdit();
    connect(_totalEdit, &QLineEdit::textEdited, this, &OptimizerLengthGroupDlg::onTotalEdited);

    auto clearBtn = new QPushButton(tr("清除约束"));
    clearBtn->setEnabled(!groups.isEmpty());
    connect(clearBtn, &QPushButton::clicked, this, &OptimizerLengthGroupDlg::clearGroup);

    _hintLabel = new QLabel();
    _hintLabel->setWordWrap(true);

    auto form = new QFormLayout();
    form->addRow(tr("固定总长 (%1)").arg(_lengthUnit->name()), _totalEdit);
    form->addRow(tr(""), clearBtn);

    auto info = new QLabel(tr("仅连续模式的长度参数可选（不含曲率 R / 焦距 F）。"
        "组内最后一个勾选的变量为从属变量：优化时它的值自动取“总长 − 其余成员”，"
        "从属变量超出范围时该次评估会被惩罚、搜索自动避开。"));
    info->setWordWrap(true);

    mainLayout()->addWidget(new QLabel(tr("选择要固定总长的变量：")));
    mainLayout()->addWidget(_memberList);
    mainLayout()->addLayout(form);
    mainLayout()->addWidget(_hintLabel);
    mainLayout()->addWidget(info);
    mainLayout()->addStretch();

    if (!anyEligible)
    {
        _hintLabel->setText(tr("没有可用的长度变量：请先在变量表中添加连续模式的长度参数。"));
        _totalEdit->setEnabled(false);
    }
    else if (!groups.isEmpty())
    {
        // Editing an existing group: keep its total, do not recompute.
        _totalEdit->setText(Z::format(_lengthUnit->fromSi(groups.first().totalSi)));
        _totalEdited = true;
        onSelectionChanged();
    }
    else
        refreshTotalFromSelection();
}

void OptimizerLengthGroupDlg::refreshTotalFromSelection()
{
    if (_totalEdited)
        return;
    double sum = 0.0;
    const auto& vars = _function->variables();
    for (int row = 0; row < _memberList->count(); row++)
    {
        auto* item = _memberList->item(row);
        if (item->checkState() != Qt::Checked)
            continue;
        int vi = item->data(Qt::UserRole).toInt();
        if (vi >= 0 && vi < vars.size() && vars.at(vi).param)
            sum += vars.at(vi).param->value().toSi();
    }
    QSignalBlocker blocker(_totalEdit);
    _totalEdit->setText(Z::format(_lengthUnit->fromSi(sum)));
}

void OptimizerLengthGroupDlg::onSelectionChanged()
{
    refreshTotalFromSelection();
    // The dependent variable is the last checked one, in table order.
    QString depName;
    for (int row = _memberList->count() - 1; row >= 0; row--)
    {
        auto* item = _memberList->item(row);
        if (item->checkState() == Qt::Checked)
        {
            depName = item->text();
            break;
        }
    }
    _hintLabel->setText(depName.isEmpty()
        ? tr("请至少勾选 2 个变量。")
        : tr("从属变量：%1（优化时自动取“总长 − 其余成员”）。").arg(depName));
}

void OptimizerLengthGroupDlg::onTotalEdited()
{
    _totalEdited = true;
}

void OptimizerLengthGroupDlg::clearGroup()
{
    _result.clear = true;
    accept();
}

void OptimizerLengthGroupDlg::collect()
{
    if (_result.clear)
    {
        accept();
        return;
    }
    QVector<int> members;
    for (int row = 0; row < _memberList->count(); row++)
    {
        auto* item = _memberList->item(row);
        if (item->checkState() == Qt::Checked)
            members << item->data(Qt::UserRole).toInt();
    }
    std::sort(members.begin(), members.end());

    bool ok = false;
    double total = _totalEdit->text().toDouble(&ok);
    if (!ok)
        return WidgetResult::fail(_totalEdit, tr("请输入有效的固定总长。")).show(this);

    OptimizerFunction::LengthGroup group;
    group.members = members;
    group.totalSi = _lengthUnit->toSi(total);
    group.enabled = true;
    // When editing the existing first group, skip it in the overlap check.
    int skip = _function->lengthGroups().isEmpty() ? -1 : 0;
    QString err = _function->validateGroup(group, skip);
    if (!err.isEmpty())
        return WidgetResult::fail(_memberList, err).show(this);

    _result.group = group;
    _result.clear = false;
    accept();
}
