#!/usr/bin/env python
#
# 本脚本为 ABCD 矩阵运算测试（../src/test/test_Math.cpp）生成验证数据。
#

import numpy as np
from rezonator import *

def Matrix_multiply():
  print('----------------------------------')
  print('矩阵 × 矩阵：')
  m1 = [[5, 6], [7, 8]]
  m2 = [[1, 2], [3, 4]]
  m3 = np.matmul(m1, m2)
  print(m3)
  m4 = np.matmul(m2, m1)
  print(m4)


def Matrix_multComplexBeam():
  print('----------------------------------')
  print('光线矩阵对复曲率半径的变换：')
  m1 = np.matrix([[5, 6], [7, 8]])
  q1 = 1 + 2j
  q2 = transform_q(q1, m1)
  print(q2)


Matrix_multiply()
Matrix_multComplexBeam()
