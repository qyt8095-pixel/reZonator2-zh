.. index:: single: thermal lens

热透镜
======

.. |n0| replace:: `n`\ :sub:`0`
.. |n2| replace:: `n`\ :sub:`2`

热透镜的折射率沿横向呈二次变化，在轴上有极大值或极小值，从而产生透镜效应。

该元件与 :doc:`ElemGrinLens` 完全相似，只是你可以直接指定焦距范围 `F` ，而不设置梯度常数 |n2| ，梯度常数使用 :doc:`../calc_grin` 工具计算。

该元件是柱对称的，在切向和弧矢平面之间没有区别。

    .. image:: ../../img/elem/ElemThermoLens.svg

.. seeAlso::

    - :doc:`./ElemThermoMedium`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - `维基百科中的渐变折射率光学 <https://en.wikipedia.org/wiki/Gradient-index_optics>`_
