#include "PlotFuncWindow.h"

#include "../app/AppSettings.h"
#include "../app/HelpSystem.h"
#include "../app/PersistentState.h"
#include "../core/Format.h"
#include "../core/Protocol.h"
#include "../funcs/InfoFuncWindow.h"
#include "../funcs/FuncWindowHelpers.h"
#include "../math/InfoFunctions.h"
#include "../math/PlotFuncRoundTripFunction.h"
#include "../math/FunctionGraph.h"
#include "../widgets/PlotHelpers.h"
#include "../widgets/FrozenStateButton.h"
#include "../widgets/PlotParamsPanel.h"
#include "../widgets/UnitWidgets.h"

#include "helpers/OriDialogs.h"
#include "helpers/OriWidgets.h"
#include "widgets/OriFlatToolBar.h"
#include "widgets/OriStatusBar.h"
#include "widgets/OriLabels.h"

#include "qcpl_cursor.h"
#include "qcpl_cursor_panel.h"
#include "qcpl_format.h"
#include "qcpl_graph_grid.h"
#include "qcpl_io_json.h"
#include "qcpl_plot.h"

using namespace Ori::Gui::V0;

enum PlotWindowStatusPanels
{
    STATUS_UNIT_X,
    STATUS_UNIT_Y,
    STATUS_POINTS,
    STATUS_INFO,

    STATUS_PANELS_COUNT,
};

PlotFuncWindow::PlotFuncWindow(PlotFunction *func) : SchemaMdiChild(func->schema()), _function(func)
{
    setTitleAndIcon(FuncWindowHelpers::makeWindowTitle(func), function()->iconPath());

    createContent();
    createActions();
    createMenuBar();
    createToolBar();
    createContextMenus();
    createStatusBar();

    updatePlotItemToggleActions();
}

PlotFuncWindow::~PlotFuncWindow()
{
    delete _function;
    delete _graphs;
}

void PlotFuncWindow::createActions()
{
    actnUpdate = action(tr("更新"), this, SLOT(update()), ":/toolbar/update", Qt::Key_F5);
    actnUpdateParams = action(tr("按参数更新…"), this,
        SLOT(updateWithParams()), ":/toolbar/update_params", Qt::CTRL | Qt::Key_F5);

    actnShowT = action(tr("显示 T 平面"), this, SLOT(activateModeT()), ":/toolbar/plot_t");
    actnShowS = action(tr("显示 S 平面"), this, SLOT(activateModeS()), ":/toolbar/plot_s");
    actnShowFlippedTS = action(tr("T-S 翻转模式"), this, SLOT(activateModeFlippedTS()), ":/toolbar/plot_ts");
    actnShowT->setCheckable(true);
    actnShowS->setCheckable(true);
    actnShowFlippedTS->setCheckable(true);
    actnShowT->setChecked(true);
    actnShowS->setChecked(true);

    actnShowRoundTrip = action(tr("显示往返"), this, SLOT(showRoundTrip()), ":/toolbar/func_round_trip");

    actnFreeze = Ori::Gui::V0::toggledAction(tr("冻结"), this, SLOT(freeze(bool)), ":/toolbar/freeze", Qt::CTRL | Qt::Key_F);

    actnAutolimits = action(tr("适应图形"), _plot, SLOT(autolimits()), ":/toolbar/limits_auto");
    actnAutolimitsX = action(tr("按 X 轴适应图形"), _plot, SLOT(autolimitsX()), ":/toolbar/limits_auto_x");
    actnAutolimitsY = action(tr("按 Y 轴适应图形"), _plot, SLOT(autolimitsY()), ":/toolbar/limits_auto_y");

    actnZoomIn = action(tr("放大"), _plot, SLOT(zoomIn()), ":/toolbar/limits_zoom_in");
    actnZoomOut = action(tr("缩小"), _plot, SLOT(zoomOut()), ":/toolbar/limits_zoom_out");
    actnZoomInX = action(tr("沿 X 轴放大"), _plot, SLOT(zoomInX()), ":/toolbar/limits_zoom_in_x");
    actnZoomOutX = action(tr("沿 X 轴缩小"), _plot, SLOT(zoomOutX()), ":/toolbar/limits_zoom_out_x");
    actnZoomInY = action(tr("沿 Y 轴放大"), _plot, SLOT(zoomInY()), ":/toolbar/limits_zoom_in_y");
    actnZoomOutY = action(tr("沿 Y 轴缩小"), _plot, SLOT(zoomOutY()), ":/toolbar/limits_zoom_out_y");

    actnSetLimitsX = action(tr("X 轴范围…"), _plot, SLOT(limitsDlgX()));
    actnSetLimitsY = action(tr("Y 轴范围…"), _plot, SLOT(limitsDlgY()));
    actnSetTextX = action(tr("X 轴文本…"), _plot, SLOT(axisTextDlgX()));
    actnSetTextY = action(tr("Y 轴文本…"), _plot, SLOT(axisTextDlgY()));
    actnSetTextT = action(tr("标题文本…"), _plot, SLOT(titleTextDlg()));

    // These actions also used in context menus, so we add the "Format" word for clearity
    // even though it's not necessary for subcommands of the "Format" menu
    actnFormatTitle = action(tr("标题格式…"), _plot, SLOT(titleFormatDlg()));
    actnFormatLegend = action(tr("图例格式…"), _plot, SLOT(legendFormatDlg()));
    actnFormatX = action(tr("X 轴格式…"), _plot, SLOT(axisFormatDlgX()));
    actnFormatY = action(tr("Y 轴格式…"), _plot, SLOT(axisFormatDlgY()));
    actnSavePlotFormat = action(tr("保存绘图格式…"), this, SLOT(savePlotFormat()));
    actnLoadPlotFormat = action(tr("加载绘图格式…"), this, SLOT(loadPlotFormat()));
    actnFormatCursor = action(tr("光标线格式…"), this, SLOT(cursorFormatDlg()));
    actnFormatGraphT = action(tr("T 线格式…"), this, SLOT(graphFormatDlgT()));
    actnFormatGraphS = action(tr("S 线格式…"), this, SLOT(graphFormatDlgS()));
    actnFormatGraph = action(tr("线条格式…"), this, SLOT(graphFormatDlg()));

    actnCopyGraphData = action(tr("复制图形数据"), this, SLOT(copyGraphData()), ":/toolbar/copy_table");
    actnCopyGraphDataCurSegment = action(tr("复制图形数据（本段）"), this, SLOT(copyGraphData()), ":/toolbar/copy_table");
    actnCopyGraphDataAllSegments = action(tr("复制图形数据（所有段）"), this, SLOT(copyGraphDataAllSegments()), ":/toolbar/copy_table");
    actnCopyGraphDataWithParams = action(tr("复制图形数据…"), this, SLOT(copyGraphDataWithParams()), ":/toolbar/copy_table");
    actnCopyPlotImage = action(tr("复制绘图图像"), this, SLOT(copyPlotImage()), ":/toolbar/copy_img");
    actnCopyFormatFromSelection = action(tr("复制格式"), this, SLOT(copyFormatFromSelection()), ":/toolbar/copy_fmt");
    actnPasteFormatToSelection = action(tr("粘贴格式"), this, SLOT(pasteFormatToSelection()), ":/toolbar/paste_fmt");
    actnCopyPlotFormat = action(tr("复制绘图格式"), this, SLOT(copyPlotFormat()), ":/toolbar/copy_fmt");
    actnPastePlotFormat = action(tr("粘贴绘图格式"), this, SLOT(pastePlotFormat()), ":/toolbar/paste_fmt");

    actnToggleTitle = action(tr("绘图标题"), this, SLOT(toggleTitle()));
    actnToggleLegend = action(tr("绘图图例"), this, SLOT(toggleLegend()));
    actnToggleTitle->setCheckable(true);
    actnToggleLegend->setCheckable(true);
}

