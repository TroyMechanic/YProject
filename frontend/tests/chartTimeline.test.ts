import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildTimeline, visibleCandleRange } from '../src/utils/chartTimeline.ts';

test('old segment endpoints extend the timeline without adding candles', () => {
  const candles = [{ time: '2026-10-08T10:00:00' }, { time: '2026-10-08T10:30:00' }];
  const times = buildTimeline(candles, ['2026-08-28T11:30:00', candles[0].time]);
  assert.deepEqual(times, ['2026-08-28T11:30:00', candles[0].time, candles[1].time]);
  assert.deepEqual(visibleCandleRange(times, candles), { from: 1, to: 6 });
});

test('empty and single-candle timelines', () => {
  assert.equal(visibleCandleRange([], []), null);
  const candles = [{ time: '2026-10-08T10:00:00' }];
  const times = buildTimeline(candles, []);
  assert.deepEqual(visibleCandleRange(times, candles), { from: 0, to: 4 });
  assert.equal(candles.length, 1);
});
