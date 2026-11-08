export function buildTimeline(candles: readonly { time: string }[], endpoints: readonly string[]): string[] {
  return [...new Set([...candles.map((row) => row.time), ...endpoints].map((time) => time.slice(0, 19)))].sort();
}

export function visibleCandleRange(timeline: readonly string[], candles: readonly { time: string }[]): { from: number; to: number } | null {
  if (!candles.length) return null;
  const first = timeline.indexOf(candles[0].time.slice(0, 19));
  const last = timeline.indexOf(candles[candles.length - 1].time.slice(0, 19));
  if (first < 0 || last < first) return null;
  const padding = Math.max(4, Math.ceil((last - first + 1) * 0.15));
  return { from: first, to: last + padding };
}
