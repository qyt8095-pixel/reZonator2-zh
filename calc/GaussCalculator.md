# 高斯光束计算器工具公式

*高斯光束计算器* 工具在改变高斯光束的某个参数并固定其他一些参数时，计算高斯光束的一些自由参数。由于不可能让所有参数都是自由的，我们引入两种固定模式，称为*锁定束腰* 和*锁定波前*。

- 锁定束腰——求出自由参数的这样一些值，使得当其中一个参数变化时，光束束腰 $w_0$ 保持不变。
- 锁定波前——求出自由参数的这样一些值，使得当其中一个参数变化时，在某个轴向距离 $z$ 处的波前曲率半径 $R$ 和光束半径 $w$ 保持不变。

二次方程有两个解，我们必须定义一种方法来指出取哪个解。因此，该工具还有一个附加参数——区域——它可以是*近区* 或*远区*。

工具的测试值通过脚本 `GaussCalculator.py` 计算。

这些公式用于文档页 `../help/calc_gauss.rst`。

## 改变束腰 $w_0$

### 锁定束腰
计算给定距离 $z$ 处的光束半径 $w$ 和波前曲率半径 $R$。

$$ z_0 = \frac{\pi w_0^2}{M^2 \lambda}  $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

$$ w = w_0 \sqrt{ 1 + \bigg( \frac{z}{z_0} \bigg)^2 } $$

$$ R = z \Bigg[ 1 + \bigg( \frac{z_0}{z} \bigg)^2 \Bigg] $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$

### 锁定波前
对于给定的束腰半径 $w_0$，求出使波前曲率半径保持先前计算值的距离 $z$ 和光束质量 $M^2$。

求解方法：分别从 $w(z)$ 和 $R(z)$ 中表示出 $z_0$，令两式相等，并对 $z$ 求解。

$$ z = R \Bigg[ 1 - \bigg( \frac{w_0}{w} \bigg)^2 \Bigg] $$

$$ z_0 = \sqrt{ \frac{ z^2 w_0^2 }{ w^2 - w_0^2 } } $$

$$ z_0 = \sqrt{ z (R - z) }  $$

$$ M^2 = \frac{ \pi w_0^2 }{ \lambda z_0 }  $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$


## 改变瑞利长度 $z_0$

### 锁定束腰
在束腰半径 $w_0$ 固定的情况下，求出能得到指定 $z_0$ 的光束质量参数 $M^2$ 的值。

$$ M^2 = \frac{ \pi w_0^2 }{ \lambda z_0 }  $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

$$ w = w_0 \sqrt{ 1 + \bigg( \frac{z}{z_0} \bigg)^2 } $$

$$ R = z \Bigg[ 1 + \bigg( \frac{z_0}{z} \bigg)^2 \Bigg] $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$

### 锁定波前
对于给定的 $z_0$，求出使波前曲率半径保持先前计算值的距离 $z$ 和光束质量 $M^2$。

$$ z = \frac R 2 \pm \frac{\sqrt{ R^2 - 4 z_0^2 }}2  $$

$+$ 号对应远区，$-$ 号对应近区。

$$ w_0 = \sqrt{ \frac{w^2}{1 + \big( z/z_0 \big)^2} } $$

$$ M^2 = \frac{ \pi w_0^2 }{ \lambda z_0 }  $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$


## 改变发散角 $V_s$

### 锁定束腰
在束腰半径 $w_0$ 固定的情况下，求出能得到指定角度的光束质量参数 $M^2$ 的值。

$$ M^2 = \frac{ \pi w_0 V_s } \lambda $$

$$ z_0 = \frac{\pi w_0^2}{M^2 \lambda}  $$

$$ w = w_0 \sqrt{ 1 + \bigg( \frac{z}{z_0} \bigg)^2 } $$

$$ R = z \Bigg[ 1 + \bigg( \frac{z_0}{z} \bigg)^2 \Bigg] $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$

### 锁定波前
对于给定的 $V_s$，求出使波前曲率半径保持先前计算值的距离 $z$ 和光束质量 $M^2$。

求 $z$ 的方法：将 $z_0$ 表示为 $w_0/V_s$ 代入 $w(z)$ 和 $R(z)$ 的公式，从两式中表示出 $w_0$，令其相等，并对 $z$ 求解。

$$ z = \frac{w^2}{R V_s^2} $$

$$ z_0 = \sqrt{z (R - z)}  $$

$$ w_0 = \frac{w}{\sqrt{ 1 + \big( z/z_0 \big)^2} } $$

$$ M^2 = \frac{\pi w_0^2}{z_0 \lambda} $$


## 改变轴向距离 $z$

### 锁定束腰

$$ z_0 = \frac{\pi w_0^2}{M^2 \lambda}  $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

$$ w = w_0 \sqrt{ 1 + \bigg( \frac{z}{z_0} \bigg)^2 } $$

