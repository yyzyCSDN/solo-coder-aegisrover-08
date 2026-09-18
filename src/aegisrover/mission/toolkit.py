import math

def topological_order(tasks, dependencies):
    incoming = {t: set(dependencies.get(t, ())) for t in tasks}
    ready = sorted((t for t, deps in incoming.items() if not deps))
    out = []
    while ready:
        task = ready.pop(0)
        out.append(task)
        for other in tasks:
            if task in incoming[other]:
                incoming[other].remove(task)
                if not incoming[other] and other not in out and (other not in ready):
                    ready.append(other)
                    ready.sort()
    if len(out) != len(tasks):
        raise ValueError('cycle')
    return out

def critical_path(durations, dependencies):
    order = topological_order(list(durations), dependencies)
    finish = {}
    for task in order:
        start = max((finish[d] for d in dependencies.get(task, ())), default=0.0)
        finish[task] = start + durations[task]
    return (max(finish.values(), default=0.0), finish)

def ready_tasks(tasks, completed, dependencies):
    return [t for t in tasks if t not in completed and set(dependencies.get(t, ())) <= set(completed)]

def resource_load(assignments):
    load = {}
    for item in assignments:
        load[item['resource']] = load.get(item['resource'], 0.0) + item.get('duration', 0.0)
    return load

def deadline_slack(finish, deadline):
    return deadline - finish

def mission_progress(states):
    if not states:
        return 1.0
    done = sum((1 for s in states.values() if s in {'completed', 'cancelled'}))
    return done / len(states)
