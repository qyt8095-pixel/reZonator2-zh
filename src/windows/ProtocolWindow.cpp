#include "ProtocolWindow.h"

#include "../core/Protocol.h"

#include "helpers/OriWidgets.h"

#include <QMenu>
#include <QPlainTextEdit>

ProtocolWindow* ProtocolWindow::_instance = nullptr;

ProtocolWindow* ProtocolWindow::create()
{
    if (!_instance)
        _instance = new ProtocolWindow();
    return _instance;
}

ProtocolWindow::ProtocolWindow() : BasicMdiChild(InitOptions(initNoDefaultWidget))
{
    setTitleAndIcon(tr("日志"), ":/toolbar/protocol");

    _log = new QPlainTextEdit;
    _log->setReadOnly(true);

    Ori::Gui::setFontMonospace(_log);

    setContent(_log);

    _windowMenu = new QMenu(tr("日志"), this);
    _windowMenu->addAction(QIcon(":/toolbar/clear_log"), tr("清除"), [&](){ _log->clear(); });

    Z::Protocol::setView(_log);
}

ProtocolWindow::~ProtocolWindow()
{
    _instance = nullptr;

    Z::Protocol::setView(nullptr);
}
