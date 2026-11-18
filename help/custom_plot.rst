自定义绘图函数
==============

:menuSelection:`函数 --> 创建自定义绘图函数`

自定义绘图函数允许你使用提供的 :doc:`py_api` 进行任意用户计算，并将结果以图形形式输出到 :doc:`绘图窗口 <plot_window>` 中，而不是像更简单的 :doc:`custom_script` 函数那样以文本形式输出。这一强大功能使你能够分析光学方案、执行自定义计算并以图形方式可视化结果，非常适合可视化光学参数之间的依赖关系、趋势和关系。

对于自定义函数，绘图窗口会显示一个附加命令 :menuSelection:`绘图 --> 显示代码` ，以及工具栏上相应的 Python 图标按钮。该命令打开一个代码编辑器窗口，用于更改脚本代码。这个窗口可以安全关闭，因为代码实际存储在绘图窗口中，而不是代码窗口中。但是，如果你关闭绘图窗口本身，函数代码 *将会丢失* 。

代码模块
--------

自定义函数是一个用户定义的 Python 模块。模块文档字符串的第一行将用作人类可读的函数名称，并显示在函数窗口标题中。这使你可以为自定义绘图函数指定一个有意义的标题。在绘图标题中，该名称将替代 ``{func_name}`` 文本变量。

``figure()``
~~~~~~~~~~~~

代码模块必须包含一个 ``figure()`` 函数，用于配置绘图属性。每次重新计算之前都会调用该函数，这使你可以动态更改绘图属性（例如根据所选元件更改坐标轴标题），而无需重新打开窗口。

.. code-block:: python

  def figure():
    return {
      'x_dim': Z.DIM_LINEAR,
      'x_title': 'Position',
      'y_dim': Z.DIM_LINEAR,
      'y_title': 'Beam radius'
    }

该函数应返回一个包含以下键的字典：

- ``x_dim`` - X 轴的值量纲（:ref:`Z.DIM_LINEAR <py_const_dim_linear>` 、:ref:`Z.DIM_ANGULAR <py_const_dim_angular>` 、:ref:`Z.DIM_NONE <py_const_dim_none>` ）
- ``x_title`` - X 轴的默认标题。它可以包含元件标签或参数描述，并将替代 ``{default_title}`` 文本变量。
- ``y_dim`` - Y 轴的值量纲
- ``y_title`` - Y 轴的默认标题

``calculate()``
~~~~~~~~~~~~~~~

代码还必须包含一个 ``calculate()`` 函数，用于执行实际计算并生成要绘制的数据。当你按下 :guilabel:`运行` 按钮，或使用 :menuSelection:`脚本 --> 运行` 菜单命令，或通过 :menuSelection:`绘图 --> 更新` 刷新绘图窗口时，将无参数调用该函数。

.. code-block:: python

  def calculate():
    # Perform calculations
    x_values = [...]
    y_values = [...]
    return [
      {
        'label': 'My graph',
        'x': x_values,
        'y': y_values
      }
    ]

该函数应返回图形线条数据列表，其中每条线条由一个包含以下键的字典表示：

- ``label`` - 图例中显示的名称；同时，它也是将多条线条组合成单个多段图形的键
- ``x`` - X 坐标值列表或数组
- ``y`` - Y 坐标值列表或数组（长度必须与 ``x`` 相同）

输出
~~~~

|rezonator| 中的所有计算均以 SI 单位（米、弧度等）进行。提供给脚本的所有参数值也以 SI 单位表示。对于自定义绘图函数，你应返回 SI 单位的计算 X 值和 Y 值，无需任何转换。因为绘图窗口具有内置功能，可根据坐标轴的量纲类型（``figure()`` 函数中定义的 ``x_dim`` 和 ``y_dim`` 属性）选择和显示单位。用户可以通过绘图窗口界面选择首选单位。

``calculate()`` 函数的结果会自动显示为 :doc:`plot_window` 中的图形。你可以返回多个字典，在同一绘图上显示多条线条。具有相同 ``label`` 的字典成为单个多段图形的组成部分。你可以在函数未定义或谐振腔不稳定的位置使用 NaN（写作 ``float('nan')`` ）作为 Y 值。包含 NaN 值的单条线条会被拆分为多个段，也成为多段图形。线条标签 "T" 和 "S" 会被特殊处理，以便应用针对子午面和弧矢面的特殊 :ref:`图形格式 <app_settings_lines>` 。

对于简单的文本输出或调试，请使用 :doc:`custom_script` 。对于表格数据展示，请考虑 :doc:`custom_table` 。

.. _custom_plot_lock:

元件锁定
--------

当你的计算改变元件参数时（例如在参数扫描中），你应在修改元件之前锁定它，之后再解锁。这种方法：

- 保留原始参数值以便自动恢复
- 在计算期间禁用界面更新，以获得更好的性能
- 防止参数变化时重新计算其他函数

.. code-block:: python

  elem.lock()
  try:
    for i in range(point_count):
      elem.set_param('R', value)
      # Perform calculations...
  finally:
      elem.unlock()

始终使用 try/finally 块，以确保即使发生错误也能解锁元件。

更方便的方法是使用 Python 的 ``with`` 块，以及 :ref:`Element.param_ref() <py_method_elem_param_ref>` 或 :ref:`schema.param_ref() <py_method_schema_param_ref>` 方法返回的 :doc:`ParamRef <py_param_ref>` 对象，它允许自动锁定/解锁和参数值恢复：

.. code-block:: python

  with elem.param_res('R') as r:
    for i in range(point_count):
      r.set_value(value)
      # Perform calculations...

自定义库
--------

你可以使用 :menuSelection:`脚本 --> 保存到自定义库` 菜单命令，将代码保存到 :ref:`自定义代码库 <custom_func_lib>` 中以供日后使用。这使你可以为常见任务建立可复用计算脚本的集合

自定义参数
----------

自定义参数是你可以在任何元件上添加的任意参数，是元件预定义参数之外的补充。它们对自定义表格函数特别有用，因为它们允许你计算或跟踪元件默认参数未涵盖的属性。

你可以通过元件属性对话框向元件添加自定义参数，然后在计算中使用 :ref:`Element.param() <py_method_elem_param>` 方法访问它们。这提供了灵活性，可以用项目特定的数据或针对你自定义计算的属性来扩展元件。

示例项目
--------

通过 :menuSelection:`文件 --> 打开示例` 打开完整的工作示例 ``custom_plot.rez`` 和 ``misalign.rez`` ，了解自定义绘图函数在实践中的工作方式，并将其用作你自己计算的模板。在“打开示例”对话框中使用 "custom plot" 筛选器查看该主题的可用示例。

.. seeAlso::

  - :doc:`py_api`
  - :doc:`plot_window`
  - :doc:`custom_funcs`
  - :doc:`custom_script`
  - :doc:`custom_table`
  - :ref:`示例 - 自定义焦散线函数 <py_example_custom_caustic>`
