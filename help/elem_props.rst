.. _elem_props:

元件属性
========

:menuSelection:`元件 --> 属性`

通用属性
--------

  .. image:: img/elem_props_common.png

.. _elem_props_label:

标签
~~~~

它是元件的标识符或标签。标签一般由几个字母组成，例如 `M1` 或 `L_foc` 。这就是元件在光学图纸上的常用标注方式。

如果相应的 :ref:`应用选项 <app_settings_gen_labels_created>` 允许，标签可以在创建元件时自动生成。每种 :ref:`元件类型 <elem_matrs>` 都有自己的标签前缀。标签由此外缀后跟一个递增序号组成。例如，距离元件的标签格式为 `L1` 、`L2`……，镜面的标签格式为 `M1` 、`M2`……。


.. _elem_props_title:

标题
~~~~

它是元件的名称或简短描述。例如“输出镜”。该字段完全是信息性的。


属性选项卡
----------

还有一组附加属性，随元件类型而变化。

.. tocTree::
  :maxDepth: 1

  elem_props_params
  elem_props_options
  elem_props_outline
  custom_params
