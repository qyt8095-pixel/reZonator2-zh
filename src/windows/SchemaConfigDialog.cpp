#include "SchemaConfigDialog.h"
#include "core/Schema.h"
#include "../orion/GuiHelper.h"
#include "../orion/OptionsGroup.h"

#include <QBoxLayout>
#include <QComboBox>
#include <QFormLayout>
#include <QGroupBox>
#include <QIcon>
#include <QLabel>
#include <QLineEdit>
#include <QTextEdit>

namespace Z {
namespace Dlgs {

bool schemaParams(QWidget *parent, Schema *schema)
{
    SchemaConfigDialog dialog(parent, schema);
    bool result = dialog.exec() == QDialog::Accepted;
    if (result)
        schema->raiseEvent(Schema::Event::ParamsChanged);
    return result;
}

} // namespace Dlgs
} // namespace Z


SchemaConfigDialog::SchemaConfigDialog(QWidget* parent, Schema* schema)
    : Ori::Gui::BasicConfigDialog(parent), _schema(schema)
{
    setWindowTitle(tr("光路图属性"));
    setWindowIcon(QIcon(":/window_icons/schema"));

    createPages({ createGeneralPage(), createUnitsPage(), createCommentPage() });
}

QWidget* SchemaConfigDialog::createGeneralPage()
{
    QGroupBox *page = new QGroupBox;
    page->setWindowTitle(tr("常规"));
    page->setWindowIcon(QIcon(":/config_pages/general"));

    editorTitle = new QLineEdit;

    ///////// main layout
    QVBoxLayout *layoutMain = new QVBoxLayout;
    layoutMain->addWidget(new QLabel(tr("标题：")));
    layoutMain->addWidget(editorTitle);
    layoutMain->addStretch();
    page->setLayout(layoutMain);

    return page;
}

QWidget* SchemaConfigDialog::createUnitsPage()
{
    QGroupBox *page = new QGroupBox;
    page->setWindowTitle(tr("计量单位"));
    page->setWindowIcon(QIcon(":/config_pages/units"));

    comboUnitsLinear = new QComboBox;
    comboUnitsAngle = new QComboBox;
    comboUnitsBeamsize = new QComboBox;
    comboUnitsLambda = new QComboBox;

    Z::Units::populate(comboUnitsLinear, Z::Units::Dim_Linear);
    Z::Units::populate(comboUnitsBeamsize, Z::Units::Dim_Linear);
    Z::Units::populate(comboUnitsLambda, Z::Units::Dim_Linear);
    Z::Units::populate(comboUnitsAngle, Z::Units::Dim_Angle);

    QFormLayout *layoutUnits = new QFormLayout;
    layoutUnits->addRow(new QLabel(tr("线性量：")), comboUnitsLinear);
    layoutUnits->addRow(new QLabel(tr("角度量：")), comboUnitsAngle);
    layoutUnits->addRow(new QLabel(tr("光束半径：")), comboUnitsBeamsize);
    layoutUnits->addRow(new QLabel(tr("波长：")), comboUnitsLambda);

    ///////// main layout
    QVBoxLayout *layoutMain = new QVBoxLayout;
    layoutMain->addLayout(layoutUnits);
    layoutMain->addStretch();
    page->setLayout(layoutMain);

    return page;
}

QWidget* SchemaConfigDialog::createCommentPage()
{
    editorComment = new QTextEdit;
    editorComment->setWindowTitle(tr("注释"));
    editorComment->setWindowIcon(QIcon(":/config_pages/comment"));
    editorComment->setAcceptRichText(false);
    QFont font("Monospace", 10);
    font.setStyleHint(QFont::TypeWriter);
    font.setFixedPitch(true);
    editorComment->setFont(font);
    return editorComment;
}

/*QWidget* SchemaConfigDialog::createCalcPage()
{
    QWidget *page = new QWidget;
    page->setWindowTitle(tr("计算"));
    page->setWindowIcon(QIcon(":/options48/calc"));

    groupStabCalcWay = new OptionsGroupBox(tr("稳定性参数计算方式："), true);
    groupStabCalcWay->addOption(tr("P = (A + D)/2。稳定性：-1 < P < 1"));
    groupStabCalcWay->addOption(tr("P = 1 - ((A + D)/2)^2。稳定性：0 < P <= 1"));

    QVBoxLayout *layoutMain = new QVBoxLayout;
    layoutMain->setMargin(0);
    layoutMain->addWidget(groupStabCalcWay);
    layoutMain->addStretch();
    page->setLayout(layoutMain);

    return page;
}*/

void SchemaConfigDialog::populate()
{
    Ori::Helpers::setSelectedId(comboUnitsLinear, _schema->units(Z::Units::Dim_Linear));
    Ori::Helpers::setSelectedId(comboUnitsLambda, _schema->units(Z::Units::Dim_Lambda));
    Ori::Helpers::setSelectedId(comboUnitsBeamsize, _schema->units(Z::Units::Dim_Beamsize));
    Ori::Helpers::setSelectedId(comboUnitsAngle, _schema->units(Z::Units::Dim_Angle));
    //groupStabCalcWay->setOption(params->stabCalcWay);

    editorComment->setText(_schema->comment());
    editorTitle->setText(_schema->title());
}

void SchemaConfigDialog::collect()
{
    _schema->lockEvents();

    _schema->setUnits(Z::Units::Dim_Linear, Ori::Helpers::getSelectedId(comboUnitsLinear));
    _schema->setUnits(Z::Units::Dim_Lambda, Ori::Helpers::getSelectedId(comboUnitsLambda));
    _schema->setUnits(Z::Units::Dim_Beamsize, Ori::Helpers::getSelectedId(comboUnitsBeamsize));
    _schema->setUnits(Z::Units::Dim_Angle, Ori::Helpers::getSelectedId(comboUnitsAngle));
    //_schema->stabCalcWay = SchemaParams::StabCalcWay(groupStabCalcWay->option());

    _schema->setComment(editorComment->toPlainText());
    _schema->setTitle(editorTitle->text());

    _schema->unlockEvents();
}
