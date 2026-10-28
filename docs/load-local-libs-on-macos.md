# 如何在 macOS 上加载本地库

这是一个加载位于应用包中的 `muparser` 库的示例。

库应放置在应用包的 `Frameworks` 子目录中。

然后需要使用 `install_name_tool` 来调整应用可执行文件中的解析规则：

```
install_name_tool -id \
    @executable_path/../Frameworks/libmuparser.2.dylib \
    bin/rezonator.app/Contents/Frameworks/libmuparser.2.dylib

install_name_tool -change \
    /usr/local/lib/libmuparser.2.dylib \
    @executable_path/../Frameworks/libmuparser.2.dylib \
    bin/rezonator.app/Contents/MacOS/rezonator
```