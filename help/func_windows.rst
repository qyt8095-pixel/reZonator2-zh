.. _func_windows:

****************
函数窗口
****************

.. tocTree::
   :maxDepth: 1

   plot_window
   plot_opers
   plot_cursor
   table_window
   table_opers
   table_symbols
   info_window
   func_freeze

任何 :ref:`函数 <functions>` 的计算结果都显示在所谓的函数窗口中。所有函数及其窗口根据所得结果的视图分为几种类型。函数类型包括 :ref:`绘图 <plot_window>`、:ref:`表格 <table_window>` 和 :ref:`信息 <info_window>`。

.. TODO: 例外是“冻结”函数，其数据保存在光路图文件中。你可以使用专门的程序首选项来禁用将函数窗口保存到光路图文件中，或禁用在加载光路图文件时恢复它们。

所有已打开函数窗口的列表及其设置都保存在光路图项目文件中，但计算结果不保存。已保存的函数窗口在加载光路图文件时会被恢复，函数会重新计算。因此，已保存的函数并不包含真实数据，而只包含获得这些数据的函数的引用。

  .. image:: img/func_windows.png
