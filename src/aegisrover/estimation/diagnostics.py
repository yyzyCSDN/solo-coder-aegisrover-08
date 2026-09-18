import math
import numpy as np

def symmetry_error(matrix):
    m = np.asarray(matrix, float)
    return float(np.max(np.abs(m - m.T)))

def minimum_eigenvalue(matrix):
    m = np.asarray(matrix, float)
    return float(np.min(np.linalg.eigvalsh((m + m.T) / 2)))

def condition_number(matrix):
    return float(np.linalg.cond(np.asarray(matrix, float)))
