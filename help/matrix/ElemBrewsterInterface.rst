.. index:: single: brewster interface

布儒斯特界面
============

.. |n1| replace:: `n`\ :sub:`1`
.. |n2| replace:: `n`\ :sub:`2`

该元件表示折射率为 |n1| 和 |n2| 的两种介质之间的平面边界。认为光束以布儒斯特角入射到该边界。

    .. image:: ElemBrewsterInterface.png

.. warning::

    界面元件左右相邻的元件应为 :doc:`ElemEmptyRange` 或 :doc:`ElemMediaRange` 。如果不是，|rezonator| 不会报错，但你可能会得到不正确的结果。

.. seeAlso::

    - :doc:`ElemSphericalInterface`
    - :doc:`ElemNormalInterface`
    - :doc:`ElemTiltedInterface`
    - :doc:`../elem_matrs`
    - :doc:`../catalog`
    - :doc:`../elem_props`
    - `维基百科中的布儒斯特角 <http://en.wikipedia.org/wiki/Brewster's_angle>`_
