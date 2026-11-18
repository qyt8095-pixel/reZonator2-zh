.. _elem_props_options:

元件属性：选项
==============

:menuSelection:`元件 --> 属性 --> 选项`

  .. image:: img/elem_props_options.png

.. --------------------------------------------------------------------------

.. _elem_props_lock:

计算中忽略（禁用元件）
~~~~~~~~~~~~~~~~~~~~~~

设置该标志后，元件在往返计算中会被忽略，并且不会出现在函数参数选择列表中。看起来就像该元件被临时从方案中删除了。

  .. image:: img/elems_table_locked.png

此外，该标志也可以通过 :doc:`方案窗口 <schema_window>` 中的 :ref:`单独命令 <elem_toggle_lock>` 快速切换。

.. --------------------------------------------------------------------------

.. _elem_props_show_label:

在布局上显示元件标签
~~~~~~~~~~~~~~~~~~~~

该选项定义是否在 :doc:`布局 <layout>` 上显示元件标签。这是一个外观选项，可以让包含某些类型元件（例如 :ref:`界面 <ElemNormalInterface>` 或 :ref:`点 <ElemPoint>` ）的布局看起来更好。

例如，下面是“singlet_thick_intf”示例的布局，其中表示透镜表面的 :doc:`matrix/ElemSphericalInterface` 元件的标签被隐藏了：

  .. image:: img/layout_hide_labels.png

.. --------------------------------------------------------------------------

.. _elem_props_draw_narrow:

绘制元件的窄版
~~~~~~~~~~~~~~

某些元件类型，例如 :doc:`matrix/ElemEmptyRange` 或 :doc:`matrix/ElemTiltedInterface` ，可以在 :doc:`布局 <layout>` 上以更窄的形式表示。这是一个外观选项，可以让包含某些类型元件的布局看起来更好。

例如，下面是“z_crystal”示例的布局，其中 :param:`L3` 以窄版模式显示，这反映了它比 :param:`L2` 范围短得多的事实：

  .. image:: img/layout_narrow_elem.png

.. --------------------------------------------------------------------------

.. seeAlso::

    - :doc:`elem_props`
    - :ref:`元件属性：参数 <elem_props_params>`
    - :ref:`元件属性：轮廓 <elem_props_outline>`