void PlotFuncWindow::createMenuBar()
{
    _unitsMenuX = new UnitsMenu(this);
    _unitsMenuY = new UnitsMenu(this);
    connect(_unitsMenuX, &UnitsMenu::unitChanged, this, &PlotFuncWindow::setUnitX);
    connect(_unitsMenuY, &UnitsMenu::unitChanged, this, &PlotFuncWindow::setUnitY);

    menuPlot = Ori::Gui::menu(tr("绘图", "Menu title"), this, {
        actnUpdate, actnUpdateParams, actnFreeze, nullptr, actnShowFlippedTS, actnShowT, actnShowS, nullptr,
        actnSetTextT, actnSetTextX, actnSetTextY, _unitsMenuX->menu(), _unitsMenuY->menu(), nullptr, actnShowRoundTrip,
    });
    connect(menuPlot, &QMenu::aboutToShow, this, [this](){
        _unitsMenuX->menu()->setTitle("X 轴单位");
        _unitsMenuY->menu()->setTitle("Y 轴单位");
        _unitsMenuX->setUnit(getUnitX());
        _unitsMenuY->setUnit(getUnitY());
    });

    menuLimits = Ori::Gui::menu(tr("范围", "Menu title"), this, {
        actnAutolimits, actnZoomIn, actnZoomOut, nullptr,
        actnSetLimitsX, actnAutolimitsX, actnZoomInX, actnZoomOutX, nullptr,
        actnSetLimitsY, actnAutolimitsY, actnZoomInY, actnZoomOutY
    });

    menuFormat = new QMenu(tr("格式", "Menu title"), this);
}

QList<QMenu*> PlotFuncWindow::menus()
{
    menuFormat->clear();
    menuFormat->addAction(actnFormatTitle);
    menuFormat->addAction(actnFormatLegend);
    menuFormat->addAction(actnFormatX);
    menuFormat->addAction(actnFormatY);
    menuFormat->addAction(actnFormatGraphT);
    menuFormat->addAction(actnFormatGraphS);
    menuFormat->addAction(actnFormatCursor);
    for (auto& item : formatMenuItems())
        item.addTo(menuFormat);
    menuFormat->addSeparator();
    menuFormat->addAction(actnSavePlotFormat);
    menuFormat->addAction(actnLoadPlotFormat);
    return {menuPlot, menuLimits, menuFormat};
}

