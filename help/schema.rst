.. index:: single: schema

******
光路图
******

在 |rezonator| 的术语中，所研究的光学系统被称为*光路图（schema）*。光路图由若干光学元件、它们之间的区间以及一些辅助对象组成。它们都被称为 :doc:`元件 <elements>`。

光路图保存在扩展名为 ``.REZ`` 的文件中。

你可以计算高斯光束在开放光学系统和稳定谐振腔中的传播。在当前版本中，|rezonator| 只能计算平面光学系统。“平面”是指光轴的所有转折（反射、折射）都发生在同一个平面内。这个平面被称为 :ref:`子午平面 <working_planes>`。

在 |rezonator| 中，开放光学系统被称为*单程系统（SP）*。例如望远镜、显微镜、扩束器等。你需要设置输入光束，软件可以计算该光束如何通过光路图的所有元件传播。

  .. image:: img/sketch_sp.png

谐振腔可以是*驻波谐振腔（SW）*或*环形谐振腔（RR）*。借助该软件，你可以构想出哪些元件参数值能使谐振腔进入稳定工作状态，以及自洽高斯光束在谐振腔内具有哪些特性。

  .. image:: img/sketch_sw_rr.png

你可以随时通过 :doc:`往返类型对话框 <trip_type>` 更改光路图类型。项目窗口的状态栏会显示一个表示所选光路图类型的图标。该图标在下面的截图中标记为 :GUIPart:`1`。

每次修改任何光路图属性或元件参数时，|rezonator| 都会计算稳定性参数的值（针对 SW 和 RR）。当光路图稳定性被破坏时，稳定性图标（在下面的截图中标记为 :GUIPart:`2`）会以红色突出显示。不支持对不稳定谐振腔进行光束特性计算。

  .. image:: img/status_bar_1.png

.. tocTree::
   :maxDepth: 1
   :caption: 目录：

   schema_window
   pumps_window
   params_window
   memo_window
   trip_type
   input_beam
   pump_mode
   wavelen
