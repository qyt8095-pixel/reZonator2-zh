#include "SchemaReaderJson.h"

#include "JsonUtils.h"
#include "ISchemaWindowStorable.h"
#include "../app/AppSettings.h"
#include "../core/Schema.h"
#include "../core/Elements.h"
#include "../core/ElementsCatalog.h"
#include "../core/ElementFormula.h"
#include "../windows/WindowsManager.h"

#include <QBuffer>
#include <QDebug>
#include <QFile>
#include <QJsonDocument>

namespace Z {
namespace IO {
namespace Json {

QString readParamValue(const QJsonObject& json, Parameter* param)
{
    auto res = readValue(json, param->dim());
    if (!res.ok())
        return QString("无法读取参数 '%1' 的值：%2").arg(param->alias(), res.error());
    param->setValue(res.value());
    return QString();
}

QString readParamValueTS(const QJsonObject& json, ParameterTS* param)
{
    auto res = readValueTS(json, param->dim());
    if (!res.ok())
        return QString("无法读取参数 '%1' 的值：%2").arg(param->alias(), res.error());
    param->setValue(res.value());
    return QString();
}

} // namespace Json
} // namespace IO
} // namespace Z

using namespace Z::IO::Json;

//------------------------------------------------------------------------------
//                           SchemaReaderJson
//------------------------------------------------------------------------------

void SchemaReaderJson::readFromFile(const QString& fileName)
{
    QFile file(fileName);
    if (!file.open(QIODevice::ReadOnly | QIODevice::Text))
    {
        qWarning() << "SchemaReaderJson::readFromFile" << fileName << file.errorString();
        return _report.error(QString("无法打开文件进行读取：%1").arg(file.errorString()));
    }
    readFromUtf8(file.readAll());
    file.close();
}

void SchemaReaderJson::readFromString(const QString& text)
{
    readFromUtf8(text.toUtf8());
}

void SchemaReaderJson::readFromUtf8(const QByteArray& data)
{
    QJsonParseError error;
    QJsonDocument doc = QJsonDocument::fromJson(data, &error);
    if (doc.isNull())
        return _report.error(QString("无法解析文件：%1").arg(error.errorString()));

    QJsonObject root = doc.object();

    Ori::Version version(root[JSON_KEY_VERSION].toString());
    if (version > Z::IO::Json::currentVersion())
        return _report.error(QString(
            "文件版本 %1 不受支持，最高支持版本：%2")
                .arg(version.str(), Z::IO::Json::currentVersion().str()));

    readGeneral(root);
    readGlobalParams(root);
    readPumps(root);
    readElements(root);
    readParamLinks(root);
    readFormulas(root);
    readMemos(root);

    if (!skipFuncWindows && !AppSettings::instance().skipFuncWindowsLoading)
        readWindows(root);
}

void SchemaReaderJson::readGeneral(const QJsonObject& root)
{
    _schema->setTitle(root["title"].toString());
    _schema->setNotes(root["notes"].toString());

    // Read trip type
    bool ok;
    auto tripTypeStr = root["trip_type"].toString();
    auto tripType = TripTypes::find(tripTypeStr, &ok);
    if (!ok)
        _report.warning(QString(
            "未知的光路图往返类型：'%1'，已改用 %2。")
                .arg(tripTypeStr, TripTypes::info(tripType).alias()));
    _schema->setTripType(tripType);

    // Read named parameters
    JsonValue paramsJson(root, "builtin_params", &_report);
    if (paramsJson)
    {
        // Read lambda
        JsonValue lambdaJson(paramsJson, "lambda", &_report);
        if (lambdaJson)
        {
            QString res = readParamValue(lambdaJson.obj(), &_schema->wavelength());
            if (!res.isEmpty())
                _report.warning(res);
        }
    }
}

void SchemaReaderJson::readGlobalParams(const QJsonObject& root)
{
    // Global parameters stored in the "custom_params" key for backward compatibility
    // Custom parameters used in elements stored in the "elem_custom_params" key
    JsonValue paramsJson(root, "custom_params", &_report);
    if (paramsJson)
    {
        const auto paramAliases = paramsJson.obj().keys();
        for (const QString& paramAlias : std::as_const(paramAliases))
        {
            JsonValue paramJson(paramsJson, paramAlias, &_report);
            if (paramJson)
            {
                readGlobalParam(paramJson.obj(), paramAlias);
            }
        }
    }
}

