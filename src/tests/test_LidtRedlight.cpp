#include "../app/AppSettings.h"
#include "../core/Schema.h"
#include "../funcs/EngineeringBackend.h"
#include "../funcs/LidtCheckRunner.h"
#include "../funcs/LidtMarks.h"
#include "../funcs/RedlightData.h"
#include "../io/SchemaReaderJson.h"
#include "../math/BeamParamsAtElemsFunction.h"
#include "../tests/TestUtils.h"

#include "testing/OriTestBase.h"

#include <cmath>

#include <QDir>
#include <QEventLoop>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QTemporaryDir>
#include <QTimer>

//------------------------------------------------------------------------------
//  Tests for the Phase 4 follow-up (LIDT red-box marks in the main
//  element list + one-click red-light toggle on the main window):
//  report parsing, mark rules, red-light overlay in the beam-data
//  function, and the async LIDT runner against the real backend.
//------------------------------------------------------------------------------

namespace Z {
namespace Tests {
namespace LidtRedlightTests {

namespace {

QJsonObject jsonFromText(const char* text)
{
    QJsonParseError error;
    const QJsonDocument doc = QJsonDocument::fromJson(QByteArray(text), &error);
    return doc.object();
}

const char* LIDT_REPORT = R"JSON({
  "version": 1,
  "checks": [
    {"id": "lidt:M1", "element": "M1", "kind": "lidt", "status": "fail",
     "value": 6.1755, "limit": 5.0, "unit": "J/cm^2", "message": "x"},
    {"id": "lidt:M2", "element": "M2", "kind": "lidt", "status": "warn",
     "value": 4.2, "limit": 5.0, "unit": "J/cm^2", "message": "x"},
    {"id": "lidt:M3", "element": "M3", "kind": "lidt", "status": "ok",
     "value": 0.27, "limit": 5.0, "unit": "J/cm^2", "message": "x"},
    {"id": "lidt:M4", "element": "M4", "kind": "lidt", "status": "nodata",
     "value": null, "limit": null, "unit": "J/cm^2", "message": "x"},
    {"id": "aperture:M1", "element": "M1", "kind": "aperture", "status": "fail",
     "value": 0.5, "limit": 0.01, "unit": "fraction", "message": "x"},
    {"id": "board_bounds:M1", "element": "M1", "kind": "board_bounds", "status": "fail",
     "value": 15.0, "limit": 0.0, "unit": "mm", "message": "x"}
  ],
  "summary": {"ok": 1, "warn": 1, "fail": 3, "nodata": 1, "total": 6}
})JSON";

const char* REDLIGHT_REPORT = R"JSON({
  "version": 1, "red_nm": 632.8, "hot_nm": 1064.0, "path": "fallback",
  "cold": {"stable": false, "g_T": -1.95, "g_S": -1.99},
  "table": [
    {"element": "M1", "s_mm": 0.0,
     "w_1064_T_mm": 0.1000, "w_1064_S_mm": 0.1031,
     "x_1064_T_mm": 0.0, "x_1064_S_mm": 0.0,
     "w_633_T_mm": 0.1040, "w_633_S_mm": 0.1050,
     "x_633_T_mm": -0.0177, "x_633_S_mm": 0.002,
     "dw_T_mm": 0.004, "dw_S_mm": 0.0019,
     "dw_T_pct": 4.0, "dw_S_pct": 1.84,
     "dx_T_mm": -0.0177, "dx_S_mm": 0.002},
    {"element": "M4", "s_mm": 1170.0,
     "w_1064_T_mm": 0.2057, "w_1064_S_mm": 0.2113,
     "x_1064_T_mm": 0.0, "x_1064_S_mm": 0.0,
     "w_633_T_mm": 0.2139, "w_633_S_mm": 0.2197,
     "x_633_T_mm": -0.0368, "x_633_S_mm": 0.0041,
     "dw_T_mm": 0.0082, "dw_S_mm": 0.0084,
     "dw_T_pct": 4.0, "dw_S_pct": 3.97,
     "dx_T_mm": -0.0368, "dx_S_mm": 0.0041},
    {"element": "M2", "s_mm": 372.07,
     "w_1064_T_mm": 0.1985, "w_1064_S_mm": 0.1990,
     "x_1064_T_mm": 0.0, "x_1064_S_mm": 0.0,
     "w_633_T_mm": null, "w_633_S_mm": null,
     "x_633_T_mm": null, "x_633_S_mm": null,
     "dw_T_mm": null, "dw_S_mm": null,
     "dw_T_pct": null, "dw_S_pct": null,
     "dx_T_mm": null, "dx_S_mm": null,
     "note": "no red beam value at this aperture"}
  ],
  "warnings": []
})JSON";

