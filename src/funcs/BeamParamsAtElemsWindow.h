#ifndef BEAM_PARAMS_AT_ELEMS_WINDOW_H
#define BEAM_PARAMS_AT_ELEMS_WINDOW_H

#include "../funcs/TableFuncWindow.h"
#include "../math/BeamParamsAtElemsFunction.h"

class BeamParamsAtElemsWindow final : public TableFuncWindow
{
    Q_OBJECT

public:
    explicit BeamParamsAtElemsWindow(Schema*);

    BeamParamsAtElemsFunction* function() const { return dynamic_cast<BeamParamsAtElemsFunction*>(_function); }

    /// Red-light overlay (Phase 4 follow-up): swap the table to the
    /// 632.8 nm values of a ``run_redlight.py`` report (W = w_633,
    /// X = axis offset, R/V = N/A) and retitle the window with the
    /// mode label. Passing an invalid report (``ok == false``)
    /// restores the normal 1064 nm display instead.
    void setRedlightMode(const RedlightReport& report);

    bool redlightMode() const;

    /// Schema recalculation clears a stale overlay: the report
    /// describes the saved file, so any edit invalidates it.
    void recalcRequired(Schema*) override;

signals:
    /// Emitted when the overlay was cleared by a schema recalculation
    /// (so the main-window toggle can uncheck itself) or when the
    /// window is being destroyed while the overlay is on.
    void redlightModeCleared();

private:
    QString _baseTitle;
};

#endif // BEAM_PARAMS_AT_ELEMS_WINDOW_H
