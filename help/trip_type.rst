.. _trip_type:
.. index:: single: round-trip type

往返类型
========

:menuSelection:`文件 --> 更改往返类型`

往返类型定义了元件矩阵 :ref:`相乘 <round_trip>` 的顺序。该命令用于更改方案的往返类型。也可以通过双击状态栏中的往返类型图标来调用该命令。

  .. image:: img/round_trip_dlg.png

.. --------------------------------------------------------------------------

.. _schema_kind_sw:
.. index:: single: standing wave system
.. index:: single: SW

SW，驻波系统
------------

元件矩阵的乘积按系统双程（往返）计算；光束两次通过每个元件（边界元件除外）。

  .. image:: img/round_trip_sw.png

.. --------------------------------------------------------------------------

.. _schema_kind_rr:
.. index:: single: ring resonator
.. index:: single: RR

RR，环形谐振腔
--------------

光束一次通过每个元件。在通过最后一个元件（最右侧）后，光束会再次进入第一个元件（最左侧）。

  .. image:: img/round_trip_rr.png

.. --------------------------------------------------------------------------

.. _schema_kind_sp:
.. index:: single: single-pass system
.. index:: single: SP

SP，单程系统
------------

在这种情况下，光束进入方案的第一个元件（最左侧），并从最后一个元件（最右侧）射出。

  .. image:: img/round_trip_sp.png

要设置输入光束参数，可以使用 :doc:`设置输入光束 <input_beam>` 命令。

.. --------------------------------------------------------------------------

.. seeAlso::

  - :doc:`round_trip_matrix`
  - :doc:`wavelen`
