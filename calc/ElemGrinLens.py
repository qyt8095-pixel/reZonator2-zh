#!/usr/bin/env python

import numpy as np
from math import cos, sin, sqrt, cosh, sinh
from rezonator import make_abcd, print_abcd, compare_abcd

show_lens = True

n0 = 1.5        # 折射率
n2 = 0.3        # 折射率梯度
L = 0.01        # 透镜厚度
h1 = 0.003      # 左半程
h2 = L - h1     # 右半程
g = sqrt(n2/n0)

M_out = make_abcd(1, 0, 0, n0)
M_in = make_abcd(1, 0, 0, 1/n0)

print('----------------------------------')
print('----------------------------------')
print('         GRIN 介质（正）          ')
print('----------------------------------')
print('预先计算的完整矩阵')
# ../help/matrix/ElemGrinMedium.png
M_GM_full = make_abcd(cos(L*g), sin(L*g)/g, -g*sin(L*g), cos(L*g))
print_abcd("M_GM_full", M_GM_full)

print('----------------------------------')
print('矩阵乘积')

# 左半程
M_GM_lf = make_abcd(cos(h1*g), sin(h1*g)/g, -g*sin(h1*g), cos(h1*g))
print_abcd("M_GM_lf", M_GM_lf)

# 右半程
M_GM_rt = make_abcd(cos(h2*g), sin(h2*g)/g, -g*sin(h2*g), cos(h2*g))
print_abcd("M_GM_rt", M_GM_rt)

# 介质矩阵——前 2 个矩阵的乘积
M_GM_2 = np.dot(M_GM_rt, M_GM_lf)
print_abcd("M_GM_2", M_GM_2) 
compare_abcd("M_GM_full == M_GM_2", M_GM_full, M_GM_2)

if show_lens:
  print('----------------------------------')
  print('         GRIN 透镜（正）          ')
  print('----------------------------------')
  print('预先计算的完整矩阵')
  # ../help/matrix/ElemGrinLens.png
  A = cos(L*sqrt(n2/n0))
  B = sin(L*sqrt(n2/n0))/sqrt(n2*n0)
  C = -sqrt(n2*n0)*sin(L*sqrt(n2/n0))
  D = cos(L*sqrt(n2/n0))
  M_GL_full = make_abcd(A, B, C, D)
  print_abcd("M_GL_full", M_GL_full)

  print('----------------------------------')
  print('矩阵乘积')

  # 进入介质并通过左半程
  # ../help/matrix/ElemGrinLens_left.png
  A1 = cos(h1*sqrt(n2/n0))
  B1 = sin(h1*sqrt(n2/n0))/sqrt(n2*n0)
  C1 = -sqrt(n2/n0)*sin(h1*sqrt(n2/n0))
  D1 = cos(h1*sqrt(n2/n0))/n0
  M_GL_lf = make_abcd(A1, B1, C1, D1)
  print_abcd("M_GL_lf", M_GL_lf)

  # 通过右半程并出射到空气中
  # ../help/matrix/ElemGrinLens_right.png
  A2 = cos(h2*sqrt(n2/n0))
  B2 = sqrt(n0/n2)*sin(h2*sqrt(n2/n0))
  C2 = -sqrt(n2*n0)*sin(h2*sqrt(n2/n0))
  D2 = n0*cos(h2*sqrt(n2/n0))
  M_GL_rt = make_abcd(A2, B2, C2, D2)
  print_abcd("M_GL_rt", M_GL_rt)

  # 透镜矩阵——前 2 个矩阵的乘积
  M_GL_2 = np.dot(M_GL_rt, M_GL_lf)
  print_abcd("M_GL_2", M_GL_2) 
  compare_abcd("M_GL_full == M_GL_2", M_GL_full, M_GL_2)

  # 透镜矩阵——3 个矩阵的乘积
  M_GL_3 = np.dot(np.dot(M_out, M_GM_full), M_in)
  print_abcd("M_GL_3", M_GL_3) 
  compare_abcd("M_GL_full == M_GL_3", M_GL_full, M_GL_3)


print('----------------------------------')
print('----------------------------------')
print('         GRIN 介质（负）          ')
print('----------------------------------')
print('预先计算的完整矩阵')
# ../help/matrix/ElemGrinMedium.png
M_GM_full_c = make_abcd(cosh(L*g), sinh(L*g)/g, g*sinh(L*g), cosh(L*g))
print_abcd("M_GM_full_c", M_GM_full_c)

print('----------------------------------')
print('矩阵乘积')

# 左半程
M_GM_lf_c = make_abcd(cosh(h1*g), sinh(h1*g)/g, g*sinh(h1*g), cosh(h1*g))
print_abcd("M_GM_lf_c", M_GM_lf_c)

# 右半程
M_GM_rt_c = make_abcd(cosh(h2*g), sinh(h2*g)/g, g*sinh(h2*g), cosh(h2*g))
print_abcd("M_GM_rt_c", M_GM_rt_c)

# 介质矩阵——前 2 个矩阵的乘积
M_GM_2_c = np.dot(M_GM_rt_c, M_GM_lf_c)
print_abcd("M_GM_2_c", M_GM_2_c) 
compare_abcd("M_GM_full_c == M_GM_2_c", M_GM_full_c, M_GM_2_c)

if show_lens:
  print('----------------------------------')
  print('         GRIN 透镜（负）          ')
  print('----------------------------------')
  print('预先计算的完整矩阵')
  # ../help/matrix/ElemGrinLens.png
  M_GL_full_c = make_abcd(cosh(L*g), sinh(L*g)/n0/g, n0*g*sinh(L*g), cosh(L*g))
  print_abcd("M_GL_full_c", M_GL_full_c)

  print('----------------------------------')
  print('矩阵乘积')

  # 进入介质并通过左半程
  # ../help/matrix/ElemGrinLens_left.png
  M_GL_lf_c = make_abcd(cosh(h1*g), sinh(h1*g)/n0/g, g*sinh(h1*g), cosh(h1*g)/n0)
  print_abcd("M_GL_lf_c", M_GL_lf_c)

  # 通过右半程并出射到空气中
  # ../help/matrix/ElemGrinLens_right.png
  M_GL_rt_c = make_abcd(cosh(h2*g), sinh(h2*g)/g, n0*g*sinh(h2*g), n0*cosh(h2*g))
  print_abcd("M_GL_rt_c", M_GL_rt_c)

  # 透镜矩阵——前 2 个矩阵的乘积
  M_GL_2_c = np.dot(M_GL_rt_c, M_GL_lf_c)
  print_abcd("M_GL_2_c", M_GL_2_c) 
  compare_abcd("M_GL_full_c == M_GL_2_c", M_GL_full_c, M_GL_2_c)

  # 透镜矩阵——3 个矩阵的乘积
  M_GL_3_c = np.dot(np.dot(M_out, M_GM_full_c), M_in)
  print_abcd("M_GL_3_c", M_GL_3_c) 
  compare_abcd("M_GL_full_c == M_GL_3_c", M_GL_full_c, M_GL_3_c)
