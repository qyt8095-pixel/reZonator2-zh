.. index:: single: thick lens
.. index:: single: lens (thick)

厚透镜
======

.. |R1| replace:: `R`\ :sub:`1`
.. |R2| replace:: `R`\ :sub:`2`

厚透镜元件可以用长度 `L` 和折射率 `n` 来参数化。此外，它的左、右表面各有一个曲率半径 |R1| 和 |R2| 。

透镜表面的 ROC 可为凹面或凸面，取决于曲率半径的符号。曲率的正方向为从左到右，与方案中主光束的 :ref:`传播方向 <propagation_dir>` 一致。

完整元件

    .. image:: ElemThickLens.png

左半程

    .. image:: ElemThickLens_left.png

右半程

    .. image:: ElemThickLens_right.png

.. note::
    自 |rezonator| 2.1 起，透镜表面 ROC 采用 `标准符号约定 <https://en.wikipedia.org/wiki/Radius_of_curvature_(optics)>`_。旧文件在打开时会自动转换。在较旧的应用版本中，你将无法加载 2.1 保存的文件，也无法通过剪贴板粘贴元件。

.. seeAlso::

    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
