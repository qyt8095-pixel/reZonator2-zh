.. index:: single: elements
.. index:: single: optical elements

********
元件
********

元件是 |rezonator| 中任何光路图的构成模块。

元件可以描述一般的光学元件，例如 :doc:`反射镜 <matrix/ElemCurveMirror>` 或 :doc:`晶体 <matrix/ElemBrewsterCrystal>`。此外，它还可以表示某种物理但非物质的实体——例如光学元件之间的 :doc:`距离 <matrix/ElemEmptyRange>`。最后，它还可以作为某种虚拟辅助对象——例如 :doc:`点 <matrix/ElemPoint>`。

|rezonator| 支持一组组织在 :doc:`目录 <catalog>` 中的标准元件。

该应用采用传统的 ABCD 矩阵方法（Kogelnik 和 Li）来计算近轴高斯光束通过元件的传播。在计算中，每个元件由其 :doc:`光线矩阵 <elem_matrs>` 表示。

你无需手动为元件指定矩阵。相反，你可以为一些典型的元件参数提供数值——例如透镜的焦距、晶体的厚度和折射率等。软件会根据这些参数值自动计算元件矩阵。

.. tocTree::
   :maxDepth: 1
   :caption: 目录：

   elem_props
   elem_opers
   catalog
   elem_matrs
   elem_library
