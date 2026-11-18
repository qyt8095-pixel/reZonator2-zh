.. _func_misalign:

.. |y_eff| replace:: `dy`\ :sub:`eff`
.. |V_eff| replace:: `dV`\ :sub:`eff`

失调
====

失调的计算依据 A.E. Siegman 的著作《Lasers》第 15.4 章“Ray optics with misaligned elements”。A. Gerrard 和 J. M. Burch 的《Introduction to Matrix Methods in Optics》附录 II 中也有相同的描述。

光学元件的 *失调* 是指它相对于系统理想光轴位移了一个小距离 `dy` ，并倾斜了一个小角度 `dV` 。

  .. image:: img/misalign.png

各个元件的失调通过 :ref:`自定义参数 <custom_params>` 设置。对于这个特定的脚本，假定这些参数在子午面内轴向和角度失调分别为 `dYt` 和 `dVt` ，在弧矢面内分别为 `dYs` 和 `dVs` ，因此在下面的公式中我们简称为 `dy` 和 `dV` 。

总体失调
--------

:ref:`失调 <misalign>` 的计算通过扩展的 3×3 ABCDEF 光线传输矩阵完成，其中附加的 `E` 和 `F` 元素分别表示元件的位移和倾斜。

  .. tex:
    \begin{bmatrix}
    A & B & E\\
    C & D & F\\
    0 & 0 & 1
    \end{bmatrix}
  .. image:: img/misalign_matrix_ex.png

其中，单个元件矩阵的 `E` 和 `F` 分量由元件的 ABCD 矩阵分量和失调参数 `dy` 和 `dV` 计算得出：

  .. image:: img/misalign_eq_12.png

然后，通过这些扩展矩阵的 :ref:`乘积 <round_trip>` 计算总体失调矢量 `E`\ :sub:`0` 和 `F`\ :sub:`0` ，它影响光束通过失调系统后的位移和斜率：

  .. image:: img/misalign_eq_16.png

如果不使用 3×3 矩阵，一组具有 ABCD 矩阵 `M`\ :sub:`1` … `M`\ :sub:`n` 和各自失调 [`E`\ :sub:`1` ，`F`\ :sub:`1`] … [`E`\ :sub:`n` ，`F`\ :sub:`n`] 的元件的总体失调可以表示为：

  .. image:: img/misalign_eq_17.png

单程系统的有效光轴
------------------

任何含有失调元件的系统都可以通过将整个系统从参考光轴向下平移距离 |y_eff| ，然后以输入面为旋转中心、向系统轴方向旋转角度 |V_eff| ，转换为等效对准的系统，旋转角度为

  .. image:: img/misalign_eq_18.png

其中 `L` 是系统总长度，`A` 、`B` 、`C` 、`D` 、`E` 、`F` 是整个系统的矩阵元素。

谐振腔的有效光轴
----------------

有效光轴的位置定义为某条光线在完整通过谐振腔（往返）后回到原点时的位移 |y_eff| 和斜率 |V_eff| （相对于系统的参考光轴）。换句话说，有效光轴的位置是一种自洽失调：

  .. image:: img/misalign_eq_20.png

其中 `A` 、`B` 、`C` 、`D` 、`E` 、`F` 是某个参考面处整个系统的矩阵元素。

.. seeAlso::

  - :doc:`py_api`
  - :doc:`custom_script`
  - :doc:`round_trip_matrix`
  - :doc:`misalign`
