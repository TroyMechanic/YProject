import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adjacentPeriod, candleBucket, makeWheelFocus, wheelLogicalRange } from '../src/utils/wheelNavigation.ts';

test('automatic ladder skips 4h and reverses into the actual prior period', () => {
  assert.equal(adjacentPeriod('daily', 'in'), 'minute60');
  assert.equal(adjacentPeriod('hour4', 'in'), 'minute60');
  assert.equal(adjacentPeriod('minute60', 'out', 'hour4'), 'hour4');
  assert.equal(adjacentPeriod('minute1', 'in'), null);
  assert.equal(adjacentPeriod('monthly', 'out'), null);
});

test('intraday buckets exclude the previous closing boundary', () => {
  assert.deepEqual(candleBucket('2026-08-21T10:30:00', 'minute30'), { start: '2026-08-21T10:00:01', end: '2026-08-21T10:30:00' });
});

test('daily expands within the same date and retains the anchor horizontal ratio', () => {
  const times = ['2026-08-21T10:30:00', '2026-08-21T11:30:00', '2026-08-21T14:00:00', '2026-08-21T15:00:00'];
  const focus = makeWheelFocus(['2026-08-21'], 'daily', '2026-08-21', '2026-08-21', '2026-08-21', 0.7)!;
  const range = wheelLogicalRange(times, times.map((time) => ({ time })), 'minute60', focus)!;
  assert.ok(Math.abs((3 - range.from + 0.5) / (range.to - range.from + 1) - 0.7) < 1e-9);
  assert.equal(range.to - range.from + 1, 4);
});

test('minute viewport keeps sub-day focus rather than expanding to whole days', () => {
  const times = ['2026-08-21T10:30:00', '2026-08-21T11:30:00', '2026-08-21T14:00:00'];
  const focus = makeWheelFocus(times, 'minute60', times[0], times[1], times[1], 0.5)!;
  assert.equal(focus.start, '2026-08-21T09:30:01');
  assert.equal(focus.end, '2026-08-21T11:30:00');
});

test('missing anchor cannot snap to a different date or an earlier part of the hour', () => {
  const focus = makeWheelFocus(['2026-08-21T11:30:00'], 'minute60', '2026-08-21T11:30:00', '2026-08-21T11:30:00', '2026-08-21T11:30:00', 0.5)!;
  const times = ['2026-08-21T11:00:00', '2026-08-24T11:30:00'];
  assert.equal(wheelLogicalRange(times, times.map((time) => ({ time })), 'minute30', focus), null);
  assert.equal(makeWheelFocus(times, 'minute30', '2020', '2021', times[0], 0.5), null);
});

test('zoom out maps an intraday anchor into its containing higher candle', () => {
  const times = ['2026-08-21T10:30:00', '2026-08-21T11:30:00'];
  const focus = makeWheelFocus(['2026-08-21T10:00:00'], 'minute30', '2026-08-21T10:00:00', '2026-08-21T10:00:00', '2026-08-21T10:00:00', 0.5)!;
  assert.deepEqual(wheelLogicalRange(times, times.map((time) => ({ time })), 'minute60', focus), { from: 0, to: 0 });
});

test('period buttons reset extreme zoom while retaining the mapped center', async () => {
  const { periodButtonRange } = await import('../src/utils/wheelNavigation.ts');
  const times = ['2026-08-21T10:30:00', '2026-08-21T11:30:00', '2026-08-21T14:00:00', '2026-08-21T15:00:00'];
  const anchor = makeWheelFocus(['2026-08-21'], 'daily', '2026-08-21', '2026-08-21', '2026-08-21', 0.5)!;
  const range = periodButtonRange(times, times.map(time => ({ time })), 'minute60', 1292, { anchor })!;
  assert.equal((range.from + range.to) / 2, 3);
  assert(1292 / (range.to - range.from + 1) <= 24);
});

test('period button fallback places latest real candle in view, including sparse history', async () => {
  const { periodButtonRange } = await import('../src/utils/wheelNavigation.ts');
  const times = ['2026-08-21T10:30:00'];
  for (const width of [320, 1292]) {
    const range = periodButtonRange(times, times.map(time => ({ time })), 'minute60', width, {})!;
    assert(range.from <= 0 && range.to >= 0);
    assert(Math.abs((0 - range.from + 0.5) / (range.to - range.from + 1) - 0.9) < 1e-9);
    assert(width / (range.to - range.from + 1) <= 24);
  }
  assert.equal(periodButtonRange([], [], 'daily', 1292, {}), null);
});
