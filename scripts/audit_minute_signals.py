"""Read-only signal funnel audit of committed local snapshots.

Run with backend/.venv/bin/python scripts/audit_minute_signals.py --as-of YYYY-MM-DD.
No provider fetch, snapshot rebuild, or CSV writes are performed.
"""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from app.models.schemas import ChartResponse, KlinePeriod
from app.services.hierarchy_service import map_time
from app.services.recursive_analyzer import RecursiveAnalyzer
from app.services.rule_policy import digest


def read_snapshot(path):
    payload = json.loads(path.read_text())
    chart = ChartResponse.model_validate(payload)
    if digest({k: v for k, v in payload.items() if k != 'analysis'}) != chart.analysis.result_hash:
        raise ValueError(f'Invalid result checksum: {path}')
    if digest(payload['klines']) != chart.analysis.input_hash:
        raise ValueError(f'Invalid input checksum: {path}')
    return chart


def counts(points):
    return {'confirmed': sum(p.confirmed for p in points),
            'candidates': sum(not p.confirmed for p in points),
            'types': dict(Counter(p.type for p in points))}


def day(value):
    return value.date() if isinstance(value, datetime) else value


def audit(directory, symbol, as_of):
    base = read_snapshot(directory / f'{symbol}_minute5_analysis.json')
    hierarchy = RecursiveAnalyzer().analyze(base, base.analysis.settings, 4)
    recursive = [p for layer in hierarchy.layers for p in layer.trading_points]
    combined = hierarchy.base_trading_points + recursive
    result = {'symbol': symbol, 'basePeriod': 'minute5',
              'baseRunId': base.analysis.run_id, 'baseInputHash': base.analysis.input_hash,
              'baseStart': base.analysis.source_start, 'baseEnd': base.analysis.source_end,
              'settings': base.analysis.settings.model_dump(mode='json', by_alias=True),
              'baseBiObservations': counts(hierarchy.base_trading_points),
              'recursivePoints': counts(recursive),
              'layers': [{'level': l.level, 'units': len(l.movements), 'zones': len(l.zones),
                          'points': counts(l.trading_points)} for l in hierarchy.layers],
              'displays': []}
    for period in (KlinePeriod.MINUTE_1, KlinePeriod.MINUTE_5,
                   KlinePeriod.MINUTE_30, KlinePeriod.MINUTE_60):
        chart = read_snapshot(directory / f'{symbol}_{period.value}_analysis.json')
        start = as_of - timedelta(days=29 if period == KlinePeriod.MINUTE_5 else 9)
        window = [b for b in chart.klines if day(b.time) >= start]
        visible = [p for p in combined if day(p.observed_at) >= start]
        drawable = [p for p in visible if map_time(p.observed_at, window, period) is not None]
        all_drawable = [p for p in combined if map_time(p.observed_at, chart.klines, period) is not None]
        result['displays'].append({
            'period': period.value, 'sourceCount': len(chart.klines),
            'sourceStart': chart.analysis.source_start, 'sourceEnd': chart.analysis.source_end,
            'standaloneBis': len(chart.bis), 'standaloneSegments': len(chart.segments),
            'standaloneZones': len(chart.signal_zones),
            'standaloneDivergences': dict(Counter(d.type for d in chart.divergences)),
            'standalonePoints': counts(chart.trading_points),
            'drawableCombinedPointsWithoutDateCrop': counts(all_drawable),
            'defaultWindowStart': start.isoformat(), 'windowKlines': len(window),
            'windowPointsByConfirmationTime': counts(visible), 'windowDrawablePoints': counts(drawable)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    parser.add_argument('--symbol', action='append')
    args = parser.parse_args()
    report = {'asOf': args.as_of.isoformat(), 'basis': 'committed local snapshots; default 5m base',
              'symbols': [audit(ROOT / 'backend/app/data/analyzed', symbol, args.as_of)
                          for symbol in (args.symbol or ['002156.SZ', '002475.SZ'])]}
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == '__main__':
    main()
