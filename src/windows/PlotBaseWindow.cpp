#include "PlotBaseWindow.h"

#include "../app/HelpSystem.h"
#include "../app/PersistentState.h"
#include "../core/Protocol.h"
#include "../widgets/PlotHelpers.h"
#include "../widgets/PlotParamsPanel.h"

#include "helpers/OriDialogs.h"
#include "helpers/OriWidgets.h"
#include "widgets/OriFlatToolBar.h"
#include "widgets/OriStatusBar.h"

#include "qcpl_cursor.h"
#include "qcpl_cursor_panel.h"
#include "qcpl_graph_grid.h"
#include "qcpl_io_json.h"
#include "qcpl_plot.h"

#define A_ Ori::Gui::V0::action

PlotBaseWindow::PlotBaseWindow(Schema* schema, const PlotWindowConfig &config): SchemaMdiChild(schema), _config(config)
{
    createContent();
    createActions();
    createMenuBar();
    createToolBar();
    createStatusBar();
    createContextMenus();

    updatePlotItemToggleActions();
}

void PlotBaseWindow::createActions()
{
    actnAutolimits = A_(tr("适应图形"), _plot, SLOT(autolimits()), ":/toolbar/limits_auto");
    actnAutolimitsX = A_(tr("按 X 轴适应图形"), _plot, SLOT(autolimitsX()), ":/toolbar/limits_auto_x");
    actnAutolimitsY = A_(tr("按 Y 轴适应图形"), _plot, SLOT(autolimitsY()), ":/toolbar/limits_auto_y");

    actnZoomIn = A_(tr("放大"), _plot, SLOT(zoomIn()), ":/toolbar/limits_zoom_in");
    actnZoomOut = A_(tr("缩小"), _plot, SLOT(zoomOut()), ":/toolbar/limits_zoom_out");
    actnZoomInX = A_(tr("沿 X 轴放大"), _plot, SLOT(zoomInX()), ":/toolbar/limits_zoom_in_x");
    actnZoomOutX = A_(tr("沿 X 轴缩小"), _plot, SLOT(zoomOutX()), ":/toolbar/limits_zoom_out_x");
    actnZoomInY = A_(tr("沿 Y 轴放大"), _plot, SLOT(zoomInY()), ":/toolbar/limits_zoom_in_y");
    actnZoomOutY = A_(tr("沿 Y 轴缩小"), _plot, SLOT(zoomOutY()), ":/toolbar/limits_zoom_out_y");

    actnSetLimitsX = A_(tr("X 轴范围…"), _plot, SLOT(limitsDlgX()));
    actnSetLimitsY = A_(tr("Y 轴范围…"), _plot, SLOT(limitsDlgY()));
    actnSetTextX = A_(tr("X 轴文本…"), _plot, SLOT(axisTextDlgX()));
    actnSetTextY = A_(tr("Y 轴文本…"), _plot, SLOT(axisTextDlgY()));
    actnSetTextT = A_(tr("标题文本…"), _plot, SLOT(titleTextDlg()));
    
    // These actions also used in context menus, so we add the "Format" word for clearity
    // even though it's not necessary for subcommands of the "Format" menu
    actnFormatTitle = A_(tr("标题格式…"), _plot, SLOT(titleFormatDlg()));
    actnFormatLegend = A_(tr("图例格式…"), _plot, SLOT(legendFormatDlg()));
    actnFormatX = A_(tr("X 轴格式…"), _plot, SLOT(axisFormatDlgX()));
    actnFormatY = A_(tr("Y 轴格式…"), _plot, SLOT(axisFormatDlgY()));
    actnFormatCursor = A_(tr("光标线格式…"), this, SLOT(cursorFormatDlg()));
    actnFormatGraph = A_(tr("线条格式…"), this, SLOT(graphFormatDlg()));
    actnSavePlotFormat = A_(tr("保存绘图格式…"), this, SLOT(savePlotFormat()));
    actnLoadPlotFormat = A_(tr("加载绘图格式…"), this, SLOT(loadPlotFormat()));
    
    actnCopyGraphData = A_(tr("复制图形数据"), this, SLOT(copyGraphData()), ":/toolbar/copy_table");
    actnCopyGraphDataCurSegment = A_(tr("复制图形数据（本段）"), this, SLOT(copyGraphData()), ":/toolbar/copy_table");
    actnCopyGraphDataAllSegments = A_(tr("复制图形数据（所有段）"), this, SLOT(copyGraphDataAllSegments()), ":/toolbar/copy_table");
    actnCopyGraphDataWithParams = A_(tr("复制图形数据…"), this, SLOT(copyGraphDataWithParams()), ":/toolbar/copy_table");
    actnCopyPlotImage = A_(tr("复制绘图图像"), this, SLOT(copyPlotImage()), ":/toolbar/copy_img");
    actnCopyPlotFormat = A_(tr("复制绘图格式"), this, SLOT(copyPlotFormat()), ":/toolbar/copy_fmt");
    actnPastePlotFormat = A_(tr("粘贴绘图格式"), this, SLOT(pastePlotFormat()), ":/toolbar/paste_fmt");
    
    actnToggleTitle = A_(tr("绘图标题"), this, SLOT(toggleTitle()));
    actnToggleLegend = A_(tr("绘图图例"), this, SLOT(toggleLegend()));
    actnToggleTitle->setCheckable(true);
    actnToggleLegend->setCheckable(true);
}

