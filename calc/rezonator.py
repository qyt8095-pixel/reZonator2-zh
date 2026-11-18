#
# 其他脚本共用的辅助函数。
#

import numpy as np
from math import *

def sqr(a):
  return a * a

# 返回矩阵元素
# M 应为 numpy.ndarray
def get_abcd(M):
  A = M[0, 0]
  B = M[0, 1]
  C = M[1, 0]
  D = M[1, 1]
  return A, B, C, D


# 由元素生成 numpy 矩阵
def make_abcd(A, B, C, D):
  return np.matrix([[A, B], [C, D]])


# 打印 ABCD 矩阵
# M 应为 numpy.ndarray
def print_abcd(name, M):
  A, B, C, D = get_abcd(M)
  print("{}: {:.7f}, {:.7f}, {:.7f}, {:.7f}".format(name, A, B, C, D))

def print_abcd_c(name, M):
  A, B, C, D = get_abcd(M)
  print("{}: _C({:.7f},{:.7f}), _C({:.7f},{:.7f}), _C({:.7f},{:.7f}), _C({:.7f},{:.7f})" \
    .format(name, A.real, A.imag, B.real, B.imag, C.real, C.imag, D.real, D.imag))

# 比较两个 ABCD 矩阵
def compare_abcd(id, M1, M2, epsilon = 1e-7):
  A1, B1, C1, D1 = get_abcd(M1)
  A2, B2, C2, D2 = get_abcd(M2)
  A = abs(A1 - A2) < epsilon
  B = abs(B1 - B2) < epsilon
  C = abs(C1 - C2) < epsilon
  D = abs(D1 - D2) < epsilon
  if not A or not B or not C or not D:
    print(id + ": (±{}) ** FAIL ** ({}, {}, {}, {})".format(epsilon, A, B, C, D))
  else:
    print(id + ': (±{}) ** OK **'.format(epsilon))

  
# 光线矩阵对复曲率半径的变换    
# M 应为 numpy.ndarray
def transform_q(q1, M):
  A, B, C, D = get_abcd(M)
  return (A * q1 + B) / (C * q1 + D)


# 打印带名称的结果值
def print_res(name, value):
  print("{}: {:.7g}".format(name, value))


# 由矩阵计算稳定参数
# M 应为 numpy.ndarray
def calc_stab(M):
  A, B, C, D = get_abcd(M)
  return (A+D)/2.0


# 由矩阵和波长计算光束尺寸
# M 应为 numpy.ndarray
def calc_w(M, wl, n):
  A, B, C, D = get_abcd(M)
  # 在纯实矩阵系统中，B 可能为负
  # 此时系统稳定，但 W 为纯虚数。
  return sqrt(wl/n/pi * 2*abs(B) / sqrt(4 - sqr(A+D)))
