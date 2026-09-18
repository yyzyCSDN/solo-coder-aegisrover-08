from dataclasses import dataclass

@dataclass(frozen=True)
class Patch:
    base_version: int
    changes: dict

def merge(base, current, patch: Patch):
    if patch.base_version > current['version']:
        raise ValueError('future base')
    if patch.base_version < current['version']:
        changed_since = set(current.get('changed_since', ()))
        conflict = changed_since & set(patch.changes)
        if conflict:
            raise ValueError(f'conflict:{sorted(conflict)}')
    cells = dict(current['cells'])
    cells.update(patch.changes)
    return {'version': current['version'] + 1, 'cells': cells, 'changed_since': set(patch.changes)}
