import { FormEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Activity, RefreshCw, Search } from 'lucide-react';
import { fetchChart, fetchRules, recalculate, syncStock } from '../api/chartApi';
import type { DateRange } from '../api/chartApi';
import { HierarchyPanel } from '../components/HierarchyPanel';
import { KLineChart } from '../components/KLineChart';
import type { ChartResponse, KlinePeriod, ResearchOptions, RuleCatalog, RuleProfile } from '../types/chart';
import { divergenceLabel, pointLabel, pointSource, strengthLabel, trendLabel } from '../utils/analysisLabels';
import type { AnalysisWindow } from '../utils/rangeNavigation';
import { adjacentPeriod, wheelLogicalRange } from '../utils/wheelNavigation';
import type { WheelFocus, ZoomDirection } from '../utils/wheelNavigation';
import type { PeriodViewport } from '../utils/wheelNavigation';

interface RangeVisit { symbol: string; query: DateRange; focus?: AnalysisWindow; expectedDays: string[]; wheelFocus?: WheelFocus; wheel?: boolean }

const defaultSymbol = '002475.SZ';
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
  const [mode, setMode] = useState<'recursive' | 'legacy'>('recursive');
  const [basePeriod, setBasePeriod] = useState<KlinePeriod>('minute5');
  const [maxLevel, setMaxLevel] = useState(4);
  const [layerFilter, setLayerFilter] = useState('all');
  const [showBiObservations, setShowBiObservations] = useState(true);
  const [period, setPeriod] = useState<KlinePeriod>('daily');
  const [minKlineGap, setMinKlineGap] = useState(1);
  const [ruleProfile, setRuleProfile] = useState<RuleProfile>('legacy');
  const [catalog, setCatalog] = useState<RuleCatalog | null>(null);
  const [research, setResearch] = useState<ResearchOptions>({ signalLevel: 'bi', divergenceRatio: 0.8, zeroAxisTolerance: 0.01, macdFast: 12, macdSlow: 26, macdSignal: 9 });
  const requestId = useRef(0);
  const [chartData, setChartData] = useState<ChartResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [visits, setVisits] = useState<RangeVisit[]>([]);
  const [focusWindow, setFocusWindow] = useState<AnalysisWindow>();
  const [wheelFocus, setWheelFocus] = useState<WheelFocus>();
  const [periodViewport, setPeriodViewport] = useState<PeriodViewport>();
  const readViewport = useRef<(() => WheelFocus | null) | null>(null);
  const [wheelTarget, setWheelTarget] = useState<KlinePeriod | null>(null);
  const wheelPending = useRef(false);
  const skipPeriodLoad = useRef(false);
  const loadedQuery = useRef<DateRange>({ period: 'daily', startDate: '2023-01-01', mode: 'recursive' });

  const range = useMemo(
    () => ({
      startDate: startDate || undefined,
      endDate: endDate || undefined,
      period, mode, basePeriod, maxLevel,
    }),
    [startDate, endDate, period, mode, basePeriod, maxLevel],
  );

  useEffect(() => {
    if (skipPeriodLoad.current) { skipPeriodLoad.current = false; return; }
    void loadChart();
  }, [period, mode]);

  useEffect(() => {
    void fetchRules().then(setCatalog).catch(() => setMessage('规则目录加载失败，请检查后端后刷新。'));
    return () => { requestId.current += 1; };
  }, []);

  function applyChart(data: ChartResponse) {
    setChartData(data);
    if (data.hierarchy) { setBasePeriod(data.hierarchy.basePeriod); setMaxLevel(data.hierarchy.maxLevel); }
    const actual = data.hierarchy?.baseAnalysis ?? data.analysis;
    if (actual) {
      setRuleProfile(actual.settings.ruleProfile);
      setMinKlineGap(actual.settings.minKlineGap);
      const { signalLevel, divergenceRatio, zeroAxisTolerance, macdFast, macdSlow, macdSignal } = actual.settings;
      setResearch({ signalLevel, divergenceRatio, zeroAxisTolerance, macdFast, macdSlow, macdSignal });
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
      loadedQuery.current = range;
      setVisits([]);
      setFocusWindow(undefined);
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

  async function navigateRange(nextPeriod: KlinePeriod, window: AnalysisWindow, viewport: AnalysisWindow | null, back?: RangeVisit) {
    if (!chartData) return;
    const id = ++requestId.current;
    const nextSymbol = back?.symbol ?? chartData.symbol;
    const nextQuery: DateRange = back?.query ?? {
      period: nextPeriod, startDate: window.start, endDate: window.end, mode,
      basePeriod: chartData.hierarchy?.basePeriod, maxLevel: chartData.hierarchy?.maxLevel,
      preserveHierarchy: true,
    };
    setLoading(true);
    setMessage('');
    try {
      const data = await fetchChart(nextSymbol, nextQuery);
      if (id !== requestId.current) return;
      const previous: RangeVisit = { symbol: chartData.symbol, query: {
        ...loadedQuery.current, basePeriod: chartData.hierarchy?.basePeriod,
        maxLevel: chartData.hierarchy?.maxLevel, preserveHierarchy: true,
      }, focus: viewport ?? focusWindow, wheelFocus, expectedDays: [...new Set(chartData.klines
        .map((bar) => bar.time.slice(0, 10)).filter((day) => day >= window.start && day <= window.end))] };
      setVisits((items) => back ? items.slice(0, -1) : [...items, previous]);
      setFocusWindow(back ? back.focus : window);
      setWheelFocus(back?.wheelFocus);
      setPeriodViewport(undefined);
      loadedQuery.current = nextQuery;
      skipPeriodLoad.current = nextQuery.period !== period;
      setPeriod(nextQuery.period);
      setStartDate(nextQuery.startDate ?? '');
      setEndDate(nextQuery.endDate ?? '');
      setSymbol(nextSymbol);
      applyChart(data);
      if (!data.klines.length) setMessage('所选区间没有该周期的本地行情。区间已保留，可尝试同步，或返回上一层；行情源未必提供这段历史。');
    } catch (error) {
      if (id === requestId.current) setMessage(`区间切换失败，已保留原图：${error instanceof Error ? error.message : '加载失败'}`);
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }

  async function navigateWheel(direction: ZoomDirection, focus: WheelFocus): Promise<boolean> {
    if (!chartData || loading || wheelPending.current) return false;
    const previous = visits[visits.length - 1];
    const returning = direction === 'out' && previous?.wheel;
    const target = adjacentPeriod(chartData.period, direction, returning ? previous.query.period : undefined);
    if (!target) {
      setMessage(direction === 'in' ? '已到最细的1m周期，继续滚动只放大K线。' : '已到最大的月K周期。');
      return false;
    }
    const id = ++requestId.current;
    wheelPending.current = true;
    setWheelTarget(target);
    setLoading(true);
    setMessage('');
    const query: DateRange = { period: target, mode, preserveHierarchy: true,
      basePeriod: chartData.hierarchy?.basePeriod, maxLevel: chartData.hierarchy?.maxLevel };
    try {
      // Load the full stored display history so subsequent panning/zoom-out is
      // not trapped inside the date window from the initial drill-down.
      const data = await fetchChart(chartData.symbol, query);
      if (id !== requestId.current) return false;
      const targetTimes = data.klines.map((bar) => bar.time.slice(0, 19));
      if (!wheelLogicalRange(targetTimes, data.klines, target, focus)) {
        setMessage(`${periodLabel(target)}在当前查看位置 ${focus.anchor.replace('T', ' ')} 没有对应本地行情，已保留${periodLabel(chartData.period)}原图。` +
          (data.klines.length ? `可用范围：${data.klines[0].time} 至 ${data.klines[data.klines.length - 1].time}。` : '本地尚无该周期行情。') + '可同步行情后重试；历史行情未必能补回。');
        return false;
      }
      const oldDays = [...new Set(chartData.klines.map((bar) => bar.time.slice(0, 10)))]
        .filter((day) => day >= focus.start.slice(0, 10) && day <= focus.end.slice(0, 10));
      const targetDays = new Set(data.klines.map((bar) => bar.time.slice(0, 10)));
      const missingDays = oldDays.filter((day) => !targetDays.has(day)).length;
      setVisits((items) => direction === 'in' ? [...items, {
        symbol: chartData.symbol, query: { ...loadedQuery.current, preserveHierarchy: true,
          basePeriod: chartData.hierarchy?.basePeriod, maxLevel: chartData.hierarchy?.maxLevel },
        focus: focusWindow, wheelFocus: focus, wheel: true, expectedDays: oldDays,
      }] : returning ? items.slice(0, -1) : []);
      setWheelFocus(focus);
      setPeriodViewport(undefined);
      setFocusWindow(undefined);
      loadedQuery.current = query;
      skipPeriodLoad.current = target !== period;
      setPeriod(target);
      setSymbol(chartData.symbol);
      setStartDate('');
      setEndDate('');
      applyChart(data);
      setMessage(`已切换到${periodLabel(target)}，保留所指时间 ${focus.anchor.replace('T', ' ')}。` +
        (missingDays ? `选区有 ${missingDays} 个父图日期在目标周期缺少行情，当前仅展示可用部分。` : ''));
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
      await syncStock(symbol, range, ruleProfile, minKlineGap, research);
      const data = await fetchChart(symbol, range);
      if (id !== requestId.current) return;
      applyChart(data);
      loadedQuery.current = range;
      setMessage(
        `同步完成：${data.klines.length} 根K线，${data.fractals.length} 个分型，${data.bis.length} 笔，${data.segments.length} 段，${data.centralZones.length} 个中枢。`,
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
      await recalculate(symbol, range, minKlineGap, ruleProfile, research);
      const data = await fetchChart(symbol, range);
      if (id !== requestId.current) return;
      applyChart(data);
      loadedQuery.current = range;
      setMessage(
        `重算完成：${data.fractals.length} 个分型，${data.bis.length} 笔，${data.segments.length} 段，${data.centralZones.length} 个中枢。`,
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
    const query: DateRange = { period: nextPeriod, mode, preserveHierarchy: true,
      basePeriod: chartData?.hierarchy?.basePeriod, maxLevel: chartData?.hierarchy?.maxLevel };
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
      setFocusWindow(undefined);
      setVisits([]);
      loadedQuery.current = query;
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

  const combinedPoints = useMemo(() => chartData ? [...chartData.tradingPoints,
    ...(showBiObservations ? chartData.hierarchy?.baseTradingPoints ?? [] : [])] : [], [chartData, showBiObservations]);
  const visiblePoints = useMemo(() => combinedPoints.filter((point) => layerFilter === 'all' ||
    (layerFilter === 'bi' ? point.structuralLevel == null && point.level === 'bi' : point.structuralLevel === Number(layerFilter)))
    .sort((a,b) => a.observedAt.localeCompare(b.observedAt)), [combinedPoints, layerFilter]);
  const renderedChart = useMemo(() => chartData ? { ...chartData, tradingPoints: visiblePoints } : null, [chartData, visiblePoints]);
  const displayedTimes = new Set(chartData?.klines.map((bar) => bar.time));
  const unmappedPoints = visiblePoints.filter((point) => !displayedTimes.has(point.displayTime ?? point.observedAt)).length;
  const displayedDays = new Set(chartData?.klines.map((bar) => bar.time.slice(0, 10)));
  const parentVisit = visits[visits.length - 1];
  const missingParentDays = parentVisit && !['weekly', 'monthly'].includes(parentVisit.query.period)
    ? parentVisit.expectedDays.filter((day) => !displayedDays.has(day)).length : 0;

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
            {[{ code: '002475.SZ', name: '立讯精密' }, { code: '002156.SZ', name: '通富微电' }].map((stock) => (
              <button key={stock.code} type="button" disabled={loading}
                aria-pressed={chartData?.symbol === stock.code}
                onClick={() => { setSymbol(stock.code); setLayerFilter('all'); void loadChart(stock.code); }}>
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
          <label><span>分析方式</span><select value={mode} disabled={loading} onChange={(e) => { setLayerFilter('all'); setMode(e.target.value as 'recursive' | 'legacy'); }}><option value="recursive">结构递归</option><option value="legacy">原单周期模型对照</option></select></label>
          {mode === 'recursive' && <>
            <label><span>基础数据周期</span><select value={basePeriod} disabled={loading} onChange={(e) => setBasePeriod(e.target.value as KlinePeriod)}><option value="minute1">1m</option><option value="minute5">5m</option><option value="minute30">30m</option><option value="minute60">60m</option></select></label>
            <label><span>最大结构层</span><input type="number" min={1} max={8} value={maxLevel} onChange={(e) => setMaxLevel(Number(e.target.value))} /></label>
          </>}
          <label>
            <span>单周期对照单位</span>
            <select disabled={loading || mode === 'recursive'} value={research.signalLevel} onChange={(event) => setResearch({ ...research, signalLevel: event.target.value as ResearchOptions['signalLevel'] })}>
              <option value="bi">笔级</option><option value="segment">线段级</option>
            </select>
          </label>
          <label>
            <span>背驰面积比阈值</span>
            <input disabled={loading} type="number" min="0.1" max="0.99" step="0.05" value={research.divergenceRatio} onChange={(event) => setResearch({ ...research, divergenceRatio: Number(event.target.value) })} />
          </label>
          <details className="advanced-rules">
            <summary>MACD 与零轴参数</summary>
            <div className="advanced-rule-fields">
              {(['macdFast', 'macdSlow', 'macdSignal', 'zeroAxisTolerance'] as const).map((key) => <label key={key}>
                <span>{{ macdFast: '快线周期', macdSlow: '慢线周期', macdSignal: '信号线周期', zeroAxisTolerance: '零轴容差 / 价格' }[key]}</span>
                <input disabled={loading} type="number" step={key === 'zeroAxisTolerance' ? 0.001 : 1} value={research[key]} onChange={(event) => setResearch({ ...research, [key]: Number(event.target.value) })} />
              </label>)}
            </div>
          </details>
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
            <span>{mode === 'recursive' ? '同步基础与展示行情' : '同步'}</span>
          </button>
          <button type="button" className="icon-button" disabled={loading} onClick={handleRecalculate} title="重新计算分型、笔、线段和中枢">
            <Activity size={18} />
            <span>重算</span>
          </button>
        </form>
      </section>

      <section className="rule-panel">
        {chartData?.hierarchy && <p>展示 {periodLabel(chartData.period)}；计算基础 {periodLabel(chartData.hierarchy.basePeriod)}。切换K线展示周期只改变展示；要改用1m计算，请修改“基础数据周期”后同步或重算。</p>}
        {chartData?.analysis?.sourceEnd && <p>本地展示行情最后时间：{chartData.analysis.sourceEnd}。查询和重算不会获取新行情，获取最新数据请点击同步。</p>}
        {chartData && chartData.klines.length === 0 && <p className="hierarchy-warning">所选日期内没有本地展示行情，无法绘制买卖点；请核对日期或同步行情，这不表示该股票没有买卖点。</p>}
        {unmappedPoints > 0 && <p className="hierarchy-warning">按确认时间显示时，当前所选图层有 {unmappedPoints} 个点不在已加载K线的覆盖范围内，图上无法绘制；明细保留原时间。请核对展示行情与基础行情的日期范围。</p>}
        <p>待应用：{catalog?.profiles.find((item) => item.id === ruleProfile)?.label ?? ruleProfile}，中心间隔至少 {Math.max(minKlineGap, catalog?.profiles.find((item) => item.id === ruleProfile)?.minimumCenterGap ?? 1)}。点击同步或重算应用；查询读取已保存方案。</p>
        <p>递归分析从基础周期线段种子逐层构造走势和中枢；图表周期仅用于展示。候选可变化，观察时间才是当时可知时间。单周期模型保留作对照。</p>
        {chartData?.analysis && <>
          <p>当前图表：规则 v{chartData.analysis.ruleVersion} · {chartData.analysis.ruleCatalog.profiles.find((item) => item.id === chartData.analysis?.settings.ruleProfile)?.label} · 输入间隔 {chartData.analysis.settings.minKlineGap} / 生效间隔 {chartData.analysis.effectiveMinKlineGap} · 全量 {chartData.analysis.sourceCount} 根K线</p>
          {chartData.hierarchy ? <><p>当前买卖点：结构递归 · 来源 {periodLabel(chartData.hierarchy.basePeriod)} · L0线段种子 → L1/L2… · 实际生成 {chartData.hierarchy.layers.length} 层</p><p>基础行情 {chartData.hierarchy.baseAnalysis.sourceCount} 根 · {chartData.hierarchy.baseAnalysis.sourceStart} 至 {chartData.hierarchy.baseAnalysis.sourceEnd} · 来源参数 {chartData.hierarchy.baseAnalysis.settings.ruleProfile} / 间隔 {chartData.hierarchy.baseAnalysis.effectiveMinKlineGap}</p>{chartData.hierarchy.warnings.map((w) => <p className="hierarchy-warning" key={w}>{w}</p>)}</> : <p>当前买卖点：{chartData.analysis.settings.signalLevel === 'bi' ? '笔级近似' : '线段级近似'} · 面积比 ≤ {chartData.analysis.settings.divergenceRatio} · MACD {chartData.analysis.settings.macdFast}/{chartData.analysis.settings.macdSlow}/{chartData.analysis.settings.macdSignal}</p>}
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
        {visits.length > 0 && <div className="range-history" aria-label="区间分析路径">
          <span>{[...visits.map((visit) => periodLabel(visit.query.period)), periodLabel(chartData?.period ?? period)].join(' → ')}</span>
          <button type="button" disabled={loading} onClick={() => {
            const previous = visits[visits.length - 1];
            void navigateRange(previous.query.period, focusWindow ?? { start: startDate, end: endDate }, null, previous);
          }}>返回上一层</button>
          <p>{wheelFocus ? `滚轮定位区间：${wheelFocus.start.replace('T', ' ')} 至 ${wheelFocus.end.replace('T', ' ')}；已加载本地历史，可拖动或缩小查看。` : `当前请求区间：${loadedQuery.current.startDate ?? '最早行情'} 至 ${loadedQuery.current.endDate ?? '最新本地行情'}。下方只查看所选区间；可继续下钻。`} 分析使用完整本地历史。</p>
          {missingParentDays > 0 && <p className="hierarchy-warning">父图选区中有 {missingParentDays} 个交易日在当前周期没有本地K线，当前图不能覆盖完整选区。可尝试同步行情或返回上一层。</p>}
        </div>}
        <div className="chart-status" role="status" aria-live="polite">
          <strong>{loading ? `正在加载 ${periodLabel(wheelTarget ?? period)} K线与MACD…` : chartData ? `${stockTitle(chartData, symbol)} · ${periodLabel(chartData.period)} K线 / MACD` : '尚未加载图表'}</strong>
          {!loading && chartData && <span>{chartData.klines.length} 根K线 · {chartData.klines[0]?.time ?? '无数据'} 至 {chartData.klines[chartData.klines.length - 1]?.time ?? '无数据'}</span>}
          {chartData?.hierarchy && <span>买卖点计算来源：{periodLabel(chartData.hierarchy.basePeriod)}；标记中的周期表示计算来源。</span>}
        </div>
        <div className={loading ? 'chart-content is-loading' : 'chart-content'} inert={loading}>
        {renderedChart && renderedChart.klines.length > 0 ? (
          <KLineChart data={renderedChart} focusWindow={focusWindow} wheelFocus={wheelFocus} periodViewport={periodViewport} readViewport={readViewport} wheelCanReturn={!!visits[visits.length - 1]?.wheel}
            onWheelNavigate={navigateWheel} onDrillDown={(target, window, viewport) => void navigateRange(target, window, viewport)} />
        ) : (
          <div className="empty-state">暂无K线数据</div>
        )}
        </div>
      </section>

      <section className="summary-band">
        <div className="metric"><span>展示周期背景 / {chartData?.trend.level === 'segment' ? '线段级' : '笔级'}</span><strong>{trendLabel(chartData?.trend.type ?? 'INSUFFICIENT')}</strong></div>
        <div className="metric"><span>所选图层买卖点 / 确认 · 候选</span><strong>{visiblePoints.filter((p) => p.confirmed).length} · {visiblePoints.filter((p) => !p.confirmed).length}</strong></div>
        <div className="metric"><span>背驰 / 动能衰减</span><strong>{chartData?.divergences.length ?? 0}</strong></div>
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

      {chartData?.hierarchy && <><HierarchyPanel data={chartData.hierarchy} />
        <label className="layer-select"><input type="checkbox" checked={showBiObservations} onChange={(e) => { setShowBiObservations(e.target.checked); setLayerFilter('all'); }} />显示笔级观察点（独立于L0/L1确认）</label>
        <label className="layer-select">显示买卖点层级 <select aria-label="显示买卖点层级" value={layerFilter} onChange={(e) => setLayerFilter(e.target.value)}><option value="all">全部已生成层及已开启观察点</option>{showBiObservations && <option value="bi">笔级观察</option>}{chartData.hierarchy.layers.map((layer) => <option key={layer.level} value={String(layer.level)}>L{layer.level}</option>)}</select></label></>}
      {chartData && (
        <section className="research-tables">
          <h2>买卖点与确认依据</h2>
          <p>买卖点发生在结构端点，确认依赖后续结构。确认时间才是当时可获知的时间；失效参考价不是自动交易指令。</p>
          {visiblePoints.length === 0 ? <p>当前所选图层没有满足条件的买卖点。笔级观察点与L0/L1递归点分别计算、独立标注，不把笔级点升级为高层确认。</p> : <table><thead><tr><th>类型</th><th>结构端点</th><th>确认 / 观察时间</th><th>价格</th><th>状态</th><th>失效参考</th><th>依据</th></tr></thead><tbody>
            {visiblePoints.slice(-30).reverse().map((point) => <tr key={point.id}>
              <td className={point.side === 'BUY' ? 'buy-text' : 'sell-text'}>{pointLabel(point.type)}<br />{pointSource(point)}</td><td>{formatDisplayTime(point.time)}</td><td>{formatDisplayTime(point.observedAt)}</td><td>{point.price.toFixed(2)}</td><td>{point.confirmed ? '模型确认' : '候选'}</td><td>{point.invalidationPrice.toFixed(2)}</td>
              <td><details><summary>查看</summary><ul>{point.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul><p>来源中枢：{point.zoneIds.join('、')}<br />依赖点：{point.parentId ?? '无'}</p></details></td>
            </tr>)}
          </tbody></table>}
          <details><summary>背驰与中枢关系明细</summary>
            <h3>背驰 / 动能衰减</h3><table><thead><tr><th>端点</th><th>类型</th><th>方向</th><th>面积比</th><th>状态</th><th>依据</th></tr></thead><tbody>{chartData.divergences.slice(-20).reverse().map((item) => <tr key={item.id}><td>{formatDisplayTime(item.time)}</td><td>{divergenceLabel(item.type)}</td><td>{item.direction === 'UP' ? '顶' : '底'}</td><td>{item.ratio.toFixed(3)}</td><td>{item.confirmed ? '模型确认' : '候选'}</td><td>{item.reasons.join('；')}</td></tr>)}</tbody></table>
            <h3>信号中枢 / {chartData.trend.level === 'bi' ? '笔级' : '线段级'}</h3><table><thead><tr><th>形成时间</th><th>核心</th><th>包络</th><th>成员</th><th>状态</th></tr></thead><tbody>{chartData.signalZones.slice(-12).map((zone) => <tr key={zone.id}><td>{formatDisplayTime(zone.formedAt)}</td><td>{zone.zd.toFixed(2)} / {zone.zg.toFixed(2)}</td><td>{zone.dd.toFixed(2)} / {zone.gg.toFixed(2)}</td><td>{zone.memberIndices.map((i) => i + 1).join('、')}</td><td>{formatCentralZoneStatus(zone.status)}</td></tr>)}</tbody></table>
            <ul>{chartData.zoneRelations.slice(-12).map((item) => <li key={item.currentZoneId}>{trendLabel(item.type)}：{item.reasons.join('；')}</li>)}</ul>
          </details>
        </section>
      )}

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
                  <th>强弱</th>
                </tr>
              </thead>
              <tbody>
                {chartData.fractals.slice(-12).map((item) => (
                  <tr key={`${item.time}-${item.type}-${item.klineIndex}`}>
                    <td>{formatDisplayTime(item.time)}</td>
                    <td>{item.type === 'TOP' ? '顶' : '底'}</td>
                    <td>{item.price.toFixed(2)}</td>
                    <td>{item.klineIndex}</td>
                    <td>{strengthLabel(item.strength?.grade ?? 'UNAVAILABLE')}</td>
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
                  <th>动能</th>
                </tr>
              </thead>
              <tbody>
                {chartData.bis.slice(-12).map((item) => (
                  <tr key={`${item.startTime}-${item.endTime}-${item.direction}`}>
                    <td>{formatDisplayTime(item.startTime)}</td>
                    <td>{formatDisplayTime(item.endTime)}</td>
                    <td>{item.direction === 'UP' ? '上' : '下'}</td>
                    <td>{item.confirmed ? '确认' : '未确认'}</td>
                    <td>{strengthLabel(item.momentum?.grade ?? 'UNAVAILABLE')}</td>
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
