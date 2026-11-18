#!/usr/bin/env python

import numpy as np
from math import *
from rezonator import *

n = 1.2     # 折射率
L = 0.088   # 平板长度
L1 = L * 0.2
L2 = L - L1

print('----------------------------------')
print_res('光程', L * n)
print_res('子程段', L1)

print('----------------------------------')
print('预先计算的完整矩阵')
# ../help/matrix/ElemPlate.png
M_full = make_abcd(1, L / n, 0, 1)
print_abcd("M_full", M_full)

print('----------------------------------')
print('4 个矩阵的乘积')

# 进入介质
M_in = make_abcd(1, 0, 0, 1/n)
# 通过介质的左半程
M_1 = make_abcd(1, L1, 0, 1)
# 通过介质的右半程
M_2 = make_abcd(1, L2, 0, 1)
# 出射到空气中
M_out = make_abcd(1, 0, 0, n)

# 完整矩阵——前 4 个矩阵的乘积
M_4 = np.linalg.multi_dot([M_out, M_2, M_1, M_in])
print_abcd("M_4(4)", M_4)
compare_abcd("M_full == M_4", M_full, M_4)

print('----------------------------------')
print('2 个矩阵的乘积')

# 进入介质并通过左半程
# ../help/matrix/ElemPlate_left.png
M_lf = make_abcd(1, L1/n, 0, 1/n)
print_abcd("M_lf", M_lf) 

# 通过右半程并出射到空气中
# ../help/matrix/ElemPlate_right.png
M_rt = make_abcd(1, L2, 0, n)
print_abcd("M_rt", M_rt) 

# 平板矩阵——前 2 个矩阵的乘积
M_2 = np.dot(M_rt, M_lf)
print_abcd("M_2", M_2) 
compare_abcd("M_full == M_2", M_full, M_2)
