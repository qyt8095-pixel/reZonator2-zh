# reZonator

> 本仓库是 [orion-project/rezonator2](https://github.com/orion-project/rezonator2) 的中文汉化副本：界面、提示、文档已翻译为中文，代码结构、文件名和功能保持不变。原项目的所有权利归原作者所有。

## 关于

[reZonator](http://rezonator.orion-project.org) 是一款功能强大的跨平台软件，用于设计激光谐振腔，并计算复杂光学系统中光束的传播（包括高斯光束和光线矢量），不仅适用于谐振腔，也适用于单程系统。它已[得到证实](http://rezonator.orion-project.org/?page=citation)，受到世界各地许多人的欢迎。

它由一位具有多年经验、拥有经典科学背景的专业程序员编写。最初，它只是作为内部使用的工具。因此我们清楚自己想要什么样的工具，并按照使用方便的原则来实现它。当然，不同的人对“方便”有不同的理解，对功能也有不同的需求。所以欢迎提出[建议和错误报告](https://github.com/orion-project/rezonator2/issues)，尤其是错误报告 🫣😀

## 下载

请参阅项目[主页](http://rezonator.orion-project.org)或 GitHub [Releases](https://github.com/orion-project/rezonator2/releases) 页面，获取 Windows、Linux 和 macOS 的二进制安装包。从源码构建请参阅[构建说明](./docs/build.md)。

**Windows：** 如果遇到缺少 DLL 文件的错误（例如 `MSVCP140.dll`），你可能需要安装 Microsoft Visual C++ Redistributable 运行库。请从官方 [Microsoft 页面](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist)下载最新版本。

## 开发动机

尽管已经有不少优秀的[示例](https://www.scilab.org)，但在今天的专业科学软件中，仍然存在一种陈旧的趋势：即便其提供的功能相当通用、直观，并且在文献中有充分描述，也要浪费用户大量的金钱。如今，大多数这类计算，一个优秀的学生仅用 [Python](https://www.python.org) 就能完成。Python 及其[库](https://numpy.org)非常强大，而且是[开源](https://opensource.org)的，它很好地展示了软件开发（即使是商业开发）的发展方向。与商业科学软件不同，它开放内部实现，鼓励用户学习和改进，[几乎](https://en.wikipedia.org/wiki/GNU_General_Public_License)不要求任何回报。本项目遵循同样的开源原则。它试图为“科学”软件的世界带来至少同样程度的开放性。它只是为你提供传统、众所周知的[方法](https://en.wikipedia.org/wiki/Ray_transfer_matrix_analysis)，并将其封装在一个方便的界面中，并不声称自己实现了某些“只有我们才知道、要保密的专利算法”。任何人都可以查看源代码、验证正确性、实现自己的功能或改进现有功能。它并不打算提供付费巨头软件的全部功能，而是提供足够有用的功能。

## 功能

- **光学系统：** reZonator 支持不同的[光学系统类型](http://rezonator.orion-project.org/help/trip_type.html)——驻波激光腔和行波（环形）谐振腔，以及传统的单程系统，例如泵浦光路或扩束器。单程系统还会考虑 M² 光束质量因子。

- **光学元件：** 程序的[元件目录](http://rezonator.orion-project.org/help/elements.html)包含许多重要的光学元件——区间、透镜、反射镜、晶体等等。元件仿真采用 ABCD 光线矩阵算法，因此你也可以通过提供矩阵来定义自己的元件。

- :new: :fire: 通过**自定义元件**，你可以提供公式，根据元件参数[计算矩阵](http://rezonator.orion-project.org/help/matrix/ElemFormula.html)，并创建标准库中没有的光学元件。

- :new: :fire: **自定义参数**允许你在标准内置参数之外，为元件扩展额外的[用户自定义参数](http://rezonator.orion-project.org/help/custom_params.html)，当你需要跟踪或计算特定光学系统的附加属性时非常有用。

- **不受限制的设计：** 该应用不计算任何特定的光学几何结构。相反，你可以从建议的或用户自定义的光学元件中构建任意光学系统。reZonator 会自动生成所研究系统的[布局图](http://rezonator.orion-project.org/help/layout.html)——就好像你可以在纸上或绘图板上勾勒它一样。

- **稳定性图：** 为了进行高级系统优化，reZonator 可以针对任意元件的[一个](http://rezonator.orion-project.org/help/func_stabmap.html)或[两个](http://rezonator.orion-project.org/help/func_stabmap_2d.html)参数计算腔稳定性图，同时还提供稳定性边界的自动计算。

- **波前计算：** reZonator 可以绘制高斯光束在[一个](http://rezonator.orion-project.org/help/func_caustic.html)或[多个](http://rezonator.orion-project.org/help/func_caustic_mr.html)元件上的尺寸和波前曲率半径，同时考虑像散。可以在系统内的任意位置计算光束尺寸。还提供元件处束腰位置和尺寸的自动确定、衍射发散半径的计算以及其他[高斯光束](http://rezonator.orion-project.org/help/calc_gauss.html)参数。

- :new: :fire: **自定义函数**提供了一种强大的方式，可以通过编写自己的 Python 代码来扩展 reZonator 的功能，分析光学光路图、执行专门的计算，并以适合你需求的方式可视化结果。

- **调节：** [调节]((http://rezonator.orion-project.org/help/adjust.html))工具允许你逐渐改变任意元件的任意参数——就像旋转反射镜架的螺丝或平移台一样。参数值改变时，所有结果都会即时重新计算。

- **参数化设计：** [全局参数](http://rezonator.orion-project.org/help/params_window.html)可以将不同的元件相互关联；由自定义公式给出的参数值可以构建动态的参数化系统。

- **更多功能：** 还提供其他方便实用的工具和功能：[重复频率](http://rezonator.orion-project.org/help/func_reprate.html)、所有元件处的[光束参数](http://rezonator.orion-project.org/help/func_beamdata.html)、元件失调（通过自定义脚本）、结果[“冻结”](http://rezonator.orion-project.org/help/func_freeze.html)、完整的绘图格式自定义、将结果复制到剪贴板等等……

##

![Main Window](./img/main_window_2.1.1.png)

##

[![Star History Chart](https://api.star-history.com/svg?repos=orion-project/rezonator2&type=Date)](https://star-history.com/#orion-project/rezonator2&Date)
