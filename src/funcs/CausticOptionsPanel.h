#ifndef CAUSTI_COPTIONS_PANEL_H
#define CAUSTI_COPTIONS_PANEL_H

#include "../funcs/FuncOptionsPanel.h"
#include "../math/CausticFunction.h"

#include "helpers/OriLayouts.h"

template <typename TCausticWindow>
class CausticOptionsPanel : public FuncOptionsPanel
{
public:
    CausticOptionsPanel(TCausticWindow *window) : FuncOptionsPanel(window), _window(window)
    {
        // TODO: check if these strings are translated
        Ori::Layouts::LayoutV({
            makeSectionHeader(tr("函数模式")),
            makeModeButton(":/toolbar/plot_w", tr("光束半径"), int(CausticFunction::Mode::BeamRadius)),
            makeModeButton(":/toolbar/plot_r", tr("波前曲率半径"), int(CausticFunction::Mode::FrontRadius)),
            //TODO:NEXT-VER makeModeButton(":/toolbar/plot_v", tr("光束发散角"), int(CausticFunction::Mode::HalfAngle)),
            Ori::Layouts::Stretch()
        }).setSpacing(0).setMargin(0).useFor(this);

        showCurrentMode();
    }

    int currentFunctionMode() const override
    {
        return static_cast<int>(_window->function()->mode());
    }

    void functionModeChanged(int mode) override
    {
        _window->function()->setMode(static_cast<CausticFunction::Mode>(mode));
    }

private:
    TCausticWindow* _window;
};

#endif // CAUSTI_COPTIONS_PANEL_H
