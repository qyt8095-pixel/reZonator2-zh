.. _py_api:
.. index:: single: python api

Python API
==========

|rezonator| 提供 Python API，你可以用它编写自定义计算和绘图函数。这些函数可以访问方案元件、执行计算，并生成自定义表格和绘图。该 API 提供两个主要模块：:doc:`rezonator <py_global>` （简写别名为 ``Z`` ）和 :doc:`schema <py_schema>` 。

.. tocTree::
   :maxDepth: 1
   :caption: API 模块与类：

   py_global
   py_schema
   py_element
   py_matrix
   py_matrix3
   py_param_ref
   py_ray_vector
   py_round_trip
   py_examples

重要说明
--------

元件索引
~~~~~~~~

与常规 Python 列表不同，方案中的元件从 1 开始索引，以与它们在 :doc:`元件列表 <schema_elems>` 中的编号一致。

计量单位
~~~~~~~~

所有值都使用 SI 单位（米、弧度等）。根据需要在文本输出中显示时进行换算。对于 :doc:`表格 <custom_table>` 和 :doc:`绘图 <custom_plot>` 函数无需换算，因为 :doc:`表格 <table_window>` 和 :doc:`绘图 <plot_window>` 窗口都允许选择合适的计量单位来显示数值。

临时更改
~~~~~~~~

在进行临时参数 :ref:`更改 <py_method_elem_set_param>` 时（例如，在 :doc:`绘图函数 <custom_plot>` 计算期间），请使用 :ref:`Element.lock() <py_method_elem_lock>` 和 :ref:`Element.unlock() <py_method_elem_unlock>` 方法（或分别处理全局参数的 :ref:`schema.param_lock() <py_method_schema_lock_param>` 和 :ref:`schema.param_unlock() <py_method_schema_unlock_param>` ），以确保正确恢复，并防止 UI 进行不必要的更新。

更方便的方法是使用 Python 的 ``with`` 语句块，以及返回 :doc:`ParamRef <py_param_ref>` 对象的 :ref:`Element.param_ref() <py_method_elem_param_ref>` 或 :ref:`schema.param_ref() <py_method_schema_param_ref>` 方法，它允许自动锁定/解锁和参数值恢复。

性能
~~~~

:ref:`往返矩阵 <round_trip>` 计算在每次光束特性计算之前自动执行（例如 :ref:`RoundTrip.beam_radius() <py_method_rt_beam_radius>` ）。这保证了实际的元件参数被纳入考虑。对于同一特性的多次查询，请将结果存入局部变量，而不是重新计算。

.. seeAlso::

  - :doc:`functions`
  - :doc:`custom_script`
  - :doc:`custom_table`
  - :doc:`custom_plot`
