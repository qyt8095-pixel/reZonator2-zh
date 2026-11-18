.. index:: single: multibeam caustic (function)

多光束焦散线
============

:menuSelection:`函数 --> 多光束焦散线`

这是 :doc:`func_caustic_mr` 的特殊版本，用于 :ref:`单程 <schema_kind_sp>` 系统。它计算在 :doc:`pumps_window` 中设置的所有输入光束的光束半径。

使用泵浦窗口中的 :ref:`设置颜色 <pump_window_set_color>` 命令，为对应某个输入光束的图形线条设置独特的外观。颜色更改会立即应用到所有已打开的函数窗口。

  .. image:: img/func_caustic_mb_colors.png

参数
----

该函数与 :doc:`func_caustic_mr` 函数具有相同的参数。

附加参数
--------

该函数没有附加参数

特殊点
------

:menuSelection:`视图 --> 特殊点`

该函数计算与 :ref:`焦散线 <func_caustic_spec_points>` 函数相同的值，但针对每个元件分别计算。值仅针对与绘图上当前选中的图形对应的一个输入光束计算。点击图形线条即可选中它。当前处理的输入光束的标签显示在特殊点选项卡中，也显示在 :ref:`光标 <cursor>` 面板中。

  .. image:: img/func_caustic_mb_spec_points.png

绘图窗口的附加命令
------------------

该函数与 :ref:`焦散线 <func_caustic_mr_aux_cmds>` 函数具有相同的命令。

.. seeAlso::

  - :doc:`plot_window`
  - :doc:`plot_opers`
  - :doc:`func_caustic`
  - :doc:`func_caustic_mr`
