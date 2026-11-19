#ifndef OPTIMIZER_WINDOW_H
#define OPTIMIZER_WINDOW_H

#include "../core/Units.h"
#include "../io/ISchemaWindowStorable.h"
#include "../math/OptimizerFunction.h"
#include "../windows/SchemaWindows.h"
#include "../windows/RezonatorDialog.h"

#include <QTableWidget>

QT_BEGIN_NAMESPACE
class QComboBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QSpinBox;
QT_END_NAMESPACE

namespace Ori {
namespace Widgets {
class StatusBar;
}}

class ElemAndParamSelector;
class ElemSelectorWidget;

/**
    Optimizer tool window: two editable tables (variables and merit targets)
    plus a bottom control bar (Start / Stop, max iterations, live Merit
    value, Apply / Revert). The calculation itself lives in OptimizerFunction.
*/
class OptimizerWindow : public SchemaMdiChild, public ISchemaWindowStorable
{
    Q_OBJECT

public:
    explicit OptimizerWindow(Schema* schema);
    ~OptimizerWindow() override;

    OptimizerFunction* function() const { return _function; }

    /// No initial setup dialog is needed: variables and targets are added
    /// inside the window, so the window can open with empty tables.
    bool configure() { return true; }

    QList<QMenu*> menus() override { return QList<QMenu*>() << _menu; }
    QString helpTopic() const override { return _function->helpTopic(); }

    // Implementation of SchemaListener
    void recalcRequired(Schema*) override { refreshCurrentValues(); }

    ElemDeletionReaction reactElemDeletion(const Elements& elems) override;

    // Implementation of ISchemaWindowStorable
    QString storableType() const override { return _function->alias(); }
    bool storableRead(const QJsonObject& root, Z::Report*) override;
    bool storableWrite(QJsonObject& root, Z::Report*) override;

public slots:
    void update();

private slots:
    void startOptimization();
    void stopOptimization();
    void applyResult();
    void revertResult();
    void addVariable();
    void removeVariable();
    void addTarget();
    void removeTarget();
    void onVariableCellChanged(int row, int col);
    void onTargetCellChanged(int row, int col);
    void onLengthUnitChanged(int index);

private:
    enum VarCols
    {
        VAR_COL_ENABLED,
        VAR_COL_PARAM,
        VAR_COL_MODE,
        VAR_COL_MIN,
        VAR_COL_MAX,
        VAR_COL_CURRENT,
        VAR_COL_RESULT,
        VAR_COLS_COUNT
    };

    enum TargetCols
    {
        TGT_COL_ELEM,
        TGT_COL_KIND,
        TGT_COL_VALUE,
        TGT_COL_WEIGHT,
        TGT_COL_CURRENT,
        TGT_COL_CONTRIB,
        TGT_COLS_COUNT
    };

    enum StatusPanels
    {
        STATUS_INFO,
        STATUS_PANELS_COUNT,
    };

    OptimizerFunction* _function;
    QTableWidget* _varTable;
    QTableWidget* _targetTable;
    QMenu* _menu = nullptr;
    QAction* _actnStart;
    QAction* _actnStop;
    QAction* _actnApply;
    QAction* _actnRevert;
    QPushButton* _btnStart;
    QPushButton* _btnStop;
    QPushButton* _btnApply;
    QPushButton* _btnRevert;
    QPushButton* _btnAddVar;
    QPushButton* _btnRemoveVar;
    QPushButton* _btnAddTarget;
    QPushButton* _btnRemoveTarget;
    QSpinBox* _maxIter;
    QLabel* _meritLabel;
    QComboBox* _lengthUnitCombo;
    /// Display unit for all length quantities in this window (beam radius
    /// targets and measured values, length-dimension variables). Internal
    /// computation and stored values always stay in SI.
    Z::Unit _lengthUnit = Z::Units::mm();
    Ori::Widgets::StatusBar* _statusBar;
    bool _running = false;
    bool _stopFlag = false;
    bool _closeRequested = false;
    bool _updatingTables = false;

protected:
    // While a run is in progress, closing is delayed: the stop flag is set
    // and the window closes after the run finishes (see startOptimization).
    void closeEvent(QCloseEvent* event) override;

    void createActions();
    void createMenuBar();
    void createToolBar();
    void createStatusBar();
    void createContent();

    void rebuildVariableTable();
    void rebuildTargetTable();
    void refreshUnitLabels();
    void refreshCurrentValues();
    void refreshTargetResults();
    void refreshResultValues();
    void refreshButtons();
    void showResultSummary();
    void setControlsEnabled(bool enabled);

    /// Unit used to display a variable's values: the window's length unit
    /// for linear-dimension parameters, the parameter's own unit otherwise.
    Z::Unit displayUnit(Z::Unit paramUnit) const;

    int rowOfCellWidget(QWidget* w, QTableWidget* table) const;
    void onVariableModeChanged(QWidget* combo);
    void onTargetKindChanged(QWidget* combo);

    static QString formatSi(double valueSi, Z::Unit unit);
    static QString formatCandidates(const QVector<double>& candidatesSi, Z::Unit unit);
};

//------------------------------------------------------------------------------

/**
    Dialog for adding a new optimization variable:
    picks an element parameter, a mode (continuous range or discrete
    candidate list) and the bounds/candidates.
*/
class OptimizerVariableDlg : public RezonatorDialog
{
    Q_OBJECT

public:
    struct Result
    {
        Element* element = nullptr;
        Z::Parameter* param = nullptr;
        OptimizerFunction::VarMode mode = OptimizerFunction::VarMode::Continuous;
        double minSi = 0;
        double maxSi = 0;
        QVector<double> candidatesSi;
    };

    explicit OptimizerVariableDlg(Schema* schema, Z::Unit lengthUnit);

    const Result& result() const { return _result; }

protected:
    QString helpTopic() const override { return OptimizerFunction::help_topic(); }

protected slots:
    void collect() override;

private slots:
    void modeChanged(int index);
    void guessBounds();

private:
    Schema* _schema;
    Result _result;
    Z::Unit _lengthUnit;
    ElemAndParamSelector* _elemSelector;
    QComboBox* _mode;
    QLineEdit* _minEdit;
    QLineEdit* _maxEdit;
    QLineEdit* _candidatesEdit;
    QLabel* _unitLabel;

    void populate();
};

//------------------------------------------------------------------------------

/**
    Dialog for adding a new merit target: picks a target element (not needed
    for the stability-center target), a metric, a target value and a weight.
*/
class OptimizerTargetDlg : public RezonatorDialog
{
    Q_OBJECT

public:
    struct Result
    {
        OptimizerFunction::TargetKind kind = OptimizerFunction::TargetKind::StabilityCenter;
        Element* element = nullptr;
        double targetSi = 0;
        double weight = 1.0;
    };

    explicit OptimizerTargetDlg(Schema* schema, Z::Unit lengthUnit);

    const Result& result() const { return _result; }

protected:
    QString helpTopic() const override { return OptimizerFunction::help_topic(); }

protected slots:
    void collect() override;

private slots:
    void kindChanged(int index);

private:
    Result _result;
    Z::Unit _lengthUnit;
    ElemSelectorWidget* _elemSelector;
    QComboBox* _kind;
    QLineEdit* _targetEdit;
    QLineEdit* _weightEdit;
};

#endif // OPTIMIZER_WINDOW_H
