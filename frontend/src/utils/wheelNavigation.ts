import type { KlinePeriod } from '../types/chart';

export type ZoomDirection = 'in' | 'out';
export interface WheelFocus {
  start: string;
  end: string;
  anchor: string;
  anchorRatio: number;
  sourcePeriod: KlinePeriod;
}
const ladder: KlinePeriod[] = ['monthly', 'weekly', 'daily', 'minute60', 'minute30', 'minute5', 'minute1'];
export const ZOOM_IN_SPACING = 70;
export const ZOOM_OUT_SPACING = 7;
export const RETURN_EXPANSION = 1.5;

export function adjacentPeriod(period: KlinePeriod, direction: ZoomDirection, previous?: KlinePeriod): KlinePeriod | null {
  if (direction === 'out' && previous) return previous;
  if (period === 'hour4') return direction === 'in' ? 'minute60' : 'weekly';
  return ladder[ladder.indexOf(period) + (direction === 'in' ? 1 : -1)] ?? null;
}

// Market timestamps are wall-clock values, represented in UTC solely for arithmetic.
export function candleBucket(time: string, period: KlinePeriod): { start: string; end: string } {
  const date = time.slice(0, 10);
  let start = new Date(`${date}T00:00:00Z`);
  let end = new Date(`${date}T23:59:59Z`);
  const minutes: number | undefined = ({ minute1: 1, minute5: 5, minute30: 30, minute60: 60 } as Partial<Record<KlinePeriod, number>>)[period];
  if (minutes) {
    end = new Date(`${time.slice(0, 19)}Z`);
    start = new Date(end.getTime() - minutes * 60_000 + 1000);
  } else if (period === 'weekly') {
    start.setUTCDate(start.getUTCDate() - (start.getUTCDay() + 6) % 7);
    end.setUTCDate(end.getUTCDate() + 6 - (end.getUTCDay() + 6) % 7);
  } else if (period === 'monthly') {
    start.setUTCDate(1);
    end.setUTCMonth(end.getUTCMonth() + 1, 0);
  }
  return { start: start.toISOString().slice(0, 19), end: end.toISOString().slice(0, 19) };
}

export function makeWheelFocus(times: readonly string[], period: KlinePeriod, from: string, to: string, anchor: string, anchorRatio: number): WheelFocus | null {
  const visible = times.filter((time) => time >= from && time <= to);
  if (!visible.length || !times.includes(anchor)) return null;
  return { start: candleBucket(visible[0], period).start, end: candleBucket(visible[visible.length - 1], period).end,
    anchor, sourcePeriod: period, anchorRatio: Math.max(0.02, Math.min(0.98, anchorRatio)) };
}

/** Null means no candles at the anchor, not permission to jump to distant history. */
export function wheelLogicalRange(timeline: readonly string[], candles: readonly { time: string }[], period: KlinePeriod, focus: WheelFocus): { from: number; to: number } | null {
  const sourceBucket = candleBucket(focus.anchor, focus.sourcePeriod);
  const matches = candles.filter((bar) => {
    const bucket = candleBucket(bar.time, period);
    if (focus.sourcePeriod.startsWith('minute')) return bucket.start <= focus.anchor.slice(0, 19) && bucket.end >= focus.anchor.slice(0, 19);
    return bucket.end >= sourceBucket.start && bucket.start <= sourceBucket.end;
  });
  if (!matches.length) return null;
  // Preserve the timestamp for intraday transitions; coarse candles expand into
  // their closing available child candle, without jumping to another date.
  const anchor = matches[matches.length - 1];
  const visible = candles.filter((bar) => {
    const bucket = candleBucket(bar.time, period);
    return bucket.end >= focus.start && bucket.start <= focus.end;
  });
  if (!visible.length) return null;
  const first = timeline.indexOf(visible[0].time.slice(0, 19));
  const last = timeline.indexOf(visible[visible.length - 1].time.slice(0, 19));
  const at = timeline.indexOf(anchor.time.slice(0, 19));
  if (first < 0 || last < first || at < 0) return null;
  const count = last - first + 1;
  const from = at + 0.5 - focus.anchorRatio * count;
  return { from, to: from + count - 1 };
}

export interface PeriodViewport { anchor?: WheelFocus }

// Manual period selection starts with readable candles, independently of the
// previous zoom density. Empty space is preferable to inventing missing bars.
export function periodButtonRange(timeline: readonly string[], candles: readonly { time: string }[], period: KlinePeriod,
  width: number, focus: PeriodViewport): { from: number; to: number } | null {
  if (!candles.length || width <= 0) return null;
  const anchorRange = focus.anchor ? wheelLogicalRange(timeline, candles, period, { ...focus.anchor, anchorRatio: 0.5 }) : null;
  const last = timeline.indexOf(candles[candles.length - 1].time.slice(0, 19));
  const first = timeline.indexOf(candles[0].time.slice(0, 19));
  if (first < 0 || last < first) return null;
  const count = Math.max(Math.ceil(width / 24), Math.min(120, Math.ceil(width / 12), last - first + 5));
  const anchorIndex = anchorRange ? (anchorRange.from + anchorRange.to) / 2 : last;
  const from = anchorIndex + 0.5 - (anchorRange ? 0.5 : 0.9) * count;
  return { from, to: from + count - 1 };
}
