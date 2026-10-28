# 在 Windows 上准备第三方库

请确保 MinGW 的 `bin` 目录已加入 `PATH`。建议使用与 Qt 相同的 MinGW 版本。例如：
```
set PATH=C:\Qt\Tools\mingw530_32\bin;%PATH%
```

假定当前目录为项目根目录，即包含 `rezonator.pro` 文件的目录。

## Lua

从 http://www.lua.org/ftp/lua-5.3.4.tar.gz 下载源码包并解压到 `libs` 目录，这样 Lua 就位于 `libs/lua-5.3.4` 中。
