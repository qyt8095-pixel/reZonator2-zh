#include "CommonUtils.h"

#include <QApplication>
#include <QFileInfo>

namespace Z {
namespace IO {
namespace Utils {

bool isOldSchema(const QString& fileName)
{
    return QFileInfo(fileName).suffix() == suffixOld();
}

QString filtersForOpen()
{
    return qApp->translate("IO",
                           "reZonator 项目文件 (*.%1)\n"
                           "reZonator 1 光路图文件 (*.%2)\n"
                           "所有文件 (*.*)")
            .arg(suffix(), suffixOld());
}

QString filtersForSave()
{
    return qApp->translate("IO",
                           "reZonator 项目文件 (*.%1)\n所有文件 (*.*)")
            .arg(suffix());
}

QString refineFileName(const QString& fileName, const QString &selectedFilter)
{
    return appendSuffix(fileName, extractSuffix(selectedFilter));
}

QString appendSuffix(const QString& fileName, const QString& selectedSuffix)
{
    QFileInfo fileInfo(fileName);
    if (fileInfo.suffix().isEmpty())
    {
        auto ext = selectedSuffix.isEmpty()? suffix(): selectedSuffix;

        if (fileName.endsWith('.'))
            return fileName % ext;

        return fileName % '.' % ext;
    }
    return fileName;
}

QString extractSuffix(const QString& filter)
{
    if (filter.isEmpty()) return suffix();

    int start = filter.indexOf('.');
    if (start < 0) return suffix();

    int stop = filter.indexOf(')');
    if (stop < 0) return suffix();

    auto ext = filter.mid(start+1, stop-start-1);
    if (ext == QStringLiteral("*")) return suffix();

    return ext;
}

} // namespace Utils
} // namespace IO
} // namespace Z
