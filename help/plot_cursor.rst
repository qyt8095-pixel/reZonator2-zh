.. _cursor:
.. index:: single: cursor
.. index:: single: plot cursor

绘图光标
========

:menuSelection:`视图 --> 光标`

光标是一条或两条可由鼠标拖动的交叉线。光标面板显示光标交点的坐标，以及在光标所在点计算的函数值（T 面和 S 面）。显示值的精度由 :ref:`应用程序设置 <app_settings_format_precision>` 控制。

光标下的函数值是精确计算的，因此不是由图形中已有的点插值得到的。例外是 :ref:`冻结 <func_freeze>` 的函数，其中光标下的函数值由图形相邻点之间插值计算。

当你把绘图 :ref:`复制 <plot_opers_copy_image>` 为图像到剪贴板时，光标线可能是不需要的。除了手动开关它们之外，还有一个 :ref:`应用程序选项 <app_settings_export_hide_cursor>` 可以自动处理。

  .. image:: img/plot_cursor.png

类型
----

:menuSelection:`视图 --> 光标 --> 竖直线`

:menuSelection:`视图 --> 光标 --> 水平线`

:menuSelection:`视图 --> 光标 --> 两条线`

你可以使用光标面板左侧的 :menuSelection:`光标` 按钮快速切换光标的可见性。光标类型可以是竖直线、水平线或两条线。你可以在光标切换按钮下的下拉菜单中选择所需的类型。

  .. image:: img/plot_cursor_dropdown.png

定位
----

除了用鼠标拖动外，你还可以精确设置光标的位置。为此，双击光标面板中的 X 或 Y 坐标，在对话框中输入所需的值，然后按 Enter 键。

  .. image:: img/plot_cursor_set_pos.png

跟随鼠标
~~~~~~~~

:menuSelection:`视图 --> 光标 --> 跟随鼠标 (F7)`

除了菜单选项外，光标面板右侧还有相应的按钮。启用该选项后，光标会立即跟随鼠标移动，函数值也会立即重新计算。双击可停止跟随。

外观
----

:menuSelection:`格式 --> 光标线格式...`

光标线的默认外观由 :ref:`程序首选项 <app_settings_lines>` 控制。它应用于所有新打开的绘图窗口，以及那些未覆盖光标格式的窗口。默认外观可以通过该菜单命令覆盖，并保存在方案项目文件中。

.. seeAlso::

  - :doc:`plot_window`
