.. index:: single: input beam

输入光束
========

:menuSelection:`文件 --> 设置输入光束 (F9)`

:menuSelection:`窗口 --> 泵浦 --> 泵浦 --> 编辑 (Enter)`

该对话框用于设置 SP 方案的输入光束参数。输入光束也称为*泵浦* 。

当你把方案的 :doc:`往返类型 <trip_type>` 改为 SP 时，第一个泵浦会自动以 :ref:`束腰 <pump_mode_waist>` 类型创建。然后你可以使用 :doc:`泵浦窗口 <pumps_window>` 添加更多 :doc:`不同类型 <pump_mode>` 的输入光束，并在它们之间切换。|rezonator| 可以存储任意数量的输入光束；但一次只能计算其中一个，它被称为*活动泵浦* 。

该命令也会为活动泵浦调用，方法是双击状态栏中的泵浦类型图标。在泵浦窗口中，双击泵浦行时会显示该对话框。

  .. image:: img/setup_input_beam.png

.. seeAlso::

  - :doc:`pump_mode`
  - :doc:`pumps_window`
