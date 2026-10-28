#include "SchemaParamsWindow.h"

#include "../app/PersistentState.h"
#include "../app/HelpSystem.h"
#include "../widgets/SchemaParamsTable.h"
#include "../widgets/ParamEditor.h"
#include "../widgets/ParamEditorEx.h"
#include "../windows/AdjustmentWindow.h"

#include "helpers/OriWidgets.h"
#include "helpers/OriDialogs.h"

#include <QAction>
#include <QLineEdit>
#include <QTimer>
#include <QToolButton>

namespace SchemaParamsWindowStorable
{
    SchemaWindow* createWindow(Schema* schema)
    {
        return SchemaParamsWindow::create(schema);
    }
} // namespace SchemaParamsWindowStorable

//------------------------------------------------------------------------------
//                             SchemaParamsWindow
//------------------------------------------------------------------------------

SchemaParamsWindow* SchemaParamsWindow::_instance = nullptr;

SchemaParamsWindow* SchemaParamsWindow::create(Schema* owner)
{
    if (!_instance)
        _instance = new SchemaParamsWindow(owner);
    return _instance;
}

SchemaParamsWindow::SchemaParamsWindow(Schema *owner) : SchemaMdiChild(owner)
{
    setTitleAndIcon(tr("参数"), ":/window_icons/parameter");

    _table = new SchemaParamsTable(owner);
    setContent(_table);

    createActions();
    createMenuBar();
    createToolBar();

    _table->setContextMenu(_contextMenu);
    connect(_table, &SchemaParamsTable::paramDoubleClicked, this, &SchemaParamsWindow::setParameterValue);
}

SchemaParamsWindow::~SchemaParamsWindow()
{
    _instance = nullptr;
}

void SchemaParamsWindow::createActions()
{
    #define A_ Ori::Gui::action

    _actnParamAdd = A_(tr("创建…"), this, &SchemaParamsWindow::createParameter, ":/toolbar/param_add", Qt::CTRL | Qt::Key_Insert);
    _actnParamDelete = A_(tr("删除…"), this, &SchemaParamsWindow::deleteParameter, ":/toolbar/param_delete", Qt::CTRL | Qt::Key_Delete);
    _actnParamSet = A_(tr("设置…"), this, &SchemaParamsWindow::setParameterValue, ":/toolbar/param_prop");
    _actnParamEdit = A_(tr("编辑…"), this, &SchemaParamsWindow::editParameter, ":/toolbar/param_edit", Qt::CTRL | Qt::Key_Return);
    _actnParamAdjust = A_(tr("调节"), this, &SchemaParamsWindow::adjustParameter, ":/toolbar/adjust");

    #undef A_
}

void SchemaParamsWindow::createMenuBar()
{
    _windowMenu = Ori::Gui::menu(tr("参数"), this,
        { _actnParamAdd, _actnParamSet, _actnParamEdit, nullptr, _actnParamAdjust, nullptr, _actnParamDelete });

    _contextMenu = Ori::Gui::menu(this,
        { _actnParamSet, _actnParamEdit, nullptr, _actnParamAdjust, nullptr, _actnParamDelete });
}

void SchemaParamsWindow::createToolBar()
{
    populateToolbar({ Ori::Gui::textToolButton(_actnParamAdd),
        Ori::Gui::textToolButton(_actnParamSet), _actnParamEdit, nullptr, _actnParamDelete });
}

void SchemaParamsWindow::createParameter()
{
    ParamSpecEditor ed(nullptr, {
        .recentKeyPrefix = "global_param",
        .existedParams = schema()->globalParamsAsElem()->params(),
    });
    if (!ed.exec(tr("创建参数")))
        return;

    auto param = new Z::Parameter(ed.dim(), ed.alias(), ed.label(), ed.name(), ed.descr());
    auto unit = RecentData::getUnit("global_param_unit", param->dim());
    param->setValue(Z::Value(0, unit));
    schema()->addGlobalParam(param);

    schema()->events().raise(SchemaEvents::GlobalParamCreated, param, "Params window: param created");
    
    QTimer::singleShot(100, this, [this, param](){
        _isSettingValueForNewParam = true;
        _table->setSelected(param);
        setParameterValue();
    });
}

