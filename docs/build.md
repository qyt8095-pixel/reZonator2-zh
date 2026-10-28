# 从源码构建

## 准备构建环境

### Qt

必须安装 [Qt 开源版](https://www.qt.io/download-open-source)。目前所有平台的目标 Qt 版本均为 5.15.2。Windows 请选择 "MSVC 2019 64-bit" 版本。QtCreator 是本项目默认使用的 IDE。

### Visual Studio

Windows 上使用 Microsoft C++ 编译器，因此必须单独安装 [Visual Studio Community 2022](https://visualstudio.microsoft.com/en/vs/community/)。唯一需要的工作负载是“使用 C++ 的桌面开发”。

Visual Studio 也可以通过 [Qt Visual Studio Tools](https://doc.qt.io/qtvstools-2) 扩展作为 Qt 项目的 IDE。在 VS 中依次进入“扩展 -> 管理扩展”，搜索该扩展并安装，然后进入“扩展 -> Qt VS Tools -> Qt Versions”并注册一个 Qt 安装路径。

### CMake

CMake 可以单独安装，也可以作为 Qt 安装的一部分安装。

### vcpkg

[vcpkg](https://vcpkg.io/) 是一个开源 C++ 包管理器。它必须安装在与项目分开的目录中，用于准备第三方依赖，例如 Python：

```bash
git clone https://github.com/microsoft/vcpkg.git
```

然后根据平台运行 `bootstrap-vcpkg.sh` 或 `bootstrap-vcpkg.bat`，将 vcpkg 目录添加到 `PATH`，并创建包含安装路径的 `VCPKG_ROOT` 变量。

在项目目录中下载并编译依赖：

```bash
vcpkg install
```

**Ubuntu：** 构建 Python 至少需要 22（jammy）版本。

**macOS：** 应使用 Qt 6.9.3 将 Python 链接到应用（详见下文“注意事项”一节）

在 QtCreator 中配置项目时，在 CMake 初始配置选项卡中添加附加选项并重新配置。该选项必须指向已安装的 vcpkg 工具链文件位置，例如：

```
-DCMAKE_TOOLCHAIN_FILE:FILEPATH=/home/user/vcpkg/scripts/buildsystems/vcpkg.cmake
```


### Qt 注意事项

**[Ubuntu] 平台插件**

如果 QtCreator 在 Ubuntu 上因以下原因拒绝运行：

```log
qt.qpa.plugin: Could not load the Qt platform plugin "xcb" in "" even though it was found.
```

请尝试运行

```bash
sudo apt-get install --reinstall libxcb-xinerama0
```

我用 16.04 构建，这样可以正常工作。（更新：自 reZonator-2.1 起使用 Ubuntu 22.04）

**[Ubuntu] GL 库**

首次在 Ubuntu 上构建时会提示：

```log
../Qt/5.15.2/gcc_64/include/QtGui/qopengl.h:141:22: fatal error: GL/gl.h: No such file or directory
```

必须安装以下开发库：

```bash
sudo apt-get install build-essential libgl1-mesa-dev
```

QCustomPlot [说明](https://www.qcustomplot.com/index.php/tutorials/settingup)中也提到了这些，因此可能也需要安装：

```bash
sudo apt-get install mesa-common-dev libgl1-mesa-dev libglu1-mesa-dev
```

**（已过时）[macOS] Sierra 适用的最新 Qt**

Qt 5.12.10 是适用于 Sierra（10.12）的最新 5.* LTS 版本。
QtCreator 4.10.2 同样是最新版本，必须手动下载安装。
此外，还必须在那个“已过时”的 QtCreator 中手动注册 5.12.10 套件。

**[macOS] Monterey 适用的最新 Qt**

为了提供更广泛的兼容性，使用 macOS 12 编译应用并构建可分发的 dmg 镜像。使用 Qt 5.15.2 时，由于 Python 与应用目标模块之间的架构名称不一致（？），Python 库链接会失败。因此应使用 Qt 6.9.3，它是支持 macOS 12 的最新 6.* 版本。支持 macOS 12 的最新 Qt Creator 是 [17.0.2](https://github.com/qt-creator/qt-creator/releases/tag/v17.0.2)，应从 GitHub 单独安装。Qt Maintenance Tool 安装的更新版本不兼容。

## 克隆 git 仓库

```bash
git clone https://github.com/orion-project/rezonator2
cd rezonator2
git submodule init
git submodule update
```

注意，子模块默认处于“分离头指针”状态。

<!--
## Prepare third-party libraries

### Windows

[QCustomPlot](https://www.qcustomplot.com) is used via wrapper [repository](https://github.com/orion-project/custom-plot-lab) (in submodule). The library source file `qcustomplot.cpp` is so large that it even fails to build in debug mode (`x86_64-w64-mingw32/bin/as.exe: debug\qcustomplot.o: too many sections (33061) Fatal error: debug\qcustomplot.o: file too big`). So if the debug mode is needed, you have to use QCustomPlot as shared library. Build the library:

```bash
cd libs\custom-plot-lab\qcustomplot
qmake
mingw32-make release
```

Then enable option `qcustomplotlab_shared` in `rezonator.pro` and rebuild the app in debug mode.
-->

## 开发构建

使用 *Qt Creator IDE* 进行开发构建。只需在 IDE 中打开项目文件 `CMakeLists.txt`，并配置使用某个已安装的 Qt 套件。任何现代 Qt 5.15.2+ 套件都适用。

目标文件为 `bin/rezonator`（Linux）、`bin/rezonator.app`（macOS）或 `bin\rezonator.exe`（Windows）。

<!--
## Release build

```bash
# Linux/MacOS
./scripts/build_release.sh

# Windows
scripts\build_release.bat
```

Ensure that Qt bin directory is in your `PATH` to make the above scripts working. On Windows you have to put MinGW `bin` directory `<qt-root>\<qt-version>\mingw*\bin` into the `PATH` too. The scripts do the full rebuild and it takes a while.
-->

## 源码文档

```bash
sudo apt install doxygen
sudo apt install graphviz
mkdir -p out/src-doc
doxygen
```

## 用户手册

请参阅[构建文档](../help/README.md)。