void PlotBaseWindow::createMenuBar()
{
    menuPlot = Ori::Gui::menu(tr("绘图", "Menu title"), this, {
        actnSetTextT, actnSetTextX, actnSetTextY, nullptr,
    });

    menuLimits = Ori::Gui::menu(tr("范围", "Menu title"), this, {
        actnAutolimits, actnZoomIn, actnZoomOut, nullptr,
        actnSetLimitsX, actnAutolimitsX, actnZoomInX, actnZoomOutX, nullptr,
        actnSetLimitsY, actnAutolimitsY, actnZoomInY, actnZoomOutY, nullptr,
    });

    menuFormat = new QMenu(tr("格式", "Menu title"), this);
}

void PlotBaseWindow::createToolBar()
{
    auto t = toolbar();
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

void PlotBaseWindow::createContextMenus()
{
    auto menuX = new QMenu(this);
    auto titleX = new QWidgetAction(this);
    auto labelX = new QLabel(tr("<b>X 轴</b>"));
    labelX->setMargin(6);
    titleX->setDefaultWidget(labelX);
    menuX->addAction(titleX);
    _contextMenuBeginX =
    menuX->addAction(tr("范围…"), _plot, &QCPL::Plot::limitsDlgX);
    menuX->addAction(tr("文本…"), _plot, &QCPL::Plot::axisTextDlgX);
    menuX->addAction(tr("格式…"), _plot, &QCPL::Plot::axisFormatDlgX);
    menuX->addAction(QIcon(":/toolbar/limits_auto_x"), tr("适应图形"), _plot, SLOT(autolimitsX()));
    menuX->addSeparator();
    menuX->addAction(QIcon(":/toolbar/copy_fmt"), tr("复制格式"), this, [this](){ QCPL::copyAxisFormat(_plot->xAxis); });
    menuX->addAction(QIcon(":/toolbar/paste_fmt"), tr("粘贴格式"), this, [this](){ pasteAxisFormat(_plot->xAxis); });

    auto menuY = new QMenu(this);
    auto titleY = new QWidgetAction(this);
    auto labelY = new QLabel(tr("<b>Y 轴</b>"));
    labelY->setMargin(6);
    titleY->setDefaultWidget(labelY);
    menuY->addAction(titleY);
    _contextMenuBeginY =
    menuY->addAction(tr("范围…"), _plot, &QCPL::Plot::limitsDlgY);
    menuY->addAction(tr("文本…"), _plot, &QCPL::Plot::axisTextDlgY);
    menuY->addAction(tr("格式…"), _plot, &QCPL::Plot::axisFormatDlgY);
    menuY->addAction(QIcon(":/toolbar/limits_auto_y"), tr("适应图形"), _plot, SLOT(autolimitsY()));
    menuY->addSeparator();
    menuY->addAction(QIcon(":/toolbar/copy_fmt"), tr("复制格式"), this, [this](){ QCPL::copyAxisFormat(_plot->yAxis); });
    menuY->addAction(QIcon(":/toolbar/paste_fmt"), tr("粘贴格式"), this, [this](){ pasteAxisFormat(_plot->yAxis); });

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
    menuGraph->addSeparator();
    menuGraph->addAction(actnCopyGraphData);
    menuGraph->addAction(actnCopyGraphDataCurSegment);
    menuGraph->addAction(actnCopyGraphDataAllSegments);
    menuGraph->addSeparator();
    menuGraph->addAction(actnCopyPlotImage);
    connect(menuGraph, &QMenu::aboutToShow, this, &PlotBaseWindow::graphsMenuAboutToShow);

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

void PlotBaseWindow::createStatusBar()
{
    _statusBar = new Ori::Widgets::StatusBar(_config.statusPanelCount);
    setContent(_statusBar);
}

void PlotBaseWindow::createContent()
{
    _splitter = new QSplitter(Qt::Horizontal);

    PlotParamsPanelCtorOptions opts;
    opts.splitter = _splitter;
    opts.hasInfoPanel = _config.leftPanelHasSpecPoints;
    opts.hasDataGrid = _config.leftPanelHasDataTable;
    opts.hasOptionsPanel = _config.leftPanelHasOptions;
    _leftPanel = new PlotParamsPanel(opts);
    connect(_leftPanel, &PlotParamsPanel::updateDataGrid, this, &PlotBaseWindow::updateDataGrid);

    auto toolbar = new Ori::Widgets::FlatToolBar;
    toolbar->setIconSize(QSize(16, 16));
    _leftPanel->placeIn(toolbar);
    toolbar->addSeparator();

    _plot = new QCPL::Plot;
    _plot->legend->setVisible(false);
    _plot->legend->setSelectableParts(QCPLegend::spLegendBox);
    _plot->setAutoAddPlottableToLegend(false);
    connect(_plot, &QCPL::Plot::graphClicked, this, &PlotBaseWindow::graphSelected);
    connect(_plot, &QCPL::Plot::modified, this, [this](auto reason){
        schema()->markModified(reason.toLatin1().data());
        updatePlotItemToggleActions();
    });
    
    _cursor = new QCPL::Cursor(_plot);
    _cursor->setPen(AppSettings::instance().pen(AppSettings::PenCursor));
    connect(_cursor, &QCPL::Cursor::positionChanged, this, &PlotBaseWindow::updateCursorInfo);
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
}

QList<QMenu*> PlotBaseWindow::menus()
{
    menuFormat->clear();
    menuFormat->addAction(actnFormatTitle);
    menuFormat->addAction(actnFormatLegend);
    menuFormat->addAction(actnFormatX);
    menuFormat->addAction(actnFormatY);
    menuFormat->addAction(actnFormatCursor);
    for (auto& item : formatMenuItems())
        item.addTo(menuFormat);
    menuFormat->addSeparator();
    menuFormat->addAction(actnSavePlotFormat);
    menuFormat->addAction(actnLoadPlotFormat);
    return {menuPlot, menuLimits, menuFormat};
}

QList<BasicMdiChild::MenuItem> PlotBaseWindow::menuItems_View()
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

QList<BasicMdiChild::MenuItem> PlotBaseWindow::menuItems_Edit()
{
    return editMenuItems()
            // TODO: << actnCopyGraphDataWithParams
            << actnCopyPlotImage
            << BasicMdiChild::MenuItem()
            // TODO: "Copy/Paste Format" should operate in selected part
            // and do copy/paste the full plot format when nothing is selected
            << actnCopyPlotFormat
            << actnPastePlotFormat;
}

void PlotBaseWindow::optionChanged(AppSettingsOption option)
{
    if (option == AppSettingsOption::NumberPrecisionData)
    {
        _cursorPanel->setNumberPrecision(AppSettings::instance().numberPrecisionData, false);
        updateCursorInfo();
    }
    else if (option == AppSettingsOption::DefaultPenFormat)
    {
        _cursor->setPen(cursorPen());
        _plot->replot();
    }
}

QPen PlotBaseWindow::cursorPen() const
{
    return _cursorPen ? *_cursorPen : AppSettings::instance().pen(AppSettings::PenCursor);
}

QCPGraph* PlotBaseWindow::selectedGraph() const
{
    auto graphs = _plot->selectedGraphs();
    return graphs.isEmpty()? nullptr: graphs.first();
}

void PlotBaseWindow::graphSelected(QCPGraph *graph)
{
    updateDataGrid();
    if (_config.selectedGraphUpdatesCursor)
        updateCursorInfo();

    if (_config.statusPanelPoints >= 0)
    {
        if (graph)
            _statusBar->setText(_config.statusPanelPoints, tr("点数：%1").arg(graph->data()->size()));
        else
            _statusBar->clear(_config.statusPanelPoints);
    }
}

void PlotBaseWindow::updateDataGrid()
{
    if (_leftPanel->dataGrid() && _leftPanel->dataGrid()->isVisible())
        if (auto graph = selectedGraph(); graph)
            _leftPanel->dataGrid()->setData(graph);
}

void PlotBaseWindow::updateCursorInfo()
{
    PlotCursorInfo info;
    auto p = _cursor->position();
    info << PlotCursorInfo::Item(PlotCursorInfo::CURSOR_X, p.x());
    info << PlotCursorInfo::Item(PlotCursorInfo::CURSOR_Y, p.y());
    fillCursorInfo(info);
    _cursorPanel->setText(info.format());
}

void PlotBaseWindow::updatePlotItemToggleActions()
{
    actnToggleTitle->setChecked(_plot->title()->visible());
    actnToggleLegend->setChecked(_plot->legend->visible());
}

void PlotBaseWindow::toggleTitle()
{
    _plot->title()->setVisible(!_plot->title()->visible());
    _plot->updateTitleVisibility();
    _plot->replot();
    schema()->markModified("PlotBaseWindow::toggleTitle");
    updatePlotItemToggleActions();
}

void PlotBaseWindow::toggleLegend()
{
    _plot->legend->setVisible(!_plot->legend->visible());
    _plot->replot();
    schema()->markModified("PlotBaseWindow::toggleLegend");
    updatePlotItemToggleActions();
}

void PlotBaseWindow::savePlotFormat()
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

void PlotBaseWindow::loadPlotFormat()
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

void PlotBaseWindow::copyPlotImage()
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

void PlotBaseWindow::copyPlotFormat()
{
    QCPL::copyPlotFormat(_plot);
}

void PlotBaseWindow::pastePlotFormat()
{
    auto err = QCPL::pastePlotFormat(_plot);
    if (err.isEmpty())
    {
        _plot->updateTitleVisibility();
        _plot->replot();
        schema()->markModified("PlotBaseWindow::pastePlotFormat");
        updatePlotItemToggleActions();
    }
    else Ori::Dlg::info(err);
}

void PlotBaseWindow::pasteLegendFormat()
{
    auto err = QCPL::pasteLegendFormat(_plot->legend);
    if (err.isEmpty())
    {
        _plot->replot();
        schema()->markModified("PlotBaseWindow::pasteLegendFormat");
    }
    else Ori::Dlg::info(err);
}

void PlotBaseWindow::pasteTitleFormat()
{
    auto err = QCPL::pasteTitleFormat(_plot->title());
    if (err.isEmpty())
    {
        _plot->replot();
        schema()->markModified("PlotBaseWindow::pasteTitleFormat");
    }
    else Ori::Dlg::info(err);
}

void PlotBaseWindow::pasteAxisFormat(QCPAxis *axis)
{
    auto err = QCPL::pasteAxisFormat(axis);
    if (err.isEmpty())
    {
        _plot->replot();
        schema()->markModified("PlotBaseWindow::pasteAxisFormat");
    }
    else Ori::Dlg::info(err);
}

void PlotBaseWindow::cursorFormatDlg()
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
        schema()->markModified("PlotBaseWindow::cursorFormatDlg");
}

void PlotBaseWindow::graphFormatDlg()
{
    auto g = _plot->selectedGraph();
    if (!g) return;

    QString id = g->name();
    QPen oldPen = g->pen();
    
    PlotHelpers::FormatPenDlgProps props;
    props.title = tr("线条格式 - %1").arg(id);
    props.onApply = [this, id](const QPen& pen){
        PlotHelpers::applyGraphPen(_plot, id, pen);
        _plot->replot();
    };
    if (id == Z::planeName(Z::T) || id == Z::planeName(Z::S)) {
        props.onReset = [this, id, oldPen](){
            auto defPen = id == Z::planeName(Z::T)
                ? AppSettings::instance().pen(AppSettings::PenGraphT)
                : AppSettings::instance().pen(AppSettings::PenGraphS);
            PlotHelpers::applyGraphPen(_plot, id, defPen);
            _plot->replot();
        };
    }
    if (PlotHelpers::formatPenDlg(oldPen, props)) {
        graphFormatted(g);
        schema()->markModified("PlotBaseWindow::graphFormatDlgT");
    }
}

void PlotBaseWindow::graphsMenuAboutToShow()
{
    auto g = _plot->selectedGraph();
    if (!g) return;
    bool manySegments = PlotHelpers::graphCount(_plot, g->name()) > 1;
    actnCopyGraphData->setVisible(!manySegments);
    actnCopyGraphDataCurSegment->setVisible(manySegments);
    actnCopyGraphDataAllSegments->setVisible(manySegments);
}

void PlotBaseWindow::copyGraphData()
{
    PlotHelpers::toClipboard(_plot->selectedGraph());
}

void PlotBaseWindow::copyGraphDataAllSegments()
{
    auto g = _plot->selectedGraph();
    if (!g) return;
    PlotHelpers::toClipboard(PlotHelpers::graphs(_plot, g->name()));
}

void PlotBaseWindow::copyGraphDataWithParams()
{
    // TODO
}
