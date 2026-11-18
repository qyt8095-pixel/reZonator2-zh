.. index:: single: Element (Python)

类：Element
===========

表示光路图中的光学 :doc:`元件 <elements>` 。

.. note::

  Element 对象不能直接创建；请使用 :ref:`schema.elem() <py_method_schema_elem>` 函数来获取它们。

属性
----

``label`` (str, 只读)
  元件的 :ref:`标签 <elem_props_label>` 。

``index`` (int, 只读)
  元件在光路图中的 1 起始索引（未找到时为 None）。与常规 Python 列表不同，光路图中的元件从 1 开始编号，以与它们在 :doc:`schema_elems` 中的编号方式保持一致。

``length`` (float, 只读)
    以米为单位的长度参数（元件没有长度时为 None）。

``axial_length`` (float, 只读)
    以米为单位的 :ref:`轴向长度 <axial_length>` （元件没有长度时为 None）。

``optical_path`` (float, 只读)
    以米为单位的光程（元件没有长度时为 None）。

``ior`` (float, 只读)
    折射率（不适用时为 None）。

``offset`` (float, 可读/写)
    元件内部以米为单位的偏移量（元件没有长度时为 None）。当往返以 ``inside=True`` :ref:`计算 <calc_round_trip_subrange>` 时，偏移量值用于具有长度的元件。参见 :ref:`schema.round_trip() <py_method_schema_round_trip>` 。

``prev`` (Element, 只读)
    遵循 :ref:`往返 <round_trip>` 规则的前一个元件。该属性还会忽略 :ref:`禁用 <elem_props_lock>` 的元件，因为它们不参与往返。

``next`` (Element, 只读)
    遵循 :ref:`往返 <round_trip>` 规则的下一个元件。该属性还会忽略 :ref:`禁用 <elem_props_lock>` 的元件，因为它们不参与往返。

``disabled`` (bool, 只读)
    元件是否 :ref:`禁用 <elem_props_lock>` 。

.. #######################################################################

方法
----

.. index:: single: param (Python)
.. _py_method_elem_param:

``param(label, default=None)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

按标签获取元件参数值。此方法可访问元件的预定义参数和 :ref:`自定义 <custom_params>` 参数。

参数：

- ``label`` (str) - 参数标签
- ``default`` (float, optional) - 未找到参数时的默认值

返回值：

- float - 以 SI 单位表示的参数值，未找到时为 None/默认值

示例：

.. code-block:: python

    elem = schema.elem('F1')
    f = elem.param('F')  # Get focal length
    r = elem.param('dYt', 0.0)  # Get axial misalignment, default to 0 if not found

.. #######################################################################

.. index:: single: set_param (Python)
.. _py_method_elem_set_param:

``set_param(label, value)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~

按标签设置元件参数值。

参数：

- ``label`` (str) - 参数标签
- ``value`` (float) - 以 SI 单位表示的参数值

引发：

- ``KeyError`` - 未找到参数时
- ``ValueError`` - 值无效时

示例：

.. code-block:: python

    elem = schema.elem('L1')
    elem.set_param('F', 0.1)  # Set focal length to 100 mm

.. #######################################################################

.. index:: single: matrix (Python)
.. _py_method_elem_matrix:

``matrix(plane)``
~~~~~~~~~~~~~~~~~

返回元件在给定平面内的矩阵；如果未提供参数，则返回 T 平面内的矩阵。

参数：

- ``plane`` - :ref:`工作平面 <work_plane>` ('T', 'S', :ref:`Z.PLANE_T <py_const_plane_t>`, or :ref:`Z.PLANE_S <py_const_plane_s>`)

引发：

- ``ValueError`` - 平面名称无效时


.. #######################################################################

.. index:: single: lock (Python)
.. _py_method_elem_lock:

``lock()``
~~~~~~~~~~

禁用元件事件并备份参数值。用于进行临时更改时。

.. #######################################################################

.. index:: single: unlock (Python)
.. _py_method_elem_unlock:

``unlock()``
~~~~~~~~~~~~

启用元件事件并恢复备份的参数值。

.. note::

  在进行临时参数更改时（例如在 :doc:`绘图函数 <custom_plot>` 计算期间），请使用 ``Element.lock()`` 和 ``Element.unlock()`` 方法，以确保正确恢复，并防止界面进行不必要的更新。界面更新过于频繁时会显著降低应用程序的速度。

示例：

.. code-block:: python

  elem = schema.elem('Cr')
  elem.lock()
  try:
    # Make temporary changes:
    elem.length = elem.length * 1.1

    # Calculate something...
  finally:
    # Restore original values
    elem.unlock()

.. #######################################################################

.. index:: single: param_ref (Python)
.. _py_method_elem_param_ref:

``param_ref(label)``
~~~~~~~~~~~~~~~~~~~~

创建一个 :doc:`ParamRef <py_param_ref>` 对象，以便在绘图函数中更方便地实现锁定-解锁模式。

参数：

- ``label`` (str) - 参数标签

引发：

- ``KeyError`` - 未找到参数时

示例：

.. code-block:: python

    elem = schema.elem('Cr')
    with elem.param_ref('L') as p:
      # Make temporary changes:
      for i in range(num_points):
        p.set_value(i)

        # Calculate something...

    #  Original value is automatically restored


.. seeAlso::

  - :doc:`py_api`
  - :doc:`elem_props`
  - :ref:`示例 - 基本元件操作 <py_example_basic_elem_manipulation>`
