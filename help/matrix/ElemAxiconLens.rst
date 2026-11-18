.. index:: single: axicon lens
.. index:: single: lens (axicon)

轴锥透镜
========

轴锥透镜是一种特殊类型的透镜，具有锥形表面；根据其角度 `θ` 的符号，它可以是会聚的或发散的。

当光束以法向角度入射时，轴锥透镜在两个平面上的矩阵相同。当入射光束以角度 `α` 倾斜入射时，T 平面和 S 平面的矩阵不同。

由于光线矩阵取决于入射光束的半径 `r` ，该元件只能有效地用于单程方案，其中光束半径从一开始就是已知的。在谐振腔中，它作为一个平面或一个点起作用，具有单位矩阵。（这与真实的轴锥无关，只是软件的一种约定。）

轴锥透镜的作用方式与 :doc:`轴锥反射镜 <ElemAxiconMirror>` 相同，只是除了角度之外，你还必须指定折射率 `n` 。

    .. image:: ElemAxiconLens.png

.. note::

  在真实的光学系统中，轴锥用于把高斯光束变成无衍射的 `类贝塞尔光束 <https://en.wikipedia.org/wiki/Bessel_beam>`_。但 |rezonator| 无法计算这样的光束，因此带有轴锥的方案的计算结果只在数学上是正确的，很难与真实情况对应起来。

.. seeAlso::

    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - `维基百科中的轴锥 <https://en.wikipedia.org/wiki/Axicon>`_
