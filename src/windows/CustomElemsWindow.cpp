#include "CustomElemsWindow.h"

#include "../app/CustomElemsManager.h"
#include "../app/HelpSystem.h"
#include "../app/PersistentState.h"
#include "../core/ElementsCatalog.h"
#include "../io/Clipboard.h"
#include "../windows/ElementsCatalogDialog.h"
#include "../windows/ElementPropsDialog.h"
#include "../widgets/SchemaElemsTable.h"
#include "../widgets/Widgets.h"
#include "../windows/WindowsManager.h"

#include "helpers/OriDialogs.h"
#include "helpers/OriLayouts.h"
#include "helpers/OriWidgets.h"
#include "helpers/OriWindows.h"
#include "widgets/OriFlatToolBar.h"

#include <QFile>
#include <QFileSystemWatcher>
#include <QIcon>
#include <QMenu>
#include <QTabWidget>
#include <QToolButton>

namespace {

CustomElemsWindow* __instance = nullptr;

} // namespace

void CustomElemsWindow::showWindow()
{
    if (!__instance)
    {
        auto res = CustomElemsManager::loadLibrary();
        if (!res.ok())
        {
            Ori::Dlg::error(tr("加载自定义元件库时有提示信息：\n\n%1").arg(res.error()));
            return;
        }
        __instance = new CustomElemsWindow(res.result());
    }
    __instance->show();
    __instance->raise();
    __instance->activateWindow();
}

CustomElemsWindow::CustomElemsWindow(Schema *library) : QWidget(), _library(library)
{
    Ori::Wnd::initWindow(this, tr("自定义元件库"), ":/window_icons/catalog");

    createActions();
    createToolbar();
    createMenu();

    _table = new SchemaElemsTable(_library);
    _table->populate();
    connect(_table, QOverload<Element*>::of(&SchemaElemsTable::doubleClicked), this, &CustomElemsWindow::rowDoubleClicked);
    connect(_table, &SchemaElemsTable::currentCellChanged, this, &CustomElemsWindow::currentCellChanged);
    connect(_table, &SchemaElemsTable::beforeContextMenuShown, this, &CustomElemsWindow::contextMenuAboutToShow);
    _table->elementContextMenu = _menuContextElement;
    _table->lastRowContextMenu = _menuContextLastRow;
    _library->registerListener(_table);
    _library->selection().registerSelector(_table);

    auto elemsPage = Ori::Layouts::LayoutV({_toolbar, _table}).setMargin(2).setSpacing(0).makeWidget();

    _tabs = new QTabWidget;
    _tabs->addTab(elemsPage, tr("元件"));

    Ori::Layouts::LayoutV({_tabs}).setMargin(3).useFor(this);

    _watcher = new QFileSystemWatcher(this);
    connect(_watcher, &QFileSystemWatcher::fileChanged, this, &CustomElemsWindow::libraryFileChanged);
    QString fileName = CustomElemsManager::libraryFile();
    if (QFile::exists(fileName))
        _watcher->addPath(fileName);

    restoreState();
    Ori::Wnd::moveToScreenCenter(this);
}

CustomElemsWindow::~CustomElemsWindow()
{
    storeState();
    __instance = nullptr;
    delete _library;
}

void CustomElemsWindow::createActions()
{
    #define A_ Ori::Gui::V0::action

    _actnElemAdd = A_(tr("追加…"), this, SLOT(actionElemAdd()), ":/toolbar/elem_add", Qt::CTRL | Qt::Key_Insert);
    _actnElemMoveUp = A_(tr("上移选中项"), this, SLOT(actionElemMoveUp()), ":/toolbar/elem_move_up");
    _actnElemMoveDown = A_(tr("下移选中项"), this, SLOT(actionElemMoveDown()), ":/toolbar/elem_move_down");
    // TODO: share Enter shortcut between actions on different tabs (when those will be)
    _actnElemProp = A_(tr("属性…"), this, SLOT(actionElemProp()), ":/toolbar/elem_prop", Qt::Key_Return);
    _actnElemDelete = A_(tr("删除…"), this, SLOT(actionElemDelete()), ":/toolbar/elem_delete", Qt::CTRL | Qt::Key_Delete);

    // TODO: share edit shortcuts between actions on different tabs (when those will be)
    _actnEditCopy = A_(tr("复制", "Edit action"), this, SLOT(copy()), ":/toolbar/copy", QKeySequence::Copy);
    _actnEditPaste = A_(tr("粘贴", "Edit action"), this, SLOT(paste()), ":/toolbar/paste", QKeySequence::Paste);
    
    _actnShowHelp = A_(tr("帮助"), this, SLOT(showHelp()), ":/toolbar/help", QKeySequence::HelpContents);

    #undef A_
}

void CustomElemsWindow::createToolbar()
{
    _toolbar = Z::Gui::makeToolBar({
        Ori::Gui::textToolButton(_actnElemAdd), nullptr,
        _actnElemMoveUp, _actnElemMoveDown, nullptr,
        _actnEditCopy, _actnEditPaste, nullptr,
        Ori::Gui::textToolButton(_actnElemProp), nullptr,
        _actnElemDelete, nullptr,
        _actnShowHelp,
    });
}

void CustomElemsWindow::createMenu()
{
    _menuContextElement = Ori::Gui::menu(this,
        { _actnElemProp, nullptr,
          _actnEditCopy, _actnEditPaste, nullptr, _actnElemDelete});

    _menuContextLastRow = Ori::Gui::menu(this,
        { _actnElemAdd, _actnEditPaste });

}

