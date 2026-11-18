.. _misalign:

失调计算
========

.. |r1| replace:: `r`\ :sub:`1`
.. |r2| replace:: `r`\ :sub:`2`
.. |e1| replace:: `e`\ :sub:`1`
.. |e2| replace:: `e`\ :sub:`2`
.. |m1| replace:: `m`\ :sub:`1`
.. |m2| replace:: `m`\ :sub:`2`
.. |dy1| replace:: `dy`\ :sub:`1`
.. |y_eff| replace:: `dy`\ :sub:`eff`
.. |V_eff| replace:: `dV`\ :sub:`eff`

假设有一个元件，其光轴相对于光学系统光轴（参考光轴）偏移了 |dy1| ，并旋转了 `dV` 。我们关心这种位移和旋转（失调）如何影响通过该元件或一组元件的光线。我们相对于参考光轴来测量光线。

  .. image:: img/misalign_calc.png

ABCDEF 光线矩阵的推导
---------------------

引入以下符号。

相对于参考光轴的输入（|r1| ）和输出（|r2| ）光线矢量：

  .. tex:
    r_1 = \begin{bmatrix} y_{1R} \\ V_{1R} \end{bmatrix}
    \qquad
    r_2 = \begin{bmatrix} y_{2R} \\ V_{2R} \end{bmatrix}
  .. image:: img/misalign_eq_01.png

相对于元件光轴的输入（|e1| ）和输出（|e2| ）光线矢量：

  .. tex:
    e_1 = \begin{bmatrix} y_{1E} \\ V_{1E} \end{bmatrix}
    \qquad
    e_2 = \begin{bmatrix} y_{2E} \\ V_{2E} \end{bmatrix}
  .. image:: img/misalign_eq_02.png

输入（|m1| ）和输出（|m2| ）处的失调矢量：

  .. tex:
    m_1 = \begin{bmatrix} dy_1 \\ dV \end{bmatrix}
    \qquad
    m_2 = \begin{bmatrix} dy_2 \\ dV \end{bmatrix}
  .. image:: img/misalign_eq_03.png

与往常一样，这里我们将 `V` 定义为几何角，而不是 :ref:`约化斜率 <reduced_slope>` 。

假设失调角很小，`r` 矢量和 `e` 矢量之间的关系为

  .. tex:
    \begin{aligned}
    & r_1 = e_1 + m_1 \\[5pt]
    & r_2 = e_2 + m_2
    \end{aligned}
  .. image:: img/misalign_eq_04.png

相对于元件光轴测量的光线矢量，由元件的 ABCD 矩阵 `M` 按常规方式变换：

  .. tex:
    e_2 = M \times e_1
  .. image:: img/misalign_eq_05.png

然后由 |r2| 和 |r1| 表示 |e2| 和 |e1| ，得到

  .. tex:
    \begin{aligned}
    & r_2 - m_2 = M(r_1 - m_1) \\[5pt]
    & r_2 = M r_1 - M m_1 + m_2
    \end{aligned}
  .. image:: img/misalign_eq_06.png

输出失调矢量 |m2| 与 |m1| 的关系为

  .. tex:
    m_2 = dM \times m_1
  .. image:: img/misalign_eq_07.png

其中 `dM` 只是长度为 `L` 的 :ref:`自由空间 <elem_empty_range>` 的光线变换矩阵。于是

  .. tex:
    \begin{aligned}
    & r_2 = M r_1 - M m_1 + dM \; m_1 \\[5pt]
    & r_2 = M r_1 + (dM - M) \; m_1 \\[5pt]
    & r_2 = M r_1 + \Delta r
    \end{aligned}
  .. image:: img/misalign_eq_08.png

可以看出，失调对近轴系统的影响，是在常规矩阵变换上附加一个修正矢量。修正矢量为：

  .. tex:
    \Delta r
    \equiv
    \begin{bmatrix} E \\ F \end{bmatrix}
    =
    (dM \; – \; M) \; m_1
    =
    \bigg(\,
      \begin{bmatrix} 1 & L \\ 0 & 1 \end{bmatrix} -
      \begin{bmatrix} A & B \\ C & D \end{bmatrix}
    \bigg)\,
    \begin{bmatrix} dy_1 \\ dV \end{bmatrix}
  .. image:: img/misalign_eq_09.png

