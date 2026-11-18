.. _func_matrix:

元件矩阵
========

:menuSelection:`元件 --> 显示矩阵`

:menuSelection:`元件 --> 显示全部矩阵`

  .. image:: img/func_matrix.png

该窗口显示在 :doc:`schema_elems` 中选中的一个或多个元件的光线矩阵。

如果某个元件的正向和反向 :ref:`传播 <propagation_dir>` 矩阵不同，例如 :doc:`matrix/ElemThickLens` ，两者都会显示。

除了便于查看的表格视图外，该窗口还可以将矩阵显示为 Python NumPy 变量。默认不使用该功能，应在 :ref:`应用程序设置 <app_settings_show_py_code>` 中启用。这是一项调试功能，可用于测试脚本。它与 :doc:`func_rt` 函数配合使用，后者也可以用相同的变量名显示往返乘法的 Python 代码。

.. seeAlso::

    - :doc:`info_window`
