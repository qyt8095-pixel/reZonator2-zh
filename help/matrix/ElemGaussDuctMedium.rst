.. index:: single: gaussian duct (medium)

高斯导管（介质）
================

该元件按照 Siegman 的著作《Lasers》（1986，ISBN 0-935702-11-5）第 20.3 章“Gaussian apertures and complex ABCD matrices”实现。

高斯导管是一种横向非均匀介质，其中折射率和吸收系数都可能沿横向变化。

系数 `α` 是单位长度的损耗系数。

该元件与 :doc:`ElemGrinMedium` 具有相同的矩阵，唯一区别是参数 `γ` 为复数值（见 Siegman 著作第 791 页公式 43）。

    .. image:: ElemGaussDuctMedium.png

.. seeAlso::

    - :doc:`ElemGaussDuctSlab`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