接下来可以将 |dy1| 简记为 `dy` ，因为它和 `dV` 一样，都是元件参数。于是

  .. tex:
    \begin{bmatrix} E \\ F \end{bmatrix} =
    \begin{bmatrix} 1-A & L-B \\ -C & 1-D \end{bmatrix}
    \begin{bmatrix} dy \\ dV \end{bmatrix}
  .. image:: img/misalign_eq_10.png

通过给光线矢量增加第三个单位分量，可以把这些结果写成方便的 3x3 矩阵形式：

  .. tex:
    \begin{bmatrix} Y_{2R} \\ V_{2R} \\ 1 \end{bmatrix} =
    \begin{bmatrix} A & B & E \\ C & D & F \\ 0 & 0 & 1 \end{bmatrix}
    \begin{bmatrix} Y_{1R} \\ V_{1R} \\ 1 \end{bmatrix}
  .. image:: img/misalign_eq_11.png

其中 `A` 、`B` 、`C` 、`D` 是元件光线矩阵的分量，并且

  .. tex:
    \begin{aligned}
    & E = (1-A) \; dy + (L-B) \; dV \\[5pt]
    & F = -C \; dy + (1-D) \; dV
    \end{aligned}
  .. image:: img/misalign_eq_12.png

级联失调元件
------------

当系统中有多个失调元件时，它们的扩展光线矩阵可以像往常一样相乘，得到整个系统的 :ref:`往返 <round_trip>` 矩阵：

  .. tex:
    \begin{bmatrix} A_0 & B_0 & E_0 \\ C_0 & D_0 & F_0 \\ 0 & 0 & 1 \end{bmatrix} =
    \begin{bmatrix} A_2 & B_2 & E_2 \\ C_2 & D_2 & F_2 \\ 0 & 0 & 1 \end{bmatrix} \times
    \begin{bmatrix} A_1 & B_1 & E_1 \\ C_1 & D_1 & F_1 \\ 0 & 0 & 1 \end{bmatrix}
  .. image:: img/misalign_eq_13.png

相乘后可以看出，附加的矩阵分量不影响基本的光线矢量变换：

  .. tex:
    \begin{bmatrix}
    A_2 A_1 + B_2 C_1   &   A_2 B_1 + B_2 D_1   &   A_2 E_1 + B_2 F_1 + E_2 \\
    C_2 A_1 + D_2 C_1   &   C_2 B_1 + D_2 D_1   &   C_2 E_1 + D_2 F_1 + F_2 \\
    0 & 0 & 1
    \end{bmatrix}
  .. image:: img/misalign_eq_14.png

`E` 和 `F` 分量的变换也可以独立写出，甚至不需要用到扩展矩阵：

  .. tex:
    \begin{bmatrix}E_0 \\ F_0\end{bmatrix} =
    \begin{bmatrix}A_2 & B_2 \\ C_2 & D_2 \end{bmatrix}
    \begin{bmatrix}E_1 \\ F_1\end{bmatrix} +
    \begin{bmatrix}E_2 \\ F_2\end{bmatrix}
  .. image:: img/misalign_eq_15.png

因此，对于任意数量的元件，系统的完整往返矩阵按以下方式计算

  .. tex:
    \begin{bmatrix}
    A_0 & B_0 & E_0 \\
    C_0 & D_0 & F_0 \\
    0 & 0 & 1
    \end{bmatrix}
    =
    \begin{bmatrix}
    A_n & B_n & E_n \\
    C_n & D_n & F_n \\
    0 & 0 & 1
    \end{bmatrix}
    \times
    \; ... \;
    \times
    \begin{bmatrix}
    A_2 & B_2 & E_2 \\
    C_2 & D_2 & V_2 \\
    0 & 0 & 1
    \end{bmatrix}
    \times
    \begin{bmatrix}
    A_1 & B_1 & E_1 \\
    C_1 & D_1 & V_1 \\
    0 & 0 & 1
    \end{bmatrix}
  .. image:: img/misalign_eq_16.png

