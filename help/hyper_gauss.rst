超高斯光束的计算
================

.. |MI| replace:: `M`\ :sup:`2`
.. |z0| replace:: `z`\ :sub:`0`
.. |w0| replace:: `w`\ :sub:`0`

当输入光束的发散参数（|MI| ）设定为大于 1 的值时，应用超高斯光束计算算法来分析单程系统（SP）。

.. index:: single: hyper-gaussian beam
.. index:: single: pseudo-gaussian beam

超高斯光束
----------

|rezonator| 中的超高斯光束定义为发散度比具有相同束腰半径的高斯光束大 |MI| 倍的光束。因此其 :ref:`瑞利距离 <gauss_confocal>` 小 |MI| 倍。

	.. image:: img/hypergauss_formula_1.png

.. index:: single: equivalent gaussian beam

等效高斯光束
------------

为了描述超高斯光束在自由空间中的传播，只需在 `w(z)` 和 `R(z)` 的公式中把瑞利距离 |z0| 替换为 |z0|/|MI| ：

	.. image:: img/hypergauss_formula_2.png

这等价于把束腰尺寸从 |w0| 改为 |w0|/`M` ：

	.. image:: img/hypergauss_formula_3.png

具有这种缩小后的束腰尺寸的光束称为 *等效高斯光束* ：

	.. image:: img/hypergauss_formula_4.png

然后我们可以用等效高斯光束来表示超高斯光束的束腰半径：

	.. image:: img/hypergauss_formula_5.png

并将其代入 `w(z)` 和 `R(z)` 的公式：

	.. image:: img/hypergauss_formula_6.png

由于等效高斯光束与超高斯光束具有相同的瑞利距离，它的半径不仅在束腰处，而且在任何位置都比原始光束的半径小 `M` 倍。

	.. image:: img/hypergauss_formula_7.png

因为等效高斯光束是标准高斯光束，它的复参数可以像往常一样通过光线矩阵进行变换。

计算算法
--------

程序使用以下算法计算超高斯光束的传播：

#. 计算输入光束的等效尺寸。它比输入光束参数对话框中指定的尺寸小 `M` 倍。

#. 计算等效高斯光束的传播。

#. 计算所得超高斯光束的特性。它的半径比等效光束的半径大 `M` 倍，波前曲率半径与之相等。

	.. image:: ./img/hypergauss_algorithm.png

   
.. seealso::

    :doc:`gauss`