void SchemaReaderJson::readGlobalParam(const QJsonObject& root, const QString &alias)
{
    auto dimStr = root["dim"].toString();
    Z::Dim dim = Z::Dims::findByAlias(dimStr);
    if (!dim)
        return _report.warning(QString(
            "全局参数 '%2' 的量纲 '%1' 未知").arg(dimStr, alias));

    auto param = new Z::Parameter(
        dim,
        alias, // alias
        alias, // label
        alias, // name
        root["descr"].toString(),
        root["category"].toString(),
        true // visible
    );

    auto res = readParamValue(root, param);
    if (!res.isEmpty())
        _report.warning(QString("读取全局参数 '%1'：%2").arg(param->alias(), res));
        
    param->setExpr(root["expr"].toString());
    param->setError(root["error"].toString());

    _schema->addGlobalParam(param);
}

void SchemaReaderJson::readPumps(const QJsonObject& root)
{
    // Remove default pump
    qDeleteAll(*_schema->pumps());
    _schema->pumps()->clear();

    auto pumps = Z::IO::Json::readPumps(root, &_report);

    if (pumps.isEmpty())
    {
        if (_schema->isSP())
        {
            _report.warning("文件中没有泵浦，已创建默认泵浦。");
            _schema->pumps()->append(Pumps::allModes().first()->makePump());
        }
        else return;
    }

    for (auto pump : std::as_const(pumps))
        _schema->pumps()->append(pump);
}

void SchemaReaderJson::readElements(const QJsonObject& root)
{
    auto elems = Z::IO::Json::readElements(root, &_report);
    _schema->insertElements(elems, -1, Arg::RaiseEvents(false));
}

void SchemaReaderJson::readParamLinks(const QJsonObject& root)
{
    JsonValue linksJson(root, "param_links", &_report);
    if (linksJson)
        for (auto it = linksJson.array().begin(); it != linksJson.array().end(); it++)
            readParamLink((*it).toObject());
}

void SchemaReaderJson::readParamLink(const QJsonObject& root)
{
    auto targetElemIndex = root["target_elem"].toInt();
    auto targetElem = _schema->element(targetElemIndex);
    if (!targetElem)
        return _report.warning(QString(
            "无法加载链接：未找到索引为 %1 的元件").arg(targetElemIndex));

    auto targetParamAlias = root["target_param"].toString();
    auto targetParam = targetElem->params().byAlias(targetParamAlias);
    if (!targetParam)
        return _report.warning(QString(
            "无法加载链接：在元件 #%2 中未找到参数 '%1'")
                .arg(targetParamAlias, targetElem->displayLabel()));

    auto sourceParamAlias = root["source_param"].toString();
    auto sourceParam = _schema->globalParams()->byAlias(sourceParamAlias);
    if (!sourceParam)
        return _report.warning(QString(
            "无法加载链接：在自定义参数中未找到参数 '%1'").arg(sourceParamAlias));

    _schema->addParamLink(sourceParam, targetParam);
}

void SchemaReaderJson::readFormulas(const QJsonObject& root)
{
    JsonValue formulasJson(root, "formulas", &_report);
    if (formulasJson)
        for (auto it = formulasJson.array().begin(); it != formulasJson.array().end(); it++)
            readFormula((*it).toObject());
}

void SchemaReaderJson::readFormula(const QJsonObject& root)
{
    auto targetAlias = root["target_param"].toString();
    auto targetParam = _schema->globalParams()->byAlias(targetAlias);
    if (!targetParam)
        return _report.warning(QString(
            "未找到公式的目标参数 '%1'，已跳过该公式").arg(targetAlias));

    auto formula = new Z::Formula(targetParam);
    formula->setCode(root["code"].toString());

    auto globalParams = _schema->availableDependencySources();
    JsonValue depsJson(root, "param_deps", &_report);
    if (depsJson)
        for (auto it = depsJson.array().begin(); it != depsJson.array().end(); it++)
        {
            auto depAlias = (*it).toString();
            auto depParam = globalParams.byAlias(depAlias);
            if (!depParam)
            {
                _report.warning(QString(
                    "未找到公式（驱动参数 '%2'）所需的参数 '%1'")
                        .arg(depAlias, targetAlias));
                continue;
            }
            formula->addDep(depParam);
        }

    _schema->formulas()->put(formula);
}

