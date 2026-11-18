.. _elem_opers_insert_into:
.. index:: single: insert into (command)

插入
====

:menuSelection:`元件 --> 插入到...`

该命令对任何具有 Length 参数的元件都有效，例如 :ref:`elem_empty_range` 或 :ref:`elem_brewster_crystal` 。该命令打开 :doc:`目录 <catalog>` ，以选择新元件的类型。新创建的元件插入到当前选定元件的中间，将其分成两个同类型元件，两者的总长度等于原元件的长度。

    .. image:: img/elem_opers_split_drawing.png

该命令与 :doc:`分割 <elem_opers_split>` 命令等效，但允许你选择插入到分开部分之间的元件类型（:doc:`分割 <elem_opers_split>` 命令只允许插入 :ref:`elem_point` ），但不允许你设定分割比例（它始终使用系数 0.5）。

    .. note::
        该命令会改变原元件的长度。因此，当长度不能直接编辑时（因为它由 :ref:`全局参数 <params_window>` 控制），该命令无法执行。

.. seeAlso::

    - :doc:`elem_opers`
    - :doc:`分割 <elem_opers_split>`
    - :doc:`elem_opers_merge`