const TableFunction::Result* findRow(const BeamParamsAtElemsFunction& func,
                                     const QString& label,
                                     TableFunction::ResultPosition pos = TableFunction::ResultPosition::ELEMENT)
{
    for (const auto& res : func.results())
    {
        if (res.element && res.element->label() == label
                && res.position == pos)
            return &res;
    }
    return nullptr;
}

} // namespace

TEST_METHOD(lidt_parse_marks_only_warn_fail)
{
    const auto marks = parseLidtReport(jsonFromText(LIDT_REPORT));
    ASSERT_EQ_INT(marks.size(), 2)
    ASSERT_IS_TRUE(marks.contains(QStringLiteral("M1")))
    ASSERT_IS_TRUE(marks.contains(QStringLiteral("M2")))
    // ok / nodata LIDT entries and other check kinds never mark.
    ASSERT_IS_FALSE(marks.contains(QStringLiteral("M3")))
    ASSERT_IS_FALSE(marks.contains(QStringLiteral("M4")))

    const LidtMark& m1 = marks[QStringLiteral("M1")];
    ASSERT_IS_TRUE(m1.isFail())
    ASSERT_NEAR_DBL(m1.fluence, 6.1755, 1e-9)
    ASSERT_NEAR_DBL(m1.limit, 5.0, 1e-9)
    ASSERT_NEAR_DBL(m1.ratio(), 1.2351, 1e-4)
    ASSERT_IS_TRUE(m1.tooltip().contains(QStringLiteral("1.24")))

    const LidtMark& m2 = marks[QStringLiteral("M2")];
    ASSERT_IS_TRUE(m2.isWarn())
    ASSERT_IS_FALSE(m2.isFail())
    ASSERT_NEAR_DBL(m2.ratio(), 0.84, 1e-9)
}

TEST_METHOD(lidt_parse_empty_report)
{
    ASSERT_EQ_INT(parseLidtReport(QJsonObject()).size(), 0)
    ASSERT_EQ_INT(parseLidtReport(jsonFromText(R"JSON({"version": 1, "checks": []})JSON")).size(), 0)
}

TEST_METHOD(lidt_eng_path)
{
    ASSERT_EQ_STR(engPathForRez(QStringLiteral("/x/cavity.rez")),
                  QStringLiteral("/x/cavity.rez.eng.json"))
}

TEST_METHOD(redlight_parse_fallback)
{
    const RedlightReport report = parseRedlightReport(jsonFromText(REDLIGHT_REPORT));
    ASSERT_IS_TRUE(report.ok)
    ASSERT_IS_TRUE(report.isFallback())
    ASSERT_EQ_STR(report.path, QStringLiteral("fallback"))
    ASSERT_NEAR_DBL(report.redNm, 632.8, 1e-9)
    ASSERT_NEAR_DBL(report.hotNm, 1064.0, 1e-9)
    ASSERT_EQ_INT(report.rows.size(), 3)
    ASSERT_IS_TRUE(report.modeLabel().contains(QStringLiteral("632.8")))

    const RedlightRow& m1 = report.rows[QStringLiteral("M1")];
    ASSERT_NEAR_DBL(m1.w633T, 0.1040, 1e-9)
    ASSERT_NEAR_DBL(m1.w633S, 0.1050, 1e-9)
    ASSERT_NEAR_DBL(m1.x633T, -0.0177, 1e-9)
    ASSERT_NEAR_DBL(m1.w1064T, 0.1000, 1e-9)

    // A row with null red values keeps NaN radii instead of
    // failing the whole report.
    const RedlightRow& m2 = report.rows[QStringLiteral("M2")];
    ASSERT_IS_TRUE(std::isnan(m2.w633T))
    ASSERT_IS_TRUE(std::isnan(m2.x633T))
    ASSERT_NEAR_DBL(m2.w1064T, 0.1985, 1e-9)
}

