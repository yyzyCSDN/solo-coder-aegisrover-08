from dataclasses import dataclass

@dataclass(frozen=True)
class Capability:
    name: str
    major: int
    minor: int
    features: frozenset[str]

def negotiate(required, offered):
    by_name = {c.name: c for c in offered}
    chosen = {}
    for req in required:
        got = by_name.get(req.name)
        if got is None or got.major != req.major or got.minor < req.minor or (not req.features <= got.features):
            raise ValueError(req.name)
        chosen[req.name] = got
    return chosen
