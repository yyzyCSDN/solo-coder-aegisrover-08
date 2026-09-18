import math

def logit(p):
    return math.log(p / (1 - p))

def logistic(l):
    return 1 / (1 + math.exp(-l))

def update(prior, occupied, p_hit=0.7, p_miss=0.4):
    l = logit(prior) + (logit(p_hit) if occupied else logit(p_miss))
    return min(0.999, max(0.001, logistic(l)))
