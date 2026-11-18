.. _ElemMediumRange:
.. _elem_medium_range:

充满介质的空间
==============

该元件是折射率为 `n` 的介质中两个参考面之间的距离。该元件与 :doc:`ElemEmptyRange` 具有相同的矩阵，但折射率会影响介质中的光束半径。

与 :doc:`ElemPlate` 不同，该元件不包含任何界面。要得到正确的结果，你应在介质两侧放置适当的界面元件。

    .. image:: ElemMediaRange.png

.. seeAlso::

    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
