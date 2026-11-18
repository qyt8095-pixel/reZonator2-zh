.. _elem_opers_merge:
.. index:: single: merge element (command)

合并
====

:menuSelection:`元件 --> 合并...`

该命令的作用与 :doc:`elem_opers_split` 命令相反。它把两个具有长度参数的相邻元件合并为一个。实际上，该命令删除所选元件中的第二个，保留下来的元件的长度增加被删除元件的长度。

    .. image:: img/elem_opers_merge_drawing.png

    .. note::
        该命令会改变保留下来的元件的长度。因此，当长度不是直接可编辑的（因为它受 :ref:`全局参数 <params_window>` 控制）时，该命令无法执行。

.. seeAlso::

    - :doc:`elem_opers`
    - :doc:`elem_opers_split`
    - :doc:`elem_opers_insert_into`
