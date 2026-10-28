#include "AppSettingsDialog.h"

#include "../app/AppSettings.h"
#include "../app/HelpSystem.h"
#include "../widgets/UnitWidgets.h"

#include "helpers/OriLayouts.h"
#include "helpers/OriWidgets.h"
#include "widgets/OriLabels.h"
#include "widgets/OriOptionsGroup.h"

#include "qcpl_format_editors.h"

#include <QApplication>
#include <QBoxLayout>
#include <QCheckBox>
#include <QComboBox>
#include <QDebug>
#include <QFormLayout>
#include <QLabel>
#include <QIcon>
#include <QSpinBox>

using namespace Ori::Layouts;
using namespace Ori::Widgets;

namespace Z {
namespace Dlg {

bool editAppSettings(Ori::Dlg::PageId currentPageId)
{
    AppSettingsDialog dialog(qApp->activeWindow(), currentPageId);
    return dialog.exec() == QDialog::Accepted;
}

} // namespace Dlgs
} // namespace Z

namespace  {
class NumberPrecisionSpinBox : public QSpinBox
{
public:
    NumberPrecisionSpinBox() : QSpinBox()
    {
        setRange(1, 16);
        setFixedWidth(QFontMetrics(font()).boundingRect("00").width() * 4);
    }
};
}

//------------------------------------------------------------------------------
//                              ConfigDialog
//------------------------------------------------------------------------------

AppSettingsDialog::AppSettingsDialog(QWidget* parent, Ori::Dlg::PageId currentPageId) : Ori::Dlg::BasicConfigDialog(parent)
{
    pageListIconSize = QSize(40, 40);

    setObjectName("AppSettingsDialog");
    setTitleAndIcon(tr("应用设置"), ":/window_icons/options");

    createPages({
                    createGeneralPage(),
                    createGeneralPage2(),
                    createViewPage(),
                    //createLayoutPage(), the only settings "transparent background" is not applicable to clipboard export (at least on Windows)
                    createUnitsPage(),
                    createExportPage(),
                    //createCalcPage(),
                    createLinesPage(),
                });

    setCurrentPageId(currentPageId);
    
    connect(this, &Ori::Dlg::BasicConfigDialog::helpRequested, this, [](const QString &topic){
        Z::HelpSystem::instance()->showTopic(topic);
    });
}

QWidget* AppSettingsDialog::createGeneralPage()
{
    auto page = new Ori::Dlg::BasicConfigPage(AppSettings::PageGeneral, tr("行为 1"), ":/toolbar/options", "app_settings_behavior.html");

    _groupOptions = new Ori::Widgets::OptionsGroupV2(tr("选项"), {
        {"editNewElem", tr("编辑刚创建的元件")},
        {"elemAutoLabel", tr("为创建的元件生成标签")},
        {"elemAutoLabelPasted", tr("为粘贴的元件生成标签")},
        {"pumpAutoLabel", tr("为新建的泵浦生成标签")},
        //{"showStartWindow", tr("应用启动时显示起始窗口")},
        {"showProtocolAtStart", tr("应用启动后显示日志窗口")},
        //{"showCustomElemLibrary", tr("在元件目录中显示自定义元件")},
        {"showPythonMatrices", tr("在信息窗口中显示矩阵的 Python 代码")},
        {"skipFuncWindowsLoading", tr("打开光路图时不加载函数窗口")},
        {"useOnlineHelp", tr("在线打开文档，而不是从本地文件打开")},
    });

    page->add({_groupOptions, page->stretch()});
    return page;
}

QWidget* AppSettingsDialog::createGeneralPage2()
{
    auto page = new Ori::Dlg::BasicConfigPage(AppSettings::PageGeneral2, tr("行为 2"), ":/config_pages/general");
    
    _updateCheckInterval = new QComboBox; 
    _updateCheckInterval->addItem(tr("无"), int(UpdateCheckInterval::None));
    _updateCheckInterval->addItem(tr("每天"), int(UpdateCheckInterval::Daily));
    _updateCheckInterval->addItem(tr("每周"), int(UpdateCheckInterval::Weekly));
    _updateCheckInterval->addItem(tr("每月"), int(UpdateCheckInterval::Monthly));
    
    auto groupUpdates = LayoutV({
        tr("自动检查更新"),
        _updateCheckInterval,
    }).makeGroupBox(tr("更新"));
    
    page->add({groupUpdates, page->stretch()});
    return page;
}

