.. _round_trip:
.. index:: single: calculation of round-trip matrix
.. index:: single: matrix of round-trip
.. index:: single: round-trip

往返矩阵的计算
==============

:doc:`光线矩阵 <elem_matrs>` 形式体系假定元件矩阵沿与光束 :ref:`传播方向 <propagation_dir>` 相反的方向逐个相乘。

一般元件
--------

每个元件由一对光线矩阵表征。一个矩阵对应切向（T）平面，另一个对应弧矢（S）平面。两个平面的往返矩阵分别计算。



.. _calc_round_trip_sw:

SW，驻波系统
^^^^^^^^^^^^^

如果方案是 :ref:`驻波谐振腔 <schema_kind_sw>` ，则元件矩阵按以下方式相乘：

- 从参考元件到方案的第一个元件，

- 从第一个元件到最后一个元件，

- 从最后一个元件到参考元件旁边的元件。

|para|

    .. image:: img/round_trip_sw_1.png

示例结果（M4 是参考元件）：

    M0 = M4 × M3 × M2 × M1 × M2 × M3 × M4 × M5 × M6 × M7 × M6 × M5



.. _calc_round_trip_rr:

RR，环形谐振腔
^^^^^^^^^^^^^^^

如果方案是 :ref:`环形谐振腔 <schema_kind_rr>` ，则元件矩阵按以下方式相乘：

- 从参考元件到方案的第一个元件，

- 从最后一个元件到参考元件旁边的元件。

|para|

    .. image:: img/round_trip_rr_1.png

示例结果（M4 是参考元件）：

    M0 = M4 × M3 × M2 × M1 × M7 × M6 × M5



.. _calc_round_trip_sp:

SP，单程系统
^^^^^^^^^^^^^

如果方案是 :ref:`单程系统 <schema_kind_sp>` ，则光线从第一个元件传到最后一个元件。因此，矩阵按相反顺序相乘（从最后一个元件到第一个元件）。

    .. image:: img/round_trip_sp_1.png

示例结果（M4 是参考元件）：

    M0 = M4 × M3 × M2 × M1


.. _calc_round_trip_subrange:

有长度的元件
------------

.. |M4_1| replace::  M4\ :sub:`1`
.. |M4_2| replace::  M4\ :sub:`2`

某些函数可以沿元件长度分析元件，例如 :ref:`焦散线 <func_caustic>` 函数。被分析的参考元件在这种函数中被分成两个子元件。第一个子元件是原元件从左边缘到当前点（例如计算光束半径的点）的部分。第二个子元件是原元件从当前点到右边缘的部分。每个子元件由其光线矩阵对表征。



.. _calc_round_trip_sw_1:

SW，驻波系统
^^^^^^^^^^^^^

如果方案是 :ref:`驻波谐振腔 <schema_kind_sw>` ，则元件矩阵按以下方式相乘：

- 从左参考子元件到方案的第一个元件，

- 从第一个元件到最后一个元件（在这一步中参考元件按整体计入），

- 从最后一个元件到右参考子元件。

|para|

    .. image:: img/round_trip_sw_2.png

示例结果（M4 是参考元件）：

	M0 = |M4_1| × M3 × M2 × M1 × M2 × M3 × M4 × M5 × M6 × M7 × M6 × M5 × |M4_2|



.. _calc_round_trip_rr_1:

RR，环形谐振腔
^^^^^^^^^^^^^^^

如果方案是 :ref:`环形谐振腔 <schema_kind_rr>` ，则元件矩阵按以下方式相乘：

- 从左参考元件到方案的第一个元件，

- 从该元件到右参考子元件。

|para|

    .. image:: img/round_trip_rr_2.png

示例结果（M4 是参考元件）：

    M0 = |M4_1| × M3 × M2 × M1 × M7 × M6 × M5 × |M4_2|



.. _calc_round_trip_sp_1:

SP，单程系统
^^^^^^^^^^^^^

如果方案是 :ref:`单程系统 <schema_kind_sp>` ，则从左参考子元件到第一个元件的矩阵相乘。

    .. image:: img/round_trip_sp_2.png

示例结果（M4 是参考元件）：

    M0 = |M4_1| × M3 × M2 × M1


|para|

.. seeAlso::

    - :doc:`elem_matrs`
