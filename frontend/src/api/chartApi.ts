import type { ChartResponse, KlinePeriod } from '../types/chart';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000';

export interface DateRange {
  startDate?: string;
  endDate?: string;
  period: KlinePeriod;
}

export async function fetchChart(symbol: string, range: DateRange): Promise<ChartResponse> {
  const params = new URLSearchParams();
  if (range.startDate) params.set('startDate', range.startDate);
  if (range.endDate) params.set('endDate', range.endDate);
  params.set('period', range.period);
  const query = params.toString();
  const response = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(symbol)}/chart${query ? `?${query}` : ''}`);
  return parseResponse(response);
}

export async function syncStock(symbol: string, range: DateRange): Promise<void> {
  const response = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(symbol)}/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(range),
  });
  await parseResponse(response);
}

export async function recalculate(symbol: string, range: DateRange, minKlineGap: number): Promise<void> {
  const response = await fetch(`${API_BASE}/api/stocks/${encodeURIComponent(symbol)}/chan/recalculate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...range, minKlineGap }),
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
