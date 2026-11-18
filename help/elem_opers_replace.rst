.. _elem_opers_replace:
.. index:: single: replace element (command)

替换
====

:menuSelection:`元件 --> 替换...`

该命令打开 :doc:`catalog` ，为当前选中的元件选择类型。当前元件被替换为新类型的元件，其属性会复制到新元件。参数按名称复制，例如，如果你把 :doc:`matrix/ElemCurveMirror` 替换为 :doc:`matrix/ElemThinLens` ，角度会被复制，因为两者都有参数 :param:`α` 。而焦距不会被复制，因为它们的名称不同，应用程序也没有任何启发式规则来判断 :param:`R` 和 :param:`F` 的含义几乎相同。

    .. image:: img/catalog.png

.. seeAlso::

    - :doc:`elem_opers`
    - :doc:`elem_opers_append`
