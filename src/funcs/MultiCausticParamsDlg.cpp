#include "MultiCausticParamsDlg.h"

#include "../widgets/ElemSelectorWidget.h"
#include "../widgets/VariableRangeEditor.h"

#include "helpers/OriWidgets.h"
#include "helpers/OriDialogs.h"

#include <QCheckBox>
#include <QGroupBox>

MultiCausticParamsDlg::MultiCausticParamsDlg(Schema *schema, const QVector<Z::Variable>& vars, const QString &helpTopic)
    : RezonatorDialog(DontDeleteOnClose | UseHelpButton)
{
    setWindowTitle(tr("区间"));
    setObjectName("MultiCausticParamsDlg");
    
    _helpTopic = helpTopic;

    ElementFilterPtr elemFilter(ElementFilter::make<ElementFilterIsRange>());

    _elemsSelector = new MultiElementSelectorWidget(schema, elemFilter);
    connect(_elemsSelector, &MultiElementSelectorWidget::currentElementChanged,
            this, &MultiCausticParamsDlg::currentElementChanged);

    _sameSettings = new QCheckBox(tr("将这些设置应用于所有元件"));

    _rangeEditor = new PointsRangeEditor;
    _rangeEditor->addWidget(_sameSettings, _rangeEditor->rowCount()+1, 0, 1, _rangeEditor->columnCount());

    mainLayout()->addWidget(_elemsSelector);
    mainLayout()->addWidget(Ori::Gui::group(tr("绘图精度"), _rangeEditor));
    mainLayout()->addSpacing(8);

    populate(vars);

    _elemsSelector->setCurrentRow(0);
    _elemsSelector->setFocus();
}

void MultiCausticParamsDlg::populate(const QVector<Z::Variable>& vars)
{
    auto elems = _elemsSelector->allElements();
    for (auto elem : std::as_const(elems))
    {
        bool hasRange = false;

        // Use given range for element
        for (const Z::Variable& var : vars)
            if (var.element == elem)
            {
                _elemsSelector->selectElement(elem);
                _elemRanges[elem] = var.range;
                hasRange = true;
                break;
            }

        // Make default range for the element if there is not given one
        if (!hasRange)
        {
            Z::VariableRange range;
            range.stop = elem->asRange()->axisLen();
            range.start = Z::Value(0, range.stop.unit());
            range.step = range.stop / 100.0;
            range.useStep = false;
            range.points = 100;
            _elemRanges[elem] = range;
        }
    }
}

void MultiCausticParamsDlg::collect()
{
    saveEditedRange(_elemsSelector->currentElement());

    auto selectedElems = _elemsSelector->selectedElements();
    if (selectedElems.isEmpty())
    {
        Ori::Dlg::warning(tr("未选择任何元件。\n请至少标记一个元件。"));
        _elemsSelector->setFocus();
        return;
    }

    _result.clear();
    for (auto elem : std::as_const(selectedElems))
    {
        Z::Variable var;
        var.element = elem;
        var.parameter = elem->asRange()->paramLength();
        var.range = _elemRanges[elem];
        _result.append(var);
    }

    accept();
}

void MultiCausticParamsDlg::currentElementChanged(Element *current, Element *previous)
{
    saveEditedRange(previous);

    if (_elemRanges.contains(current))
        _rangeEditor->setRange(_elemRanges[current]);
}

void MultiCausticParamsDlg::saveEditedRange(Element *elem)
{
    auto newRange = _rangeEditor->range();
    if (_sameSettings->isChecked())
        for (auto elem : _elemRanges.keys())
            _elemRanges[elem].assignPoints(newRange);
    else if (_elemRanges.contains(elem))
        _elemRanges[elem].assignPoints(newRange);
}
