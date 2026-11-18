.. index:: single: round-trip matrix (function)

往返矩阵
========

:menuSelection:`函数 --> 往返矩阵`

该函数计算方案的 :doc:`往返矩阵 <round_trip_matrix>` ，并显示在专门的窗口中。在元件列表中选定的元件被视为参考元件。元件矩阵的乘法从参考元件开始。

    .. image:: img/func_rt_1.png

如果方案是谐振腔（不是单程系统），则还会计算方案的 :ref:`稳定参数 <stability_param>` 。

在上一行中，元件列表按矩阵相乘的顺序显示。你可以单击每个元件的标签，打开一个单独的 :ref:`信息窗口 <func_matrix>` ，显示该元件的矩阵。

此外，如果启用了 :ref:`应用程序设置 <app_settings_show_py_code>` ，窗口可以将往返公式显示为 Python 代码，使用与 :doc:`func_matrix` 函数为此目的显示的相同变量名。

附加命令
--------

除了 :ref:`标准按钮 <info_window>` 之外，该函数还添加了几个新选项。


显示所有元件矩阵
~~~~~~~~~~~~~~~~

可选地，所有元件的矩阵都可以直接显示在窗口中，请使用工具栏按钮：

    .. image:: img/func_rt_2.png


设置参考面偏移
~~~~~~~~~~~~~~

默认情况下，往返计算使用整个元件矩阵。参考面位于选定元件之后，矩阵乘法从该元件开始。但如果选作参考的是具有长度参数的元件（例如晶体），则可以设置元件内部的可选偏移。然后元件根据 :ref:`图 <calc_round_trip_subrange>` 分成两个子元件，并计算元件内部的往返矩阵。

    .. image:: img/func_rt_3.png

根据一般的 :ref:`往返规则 <propagation_dir>` ，光束从左向右传播，而矩阵从右向左相乘，因此该偏移从元件的左边缘起量。

对话框中的“轴向长度”值显示最大可能的偏移，它是光束在元件中能传播的最长几何路径。对于某些元件（例如 :doc:`matrix/ElemBrewsterPlate` ），轴向长度大于元件长度，因为光轴与长度测量方向之间存在夹角。

.. seeAlso::

    - :doc:`info_window`
    - :doc:`func_rt_plot`
    - :doc:`round_trip_matrix`
    - :doc:`func_freeze`
