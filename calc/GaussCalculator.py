#!/usr/bin/env python
#
# 本脚本为高斯光束计算器工具测试（../src/test/test_GaussCalculator.cpp）生成验证数据。
# 该工具的公式说明见 GaussCalculator.md 文件。
#

from math import *
from cmath import *
from rezonator import *

NAMES = ['mi', 'wl', 'w0', 'z0', 'Vs', 
         'z', 'w', 'R', 'q_inv', 'q']


def change_W0():
  print('\n----------------------------------')
  print('改变束腰：')
  wl = 980e-9
  z = 0.1
  mi = 2

  print('\n锁定束腰：')
  w0 = 100e-6
  
  z0 = pi * sqr(w0) / mi / wl
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))

  print('\n锁定波前：')
  w0 = 75e-6
  
  z = R*(1 - sqr(w0 / w))
  z0 = sqrt(z * (R - z))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  
  for name in NAMES: print_res(name, eval(name))


def change_Z0():
  print('\n----------------------------------')
  print('改变瑞利长度：')

  wl = 1.1e-6
  w0 = 100e-6
  z = 0.1

  print('\n锁定束腰：')
  z0 = 0.012
  
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))

  print('\n锁定波前：')
  z0 = 0.016

  print('\n远区：')
  z = R/2.0 + sqrt(sqr(R) - 4*sqr(z0))/2.0
  w0 = sqrt(sqr(w) / (1 + sqr(z / z0)))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0

  for name in NAMES: print_res(name, eval(name))

  print('\n近区：')
  z = R/2.0 - sqrt(sqr(R) - 4*sqr(z0))/2.0
  w0 = sqrt(sqr(w) / (1 + sqr(z / z0)))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0

  for name in NAMES: print_res(name, eval(name))


def change_Vs():
  print('\n----------------------------------')
  print('改变发散角：')

  wl = 640e-9
  w0 = 100e-6
  z = 0.1

  print('\n锁定束腰：')
  Vs = 0.07

  mi = pi * w0 * Vs / wl
  z0 = pi * sqr(w0) / mi / wl
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv

  for name in NAMES: print_res(name, eval(name))

  print('\n锁定波前：')
  Vs = 0.08

  z = sqr(w) / R / sqr(Vs)
  z0 = sqrt(z * (R - z))
  w0 = w / sqrt(1 + sqr(z / z0))
  mi = pi * sqr(w0) / wl / z0

  for name in NAMES: print_res(name, eval(name))


def change_Z():
  print('\n----------------------------------')
  print('改变轴向距离：')

  wl = 640e-9
  w0 = 100e-6
  mi = 2

  print('\n锁定束腰：')
  z = 0.1

  z0 = pi * sqr(w0) / mi / wl
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv

  for name in NAMES: print_res(name, eval(name))

  print('\n锁定波前：')
  z = 0.09

  z0 = sqrt(z * (R - z))
  w0 = w / sqrt(1 + sqr(z / z0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0

  for name in NAMES: print_res(name, eval(name))


def change_M2():
  print('\n----------------------------------')
  print('改变光束质量：')
  wl = 980e-9
  w0 = 100e-6
  z = 0.1

  print('\n锁定束腰：')
  mi = 2
  
  z0 = pi * sqr(w0) / mi / wl
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))

  print('\n锁定波前：')
  mi = 1.7
  
  tmp = pow(w, 4) * sqr(pi)
  z = tmp * R / (sqr(mi * wl * R) + tmp)
  z0 = sqrt(z * (R - z))
  w0 = sqrt(mi * z0 * wl / pi)
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv

  for name in NAMES: print_res(name, eval(name))


def change_W():
  print('\n----------------------------------')
  print('改变光束半径：')
  wl = 640e-9
  w0 = 100e-6
  z = 0.1  
  
  print('\n锁定束腰：')
  w = 600e-6
  
  z0 = z * w0 / sqrt(sqr(w) - sqr(w0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))
  
  print('\n锁定波前：')
  w = 700e-6
  
  z0 = sqrt(z * (R - z))
  w0 = w / sqrt(1 + sqr(z / z0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))


def change_R():
  print('\n----------------------------------')
  print('改变波前曲率半径：')
  wl = 640e-9
  w0 = 100e-6
  z = 0.1  

  print('\n锁定束腰：')
  R = 0.12
  
  z0 = sqrt(z * (R - z))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))
  
  print('\n锁定波前：')
  R = 0.11
  
  z0 = sqrt(z * (R - z))
  w0 = w / sqrt(1 + sqr(z / z0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv

  for name in NAMES: print_res(name, eval(name))


def change_Q():
  print('\n----------------------------------')
  print('改变复光束参数：')
  wl = 640e-9
  w0 = 100e-6
  
  print('\n锁定束腰：')
  q = complex(0.1, -0.036)
  q_inv = 1 / q
  
  R = 1.0 / q_inv.real
  w = sqrt(wl / pi / q_inv.imag)
  z = R * (1 - sqr(w0/w))
  z0 = sqrt(z * (R - z))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))
  
  print('\n锁定束腰：')
  q = complex(0.9, -0.040)
  q_inv = 1 / q
  
  R = 1.0 / q_inv.real
  w = sqrt(wl / pi / q_inv.imag)
  z0 = sqrt(z * (R - z))
  w0 = w / sqrt(1 + sqr(z / z0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))


def change_Q1_re():
  print('\n----------------------------------')
  print('改变倒复光束参数（实部）：')
  wl = 640e-9
  w0 = 100e-6
  z = 0.1  

  print('\n锁定束腰：')
  q_inv_re = 9 
  
  R = 1.0 / q_inv_re
  z0 = sqrt(z * (R - z))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))
  
  print('\n锁定波前：')
  q_inv_re = 8

  R = 1.0 / q_inv_re
  z0 = sqrt(z * (R - z))
  w0 = w / sqrt(1 + sqr(z / z0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv

  for name in NAMES: print_res(name, eval(name))


def change_Q1_im():
  print('\n----------------------------------')
  print('改变倒复光束参数（虚部）：')
  wl = 640e-9
  w0 = 100e-6
  z = 0.1  
  
  print('\n锁定束腰：')
  q_inv_im = 0.05
  
  w = sqrt(wl / pi / q_inv_im)
  z0 = z * w0 / sqrt(sqr(w) - sqr(w0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))
  
  print('\n锁定波前：')
  q_inv_im = 0.45
  
  w = sqrt(wl / pi / q_inv_im)
  z0 = sqrt(z * (R - z))
  w0 = w / sqrt(1 + sqr(z / z0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))


def change_Lambda():
  print('\n----------------------------------')
  print('改变波长：')
  w0 = 100e-6
  z = 0.1
  mi = 2

  print('\n锁定束腰：')
  wl = 980e-9
  
  z0 = pi * sqr(w0) / mi / wl
  Vs = mi * wl / pi / w0
  w = w0 * sqrt(1 + sqr(z/z0))
  R = z * (1 +  sqr(z0/z))
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv
  
  for name in NAMES: print_res(name, eval(name))

  print('\n锁定波前：')
  wl = 640e-9

  z0 = sqrt(z * (R - z))
  w0 = w / sqrt(1 + sqr(z / z0))
  mi = pi * sqr(w0) / wl / z0
  Vs = mi * wl / pi / w0
  q_inv = complex(1/R, wl/pi/sqr(w))
  q = 1 / q_inv

  for name in NAMES: print_res(name, eval(name))


change_W0()
change_Z0()
change_Vs()
change_Z()
change_M2()
change_W()
change_R()
change_Q()
change_Q1_re()
change_Q1_im()
change_Lambda()
