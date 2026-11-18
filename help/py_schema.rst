.. index:: single: schema (Python API)

模块：schema
============

``schema`` 模块提供用于访问和操作当前光学方案的函数。

函数
----

.. #######################################################################

.. index:: single: elem (Python API)
.. _py_method_schema_elem:

``elem(identifier)``
~~~~~~~~~~~~~~~~~~~~

按标签或索引获取元件。

参数：

- ``identifier`` - 元件标签（str）或从 1 开始的索引（int）。与常规 Python 列表不同，方案中的元件从 1 开始索引，以与它们在 :doc:`元件列表 <schema_elems>` 中的编号一致。

返回值：

- :doc:`Element <py_element>` - 请求的元件

异常：

- ``KeyError`` - 如果找不到给定标签的元件
- ``IndexError`` - 如果找不到给定索引的元件
- ``TypeError`` - 如果标识符既不是字符串也不是整数

示例：

.. code-block:: python

    import schema

    # Get element by label
    elem1 = schema.elem('Cr')

    # Get element by 1-based index
    elem2 = schema.elem(2)

.. #######################################################################

.. index:: single: elem_count (Python)

``elem_count()``
~~~~~~~~~~~~~~~~

获取方案中元件的总数。

返回值：

- int - 元件数量

示例：

.. code-block:: python

    import schema
    count = schema.elem_count()
    for i in range(count):
        elem = schema.elem(i+1)  # Elements are 1-based
        # Process element...

.. #######################################################################

.. index:: single: wavelength (Python)

``wavelength()``
~~~~~~~~~~~~~~~~

获取当前的 :doc:`波长 <wavelen>` 。

返回值：

- float - 以米为单位的波长

示例：

.. code-block:: python

    import schema
    wl = schema.wavelength()
    print(f'Wavelength: {wl*1e9} nm')

.. #######################################################################

.. index:: single: param (Python)

``param(label)``
~~~~~~~~~~~~~~~~

按标签获取 :doc:`全局参数 <params_window>` 的值。

参数：

- ``label`` (str) - 参数标签

返回值：

- float - 以 SI 单位表示的参数值，如果未找到则为 None

示例：

.. code-block:: python

    import schema
    p1_value = schema.param('P1')

.. #######################################################################

.. index:: single: set_param (Python)

``set_param(label, value)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

按标签设置 :doc:`全局参数 <params_window>` 的值。

参数：

- ``label`` (str) - 参数标签
- ``value`` (float) - 以 SI 单位表示的参数值

异常：

- ``KeyError`` - 如果找不到参数
- ``ValueError`` - 如果值无效

示例：

.. code-block:: python

    import schema
    schema.set_param('P1', 10e-3)


.. #######################################################################

.. index:: single: lock_param (Python)
.. _py_method_schema_lock_param:

``lock_param(label)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

锁定直接或间接依赖于 :doc:`全局参数 <params_window>` 的元件。

参数：

- ``label`` (str) - 参数标签

异常：

- ``KeyError`` - 如果找不到参数

.. #######################################################################

.. index:: single: unlock_param (Python)
.. _py_method_schema_unlock_param:

``unlock_param(label)``
~~~~~~~~~~~~~~~~~~~~~~~

解锁之前由 :ref:`lock_param <py_method_schema_lock_param>` 方法锁定的元件。

参数：

- ``label`` (str) - 参数标签

异常：

- ``KeyError`` - 如果找不到参数

.. note::

  在进行临时参数更改时（例如，在 :doc:`绘图函数 <custom_plot>` 计算期间），请使用 ``schema.lock_param()`` 和 ``schema.unlock_param()`` 方法，以确保正确恢复，并防止 UI 进行不必要的更新。UI 更新过于频繁时会显著拖慢应用程序。

示例：

.. code-block:: python

    import schema
    schema.lock_param('P1')
    try:
      # Make temporary changes:
      for i in range(num_points):
        schema.set_param('P1', i)
        # Calculate something...
    finally:
      # Restore original values
      schema.unlock_param('P1')

.. #######################################################################

.. index:: single: param_ref (Python)
.. _py_method_schema_param_ref:

``param_ref(label)``
~~~~~~~~~~~~~~~~~~~~

创建 :doc:`ParamRef <py_param_ref>` 对象，以便在绘图函数中更方便地实现锁定-解锁模式。

参数：

- ``label`` (str) - 参数标签

异常：

- ``KeyError`` - 如果找不到参数

示例：

.. code-block:: python

    import schema
    with schema.param_ref('P1') as p:
      # Make temporary changes:
      for i in range(num_points):
        p.set_value(i)
        # Calculate something...
    #  Original value is automatically restored

.. #######################################################################

.. index:: single: is_sp (Python)
.. index:: single: is_sw (Python)
.. index:: single: is_rr (Python)

``is_sp()``, ``is_sw()``, ``is_rr()``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

检查方案的 :doc:`类型 <trip_type>` 。

返回值：

- bool - 如果方案是相应类型，则为 True

示例：

.. code-block:: python

    import schema
    if schema.is_sp():
        print('Single-pass system')
    elif schema.is_sw():
        print('Standing wave resonator')
    elif schema.is_rr():
        print('Ring resonator')

.. #######################################################################

.. index:: single: round_trip (Python)
.. _py_method_schema_round_trip:

``round_trip(ref=None, plane='T', inside=False)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

创建用于光束参数的 :ref:`往返 <round_trip>` 计算器。

参数：

- ``ref`` - 参考元件（:doc:`Element <py_element>` 、str 标签、int 索引，或 None 表示最后一个元件）
- ``plane`` - :ref:`工作平面 <work_plane>` （'T'、'S'、:ref:`Z.PLANE_T <py_const_plane_t>` 或 :ref:`Z.PLANE_S <py_const_plane_s>` ）
- ``inside`` (bool) - 如果为 True，在参考点处 :ref:`拆分有长度的元件 <calc_round_trip_subrange>`

返回值：

- :doc:`RoundTrip <py_round_trip>` - 往返计算器对象

异常：

- ``KeyError`` - 如果找不到参考元件
- ``ValueError`` - 如果平面名称或元件引用无效

示例：

.. code-block:: python

    import rezonator as Z
    import schema
    # Create round trip for element 'M2' in tangential plane
    rt_t = schema.round_trip(ref='M2', plane='T')
    # Create round trip with element split at midpoint
    elem = schema.elem(4)
    elem.offset = elem.axial_length / 2
    rt = schema.round_trip(ref=elem, inside=True, plane=Z.PLANE_T)

.. #######################################################################

.. seeAlso::

  - :doc:`py_api`
  - :doc:`py_global`
  - :ref:`示例——基本方案访问 <py_example_basic_schema_access>`
  - :ref:`示例——基本元件操作 <py_example_basic_elem_manipulation>`