void PlotFuncWindow::createContextMenus()
{
    auto menuX = new QMenu(this);
    auto titleX = new QWidgetAction(this);
    auto labelX = new QLabel(tr("<b>X 轴</b>"));
    labelX->setMargin(6);
    titleX->setDefaultWidget(labelX);
    menuX->addAction(titleX);
    menuX->addMenu(_unitsMenuX->menu());
    menuX->addAction(tr("范围…"), _plot, &QCPL::Plot::limitsDlgX);
    menuX->addAction(tr("文本…"), _plot, &QCPL::Plot::axisTextDlgX);
    menuX->addAction(tr("格式…"), _plot, &QCPL::Plot::axisFormatDlgX);
    menuX->addAction(QIcon(":/toolbar/limits_auto_x"), tr("适应图形"), _plot, SLOT(autolimitsX()));
    menuX->addSeparator();
    menuX->addAction(QIcon(":/toolbar/copy_fmt"), tr("复制格式"), this, [this](){ QCPL::copyAxisFormat(_plot->xAxis); });
    menuX->addAction(QIcon(":/toolbar/paste_fmt"), tr("粘贴格式"), this, [this](){ pasteAxisFormat(_plot->xAxis); });
    connect(menuX, &QMenu::aboutToShow, this, [this](){
        _unitsMenuX->menu()->setTitle(tr("单位"));
        _unitsMenuX->setUnit(getUnitX());
    });

    auto menuY = new QMenu(this);
    auto titleY = new QWidgetAction(this);
    auto labelY = new QLabel(tr("<b>Y 轴</b>"));
    labelY->setMargin(6);
    titleY->setDefaultWidget(labelY);
    menuY->addAction(titleY);
    menuY->addMenu(_unitsMenuY->menu());
    menuY->addAction(tr("范围…"), _plot, &QCPL::Plot::limitsDlgY);
    menuY->addAction(tr("文本…"), _plot, &QCPL::Plot::axisTextDlgY);
    menuY->addAction(tr("格式…"), _plot, &QCPL::Plot::axisFormatDlgY);
    menuY->addAction(QIcon(":/toolbar/limits_auto_y"), tr("适应图形"), _plot, SLOT(autolimitsY()));
    menuY->addSeparator();
    menuY->addAction(QIcon(":/toolbar/copy_fmt"), tr("复制格式"), this, [this](){ QCPL::copyAxisFormat(_plot->yAxis); });
    menuY->addAction(QIcon(":/toolbar/paste_fmt"), tr("粘贴格式"), this, [this](){ pasteAxisFormat(_plot->yAxis); });
    connect(menuY, &QMenu::aboutToShow, this, [this](){
        _unitsMenuY->menu()->setTitle(tr("单位"));
        _unitsMenuY->setUnit(getUnitY());
    });

    auto menuLegend = new QMenu(this);
    menuLegend->addAction(actnFormatLegend);
    menuLegend->addSeparator();
    menuLegend->addAction(QIcon(":/toolbar/copy_fmt"), tr("复制格式"), this, [this](){ QCPL::copyLegendFormat(_plot->legend); });
    menuLegend->addAction(QIcon(":/toolbar/paste_fmt"), tr("粘贴格式"), this, [this](){ pasteLegendFormat(); });

    auto menuTitle = new QMenu(this);
    menuTitle->addAction(tr("标题文本…"), _plot, &QCPL::Plot::titleTextDlg);
    menuTitle->addAction(actnFormatTitle);
    menuTitle->addSeparator();
    menuTitle->addAction(QIcon(":/toolbar/copy_fmt"), tr("复制标题格式"), this, [this](){ QCPL::copyTitleFormat(_plot->title()); });
    menuTitle->addAction(QIcon(":/toolbar/paste_fmt"), tr("粘贴标题格式"), this, [this](){ pasteTitleFormat(); });

    auto menuGraph = new QMenu(this);
    menuGraph->addAction(actnFormatGraph);
    menuGraph->addAction(actnCopyGraphData);
    menuGraph->addAction(actnCopyGraphDataCurSegment);
    menuGraph->addAction(actnCopyGraphDataAllSegments);
    menuGraph->addAction(actnCopyPlotImage);
    connect(menuGraph, &QMenu::aboutToShow, this, &PlotFuncWindow::graphsMenuAboutToShow);

    auto menuPlot = new QMenu(this);
    menuPlot->addAction(actnCopyPlotImage);
    menuPlot->addSeparator();
    menuPlot->addAction(actnCopyPlotFormat);
    menuPlot->addAction(actnPastePlotFormat);

    _plot->menuAxisX = menuX;
    _plot->menuAxisY = menuY;
    _plot->menuGraph = menuGraph;
    _plot->menuPlot = menuPlot;
    _plot->menuLegend = menuLegend;
    _plot->menuTitle = menuTitle;
}

void PlotFuncWindow::createToolBar()
{
    _buttonFrozenInfo = new FrozenStateButton(tr("冻结信息"), "frozen_info");

    auto t = toolbar();
    t->addAction(actnUpdate);
    t->addAction(actnUpdateParams);
    t->addSeparator();
    t->addAction(actnFreeze);
    actnFrozenInfo = t->addWidget(_buttonFrozenInfo);
    t->addSeparator();
    t->addAction(actnShowFlippedTS);
    t->addAction(actnShowT);
    t->addAction(actnShowS);
    t->addSeparator();
    t->addAction(actnAutolimits);
    t->addAction(actnZoomIn);
    t->addAction(actnZoomOut);
    t->addSeparator();
    t->addAction(actnAutolimitsX);
    t->addAction(actnZoomInX);
    t->addAction(actnZoomOutX);
    t->addSeparator();
    t->addAction(actnAutolimitsY);
    t->addAction(actnZoomInY);
    t->addAction(actnZoomOutY);
}