QWidget* AppSettingsDialog::createViewPage()
{
    auto page = new Ori::Dlg::BasicConfigPage(AppSettings::PageView, tr("界面"), ":/config_pages/view", "app_settings_intf.html");

    // group box "Options"
    _groupView = new Ori::Widgets::OptionsGroupV2(tr("选项"), {
        {"smallToolbarImages", tr("使用小工具栏图标")},
        {"showBackground", tr("显示背景图片")},
        {"useNativeMenuBar", tr("使用原生菜单栏（需要重启）")},
        {"useSystemDialogs", tr("使用系统打开/保存文件对话框")},
    });

    _numberPrecisionData = new NumberPrecisionSpinBox;
    _showImagUnitAsJ = new QCheckBox(tr("用 'j' 而不是 'i' 显示虚数单位"));
    _showImagUnitAtEnd = new QCheckBox(tr("在虚部之后显示虚数单位"));
    auto groupFormat = LayoutV({
        LayoutH({
            new QLabel(tr("结果格式化的数字精度")), _numberPrecisionData
        }),
        _showImagUnitAsJ, _showImagUnitAtEnd,
    }).makeGroupBox(tr("数字格式"));

    page->add({_groupView, groupFormat, page->stretch()});
    return page;
}

QWidget* AppSettingsDialog::createLayoutPage()
{
    auto page = new Ori::Dlg::BasicConfigPage(AppSettings::PageLayout, tr("布局"), ":/config_pages/layout");

    // group box "Options"
    _groupLayoutExport = new Ori::Widgets::OptionsGroupV2(tr("图像导出选项"), {
        {"layoutExportTransparent", tr("使用透明背景")},
    });

    page->add({_groupLayoutExport, page->stretch()});
    return page;
}

QWidget* AppSettingsDialog::createUnitsPage()
{
    auto page = new Ori::Dlg::BasicConfigPage(AppSettings::PageUnits, tr("单位"), ":/config_pages/units");

    _defaultUnitBeamRadius = new UnitComboBox(Z::Dims::linear());
    _defaultUnitLinear = new UnitComboBox(Z::Dims::linear());
    _defaultUnitAngle = new UnitComboBox(Z::Dims::angular());

    auto unitsLayout = new QFormLayout;
    unitsLayout->setHorizontalSpacing(12);
    unitsLayout->addRow(tr("光束半径"), _defaultUnitBeamRadius);
    unitsLayout->addRow(tr("线性量"), _defaultUnitLinear);
    unitsLayout->addRow(tr("角度量"), _defaultUnitAngle);

    auto infoLabel = new QLabel(tr(
        "这些单位用于展示函数结果，"
        "当函数首次计算且尚未选择自定义单位时。"));
    infoLabel->setWordWrap(true);
    auto infoIcon = new QLabel;
    infoIcon->setPixmap(QIcon(":/toolbar/info").pixmap(24, 24));
    infoIcon->setFixedWidth(24);

    auto defUnitsGroup = LayoutV({
        unitsLayout,
        Space(12),
        LayoutH({
            LayoutV({infoIcon, Stretch()}),
            infoLabel
        })
    }).makeGroupBox(tr("默认单位"));

    page->add({defUnitsGroup, page->stretch()});
    return page;
}

