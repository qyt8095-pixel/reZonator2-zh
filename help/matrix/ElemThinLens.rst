.. _elem_thin_lens:
.. index:: single: thin lens
.. index:: single: lens (thin)

薄透镜
======

薄透镜没有厚度参数，不考虑玻璃的折射率，也不计算透镜体内光束的传播。

根据焦距的符号，透镜可以是会聚的或发散的（正或负）。

该透镜在子午面和弧矢面的焦距 `F` 相同。当光束沿法线入射到透镜上时，两个面的矩阵也相等。当入射光束以角度 `α` 倾斜入射时，T 面和 S 面的矩阵不同。

薄透镜的作用与 :doc:`球面镜 <ElemCurveMirror>` 相同，只是你需要指定焦距而不是曲率半径。

    .. image:: ElemThinLens.png

.. seeAlso::

    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - :doc:`ElemCurveMirror`
