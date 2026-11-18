#!/usr/bin/env python

import numpy as np
from math import pi
from cmath import cos, sin, sqrt
from rezonator import make_abcd, print_abcd_c, print_res, compare_abcd

wl = 980e-9     # 波长
n0 = 1.5        # 折射率
n2 = 0.2        # 折射率梯度
L = 0.01        # 透镜厚度
h1 = 0.003      # 左半程
h2 = L - h1     # 右半程
a2 = 2e6        # 损耗因子
F = 0.6         # 焦距范围
g = sqrt((n2/n0 + 1j*wl*a2/n0/2/pi))
print_res("L", L)
print_res("n0", n0)
print_res("n2", n2)
print_res("a2", a2)
print_res("wl", wl)
print_res("gamma", g)

M_out = make_abcd(1, 0, 0, n0)
M_in = make_abcd(1, 0, 0, 1/n0)

print('----------------------------------')
print('----------------------------------')
print('             高斯光阑             ')
print('----------------------------------')
print_res("C", -1j*wl*a2/2/pi)

print('----------------------------------')
print('----------------------------------')
print('           高斯光阑透镜           ')
print('----------------------------------')
print_res("C", -1/F - 1j*wl*a2/2/pi)

print('----------------------------------')
print('----------------------------------')
print('           高斯导管介质           ')
print('----------------------------------')
print('预先计算的完整矩阵')
# ../help/matrix/ElemGrinMedium.png
M_GM_full = make_abcd(cos(L*g), sin(L*g)/g, -g*sin(L*g), cos(L*g))
print_abcd_c("M_GM_full", M_GM_full)

print('----------------------------------')
print('矩阵乘积')

# 左半程
M_GM_lf = make_abcd(cos(h1*g), sin(h1*g)/g, -g*sin(h1*g), cos(h1*g))
print_abcd_c("M_GM_lf", M_GM_lf)

# 右半程
M_GM_rt = make_abcd(cos(h2*g), sin(h2*g)/g, -g*sin(h2*g), cos(h2*g))
print_abcd_c("M_GM_rt", M_GM_rt)

# 介质矩阵——前 2 个矩阵的乘积
M_GM_2 = np.dot(M_GM_rt, M_GM_lf)
print_abcd_c("M_GM_2", M_GM_2) 
compare_abcd("M_GM_full == M_GM_2", M_GM_full, M_GM_2)

print('----------------------------------')
print('           高斯导管平板           ')
print('----------------------------------')
print('预先计算的完整矩阵')
# ../help/matrix/ElemGrinLens.png
M_GL_full = make_abcd(cos(L*g), sin(L*g)/g/n0, -g*n0*sin(L*g), cos(L*g))
print_abcd_c("M_GL_full", M_GL_full)

print('----------------------------------')
print('矩阵乘积')

# 进入介质并通过左半程
# ../help/matrix/ElemGrinLens_left.png
M_GL_lf = make_abcd(cos(h1*g), sin(h1*g)/g/n0, -g*sin(h1*g), cos(h1*g)/n0)
print_abcd_c("M_GL_lf", M_GL_lf)

# 通过右半程并出射到空气中
# ../help/matrix/ElemGrinLens_right.png
M_GL_rt = make_abcd(cos(h2*g), sin(h2*g)/g, -g*n0*sin(h2*g), n0*cos(h2*g))
print_abcd_c("M_GL_rt", M_GL_rt)

# 透镜矩阵——前 2 个矩阵的乘积
M_GL_2 = np.dot(M_GL_rt, M_GL_lf)
print_abcd_c("M_GL_2", M_GL_2) 
compare_abcd("M_GL_full == M_GL_2", M_GL_full, M_GL_2)

# 透镜矩阵——3 个矩阵的乘积
M_GL_3 = np.dot(np.dot(M_out, M_GM_full), M_in)
print_abcd_c("M_GL_3", M_GL_3) 
compare_abcd("M_GL_full == M_GL_3", M_GL_full, M_GL_3)
