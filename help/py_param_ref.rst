.. index:: single: ParamRef (Python)

类：ParamRef
============

对全局参数或元件参数的引用，针对多次更改参数值并恢复其原始值进行了优化，绘图函数需要这样做。

该类的对象不能直接构造；请使用 :ref:`schema.param_ref() <py_method_schema_param_ref>` 或 :ref:`Element.param_ref() <py_method_elem_param_ref>` 函数获取它们。

该类用于配合 Python 的 ``with`` 语句使用。执行进入代码块时，会记住原始参数值，所有直接或间接依赖该参数的元件都会被 :ref:`锁定 <custom_plot_lock>` ，以防止在修改参数值时出现不必要的界面变化。执行退出代码块后，原始参数值会恢复，所有锁定的元件都会解锁。这简化了绘图，你不必记住显式调用锁定/解锁方法。

典型用法如下

.. code-block:: python

    # Prepare arrays for store graph points
    graph_x = []
    graph_y = []
    # Prepare a round trip once,
    # no need to rebuild it for each point
    rt = schema.round_trip()
    with schema.param_ref('L_foc') as L_foc:
      for i in range(num_points):
        # Calculate the next argument
        x = L_foc_min + L_foc_step * i
        L_foc.set_value(x)
        # Calculate the next plot point
        y = rt.beam_radius()
        graph_x.append(x)
        graph_y.append(y)

参见 ``global_params_py_set.rez`` 示例，了解它的实际用法。

方法
----

.. index:: single: value (Python)
.. _py_method_param_ref_value:

``value()``
~~~~~~~~~~~

返回 SI 单位制的参数值。

.. #######################################################################

.. index:: single: set_value (Python)
.. _py_method_param_ref_set_value:

``set_value(value)``
~~~~~~~~~~~~~~~~~~~~

设置参数值。

参数：

- ``value`` (float) - SI 单位制的参数值

引发：

- ``ValueError`` - 如果值无效

.. seeAlso::

  - :doc:`custom_plot`
