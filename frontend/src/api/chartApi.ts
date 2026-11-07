import type { ChartResponse, KlinePeriod, ResearchOptions, RuleCatalog, RuleProfile } from '../types/chart';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

export interface DateRange {
  startDate?: string;
  endDate?: string;
  period: KlinePeriod;
  mode?: "recursive" | "legacy"; basePeriod?: KlinePeriod; maxLevel?: number;
  preserveHierarchy?: boolean;
}

export async function fetchChart(symbol: string, range: DateRange): Promise<ChartResponse> {
  const params = new URLSearchParams();
  if (range.startDate) params.set('startDate', range.startDate);
  if (range.endDate) params.set('endDate', range.endDate);
  params.set('period', range.period);
  if (range.preserveHierarchy && range.mode === 'recursive') {
    if (range.basePeriod) params.set('basePeriod', range.basePeriod);
    if (range.maxLevel) params.set('maxLevel', String(range.maxLevel));
  }
  const query = params.toString();
  const response = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(symbol)}/${range.mode === "recursive" ? "structure/chart" : "chart"}${query ? `?${query}` : ''}`);
  return parseResponse(response);
}

export async function fetchRules(): Promise<RuleCatalog> {
  return parseResponse(await fetch(`${API_BASE}/api/chan/rules`));
}

export async function syncStock(symbol: string, range: DateRange, ruleProfile: RuleProfile, minKlineGap: number, options: ResearchOptions): Promise<void> {
  const response = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(symbol)}/${range.mode === "recursive" ? "structure/sync" : "sync"}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ period: range.period, startDate: range.startDate, endDate: range.endDate, ...(range.mode === "recursive" ? { basePeriod: range.basePeriod, maxLevel: range.maxLevel } : {}), ruleProfile, minKlineGap, ...options }),
  });
  await parseResponse(response);
}

export async function recalculate(symbol: string, range: DateRange, minKlineGap: number, ruleProfile: RuleProfile, options: ResearchOptions): Promise<void> {
  const response = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(symbol)}/${range.mode === "recursive" ? "structure/recalculate" : "chan/recalculate"}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ period: range.period, startDate: range.startDate, endDate: range.endDate, ...(range.mode === "recursive" ? { basePeriod: range.basePeriod, maxLevel: range.maxLevel } : {}), minKlineGap, ruleProfile, ...options }),
  });
  await parseResponse(response);
}

async function parseResponse<T>(response: Response): Promise<T> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = payload?.detail ?? `HTTP ${response.status}`;
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return payload as T;
}
