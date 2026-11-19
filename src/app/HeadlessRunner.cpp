#include "HeadlessRunner.h"

#include "../core/Element.h"
#include "../core/Elements.h"
#include "../core/Parameters.h"
#include "../core/Report.h"
#include "../core/Schema.h"
#include "../core/Values.h"
#include "../io/SchemaReaderJson.h"
#include "../math/BeamCalculator.h"
#include "../math/MisalignmentCalculator.h"

#include <QDebug>
#include <QFile>
#include <QJsonArray>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QMap>
#include <QSet>
#include <QStringList>

#include <cmath>
#include <complex>
#include <cstdio>
#include <memory>
#include <optional>
#include <vector>

#ifdef Q_OS_WIN
#include <windows.h>
#endif

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

namespace {

// All Qt logging (qDebug/qWarning from the app and third-party code) must
// go to stderr: stdout carries exactly one JSON object.
void headlessMessageHandler(QtMsgType type, const QMessageLogContext& context, const QString& message)
{
    Q_UNUSED(type)
    Q_UNUSED(context)
    std::fprintf(stderr, "%s\n", qPrintable(message));
    std::fflush(stderr);
}

void printError(const QString& message)
{
    std::fprintf(stderr, "headless: %s\n", qPrintable(message));
    std::fflush(stderr);
}

/// JSON number for a double, or null when it is not finite.
/// Non-finite values must never reach the output JSON.
QJsonValue jsonDouble(double value)
{
    return std::isfinite(value) ? QJsonValue(value) : QJsonValue::Null;
}

/// JSON number for a wavefront ROC in mm, or null when it is not finite
/// or absurdly large. At a waist the exact value is infinite, but floating
/// point gives ~1e17 mm instead; anything beyond 1e9 mm (1000 km) is
/// physically a flat wavefront, so report it as null.
QJsonValue jsonRadiusMm(double valueMm)
{
    return (std::isfinite(valueMm) && std::fabs(valueMm) <= 1e9)
        ? QJsonValue(valueMm) : QJsonValue::Null;
}

//------------------------------------------------------------------------------
//                              Waist derivation
//------------------------------------------------------------------------------

// Derives the beam-segment waist from the radius w and the wavefront ROC R
// measured at one plane, using 1/q = 1/R - i*lambda/(pi*w^2) (see protocol §4).
// The result is the waist of the beam segment containing that plane: w0 is
// unchanged by free-space propagation but changes across a focusing element.
// R must be finite; R == inf (flat wavefront) is passed as NaN here and
// means 1/R == 0. Returns false when the waist cannot be derived.
bool waistFromPlane(double w, double r, double lambdaSi, double& w0, double& z)
{
    if (!(w > 0.0) || !std::isfinite(w) || !(lambdaSi > 0.0))
        return false;
    double invR = std::isfinite(r) ? 1.0 / r : 0.0;
    if (invR == 0.0 && r == 0.0)
        return false; // R == 0: point focus at the plane, no meaningful waist
    std::complex<double> invQ(invR, -lambdaSi / (M_PI * w * w));
    if (invQ == std::complex<double>(0.0, 0.0))
        return false;
    std::complex<double> q = 1.0 / invQ;
    double zR = q.imag();
    if (!(zR > 0.0) || !std::isfinite(zR) || !std::isfinite(q.real()))
        return false;
    w0 = std::sqrt(lambdaSi * zR / M_PI);
    z = q.real();
    return std::isfinite(w0);
}

//------------------------------------------------------------------------------
//                              Request model
//------------------------------------------------------------------------------

struct ResolvedOverride
{
    Z::Parameter* param = nullptr;
    double valueSi = 0;
};

struct Mutation
{
    QJsonValue id;
    // Filled by resolveMutation(); empty when the mutation failed to resolve.
    std::vector<ResolvedOverride> resolved;
    QString error; // non-empty when the mutation must fail as a whole
    // Resolved misalignment tilts (mirror element -> delta tilt, radians,
    // unfolded frame). Empty when the mutation does not request an axis;
    // `wantsAxis` is true exactly when a `misalign` field was present.
    QMap<Element*, MisalignmentCalculator::Tilt> misalign;
    bool wantsAxis = false;
};

} // namespace

//------------------------------------------------------------------------------
//                              runHeadless
//------------------------------------------------------------------------------