也可以写成常规 2x2 往返矩阵加一个独立计算的附加失调矢量：

  .. tex:
    \begin{aligned}
    & \begin{bmatrix} E_0 \\ F_0 \end{bmatrix} =
    M_n M_{n-1} ... M_3 M_2 \begin{bmatrix} E_1 \\ F_1 \end{bmatrix} +
    M_n M_{n-1} ... M_3 \begin{bmatrix} E_2 \\ F_2 \end{bmatrix} +
    \; ... \;
    M_n \begin{bmatrix} E_{n-1} \\ F_{n-1} \end{bmatrix} +
    \begin{bmatrix} E_n \\ F_n \end{bmatrix}
    \\[10pt]
    & \begin{bmatrix} E_0 \\ F_0 \end{bmatrix} =
    \sum_{r=1}^n \bigg(\, \prod_{i=n}^{r+1} M_i \bigg)\, \begin{bmatrix} E_r \\ F_r \end{bmatrix}
    \end{aligned}
  .. image:: img/misalign_eq_17.png

有效光轴
--------

一个具有总矩阵 `A` 、`B` 、`C` 、`D` 和总失调矢量 `E` 、`F` 的失调元件系统（以下为简便起见省略下标 0），可以通过将系统平移到距参考光轴 |y_eff| 处，并旋转 |V_eff| 角，转换为一个等效对准的系统。

  .. image:: img/misalign_overall_axis.png

这里 |y_eff| 和 |V_eff| 的表达式，是通过求解以元件矩阵分量和元件失调参数表示 `E` 和 `F` 的线性方程组得到的（见上文）：

  .. tex:
    \begin{aligned}
    & dy_{eff} = \cfrac{(1-D)E - (L-B)F}{(1-A)(1-D) + (L-B)C} \\[5pt]
    & dV_{eff} = \cfrac{CE + (1-A)F}{(1-A)(1-D) + (L-B)C}
    \end{aligned}
  .. image:: img/misalign_eq_18.png

矢量（|y_eff| ，|V_eff| ）给出了失调系统相对于参考光轴的新有效光轴位置。这样的系统看起来像是完全对准的，尽管其内部元件是失调的。

谐振腔的有效光轴
----------------

谐振腔可以展开为一个等效周期系统，每个周期（往返）被视为一个具有各自有效光轴的单个元件。这样，每个往返看起来都像一个完全对准的系统。问题在于，这个有效光轴经过一个往返后并不能回到自身。因此，通过谐振腔的光束经过往返后不能自我再现。所以谐振腔是不稳定的。

  .. image:: img/misalign_resonator_axis.png

因此，谐振腔有效光轴的条件应与单程系统的条件不同，它应与 :ref:`自洽光束 <self_conformed_beam>` 的条件相符，但要计入谐振腔往返的失调：

  .. tex:
    \begin{aligned}
    & \begin{bmatrix} A & B \\ C & D \end{bmatrix}
    \begin{bmatrix} y_{eff} \\ V_{eff} \end{bmatrix} +
    \begin{bmatrix} E \\ F \end{bmatrix} =
    \begin{bmatrix} y_{eff} \\ V_{eff} \end{bmatrix} \\[10pt]
    & \begin{bmatrix} y_{eff} \\ V_{eff} \end{bmatrix} =
    {\bigg(\,
    \begin{bmatrix} 1 & 0 \\ 0 & 1 \end{bmatrix} -
    \begin{bmatrix} A & B \\ C & D \end{bmatrix}
    \bigg)\,}^{-1}
    \begin{bmatrix} E \\ F \end{bmatrix}
    \end{aligned}
  .. image:: img/misalign_eq_19.png

求解该方程，得到一条“轴向光线”的位置——即在具有失调元件的谐振腔中经过往返后自我再现的光线。这条轴向光线构成了谐振腔的有效光轴。

  .. tex:
    \begin{aligned}
    & y_{eff} = \cfrac{(1-D) \, E + BF}{2-A-D} \\[10pt]
    & V_{eff} = \cfrac{CE + (1-A) \, F}{2-A-D}
    \end{aligned}
  .. image:: img/misalign_eq_20.png

需要注意的是，与单程系统的有效光轴不同——后者是一条通过所有元件的直线——谐振腔的有效光轴是一系列线段。一般来说，如果考虑非线性元件，这些线段甚至可以是弯曲的。在谐振腔的每个元件处，都可以计算其各自的（|y_eff| ，|V_eff| ），它定义了自洽（稳定）光线通过该元件的位置。

  .. image:: img/misalign_resonator_axis_1.png

.. seeAlso::

  - :doc:`失调（自定义函数） <func_misalign>`