TEST_METHOD(redlight_parse_rejects_bad_reports)
{
    ASSERT_IS_FALSE(parseRedlightReport(QJsonObject()).ok)
    ASSERT_IS_FALSE(parseRedlightReport(jsonFromText(
        R"JSON({"path": "sideways", "table": []})JSON")).ok)
    const RedlightReport cold = parseRedlightReport(jsonFromText(
        R"JSON({"path": "cold_eigenmode", "table": []})JSON"));
    ASSERT_IS_TRUE(cold.ok)
    ASSERT_IS_FALSE(cold.isFallback())
    ASSERT_IS_TRUE(cold.modeLabel().contains(QStringLiteral("冷腔本征模")))
}

TEST_METHOD(beam_params_redlight_overlay)
{
    bool oldSkip = AppSettings::instance().skipFuncWindowsLoading;
    AppSettings::instance().skipFuncWindowsLoading = true;
    TEST_FILE(fullFileName, "calc_beamdata_elems_sw.rez")
    Schema schema;
    SchemaReaderJson reader(&schema);
    reader.readFromFile(fullFileName);
    AppSettings::instance().skipFuncWindowsLoading = oldSkip;
    ASSERT_IS_FALSE(reader.report().hasErrors())

    BeamParamsAtElemsFunction func(&schema);
    func.calculate();
    ASSERT_IS_TRUE(func.ok())
    ASSERT_EQ_INT(func.columns().size(), 4)
    const TableFunction::Result* m1 = findRow(func, QStringLiteral("M1"));
    ASSERT_IS_TRUE(m1 != nullptr)
    ASSERT_EQ_INT(m1->values.size(), 4)
    // Normal mode: hot eigenmode values, axis offset zero.
    const double hotWT = m1->values.at(0).T;
    const double hotWS = m1->values.at(0).S;
    ASSERT_IS_TRUE(hotWT > 0)
    ASSERT_NEAR_DBL(m1->values.at(3).T, 0.0, 1e-12)
    ASSERT_NEAR_DBL(m1->values.at(3).S, 0.0, 1e-12)

    // Red-light mode: W and X come from the report, R and V are N/A.
    const RedlightReport report = parseRedlightReport(jsonFromText(REDLIGHT_REPORT));
    ASSERT_IS_TRUE(report.ok)
    func.setRedlightData(report);
    ASSERT_IS_TRUE(func.redlightMode())
    ASSERT_EQ_STR(func.redlightPath(), QStringLiteral("fallback"))
    func.calculate();
    ASSERT_IS_TRUE(func.ok())
    m1 = findRow(func, QStringLiteral("M1"));
    ASSERT_IS_TRUE(m1 != nullptr)
    ASSERT_NEAR_DBL(m1->values.at(0).T, 0.1040, 1e-9)
    ASSERT_NEAR_DBL(m1->values.at(0).S, 0.1050, 1e-9)
    ASSERT_IS_TRUE(std::isnan(m1->values.at(1).T))
    ASSERT_IS_TRUE(std::isnan(m1->values.at(2).S))
    ASSERT_NEAR_DBL(m1->values.at(3).T, -0.0177, 1e-9)
    ASSERT_NEAR_DBL(m1->values.at(3).S, 0.002, 1e-9)

    // A row with no red value renders as N/A everywhere.
    // M2 is a middle mirror: it has LEFT/RIGHT rows, no ELEMENT row.
    const TableFunction::Result* m2 = findRow(func, QStringLiteral("M2"),
                                              TableFunction::ResultPosition::RIGHT);
    ASSERT_IS_TRUE(m2 != nullptr)
    ASSERT_IS_TRUE(std::isnan(m2->values.at(0).T))
    ASSERT_IS_TRUE(std::isnan(m2->values.at(3).T))

    // Clearing the overlay restores the hot values exactly.
    func.clearRedlightData();
    ASSERT_IS_FALSE(func.redlightMode())
    func.calculate();
    ASSERT_IS_TRUE(func.ok())
    m1 = findRow(func, QStringLiteral("M1"));
    ASSERT_IS_TRUE(m1 != nullptr)
    ASSERT_NEAR_DBL(m1->values.at(0).T, hotWT, 1e-12)
    ASSERT_NEAR_DBL(m1->values.at(0).S, hotWS, 1e-12)
    ASSERT_NEAR_DBL(m1->values.at(3).T, 0.0, 1e-12)
}

