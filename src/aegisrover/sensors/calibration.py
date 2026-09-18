import numpy as np

def affine_fit(raw, truth):
    x = np.c_[np.asarray(raw, float), np.ones(len(raw))]
    y = np.asarray(truth, float)
    coef = np.linalg.lstsq(x, y, rcond=None)[0]
    return coef

def apply(value, coef):
    return float(np.dot([value, 1], coef))
