.. index:: single: GRIN lens
.. index:: single: lens (GRIN)

GRIN 透镜
=========

.. |n2| replace:: `n`\ :sub:`2`

GRIN 透镜是一块折射率在横向呈二次变化的平行平面板，在轴上有最大值或最小值，从而产生透镜效应。该元件在两个工作面的矩阵类似，但梯度常数 |n2| 可以分别为子午面和弧矢面独立设定。

注意，该元件表示自由空间中的一段 GRIN 介质。它具有平面的输入和输出界面。如果你想构建更复杂的 GRIN 棒，例如一个或两个界面为曲面，你应使用 :doc:`ElemGrinMedium` 元件，并在其两侧加上适当的界面元件。

完整元件

    .. image:: ElemGrinLens.png

透镜内部的光束传播也可以计算。

左半程

    .. image:: ElemGrinLens_left.png

右半程

    .. image:: ElemGrinLens_right.png

当梯度常数 |n2| 设为零时，该元件变为简单的 :doc:`ElemPlate` 。

.. seeAlso::

    - :doc:`./ElemGrinMedium`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - `维基百科中的梯度折射率光学 <https://en.wikipedia.org/wiki/Gradient-index_optics>`_
