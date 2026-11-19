#ifndef REDLIGHT_DATA_H
#define REDLIGHT_DATA_H

#include <QJsonObject>
#include <QMap>
#include <QString>

/// One row of a ``run_redlight.py`` report table
/// (``engineering/rezeng/redlight.py::redlight_report``):
/// the hot (1064 nm) eigenmode spot and the red (632.8 nm) beam
/// spot at one element's exit plane, plus the red beam's axis
/// offset. Radii are NaN when the report has no red value for
/// the element.
struct RedlightRow
{
    QString label;
    double w1064T = qQNaN();
    double w1064S = qQNaN();
    double w633T = qQNaN();
    double w633S = qQNaN();
    double x633T = qQNaN();
    double x633S = qQNaN();
};

/// Parsed ``run_redlight.py`` report.
struct RedlightReport
{
    bool ok = false;
    QString error;
    double redNm = 632.8;
    double hotNm = 1064.0;
    /// "cold_eigenmode" (red beam is the cold cavity eigenmode) or
    /// "fallback" (cold cavity unstable, externally injected HeNe).
    QString path;
    QMap<QString, RedlightRow> rows; // by element label

    bool isFallback() const { return path == QStringLiteral("fallback"); }

    /// Short mode label for the beam-data window title, e.g.
    /// "红光 632.8 nm（外部注入）" or "红光 632.8 nm（冷腔本征模）".
    QString modeLabel() const;
};

/// Parse a ``run_redlight.py`` report object. A report without a
/// ``table`` array (or with a missing ``path``) parses to ``ok=false``
/// with an error message; rows whose red values are null keep NaN
/// radii instead of failing the whole report.
RedlightReport parseRedlightReport(const QJsonObject& report);

#endif // REDLIGHT_DATA_H
