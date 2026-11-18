.. index:: single: RoundTrip (Python)

类：RoundTrip
=============

:ref:`往返 <round_trip>` 计算器，用于计算光束参数和稳定性。

.. note::

  RoundTrip 对象不能直接创建；请使用 :ref:`schema.round_trip() <py_method_schema_round_trip>` 函数获取它们。

属性
----

``ref`` (:doc:`元件 <py_element>`, 只读)
    往返的参考元件

.. _py_method_rt_plane:

``plane`` (int, 只读)
    :ref:`工作平面 <work_plane>` （:ref:`Z.PLANE_T <py_const_plane_t>` 或 :ref:`Z.PLANE_S <py_const_plane_t>` ）

``ior`` (float, 只读)
    当前折射率。折射率根据参考元件是什么自动指定。例如，如果元件是 :ref:`界面 <ElemNormalInterface>` ，则 IOR 将取自紧跟在该界面之后的 :ref:`介质 <ElemMediumRange>` 元件。

``matrix_count`` (int, 只读)
    往返中的矩阵数量

``stabil_nor`` (float, 只读)
    :ref:`稳定参数 <stability_param>` （常规模式）：`P = (A + D)/2`

``stabil_sqr`` (float, 只读)
    :ref:`稳定参数 <stability_param>` （平方模式）：`P = 1 - ((A + D)/2)²`

方法
----

.. ##################################################################

.. index:: single: matrix (Python)
.. _py_method_rt_matrix:

``matrix(index=None)``
~~~~~~~~~~~~~~~~~~~~~~

计算并返回参考点处的往返矩阵。

参数：

- ``index`` (int, 可选) - 矩阵索引，或 None 表示总往返矩阵

返回：

- :doc:`矩阵 <py_matrix>` - 请求的矩阵

抛出：

- ``IndexError`` - 如果索引无效

.. ##################################################################

.. index:: single: beam_radius (Python)
.. _py_method_rt_beam_radius:

``beam_radius()``
~~~~~~~~~~~~~~~~~

计算参考点处的往返矩阵，并返回根据矩阵分量计算出的 :ref:`光束半径 <abcd_beam_size>` 。

返回：

- float - 光束半径，单位为米

.. ##################################################################

.. index:: single: front_radius (Python)
.. _py_method_rt_front_radius:

``front_radius()``
~~~~~~~~~~~~~~~~~~

计算参考点处的往返矩阵，并返回根据矩阵分量计算出的 :ref:`波前曲率半径 <abcd_beam_roc>` 。

返回：

- float - 波前曲率半径，单位为米

.. ##################################################################

.. index:: single: half_angle (Python)
.. _py_method_rt_half_angle:

``half_angle()``
~~~~~~~~~~~~~~~~

计算参考点处的往返矩阵，并返回根据矩阵分量计算出的 :ref:`远场发散角的一半 <abcd_beam_angle>` 。


返回：

- float - 半角，单位为弧度

.. ##################################################################

.. index:: single: beam (Python)
.. _py_method_rt_beam:

``beam()``
~~~~~~~~~~

计算参考点处的往返矩阵，并返回根据矩阵分量计算出的 :ref:`全部光束属性 <abcd_beam>` 。

返回：

- tuple(float, float, float) - (beam_radius, front_radius, half_angle)，单位为 m、m、rad

.. ##################################################################

.. note::

  :ref:`往返矩阵 <round_trip>` 的计算在每次光束属性计算（例如 ``beam_radius()`` ）之前自动执行。这保证了元件的实际参数会被考虑在内。对于同一属性的多次查询，请把结果存入局部变量，而不是重新计算。

.. ##################################################################

.. index:: single: elem (Python)
.. _py_method_rt_elem:

``elem(index)``
~~~~~~~~~~~~~~~

获取拥有指定矩阵的元件。

参数：

- ``index`` (int) - 矩阵索引

返回：

- :doc:`元件 <py_element>` - 拥有该矩阵的元件

抛出：

- ``IndexError`` - 如果索引无效

.. ##################################################################

示例
----

.. code-block:: python

    import rezonator as Z
    import schema

    def calculate():
        ref_elem = schema.elem(4)

        # Set offset inside element
        if ref_elem.length is not None:
            ref_elem.offset = ref_elem.length / 2.0

        # Create round trip calculators for both planes
        rt_t = schema.round_trip(ref=ref_elem, inside=True, plane=Z.PLANE_T)
        rt_s = schema.round_trip(ref=ref_elem, inside=True, plane=Z.PLANE_S)

        # Get matrices
        Z.print('Tangential matrix:', rt_t.matrix())
        Z.print('Sagittal matrix:', rt_s.matrix())

        # Get stability parameters
        Z.print('Stability (T, normal):', rt_t.stabil_nor)
        Z.print('Stability (S, normal):', rt_s.stabil_nor)
        Z.print('Stability (T, squared):', rt_t.stabil_sqr)
        Z.print('Stability (S, squared):', rt_s.stabil_sqr)

        # Get beam parameters
        w_t = rt_t.beam_radius()
        w_s = rt_s.beam_radius()
        Z.print(f'Beam size: {w_t*1e3:.3f} × {w_s*1e3:.3f} mm')

.. seeAlso::

  - :doc:`py_api`
  - :doc:`py_element`
  - :doc:`py_matrix`
  - :ref:`示例 - 往返与光束属性 <py_example_round_trip>`
  - :ref:`示例 - 自定义焦散线函数 <py_example_custom_caustic>`
