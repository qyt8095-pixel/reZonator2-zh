.. index:: single: tilted interface

倾斜界面
========

.. |n1| replace:: `n`\ :sub:`1`
.. |n2| replace:: `n`\ :sub:`2`

该元件表示折射率为 |n1| 和 |n2| 的两种介质之间的平面边界。光束的入射角通过元件的参数 `α` 设定。

    .. image:: ElemTiltedInterface_1.png

有时将 |n2| 介质内的角度设定为 `β` 角而不是 `α` 角会更方便。但该元件没有额外的 `β` 参数，因为这会导致应以哪个角为准的歧义。取而代之，你可以给角度加上负号，这会迫使 |rezonator| 把该角度当作 |n2| 介质内的角度，并据此计算第一个角。

    .. image:: ElemTiltedInterface_2.png

.. warning::

    界面元件左右相邻的元件应为 :doc:`ElemEmptyRange` 或 :doc:`ElemMediaRange` 。如果不是，|rezonator| 不会报错，但你可能会得到不正确的结果。

.. seeAlso::

    - :doc:`ElemSphericalInterface`
    - :doc:`ElemBrewsterInterface`
    - :doc:`ElemNormalInterface`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
