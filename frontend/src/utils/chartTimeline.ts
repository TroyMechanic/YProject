// One logical index must represent the same time in the price and MACD charts.
export function buildTimeline(candles: readonly { time: string }[], indicators: readonly { time: string }[], endpoints: readonly string[]): string[] {
  return [...new Set([...candles.map((row) => row.time), ...indicators.map((row) => row.time), ...endpoints].map((time) => time.slice(0, 19)))].sort();
}

export function visibleCandleRange(timeline: readonly string[], candles: readonly { time: string }[], focus?: { start: string; end: string }, padRight = true): { from: number; to: number } | null {
  if (!candles.length) return null;
  const focused = focus ? candles.filter((row) => row.time.slice(0, 10) >= focus.start && row.time.slice(0, 10) <= focus.end) : candles;
  const visible = focused.length ? focused : candles;
  const first = timeline.indexOf(visible[0].time.slice(0, 19));
  const last = timeline.indexOf(visible[visible.length - 1].time.slice(0, 19));
  if (first < 0 || last < first) return null;
  const padding = padRight ? Math.max(4, Math.ceil((last - first + 1) * 0.15)) : 0;
  return { from: first, to: last + padding };
}
