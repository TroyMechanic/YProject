import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Activity, RefreshCw, Search } from 'lucide-react';
import { fetchChart, recalculate, syncStock } from '../api/chartApi';
import { KLineChart } from '../components/KLineChart';
import type { ChartResponse, KlinePeriod } from '../types/chart';

const defaultSymbol = '002475.SZ';
const periodOptions: Array<{ value: KlinePeriod; label: string }> = [
  { value: 'minute1', label: '1m' },
  { value: 'minute30', label: '30m' },
  { value: 'minute60', label: '60m' },
  { value: 'hour4', label: '4H' },
  { value: 'daily', label: '日K' },
  { value: 'weekly', label: '周K' },
  { value: 'monthly', label: '月K' },
];

export function StockChartPage() {
  const [symbol, setSymbol] = useState(defaultSymbol);
  const [startDate, setStartDate] = useState('2023-01-01');
  const [endDate, setEndDate] = useState('');
  const [period, setPeriod] = useState<KlinePeriod>('daily');
  const [minKlineGap, setMinKlineGap] = useState(1);
  const [chartData, setChartData] = useState<ChartResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const range = useMemo(
    () => ({
      startDate: startDate || undefined,
      endDate: endDate || undefined,
      period,
    }),
    [startDate, endDate, period],
  );

  useEffect(() => {
    void loadChart();
  }, [period]);

  async function loadChart(nextSymbol = symbol) {
    setLoading(true);
    setMessage('');
    try {
      const data = await fetchChart(nextSymbol, range);
      setChartData(data);
      if (data.klines.length === 0) {
        setMessage('本地还没有这只股票的数据，先同步一次。');
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await loadChart();
  }

  async function handleSync() {
    setLoading(true);
    setMessage('');
    try {
      await syncStock(symbol, range);
      const data = await fetchChart(symbol, range);
      setChartData(data);
      setMessage(
        `同步完成：${data.klines.length} 根K线，${data.fractals.length} 个分型，${data.bis.length} 笔，${data.segments.length} 段，${data.centralZones.length} 个中枢。`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '同步失败');
    } finally {
      setLoading(false);
    }
  }

  async function handleRecalculate() {
    setLoading(true);
    setMessage('');
    try {
      await recalculate(symbol, range, minKlineGap);
      const data = await fetchChart(symbol, range);
      setChartData(data);
      setMessage(
        `重算完成：${data.fractals.length} 个分型，${data.bis.length} 笔，${data.segments.length} 段，${data.centralZones.length} 个中枢。`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '重算失败');
    } finally {
      setLoading(false);
    }
  }

  function handlePeriodChange(nextPeriod: KlinePeriod) {
    if (isIntradayPeriod(nextPeriod)) {
      const nextStartDate = daysAgo(nextPeriod === 'hour4' ? 119 : 9);
      setStartDate(nextStartDate);
      setEndDate('');
      setPeriod(nextPeriod);
      return;
    }
    if (isIntradayPeriod(period)) {
      setStartDate('2023-01-01');
      setEndDate('');
    }
    setPeriod(nextPeriod);
  }

  return (
    <main className="app-shell">
      <section className="toolbar-band">
        <div className="title-block">
          <div className="product-mark">
            <Activity size={22} />
            <span>Chan Stock</span>
          </div>
          <h1>{stockTitle(chartData, symbol)} {periodLabel(chartData?.period ?? period)}缠论分析</h1>
        </div>

        <form className="control-grid" onSubmit={handleSearch}>
          <label>
            <span>股票代码</span>
            <input value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="DEMO / AAPL / 000001.SZ" />
          </label>
          <label>
            <span>开始日期</span>
            <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </label>
          <label>
            <span>结束日期</span>
            <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </label>
          <label>
            <span>标准K线最小间隔</span>
            <input
              type="number"
              min="1"
              max="20"
              value={minKlineGap}
              onChange={(event) => setMinKlineGap(Number(event.target.value))}
            />
          </label>
          <div className="period-control" aria-label="K线周期">
            {periodOptions.map((item) => (
              <button
                key={item.value}
                type="button"
                className={period === item.value ? 'active' : ''}
                onClick={() => handlePeriodChange(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <button type="submit" className="icon-button" disabled={loading} title="查询本地数据">
            <Search size={18} />
            <span>查询</span>
          </button>
          <button type="button" className="icon-button primary" disabled={loading} onClick={handleSync} title="同步行情数据">
            <RefreshCw size={18} />
            <span>同步</span>
          </button>
          <button type="button" className="icon-button" disabled={loading} onClick={handleRecalculate} title="重新计算分型、笔、线段和中枢">
            <Activity size={18} />
            <span>重算</span>
          </button>
        </form>
      </section>

      {message && <div className="status-line">{message}</div>}

      <section className="chart-band">
        {chartData && chartData.klines.length > 0 ? (
          <KLineChart data={chartData} />
        ) : (
          <div className="empty-state">暂无K线数据</div>
        )}
      </section>

      <section className="summary-band">
        <div className="metric">
          <span>K线</span>
          <strong>{chartData?.klines.length ?? 0}</strong>
        </div>
        <div className="metric">
          <span>顶底分型</span>
          <strong>{chartData?.fractals.length ?? 0}</strong>
        </div>
        <div className="metric">
          <span>笔</span>
          <strong>{chartData?.bis.length ?? 0}</strong>
        </div>
        <div className="metric">
          <span>线段</span>
          <strong>{chartData?.segments.length ?? 0}</strong>
        </div>
        <div className="metric">
          <span>中枢</span>
          <strong>{chartData?.centralZones.length ?? 0}</strong>
        </div>
      </section>

      {chartData && (
        <section className="tables-band">
          <div>
            <h2>分型</h2>
            <table>
              <thead>
                <tr>
                  <th>日期</th>
                  <th>类型</th>
                  <th>价格</th>
                  <th>序号</th>
                </tr>
              </thead>
              <tbody>
                {chartData.fractals.slice(-12).map((item) => (
                  <tr key={`${item.time}-${item.type}-${item.klineIndex}`}>
                    <td>{formatDisplayTime(item.time)}</td>
                    <td>{item.type === 'TOP' ? '顶' : '底'}</td>
                    <td>{item.price.toFixed(2)}</td>
                    <td>{item.klineIndex}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h2>笔</h2>
            <table>
              <thead>
                <tr>
                  <th>起点</th>
                  <th>终点</th>
                  <th>方向</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {chartData.bis.slice(-12).map((item) => (
                  <tr key={`${item.startTime}-${item.endTime}-${item.direction}`}>
                    <td>{formatDisplayTime(item.startTime)}</td>
                    <td>{formatDisplayTime(item.endTime)}</td>
                    <td>{item.direction === 'UP' ? '上' : '下'}</td>
                    <td>{item.confirmed ? '确认' : '未确认'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h2>线段</h2>
            <table>
              <thead>
                <tr>
                  <th>起点</th>
                  <th>终点</th>
                  <th>方向</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {chartData.segments.slice(-12).map((item) => (
                  <tr key={`${item.startTime}-${item.endTime}-${item.direction}`}>
                    <td>{formatDisplayTime(item.startTime)}</td>
                    <td>{formatDisplayTime(item.endTime)}</td>
                    <td>{item.direction === 'UP' ? '上' : '下'}</td>
                    <td>{item.confirmed ? '确认' : '未确认'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div>
            <h2>中枢</h2>
            <table>
              <thead>
                <tr>
                  <th>起点</th>
                  <th>ZD / ZG</th>
                  <th>线段数</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {chartData.centralZones.slice(-12).map((item) => (
                  <tr key={`${item.startTime}-${item.endTime}-${item.startSegmentIndex}`}>
                    <td>{formatDisplayTime(item.startTime)}</td>
                    <td>{item.zd.toFixed(2)} / {item.zg.toFixed(2)}</td>
                    <td>{item.segmentCount}</td>
                    <td>{formatCentralZoneStatus(item.status)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </main>
  );
}

function periodLabel(period: KlinePeriod): string {
  return periodOptions.find((item) => item.value === period)?.label ?? '日K';
}

function stockTitle(chartData: ChartResponse | null, symbol: string): string {
  if (!chartData) {
    return symbol.toUpperCase();
  }
  return chartData.name ? `${chartData.name} ${chartData.symbol}` : chartData.symbol;
}

function isIntradayPeriod(period: KlinePeriod): boolean {
  return ['hour4', 'minute60', 'minute30', 'minute1'].includes(period);
}

function daysAgo(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() - days);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, '0');
  const day = String(value.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function formatDisplayTime(value: string): string {
  return value.includes('T') ? value.slice(0, 16).replace('T', ' ') : value;
}

function formatCentralZoneStatus(status: 'EXTENDING' | 'LEFT_UP' | 'LEFT_DOWN'): string {
  if (status === 'LEFT_UP') {
    return '向上离开';
  }
  if (status === 'LEFT_DOWN') {
    return '向下离开';
  }
  return '延伸中';
}
