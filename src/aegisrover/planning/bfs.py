from collections import deque

def shortest(start, goal, neighbors):
    q = deque([start])
    p = {start: None}
    while q:
        n = q.popleft()
        if n == goal:
            break
        for x in neighbors(n):
            if x not in p:
                p[x] = n
                q.append(x)
    if goal not in p:
        return None
    out = []
    n = goal
    while n is not None:
        out.append(n)
        n = p[n]
    return out[::-1]
