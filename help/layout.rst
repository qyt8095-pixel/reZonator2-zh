.. _layout:

布局
====

方案布局是方案在线性视图中自动形成的示意图，即忽略光轴的所有弯折，将元件显示在一条线上。

下面是“z_crystal”示例的布局。它展示了 Z 形谐振腔如何展开为线性视图：

  .. image:: img/layout.png

每种元件类型在布局中都有自己的表示形式。注意，如果球面镜没有放在方案的端部，会显示为透镜。如果光束以一定角度入射到镜面或透镜上，相应的元件会在布局中倾斜显示，以表示该系统是像散的。

  .. note:: 与 :doc:`schema_elems` 不同，:ref:`禁用 <elem_props_lock>` 的元件不会显示在布局上。

功能
----

交互性
~~~~~~

布局是可交互的。你可以点击元件来选中它。按住 :menuSelection:`Ctrl` 键可以选择多个元件。选择与 :doc:`schema_elems` 中的选择同步。当在布局上选中元件时，上下文菜单中包含针对元件的 :ref:`一些命令 <elem_opers>` 。当你点击空白处时，上下文菜单中会出现 :menuSelection:`复制图像` 命令。它将布局内容作为图像复制到剪贴板。

可选标签
~~~~~~~~

元件 :ref:`标签 <elem_props_label>` 显示在元件上方。为了获得更好的视图，你可以使用相应的 :ref:`元件选项 <elem_props_show_label>` 隐藏一些标签。

  .. image:: img/layout_hide_labels.png

窄视图
~~~~~~

元件长度在布局上不按比例显示。它们都具有固定长度。为了获得更好的视图，某些元件类型，如 :doc:`matrix/ElemEmptyRange` 或 :doc:`matrix/ElemTiltedInterface` ，可以采用更窄的表示形式。这可以通过另一个 :ref:`元件选项 <elem_props_draw_narrow>` 启用。

  .. image:: img/layout_narrow_elem.png

.. seeAlso::

  - :doc:`schema_elems`
