#!/usr/bin/env python

import numpy as np
from math import *
from rezonator import *

n = 1.5                # 折射率
a = radians(15)        # 入射角
b = asin(sin(a)/n)     # 介质内角度
L = 0.0045             # 平板长度
L1 = L * 0.2
L2 = L - L1

print('----------------------------------')
print_res('入射角', a)
print_res('光程', L * n)
print_res('子程段', L1)

print('----------------------------------')
print('预先计算的完整矩阵')
# ../help/matrix/ElemTiltedCrystal.png
M_t_full = make_abcd(1, n * L * sqr(cos(a)) / (sqr(n) - sqr(sin(a))), 0, 1)
M_s_full = make_abcd(1, L / n, 0, 1)
print_abcd("M_t(pre)", M_t_full)
print_abcd("M_s(pre)", M_s_full)

print('----------------------------------')
print('4 个矩阵的乘积')

# 进入介质
M_in_t = make_abcd(cos(b)/cos(a), 0, 0, 1/n * cos(a)/cos(b))
M_in_s = make_abcd(1, 0, 0, 1/n)
# 通过介质的左半程
M_1 = make_abcd(1, L1, 0, 1)
# 通过介质的右半程
M_2 = make_abcd(1, L2, 0, 1)
# 出射到空气中
M_out_t = make_abcd(cos(a)/cos(b), 0, 0, n * cos(b)/cos(a))
M_out_s = make_abcd(1, 0, 0, n)

# 完整矩阵——前 4 个矩阵的乘积
M_t_4 = np.linalg.multi_dot([M_out_t, M_2, M_1, M_in_t])
M_s_4 = np.linalg.multi_dot([M_out_s, M_2, M_1, M_in_s])
print_abcd("M_t(4)", M_t_4)
print_abcd("M_s(4)", M_s_4)
compare_abcd("M_t_full == M_t_4", M_t_full, M_t_4)
compare_abcd("M_s_full == M_s_4", M_s_full, M_s_4)

print('----------------------------------')
print('2 个矩阵的乘积')

# 进入介质并通过左半程
# ../help/matrix/ElemTiltedCrystal_left.png
M_lf_t = make_abcd(cos(b)/cos(a), L1/n * cos(a)/cos(b), 0, 1/n * cos(a)/cos(b))
M_lf_s = make_abcd(1, L1/n, 0, 1/n)
print_abcd("M_lf_t", M_lf_t) 
print_abcd("M_lf_s", M_lf_s)

# 通过右半程并出射到空气中
# ../help/matrix/ElemTiltedCrystal_right.png
M_rt_t = make_abcd(cos(a)/cos(b), L2 * cos(a)/cos(b), 0, n * cos(b)/cos(a))
M_rt_s = make_abcd(1, L2, 0, n)
print_abcd("M_rt_t", M_rt_t) 
print_abcd("M_rt_s", M_rt_s)

# 平板矩阵——前 2 个矩阵的乘积
M_t_2 = np.dot(M_rt_t, M_lf_t)
M_s_2 = np.dot(M_rt_s, M_lf_s)
print_abcd("M_t(2)", M_t_2) 
print_abcd("M_s(2)", M_s_2)
compare_abcd("M_t_full == M_t_2", M_t_full, M_t_2)
compare_abcd("M_s_full == M_s_2", M_s_full, M_s_2)
