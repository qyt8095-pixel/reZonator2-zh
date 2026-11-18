.. _elem_opers_split:
.. index:: single: split element (command)

拆分
====

:menuSelection:`元件 --> 拆分...`

该命令适用于任何具有长度参数的元件，例如 :ref:`elem_empty_range` 或 :ref:`elem_brewster_crystal` 。它允许把元件拆分为两个同类型元件，其总长度等于原元件的长度。实际上，只插入一个新元件，它分走原元件的一部分长度，原元件的长度则相应减少。

    .. image:: img/elem_opers_split_drawing.png

该命令是一种脚本，提供了一种方便而简单的方式，替代了使用 :doc:`elem_opers_append` 命令插入新元件并通过 :doc:`elem_opers_props` 命令调整新旧两个元件参数的做法。之后，两个元件可以独立编辑。或者，也可以使用 :doc:`elem_opers_slide` 命令同时更改两个元件。

    .. note::
        该命令会改变原元件的长度。因此，当长度不是直接可编辑的（因为它受 :ref:`全局参数 <params_window>` 控制）时，该命令无法执行。

该命令的参数对话框允许为新元件设置 :ref:`标签 <elem_props_label>` 。默认情况下，标签自动生成，但可以手动更改。如有需要，也可以更改原元件的标签。

源元件的长度按比例分配给原元件和新元件。可以通过移动滑块或手动编辑来改变比例。

标签编辑器之间有一个很小的双箭头按钮。该按钮决定新元件应放在原元件之前还是之后。默认情况下，新元件插入在原元件之后。点击该按钮可以交换两个元件。

如果勾选了“在程段之间插入点”选项，则会在原元件和新元件之间自动创建一个 :ref:`elem_point` 。点元件的标签会自动生成，也可以手动编辑。

    .. image:: img/elem_opers_split.png

.. seeAlso::

    - :doc:`elem_opers`
    - :doc:`elem_opers_insert_into`
    - :doc:`elem_opers_merge`
    - :doc:`elem_opers_slide`