void SchemaReaderJson::readWindows(const QJsonObject& root)
{
    JsonValue windowsJson(root, "windows", &_report);
    if (windowsJson)
        for (auto it = windowsJson.array().begin(); it != windowsJson.array().end(); it++)
            readWindow((*it).toObject());
}

void SchemaReaderJson::readWindow(const QJsonObject& root)
{
    auto type = root["type"].toString();
    if (type == "Multicaustic") type = "MultirangeCaustic";

    auto ctor = WindowsManager::getConstructor(type);
    if (!ctor)
        return _report.warning(QString(
            "无法加载未知类型 '%1' 的窗口，已跳过。").arg(type));

    SchemaWindow* window = ctor(_schema);
    ISchemaWindowStorable* storable = dynamic_cast<ISchemaWindowStorable*>(window);
    if (!storable)
    {
        _report.warning(QString(
            "文件中存储了类型为 '%1' 的窗口，但不知如何加载，已跳过。").arg(type));
        delete window;
        return;
    }

    Z::Report windowReport;
    if (storable->storableRead(root, &windowReport))
    {
        WindowsManager::instance().show(window);
        // Window will be recalculated on RecalRequred after loading is completed
        if (!windowReport.isEmpty())
        {
            _report.info(QString("加载类型为 '%1' 的窗口时有提示信息").arg(type));
            _report.report(windowReport);
        }
    }
    else
    {
        _report.warning(QString("无法加载类型为 '%1' 的窗口").arg(type));
        _report.report(windowReport);
        delete window;
    }
}

void SchemaReaderJson::readMemos(const QJsonObject& root)
{
    auto memosJson = root["memos"].toArray();
    for (auto it = memosJson.begin(); it != memosJson.end(); it++)
    {
        readMemo((*it).toObject());
        break; // only one memo at this time
    }
}

void SchemaReaderJson::readMemo(const QJsonObject& root)
{
    QString text;
    if (root.contains("text")) {
        text = root["text"].toString();
    } else {
        text = root["content"].toString();
        if (!text.isEmpty()) {
            auto res = QByteArray::fromBase64Encoding(text.toLatin1());
            if (res)
                text = QString::fromUtf8(res.decoded);
            else {
                _report.warning("无法从 base64 解码备忘录内容");
                return;
            }
        }
    }
    if (text.isEmpty()) return;

    _schema->memo = new SchemaMemo;
    _schema->memo->text = text;

    auto imagesIson = root["images"].toObject();
    auto it = imagesIson.constBegin();
    while (it != imagesIson.constEnd())
    {
        auto bytes = QByteArray::fromBase64(it.value().toString().toLatin1());
        QBuffer buf(&bytes);
        QImage img;
        if (!img.load(&buf, "png"))
            _report.warning(QString("无法为备忘录加载图片 %1").arg(it.key()));
        else
            _schema->memo->images[it.key()] = img;
        it++;
    }
}

