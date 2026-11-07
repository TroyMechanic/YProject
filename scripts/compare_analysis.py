"""Compare two full archived analysis JSON files without mutating either."""
import hashlib
import json
import sys
from pathlib import Path


def digest(value):
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def load(path):
    chart = json.loads(Path(path).read_text())
    metadata = chart['analysis']
    if metadata['resultHash'] != digest({key:value for key,value in chart.items() if key != 'analysis'}):
        raise ValueError(f'Result checksum failed: {path}')
    if metadata['inputHash'] != digest(chart['klines']):
        raise ValueError(f'Input checksum failed: {path}')
    return chart


def compare(left, right):
    if (left['symbol'], left['period']) != (right['symbol'], right['period']):
        raise ValueError('Only compare the same symbol and period.')
    report = {
        'symbol': left['symbol'], 'period': left['period'],
        'sameInput': left['analysis']['inputHash'] == right['analysis']['inputHash'],
        'sameEngine': left['analysis']['engineHash'] == right['analysis']['engineHash'],
        'before': left['analysis'], 'after': right['analysis'], 'changes': {},
    }
    for key in ['fractals', 'bis', 'segments', 'centralZones', 'signalZones', 'divergences', 'tradingPoints', 'zoneRelations']:
        # Reasons may change wording without changing the geometric result.
        previous = {json.dumps({k:v for k,v in item.items() if k != 'reasons'}, sort_keys=True, ensure_ascii=False) for item in left.get(key,[])}
        current = {json.dumps({k:v for k,v in item.items() if k != 'reasons'}, sort_keys=True, ensure_ascii=False) for item in right.get(key,[])}
        report['changes'][key] = {
            'beforeCount': len(left.get(key,[])), 'afterCount': len(right.get(key,[])),
            'removed': [json.loads(value) for value in sorted(previous-current)],
            'added': [json.loads(value) for value in sorted(current-previous)],
        }
    return report


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: python3 scripts/compare_analysis.py BEFORE.json AFTER.json')
    print(json.dumps(compare(load(sys.argv[1]), load(sys.argv[2])), ensure_ascii=False, indent=2))
