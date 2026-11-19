#ifndef LIDT_MARKS_H
#define LIDT_MARKS_H

#include <QJsonObject>
#include <QMap>
#include <QString>

/// LIDT warning mark for one element in the main element list
/// (Phase 4 follow-up: LIDT red-box warning in the main UI).
///
/// The marks come from the ``lidt`` entries of a ``run_checks.py``
/// JSON report (``engineering/rezeng/checks.py``): each entry carries
/// the peak fluence as ``value``, the damage threshold as ``limit``
/// and the status (``ok`` / ``warn`` / ``fail`` / ``nodata``).
/// Only ``warn`` (ratio > 0.8) and ``fail`` (ratio > 1.0) entries
/// produce a mark; ``ok`` and ``nodata`` (missing laser params or
/// missing LIDT data) never mark the row.
struct LidtMark
{
    QString label;
    QString status; // "warn" or "fail"
    double fluence = 0.0; // peak fluence, J/cm^2 (report "value")
    double limit = 0.0;   // LIDT threshold, J/cm^2 (report "limit")

    double ratio() const { return limit > 0 ? fluence / limit : 0.0; }
    bool isFail() const { return status == QStringLiteral("fail"); }
    bool isWarn() const { return status == QStringLiteral("warn"); }

    /// Row tooltip, e.g. "峰值 6.18 J/cm² / LIDT 5.0，比值 1.24".
    QString tooltip() const;
};

/// Parse a ``run_checks.py`` report object into per-element marks,
/// keyed by element label. Entries of other kinds (aperture, board)
/// and ``ok`` / ``nodata`` LIDT entries are ignored.
QMap<QString, LidtMark> parseLidtReport(const QJsonObject& report);

/// Side-car path for a .rez file: ``<file>.rez.eng.json``
/// (same rule as ``engineering/rezeng/eng.py::eng_path``).
QString engPathForRez(const QString& rezPath);

#endif // LIDT_MARKS_H
