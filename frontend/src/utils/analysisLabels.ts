export function strengthLabel(value: string): string {
  return ({ STRONG: '强', NORMAL: '中', WEAK: '弱', UNAVAILABLE: '不足以比较' } as Record<string, string>)[value] ?? value;
}
export function pointLabel(value: string): string {
  return ({ B1: '一买', B2: '二买', B3: '三买', S1: '一卖', S2: '二卖', S3: '三卖' } as Record<string, string>)[value] ?? value;
}
export function trendLabel(value: string): string {
  return ({ TREND_UP: '上涨趋势', TREND_DOWN: '下跌趋势', CONSOLIDATION: '盘整', INSUFFICIENT: '结构不足',
    CORE_OVERLAP: '核心重叠 / 扩展', EXPANSION: '包络重叠 / 扩张候选' } as Record<string, string>)[value] ?? value;
}
export function divergenceLabel(value: string): string {
  return ({ TREND: '趋势背驰', CONSOLIDATION: '盘整背驰', LOCAL: '局部动能衰减' } as Record<string, string>)[value] ?? value;
}

export function pointSource(point: { structuralLevel: number | null; sourcePeriod: string | null; level: string }): string {
  const periods: Record<string,string> = { minute1: '1m', minute5: '5m', minute30: '30m', minute60: '60m' };
  return point.structuralLevel != null ? `${periods[point.sourcePeriod ?? ''] ?? point.sourcePeriod} · L${point.structuralLevel}` : point.sourcePeriod && point.level === 'bi' ? `${periods[point.sourcePeriod] ?? point.sourcePeriod} · 笔级观察` : point.level === 'bi' ? '笔级近似' : '线段级近似';
}

export function periodLabel(period: string): string {
  return ({daily:'日K',weekly:'周K',monthly:'月K',hour4:'4H',minute60:'60m',minute30:'30m',minute5:'5m',minute1:'1m'} as Record<string,string>)[period] ?? period;
}
