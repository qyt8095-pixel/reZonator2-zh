#!/usr/bin/env python

import numpy as np
from math import *
from rezonator import *

n = 1.5                # 折射率
L = 0.01               # 透镜厚度
L1 = L * 0.2
L2 = L - L1
R1 = 0.09              # -->(//  R > 0
R2 = -0.15             # //)-->  R < 0

#R1 = float('inf')
#R2 = float('inf')

print('----------------------------------')
print_res('光程', L * n)
print_res('子程段', L1)

print('----------------------------------')
print('预先计算的完整矩阵')
# ../help/matrix/ElemThickLens.png
A = 1 - L/R1*(n-1)/n
B = L/n
C = (n-1)*(1/R2 - 1/R1) - L/R1/R2*(n-1)*(n-1)/n
D = 1 + L/R2*(n-1)/n
M_full = make_abcd(A, B, C, D)
print_abcd("M(pre)", M_full)

R1_inv = -R2
R2_inv = -R1
A = 1 - L/R1_inv*(n-1)/n
B = L/n
C = (n-1)*(1/R2_inv - 1/R1_inv) - L/R1_inv/R2_inv*(n-1)*(n-1)/n
D = 1 + L/R2_inv*(n-1)/n
M_full_inv = make_abcd(A, B, C, D)
print_abcd("M(pre, inv)", M_full_inv)

print('----------------------------------')
print('4 个矩阵的乘积')

# 进入介质
M_in = make_abcd(1, 0, -(n-1)/R1/n, 1/n)
# 通过介质的左半程
M_1 = make_abcd(1, L1, 0, 1)
# 通过介质的右半程
M_2 = make_abcd(1, L2, 0, 1)
# 出射到空气中
M_out = make_abcd(1, 0, (n-1)/R2, n)

# 完整矩阵——前 4 个矩阵的乘积
M_4 = np.linalg.multi_dot([M_out, M_2, M_1, M_in])
print_abcd("M(4)", M_4)
compare_abcd("M_full == M_4", M_full, M_4)

print('----------------------------------')
print('2 个矩阵的乘积')

# 进入介质并通过左半程
# ../help/matrix/ElemThickLens_left.png
M_lf = make_abcd(1 - L1*(n-1)/R1/n, L1/n, -(n-1)/R1/n, 1/n)
print_abcd("M_lf", M_lf) 

# 通过右半程并出射到空气中
# ../help/matrix/ElemThickLens_right.png
M_rt = make_abcd(1, L2, (n-1)/R2, L2*(n-1)/R2 + n)
print_abcd("M_rt", M_rt) 

# 平板矩阵——前 2 个矩阵的乘积
M_2 = np.dot(M_rt, M_lf)
print_abcd("M(2)", M_2) 
compare_abcd("M_full == M_2", M_full, M_2)
compare_abcd("M_2 == M_4", M_2, M_4)