void SchemaParamsWindow::deleteParameter()
{
    auto deletingParam = _table->selected();
    if (!deletingParam) return;

    // Check if there are dependent parameters via formulas
    Z::Parameters dependentParams = schema()->formulas()->dependentParams(deletingParam);
    if (!dependentParams.isEmpty())
    {
        QStringList dependentAliases;
        for (Z::Parameter *param : std::as_const(dependentParams))
            dependentAliases << "<b>" % param->alias() % "</b>";
        return Ori::Dlg::info(
            tr("无法删除参数 <b>%1</b>，因为有全局参数依赖于它：<br><br>%2")
                .arg(deletingParam->alias(), dependentAliases.join(", ")));
    }

    // Check if there are dependent parameters via links
    Z::ParamLink *dependentLink = schema()->paramLinks()->bySource(deletingParam);
    if (dependentLink)
    {
        QStringList dependentParams;
        for (Element *elem : schema()->elements())
            for (Z::Parameter *param : elem->params())
                if (param == dependentLink->target())
                    dependentParams << tr("元件 <b>%1</b>，参数 <b>%2</b>").arg(elem->label(), param->label());
        if (!dependentParams.isEmpty())
            return Ori::Dlg::info(
                tr("无法删除全局参数 <b>%1</b>，<br>因为某些元件的参数依赖于它：<br><br>%2")
                    .arg(deletingParam->alias(), dependentParams.join("<br>")));
    }

    if (Ori::Dlg::yes(tr("删除参数 <b>%1</b> 吗？").arg(deletingParam->alias())))
    {
        schema()->events().raise(SchemaEvents::GlobalParamDeleting, deletingParam, "Params window: param deleting");
        schema()->formulas()->free(deletingParam);
        schema()->removeGlobalParam(deletingParam, true);
        schema()->events().raise(SchemaEvents::GlobalParamDeleted, deletingParam, "Params window: param deleted");
    }
}

void SchemaParamsWindow::setParameterValue()
{
    auto param = _table->selected();
    if (!param) return;

    auto globalParams = schema()->availableDependencySources();
    ParamEditorEx editor(param, schema()->formulas(), &globalParams);
    bool ok = Ori::Dlg::Dialog(&editor, false)
                .withTitle(tr("设置数值"))
                .withIconPath(":/window_icons/parameter")
                .withOnHelp([]{
                    Z::HelpSystem::instance()->showTopic("params_window.html#params-window-value");
                })
                .withContentToButtonsSpacingFactor(2)
                .withOnDlgShown([&editor]{ editor.focus(); })
                .connectOkToContentApply()
                .exec();
    if (ok)
    {
        schema()->events().raise(SchemaEvents::RecalRequred, "Params window: param value set");
    }

    if (_isSettingValueForNewParam)
    {
        _isSettingValueForNewParam = false;
        RecentData::setUnit("global_param_unit", param->value().unit());
    }
}

void SchemaParamsWindow::editParameter()
{
    auto param = _table->selected();
    if (!param) return;

    ParamSpecEditor editor(param, {
        .existedParams = schema()->globalParamsAsElem()->params()
    });
    if (!editor.exec(tr("编辑参数")))
        return;

    bool edited = false;
    bool changed = false;
    auto alias = editor.label();
    auto descr = editor.descr();
    auto dim = editor.dim();
    Z::Value newValue;
    if (param->alias() != alias) {
        if (schema()->formulas()->renameDependency(param, alias)) {
            // do recalc to put formulas in error state if rename failed
            newValue = param->value();
            changed = true;
        }
        param->setAlias(alias);
        param->setLabel(alias);
        param->setName(alias);
        edited = true;
    }
    if (param->description() != descr) {
        param->setDescription(descr);
        edited = true;
    }
    if (param->dim() != dim) {
        auto unit = RecentData::getUnit("global_param_unit", dim);
        auto value = unit->fromSi(param->value().toSi());
        newValue = Z::Value(value, unit);
        param->setDim(dim);
        edited = true;
        changed = true;
    }
    if (edited)
        schema()->events().raise(SchemaEvents::GlobalParamEdited, param, "Params window: param edited");
    if (changed) {
        param->setValue(newValue);
        schema()->events().raise(SchemaEvents::RecalRequred, "Params window: param value set");
    }
}

void SchemaParamsWindow::adjustParameter()
{
    auto param = _table->selected();
    if (!param) return;

    AdjustmentWindow::adjust(schema(), param);
}

void SchemaParamsWindow::shortcutEnterPressed()
{
    setParameterValue();
}
