.. index:: single: gaussian duct (slab)

高斯导管（平板）
================

该元件依据 Siegman 的著作《Lasers》（1986，ISBN 0-935702-11-5）第 20.3 章“Gaussian apertures and complex ABCD matrices”实现。

高斯导管是一种横向非均匀介质，其中折射率和吸收系数都可能随横向位置变化。

系数 `α` 是单位长度的损耗因子。

该元件与 :doc:`ElemGrinLens` 具有相同的矩阵，唯一的区别是参数 `γ` 为复数值（见 Siegman 著作第 791 页公式 43）。

    .. image:: ElemGaussDuctSlab.png

.. seeAlso::

    - :doc:`ElemGaussDuctMedium`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