int runHeadless()
{
    qInstallMessageHandler(headlessMessageHandler);

#ifdef Q_OS_WIN
    // Best effort: keep console output UTF-8 so Chinese labels survive
    // when stdout is shown on a console. Piped bytes are unaffected.
    SetConsoleOutputCP(CP_UTF8);
#endif

    // --- Read the whole request from stdin (bytes, no decoding yet) ---
    QFile stdinFile;
    if (!stdinFile.open(stdin, QIODevice::ReadOnly))
    {
        printError(QStringLiteral("cannot read stdin"));
        return 2;
    }
    QByteArray requestBytes = stdinFile.readAll();
    stdinFile.close();

    QJsonParseError parseError;
    QJsonDocument requestDoc = QJsonDocument::fromJson(requestBytes, &parseError);
    if (requestDoc.isNull() || !requestDoc.isObject())
    {
        printError(QStringLiteral("invalid request JSON: %1").arg(parseError.errorString()));
        return 2;
    }
    QJsonObject request = requestDoc.object();
    if (!request.contains(QStringLiteral("base_schema"))
        || !request.value(QStringLiteral("base_schema")).isObject())
    {
        printError(QStringLiteral("request must contain a 'base_schema' object"));
        return 2;
    }
    QJsonObject baseSchemaJson = request.value(QStringLiteral("base_schema")).toObject();

    QJsonArray mutationsJson;
    if (request.contains(QStringLiteral("mutations")))
    {
        if (!request.value(QStringLiteral("mutations")).isArray())
        {
            printError(QStringLiteral("'mutations' must be an array"));
            return 2;
        }
        mutationsJson = request.value(QStringLiteral("mutations")).toArray();
    }
    // No (or empty) mutations list: evaluate the base schema once, id 0.
    std::vector<Mutation> mutations;
    if (mutationsJson.isEmpty())
    {
        Mutation m;
        m.id = QJsonValue(0);
        mutations.push_back(std::move(m));
    }
    else
    {
        for (const auto& item : mutationsJson)
        {
            if (!item.isObject())
            {
                printError(QStringLiteral("each mutation must be an object"));
                return 2;
            }
            Mutation m;
            QJsonObject obj = item.toObject();
            m.id = obj.contains(QStringLiteral("id")) ? obj.value(QStringLiteral("id"))
                                                       : QJsonValue::Null;
            if (obj.contains(QStringLiteral("overrides"))
                && !obj.value(QStringLiteral("overrides")).isObject())
            {
                printError(QStringLiteral("mutation 'overrides' must be an object"));
                return 2;
            }
            if (obj.contains(QStringLiteral("misalign"))
                && !obj.value(QStringLiteral("misalign")).isObject())
            {
                printError(QStringLiteral("mutation 'misalign' must be an object"));
                return 2;
            }
            mutations.push_back(std::move(m));
        }
    }

    // --- Load the base schema (once) with the app's own reader ---
    Schema schema;
    SchemaReaderJson reader(&schema);
    reader.skipFuncWindows = true;
    reader.readFromUtf8(QJsonDocument(baseSchemaJson).toJson(QJsonDocument::Compact));
    if (reader.report().hasErrors())
    {
        printError(QStringLiteral("failed to load base_schema: %1")
            .arg(reader.report().str()));
        return 1;
    }

    QStringList warnings;
    for (const auto& event : reader.report().events())
        if (event.type() == Z::Report::Event::Warning)
            warnings << event.message();

    // Duplicate labels: overrides address elements by label, first match wins.
    {
        QSet<QString> seenLabels, dupLabels;
        for (Element* elem : schema.elements())
        {
            if (seenLabels.contains(elem->label()))
                dupLabels.insert(elem->label());
            else
                seenLabels.insert(elem->label());
        }
        for (const QString& label : dupLabels)
            warnings << QStringLiteral(
                "duplicate element label '%1' (overrides use the first match)").arg(label);
    }

    Elements activeElems = schema.activeElements();
    if (activeElems.isEmpty())
    {
        printError(QStringLiteral("base_schema has no active elements"));
        return 1;
    }
    const bool isResonator = schema.isResonator();
    const double lambdaSi = schema.wavelenSi();

    // --- One BeamCalculator per active element (built once, reused) ---
    struct ElemCalc
    {
        Element* element = nullptr;
        std::unique_ptr<BeamCalculator> calc;
    };
    std::vector<ElemCalc> elemCalcs;
    for (Element* elem : activeElems)
    {
        auto calc = std::make_unique<BeamCalculator>(&schema);
        if (!calc->ok())
        {
            printError(QStringLiteral("cannot create beam calculator for element '%1': %2")
                .arg(elem->label(), calc->error()));
            return 1;
        }
        calc->calcRoundTrip(elem, false, "HeadlessRunner");
        elemCalcs.push_back({ elem, std::move(calc) });
    }
    std::unique_ptr<BeamCalculator> stabCalc;
    if (isResonator)
    {
        stabCalc = std::make_unique<BeamCalculator>(&schema);
        if (!stabCalc->ok())
        {
            printError(QStringLiteral("cannot create stability calculator: %1")
                .arg(stabCalc->error()));
            return 1;
        }
        stabCalc->calcRoundTrip(activeElems.first(), false, "HeadlessRunner");
    }

    // For single-pass schemas the "beam radius" only exists for Gaussian
    // pumps: a ray-vector pump has no beam radius, its BeamCalculator
    // returns the ray height instead (which may even be negative).
    bool beamAvailable = true;
    if (!isResonator)
    {
        auto* pumpCalc = elemCalcs.front().calc->pumpCalc();
        beamAvailable = pumpCalc && pumpCalc->isGauss();
        if (!beamAvailable)
            warnings << QStringLiteral(
                "single-pass schema uses a ray-vector pump: no Gaussian beam radii");
    }

    // --- Resolve all mutations up front (validate, collect lock targets) ---
    // Resolution is per mutation; a mutation with any bad override fails
    // as a whole (nothing is applied for it).
    auto resolveMutation = [&](const QJsonObject& mutObj, Mutation& mut) {
        if (mutObj.contains(QStringLiteral("overrides")))
        {
        QJsonObject overrides = mutObj.value(QStringLiteral("overrides")).toObject();
        for (auto it = overrides.constBegin(); it != overrides.constEnd(); ++it)
        {
            const QString label = it.key();
            if (!it.value().isObject())
            {
                mut.error = QStringLiteral("overrides for element '%1' must be an object").arg(label);
                return;
            }
            Element* elem = schema.element(label);
            if (!elem)
            {
                mut.error = QStringLiteral("unknown element '%1'").arg(label);
                return;
            }
            if (elem->disabled())
            {
                mut.error = QStringLiteral("element '%1' is disabled").arg(label);
                return;
            }
            QJsonObject params = it.value().toObject();
            for (auto pit = params.constBegin(); pit != params.constEnd(); ++pit)
            {
                const QString alias = pit.key();
                if (!pit.value().isDouble())
                {
                    mut.error = QStringLiteral("override value for '%1.%2' must be a number")
                        .arg(label, alias);
                    return;
                }
                double value = pit.value().toDouble();
                if (!std::isfinite(value))
                {
                    mut.error = QStringLiteral("override value for '%1.%2' is not finite")
                        .arg(label, alias);
                    return;
                }
                Z::Parameter* param = elem->param(alias);
                if (!param)
                {
                    mut.error = QStringLiteral("unknown parameter '%1' on element '%2'")
                        .arg(alias, label);
                    return;
                }
                // A driven parameter is owned by its driver: an external
                // override would be overwritten on recalc, so refuse it
                // instead of silently computing with a wrong value.
                if (param->valueDriver() != Z::ParamValueDriver::None)
                {
                    const QString driver = param->valueDriver() == Z::ParamValueDriver::Link
                        ? QStringLiteral("a link") : QStringLiteral("a formula");
                    mut.error = QStringLiteral("parameter '%1.%2' is driven by %3")
                        .arg(label, alias, driver);
                    return;
                }
                double valueSi = param->value().unit()->toSi(value);
                if (!std::isfinite(valueSi))
                {
                    mut.error = QStringLiteral("override value for '%1.%2' is not finite after unit conversion")
                        .arg(label, alias);
                    return;
                }
                // Guards copied from OptimizerFunction::validate():
                // lengths must stay >= 1 um, curvature/focal values must
                // not be zero (they are divided by in element matrices).
                if (alias == QLatin1String("L") && valueSi < 1e-6)
                {
                    mut.error = QStringLiteral("length '%1.%2' must be >= 1 um").arg(label, alias);
                    return;
                }
                if ((alias == QLatin1String("R") || alias == QLatin1String("F")) && valueSi == 0.0)
                {
                    mut.error = QStringLiteral("parameter '%1.%2' must not be zero").arg(label, alias);
                    return;
                }
                mut.resolved.push_back({ param, valueSi });
            }
        }
        } // no `overrides`: evaluate the base values

        // --- Misalignment tilts (optional per-mutation axis request) ---
        // {"label": {"dT_mrad": <number>, "dS_mrad": <number>}}: delta
        // tilts of mirrors, milliradians, in the unfolded frame
        // (see protocol §12). Both components are optional, default 0.
        if (!mutObj.contains(QStringLiteral("misalign")))
            return;
        mut.wantsAxis = true;
        if (!isResonator)
        {
            mut.error = QStringLiteral(
                "misalignment axis requires a resonator (SW or RR); "
                "single-pass schemas have no round-trip axis");
            return;
        }
        QJsonObject misalign = mutObj.value(QStringLiteral("misalign")).toObject();
        for (auto it = misalign.constBegin(); it != misalign.constEnd(); ++it)
        {
            const QString label = it.key();
            if (!it.value().isObject())
            {
                mut.error = QStringLiteral("misalign for element '%1' must be an object")
                    .arg(label);
                return;
            }
            Element* elem = schema.element(label);
            if (!elem)
            {
                mut.error = QStringLiteral("unknown element '%1'").arg(label);
                return;
            }
            if (elem->disabled())
            {
                mut.error = QStringLiteral("element '%1' is disabled").arg(label);
                return;
            }
            if (!MisalignmentCalculator::isMirror(elem))
            {
                mut.error = QStringLiteral(
                    "element '%1' is not a mirror; a misalignment tilt "
                    "applies to flat/curved mirrors only").arg(label);
                return;
            }
            MisalignmentCalculator::Tilt tilt;
            QJsonObject t = it.value().toObject();
            for (auto tit = t.constBegin(); tit != t.constEnd(); ++tit)
            {
                const QString key = tit.key();
                if (key != QLatin1String("dT_mrad") && key != QLatin1String("dS_mrad"))
                {
                    mut.error = QStringLiteral("unknown misalignment key '%1' on element '%2' "
                        "(expected 'dT_mrad' / 'dS_mrad')").arg(key, label);
                    return;
                }
                if (!tit.value().isDouble() || !std::isfinite(tit.value().toDouble()))
                {
                    mut.error = QStringLiteral("misalignment value '%1.%2' must be a finite number")
                        .arg(label, key);
                    return;
                }
                double rad = tit.value().toDouble() * 1e-3; // mrad -> rad
                if (key == QLatin1String("dT_mrad"))
                    tilt.dT = rad;
                else
                    tilt.dS = rad;
            }
            mut.misalign.insert(elem, tilt);
        }
    };

    for (int i = 0; i < mutationsJson.size(); i++)
        resolveMutation(mutationsJson.at(i).toObject(), mutations[i]);

    // --- One MisalignmentCalculator per active element, only when asked ---
    // Built lazily: requests without `misalign` behave exactly as before
    // (and single-pass schemas never get here: `misalign` on them fails
    // per mutation in resolveMutation()).
    struct ElemAxisCalc
    {
        Element* element = nullptr;
        std::unique_ptr<MisalignmentCalculator> calc;
    };
    std::vector<ElemAxisCalc> axisCalcs;
    bool anyWantsAxis = false;
    for (const auto& mut : mutations)
        if (mut.wantsAxis)
            anyWantsAxis = true;
    if (anyWantsAxis && isResonator)
    {
        for (Element* elem : activeElems)
        {
            auto calc = std::make_unique<MisalignmentCalculator>(&schema, elem);
            if (!calc->ok())
            {
                printError(QStringLiteral("cannot create misalignment calculator for element '%1': %2")
                    .arg(elem->label(), calc->error()));
                return 1;
            }
            axisCalcs.push_back({ elem, std::move(calc) });
        }
    }

    // Lock + back up every parameter any mutation touches (optimizer pattern:
    // events locked, original values restored when the backups are destroyed).
    std::vector<std::unique_ptr<ElementEventsLocker>> locks;
    std::vector<std::unique_ptr<Z::ParamValueBackup>> backups;
    {
        QSet<Z::Parameter*> seenParams;
        for (auto& mut : mutations)
            for (auto& ov : mut.resolved)
                if (!seenParams.contains(ov.param))
                {
                    seenParams.insert(ov.param);
                    locks.emplace_back(new ElementEventsLocker(ov.param, "HeadlessRunner"));
                    backups.emplace_back(new Z::ParamValueBackup(ov.param, "HeadlessRunner"));
                }
    }

    auto totalLengthMm = [&]() {
        double totalSi = 0.0;
        for (Element* elem : activeElems)
            if (auto* p = elem->param(QStringLiteral("L")))
                totalSi += p->value().toSi();
        return totalSi * 1e3;
    };

    // --- Evaluate every mutation in-process ---
    // A null axis is reported once in the top-level warnings (singular
    // solve at g = +/-1, or a complex round-trip matrix), it is not a
    // mutation failure.
    bool axisWarned = false;
    QJsonArray results;
    for (auto& mut : mutations)
    {
        QJsonObject result;
        result[QStringLiteral("id")] = mut.id;
        auto fail = [&](const QString& error) {
            result[QStringLiteral("ok")] = false;
            result[QStringLiteral("error")] = error;
            result[QStringLiteral("g_T")] = QJsonValue::Null;
            result[QStringLiteral("g_S")] = QJsonValue::Null;
            result[QStringLiteral("stable")] = QJsonValue::Null;
            result[QStringLiteral("total_length_mm")] = QJsonValue::Null;
            result[QStringLiteral("beam")] = QJsonValue::Null;
            result[QStringLiteral("waist")] = QJsonValue::Null;
            result[QStringLiteral("axis")] = QJsonValue::Null;
            results.append(result);
        };
        if (!mut.error.isEmpty())
        {
            fail(mut.error);
            continue;
        }
        for (auto& ov : mut.resolved)
            Z::Param::setSi(ov.param, ov.valueSi);

        double gT = qQNaN(), gS = qQNaN();
        bool stable = false;
        if (isResonator)
        {
            stabCalc->multMatrix("HeadlessRunner");
            stabCalc->setPlane(Z::T);
            gT = stabCalc->stability_normal();
            stabCalc->setPlane(Z::S);
            gS = stabCalc->stability_normal();
            if (!std::isfinite(gT) || !std::isfinite(gS))
            {
                fail(QStringLiteral("non-finite stability (g_T=%1, g_S=%2)")
                    .arg(gT).arg(gS));
                continue;
            }
            stable = (qAbs(gT) < 1.0 && qAbs(gS) < 1.0);
        }

        result[QStringLiteral("ok")] = true;
        result[QStringLiteral("error")] = QJsonValue::Null;
        result[QStringLiteral("g_T")] = isResonator ? jsonDouble(gT) : QJsonValue::Null;
        result[QStringLiteral("g_S")] = isResonator ? jsonDouble(gS) : QJsonValue::Null;
        result[QStringLiteral("stable")] = isResonator ? QJsonValue(stable) : QJsonValue::Null;
        result[QStringLiteral("total_length_mm")] = totalLengthMm();

        // --- Optical axis under the requested mirror tilts ---
        // Computed even for unstable cavities (the axis needs no
        // eigenmode, only a non-singular solve); parallel to `beam`.
        // Not requested -> null. Singular/complex -> null + one warning.
        if (mut.wantsAxis && isResonator && !axisCalcs.empty())
        {
            QJsonArray axisArr;
            bool axisOk = true;
            QString axisProblem;
            for (auto& ac : axisCalcs)
            {
                ac.calc->multMatrix("HeadlessRunner");
                MisalignmentCalculator::AxisResult ar = ac.calc->calcAxis(mut.misalign);
                if (!ar.ok)
                {
                    axisOk = false;
                    axisProblem = ar.singular
                        ? QStringLiteral("axis is singular (cavity at g = +/-1), no unique axis")
                        : ar.error;
                    break;
                }
                QJsonObject a;
                a[QStringLiteral("label")] = ac.element->label();
                a[QStringLiteral("x_T_mm")] = ar.xT * 1e3;
                a[QStringLiteral("th_T_mrad")] = ar.thT * 1e3;
                a[QStringLiteral("x_S_mm")] = ar.xS * 1e3;
                a[QStringLiteral("th_S_mrad")] = ar.thS * 1e3;
                axisArr.append(a);
            }
            if (axisOk)
            {
                result[QStringLiteral("axis")] = axisArr;
            }
            else
            {
                result[QStringLiteral("axis")] = QJsonValue::Null;
                if (!axisWarned)
                {
                    axisWarned = true;
                    warnings << axisProblem;
                }
            }
        }
        else
        {
            result[QStringLiteral("axis")] = QJsonValue::Null;
        }

        if (isResonator && !stable)
        {
            // Unstable: no eigenmode exists, beam radii are undefined.
            // This is a valid answer, not an error.
            result[QStringLiteral("beam")] = QJsonValue::Null;
            result[QStringLiteral("waist")] = QJsonValue::Null;
            results.append(result);
            continue;
        }

        if (!beamAvailable)
        {
            // Ray-vector pump (single-pass): no Gaussian beam to report.
            result[QStringLiteral("beam")] = QJsonValue::Null;
            result[QStringLiteral("waist")] = QJsonValue::Null;
            results.append(result);
            continue;
        }

        QJsonArray beamArr;
        bool beamOk = true;
        QString beamError;
        double firstWT = qQNaN(), firstWS = qQNaN();
        double firstRT = qQNaN(), firstRS = qQNaN();
        for (size_t i = 0; i < elemCalcs.size(); i++)
        {
            auto& ec = elemCalcs[i];
            ec.calc->multMatrix("HeadlessRunner");
            ec.calc->setPlane(Z::T);
            BeamResult resT = ec.calc->calc();
            ec.calc->setPlane(Z::S);
            BeamResult resS = ec.calc->calc();
            if (!std::isfinite(resT.beamRadius) || !std::isfinite(resS.beamRadius))
            {
                beamOk = false;
                beamError = QStringLiteral("non-finite beam radius at element '%1'")
                    .arg(ec.element->label());
                break;
            }
            QJsonObject b;
            b[QStringLiteral("label")] = ec.element->label();
            b[QStringLiteral("w_T_mm")] = resT.beamRadius * 1e3;
            b[QStringLiteral("w_S_mm")] = resS.beamRadius * 1e3;
            b[QStringLiteral("R_T_mm")] = jsonRadiusMm(resT.frontRadius * 1e3);
            b[QStringLiteral("R_S_mm")] = jsonRadiusMm(resS.frontRadius * 1e3);
            beamArr.append(b);
            if (i == 0)
            {
                firstWT = resT.beamRadius;
                firstWS = resS.beamRadius;
                firstRT = resT.frontRadius;
                firstRS = resS.frontRadius;
            }
        }
        if (!beamOk)
        {
            fail(beamError);
            continue;
        }
        result[QStringLiteral("beam")] = beamArr;

        // Waist derived from the first element's (w, R); see protocol §4.
        QJsonValue waist = QJsonValue::Null;
        double w0T = 0, zT = 0, w0S = 0, zS = 0;
        if (waistFromPlane(firstWT, firstRT, lambdaSi, w0T, zT)
            && waistFromPlane(firstWS, firstRS, lambdaSi, w0S, zS))
        {
            QJsonObject w;
            w[QStringLiteral("w0_T_mm")] = w0T * 1e3;
            w[QStringLiteral("w0_S_mm")] = w0S * 1e3;
            w[QStringLiteral("z_T_mm")] = zT * 1e3;
            w[QStringLiteral("z_S_mm")] = zS * 1e3;
            waist = w;
        }
        result[QStringLiteral("waist")] = waist;
        results.append(result);
    }

    QJsonObject response;
    response[QStringLiteral("version")] = 1;
    response[QStringLiteral("trip_type")] = TripTypes::info(schema.tripType()).alias();
    QJsonArray warningsJson;
    for (const QString& w : warnings)
        warningsJson.append(w);
    response[QStringLiteral("warnings")] = warningsJson;
    response[QStringLiteral("results")] = results;

    QByteArray out = QJsonDocument(response).toJson(QJsonDocument::Compact);
    out.append('\n');
    std::fwrite(out.constData(), 1, static_cast<size_t>(out.size()), stdout);
    std::fflush(stdout);
    return 0;
}
