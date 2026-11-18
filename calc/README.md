# 计算脚本

本目录包含各种计算脚本。这些脚本为单元测试提供验证数据（例如 `Elem*` 文件对应 `../src/test/test_Elements.cpp`），或为函数验证提供一些计算。

## 准备环境

不同项目部分（例如 `calc` 和 `help`）共用虚拟环境，因此最好在项目顶层创建。

Linux、macOS：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows：

```bash
python -m venv .venv
.venv\Scripts\activate
```

Windows 上没有 `python3` 命令，因此请确保 Python 3 已加入 `PATH`。

## 安装依赖

```bash
pip install -r requirements.txt
```

## 运行笔记本

虽然这里的许多脚本只是应在终端中运行的 Python 代码，但也有几个 Jupyter 笔记本。要查看和编辑它们，请运行

```bash
jupyter notebook --port 9999
```

端口是可选的，默认为 8888。