void CustomElemsWindow::restoreState()
{
    QJsonObject root = PersistentState::load("elems");
    PersistentState::restoreWindowGeometry(root, this);
}

void CustomElemsWindow::storeState()
{
    QJsonObject root;
    PersistentState::storeWindowGeometry(root, this);
    PersistentState::save("elems", root);
}

void CustomElemsWindow::actionElemAdd()
{
    auto sample = ElementsCatalogDialog::chooseElementSample();
    if (!sample) return;

    Element *elem = ElementsCatalog::instance().create(sample->elem);
    if (!elem) return;

    _library->insertElements({elem}, _table->currentRow(), Arg::RaiseEvents(true));
    saveLibrary();
    editElement(elem);
}

void CustomElemsWindow::actionElemMoveUp()
{
    auto elem = _table->selected();
    if (elem)
    {
        _library->moveElementUp(elem);
        _table->setSelected(elem);
        saveLibrary();
    }
}

void CustomElemsWindow::actionElemMoveDown()
{
    auto elem = _table->selected();
    if (elem)
    {
        _library->moveElementDown(elem);
        _table->setSelected(elem);
        saveLibrary();
    }
}

void CustomElemsWindow::actionElemProp()
{
    auto elem = _table->selected();
    if (elem)
        editElement(elem);
    else
        // There will be no element when we press Enter on the last row
        // which is for element creation
        actionElemAdd();
}

void CustomElemsWindow::actionElemDelete()
{
    Elements elements = _table->selection();
    if (elements.isEmpty()) return;

    QStringList confirmation;
    confirmation << tr("正在删除元件：") << "";

    // List deleting elements
    for (int i = 0; i < elements.size(); i++)
        confirmation << QString("<b>%1</b>").arg(elements[i]->displayLabelTitle());

    if (!Ori::Dlg::ok(confirmation.join("<br>"))) return;

    _library->deleteElements(elements, Arg::RaiseEvents(true), Arg::FreeElem(true));

    saveLibrary();
}

void CustomElemsWindow::editElement(Element* elem)
{
    if (ElementPropsDialog::editElement(elem))
    {
        _library->events().raise(SchemaEvents::ElemChanged, elem, "CustomElemsWindow: element edited");
        saveLibrary();
    }
}

void CustomElemsWindow::rowDoubleClicked(Element* elem)
{
    if (elem)
        editElement(elem);
    else
        actionElemAdd();
}

void CustomElemsWindow::currentCellChanged(int curRow, int, int prevRow, int)
{
    int lastRow = _table->rowCount() - 1;
    if (curRow < lastRow && prevRow < lastRow) return;
    bool hasElem = curRow < lastRow;
    _actnElemDelete->setEnabled(hasElem);
    _actnEditCopy->setEnabled(hasElem);
    _actnElemMoveUp->setEnabled(hasElem);
    _actnElemMoveDown->setEnabled(hasElem);
}

void CustomElemsWindow::contextMenuAboutToShow(QMenu* menu)
{
    if (menu != _menuContextElement) return;

    auto elem = _table->selected();
    if (!elem) return;

    // TODO: check if element is formula and activate the 'Edit Formula' command
}

void CustomElemsWindow::copy()
{
    auto elems = _table->selection();
    if (!elems.isEmpty())
        Z::IO::Clipboard::setElements(elems);
}

void CustomElemsWindow::paste()
{
    auto elems = Z::IO::Clipboard::getElements();
    if (elems.isEmpty()) return;

    _library->insertElements(elems, _table->currentRow(), Arg::RaiseEvents(true));
    saveLibrary();
}

bool CustomElemsWindow::saveLibrary()
{
    _isLibrarySaving = true;
    QString res = CustomElemsManager::saveLibrary(_library);
    if (!res.isEmpty())
    {
        Ori::Dlg::error(tr("保存自定义元件库时有提示信息：\n\n%1").arg(res));
        return false;
    }
    QString fileName = CustomElemsManager::libraryFile();
    if (!_watcher->files().contains(fileName))
        _watcher->addPath(fileName);
    return true;
}

void CustomElemsWindow::libraryFileChanged(const QString&)
{
    if (_isLibrarySaving)
    {
        _isLibrarySaving = false;
        return;
    }

    auto res = CustomElemsManager::loadLibrary();
    if (!res.ok())
    {
        Ori::Dlg::error(tr("重新加载自定义元件库时有提示信息：\n\n%1").arg(res.error()));
        return;
    }

    QSharedPointer<Schema> reloadedLibrary(res.result());

    QString fileName = CustomElemsManager::libraryFile();
    if (!QFile::exists(fileName))
    {
        _watcher->removePath(fileName);
        if (_library->count() > 0)
        {
            if (Ori::Dlg::yes(tr(
                 "检测到自定义元件库"
                 "已被其他进程从文件系统中删除。"
                 "是否要将当前元件集保存为新库？")))
            {
                saveLibrary();
            }
            else
            {
                _library->deleteElements(_library->elements(), Arg::RaiseEvents(false), Arg::FreeElem(true));
                _table->populate();
            }
        }
        return;
    }

    // Move elements from reloaded library to the current library instance
    Elements reloadedElems(reloadedLibrary->elements());
    reloadedLibrary->deleteElements({reloadedElems}, Arg::RaiseEvents(false), Arg::FreeElem(false));
    _library->deleteElements(_library->elements(), Arg::RaiseEvents(false), Arg::FreeElem(true));
    _library->insertElements({reloadedElems}, -1, Arg::RaiseEvents(false));
    _table->populate();
}

void CustomElemsWindow::showHelp()
{
    Z::HelpSystem::instance()->showTopic("elem_library.html");
}
