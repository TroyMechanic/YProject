import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildTimeline, visibleCandleRange } from '../src/utils/chartTimeline.ts';

test('old segment endpoints occupy the same whitespace index in both panes', () => {
  const candles = [{ time: '2026-10-08T10:00:00' }, { time: '2026-10-08T10:30:00' }];
  const times = buildTimeline(candles, candles, ['2026-08-28T11:30:00', candles[0].time]);
  assert.deepEqual(times, ['2026-08-28T11:30:00', candles[0].time, candles[1].time]);
  assert.deepEqual(visibleCandleRange(times, candles), { from: 1, to: 6 });
});

test('daily focus uses shared time indices rather than raw candle indices', () => {
  const candles = ['2026-08-28', '2026-09-01', '2026-09-02'].map((time) => ({ time }));
  const times = buildTimeline(candles, candles, ['2026-08-01']);
  assert.deepEqual(visibleCandleRange(times, candles, { start: '2026-09-01', end: '2026-09-30' }), { from: 2, to: 7 });
});

test('empty and unavailable focus do not invent candle data', () => {
  assert.equal(visibleCandleRange([], []), null);
  const candles = [{ time: '2026-10-08T10:00:00' }];
  const times = buildTimeline(candles, [], []);
  assert.deepEqual(visibleCandleRange(times, candles, { start: '2026-11-01', end: '2026-11-30' }), { from: 0, to: 4 });
  assert.equal(candles.length, 1);
});

test('explicit navigation focus does not bring later candles into the restored view', () => {
  const candles = ['2026-08-21', '2026-08-28', '2026-09-01'].map((time) => ({ time }));
  assert.deepEqual(visibleCandleRange(buildTimeline(candles, [], []), candles,
    { start: '2026-08-21', end: '2026-08-28' }, false), { from: 0, to: 1 });
});
