.. _elem_formula:
.. index:: single: formula (element)

公式元件
========

公式元件可用于设计任意光学元件，其光线矩阵由用户给定的 :ref:`Python <py_api>` 代码计算。

将公式元件添加到方案中后，使用 :doc:`../elem_opers_formula` 命令更改元件的代码。代码必须提供一个函数 ``calc_matrix`` ，返回一个元件矩阵字典。该字典应分别包含 Mt 和 Ms 项，对应子午矩阵和弧矢矩阵。当 |rezonator| 需要重新计算元件的光线矩阵时，会调用此函数，并传入目标元件的引用。代码可以查询元件的参数并在计算中使用它们。参数应创建为 :ref:`自定义参数 <custom_params>` 。

下面是一个表示薄透镜的简单公式元件示例。该元件与内置的 :ref:`薄透镜 <elem_thin_lens>` 元件作用相同，但允许改变透镜的光焦度，而不是其焦距。

.. code-block:: python

  from math import cos
  from rezonator import Element, Matrix

  def calc_matrix(elem: Element):
    P = elem.param('P', 1)
    a = elem.param('alpha', 0)
    return {
      'Mt': Matrix(1, 0, -P/cos(a), 1),
      'Ms': Matrix(1, 0, -P*cos(a), 1),
    }

当你 :ref:`复制 <elem_opers_copy>` 这样的元件或将其 :ref:`保存 <elem_opers_save_custom>` 到 :doc:`../elem_library` 时，公式代码和自定义参数也会被一同复制，从而得到一个可以独立更改而不影响原始元件的副本。

.. seeAlso::

    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - :doc:`../custom_params`
    - :doc:`../custom_funcs`