void PlotFuncWindow::createContent()
{
    _splitter = new QSplitter(Qt::Horizontal);

    PlotParamsPanelCtorOptions opts;
    opts.splitter = _splitter;
    opts.hasInfoPanel = function()->hasSpecPoints();
    opts.hasDataGrid = function()->hasDataTable();
    opts.hasOptionsPanel = function()->hasOptions();
    _leftPanel = new PlotParamsPanel(opts);
    connect(_leftPanel, &PlotParamsPanel::updateSpecPoints, this, &PlotFuncWindow::updateSpecPoints);
    connect(_leftPanel, &PlotParamsPanel::updateDataGrid, this, &PlotFuncWindow::updateDataGrid);
    connect(_leftPanel, &PlotParamsPanel::optionsPanelRequired, this, &PlotFuncWindow::optionsPanelRequired);

    auto toolbar = new Ori::Widgets::FlatToolBar;
    toolbar->setIconSize(QSize(16, 16));
    _leftPanel->placeIn(toolbar);
    toolbar->addSeparator();

    _plot = new QCPL::Plot;
    _plot->legend->setVisible(false);
    _plot->legend->setSelectableParts(QCPLegend::spLegendBox);
    _plot->setAutoAddPlottableToLegend(false);
    connect(_plot, &QCPL::Plot::graphClicked, this, &PlotFuncWindow::graphSelected);
    connect(_plot, &QCPL::Plot::modified, this, [this](auto reason){
        schema()->markModified(reason.toLatin1().data());
        updatePlotItemToggleActions();
    });

    _plot->getAxisUnitString = [this](QCPAxis* axis) {
        if (axis == _plot->xAxis) return getUnitX()->name();
        if (axis == _plot->yAxis) return getUnitY()->name();
        return QString();
    };

    _plot->putTextVar("{func_name}", tr("函数名"), [this]{ return function()->name(); });

    _plot->putTextVarX("{unit}", tr("计量单位"), [this]{ return getUnitX()->name(); });
    _plot->putTextVarX("{(unit)}", tr("计量单位（括号内）"), [this]{
        auto unit = getUnitX(); return unit == Z::Units::none() ? QString() : QStringLiteral("(%1)").arg(unit->name()); });

    _plot->putTextVarY("{unit}", tr("计量单位"), [this]{ return getUnitY()->name(); });
    _plot->putTextVarY("{(unit)}", tr("计量单位（括号内）"), [this]{
        auto unit = getUnitY(); return unit == Z::Units::none() ? QString() : QStringLiteral("(%1)").arg(unit->name()); });

    _plot->setDefaultTextT(QStringLiteral("{func_name}"));
    _plot->setFormatterTextT(_plot->defaultTextT());

    _cursor = new QCPL::Cursor(_plot);
    _cursor->setPen(AppSettings::instance().pen(AppSettings::PenCursor));
    connect(_cursor, &QCPL::Cursor::positionChanged, this, &PlotFuncWindow::updateCursorInfo);
    auto axesLayer = _plot->layer("axes");
    if (axesLayer) _cursor->setLayer(axesLayer);

    auto actnShowCursorHelp = Ori::Gui::action(tr("帮助"), this, []{
        Z::HelpSystem::instance()->showTopic("plot_cursor.html");
    }, ":/toolbar/help");

    _cursorMenu = new QMenu(tr("光标"), this);
    _cursorPanel = new QCPL::CursorPanel(_cursor);
    _cursorPanel->setAutoUpdateInfo(false);
    _cursorPanel->setNumberPrecision(AppSettings::instance().numberPrecisionData, false);
    _cursorPanel->placeIn(toolbar, { actnShowCursorHelp });
    _cursorPanel->fillMenu(_cursorMenu);

    _splitter->addWidget(_leftPanel);
    _splitter->addWidget(_plot);
    _splitter->setChildrenCollapsible(false);

    setContent(toolbar);
    setContent(_splitter);

    _graphs = new FunctionGraphSet(_plot, [this]{ return GraphUnits {getUnitX(), getUnitY()}; });
    _graphs->T()->setPen(AppSettings::instance().pen(AppSettings::PenGraphT));
    _graphs->S()->setPen(AppSettings::instance().pen(AppSettings::PenGraphS));
}

void PlotFuncWindow::createStatusBar()
{
    _statusBar = new Ori::Widgets::StatusBar(STATUS_PANELS_COUNT);
    _statusBar->connect(STATUS_UNIT_X, &QWidget::customContextMenuRequested, [this](const QPoint& p){
        _unitsMenuX->setUnit(getUnitX());
        _unitsMenuX->menu()->popup(_statusBar->mapToGlobal(STATUS_UNIT_X, p));
    });
    _statusBar->connect(STATUS_UNIT_Y, &QWidget::customContextMenuRequested, [this](const QPoint& p){
        _unitsMenuY->setUnit(getUnitY());
        _unitsMenuY->menu()->popup(_statusBar->mapToGlobal(STATUS_UNIT_Y, p));
    });
    setContent(_statusBar);
}

QList<BasicMdiChild::MenuItem> PlotFuncWindow::menuItems_View()
{
    QList<BasicMdiChild::MenuItem> menuItems;
    if (auto actions = _leftPanel->panelToogleActions(); !actions.isEmpty())
    {
        foreach (auto a, actions)
            menuItems << a;
        menuItems << BasicMdiChild::MenuItem();
    }
    return menuItems
            << _cursorMenu
            << actnToggleTitle
            << actnToggleLegend
            << viewMenuItems();
}