namespace Z {
namespace IO {
namespace Json {

QList<Element*> readElements(const QJsonObject& root, Z::Report* report)
{
    QList<Element*> elems;
    JsonValue elemsJson(root, "elements", report);
    if (elemsJson)
        for (auto it = elemsJson.array().begin(); it != elemsJson.array().end(); it++)
        {
            auto elem = readElement((*it).toObject(), report);
            if (elem) elems << elem;
        }
    
    Ori::Version version(root[JSON_KEY_VERSION].toString());
    if (version <= Ori::Version(2, 0))
    {
        // Up to 2.0: 0 used instead of Inf for thick lens ROC
        // Since 2.1: Inf is used
        // Here we don't care if the parameter is linked to a global param
        // because there is no direct way to say the global param means "ROC"
        for (int i = 0; i < elems.size(); i++) {
            auto elem = elems.at(i);
            if (auto lens = dynamic_cast<ElemThickLens*>(elem); lens) {
                for (const auto *r : {"R1", "R2"}) {
                    if (auto p = lens->param(r); p) {
                        auto u = p->value().unit();
                        if (p->value().isZero())
                            p->setValue(Z::Value::inf(u));
                        else p->setValue(Z::Value(-p->value().value(), u));
                    } else {
                        report->warning(QString("元件 #%2 中应有参数 %1，但未找到").arg(r).arg(i));
                    }
                }
            } else if (auto intf = dynamic_cast<ElemSphericalInterface*>(elem); intf) {
                if (auto p = intf->param("R"); p) {
                    auto u = p->value().unit();
                    if (p->value().isZero())
                        p->setValue(Z::Value::inf(u));
                    else p->setValue(Z::Value(-p->value().value(), u));
                } else {
                    report->warning(QString("元件 #%1 中应有参数 R，但未找到").arg(i));
                }
            }
        }
    }
    
    return elems;
}

Element* readElement(const QJsonObject& root, Z::Report* report)
{
    auto elemType = root["type"].toString();
    auto elem = ElementsCatalog::instance().create(elemType);
    if (!elem)
    {
        report->warning(QString("未知元件类型 '%1'，已跳过该元件").arg(elemType));
        return nullptr;
    }

    // No need in locking element events here as all the schema events are locked during loading
    ElementMatrixLocker matrixLocker(elem, "Z::IO::Json::readElement");


    elem->setLabel(root["label"].toString());
    elem->setTitle(root["title"].toString());
    elem->layoutOptions.showLabel = root["layout_show_label"].toBool(elem->layoutOptions.showLabel);
    elem->layoutOptions.drawAlt = root[root.contains("layout_draw_narrow")
                                           ? "layout_draw_narrow" // before 2.0.13
                                           : "layout_draw_alt" // since 2.0.13
        ].toBool(elem->layoutOptions.drawAlt);
    elem->setDisabled(root["is_disabled"].toBool());

    auto formulaElem = dynamic_cast<ElemFormula*>(elem);
    if (formulaElem)
    {
        formulaElem->setTypeName(root["type_name"].toString());
        formulaElem->setFormula(root["formula"].toString());
        formulaElem->scheduleCalcMatrix();
    }
    
    auto paramSpecsJson = root["param_specs"];
    if (paramSpecsJson.isArray())
    {
        auto arr = paramSpecsJson.toArray();
        for (auto it = arr.cbegin(); it != arr.cend(); it++)
        {
            auto res = readParamSpec(it->toObject());
            if (!res.ok()) 
            {
                report->warning(QString("读取元件 '%1'：%2").arg(elem->displayLabel(), res.error()));
                continue;
            }
            elem->addParam(res.value());
        }
    }

    JsonValue paramsJson(root, "params", report);
    if (paramsJson)
    {
        for (Z::Parameter *param : elem->params())
        {
            JsonValue paramJson(paramsJson, param->alias(), report);
            if (paramJson)
            {
                auto paramObj = paramJson.obj();
                auto res = readParamValue(paramObj, param);
                if (!res.isEmpty())
                    report->warning(QString("读取元件 '%1'：%2").arg(elem->displayLabel(), res));
                param->setExpr(paramObj["expr"].toString());
                param->setError(paramObj["error"].toString());
            }
        }
    }

    return elem;
}

QList<PumpParams*> readPumps(const QJsonObject& root, Z::Report* report)
{
    if (!root.contains("pumps")) return {};

    JsonValue pumpsJson(root, "pumps", report);
    if (!pumpsJson) return {};

    QList<PumpParams*> pumps;
    for (auto it = pumpsJson.array().begin(); it != pumpsJson.array().end(); it++)
    {
        auto pump = readPump((*it).toObject(), report);
        if (pump) pumps << pump;
    }
    return pumps;
}

PumpParams* readPump(const QJsonObject& root, Z::Report* report)
{
    auto pumpModeName = root["mode"].toString();
    auto pumpMode = Pumps::findByModeName(pumpModeName);
    if (!pumpMode)
    {
        report->warning(QString("未知泵浦模式 '%1'，已跳过该泵浦").arg(pumpModeName));
        return nullptr;
    }

    auto pump = pumpMode->makePump();
    pump->setLabel(root["label"].toString());
    pump->setTitle(root["title"].toString());
    pump->setColor(root["color"].isString() ? root["color"].toString() : pump->color());
    pump->activate(root["is_active"].toBool());

    JsonValue paramsJson(root, "params", report);
    if (!paramsJson)
    {
        delete pump;
        return nullptr;
    }

    const auto pumpParams = *pump->params();
    for (Z::ParameterTS *param : std::as_const(pumpParams))
    {
        JsonValue paramJson(paramsJson, param->alias(), report);
        if (!paramJson) continue;

        auto res = readParamValueTS(paramJson.obj(), param);
        if (!res.isEmpty())
            report->warning(QString("读取泵浦 %1：%2").arg(pump->label(), res));
    }

    return pump;
}

} // namespace Json
} // namespace IO
} // namespace Z
