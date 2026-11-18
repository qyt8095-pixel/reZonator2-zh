自定义表格函数
==============

:menuSelection:`函数 --> 创建自定义表格函数`

自定义表格函数让你可以使用提供的 :doc:`py_api` 执行任意用户计算，并把结果输出到 :doc:`表格视图 <table_window>` 中，而不是像更简单的 :doc:`custom_script` 函数那样以文本形式输出。这一强大的功能让你可以分析光学方案、执行自定义计算，并以结构化的表格形式呈现结果，非常适合比较多个元件或位置的值。

对于自定义函数，表格窗口会多出一条命令 :menuSelection:`表格 --> 显示代码` ，以及工具栏上一个带 Python 图标的相应按钮。该命令会打开代码编辑器窗口来修改脚本代码。这个窗口可以安全地关闭，因为代码实际保存在表格窗口中，而不是代码窗口中。但是，如果你关闭表格窗口本身，函数代码 *将会丢失* 。

代码模块
--------

自定义函数是一个用户定义的 Python 模块。模块文档字符串的第一行将用作人类可读的函数名，并显示在函数窗口的标题中。这样你可以给函数起一个有意义的标题。

``columns()``
~~~~~~~~~~~~~

代码模块必须提供一个 ``columns()`` 函数，用于定义表格列的结构和属性。该函数在每次重新计算之前调用，这让你可以动态改变表格结构（例如根据所选元件或参数改变列标题），而无需重新打开窗口。

.. code-block:: python

  def columns():
    return [
      {
        'label': 'W',
        'title': 'Beam radius',
        'dim': Z.DIM_LINEAR
      },
      {
        'label': 'Ratio',
        'title': 'Aperture ratio',
        'dim': Z.DIM_NONE
      }
    ]

每个列定义是一个字典，包含以下键：

- ``label`` - 计算值的简称；显示在列标题中，也用于从 ``calculate()`` 函数返回的结果字典中提取值
- ``title`` - 完整的描述性标题，显示在表格窗口的菜单中
- ``dim`` - 量纲类型（:ref:`Z.DIM_LINEAR <py_const_dim_linear>` 、:ref:`Z.DIM_ANGULAR <py_const_dim_angular>` 、:ref:`Z.DIM_NONE <py_const_dim_none>` ），用于为该列选择度量单位

``calculate()``
~~~~~~~~~~~~~~~

代码还必须包含一个 ``calculate()`` 函数，用于执行实际计算。对于表格函数，该函数会被多次调用——每个元件至少调用两次（分别针对 T 平面和 S 平面），并且根据表格窗口中选择的 :ref:`选项 <table_opers_calc_at_medium_ends>` ，同一个元件还可能被 :doc:`调用多次 <table_symbols>` 。

.. code-block:: python

  def calculate(elem, pos, rt):
    # Perform calculations for the given element and position
    if pos == POS_RIGHT:
      w = rt.beam_radius()
      return {'W': w}
    return None

该函数接收三个参数：

- ``elem`` - 当前正在处理的 :doc:`元件 <py_element>` 对象
- ``pos`` - 位置指示，可能的值有：

  - ``POS_LEFT`` - 元件左侧（之前）
  - ``POS_BEG`` - 元件内部起始处
  - ``POS_MID`` - 元件内部中间处
  - ``POS_END`` - 元件内部末端处
  - ``POS_RIGHT`` - 元件右侧（之后）

- ``rt`` - 当前位置预先计算好的 :doc:`往返 <py_round_trip>` 对象。:ref:`RoundTrip.plane <py_method_rt_plane>` 属性表示该函数针对哪个工作平面被调用。

该函数应返回：

- 一个字典，其键与 ``columns()`` 中定义的列标签相匹配；或
- ``None`` ，表示该元件/位置组合不显示数据

输出
~~~~

|rezonator| 中的所有计算都以 SI 单位（米、弧度等）执行。提供给脚本的所有参数值也都是 SI 单位。对于自定义表格函数，你也应该返回 SI 单位的计算值，无需任何换算。因为表格窗口内置了根据列的量纲类型（``dim`` 属性）选择和显示 :ref:`单位 <table_opers_units>` 的功能。

``calculate()`` 函数的结果会自动格式化并显示在 :doc:`table_window` 中。表格中的每一行对应一个元件或位置，每一列显示按你的 ``columns()`` 函数定义计算出的值。

如需简单的文本输出或调试，请改用 :doc:`custom_script` 。如需图形化可视化，请考虑 :doc:`custom_plot` 。

自定义代码库
------------

你可以使用 :menuSelection:`脚本 --> 保存到自定义库` 菜单命令把代码保存到 :ref:`自定义代码库 <custom_func_lib>` 以备后用。这样你可以建立一个可复用计算脚本的集合，用于常见任务。

自定义参数
----------

自定义参数是你可以为任何元件添加的任意参数，作为其预定义参数的补充。它们对自定义表格函数尤其有用，因为它们让你可以计算或跟踪元件默认参数未涵盖的属性。

你可以通过元件属性对话框为元件添加自定义参数，然后在计算中使用 :ref:`Element.param()<py_method_elem_param>` 方法访问它们。这为扩展元件以容纳项目特定数据或特定于你的自定义计算的属性提供了灵活性。

示例项目
--------

通过 :menuSelection:`文件 --> 打开示例` 打开完整可用的示例 ``custom_func_aper_ratio.rez`` 和 ``misalign.rez`` ，查看自定义表格函数的实际工作方式，并将其用作你自己计算的模板。在“打开示例”对话框中使用“custom table”筛选器可以查看该主题的可用示例。

.. seeAlso::

  - :doc:`py_api`
  - :doc:`table_window`
  - :doc:`custom_funcs`
  - :doc:`custom_script`
  - :doc:`custom_plot`
  - :ref:`示例 - 光阑比计算 <py_example_aper_ratio>`