QList<BasicMdiChild::MenuItem> PlotFuncWindow::menuItems_Edit()
{
    return editMenuItems()
            << actnCopyGraphDataWithParams
            << actnCopyPlotImage
            << BasicMdiChild::MenuItem()
            // << actnCopyFormatFromSelection
            // << actnPasteFormatToSelection
            // TODO: "Copy/Paste plot format" should be just modes of
            // "Copy/Paste selected format" when nothing is selected
            << actnCopyPlotFormat
            << actnPastePlotFormat;
}

QCPL::Graph* PlotFuncWindow::selectedGraph() const
{
    auto graphs = _plot->selectedGraphs();
    return graphs.isEmpty()? nullptr: graphs.first();
}

void PlotFuncWindow::activateModeT()
{
    if (_exclusiveModeTS)
        actnShowS->setChecked(!actnShowT->isChecked());
    else if (!actnShowT->isChecked() && !actnShowS->isChecked())
        actnShowS->setChecked(true);

    updateModeTS();
}

void PlotFuncWindow::activateModeS()
{
    if (_exclusiveModeTS)
        actnShowT->setChecked(!actnShowS->isChecked());
    else if (!actnShowS->isChecked() && !actnShowT->isChecked())
        actnShowT->setChecked(true);

    updateModeTS();
}

void PlotFuncWindow::activateModeFlippedTS()
{
    updateModeTS();
}

void PlotFuncWindow::updateModeTS()
{
    showModeTS();

    if (_recalcWhenChangeModeTS)
    {
        update();
    }
    else
    {
        updateGraphs();
        afterUpdate();
        _plot->replot();
    }

    schema()->markModified("PlotFuncWindow::updateModeTS");
}

void PlotFuncWindow::showModeTS()
{
    bool flipped = actnShowFlippedTS->isChecked();
    _graphs->T()->setVisible(flipped || actnShowT->isChecked());
    _graphs->S()->setVisible(flipped || actnShowS->isChecked());
    _graphs->S()->setFlipped(flipped);

    actnShowT->setEnabled(!flipped);
    actnShowT->setVisible(!flipped);
    actnShowS->setEnabled(!flipped);
    actnShowS->setVisible(!flipped);
}

void PlotFuncWindow::updateSpecPoints()
{
    if (_frozen)
    {
        _needRecalc = true;
        return;
    }
    if (_leftPanel->infoPanel() && _leftPanel->infoPanel()->isVisible())
    {
        prepareSpecPoints();
        _leftPanel->infoPanel()->setHtml(_function->calculateSpecPoints(getSpecPointsParams()));
    }
}

void PlotFuncWindow::updateStatusUnits()
{
    auto unitX = getUnitX();
    auto unitY = getUnitY();
    _statusBar->setText(STATUS_UNIT_X, QStringLiteral("X: ") + (
        unitX == Z::Units::none() ? QStringLiteral("n/a") : unitX->name()));
    _statusBar->setText(STATUS_UNIT_Y, QStringLiteral("Y: ") + (
        unitY == Z::Units::none() ? QStringLiteral("n/a") : unitY->name()));
}

void PlotFuncWindow::updateDataGrid()
{
    if (_leftPanel->dataGrid() && _leftPanel->dataGrid()->isVisible())
    {
        auto graph = selectedGraph();
        if (graph)
            _leftPanel->dataGrid()->setData(graph);
    }
}

void PlotFuncWindow::updateCursorInfo()
{
    if (_frozen)
    {
        _cursorPanel->update();
        // TODO:NEXT-VER calculate by interpolating between existing graph points
        return;
    }

    auto unitX = getUnitX();
    auto unitY = getUnitY();
    CursorInfoValues values;
    auto p = _cursor->position();
    values << CursorInfoValue(CursorInfoValue::VALUE_X, unitX->toSi(p.x()));
    values << CursorInfoValue(CursorInfoValue::VALUE_Y, unitY->toSi(p.y()));
    getCursorInfo({Z::Value(p.x(), unitX), Z::Value(p.y(), unitY)}, values);
    QString str;
    QTextStream info(&str);
    for (int i = 0; i < values.size(); i++)
    {
        const CursorInfoValue& v = values.at(i);
        if (v.kind == CursorInfoValue::VALUE_X)
            info << _cursorPanel->formatLinkX(Z::format(p.x()));
        else if (v.kind == CursorInfoValue::VALUE_Y)
            info << _cursorPanel->formatLinkY(Z::format(p.y()));
        else if (v.kind == CursorInfoValue::SECTION)
            info << "<b>" << v.name << ":</b> ";
        else if (v.kind == CursorInfoValue::RAW)
            info << v.name << " = " << Z::format(v.value);
        else
            info << v.name << " = " << Z::format(unitY->fromSi(v.value));
        if (!v.note.isEmpty())
            info << ' ' << v.note;
        if (v.kind != CursorInfoValue::SECTION && i < values.size()-1)
            info << "; ";
    }
    _cursorPanel->setText(str);
}

void PlotFuncWindow::updateWithParams()
{
    if (configure()) update();
}

void PlotFuncWindow::update()
{
    beforeUpdate();
    
    if (_frozen)
    {
        _needRecalc = true;
        return;
    }

    calculate();

    if (_autolimitsRequest)
    {
        _autolimitsRequest = false;
        _plot->autolimits(false);
    }

    if (_centerCursorRequested)
    {
        _centerCursorRequested = false;
        _cursor->moveToCenter();
        // Cursor info will be updated by positionChanged signal
    }
    else updateCursorInfo();

    _plot->updateTexts();
    updateStatusUnits();
    updateSpecPoints();
    updateDataGrid();
    afterUpdate();

    _plot->replot();
}

