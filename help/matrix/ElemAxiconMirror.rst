.. index:: single: axicon mirror
.. index:: single: mirror (axicon)

轴锥反射镜
==========

轴锥反射镜是一种特殊类型的反射镜，具有锥形表面；根据其角度 `θ` 的符号，它可以是会聚的或发散的。

当光束沿法线入射时，轴锥反射镜在两个面的矩阵相同。当入射光束以角度 `α` 倾斜入射时，T 面和 S 面的矩阵不同。

由于光线矩阵取决于入射光束的半径 `r` ，该元件只能在单程方案中有效使用，其中光束半径从一开始就是已知的。在谐振腔中，它的作用相当于一个平面或一个点，具有单位矩阵。（这与真实的轴锥镜无关，只是软件的一种约定。）

轴锥反射镜的作用与 :doc:`轴锥透镜 <ElemAxiconLens>` 相同，只是你不必指定折射率。即使在 :ref:`布局 <layout>` 上，当它不在光学系统的端部时，也显示为透镜。

    .. image:: ElemAxiconMirror.png

.. note::

  在真实光学系统中，轴锥镜用于将高斯光束转变为无衍射的 `贝塞尔类光束 <https://en.wikipedia.org/wiki/Bessel_beam>`_。但 |rezonator| 无法计算这种光束，因此含轴锥镜的方案的计算结果仅在数学上正确，很难与实际情况对应。

.. seeAlso::

    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - `维基百科中的轴锥镜 <https://en.wikipedia.org/wiki/Axicon>`_
