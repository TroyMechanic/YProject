import type { KlinePeriod } from '../types/chart';

export interface AnalysisWindow { start: string; end: string }

export const drillPeriods: { value: KlinePeriod; label: string }[] = [
  { value: 'monthly', label: '月K' }, { value: 'weekly', label: '周K' },
  { value: 'daily', label: '日K' }, { value: 'hour4', label: '4h' },
  { value: 'minute60', label: '60m' }, { value: 'minute30', label: '30m' },
  { value: 'minute5', label: '5m' }, { value: 'minute1', label: '1m' },
];

export function smallerPeriods(period: KlinePeriod) {
  return drillPeriods.slice(drillPeriods.findIndex((item) => item.value === period) + 1);
}

// Queries are day-based: include both endpoint trading days, including the
// complete calendar bucket represented by a weekly/monthly parent candle.
export function analysisWindow(first: string, last: string, period: KlinePeriod): AnalysisWindow {
  const days = [first.slice(0, 10), last.slice(0, 10)].sort();
  const start = new Date(`${days[0]}T00:00:00Z`);
  const end = new Date(`${days[1]}T00:00:00Z`);
  if (period === 'weekly') {
    start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7);
    end.setUTCDate(end.getUTCDate() + 6 - (end.getUTCDay() + 6) % 7);
  } else if (period === 'monthly') {
    start.setUTCDate(1);
    end.setUTCMonth(end.getUTCMonth() + 1, 0);
  }
  return { start: start.toISOString().slice(0, 10), end: end.toISOString().slice(0, 10) };
}

export function candleWindow(times: readonly string[], from: string, to: string, period: KlinePeriod): AnalysisWindow | null {
  const visible = times.filter((time) => time >= from && time <= to);
  return visible.length ? analysisWindow(visible[0], visible[visible.length - 1], period) : null;
}