void PlotFuncWindow::calculate()
{
    _function->calculate();
    if (!_function->ok())
    {
        showStatusError(_function->errorText());
        _graphs->clear();
    }
    else
    {
        clearStatusInfo();
        updateGraphs();
    }
}

void PlotFuncWindow::showStatusError(const QString& message)
{
    _statusBar->setText(STATUS_INFO, message);
    _statusBar->highlightError(STATUS_INFO);
}

void PlotFuncWindow::clearStatusInfo()
{
    _statusBar->clear(STATUS_INFO);
}

void PlotFuncWindow::updateGraphs()
{
    _graphs->update(_function);
}

void PlotFuncWindow::graphSelected(QCPGraph *graph)
{
    updateDataGrid();
    if (_selectGraphOptions.testFlag(SG_UPDATE_CUSROR))
        updateCursorInfo();
    if (_selectGraphOptions.testFlag(SG_UPDATE_SPEC_POINTS))
        updateSpecPoints();

    if (graph)
        _statusBar->setText(STATUS_POINTS, tr("点数：%1").arg(graph->data()->size()));
    else
        _statusBar->clear(STATUS_POINTS);
}

void PlotFuncWindow::showRoundTrip()
{
    InfoFuncWindow::open(new PlotFuncRoundTripFunction(windowTitle(), _function), this);
}

void PlotFuncWindow::freeze(bool frozen)
{
    _frozen = frozen;
    actnUpdate->setEnabled(!_frozen);
    actnUpdateParams->setEnabled(!_frozen);
    actnFrozenInfo->setVisible(_frozen);
    if (_frozen)
    {
        InfoFuncSummary summary(schema());
        summary.calculate();
        _buttonFrozenInfo->setInfo(summary.result());
    }
    _leftPanel->setOptionsPanelEnabled(!_frozen);
    if (!_frozen && _needRecalc)
        update();
}

QWidget* PlotFuncWindow::optionsPanelRequired()
{
    auto panel = makeOptionsPanel();
    if (!panel)
        qCritical() << "Function" << function()->alias() << "declared with "
            "hasOptions=true but its window does not provide options panel";
    return panel;
}

bool PlotFuncWindow::configure()
{
    bool ok = configureInternal();
    if (ok)
        schema()->events().raise(SchemaEvents::Changed, "PlotFuncWindow: configure");
    return ok;
}

void PlotFuncWindow::storeViewParts(ViewSettings& vs, ViewParts parts)
{
    if (parts.testFlag(VP_LIMITS_Y))
    {
        auto limits = _plot->limitsY();
        vs["y_min"] = limits.min;
        vs["y_max"] = limits.max;
    }
    if (parts.testFlag(VP_TITLE_Y))
    {
        vs["y_title"] = _plot->formatterTextY();
    }
    if (parts.testFlag(VP_UNIT_Y))
    {
        vs["y_unit"] = getUnitY()->alias();
    }
    if (parts.testFlag(VP_CUSRSOR_POS))
    {
        auto pos = _cursor->position();
        vs["cursor_x"] = pos.x();
        vs["cursor_y"] = pos.y();
    }
}

void PlotFuncWindow::restoreViewParts(const ViewSettings &vs, ViewParts parts)
{
    if (parts.testFlag(VP_LIMITS_Y))
    {
        bool minOk, maxOk;
        double min = vs["y_min"].toDouble(&minOk);
        double max = vs["y_max"].toDouble(&maxOk);
        if (minOk && maxOk)
            _plot->setLimitsY(min, max, false);
        else _autolimitsRequest = true;
    }
    if (parts.testFlag(VP_TITLE_Y))
    {
        if (vs.contains("y_title"))
            _plot->setFormatterTextY(vs["y_title"].toString());
        else _plot->setFormatterTextY(_plot->defaultTextY());
    }
    if (parts.testFlag(VP_UNIT_Y))
    {
        auto unit = Z::Units::findByAlias(vs["y_unit"].toString());
        _unitY = unit ? unit : getDefaultUnitY();
    }
    if (parts.testFlag(VP_CUSRSOR_POS))
    {
        bool xOk, yOk;
        double x = vs["cursor_x"].toDouble(&xOk);
        double y = vs["cursor_y"].toDouble(&yOk);
        if (xOk && yOk)
            _cursor->setPosition(x, y, false);
        else _centerCursorRequested = true;
    }
}

ElemDeletionReaction PlotFuncWindow::reactElemDeletion(const Elements& elems)
{
    return function()->dependsOn().check(elems)
        ? ElemDeletionReaction::Close
        : ElemDeletionReaction::None;
}

void PlotFuncWindow::elementDeleting(Schema*, Element* elem)
{
    // TODO:NEXT-VER: see InfoFuncWindow::elementDeleting() and implement similar behaviour.
    // Current behaviour is ok for now as full FunctionBase::Dead processing
    // requires an ability of saving of frozen data.
    if (function()->dependsOn().check(elem))
        disableAndClose();
}

void PlotFuncWindow::globalParamDeleting(Schema*, Z::Parameter *param)
{
    if (function()->dependsOn().check(param))
        disableAndClose();
}

void PlotFuncWindow::elemParamDeleting(Z::Parameter *param)
{
    if (function()->dependsOn().check(param))
        disableAndClose();
}

void PlotFuncWindow::disableAndClose()
{
    _frozen = true; // disable updates
    QTimer::singleShot(0, this, [this]{close();});
}

