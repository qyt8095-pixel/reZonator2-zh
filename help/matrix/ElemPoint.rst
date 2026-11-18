.. _ElemPoint:
.. _elem_point:
.. index:: single: point element

点元件
======

点元件是一种辅助元件，具有单位矩阵。它对传播的光束没有任何影响。该元件与 :doc:`平面镜 <ElemFlatMirror>` 的区别仅在于外观表示，计算上完全相同。

    .. image:: ../../img/elem/ElemPoint.svg

例如，你可以将该元件用作两个相邻的不同语义的区间元件之间的分隔符，然后独立地更改各区间的数值。

    .. image:: ElemPoint_example.png

.. seeAlso::

    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
