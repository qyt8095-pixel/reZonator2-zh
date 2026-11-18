.. index:: single: rezonator (Python)

模块：rezonator
===============

``rezonator`` 模块（简写别名为 ``Z`` ）提供全局常量、实用函数，以及用于矩阵和光束计算的类。

常量
----

.. ###################################################################

.. index:: single: C (Python)

``Z.C``
  光速，单位为 m/s

.. ###################################################################

.. index:: single: PI (Python)

``Z.PI``
  圆周率常量

.. ###################################################################

.. index:: single: PLANE_T (Python)
.. _py_const_plane_t:

``Z.PLANE_T``
  :ref:`切向 <working_planes>` 平面

.. ###################################################################

.. index:: single: PLANE_S (Python)
.. _py_const_plane_s:

``Z.PLANE_S``
  :ref:`弧矢 <working_planes>` 平面

.. ###################################################################

.. index:: single: DIM_NONE (Python)
.. _py_const_dim_none:

``Z.DIM_NONE``
  无量纲。

.. ###################################################################

.. index:: single: DIM_LINEAR (Python)
.. _py_const_dim_linear:

``Z.DIM_LINEAR``
  线性量纲（长度）

.. ###################################################################

.. index:: single: DIM_ANGULAR (Python)
.. _py_const_dim_angular:

``Z.DIM_ANGULAR``
  角度量纲

.. ###################################################################

函数
----

.. ###################################################################

.. index:: single: print (Python)
.. _py_module_z_print:

``print(*args, spaced=True)``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

将消息打印到函数输出窗口。

参数：

- ``*args`` - 要打印的值（字符串、数字或具有 ``__repr__`` 的对象）。当参数是数字时，它会根据 :ref:`应用程序设置 <app_settings_format_precision>` 进行格式化。要获得未格式化的输出，请使用 Python 内置函数 ``str`` 将数字转换为字符串，忽略应用程序设置。
- ``spaced`` (bool, optional) - 如果为 True（默认值），用空格分隔参数

示例：

.. code-block:: python

    import rezonator as Z
    Z.print('Speed of light:', Z.C, 'm/s')  # Output: Speed of light: 2.998e+08 m/s
    Z.print('Speed of light:', str(Z.C), 'm/s') # Output: Speed of light: 299792458.0 m/s
    Z.print('L=', elem.length, spaced=False)  # Output: L=0.1

.. ###################################################################

.. index:: single: format (Python)

``format(value)``
~~~~~~~~~~~~~~~~~

将数值格式化为用户友好的显示字符串，遵循 :ref:`应用程序设置 <app_settings_format_precision>` 。

参数：

- ``value`` (float) - 要格式化的数值

返回值：

- str - 格式化后的字符串表示

示例：

.. code-block:: python

    import rezonator as Z
    Z.print('Length:', Z.format(0.00123))  # Output: "1.23e-3"

.. ###################################################################

.. index:: single: version (Python)

``version()``
~~~~~~~~~~~~~

获取应用程序版本字符串，例如“2.1.2”。

.. ###################################################################

.. index:: single: exe_dir (Python)

``exe_dir()``
~~~~~~~~~~~~~

获取应用程序可执行文件所在目录的路径。

返回值：

- str - 包含应用程序可执行文件的目录的完整路径

该函数在 Linux 上特别有用（从 AppImage 启动的路径与实际运行位置不同）和 macOS 上（资源打包在应用程序包中）。访问内置应用程序资源（如示例文件）时，使用 ``getcwd() + "/examples"`` 可能会失败，而 ``Z.exe_dir() + "/examples"`` 可以正常工作。

示例：

.. code-block:: python

    import rezonator as Z
    import os

    # Get path to built-in examples
    examples_dir = os.path.join(Z.exe_dir(), 'examples')
    Z.print('Examples directory:', examples_dir)

.. ###################################################################

.. index:: single: plane_str (Python)

``plane_str(plane)``
~~~~~~~~~~~~~~~~~~~~

将 :ref:`工作平面 <work_plane>` 常量转换为字符串名称。

参数：

- ``plane`` (int) - 平面常量（``Z.PLANE_T`` 或 ``Z.PLANE_S`` ）

返回值：

- str - 平面名称（'T' 或 'S'）

示例：

.. code-block:: python

    import rezonator as Z
    name = Z.plane_str(Z.PLANE_T)  # Returns 'T'

.. ###################################################################

.. seeAlso::

  - :doc:`py_api`
  - :doc:`py_schema`