Z::Unit PlotFuncWindow::getUnitX() const
{
    auto defUnit = getDefaultUnitX();
    auto thisDim = Z::Units::guessDim(_unitX);
    auto funcDim = Z::Units::guessDim(defUnit);
    return thisDim == funcDim ? _unitX : defUnit;
}

Z::Unit PlotFuncWindow::getUnitY() const
{
    auto defUnit = getDefaultUnitY();
    auto thisDim = Z::Units::guessDim(_unitY);
    auto funcDim = Z::Units::guessDim(defUnit);
    return thisDim == funcDim ? _unitY : defUnit;
}

Z::Unit PlotFuncWindow::getUnitY(FuncMode mode) const
{
    if (_storedView.contains(mode))
    {
        const ViewSettings& vs = _storedView[mode];
        auto unit = Z::Units::findByAlias(vs["y_unit"].toString());
        return unit ? unit : getDefaultUnitY(mode);
    }
    return getDefaultUnitY(mode);
}

void PlotFuncWindow::setUnitX(Z::Unit unit)
{
    auto oldUnit = getUnitX();
    if (oldUnit == unit) return;
    _unitX = unit;
    _plot->updateTextX();
    updateStatusUnits();
    schema()->markModified("PlotFuncWindow::setUnitX");
    PlotHelpers::rescaleLimits(_plot, PlotAxis::X, oldUnit, unit);
    PlotHelpers::rescaleCursor(_cursor, PlotAxis::X, oldUnit, unit);
    update();
}

void PlotFuncWindow::setUnitY(Z::Unit unit)
{
    auto oldUnit = getUnitY();
    if (oldUnit == unit) return;
    _unitY = unit;
    _plot->updateTextY();
    updateStatusUnits();
    schema()->markModified("PlotFuncWindow::setUnitY");
    PlotHelpers::rescaleLimits(_plot, PlotAxis::Y, oldUnit, unit);
    PlotHelpers::rescaleCursor(_cursor, PlotAxis::Y, oldUnit, unit);
    update();
}

void PlotFuncWindow::optionChanged(AppSettingsOption option)
{
    if (option == AppSettingsOption::NumberPrecisionData)
    {
        _cursorPanel->setNumberPrecision(AppSettings::instance().numberPrecisionData, false);
        updateCursorInfo();
        updateSpecPoints();
    }
    else if (option == AppSettingsOption::DefaultPenFormat)
    {
        _graphs->T()->setPen(graphPenT());
        _graphs->S()->setPen(graphPenS());
        _cursor->setPen(cursorPen());
        _plot->replot();
    }
}

void PlotFuncWindow::copyGraphData()
{
    PlotHelpers::toClipboard(_plot->selectedGraph());
}

void PlotFuncWindow::copyGraphDataAllSegments()
{
    auto ts = _graphs->findBy(_plot->selectedGraph());
    if (ts) PlotHelpers::toClipboard(ts->segments());
}

void PlotFuncWindow::copyPlotImage()
{
    bool oldVisible = _cursor->visible();
    if (AppSettings::instance().exportHideCursor)
        _cursor->setVisible(false);

    QImage image(_plot->width(), _plot->height(), QImage::Format_RGB32);
    QCPPainter painter(&image);
    _plot->toPainter(&painter);
    emit finishImageBeforeCopy(&painter);
    qApp->clipboard()->setImage(image);

    if (oldVisible != _cursor->visible())
        _cursor->setVisible(oldVisible);
}

void PlotFuncWindow::copyGraphDataWithParams()
{
    PlotHelpers::exportGraphsData(_graphs, _plot->selectedGraph());
}

void PlotFuncWindow::graphsMenuAboutToShow()
{
    auto ts = _graphs->findBy(_plot->selectedGraph());
    bool manySegments = ts && ts->segmentsCount() > 1;
    actnCopyGraphData->setVisible(!manySegments);
    actnCopyGraphDataCurSegment->setVisible(manySegments);
    actnCopyGraphDataAllSegments->setVisible(manySegments);
}

void PlotFuncWindow::legendFormatDlg()
{
    QCPL::LegendFormatDlgProps props;
    props.title = tr("图例格式");
    props.sampleText = tr("• T 线\n• S 线");
    if (QCPL::legendFormatDlg(_plot->legend, props))
    {
        schema()->markModified("PlotFuncWindow::formatLegend");
        updatePlotItemToggleActions();
    }
}

void PlotFuncWindow::copyPlotFormat()
{
    QCPL::copyPlotFormat(_plot);
}

void PlotFuncWindow::pastePlotFormat()
{
    auto err = QCPL::pastePlotFormat(_plot);
    if (err.isEmpty())
    {
        _plot->updateTitleVisibility();
        _plot->replot();
        schema()->markModified("PlotFuncWindow::pastePlotFormat");
        updatePlotItemToggleActions();
    }
    else Ori::Dlg::info(err);
}

void PlotFuncWindow::pasteLegendFormat()
{
    auto err = QCPL::pasteLegendFormat(_plot->legend);
    if (err.isEmpty())
    {
        _plot->replot();
        schema()->markModified("PlotFuncWindow::pasteLegendFormat");
    }
    else Ori::Dlg::info(err);
}

void PlotFuncWindow::pasteTitleFormat()
{
    auto err = QCPL::pasteTitleFormat(_plot->title());
    if (err.isEmpty())
    {
        _plot->replot();
        schema()->markModified("PlotFuncWindow::pasteTitleFormat");
    }
    else Ori::Dlg::info(err);
}

