def wait_for_graph(waits, owners):
    g = {}
    for robot, resource in waits.items():
        owner = owners.get(resource)
        if owner and owner != robot:
            g.setdefault(robot, set()).add(owner)
    return g

def find_cycle(graph):
    visiting = set()
    done = set()
    stack = []

    def dfs(n):
        if n in visiting:
            i = stack.index(n)
            return stack[i:] + [n]
        if n in done:
            return None
        visiting.add(n)
        stack.append(n)
        for m in graph.get(n, ()):
            c = dfs(m)
            if c:
                return c
        stack.pop()
        visiting.remove(n)
        done.add(n)
        return None
    for n in graph:
        c = dfs(n)
        if c:
            return c
    return None
