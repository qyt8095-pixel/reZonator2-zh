#include "LidtMarks.h"

#include <QJsonArray>
#include <QJsonValue>
#include <QObject>

QString LidtMark::tooltip() const
{
    // Keep the numbers short: fluence and limit with up to 4
    // significant digits, ratio with two decimals.
    return QObject::tr("LIDT：峰值 %1 J/cm² / 阈值 %2，比值 %3")
            .arg(QString::number(fluence, 'g', 4),
                 QString::number(limit, 'g', 4),
                 QString::number(ratio(), 'f', 2));
}

QMap<QString, LidtMark> parseLidtReport(const QJsonObject& report)
{
    QMap<QString, LidtMark> marks;
    const QJsonArray checks = report.value(QStringLiteral("checks")).toArray();
    for (const QJsonValue& checkValue : checks)
    {
        const QJsonObject check = checkValue.toObject();
        if (check.value(QStringLiteral("kind")).toString()
                != QStringLiteral("lidt"))
            continue;
        const QString status = check.value(QStringLiteral("status")).toString();
        if (status != QStringLiteral("fail")
                && status != QStringLiteral("warn"))
            continue;
        const QString label = check.value(QStringLiteral("element")).toString();
        if (label.isEmpty())
            continue;
        LidtMark mark;
        mark.label = label;
        mark.status = status;
        mark.fluence = check.value(QStringLiteral("value")).toDouble();
        mark.limit = check.value(QStringLiteral("limit")).toDouble();
        marks.insert(label, mark);
    }
    return marks;
}

QString engPathForRez(const QString& rezPath)
{
    return rezPath + QStringLiteral(".eng.json");
}
