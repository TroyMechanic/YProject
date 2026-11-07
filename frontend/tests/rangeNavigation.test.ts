import { test } from 'node:test';
import assert from 'node:assert/strict';
import { analysisWindow, candleWindow, smallerPeriods } from '../src/utils/rangeNavigation.ts';

test('daily selection retains both endpoint dates when drilling into 4h', () => {
  assert.deepEqual(analysisWindow('2026-09-30', '2026-09-17', 'daily'), { start: '2026-09-17', end: '2026-09-30' });
  assert.equal(smallerPeriods('daily')[0].value, 'hour4');
  assert.equal(smallerPeriods('hour4')[0].value, 'minute60');
  assert.deepEqual(smallerPeriods('minute1'), []);
});

test('intraday selection explicitly includes complete endpoint trading days', () => {
  assert.deepEqual(analysisWindow('2026-09-30T10:30:00', '2026-09-30T14:00:00', 'minute30'), { start: '2026-09-30', end: '2026-09-30' });
});

test('weekly and monthly parents include their complete calendar buckets', () => {
  assert.deepEqual(analysisWindow('2026-01-02', '2026-01-09', 'weekly'), { start: '2025-12-29', end: '2026-01-11' });
  assert.deepEqual(analysisWindow('2024-02-29', '2024-02-29', 'monthly'), { start: '2024-02-01', end: '2024-02-29' });
});

test('visible selection uses actual candles, ignoring padded geometry and blank space', () => {
  const times = ['2026-09-17', '2026-09-18', '2026-09-21'];
  assert.deepEqual(candleWindow(times, '2026-08-01', '2026-09-18', 'daily'), { start: '2026-09-17', end: '2026-09-18' });
  assert.equal(candleWindow(times, '2026-08-01', '2026-08-30', 'daily'), null);
});