QWidget* AppSettingsDialog::createExportPage()
{
    auto page = new Ori::Dlg::BasicConfigPage(AppSettings::PageExport, tr("导出"), ":/toolbar/save", "app_settings_export.html");

    _groupExportData = new Ori::Widgets::OptionsGroupV2(tr("图形数据导出选项"), {
        {"exportAsCsv", tr("使用 CSV 格式（否则使用纯文本格式）")},
        {"exportSystemLocale", tr("使用系统区域设置（否则使用 C 区域设置）")},
        {"exportTransposed", tr("转置模式（按行而非按列写入数值）")},
    });

    _exportNumberPrecision = new NumberPrecisionSpinBox;
    _groupExportData->addControls({
        LayoutH({new QLabel(tr("数字精度")), _exportNumberPrecision, Stretch()}).boxLayout(),
    });

    _groupExportPlot = new Ori::Widgets::OptionsGroupV2(tr("绘图图像导出选项"), {
        {"exportHideCursor", tr("保存、复制或打印图像时隐藏光标线")}
    });

    page->add({_groupExportData, _groupExportPlot, page->stretch()});
    return page;
}

QWidget* AppSettingsDialog::createCalcPage()
{
    auto page = new Ori::Dlg::BasicConfigPage(AppSettings::PageCalc, tr("计算"), ":/toolbar/options");

    _groupCalcOpts = new Ori::Widgets::OptionsGroupV2(tr("选项"), {
    });

    page->add({_groupCalcOpts, page->stretch()});
    return page;
}

QWidget* AppSettingsDialog::createLinesPage()
{
    auto page = new Ori::Dlg::BasicConfigPage(AppSettings::PageCalc, tr("线条"), ":/toolbar/gauss_near_zone", "app_settings_lines.html");
    page->setLongTitle(tr("默认线条格式"));

    _elemBoundMarkersPen = new QCPL::PenEditorWidget;
    _stabBoundMarkerPen = new QCPL::PenEditorWidget;
    _cursorPen = new QCPL::PenEditorWidget;
    _graphPenT = new QCPL::PenEditorWidget;
    _graphPenS = new QCPL::PenEditorWidget;

    page->add({
        LayoutV({
            new LabelSeparator(tr("T 图线条"), true), _graphPenT, SpaceV(2),
            new LabelSeparator(tr("S 图线条"), true), _graphPenS, SpaceV(2),
            new LabelSeparator(tr("光标线"), true), _cursorPen, SpaceV(2),
            new LabelSeparator(tr("稳定性边界标记"), true), _stabBoundMarkerPen, SpaceV(2),
            new LabelSeparator(tr("元件边缘标记"), true), _elemBoundMarkersPen,
        }).setMargin(0).boxLayout(),
        page->stretch(),
    });
    return page;
}

void AppSettingsDialog::populate()
{
    const AppSettings &settings = AppSettings::instance();

    // options
    _groupOptions->setOption("editNewElem", settings.editNewElem);
    _groupOptions->setOption("elemAutoLabel", settings.elemAutoLabel);
    _groupOptions->setOption("elemAutoLabelPasted", settings.elemAutoLabelPasted);
    _groupOptions->setOption("pumpAutoLabel", settings.pumpAutoLabel);
    //_groupOptions->setOption("showStartWindow", settings.showStartWindow);
    _groupOptions->setOption("showProtocolAtStart", settings.showProtocolAtStart);
    //_groupOptions->setOption("showCustomElemLibrary", settings.showCustomElemLibrary);
    _groupOptions->setOption("showPythonMatrices", settings.showPythonMatrices);
    _groupOptions->setOption("skipFuncWindowsLoading", settings.skipFuncWindowsLoading);
    _groupOptions->setOption("useOnlineHelp", settings.useOnlineHelp);
    
    Ori::Gui::setSelectedId(_updateCheckInterval, (int)settings.updateCheckInterval);

    // view
    _groupView->setOption("smallToolbarImages", settings.smallToolbarImages);
    _groupView->setOption("showBackground", settings.showBackground);
    _groupView->setOption("useNativeMenuBar", settings.useNativeMenuBar);
    _groupView->setOption("useSystemDialogs", settings.useSystemDialogs);
    _numberPrecisionData->setValue(settings.numberPrecisionData);
    _showImagUnitAsJ->setChecked(settings.showImagUnitAsJ);
    _showImagUnitAtEnd->setChecked(settings.showImagUnitAtEnd);

    // layout
    //_groupLayoutExport->setOption("layoutExportTransparent", settings.layoutExportTransparent);

    // units
    _defaultUnitBeamRadius->setSelectedUnit(settings.defaultUnitBeamRadius);
    _defaultUnitLinear->setSelectedUnit(settings.defaultUnitLinear);
    _defaultUnitAngle->setSelectedUnit(settings.defaultUnitAngle);

    // export
    _groupExportData->setOption("exportAsCsv", settings.exportAsCsv);
    _groupExportData->setOption("exportSystemLocale", settings.exportSystemLocale);
    _groupExportData->setOption("exportTransposed", settings.exportTransposed);
    _exportNumberPrecision->setValue(settings.exportNumberPrecision);
    _groupExportPlot->setOption("exportHideCursor", settings.exportHideCursor);

    // graphs
    _elemBoundMarkersPen->setValue(settings.pen(AppSettings::PenElemBound));
    _stabBoundMarkerPen->setValue(settings.pen(AppSettings::PenStabBound));
    _cursorPen->setValue(settings.pen(AppSettings::PenCursor));
    _graphPenT->setValue(settings.pen(AppSettings::PenGraphT));
    _graphPenS->setValue(settings.pen(AppSettings::PenGraphS));
}

