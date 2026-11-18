.. _func_caustic:
.. index:: single: caustic (function)

焦散线
======

:menuSelection:`函数 --> 焦散线`

该函数沿指定元件绘制光束半径和波前曲率半径。

参数
----

    .. image:: img/func_caustic_params.png

元件
~~~~

该选择器让你指定沿哪个元件绘制焦散线。只有具有长度参数的元件才能被选择。这些元件是自由空间、晶体等。长度参数通常称为 :param:`L` 。

绘图精度
~~~~~~~~

这些字段让你设置结果图形中的点数。点数可以直接输入到“点数”字段中。也可以在“按步长”字段中指定点与点之间的距离（绘图步长）。

对话框中的“可绘长度”值表示光束在该元件内可以走过的最长 :ref:`几何路径 <axial_length>` 。它成为绘图的横向范围。对于某些元件（例如 :doc:`matrix/ElemBrewsterPlate` ），可绘长度大于元件长度，因为光轴与长度测量方向之间存在夹角。

附加参数
--------

.. _func_caustic_aux_params:

:menuSelection:`视图 --> 函数参数`

在这个选项卡中，你可以选择要绘制的内容——光束半径或波前曲率半径。绘图会为每种绘图模式记住不同的度量单位。

    .. image:: img/func_caustic_aux_params.png

如果元件内部有束腰，光束半径的图形通常比波前曲率图形需要更少的点就能达到准确。这是因为波前曲率半径在近场区变化很快，不能像在远场区那样用几个点来近似。

    .. image:: img/func_caustic_r_1.png

    .. image:: img/func_caustic_r_2.png

.. _func_caustic_spec_points:

特殊点
------

:menuSelection:`视图 --> 特殊点`

该函数计算绘图范围起点和终点处的光束半径。此外，如果图中存在束腰，还会显示其位置和半径。见黄色高亮的值。光束的瑞利距离（`z`\ :sub:`0` ）和发散角之半（`V`\ :sub:`S` ），以弧度和度为单位，也会根据找到的束腰尺寸计算出来。

  .. image:: img/func_caustic_spec_points.png


.. _func_caustic_aux_cmds:

绘图窗口的附加命令
------------------

显示光束形状
~~~~~~~~~~~~

:menuSelection:`视图 --> 光束形状`

该函数可以在 :ref:`光标 <cursor>` 位置示意性地渲染光束截面，以可视化光束像散。

光束形状面板可以用鼠标在绘图上移动。当鼠标位于面板上方时，靠近其边框（显示为细虚线）处点击鼠标，还可以调整其大小。

光束形状图像可以与整个绘图分开复制；请使用它的上下文菜单。

  .. image:: img/func_caustic_shape.png

.. seeAlso::

    - :doc:`plot_window`
    - :doc:`plot_opers`
    - :doc:`func_caustic_mr`
    - :doc:`func_caustic_mb`