TEST_METHOD(lidt_runner_real_backend_smoke)
{
    // End-to-end smoke: the async runner against the real Python
    // backend on the user's cavity + the Phase 4 example side-car.
    // Skipped when REZONATOR_ENGINEERING_DIR is not set (same
    // convention as the EngineeringHub smoke test).
    const QString engDir = qEnvironmentVariable("REZONATOR_ENGINEERING_DIR");
    if (engDir.isEmpty())
        return;
    const QString rez = QStringLiteral(
        "/home/hatch/workspace/user/files/upload.rez");
    const QString eng = QDir(engDir).filePath(
        QStringLiteral("tests/data/example-phase4.eng.json"));
    if (!QFileInfo::exists(rez) || !QFileInfo::exists(eng))
        return;

    LidtCheckRunner runner;
    QMap<QString, LidtMark> marks;
    QString failure;
    QEventLoop loop;
    QTimer watchdog;
    watchdog.setSingleShot(true);
    QObject::connect(&watchdog, &QTimer::timeout, &loop, &QEventLoop::quit);
    QObject::connect(&runner, &LidtCheckRunner::finished,
                     [&](const QMap<QString, LidtMark>& result) {
                         marks = result;
                         loop.quit();
                     });
    QObject::connect(&runner, &LidtCheckRunner::failed,
                     [&](const QString& error) {
                         failure = error;
                         loop.quit();
                     });
    watchdog.start(120000);
    runner.run(rez, eng);
    loop.exec();
    ASSERT_IS_TRUE(failure.isEmpty())
    // Example side-car: only M1 (SESAM) exceeds its example LIDT.
    ASSERT_EQ_INT(marks.size(), 1)
    ASSERT_IS_TRUE(marks.contains(QStringLiteral("M1")))
    const LidtMark& m1 = marks[QStringLiteral("M1")];
    ASSERT_IS_TRUE(m1.isFail())
    ASSERT_NEAR_DBL(m1.fluence, 6.1755, 1e-3)
    ASSERT_NEAR_DBL(m1.limit, 5.0, 1e-9)
    ASSERT_NEAR_DBL(m1.ratio(), 1.2351, 1e-3)
}

TEST_GROUP("LidtRedlight",
    ADD_TEST(lidt_parse_marks_only_warn_fail),
    ADD_TEST(lidt_parse_empty_report),
    ADD_TEST(lidt_eng_path),
    ADD_TEST(redlight_parse_fallback),
    ADD_TEST(redlight_parse_rejects_bad_reports),
    ADD_TEST(beam_params_redlight_overlay),
    ADD_TEST(lidt_runner_real_backend_smoke),
)
} // namespace LidtRedlightTests
} // namespace Tests
} // namespace Z
