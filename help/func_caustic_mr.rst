.. _func_caustic_mr:
.. index:: single: multirange caustic (function)

多段焦散线
==========

:menuSelection:`函数 --> 多段焦散线`

该函数与 :doc:`func_caustic` 函数相同，但允许你同时沿多个元件绘制焦散线。

参数
----

元件
~~~~

应沿其绘制焦散线的元件列表。列表中只显示具有长度参数的元件，如空段、晶体等。长度参数通常称为 :param:`L` 。列表右侧有按钮，可让你快速选中或取消选中元件。

绘图精度
~~~~~~~~

这些字段用于设置结果图形中的点数。点数可以直接在“点数”字段中输入。也可以在“按步长”字段中指定点之间的距离（绘图步长）。

对话框中的“可绘长度”值显示光束在元件中能走过的最长 :ref:`几何路径 <axial_length>` 。这成为绘图的水平范围。对于某些元件（例如 :doc:`matrix/ElemBrewsterPlate` ），可绘长度大于元件长度，因为光轴与长度测量方向之间存在夹角。

对所有元件使用这些设置
~~~~~~~~~~~~~~~~~~~~~~

对每个元件使用相同的点数。当你不想为元件设置不同的点数时，只需设置该标志并仅指定一次所需的点数。在这种情况下，参数“点数”或“按步长”的相同值将用于所有元件。

  .. image:: img/func_caustic_mr_params.png

附加参数
--------

:menuSelection:`视图 --> 函数参数`

该函数与 :ref:`焦散线 <func_caustic_aux_params>` 函数具有相同的绘图模式。

特殊点
------

:menuSelection:`视图 --> 特殊点`

该函数计算与 :ref:`焦散线 <func_caustic_spec_points>` 函数相同的值，但针对每个元件分别计算。

.. _func_caustic_mr_aux_cmds:

绘图窗口的附加命令
------------------

该函数与 :ref:`焦散线 <func_caustic_aux_cmds>` 函数具有相同的命令，并增加了一些新命令。

.. _func_caustic_mr_elem_edges:

切换元件边缘标记
~~~~~~~~~~~~~~~~

:menuSelection:`视图 --> 元件边缘标记`

该命令切换相邻绘图范围（元件）之间绘制的竖直线的可见性。

  .. image:: img/func_caustic_mr_elem_edges.png

元件边界标记格式
~~~~~~~~~~~~~~~~

:menuSelection:`格式 --> 元件边缘标记格式`

该命令更改当前函数窗口中元件边缘标记的外观。应用于所有新打开的函数窗口的默认外观由 :ref:`应用程序设置 <app_settings_lines>` 控制。

.. seeAlso::

  - :doc:`plot_window`
  - :doc:`plot_opers`
  - :doc:`func_caustic`
  - :doc:`func_caustic_mb`