void PlotFuncWindow::pasteAxisFormat(QCPAxis *axis)
{
    auto err = QCPL::pasteAxisFormat(axis);
    if (err.isEmpty())
    {
        _plot->replot();
        schema()->markModified("PlotFuncWindow::pasteAxisFormat");
    }
    else Ori::Dlg::info(err);
}

void PlotFuncWindow::toggleTitle()
{
    _plot->title()->setVisible(!_plot->title()->visible());
    _plot->updateTitleVisibility();
    _plot->replot();
    schema()->markModified("PlotFuncWindow::toggleTitle");
    updatePlotItemToggleActions();
}

void PlotFuncWindow::toggleLegend()
{
    _plot->legend->setVisible(!_plot->legend->visible());
    _plot->replot();
    schema()->markModified("PlotFuncWindow::toggleLegend");
    updatePlotItemToggleActions();
}

void PlotFuncWindow::updatePlotItemToggleActions()
{
    actnToggleTitle->setChecked(_plot->title()->visible());
    actnToggleLegend->setChecked(_plot->legend->visible());
}

void PlotFuncWindow::copyFormatFromSelection()
{
    qDebug() << "TODO: PlotFuncWindow::copyFormatFromSelection()";
}

void PlotFuncWindow::pasteFormatToSelection()
{
    qDebug() << "TODO: PlotFuncWindow::pasteFormatToSelection()";
}

void PlotFuncWindow::savePlotFormat()
{
    QString recentPath = RecentData::getDir("plot_format_path");
    auto fileName = QFileDialog::getSaveFileName(
        this, tr("保存绘图格式"), recentPath, tr("JSON 文件 (*.json)\n所有文件 (*.*)"));
    if (fileName.isEmpty())
        return;
    RecentData::setDir("plot_format_path", fileName);
    QString err = QCPL::saveFormatToFile(fileName, _plot);
    if (!err.isEmpty())
        Ori::Dlg::error(err);
}

void PlotFuncWindow::loadPlotFormat()
{
    QString recentPath = RecentData::getDir("plot_format_path");
    auto fileName = QFileDialog::getOpenFileName(
        this, tr("加载绘图格式"), recentPath, tr("JSON 文件 (*.json)\n所有文件 (*.*)"));
    if (fileName.isEmpty())
        return;
    RecentData::setDir("plot_format_path", fileName);
    QCPL::JsonReport report;
    auto err = QCPL::loadFormatFromFile(fileName, _plot, &report);
    if (!err.isEmpty())
    {
        Ori::Dlg::error(err);
        return;
    }
    _plot->replot();
    if (!report.isEmpty() && Z::Protocol::isEnabled)
    {
        foreach (auto err, report)
            Z::Protocol(Z::Protocol::Warning) << err.message;
    }
}

QPen PlotFuncWindow::cursorPen() const
{
    return _cursorPen ? *_cursorPen : AppSettings::instance().pen(AppSettings::PenCursor);
}

QPen PlotFuncWindow::graphPenT() const
{
    return _graphPenT ? *_graphPenT : AppSettings::instance().pen(AppSettings::PenGraphT);
}

QPen PlotFuncWindow::graphPenS() const
{
    return _graphPenS ? *_graphPenS : AppSettings::instance().pen(AppSettings::PenGraphS);
}

void PlotFuncWindow::cursorFormatDlg()
{
    PlotHelpers::FormatPenDlgProps props;
    props.title = tr("光标线格式");
    props.onApply = [this](const QPen& pen){
        _cursorPen = pen;
        _cursor->setPen(pen);
        _plot->replot();
    };
    props.onReset = [this](){
        _cursorPen.reset();
        _cursor->setPen(cursorPen());
        _plot->replot();
    };
    if (PlotHelpers::formatPenDlg(cursorPen(), props))
        schema()->markModified("PlotFuncWindow::cursorFormatDlg");
}

void PlotFuncWindow::graphFormatDlgT()
{
    PlotHelpers::FormatPenDlgProps props;
    props.title = tr("T 线格式");
    props.onApply = [this](const QPen& pen){
        _graphPenT = pen;
        _graphs->T()->setPen(pen);
        _plot->replot();
    };
    props.onReset = [this](){
        _graphPenT.reset();
        _graphs->T()->setPen(graphPenT());
        _plot->replot();
    };
    if (PlotHelpers::formatPenDlg(graphPenT(), props))
        schema()->markModified("PlotFuncWindow::graphFormatDlgT");
}

void PlotFuncWindow::graphFormatDlgS()
{
    PlotHelpers::FormatPenDlgProps props;
    props.title = tr("S 线格式");
    props.onApply = [this](const QPen& pen){
        _graphPenS = pen;
        _graphs->S()->setPen(pen);
        _plot->replot();
    };
    props.onReset = [this](){
        _graphPenS.reset();
        _graphs->S()->setPen(graphPenS());
        _plot->replot();
    };
    if (PlotHelpers::formatPenDlg(graphPenS(), props))
        schema()->markModified("PlotFuncWindow::graphFormatDlgT");
}

void PlotFuncWindow::graphFormatDlg()
{
    auto g = _plot->selectedGraph();
    if (_graphs->T()->contains(g))
        graphFormatDlgT();
    else if (_graphs->S()->contains(g))
        graphFormatDlgS();
    else if (auto graph = _graphs->findBy(g); graph)
        formatMultiGraph(graph);
}
