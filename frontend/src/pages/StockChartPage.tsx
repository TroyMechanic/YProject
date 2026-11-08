import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, RefreshCw, Search } from 'lucide-react';
import { fetchChart, fetchRules, recalculate, syncStock } from '../api/chartApi';
import type { DateRange } from '../api/chartApi';
import { KLineChart } from '../components/KLineChart';
import type { ChartResponse, KlinePeriod, RuleCatalog, RuleProfile } from '../types/chart';
import { adjacentPeriod, wheelLogicalRange } from '../utils/wheelNavigation';
import type { WheelFocus, ZoomDirection } from '../utils/wheelNavigation';
import type { PeriodViewport } from '../utils/wheelNavigation';


const defaultSymbol = '000001.SH';
const periodOptions: Array<{ value: KlinePeriod; label: string }> = [
  { value: 'minute1', label: '1m' },
  { value: 'minute5', label: '5m' },
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
  const [ruleProfile, setRuleProfile] = useState<RuleProfile>('legacy');
  const [catalog, setCatalog] = useState<RuleCatalog | null>(null);
  const requestId = useRef(0);
  const [chartData, setChartData] = useState<ChartResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState('');
  const [wheelHistory, setWheelHistory] = useState<KlinePeriod[]>([]);
  const [wheelFocus, setWheelFocus] = useState<WheelFocus>();
  const [periodViewport, setPeriodViewport] = useState<PeriodViewport>();
  const readViewport = useRef<(() => WheelFocus | null) | null>(null);
  const [wheelTarget, setWheelTarget] = useState<KlinePeriod | null>(null);
  const wheelPending = useRef(false);
  const skipPeriodLoad = useRef(false);

  const range = useMemo(
    () => ({
      startDate: startDate || undefined,
      endDate: endDate || undefined,
      period,
    }),
    [startDate, endDate, period],
  );

  useEffect(() => {
    if (skipPeriodLoad.current) { skipPeriodLoad.current = false; return; }
    void loadChart();
  }, [period]);

  useEffect(() => {
    void fetchRules().then(setCatalog).catch(() => setMessage('规则目录加载失败，请检查后端后刷新。'));
    return () => { requestId.current += 1; };
  }, []);

  function applyChart(data: ChartResponse) {
    setChartData(data);
    const actual = data.analysis;
    if (actual) {
      setRuleProfile(actual.settings.ruleProfile);
      setMinKlineGap(actual.settings.minKlineGap);
    }
  }

  function exportView() {
    if (!chartData) return;
    const blob = new Blob([JSON.stringify({ viewRange: range, wheelFocus, periodViewport, chart: chartData }, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${chartData.symbol}_${chartData.period}_${chartData.analysis?.runId ?? 'view'}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }

  async function loadChart(nextSymbol = symbol) {
    const id = ++requestId.current;
    setLoading(true);
    setMessage('');
    try {
      const data = await fetchChart(nextSymbol, range);
      if (id !== requestId.current) return;
      applyChart(data);
      setWheelHistory([]);
      setWheelFocus(undefined);
      setPeriodViewport(undefined);
      if (data.klines.length === 0) {
        setMessage('本地还没有这只股票的数据，先同步一次。');
      }
    } catch (error) {
      if (id !== requestId.current) return;
      setMessage(error instanceof Error ? error.message : '加载失败');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  async function navigateWheel(direction: ZoomDirection, focus: WheelFocus): Promise<boolean> {
    if (!chartData || loading || wheelPending.current) return false;
    const previous = wheelHistory[wheelHistory.length - 1];
    const target = adjacentPeriod(chartData.period, direction, previous);
    if (!target) {
      setMessage(direction === 'in' ? '已到最细的1m周期，继续滚动只放大K线。' : '已到最大的月K周期。');
      return false;
    }
    const id = ++requestId.current;
    wheelPending.current = true;
    setWheelTarget(target);
    setLoading(true);
    setMessage('');
    const query: DateRange = { period: target };
    try {
      const data = await fetchChart(chartData.symbol, query);
      if (id !== requestId.current) return false;
      const targetTimes = data.klines.map((bar) => bar.time.slice(0, 19));
      if (!wheelLogicalRange(targetTimes, data.klines, target, focus)) {
        setMessage(`${periodLabel(target)}在当前查看位置 ${focus.anchor.replace('T', ' ')} 没有对应本地行情，已保留${periodLabel(chartData.period)}原图。` +
          (data.klines.length ? `可用范围：${data.klines[0].time} 至 ${data.klines[data.klines.length - 1].time}。` : '本地尚无该周期行情。') + '可同步行情后重试；历史行情未必能补回。');
        return false;
      }
      setWheelHistory((items) => direction === 'in' ? [...items, chartData.period] : items.slice(0, -1));
      setWheelFocus(focus);
      setPeriodViewport(undefined);
      skipPeriodLoad.current = target !== period;
      setPeriod(target);
      setSymbol(chartData.symbol);
      setStartDate('');
      setEndDate('');
      applyChart(data);
      setMessage(`已切换到${periodLabel(target)}，保留所指时间 ${focus.anchor.replace('T', ' ')}。`);
      return true;
    } catch (error) {
      if (id === requestId.current) setMessage(`周期切换失败，已保留原图：${error instanceof Error ? error.message : '加载失败'}`);
      return false;
    } finally {
      wheelPending.current = false;
      if (id === requestId.current) { setLoading(false); setWheelTarget(null); }
    }
  }

  async function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await loadChart();
  }

  async function handleSync() {
    const id = ++requestId.current;
    setLoading(true);
    setMessage('');
    try {
      await syncStock(symbol, range, ruleProfile, minKlineGap);
      const data = await fetchChart(symbol, range);
      if (id !== requestId.current) return;
      applyChart(data);
      setMessage(
        `同步完成：${data.klines.length} 根K线，${data.fractals.length} 个分型，${data.bis.length} 笔，${data.segments.length} 段。`,
      );
    } catch (error) {
      if (id !== requestId.current) return;
      setMessage(error instanceof Error ? error.message : '同步失败');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  async function handleRecalculate() {
    const id = ++requestId.current;
    setLoading(true);
    setMessage('');
    try {
      await recalculate(symbol, range, minKlineGap, ruleProfile);
      const data = await fetchChart(symbol, range);
      if (id !== requestId.current) return;
      applyChart(data);
      setMessage(
        `重算完成：${data.fractals.length} 个分型，${data.bis.length} 笔，${data.segments.length} 段。`,
      );
    } catch (error) {
      if (id !== requestId.current) return;
      setMessage(error instanceof Error ? error.message : '重算失败');
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  async function handlePeriodChange(nextPeriod: KlinePeriod) {
    if (loading) return;
    const anchor = readViewport.current?.() ?? undefined;
    const nextSymbol = chartData?.symbol ?? symbol;
    const query: DateRange = { period: nextPeriod };
    const id = ++requestId.current;
    setWheelTarget(nextPeriod);
    setLoading(true);
    setMessage('');
    try {
      const data = await fetchChart(nextSymbol, query);
      if (id !== requestId.current) return;
      if (!data.klines.length) {
        setMessage(`${periodLabel(nextPeriod)}暂无本地行情，已保留原图。请同步该周期行情后重试。`);
        return;
      }
      const covered = anchor && wheelLogicalRange(data.klines.map((bar) => bar.time.slice(0, 19)), data.klines, nextPeriod, anchor);
      setPeriodViewport({ anchor: covered ? anchor : undefined });
      setWheelFocus(undefined);
      setWheelHistory([]);
      skipPeriodLoad.current = nextPeriod !== period;
      setPeriod(nextPeriod);
      setSymbol(nextSymbol);
      setStartDate('');
      setEndDate('');
      applyChart(data);
      setMessage(covered ? `已切换到${periodLabel(nextPeriod)}，图表缩放已适配，保留查看位置 ${anchor!.anchor.replace('T', ' ')}。`
        : `${anchor ? `原查看位置 ${anchor.anchor.replace('T', ' ')} 无对应${periodLabel(nextPeriod)}行情；` : ''}已按${periodLabel(nextPeriod)}适配缩放，定位到最新本地行情 ${data.klines[data.klines.length - 1].time.replace('T', ' ')}。`);
    } catch (error) {
      if (id === requestId.current) setMessage(`周期切换失败，已保留原图：${error instanceof Error ? error.message : '加载失败'}`);
    } finally {
      if (id === requestId.current) { setLoading(false); setWheelTarget(null); }
    }
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
          <div className="stock-shortcuts" role="group" aria-label="常用股票">
            {[{ code: '002475.SZ', name: '立讯精密' }, { code: '002156.SZ', name: '通富微电' }, { code: '000001.SH', name: '上证指数' }].map((stock) => (
              <button key={stock.code} type="button" disabled={loading}
                aria-pressed={chartData?.symbol === stock.code}
                onClick={() => { setSymbol(stock.code); void loadChart(stock.code); }}>
                {stock.name} {stock.code.slice(0, 6)}
              </button>
            ))}
          </div>
        </div>

        <form className="control-grid" onSubmit={handleSearch}>
          <label>
            <span>股票代码</span>
            <input disabled={loading} value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="002475 / 600519 / AAPL" />
          </label>
          <label>
            <span>开始日期</span>
            <input disabled={loading} type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
          </label>
          <label>
            <span>结束日期</span>
            <input disabled={loading} type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
          </label>
          <label>
            <span>标准K线最小间隔</span>
            <input
              type="number"
              disabled={loading}
              min="1"
              max="20"
              value={minKlineGap}
              onChange={(event) => setMinKlineGap(Number(event.target.value))}
            />
          </label>
          <label>
            <span>缠论规则方案</span>
            <select disabled={loading || !catalog} value={ruleProfile} onChange={(event) => setRuleProfile(event.target.value as RuleProfile)}>
              {(catalog?.profiles ?? []).map((item) => <option key={item.id} value={item.id}>{item.label}{item.id === catalog?.recommendedProfile ? '（推荐）' : ''}</option>)}
            </select>
          </label>
          <div className="period-control" aria-label="K线展示周期">
            {periodOptions.map((item) => (
              <button
                key={item.value}
                type="button"
                disabled={loading}
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
            <span>同步行情</span>
          </button>
          <button type="button" className="icon-button" disabled={loading} onClick={handleRecalculate} title="重新计算分型、笔、线段">
            <Activity size={18} />
            <span>重算</span>
          </button>
        </form>
      </section>

      <section className="rule-panel">
        {chartData?.analysis?.sourceEnd && <p>本地展示行情最后时间：{chartData.analysis.sourceEnd}。查询和重算不会获取新行情，获取最新数据请点击同步。</p>}
        <p>待应用：{catalog?.profiles.find((item) => item.id === ruleProfile)?.label ?? ruleProfile}，中心间隔至少 {Math.max(minKlineGap, catalog?.profiles.find((item) => item.id === ruleProfile)?.minimumCenterGap ?? 1)}。点击同步或重算应用；查询读取已保存方案。</p>
        {chartData?.analysis && <>
          <p>当前图表：规则 v{chartData.analysis.ruleVersion} · {chartData.analysis.ruleCatalog.profiles.find((item) => item.id === chartData.analysis?.settings.ruleProfile)?.label} · 输入间隔 {chartData.analysis.settings.minKlineGap} / 生效间隔 {chartData.analysis.effectiveMinKlineGap} · 全量 {chartData.analysis.sourceCount} 根K线</p>
          <details>
            <summary>查看缠论原则与计算溯源</summary>
            <p>计算时间：{new Date(chartData.analysis.generatedAt).toLocaleString()}<br />历史范围：{chartData.analysis.sourceStart ?? '无'} 至 {chartData.analysis.sourceEnd ?? '无'}</p>
            <dl className="trace-fields">
              <dt>计算批次</dt><dd>{chartData.analysis.runId}</dd>
              <dt>行情指纹</dt><dd>{chartData.analysis.inputHash}</dd>
              <dt>规则指纹</dt><dd>{chartData.analysis.ruleHash}</dd>
              <dt>代码指纹</dt><dd>{chartData.analysis.engineHash}</dd>
              <dt>全量结果指纹</dt><dd>{chartData.analysis.resultHash}</dd>
            </dl>
            <ul>{chartData.analysis.ruleCatalog.principles.map((item) => <li key={item.id}><strong>{item.id}</strong>：{item.text}</li>)}</ul>
            <button type="button" className="icon-button" onClick={exportView}>导出当前视图 JSON</button>
            <p>导出包含当前视图和溯源信息。结果指纹对应全量快照；完整历史快照保存在后端 runs 目录。</p>
          </details>
        </>}
      </section>

      <section className="chart-band" aria-busy={loading}>
        {message && <div className="status-line" role="status" aria-live="polite">{message}</div>}
        <div className="chart-status" role="status" aria-live="polite">
          <strong>{loading ? `正在加载 ${periodLabel(wheelTarget ?? period)} K线…` : chartData ? `${stockTitle(chartData, symbol)} · ${periodLabel(chartData.period)} K线` : '尚未加载图表'}</strong>
          {!loading && chartData && <span>{chartData.klines.length} 根K线 · {chartData.klines[0]?.time ?? '无数据'} 至 {chartData.klines[chartData.klines.length - 1]?.time ?? '无数据'}</span>}
        </div>
        <div className={loading ? 'chart-content is-loading' : 'chart-content'} inert={loading}>
        {chartData && chartData.klines.length > 0 ? (
          <KLineChart data={chartData} wheelFocus={wheelFocus} periodViewport={periodViewport} readViewport={readViewport} wheelCanReturn={wheelHistory.length > 0}
            onWheelNavigate={navigateWheel} />
        ) : (
          <div className="empty-state">{loading ? "正在加载行情…" : message || "当前标的在所选区间暂无 K 线数据。"}</div>
        )}
        </div>
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
                    <td>{item.confirmed ? '终点已确认' : '终点待定'}</td>
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
                    <td>{item.confirmed ? '终点已确认' : '终点待定'}</td>
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

function formatDisplayTime(value: string): string {
  return value.includes('T') ? value.slice(0, 16).replace('T', ' ') : value;
}

