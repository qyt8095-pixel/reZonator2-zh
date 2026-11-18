.. _elem_opers_slide:
.. index:: single: slide element (command)

滑动
====

:menuSelection:`元件 --> 滑动...`

当所选元件位于具有长度参数的同类元件之间时，例如 :ref:`elem_empty_range` 或 :ref:`elem_medium_range` ，该命令会产生沿周围元件移动该元件的效果。

    .. image:: img/elem_opers_slide_drawing.png

实际上，它改变两个周围元件的长度，使其中一个变长、另一个缩短相同的量。因此没有必要选择位于两个空程之间的元件。你可以直接选择任意两个空程并重新分配它们的长度。

    .. note::
        该命令会改变两个元件的长度。因此，当任一长度不是直接可编辑的（因为它受 :ref:`全局参数 <params_window>` 控制）时，该命令无法执行。

滑块显示总长度，拖动滑块手柄可以在两个元件之间重新分配长度。或者，也可以手动编辑一个元件的长度；第二个元件的长度会相应地重新计算。

    .. image:: img/elem_opers_slide.png

.. seeAlso::

    - :doc:`elem_opers`
    - :doc:`elem_opers_split`
    - :doc:`elem_opers_insert_into`
