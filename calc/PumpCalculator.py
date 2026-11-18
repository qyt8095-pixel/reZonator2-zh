#!/usr/bin/env python
#
# 本脚本为泵浦计算器测试（../src/test/test_PumpCalculator.cpp）生成验证数据。
# 公式见 GaussCalculator.py、GaussCalculator.md。
#

from math import *
from cmath import *
from rezonator import *

def Waist_gauss():
  print('\n----------------------------------')
  print('束腰（高斯）：')

  # 泵浦参数
  wl = 980e-9
  w0 = 150e-6
  z = 0.11

  # 方案入口处的光束
  z0 = pi * sqr(w0) / wl
  V_in = wl / pi / w0
  w_in = w0 * sqrt(1 + sqr(z/z0))
  R_in = z * (1 +  sqr(z0/z))
  print_res('w_in', w_in)
  print_res('R_in', R_in)
  print_res('V_in', V_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.4379022
  B = 0.1681906
  C = -10.1543000
  D = 0.4922850

  # 输出光束
  q_in = 1.0 / complex(1.0/R_in, wl / pi / sqr(w_in))
  q_out_inv = 1.0 / ((A * q_in + B) / (C * q_in + D))
  R_out = 1.0 / q_out_inv.real
  w_out = sqrt(wl / pi / q_out_inv.imag)
  tmp = pow(w_out, 4) * sqr(pi)
  z = tmp * R_out / (sqr(wl * R_out) + tmp)
  z0 = sqrt(z * (R_out - z))
  w0 = sqrt(z0 * wl / pi)
  V_out = wl / pi / w0
  print_res('w_out', w_out)
  print_res('R_out', R_out)
  print_res('V_out', V_out)


def Waist_hyper():
  print('\n----------------------------------')
  print('束腰（超高斯）：')

  # 泵浦参数
  wl = 980e-9
  w0 = 100e-6
  z = 0.1
  MI = 3

  # 方案入口处的光束
  z0 = pi * sqr(w0) / MI / wl
  V_in = MI * wl / pi / w0
  w_in = w0 * sqrt(1 + sqr(z/z0))
  R_in = z * (1 +  sqr(z0/z))
  print_res('w_in', w_in)
  print_res('R_in', R_in)
  print_res('V_in', V_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.3899498
  B = 0.1731843
  C = -9.8480800
  D = 0.5075960

  # 输出光束
  w_in_equiv = w_in / sqrt(MI)
  q_in_equiv = 1.0 / complex(1.0/R_in, wl/pi/sqr(w_in_equiv))
  q_out_inv_equiv = 1.0 / ((A * q_in_equiv + B) / (C * q_in_equiv + D))
  R_out = 1.0 / q_out_inv_equiv.real
  w_out_equiv = sqrt(wl / pi / q_out_inv_equiv.imag)
  w_out = w_out_equiv * sqrt(MI)
  tmp = pow(w_out, 4) * sqr(pi)
  z = tmp * R_out / (sqr(MI * wl * R_out) + tmp)
  z0 = sqrt(z * (R_out - z))
  w0 = sqrt(MI * z0 * wl / pi)
  V_out = MI * wl / pi / w0
  print_res('w_out', w_out)
  print_res('R_out', R_out)
  print_res('V_out', V_out)


def Front_gauss():
  print('\n----------------------------------')
  print('波前（高斯）：')

  # 泵浦参数
  wl = 980e-9
  w = 400e-6
  R = 0.12

  # 方案入口处的光束
  w_in = w
  R_in = R
  tmp = pow(w_in, 4) * sqr(pi)
  z = tmp * R_in / (sqr(wl * R_in) + tmp)
  z0 = sqrt(z * (R_in - z))
  w0 = sqrt(z0 * wl / pi)
  V_in = wl / pi / w0
  print_res('w_in', w_in)
  print_res('R_in', R_in)
  print_res('V_in', V_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.4379022
  B = 0.1681906
  C = -10.1543000
  D = 0.4922850

  # 输出光束
  q_in = 1.0 / complex(1.0/R_in, wl/pi/sqr(w_in))
  q_out_inv = 1.0 / ((A * q_in + B) / (C * q_in + D))
  R_out = 1.0 / q_out_inv.real
  w_out = sqrt(wl / pi / q_out_inv.imag)
  tmp = pow(w_out, 4) * sqr(pi)
  z = tmp * R_out / (sqr(wl * R_out) + tmp)
  z0 = sqrt(z * (R_out - z))
  w0 = sqrt(z0 * wl / pi)
  V_out = wl / pi / w0
  print_res('w_out', w_out)
  print_res('R_out', R_out)
  print_res('V_out', V_out)


def Front_hyper():
  print('\n----------------------------------')
  print('波前（超高斯）：')

  # 泵浦参数
  wl = 980e-9
  w = 300e-6
  R = 0.11
  MI = 3

  # 方案入口处的光束
  w_in = w
  R_in = R
  tmp = pow(w_in, 4) * sqr(pi)
  z = tmp * R_in / (sqr(MI * wl * R_in) + tmp)
  z0 = sqrt(z * (R_in - z))
  w0 = sqrt(MI * z0 * wl / pi)
  V_in = MI * wl / pi / w0
  print_res('w_in', w_in)
  print_res('R_in', R_in)
  print_res('V_in', V_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.3899498
  B = 0.1731843
  C = -9.8480800
  D = 0.5075960

  # 输出光束
  w_in_equiv = w_in / sqrt(MI)
  q_in_equiv = 1.0 / complex(1.0/R_in, wl/pi/sqr(w_in_equiv))
  q_out_inv_equiv = 1.0 / ((A * q_in_equiv + B) / (C * q_in_equiv + D))
  R_out = 1.0 / q_out_inv_equiv.real
  w_out_equiv = sqrt(wl / pi / q_out_inv_equiv.imag)
  w_out = w_out_equiv * sqrt(MI)
  tmp = pow(w_out, 4) * sqr(pi)
  z = tmp * R_out / (sqr(MI * wl * R_out) + tmp)
  z0 = sqrt(z * (R_out - z))
  w0 = sqrt(MI * z0 * wl / pi)
  V_out = MI * wl / pi / w0
  print_res('w_out', w_out)
  print_res('R_out', R_out)
  print_res('V_out', V_out)


def RayVector():
  print('\n----------------------------------')
  print('光线矢量：')

  # 泵浦参数
  y = 0.0015
  V = radians(5)
  z = 0.1

  # 方案入口处的光束
  y_in = y + z * tan(V)
  V_in = V
  R_in = y_in / sin(V_in);
  print_res('y_in', y_in)
  print_res('V_in', V_in)
  print_res('R_in', R_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.4379022
  B = 0.1681906
  C = -10.1543000
  D = 0.4922850

  # 输出光束
  y_out = y_in * A + V_in * B
  V_out = y_in * C + V_in * D
  R_out = y_out / sin(V_out)
  print_res('y_out', y_out)
  print_res('V_out', V_out)
  print_res('R_out', R_out)


def TwoSections():
  print('\n----------------------------------')
  print('两段：')

  # 泵浦参数
  y1 = 0.0015
  y2 = 0.0025
  z = 0.11

  # 方案入口处的光束
  y_in = y2
  V_in = atan((y2 - y1) / z)
  R_in = y_in / sin(V_in);
  print_res('y_in', y_in)
  print_res('V_in', V_in)
  print_res('R_in', R_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.3899498
  B = 0.1731843
  C = -9.8480800
  D = 0.5075960

  # 输出光束
  y_out = y_in * A + V_in * B
  V_out = y_in * C + V_in * D
  R_out = y_out / sin(V_out)
  print_res('y_out', y_out)
  print_res('V_out', V_out)
  print_res('R_out', R_out)


def Complex_gauss():
  print('\n----------------------------------')
  print('复光束参数（高斯）：')

  # 泵浦参数
  wl = 980e-9
  re = 0.1
  im = -0.0320571

  # 方案入口处的光束
  q_in_inv = 1.0 / complex(re, im)
  R_in = 1.0 / q_in_inv.real
  w_in = sqrt(wl / pi / q_in_inv.imag)
  tmp = pow(w_in, 4) * sqr(pi)
  z = tmp * R_in / (sqr(wl * R_in) + tmp)
  z0 = sqrt(z * (R_in - z))
  w0 = sqrt(z0 * wl / pi)
  V_in = wl / pi / w0
  print_res('w_in', w_in)
  print_res('R_in', R_in)
  print_res('V_in', V_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.4379022
  B = 0.1681906
  C = -10.1543000
  D = 0.4922850

  # 输出光束
  q_in = 1.0 / complex(1.0/R_in, wl/pi/sqr(w_in))
  q_out_inv = 1.0 / ((A * q_in + B) / (C * q_in + D))
  R_out = 1.0 / q_out_inv.real
  w_out = sqrt(wl / pi / q_out_inv.imag)
  tmp = pow(w_out, 4) * sqr(pi)
  z = tmp * R_out / (sqr(wl * R_out) + tmp)
  z0 = sqrt(z * (R_out - z))
  w0 = sqrt(z0 * wl / pi)
  V_out = wl / pi / w0
  print_res('w_out', w_out)
  print_res('R_out', R_out)
  print_res('V_out', V_out)


def Complex_hyper():
  print('\n----------------------------------')
  print('复光束参数（超高斯）：')

  # 泵浦参数
  wl = 980e-9
  re = 0.101014
  im = -0.003598
  MI = 3

  # 方案入口处的光束
  q_in_inv = 1.0 / complex(re, im)
  R_in = 1.0 / q_in_inv.real
  w_in = sqrt(wl / pi / q_in_inv.imag)
  tmp = pow(w_in, 4) * sqr(pi)
  z = tmp * R_in / (sqr(MI * wl * R_in) + tmp)
  z0 = sqrt(z * (R_in - z))
  w0 = sqrt(MI * z0 * wl / pi)
  V_in = MI * wl / pi / w0
  print_res('w_in', w_in)
  print_res('R_in', R_in)
  print_res('V_in', V_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.3899498
  B = 0.1731843
  C = -9.8480800
  D = 0.5075960

  # 输出光束
  w_in_equiv = w_in / sqrt(MI)
  q_in_equiv = 1.0 / complex(1.0/R_in, wl/pi/sqr(w_in_equiv))
  q_out_inv_equiv = 1.0 / ((A * q_in_equiv + B) / (C * q_in_equiv + D))
  R_out = 1.0 / q_out_inv_equiv.real
  w_out_equiv = sqrt(wl / pi / q_out_inv_equiv.imag)
  w_out = w_out_equiv * sqrt(MI)
  tmp = pow(w_out, 4) * sqr(pi)
  z = tmp * R_out / (sqr(MI * wl * R_out) + tmp)
  z0 = sqrt(z * (R_out - z))
  w0 = sqrt(MI * z0 * wl / pi)
  V_out = MI * wl / pi / w0
  print_res('w_out', w_out)
  print_res('R_out', R_out)
  print_res('V_out', V_out)


def InvComplex_gauss():
  print('\n----------------------------------')
  print('倒复光束参数（高斯）：')
  # 泵浦参数

  wl = 980e-9
  re_inv = 9.06811
  im_inv = 2.90697

  # 方案入口处的光束
  q_in_inv = complex(re_inv, im_inv)
  R_in = 1.0 / q_in_inv.real
  w_in = sqrt(wl / pi / q_in_inv.imag)
  tmp = pow(w_in, 4) * sqr(pi)
  z = tmp * R_in / (sqr(wl * R_in) + tmp)
  z0 = sqrt(z * (R_in - z))
  w0 = sqrt(z0 * wl / pi)
  V_in = wl / pi / w0
  print_res('w_in', w_in)
  print_res('R_in', R_in)
  print_res('V_in', V_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.4379022
  B = 0.1681906
  C = -10.1543000
  D = 0.4922850

  # 输出光束
  q_in = 1.0 / complex(1.0/R_in, wl/pi/sqr(w_in))
  q_out_inv = 1.0 / ((A * q_in + B) / (C * q_in + D))
  R_out = 1.0 / q_out_inv.real
  w_out = sqrt(wl / pi / q_out_inv.imag)
  tmp = pow(w_out, 4) * sqr(pi)
  z = tmp * R_out / (sqr(wl * R_out) + tmp)
  z0 = sqrt(z * (R_out - z))
  w0 = sqrt(z0 * wl / pi)
  V_out = wl / pi / w0
  print_res('w_out', w_out)
  print_res('R_out', R_out)
  print_res('V_out', V_out)


def InvComplex_hyper():
  print('\n----------------------------------')
  print('倒复光束参数（超高斯）：')
  # 泵浦参数

  wl = 980e-9
  re_inv = 9.88711
  im_inv = 0.352168
  MI = 3

  # 方案入口处的光束
  q_in_inv = complex(re_inv, im_inv)
  R_in = 1.0 / q_in_inv.real
  w_in = sqrt(wl / pi / q_in_inv.imag)
  tmp = pow(w_in, 4) * sqr(pi)
  z = tmp * R_in / (sqr(MI * wl * R_in) + tmp)
  z0 = sqrt(z * (R_in - z))
  w0 = sqrt(MI * z0 * wl / pi)
  V_in = MI * wl / pi / w0
  print_res('w_in', w_in)
  print_res('R_in', R_in)
  print_res('V_in', V_in)

  # 方案 ../bin/test_files/test_mult_matrix.rez 的矩阵
  A = -1.3899498
  B = 0.1731843
  C = -9.8480800
  D = 0.5075960

  # 输出光束
  w_in_equiv = w_in / sqrt(MI)
  q_in_equiv = 1.0 / complex(1.0/R_in, wl/pi/sqr(w_in_equiv))
  q_out_inv_equiv = 1.0 / ((A * q_in_equiv + B) / (C * q_in_equiv + D))
  R_out = 1.0 / q_out_inv_equiv.real
  w_out_equiv = sqrt(wl / pi / q_out_inv_equiv.imag)
  w_out = w_out_equiv * sqrt(MI)
  tmp = pow(w_out, 4) * sqr(pi)
  z = tmp * R_out / (sqr(MI * wl * R_out) + tmp)
  z0 = sqrt(z * (R_out - z))
  w0 = sqrt(MI * z0 * wl / pi)
  V_out = MI * wl / pi / w0
  print_res('w_out', w_out)
  print_res('R_out', R_out)
  print_res('V_out', V_out)


Waist_gauss()
Waist_hyper()
Front_gauss()
Front_hyper()
RayVector()
TwoSections()
Complex_gauss()
Complex_hyper()
InvComplex_gauss()
InvComplex_hyper()
