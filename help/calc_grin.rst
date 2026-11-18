GRIN 透镜评估
=============

.. |n0| replace:: `n`\ :sub:`0`
.. |n2| replace:: `n`\ :sub:`2`
.. |r1| replace:: `r`\ :sub:`1`
.. |v1| replace:: `V`\ :sub:`1`
.. |r2| replace:: `r`\ :sub:`2`
.. |v2| replace:: `V`\ :sub:`2`
.. |r3| replace:: `r`\ :sub:`3`
.. |v3| replace:: `V`\ :sub:`3`

:menuselection:`工具 --> GRIN 透镜评估`

工具 *GRIN 透镜评估* 可以根据已知的长度 `L` 、轴向折射率 |n0| 和梯度常数 |n2| 计算 GRIN 透镜的焦距范围 `F` 。

也可以根据已知的焦距范围 `F` 、长度 `L` 和轴向折射率 |n0| 计算梯度常数 |n2| 。无论哪种情况，`L` 和 |n0| 始终是输入参数。

  .. image:: img/calc_grin.png

工具栏上的按钮决定了当我们改变 `L` 或 |n0| 中的一个时，计算 |n2| 和 `F` 中的哪一个值。
 
因为在这里 |n2| 和 `F` 都是自由参数，所以当其中一个改变时，另一个会被计算出来，与工具栏上按下哪个按钮无关。

  
焦距范围评估
------------

一种用于估算 GRIN 透镜焦距范围的几何方法。它依据 A. Yariv 的著作 "Quantum Electronics"，见第 6.4 章 "Rays in lenslike media"（其中没有给出精确算法，但给出了最终公式）。

  .. image:: img/calc_grin_draw.png
  
我们有一个 :doc:`matrix/ElemGrinLens` 和一束进入它的平行入射光线（|r1| 、|v1| ）。然后可以用 :ref:`光线矢量变换 <ray_vector>` 公式计算出射光线（|r2| 、|v2| ）：

  .. tex:
    \begin{aligned}
    & \begin{bmatrix}r_2 \\ V_2 \end{bmatrix} =
      \begin{bmatrix}
        \cos(\gamma L) & \cfrac {\sin(\gamma L)} {n_0 \gamma} \\
        -n_0 \gamma \: \sin(\gamma L) & \cos(\gamma L) 
      \end{bmatrix}
      \begin{bmatrix}r_1 \\ V_1 \end{bmatrix} \\ \\
    & \gamma = \sqrt \frac {n_2} {n_0} \\ \\
    & V_1 = 0 \\ \\
    & r_2 = r_1 \cos(\gamma L) \\ \\
    & V_2 = -r_1 n_0 \gamma \sin(\gamma L)
    \end{aligned}
  .. image:: img/calc_grin_f1.png

然后类似地，我们可以根据光线（|r2| 、|v2| ）和 :doc:`自由空间 <matrix/ElemEmptyRange>` 的矩阵表示光线（|r3| 、|v3| ）：

  .. tex:
    \begin{aligned}
    & \begin{bmatrix}r_3 \\ V_3 \end{bmatrix} =
      \begin{bmatrix}
        1 & F \\
        0 & 1 
      \end{bmatrix}
    \begin{bmatrix}r_2 \\ V_2 \end{bmatrix} \\ \\
    & r_3 = r_2 + F V_2 = 0 \\ \\
    & V_3 = V_2
    \end{aligned}
  .. image:: img/calc_grin_f2.png

然后把这两个表达式联立起来对 `F` 求解，可以得到最终公式：

  .. tex: F = \frac 1 {n_0 \gamma} \frac {\cos(\gamma L)}{\sin(\gamma L)} = \frac 1 {n_0 \gamma \tan(\gamma L)}
  .. image:: img/calc_grin_f0.png

负透镜
^^^^^^

  .. image:: img/calc_grin_draw_neg.png

用类似的方法可以得到负热透镜的焦距：

  .. tex:
    \begin{aligned}
    & \begin{bmatrix}r_2 \\ V_2 \end{bmatrix} =
      \begin{bmatrix}
        \cosh(\gamma L)                &   \cfrac {\sinh(\gamma L)} {n_0 \gamma} \\
        n_0 \gamma \: \sinh(\gamma L)  &   \cosh(\gamma L) 
      \end{bmatrix}
      \begin{bmatrix}r_1 \\ V_1 \end{bmatrix} \\ \\
    & \gamma = \sqrt \frac {|n_2|} {n_0} \\ \\
    & V_1 = 0 \\ \\
    & r_2 = r_1 \cosh(\gamma L) \\ \\
    & V_2 = r_1 n_0 \gamma \sinh(\gamma L)
    \end{aligned}
  .. image:: img/calc_grin_f1_neg.png

从图中可以看出，光线矢量的半径 |r3| 在经过焦距后加倍：

  .. tex:
    \begin{aligned}
    & \begin{bmatrix}r_3 \\ V_3 \end{bmatrix} =
      \begin{bmatrix}
        1 & F \\
        0 & 1 
      \end{bmatrix}
    \begin{bmatrix}r_2 \\ V_2 \end{bmatrix} \\ \\
    & r_3 = r_2 + F V_2 = 2 r_2 \\ \\
    & V_3 = V_2
    \end{aligned}
  .. image:: img/calc_grin_f2_neg.png

因此把这两个表达式联立起来对 `F` 求解，得到的公式与正透镜的公式非常相似：

  .. tex: F = - \frac 1 {n_0 \gamma} \frac {\cosh(\gamma L)}{\sinh(\gamma L)} = - \frac 1 {n_0 \gamma \tanh(\gamma L)}
  .. image:: img/calc_grin_f0_neg.png

梯度常数评估
------------

梯度折射率 |n2| 没有这样简单的公式，因此是在已知 `F` 、`L` 和 |n0| 的情况下，通过对上述公式关于 |n2| 的数值求解来计算的。
