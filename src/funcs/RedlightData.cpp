#include "RedlightData.h"

#include <QJsonArray>
#include <QJsonValue>
#include <QObject>
#include <QtMath>

namespace {

double jsonDouble(const QJsonObject& obj, const char* key)
{
    const QJsonValue value = obj.value(QLatin1String(key));
    return value.isDouble() ? value.toDouble() : qQNaN();
}

} // namespace

QString RedlightReport::modeLabel() const
{
    const QString nm = QString::number(redNm, 'g', 4);
    if (isFallback())
        return QObject::tr("红光 %1 nm（外部注入）").arg(nm);
    return QObject::tr("红光 %1 nm（冷腔本征模）").arg(nm);
}

RedlightReport parseRedlightReport(const QJsonObject& report)
{
    RedlightReport result;
    if (!report.contains(QStringLiteral("table"))
            || !report.contains(QStringLiteral("path")))
    {
        result.error = QObject::tr("红光报告缺少 table 或 path 字段");
        return result;
    }
    result.redNm = report.value(QStringLiteral("red_nm")).toDouble(632.8);
    result.hotNm = report.value(QStringLiteral("hot_nm")).toDouble(1064.0);
    result.path = report.value(QStringLiteral("path")).toString();
    if (result.path != QStringLiteral("cold_eigenmode")
            && result.path != QStringLiteral("fallback"))
    {
        result.error = QObject::tr("红光报告的 path 未知：%1").arg(result.path);
        return result;
    }
    const QJsonArray table = report.value(QStringLiteral("table")).toArray();
    for (const QJsonValue& rowValue : table)
    {
        const QJsonObject rowObj = rowValue.toObject();
        const QString label = rowObj.value(QStringLiteral("element")).toString();
        if (label.isEmpty())
            continue;
        RedlightRow row;
        row.label = label;
        row.w1064T = jsonDouble(rowObj, "w_1064_T_mm");
        row.w1064S = jsonDouble(rowObj, "w_1064_S_mm");
        row.w633T = jsonDouble(rowObj, "w_633_T_mm");
        row.w633S = jsonDouble(rowObj, "w_633_S_mm");
        row.x633T = jsonDouble(rowObj, "x_633_T_mm");
        row.x633S = jsonDouble(rowObj, "x_633_S_mm");
        result.rows.insert(label, row);
    }
    result.ok = true;
    return result;
}
