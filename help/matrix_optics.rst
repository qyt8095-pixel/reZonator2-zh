.. index:: single: matrix optics

谐振腔中光束参数的计算
======================

描述依据 A.E. Siegman 的著作 "Lasers"，见第 21 章 "Generalized paraxial resonator theory"。

为了进行分析，我们需要选择一个参考平面来计算 :doc:`往返矩阵 <round_trip_matrix>` 。一般来说，作为某个函数的参数而选定的元件就是参考平面。

.. _self_conformed_beam:

有了往返矩阵，我们可以写出 :ref:`复参数 <gauss_complex_param>` 变换的表达式：

    .. image:: img/gauss_q_abcd.png

由于我们考虑的是稳定谐振腔，输出参数与输入参数相同，因此光束是自洽的，在通过谐振腔完成一次完整往返后会自我再现：

    .. image:: img/abcd_q_in_out.png

|para|

    .. image:: img/abcd_q.png

然后，我们可以将复参数求解为二次方程的解：

    .. image:: img/abcd_q_quadratic.png


但为方便起见，最好将该方程改写为关于复参数倒数的形式：

    .. image:: img/abcd_q_quadratic_1.png


利用关系式

    .. image:: img/abcd_ad_bc.png

自洽复曲率半径
--------------

该方程的解给出了谐振腔中自洽厄米-高斯模式的复参数值：

    .. image:: img/abcd_solution.png

或

    .. image:: img/abcd_solution_1.png


其中一个解给出的情形是不真实的，即光束能量随径向距离增大而增大。

已知复参数通过光束特性表示的表达式

    .. image:: img/gauss_q.png

我们可以计算谐振腔中自洽光束的光束半径和波前曲率半径：

    .. image:: img/gauss_q_r_w.png

.. ##################################################################

.. _abcd_beam:

用矩阵分量表示的光束特性
------------------------

.. _abcd_beam_roc:

自洽光束的波前曲率半径：

    .. image:: img/abcd_curvature.png

.. _abcd_beam_size:

自洽光束半径：

    .. image:: img/abcd_radius_1.png

|para|

    .. image:: img/abcd_radius_2.png

|para|

    .. image:: img/abcd_radius_3.png

.. _abcd_beam_angle:

远场区半发散角：

    .. tex:
        V_S^2 = \cfrac{\lambda}{\pi} \cfrac{2 C}{\sqrt{4 - (A + D)^2}}

    .. image:: img/abcd_angle.png

这些公式仅供参考。当矩阵分量为复数时，它们并不适用，因此应用程序实际上并不使用它们，而是直接根据自洽的 `q` 参数计算光束特性。

.. seeAlso::

    - :doc:`gauss`
