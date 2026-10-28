# reZonator-1 光路图文件格式说明

光路图文件扩展名为 `*.she`。它们是 INI 格式的通用 ASCII 文本文件。

整体结构如下：

```ini
[section1]
key1=value1
key2=value2
...

[section2]
key1=value1
key2=value2
...
```

本文档仅描述 reZonator-2 加载光路图所需的节和键的一部分。

## 节 [PREFERENCES]

### Version
光路图格式版本。支持 1、1.1 和 1.2 版本。

### Title
显示在窗口标题栏中的光路图标题。

### HasTitle
定义 `Title` 键是否有效。可以为 0 或 1。

### Notes
光路图的文本注释。

### SchemaKind
往返类型。

* 0 is SW
* 1 is RR
* 2 is SP

### Wavelen
工作波长。对于 `Version=1`，单位始终为纳米；否则单位由 `Units\Lambda` 键定义。

### LinearUnits
仅适用于 `Version=1`。线性量的计量单位——元件长度、焦距范围等。

* 0 is millimeters
* 1 is micrometers

### AngleUnits
仅适用于 `Version=1`。角度量的计量单位。

* 0 is degrees
* 1 is milliradians
* 2 is angular minutes
* 4 is radians

**注意：** 该单位仅定义数值在程序中的显示方式。角度值在光路图文件中始终以**弧度**存储。

### Units\Linear
适用于 `Version` > 1。线性量的计量单位——元件长度、焦距范围等。支持的值为 `A`、`nm`、`mkm`、`mm`、`cm`、`m`。

### Units\Beamsize
适用于 `Version` > 1。光束半径的计量单位。支持的值为 `A`、`nm`、`mkm`、`mm`、`cm`、`m`。

### Units\Lambda
适用于 `Version` > 1。波长的计量单位。支持的值为 `A`、`nm`、`mkm`、`mm`、`cm`、`m`。

### Units\Angle
适用于 `Version` > 1。角度量的计量单位。支持的值为 `rad`、`deg`、`mrad`、`min`。

**注意：** 该单位仅定义数值在程序中的显示方式。角度值在光路图文件中始终以**弧度**存储。

### PumpType
仅适用于 `Version=1`。定义单程光路图的输入光束类型。

* 0 - input beam is gaussisan beam
* 1 - input beam is hypergaussian beam

### PumpSize
仅适用于 `Version=1`。以微米为单位的光束半径。

### PumpParam1
仅适用于 `Version=1`。当 `PumpType=1` 时的光束质量参数 MI。

### Pump\\...
适用于 `Version` > 1。单程光路图的输入光束参数。光束参数通过以下键分别针对 T 平面和 S 平面定义：

* `Pump\Param1T`, `Pump\Param1S`
* `Pump\Param2T`, `Pump\Param2S`
* `Pump\QualT`, `Pump\QualS`

这些键的含义取决于 `Pump\ParamsKind` 键的值。

#### Pump\ParamsKind=0
输入光束由其束腰半径定义。

* `Pump\Param1T`, `Pump\Param1S` - 光束束腰半径。
* `Pump\Param2T`, `Pump\Param2S` - 泵浦源到第一个光路图元件的距离。
* `Pump\QualT`, `Pump\QualS` - 光束质量参数 MI。

#### Pump\ParamsKind=1
输入光束由其在第一个光路图元件处的半径定义。

* `Pump\Param1T`, `Pump\Param1S` - 在第一个光路图元件处的光束半径。
* `Pump\Param2T`, `Pump\Param2S` - 泵浦源到第一个光路图元件的距离。
* `Pump\QualT`, `Pump\QualS` - 光束质量参数 MI。

#### Pump\ParamsKind=2 
输入光束由其复光束参数定义。

* `Pump\Param1T`, `Pump\Param1S` - 实部。
* `Pump\Param2T`, `Pump\Param2S` - 虚部。
* `Pump\QualT`, `Pump\QualS` - 光束质量参数 MI。

#### Pump\ParamsKind=3
输入光束由其倒复光束参数定义。

* `Pump\Param1T`, `Pump\Param1S` - 实部。
* `Pump\Param2T`, `Pump\Param2S` - 虚部。
* `Pump\QualT`, `Pump\QualS` - 光束质量参数 MI。

#### Pump\ParamsKind=4
输入光束定义为由其半径和半发散角确定的光线矢量。

* `Pump\Param1T`, `Pump\Param1S` - 在第一个光路图元件处的光束半径。
* `Pump\Param2T`, `Pump\Param2S` - 发散角的一半。
* `Pump\QualT`, `Pump\QualS` - 不使用。

#### Pump\ParamsKind=5
输入光束定义为由其两个半径确定的光线矢量。

* `Pump\Param1T`, `Pump\Param1S` - 在泵浦源处的光束半径。
* `Pump\Param2T`, `Pump\Param2S` - 在第一个光路图元件处的光束半径。
* `Pump\QualT`, `Pump\QualS` - 泵浦源与第一个光路图元件之间的距离。

## 节 [Element...]
这些节存储光路图的元件。每个节的名称为 `Element` + 元件序号（从 1 开始）。

### Type
元件类型：

* TElemFlatMirror
* TElemCurveMirror
* TElemEmptyRange
* TElemMediaRange
* TElemPlate (for `Version` > 1)
* TElemBrewsterCrystal
* TElemBrewsterPlate
* TElemTiltedCrystal
* TElemTiltedPlate
* TElemThinLens
* TElemThinCylinderLensT (for `Version` > 1)
* TElemThinCylinderLensS (for `Version` > 1)
* TElemPoint
* TElemThinLensCylT (only for `Version=1`, --> TElemThinCylinderLensT)
* TElemThinLensCylS (only for `Version=1`, --> TElemThinCylinderLensS)
* TElemRange (only for `Version=1`, --> TElemPlate)
* TElemCustom (for `Version` < 1.2, --> TElemMatrix)
* TElemMatrix (for `Version` >= 1.2)

### Alias
元件标签。

### Title
元件标题。

### Disabled
可以为 0 或 1。如果 `Disabled=1`，该元件在计算中将被忽略。

### Param_...
元件参数的值。每个键名为 `Param_` + 参数名，例如 `Param_L`、`Param_n`。各元件的参数名可从元件目录中获取。

- 线性参数的值根据 `Version` 存储在 `LinearUnits` 或 `Units\Linear` 中。

- 角度参数的值始终以**弧度**存储。

### Misalign\\...
适用于 `Version` > 1。元件失调。*reZonator-2 尚不支持*。


## 节 [WINDOWS]
函数窗口列表，格式如下：

```ini
Window...=<window type>
``` 

其中 `Window...` 定义要加载的节（见下文），`<window type>` 可以是以下之一：

* TwndGraph (only for `Version=1`)
* TwndGraphMultiCaustic (For `Version` > 1)
* ... **TODO** to be continued ...

*reZonator-2 尚不支持加载已存储的函数窗口。*

## 节 [Window...]
*reZonator-2 尚不支持加载已存储的函数窗口。*
