import numpy as np

def predict(x, P, F, Q):
    x = np.asarray(F, float) @ np.asarray(x, float)
    P = np.asarray(F, float) @ np.asarray(P, float) @ np.asarray(F, float).T + np.asarray(Q, float)
    return (x, P)

def update(x, P, z, H, R):
    x = np.asarray(x, float)
    P = np.asarray(P, float)
    z = np.asarray(z, float)
    H = np.asarray(H, float)
    R = np.asarray(R, float)
    y = z - H @ x
    S = H @ P @ H.T + R
    K = P @ H.T @ np.linalg.inv(S)
    xn = x + K @ y
    I = np.eye(P.shape[0])
    A = I - K @ H
    Pn = A @ P @ A.T + K @ R @ K.T
    return (xn, Pn)
