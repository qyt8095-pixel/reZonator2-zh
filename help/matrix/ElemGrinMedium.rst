.. index:: single: GRIN medium

GRIN 介质
=========

.. |n2| replace:: `n`\ :sub:`2`

GRIN 介质的折射率沿横向呈二次变化，在轴上有极大值或极小值，从而产生透镜效应。该元件在两个工作平面上具有相似的矩阵，但梯度常数 |n2| 可以分别为切向和弧矢平面独立设置。

与 :doc:`ElemGrinLens` 不同，该元件不包含任何界面。为了得到正确的结果，你应在介质两侧放置适当的界面元件。

    .. image:: ElemGrinMedium.png

当梯度常数 |n2| 设为零时，该元件变为简单的 :doc:`ElemMediaRange` 。

.. seeAlso::

    - :doc:`./ElemGrinLens`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - `维基百科中的渐变折射率光学 <https://en.wikipedia.org/wiki/Gradient-index_optics>`_
