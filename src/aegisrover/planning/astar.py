import heapq, math

def astar(start, goal, neighbors, cost):
    q = [(0.0, 0, start, None)]
    seq = 1
    g = {start: 0.0}
    parent = {}
    while q:
        _, _, cur, par = heapq.heappop(q)
        if par is not None and cur not in parent:
            parent[cur] = par
        if cur == goal:
            path = [cur]
            while path[-1] != start:
                path.append(parent[path[-1]])
            return (list(reversed(path)), g[cur])
        for nxt in neighbors(cur):
            ng = g[cur] + cost(cur, nxt)
            if ng < g.get(nxt, float('inf')):
                g[nxt] = ng
                parent[nxt] = cur
                h = math.hypot(goal[0] - nxt[0], goal[1] - nxt[1]) if isinstance(goal, tuple) and isinstance(nxt, tuple) and (len(goal) >= 2) and (len(nxt) >= 2) else 0.0
                heapq.heappush(q, (ng + h, seq, nxt, cur))
                seq += 1
    return (None, float('inf'))
