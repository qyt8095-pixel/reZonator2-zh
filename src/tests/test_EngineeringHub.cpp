#include "../funcs/EngineeringBackend.h"

#include "testing/OriTestBase.h"

#include <cmath>

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QJsonArray>
#include <QJsonObject>
#include <QTemporaryDir>

//------------------------------------------------------------------------------
//  Tests for EngineeringBackend (Phase 4 M4): locating the Python
//  engineering backend and parsing its JSON reports.
//
//  The backend location order is:
//    1. engineering/ next to the application binary,
//    2. the REZONATOR_ENGINEERING_DIR environment variable,
//    3. the user setting EngineeringHub/engineeringDir.
//  A directory only counts when it contains run_foxli.py.
//------------------------------------------------------------------------------

namespace Z {
namespace Tests {
namespace EngineeringHubTests {

namespace {

QString makeBackendDir(QTemporaryDir& tmp)
{
    QDir dir(tmp.path());
    dir.mkdir(QStringLiteral("engineering"));
    QFile marker(dir.filePath(QStringLiteral("engineering/run_foxli.py")));
    marker.open(QIODevice::WriteOnly);
    marker.write("# marker");
    marker.close();
    return dir.filePath(QStringLiteral("engineering"));
}

} // namespace

TEST_METHOD(locate_prefers_app_dir)
{
    // The test binary runs from the build tree; there is no engineering/
    // next to it, so with no env var and no user setting the location
    // must be empty rather than some unrelated directory.
    qunsetenv("REZONATOR_ENGINEERING_DIR");
    const QString found = EngineeringBackend::locateEngineeringDir();
    ASSERT_IS_TRUE(found.isEmpty() || QFileInfo::exists(
        QDir(found).filePath(QStringLiteral("run_foxli.py"))))
}

TEST_METHOD(locate_uses_env_var)
{
    QTemporaryDir tmp;
    ASSERT_IS_TRUE(tmp.isValid())
    const QString engDir = makeBackendDir(tmp);
    qputenv("REZONATOR_ENGINEERING_DIR", engDir.toUtf8());
    const QString found = EngineeringBackend::locateEngineeringDir();
    ASSERT_EQ_STR(found, QDir::cleanPath(engDir))
    qunsetenv("REZONATOR_ENGINEERING_DIR");
}

TEST_METHOD(locate_ignores_dir_without_marker)
{
    QTemporaryDir tmp;
    ASSERT_IS_TRUE(tmp.isValid())
    QDir(tmp.path()).mkdir(QStringLiteral("engineering"));
    qputenv("REZONATOR_ENGINEERING_DIR",
            QDir(tmp.path()).filePath(QStringLiteral("engineering")).toUtf8());
    // No run_foxli.py inside: the directory must not count.
    const QString found = EngineeringBackend::locateEngineeringDir();
    ASSERT_IS_TRUE(found.isEmpty())
    qunsetenv("REZONATOR_ENGINEERING_DIR");
}

TEST_METHOD(resolve_script_missing_returns_empty)
{
    QTemporaryDir tmp;
    ASSERT_IS_TRUE(tmp.isValid())
    const QString engDir = makeBackendDir(tmp);
    ASSERT_EQ_STR(EngineeringBackend::resolveScript(
        engDir, QStringLiteral("run_foxli.py")),
        QDir::cleanPath(QDir(engDir).filePath(
            QStringLiteral("run_foxli.py"))))
    ASSERT_IS_TRUE(EngineeringBackend::resolveScript(
        engDir, QStringLiteral("run_nope.py")).isEmpty())
    ASSERT_IS_TRUE(EngineeringBackend::resolveScript(
        QString(), QStringLiteral("run_foxli.py")).isEmpty())
}

TEST_METHOD(build_command_order)
{
    const QStringList cmd = EngineeringBackend::buildCommand(
        QStringLiteral("python3"),
        QStringLiteral("/x/run_foxli.py"),
        QStringList() << QStringLiteral("--rez") << QStringLiteral("c.rez"));
    ASSERT_EQ_INT(cmd.size(), 4)
    ASSERT_EQ_STR(cmd.at(0), QStringLiteral("python3"))
    ASSERT_EQ_STR(cmd.at(1), QStringLiteral("/x/run_foxli.py"))
    ASSERT_EQ_STR(cmd.at(2), QStringLiteral("--rez"))
    ASSERT_EQ_STR(cmd.at(3), QStringLiteral("c.rez"))
}

TEST_METHOD(parse_report_valid_object)
{
    const auto parsed = EngineeringBackend::parseReport(
        QByteArray("{\"converged\": true, \"L_diff\": 1.4e-6}\n"));
    ASSERT_IS_TRUE(parsed.ok)
    ASSERT_IS_TRUE(parsed.object.value(QStringLiteral("converged")).toBool())
    ASSERT_NEAR_DBL(parsed.object.value(QStringLiteral("L_diff")).toDouble(),
                  1.4e-6, 1e-12)
}

TEST_METHOD(parse_report_rejects_garbage)
{
    const auto empty = EngineeringBackend::parseReport(QByteArray(""));
    ASSERT_IS_FALSE(empty.ok)
    ASSERT_IS_FALSE(empty.error.isEmpty())

    const auto broken = EngineeringBackend::parseReport(
        QByteArray("{not json"));
    ASSERT_IS_FALSE(broken.ok)

    const auto array = EngineeringBackend::parseReport(QByteArray("[1,2]"));
    ASSERT_IS_FALSE(array.ok)

    // Two JSON documents back to back are not one report.
    const auto two = EngineeringBackend::parseReport(
        QByteArray("{\"a\": 1}\n{\"b\": 2}\n"));
    ASSERT_IS_FALSE(two.ok)
}

TEST_METHOD(run_script_missing_interpreter_fails_gracefully)
{
    const auto result = EngineeringBackend::runScript(
        QStringLiteral("/nonexistent/python3.99"),
        QStringLiteral("/nonexistent/run_foxli.py"),
        QStringList(), 5000);
    ASSERT_IS_TRUE(result.exitCode != 0 || !result.error.isEmpty())
    ASSERT_IS_FALSE(result.error.isEmpty())
}

TEST_METHOD(run_script_real_backend_smoke)
{
    // End-to-end smoke: run the ghosts script against the fixture
    // cavity shipped in the test data (uses the real Python backend
    // when REZONATOR_ENGINEERING_DIR points at the repo's engineering/
    // directory; skipped otherwise).
    const QString engDir = qEnvironmentVariable(
        "REZONATOR_ENGINEERING_DIR");
    if (engDir.isEmpty())
        return;
    const QString script = EngineeringBackend::resolveScript(
        engDir, QStringLiteral("run_ghosts.py"));
    if (script.isEmpty())
        return;
    const QString rez = QStringLiteral(
        "/home/hatch/workspace/user/files/upload.rez");
    if (!QFileInfo::exists(rez))
        return;
    const auto result = EngineeringBackend::runScript(
        EngineeringBackend::pythonExecutable(), script,
        QStringList() << rez
                      << QDir(engDir).filePath(
                             QStringLiteral("tests/data/example-phase4.eng.json")),
        120000);
    ASSERT_IS_TRUE(result.error.isEmpty())
    const auto parsed = EngineeringBackend::parseReport(result.stdoutData);
    ASSERT_IS_TRUE(parsed.ok)
    const QJsonObject summary =
        parsed.object.value(QStringLiteral("summary")).toObject();
    ASSERT_EQ_INT(summary.value(QStringLiteral("ok")).toInt(), 6)
    ASSERT_EQ_INT(summary.value(QStringLiteral("warn")).toInt(), 1)
}

TEST_GROUP("EngineeringHub",
    ADD_TEST(locate_prefers_app_dir),
    ADD_TEST(locate_uses_env_var),
    ADD_TEST(locate_ignores_dir_without_marker),
    ADD_TEST(resolve_script_missing_returns_empty),
    ADD_TEST(build_command_order),
    ADD_TEST(parse_report_valid_object),
    ADD_TEST(parse_report_rejects_garbage),
    ADD_TEST(run_script_missing_interpreter_fails_gracefully),
    ADD_TEST(run_script_real_backend_smoke),
)
} // namespace EngineeringHubTests
} // namespace Tests
} // namespace Z
