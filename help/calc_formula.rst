.. index:: single: formula calculator

公式计算器
==========

:menuselection:`工具 --> 公式计算器`

公式计算器是用于计算以文本表达式给出的自定义公式的工具。在文本字段 :guipart:`1` 中输入公式，然后按 :kbd:`Ctrl+Enter` 或点击工具栏上的 :guilabel:`计算` 按钮。计算结果显示在字段 :guipart:`2` 中。

|rezonator| 内部使用 `Lua <http://www.lua.org>`_ 计算自定义公式。参见 :doc:`lua_primer` ，了解支持的操作和函数。

    .. image:: img/calc_formula.png

对于简单的公式，你可以直接输入，例如：::

    sin(deg2rad(30))

对于更复杂的公式，可以定义附加变量，使表达式更清晰、易于理解，例如：::

    L = 2.5
    n = 1.33
    alpha = deg2rad(30)
    ans = L / sqrt(n^2 - sin(alpha)^2)

在这种情况下，你必须明确指定哪个值应作为最终结果。将结果值存入预定义变量 ``ans`` （即 'answer' 的缩写）。所有变量，包括 ``ans`` ，都列在表格 :guipart:`3` 中，可以在后续计算中重复使用。


    .. note::

        你不能只定义一个变量而不提供答案，因此像 ``a = 2`` 这样的表达式无效。如果你只想给变量赋值，请把该变量用作答案：``a = 2; ans = a`` 。

.. seealso::

    :doc:`lua_primer`
