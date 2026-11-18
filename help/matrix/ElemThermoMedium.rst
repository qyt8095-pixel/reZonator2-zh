.. index:: single: thermo medium

热介质
======

.. |n0| replace:: `n`\ :sub:`0`
.. |n2| replace:: `n`\ :sub:`2`

热介质的折射率在横向呈二次变化，在轴上有最大值或最小值，从而产生透镜效应。

该元件与 :doc:`ElemGrinMedium` 完全类似，不过你不用设置梯度常数 |n2| ，而是可以直接指定焦距 `F` ，梯度常数用 :doc:`../calc_grin` 工具计算。

该元件是柱对称的，子午面和弧矢面之间没有区别。

    .. image:: ../../img/elem/ElemThermoMedium.svg


.. seeAlso::

    - :doc:`./ElemThermoLens`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - `维基百科中的梯度折射率光学 <https://en.wikipedia.org/wiki/Gradient-index_optics>`_
