.. _elem_library:

自定义元件库
============

:menuSelection:`工具 --> 自定义元件库`

  .. image:: img/elem_library.png

元件库包含元件预设。它们是具有预先指定参数值和属性的元件。自定义预设显示在 :doc:`catalog` 的“自定义库”选项卡中。可以像往常一样从那里把它们添加到方案中。预设的副本会被添加到方案中，所有参数值都会赋给目标元件。预设的标签用作新元件的 *标签前缀* （见 :ref:`elem_props_label` 、:ref:`app_settings_gen_labels_created` ）。

使用 :menuSelection:`添加` 按钮打开 :doc:`catalog` 并向库中添加预设。或者，你可以在方案窗口中使用 :ref:`elem_save_custom_lib` 命令从现有元件创建预设。此外，你还可以在库窗口中使用 :menuSelection:`复制` 命令，并在方案窗口中使用 :ref:`粘贴 <elem_opers_paste>` 命令。在这种情况下，它的作用与常规粘贴操作相同，预设标签不会用作标签前缀（见 :ref:`app_settings_gen_labels_pasted` ）。

使用工具栏上的 :menuSelection:`属性` 按钮更改预设参数。该更改不会影响已从该预设创建的元件。

使用工具栏上的 :menuSelection:`删除` 按钮从库和 :doc:`catalog` 中删除预设。这不会影响已从该预设创建的元件。

.. note::
  自定义库保存在本地用户配置文件中，因此不会影响同一系统中的其他用户。
