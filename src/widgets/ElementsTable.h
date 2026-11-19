#ifndef ELEMENTS_TABLE_H
#define ELEMENTS_TABLE_H

#include "../core/Schema.h"
#include "../core/Element.h"
#include "../funcs/LidtMarks.h"

#include <QMap>
#include <QTableView>

class ElementsTableModel;

class ElementsTable : public QTableView, public ElementSelector
{
    Q_OBJECT

public:
    explicit ElementsTable(Schema* schema, QWidget *parent = nullptr);
    ~ElementsTable();

    // Inherited from ElementSelector
    Element* selected() const override { return currentElem(); }
    Elements selection() const override;

    void selectElems(const Elements& elems);

    Element* currentElem() const;
    void setCurrentElem(Element*);
    int currentRow() const;

    /// LIDT marks for the element list (Phase 4 follow-up):
    /// fail rows get a red background, warn rows an amber one,
    /// with a fluence/ratio tooltip. An empty map clears the marks.
    void setLidtMarks(const QMap<QString, LidtMark>& marks);
    void clearLidtMarks();

    QMenu *elementContextMenu = nullptr;
    QMenu *lastRowContextMenu = nullptr;

protected:
    void selectionChanged(const QItemSelection &selected, const QItemSelection &deselected) override;

signals:
    void currentElemChanged(Element*);
    void selectedElemsChanged(const Elements&);
    void elemDoubleClicked(Element*);

private slots:
     void currentRowChanged(const QModelIndex &current, const QModelIndex &);
     void indexDoubleClicked(const QModelIndex &index);
     void showContextMenu(const QPoint&);

private:
    Schema* _schema;
    ElementsTableModel* _model;
    Element* _curElem = nullptr;
};

#endif // ELEMENTS_TABLE_H