bool AppSettingsDialog::collect()
{
    AppSettings &settings = AppSettings::instance();

    // options
    settings.editNewElem = _groupOptions->option("editNewElem");
    settings.elemAutoLabel = _groupOptions->option("elemAutoLabel");
    settings.elemAutoLabelPasted = _groupOptions->option("elemAutoLabelPasted");
    settings.pumpAutoLabel = _groupOptions->option("pumpAutoLabel");
    //settings.showStartWindow = _groupOptions->option("showStartWindow");
    settings.showProtocolAtStart = _groupOptions->option("showProtocolAtStart");
    //settings.showCustomElemLibrary = _groupOptions->option("showCustomElemLibrary");
    settings.showPythonMatrices = _groupOptions->option("showPythonMatrices");
    settings.skipFuncWindowsLoading = _groupOptions->option("skipFuncWindowsLoading");
    settings.useOnlineHelp = _groupOptions->option("useOnlineHelp");
    
    settings.updateCheckInterval = (UpdateCheckInterval)Ori::Gui::getSelectedId(
        _updateCheckInterval, (int)UpdateCheckInterval::Weekly);

    // view
    settings.smallToolbarImages = _groupView->option("smallToolbarImages");
    settings.showBackground = _groupView->option("showBackground");
    settings.useNativeMenuBar = _groupView->option("useNativeMenuBar");
    settings.useSystemDialogs = _groupView->option("useSystemDialogs");
    settings.numberPrecisionData = _numberPrecisionData->value();
    settings.showImagUnitAsJ = _showImagUnitAsJ->isChecked();
    settings.showImagUnitAtEnd = _showImagUnitAtEnd->isChecked();

    // layout
    //settings.layoutExportTransparent = _groupLayoutExport->option("layoutExportTransparent");

    // units
    settings.defaultUnitBeamRadius = _defaultUnitBeamRadius->selectedUnit();
    settings.defaultUnitLinear = _defaultUnitLinear->selectedUnit();
    settings.defaultUnitAngle = _defaultUnitAngle->selectedUnit();

    // export
    settings.exportAsCsv = _groupExportData->option("exportAsCsv");
    settings.exportSystemLocale = _groupExportData->option("exportSystemLocale");
    settings.exportTransposed = _groupExportData->option("exportTransposed");
    settings.exportNumberPrecision = _exportNumberPrecision->value();
    settings.exportHideCursor = _groupExportPlot->option("exportHideCursor");

    // graphs
    settings.setPen(AppSettings::PenElemBound, _elemBoundMarkersPen->value());
    settings.setPen(AppSettings::PenStabBound, _stabBoundMarkerPen->value());
    settings.setPen(AppSettings::PenCursor, _cursorPen->value());
    settings.setPen(AppSettings::PenGraphT, _graphPenT->value());
    settings.setPen(AppSettings::PenGraphS, _graphPenS->value());

    settings.save();
    return true;
}