$$ R = z \Bigg[ 1 + \bigg( \frac{z_0}{z} \bigg)^2 \Bigg] $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$

### 锁定波前

$$ z_0 = \sqrt{z (R - z)}  $$

$$ w_0 = \frac{w}{\sqrt{ 1 + \big( z/z_0 \big)^2} } $$

$$ M^2 = \frac{\pi w_0^2}{z_0 \lambda} $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$


## 改变光束质量 $M^2$

### 锁定束腰
与改变束腰时相同。

$$ z_0 = \frac{\pi w_0^2}{M^2 \lambda}  $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

$$ w = w_0 \sqrt{ 1 + \bigg( \frac{z}{z_0} \bigg)^2 } $$

$$ R = z \Bigg[ 1 + \bigg( \frac{z_0}{z} \bigg)^2 \Bigg] $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$

### 锁定波前
取一个新的 $M^2$ 值，求出使波前保持不变的距离 $z$ 和束腰半径 $w_0$。

求 $z$ 的方法：从 $R(z)$ 的公式中表示出 $w_0^2$，将该表达式代入 $w(z)$ 的公式，并对 $z$ 求解。

$$ z = \frac{w^4 \pi^2 R}{\big(M^2 \lambda R\big)^2 + w^4 \pi^2} $$

$$ z_0 = \sqrt{z (R - z)}  $$

$$ w_0 = \frac{w}{\sqrt{ 1 + \big( z/z_0 \big)^2} } $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$


## 改变光束半径 $w$

### 锁定束腰
求出在相同轴向距离 $z$ 处、相同束腰半径 $w_0$ 下给出指定光束半径的光束质量参数 $M^2$。

$$ z_0 = \frac{z w_0}{\sqrt{w^2 - w_0^2}} $$

$$ M^2 = \frac{\pi w_0^2}{z_0 \lambda} $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

$$ R = z \Bigg[ 1 + \bigg( \frac{z_0}{z} \bigg)^2 \Bigg] $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$

### 锁定波前
求出在相同轴向距离 $z$ 处给出指定光束半径的束腰半径 $w_0$ 和光束质量参数 $M^2$。

$$ z_0 = \sqrt{z (R - z)}  $$

$$ w_0 = \frac{w}{\sqrt{ 1 + \big( z/z_0 \big)^2} } $$

$$ M^2 = \frac{\pi w_0^2}{z_0 \lambda} $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$


## 改变波前曲率半径 $R$

### 锁定束腰
求出在相同轴向距离 $z$ 处、相同束腰半径 $w_0$ 下给出指定曲率半径的光束质量参数 $M^2$。

$$ z_0 = \sqrt{z (R - z)}  $$

$$ M^2 = \frac{\pi w_0^2}{z_0 \lambda} $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

$$ w = w_0 \sqrt{ 1 + \bigg( \frac{z}{z_0} \bigg)^2 } $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$

### 锁定波前
求出在相同轴向距离 $z$ 处给出指定曲率半径的束腰半径 $w_0$ 和光束质量参数 $M^2$。

$$ z_0 = \sqrt{z (R - z)}  $$

$$ w_0 = \frac{w}{\sqrt{ 1 + \big( z/z_0 \big)^2} } $$

$$ M^2 = \frac{\pi w_0^2}{z_0 \lambda} $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

$$ q^{-1} = \frac 1 R + i \frac{\lambda}{\pi w^2} $$


## 改变复光束参数 $q$
通过指定复光束参数的实部或虚部，我们同时确定在同一位置的光束半径 $w$ 和波前曲率半径 $R$。

$$ R = \frac{1}{Re\big(q^{-1}\big)} $$

$$ w = \sqrt{\frac{\lambda}{\pi Im\big(q^{-1}\big)}} $$

### 锁定束腰
在束腰半径 $w_0$ 固定的情况下，求出达到指定波前的轴向距离 $z$ 和光束质量 $M^2$。

$$ z = R \Bigg[ 1 - \bigg( \frac{w_0}{w} \bigg)^2 \Bigg] $$

$$ z_0 = \sqrt{z (R - z)}  $$

$$ M^2 = \frac{\pi w_0^2}{z_0 \lambda} $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$

### 锁定波前

$$ z_0 = \sqrt{z (R - z)}  $$

$$ w_0 = \frac{w}{\sqrt{ 1 + \big( z/z_0 \big)^2} } $$

$$ M^2 = \frac{\pi w_0^2}{z_0 \lambda} $$

$$ V_s = \frac{M^2 \lambda}{\pi w_0}  $$


## 改变倒复光束参数

改变实部等效于改变波前曲率半径 $R$，改变虚部等效于改变光束半径 $w$。


## 改变波长 $\lambda$

### 锁定束腰

与束腰 $w_0$ 变化时使用的公式相同。

### 锁定波前

与光束半径 $w$ 或波前曲率半径 $R$ 变化时使用的公式相同。
