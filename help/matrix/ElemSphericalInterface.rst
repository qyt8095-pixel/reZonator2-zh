.. index:: single: spherical interface

球面界面
========

.. |n1| replace:: `n`\ :sub:`1`
.. |n2| replace:: `n`\ :sub:`2`

该元件表示两种介质之间曲率为 `R` 的球面边界，两种介质的折射率分别为 |n1| 和 |n2| 。光束被认为正入射到该边界上。

界面可以是凹的或凸的，取决于曲率半径的符号。曲率的正方向是从左到右，与方案中主光束的 :ref:`传播方向 <propagation_dir>` 一致。

  .. image:: ElemSphericalInterface.png

.. note::
  自 |rezonator| 2.1 起，界面 ROC 使用 `标准符号约定 <https://en.wikipedia.org/wiki/Radius_of_curvature_(optics)>`_。旧文件在打开时会自动转换。在旧版本应用中，你将无法加载 2.1 保存的文件，也无法通过剪贴板粘贴元件。

.. warning::
  界面元件左右相邻的元件应该是 :doc:`ElemEmptyRange` 或 :doc:`ElemMediaRange` 。如果不是，|rezonator| 不会报错，但你可能会得到不正确的结果。

.. seeAlso::

    - :doc:`ElemNormalInterface`
    - :doc:`ElemBrewsterInterface`
    - :doc:`ElemTiltedInterface`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
