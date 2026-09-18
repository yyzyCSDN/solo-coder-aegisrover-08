from collections import Counter

def summarize_packets(packets):
    seq = [p['seq'] for p in packets]
    missing = 0
    dupes = len(seq) - len(set(seq))
    for a, b in zip(seq, seq[1:]):
        if b > a + 1:
            missing += b - a - 1
    kinds = Counter((p.get('kind', 'unknown') for p in packets))
    return {'count': len(packets), 'duplicates': dupes, 'missing': missing, 'kinds': dict(kinds)}

def latency_stats(packets):
    xs = [p['received'] - p['sent'] for p in packets if 'received' in p and 'sent' in p]
    return {'min': min(xs) if xs else None, 'max': max(xs) if xs else None, 'avg': sum(xs) / len(xs) if xs else None}
