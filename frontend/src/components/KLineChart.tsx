import { useEffect, useMemo, useRef, useState } from 'react';
import type { MutableRefObject } from 'react';
import {
  CandlestickData,
  ColorType,
  createChart,
  LineData,
  Time,
  SeriesMarker,
  WhitespaceData,
} from 'lightweight-charts';
import type { Bi, CentralZone, ChartResponse, Fractal, KlinePeriod, Momentum, Segment, SignalZone, TradingPoint } from '../types/chart';
import { pointLabel, pointSource, strengthLabel } from '../utils/analysisLabels';
import { buildTimeline, visibleCandleRange } from '../utils/chartTimeline';
import { analysisWindow, candleWindow, smallerPeriods } from '../utils/rangeNavigation';
import type { AnalysisWindow } from '../utils/rangeNavigation';
import { makeWheelFocus, wheelLogicalRange, ZOOM_IN_SPACING, ZOOM_OUT_SPACING, RETURN_EXPANSION } from '../utils/wheelNavigation';
import type { WheelFocus, ZoomDirection } from '../utils/wheelNavigation';
import { periodButtonRange } from '../utils/wheelNavigation';
import type { PeriodViewport } from '../utils/wheelNavigation';

interface Props {
  data: ChartResponse;
  focusWindow?: AnalysisWindow;
  onDrillDown?: (period: KlinePeriod, window: AnalysisWindow, viewport: AnalysisWindow | null) => void;
  wheelFocus?: WheelFocus;
  wheelCanReturn?: boolean;
  onWheelNavigate?: (direction: ZoomDirection, focus: WheelFocus) => Promise<boolean>;
  periodViewport?: PeriodViewport;
  readViewport?: MutableRefObject<(() => WheelFocus | null) | null>;
}

interface HoverKline {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  change: number | null;
  changePercent: number | null;
  amplitude: number | null;
}

interface CentralZoneRect {
  zone: CentralZone;
  index: number;
  left: number;
  top: number;
  width: number;
  height: number;
  signalZone?: SignalZone;
}

type SelectedExplanation =
  | { kind: 'fractal'; item: Fractal }
  | { kind: 'bi'; item: Bi }
  | { kind: 'segment'; item: Segment }
  | { kind: 'centralZone'; item: CentralZone }
  | { kind: 'tradingPoint'; item: TradingPoint[] }
  | { kind: 'signalZone'; item: SignalZone }
  | null;

export function KLineChart({ data, focusWindow, onDrillDown, wheelFocus, wheelCanReturn, onWheelNavigate, periodViewport, readViewport }: Props) {
  const shellRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const macdRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const [hoverKline, setHoverKline] = useState<HoverKline | null>(null);
  const [selected, setSelected] = useState<SelectedExplanation>(null);
  const [centralZoneRects, setCentralZoneRects] = useState<CentralZoneRect[]>([]);
  const [showBis, setShowBis] = useState(true);
  const [showSegments, setShowSegments] = useState(true);
  const [showCentralZones, setShowCentralZones] = useState(false);
  const [showSignalZones, setShowSignalZones] = useState(true);
  const [showSignals, setShowSignals] = useState(true);
  const [showCandidates, setShowCandidates] = useState(true);
  const [showFractals, setShowFractals] = useState(false);
  const [signalPlacement, setSignalPlacement] = useState<'observed' | 'endpoint'>('observed');
  const [rangeSelection, setRangeSelection] = useState<AnalysisWindow | null>(null);
  const [picking, setPicking] = useState(false);
  const pickRef = useRef<{ active: boolean; anchor: string | null }>({ active: false, anchor: null });
  const targets = smallerPeriods(data.period);
  const [targetPeriod, setTargetPeriod] = useState<KlinePeriod>(targets[0]?.value ?? 'minute1');
  const [autoPeriod, setAutoPeriod] = useState(true);
  const wheelOptions = useRef({ onWheelNavigate, wheelCanReturn, autoPeriod });
  wheelOptions.current = { onWheelNavigate, wheelCanReturn, autoPeriod };
  const wheelState = useRef({ busy: false, lastEvent: 0, switched: false, blocked: '' });
  useEffect(() => {
    if (periodViewport) wheelState.current = { busy: false, lastEvent: 0, switched: false, blocked: '' };
  }, [periodViewport]);

  useEffect(() => {
    setRangeSelection(null);
    setPicking(false);
    pickRef.current = { active: false, anchor: null };
    setTargetPeriod(smallerPeriods(data.period)[0]?.value ?? 'minute1');
    wheelState.current.blocked = '';
  }, [data.symbol, data.period, data.klines]);

  function currentWindow(): AnalysisWindow | null {
    const visible = chartRef.current?.timeScale().getVisibleRange();
    return visible ? candleWindow(data.klines.map((bar) => bar.time), formatChartTime(visible.from), formatChartTime(visible.to), data.period) : null;
  }

  function chooseWindow(window: AnalysisWindow | null) {
    pickRef.current = { active: false, anchor: null };
    setPicking(false);
    setRangeSelection(window);
  }

  const klineByTime = useMemo(() => {
    const result = new Map<string, HoverKline>();
    data.klines.forEach((item, index) => {
      const prevClose = index > 0 ? data.klines[index - 1].close : null;
      const changeValue = prevClose === null ? null : item.close - prevClose;
      const changePercent = prevClose === null || prevClose === 0 ? null : ((item.close - prevClose) / prevClose) * 100;
      const amplitude = prevClose === null || prevClose === 0 ? null : ((item.high - item.low) / prevClose) * 100;
      result.set(chartTimeKey(item.time), {
        time: item.time,
        open: item.open,
        high: item.high,
        low: item.low,
        close: item.close,
        volume: item.volume,
        change: changeValue,
        changePercent,
        amplitude,
      });
    });
    return result;
  }, [data.klines]);

  const fractalByTime = useMemo(() => {
    const result = new Map<string, Fractal>();
    data.fractals.forEach((item) => result.set(chartTimeKey(item.time), item));
    return result;
  }, [data.fractals]);

  useEffect(() => {
    if (!containerRef.current) return;
    setSelected(null);
    setHoverKline(null);
    const timeline = buildTimeline(data.klines, data.indicators, [
      ...(showBis ? data.bis.flatMap((bi) => [bi.startTime, bi.endTime]) : []),
      ...(showSegments ? data.segments.flatMap((segment) => [segment.startTime, segment.endTime]) : []),
    ]);
    const timelineIndices = new Map(timeline.map((time, index) => [time, index]));

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: 560,
      layout: {
        background: { type: ColorType.Solid, color: '#f8fafc' },
        textColor: '#1f2937',
        fontFamily: 'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif',
      },
      grid: {
        vertLines: { color: '#e5e7eb' },
        horzLines: { color: '#e5e7eb' },
      },
      rightPriceScale: {
        borderColor: '#cbd5e1',
        minimumWidth: 96,
      },
      timeScale: {
        borderColor: '#cbd5e1',
        timeVisible: isIntradayData(data),
        secondsVisible: false,
      },
      crosshair: {
        mode: 1,
      },
    });
    chartRef.current = chart;

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#dc2626',
      downColor: '#0f766e',
      borderUpColor: '#dc2626',
      borderDownColor: '#0f766e',
      wickUpColor: '#dc2626',
      wickDownColor: '#0f766e',
    });
    const candlesByTime = new Map(data.klines.map((item) => [chartTimeKey(item.time), item]));
    const candleData: Array<CandlestickData | WhitespaceData> = timeline.map((time) => {
      const item = candlesByTime.get(time);
      return item ? { time: toChartTime(time), open: item.open, high: item.high, low: item.low, close: item.close }
        : { time: toChartTime(time) };
    });
    candleSeries.setData(candleData);
    const markers: SeriesMarker<Time>[] = showFractals ? data.fractals.map((item) => ({
        time: toChartTime(item.time),
        position: item.type === 'TOP' ? 'aboveBar' : 'belowBar',
        color: item.type === 'TOP' ? '#b91c1c' : '#047857',
        shape: 'circle',
        text: item.type === 'TOP' ? '顶' : '底',
      })) : [];
    const visibleSignals = showSignals ? data.tradingPoints.filter((point) => showCandidates || point.confirmed) : [];
    const signalsByTime = new Map<string, TradingPoint[]>();
    visibleSignals.forEach((point) => {
      const time = signalPlacement === 'endpoint' ? (point.displayEndpointTime ?? point.time) : (point.displayTime ?? point.observedAt);
      if (!klineByTime.has(chartTimeKey(time))) return;
      const key = chartTimeKey(time);
      signalsByTime.set(key, [...(signalsByTime.get(key) ?? []), point]);
      markers.push({ time: toChartTime(time), id: point.id, position: point.side === 'BUY' ? 'belowBar' : 'aboveBar',
        shape: point.side === 'BUY' ? 'arrowUp' : 'arrowDown', color: point.confirmed ? point.side === 'BUY' ? '#dc2626' : '#047857' : '#b45309',
        size: 2, text: `${pointLabel(point.type)}${point.confirmed ? '' : '?'}·${pointSource(point)}` });
    });
    const barOrder = new Map(data.klines.map((bar, index) => [chartTimeKey(bar.time), index]));
    markers.sort((a, b) => (barOrder.get(formatChartTime(a.time)) ?? 0) - (barOrder.get(formatChartTime(b.time)) ?? 0));
    candleSeries.setMarkers(markers);

    const macdChart = macdRef.current ? createChart(macdRef.current, {
      width: containerRef.current.clientWidth, height: 170,
      layout: { background: { type: ColorType.Solid, color: '#f8fafc' }, textColor: '#475569' },
      timeScale: { timeVisible: isIntradayData(data) },
      rightPriceScale: { minimumWidth: 96 },
    }) : null;
    if (macdChart) {
      const indicatorsByTime = new Map(data.indicators.map((item) => [chartTimeKey(item.time), item]));
      const histogram = macdChart.addHistogramSeries({ priceLineVisible: false, lastValueVisible: false });
      histogram.setData(timeline.map((time) => {
        const point = indicatorsByTime.get(time);
        return point ? { time: toChartTime(time), value: point.histogram, color: point.histogram >= 0 ? '#dc2626' : '#047857' }
          : { time: toChartTime(time) };
      }));
      const dif = macdChart.addLineSeries({ color: '#2563eb', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      const dea = macdChart.addLineSeries({ color: '#d97706', lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
      dif.setData(timeline.map((time) => {
        const point = indicatorsByTime.get(time);
        return point ? { time: toChartTime(time), value: point.dif } : { time: toChartTime(time) };
      }));
      dea.setData(timeline.map((time) => {
        const point = indicatorsByTime.get(time);
        return point ? { time: toChartTime(time), value: point.dea } : { time: toChartTime(time) };
      }));
    }

    if (showBis) {
      data.bis.forEach((bi) => {
        const line = chart.addLineSeries({
          color: bi.direction === 'UP' ? '#2563eb' : '#ea580c',
          lineWidth: bi.confirmed ? 2 : 1,
          lineStyle: bi.confirmed ? 0 : 2,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        line.setData(toBiLineData(bi));
      });
    }

    if (showSegments) {
      data.segments.forEach((segment) => {
        const line = chart.addLineSeries({
          color: segment.direction === 'UP' ? '#be123c' : '#047857',
          lineWidth: segment.confirmed ? 4 : 3,
          lineStyle: segment.confirmed ? 0 : 2,
          pointMarkersVisible: true,
          pointMarkersRadius: 4,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        line.setData(toSegmentLineData(segment));
      });
    }

    const updateCentralZoneRects = () => {
      if (!showCentralZones && !showSignalZones) {
        setCentralZoneRects([]);
        return;
      }
      setCentralZoneRects(
        [...(showCentralZones ? data.centralZones : []).flatMap((zone, index) => {
          const bounds = centralZoneBounds(
            zone,
            chart,
            candleSeries,
            data.klines[0]?.time,
            data.klines[data.klines.length - 1]?.time,
          );
          return bounds ? [{ zone, index, ...bounds }] : [];
        }), ...(showSignalZones ? data.signalZones : []).flatMap((signalZone, index) => {
          const zone = displaySignalZone(signalZone);
          const bounds = centralZoneBounds(zone, chart, candleSeries, data.klines[0]?.time, data.klines[data.klines.length - 1]?.time);
          return bounds ? [{ zone, index, signalZone, ...bounds }] : [];
        })],
      );
    };

    chart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.point || param.point.x < 0 || param.point.y < 0) {
        setHoverKline(null);
        return;
      }
      setHoverKline(klineByTime.get(formatChartTime(param.time)) ?? null);
    });

    chart.subscribeClick((param) => {
      if (!param.time || !param.point) {
        return;
      }
      if (pickRef.current.active) {
        return;
      }
      const clickedSignal = visibleSignals.find((point) => point.id === param.hoveredObjectId);
      const sameTimeSignals = signalsByTime.get(formatChartTime(param.time));
      if (clickedSignal) {
        setSelected({ kind: 'tradingPoint', item: [clickedSignal] });
        return;
      }
      const clickedCentralZone = showCentralZones
        ? findCentralZone(
            data.centralZones,
            param.point,
            chart,
            candleSeries,
            data.klines[0]?.time,
            data.klines[data.klines.length - 1]?.time,
          )
        : null;
      if (clickedCentralZone) {
        setSelected({ kind: 'centralZone', item: clickedCentralZone });
        return;
      }
      const clickedSegment = showSegments
        ? findNearestLine(data.segments, param.point, chart, candleSeries, 12)
        : null;
      if (clickedSegment) {
        setSelected({ kind: 'segment', item: clickedSegment });
        return;
      }

      const clickedBi = showBis
        ? findNearestLine(data.bis, param.point, chart, candleSeries, 8)
        : null;
      if (clickedBi) {
        setSelected({ kind: 'bi', item: clickedBi });
        return;
      }

      if (sameTimeSignals?.length) {
        setSelected({ kind: 'tradingPoint', item: sameTimeSignals });
        return;
      }

      const clickedFractal = fractalByTime.get(formatChartTime(param.time));
      if (clickedFractal) {
        setSelected({ kind: 'fractal', item: clickedFractal });
      }
    });

    const baseBars = data.hierarchy?.baseKlines;
    const focus = focusWindow ?? (data.period === 'daily' && baseBars?.length ? {
      start: baseBars[0].time.slice(0, 10), end: baseBars[baseBars.length - 1].time.slice(0, 10),
    } : undefined);
    const initialCandleRange = periodViewport ? periodButtonRange(timeline, data.klines, data.period, chart.timeScale().width(), periodViewport)
      : wheelFocus ? wheelLogicalRange(timeline, data.klines, data.period, wheelFocus)
      : visibleCandleRange(timeline, data.klines, focus, !focusWindow);
    if (initialCandleRange) chart.timeScale().setVisibleLogicalRange(initialCandleRange);
    else chart.timeScale().fitContent();
    if (readViewport) readViewport.current = () => {
      const scale = chart.timeScale();
      const visible = scale.getVisibleRange();
      const logical = scale.getVisibleLogicalRange();
      if (!visible || !logical || !data.klines.length) return null;
      const center = (logical.from + logical.to) / 2;
      const anchor = data.klines.reduce((best, bar) => Math.abs(timelineIndices.get(chartTimeKey(bar.time))! - center)
        < Math.abs(timelineIndices.get(chartTimeKey(best.time))! - center) ? bar : best);
      return makeWheelFocus(data.klines.map((bar) => bar.time), data.period,
        formatChartTime(visible.from), formatChartTime(visible.to), anchor.time, 0.5);
    };
    let syncingRange = false;
    const syncToMacd = (range: { from: number; to: number } | null) => {
      if (!range || !macdChart || syncingRange) return;
      syncingRange = true;
      macdChart.timeScale().setVisibleLogicalRange(range);
      syncingRange = false;
    };
    const syncToMain = (range: { from: number; to: number } | null) => {
      if (!range || syncingRange) return;
      syncingRange = true;
      chart.timeScale().setVisibleLogicalRange(range);
      syncingRange = false;
    };
    const initialRange = chart.timeScale().getVisibleLogicalRange();
    if (initialRange) syncToMacd(initialRange);
    chart.timeScale().subscribeVisibleLogicalRangeChange(syncToMacd);
    macdChart?.timeScale().subscribeVisibleLogicalRangeChange(syncToMain);
    chart.timeScale().subscribeVisibleLogicalRangeChange(updateCentralZoneRects);
    requestAnimationFrame(updateCentralZoneRects);
    const initialZoneRenderTimer = window.setTimeout(updateCentralZoneRects, 100);
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
        macdChart?.applyOptions({ width: containerRef.current.clientWidth });
        requestAnimationFrame(updateCentralZoneRects);
      }
    };
    window.addEventListener('resize', handleResize);

    const initialCount = initialCandleRange ? initialCandleRange.to - initialCandleRange.from + 1 : 0;
    const wheelSurface = shellRef.current;
    const handleWheel = (event: WheelEvent) => {
      if (!event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY) || pickRef.current.active) return;
      if ((event.target as Element).closest('button, input, select, .explanation-panel, .chart-layer-controls')) return;
      const surface = [containerRef.current, macdRef.current].find((element) => {
        const bounds = element?.getBoundingClientRect();
        return bounds && event.clientY >= bounds.top && event.clientY < bounds.bottom;
      });
      if (!surface) return;
      const scale = chart.timeScale();
      const x = event.clientX - surface.getBoundingClientRect().left;
      if (x < 0 || x >= scale.width()) return; // Keep price-axis gestures independent.
      event.preventDefault();
      event.stopPropagation();
      const state = wheelState.current;
      const now = performance.now();
      if (now - state.lastEvent > 300) state.switched = false;
      state.lastEvent = now;
      if (state.busy || state.switched) return;
      const before = scale.getVisibleLogicalRange();
      const logicalAnchor = scale.coordinateToLogical(x);
      if (!before || logicalAnchor === null) return;
      const ratio = (x + 1) / scale.width();
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? surface.clientHeight : 1);
      const count = Math.max(1, (before.to - before.from + 1) * Math.exp(Math.max(-120, Math.min(120, delta)) * 0.002));
      const from = logicalAnchor + 0.5 - ratio * count;
      scale.setVisibleLogicalRange({ from, to: from + count - 1 });
      const options = wheelOptions.current;
      if (!options.autoPeriod || !options.onWheelNavigate) return;
      const direction: ZoomDirection = delta < 0 ? 'in' : 'out';
      const spacing = scale.width() / count;
      const crossing = direction === 'in' ? spacing >= ZOOM_IN_SPACING
        : spacing <= ZOOM_OUT_SPACING || (options.wheelCanReturn && initialCount > 0 && count >= initialCount * RETURN_EXPANSION);
      if (!crossing) return;
      const visible = scale.getVisibleRange();
      if (!visible) return;
      const nearest = data.klines.reduce((best, bar) => Math.abs(timelineIndices.get(chartTimeKey(bar.time))! - logicalAnchor)
        < Math.abs(timelineIndices.get(chartTimeKey(best.time))! - logicalAnchor) ? bar : best);
      // A structure-only timestamp or blank margin is not a candle to drill into.
      if (Math.abs(timelineIndices.get(chartTimeKey(nearest.time))! - logicalAnchor) > 0.5) return;
      const nextFocus = makeWheelFocus(data.klines.map((bar) => bar.time), data.period,
        formatChartTime(visible.from), formatChartTime(visible.to), nearest.time, ratio);
      if (!nextFocus) return;
      const key = `${direction}:${nearest.time.slice(0, 10)}`;
      if (state.blocked === key) return;
      state.busy = true;
      state.switched = true;
      void options.onWheelNavigate(direction, nextFocus).then((changed) => {
        if (!changed) state.blocked = key;
      }).finally(() => { state.busy = false; });
    };
    wheelSurface?.addEventListener('wheel', handleWheel, { passive: false, capture: true });

    return () => {
      window.clearTimeout(initialZoneRenderTimer);
      window.removeEventListener('resize', handleResize);
      wheelSurface?.removeEventListener('wheel', handleWheel, true);
      if (readViewport) readViewport.current = null;
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(updateCentralZoneRects);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(syncToMacd);
      macdChart?.timeScale().unsubscribeVisibleLogicalRangeChange(syncToMain);
      macdChart?.remove();
      chartRef.current = null;
      chart.remove();
    };
  }, [data, focusWindow, wheelFocus, periodViewport, readViewport, fractalByTime, klineByTime, showBis, showCentralZones, showSignalZones, showSegments, showSignals, showCandidates, showFractals, signalPlacement]);

  return (
    <>
      {onDrillDown && <section className="range-navigation" aria-label="区间下钻">
        <strong>区间下钻</strong>
        <label><input type="checkbox" checked={autoPeriod} onChange={(event) => setAutoPeriod(event.target.checked)} />滚轮自动切换周期</label>
        <p>滚轮放大到阈值进入更细周期，缩小返回；围绕鼠标所指时间。A股自动切换跳过4h，可用下方选项手动选择。</p>
        {targets.length ? <>
          <button type="button" aria-pressed={picking} onClick={() => {
            pickRef.current = { active: !picking, anchor: null };
            setPicking(!picking);
            if (!picking) { setRangeSelection(null); setSelected(null); }
          }}>{picking ? '取消选取' : '在图上选起止'}</button>
          <button type="button" onClick={() => chooseWindow(currentWindow())}>使用当前可见区间</button>
          {selected && (selected.kind === 'bi' || selected.kind === 'segment' || selected.kind === 'centralZone' || selected.kind === 'signalZone') &&
            <button type="button" onClick={() => chooseWindow(analysisWindow(selected.item.startTime, selected.item.endTime, data.period))}>使用选中{selected.kind === 'bi' ? '笔' : selected.kind === 'segment' ? '线段' : '中枢'}区间</button>}
          <label>目标周期 <select aria-label="下钻目标周期" value={targetPeriod} onChange={(event) => setTargetPeriod(event.target.value as KlinePeriod)}>
            {targets.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select></label>
          <button type="button" className="primary" disabled={!rangeSelection || picking} onClick={() => rangeSelection && onDrillDown(targetPeriod, rangeSelection, currentWindow())}>下钻分析</button>
          <p role="status">{picking ? (rangeSelection ? '已选起点，请再点一根K线作为终点。' : '依次点击两根K线，确定起止日期（可反向选取）。') : rangeSelection ? `已选 ${rangeSelection.start} 至 ${rangeSelection.end}` : '点击一笔／线段后可使用其区间，也可选择当前可见范围。'} 按起止交易日期查看，包含两端整日。</p>
          {targetPeriod === 'hour4' && <p>A股 4h 通常一天一根；查看日内细节可选 60m 或 30m。</p>}
        </> : <p>已到最小支持周期 1m，可返回上一级对照。</p>}
      </section>}
    <div ref={shellRef} className={`chart-shell${picking ? ' is-picking-range' : ''}`}>
      {hoverKline && <KlineHoverPanel item={hoverKline} />}
      {selected && <ExplanationPanel selected={selected} onClose={() => setSelected(null)} />}
      <div className="chart-layer-controls">
        <label><input type="checkbox" checked={showSignals} onChange={(event) => setShowSignals(event.target.checked)} /><span>买卖点</span></label>
        <label><input type="checkbox" checked={showCandidates} onChange={(event) => setShowCandidates(event.target.checked)} /><span>候选点</span></label>
        <label><input type="checkbox" checked={showFractals} onChange={(event) => setShowFractals(event.target.checked)} /><span>分型</span></label>
        <label><input type="checkbox" checked={showSignalZones} onChange={(event) => setShowSignalZones(event.target.checked)} /><span>信号中枢</span></label>
        <select aria-label="买卖点显示位置" value={signalPlacement} onChange={(event) => setSignalPlacement(event.target.value as 'observed' | 'endpoint')}><option value="observed">确认时间</option><option value="endpoint">结构端点（事后）</option></select>
        <label>
          <input type="checkbox" checked={showBis} onChange={(event) => setShowBis(event.target.checked)} />
          <span>笔</span>
        </label>
        <label>
          <input type="checkbox" checked={showSegments} onChange={(event) => setShowSegments(event.target.checked)} />
          <span>线段</span>
        </label>
        <label>
          <input
            type="checkbox"
            checked={showCentralZones}
            onChange={(event) => setShowCentralZones(event.target.checked)}
          />
          <span>线段中枢</span>
        </label>
      </div>
      <div className="chart-surface" ref={containerRef} />
      {picking && <div className="range-pick-surface" title="点击K线选择起止日期" onClick={(event) => {
        const chart = chartRef.current;
        const bounds = containerRef.current?.getBoundingClientRect();
        if (!chart || !bounds) return;
        const time = chart.timeScale().coordinateToTime(event.clientX - bounds.left);
        const bar = time ? klineByTime.get(formatChartTime(time)) : null;
        if (!bar) return;
        const first = pickRef.current.anchor;
        setRangeSelection(analysisWindow(first ?? bar.time, bar.time, data.period));
        if (first) {
          pickRef.current = { active: false, anchor: null };
          setPicking(false);
        } else pickRef.current.anchor = bar.time;
      }} />}
      <div className="central-zone-layer">
        {centralZoneRects.map(({ zone, signalZone, index, left, top, width, height }) => (
          <div
            key={`${signalZone?.id ?? 'segment'}-${zone.startTime}-${zone.endTime}-${zone.startSegmentIndex}`}
            className={`central-zone-box ${signalZone ? 'signal-zone-box' : ''} ${zone.status === 'EXTENDING' ? 'extending' : 'left'}`}
            style={{ left, top, width, height }}
            onClick={() => setSelected(signalZone ? { kind: 'signalZone', item: signalZone } : { kind: 'centralZone', item: zone })}
            onMouseMove={(event) => {
              const chart = chartRef.current;
              const chartRect = containerRef.current?.getBoundingClientRect();
              if (!chart || !chartRect) {
                return;
              }
              const time = chart.timeScale().coordinateToTime(event.clientX - chartRect.left);
              setHoverKline(time ? klineByTime.get(formatChartTime(time)) ?? null : null);
            }}
            onMouseLeave={() => setHoverKline(null)}
          >
            <button
              type="button"
              className="central-zone-label"
              aria-label={`查看中枢 ${index + 1} 判定`}
            >
              {signalZone ? signalZone.level === 'bi' ? '笔级' : '线段级' : '线段'}中枢 {index + 1} ZG {formatPrice(zone.zg)} / ZD {formatPrice(zone.zd)}
            </button>
          </div>
        ))}
      </div>
      <div className="macd-legend">MACD · DIF 蓝线 / DEA 橙线 / 柱面积用于同向动能比较；不足预热长度不判断背驰</div>
      <div className="macd-surface" ref={macdRef} />
    </div>
    </>
  );
}

function toBiLineData(bi: Bi): LineData[] {
  return [
    { time: toChartTime(bi.startTime), value: bi.startPrice },
    { time: toChartTime(bi.endTime), value: bi.endPrice },
  ];
}

function toSegmentLineData(segment: Segment): LineData[] {
  return [
    { time: toChartTime(segment.startTime), value: segment.startPrice },
    { time: toChartTime(segment.endTime), value: segment.endPrice },
  ];
}

function KlineHoverPanel({ item }: { item: HoverKline }) {
  const isUp = item.change !== null && item.change >= 0;
  const changeClass = isUp ? 'up' : 'down';
  return (
    <div className="kline-hover-panel">
      <span className="hover-date">{formatDisplayTime(item.time)}</span>
      <span>开 {formatPrice(item.open)}</span>
      <span>高 {formatPrice(item.high)}</span>
      <span>低 {formatPrice(item.low)}</span>
      <span>收 {formatPrice(item.close)}</span>
      <span className={changeClass}>涨跌 {formatSigned(item.change)}</span>
      <span className={changeClass}>涨跌幅 {formatPercent(item.changePercent)}</span>
      <span>振幅 {formatPercent(item.amplitude)}</span>
      <span>量 {formatVolume(item.volume)}</span>
    </div>
  );
}

function ExplanationPanel({ selected, onClose }: { selected: Exclude<SelectedExplanation, null>; onClose: () => void }) {
  if (selected.kind === 'tradingPoint') {
    return <div className="explanation-panel"><button type="button" className="explanation-close" onClick={onClose} aria-label="关闭说明">×</button>
      {selected.item.map((point) => <section key={point.id}><h3>{pointLabel(point.type)} · {pointSource(point)} · {point.confirmed ? '模型确认' : '候选'}</h3>
        <p>端点：{formatDisplayTime(point.time)} / {formatPrice(point.price)}<br />确认 / 观察：{formatDisplayTime(point.observedAt)}<br />失效参考价：{formatPrice(point.invalidationPrice)}</p>
        <ReasonList reasons={point.reasons} /><p>中枢：{point.zoneIds.join('、')}<br />依赖：{point.parentId ?? point.divergenceId ?? '离开与回试结构'}</p></section>)}
    </div>;
  }
  if (selected.kind === 'signalZone') {
    const zone = selected.item;
    return <div className="explanation-panel"><button type="button" className="explanation-close" onClick={onClose} aria-label="关闭说明">×</button><h3>{zone.level === 'bi' ? '笔级' : '线段级'}信号中枢</h3>
      <p>核心：{formatPrice(zone.zd)} / {formatPrice(zone.zg)}<br />包络：{formatPrice(zone.dd)} / {formatPrice(zone.gg)}<br />形成可知时间：{formatDisplayTime(zone.formedAt)}<br />关闭可知时间：{zone.closedAt ? formatDisplayTime(zone.closedAt) : '延伸中'}<br />成员序号：{zone.memberIndices.map((i) => i + 1).join('、')}</p><p>连续至少三个已确认同层单元的严格交集；核心固定，确认外侧回试后关闭并剔除离开连接单元。买卖点引用此ID：{zone.id}</p>
    </div>;
  }
  if (selected.kind === 'centralZone') {
    const item = selected.item;
    return (
      <div className="explanation-panel central-zone-explanation-panel">
        <button type="button" className="explanation-close" onClick={onClose} aria-label="关闭说明">
          ×
        </button>
        <h3>线段级中枢判定</h3>
        <div className="explanation-meta">
          <span>{formatDisplayTime(item.startTime)} 至 {formatDisplayTime(item.endTime)}</span>
          <span>{item.segmentCount} 段</span>
          <span>{formatCentralZoneStatus(item.status)}</span>
        </div>
        <div className="explanation-meta">
          <span>ZD {formatPrice(item.zd)}</span>
          <span>ZG {formatPrice(item.zg)}</span>
          <span>DD {formatPrice(item.dd)}</span>
          <span>GG {formatPrice(item.gg)}</span>
        </div>
        <div className="explanation-meta">
          <span>组成线段 {formatSegmentIndices(item.sourceSegmentIndices)}</span>
        </div>
        <ReasonList reasons={item.reasons} />
      </div>
    );
  }

  if (selected.kind === 'fractal') {
    const item = selected.item;
    return (
      <div className="explanation-panel">
        <button type="button" className="explanation-close" onClick={onClose} aria-label="关闭说明">
          ×
        </button>
        <h3>{item.type === 'TOP' ? '顶分型' : '底分型'}判定</h3>
        <div className="explanation-meta">
          <span>{formatDisplayTime(item.time)}</span>
          <span>价格 {formatPrice(item.price)}</span>
          <span>序号 {item.klineIndex}</span>
        </div>
        <div className="explanation-meta">
          <span>三元素最高 {formatOptionalPrice(item.elementHigh)}</span>
          <span>三元素最低 {formatOptionalPrice(item.elementLow)}</span>
        </div>
        {item.elements.length > 0 && (
          <table className="fractal-elements-table">
            <thead>
              <tr>
                <th>位置</th>
                <th>标准K线日期</th>
                <th>原始K线来源</th>
                <th>高</th>
                <th>高点来源</th>
                <th>低</th>
                <th>低点来源</th>
              </tr>
            </thead>
            <tbody>
              {item.elements.map((element, index) => (
                <tr key={`${element.time}-${element.klineIndex}`}>
                  <td>{index === 0 ? '左' : index === 1 ? '中' : '右'}</td>
                  <td>{formatDisplayTime(element.time)}</td>
                  <td>{formatSourceTimes(element.sourceTimes)}</td>
                  <td>{formatPrice(element.high)}</td>
                  <td>{formatDisplayTime(element.highSourceTime ?? element.time)}</td>
                  <td>{formatPrice(element.low)}</td>
                  <td>{formatDisplayTime(element.lowSourceTime ?? element.time)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ReasonList reasons={item.reasons} />
        {item.strength && <><h4>分型强弱：{strengthLabel(item.strength.grade)}</h4><ReasonList reasons={item.strength.reasons} /></>}
      </div>
    );
  }

  if (selected.kind === 'segment') {
    const item = selected.item;
    return (
      <div className="explanation-panel segment-explanation-panel">
        <button type="button" className="explanation-close" onClick={onClose} aria-label="关闭说明">
          ×
        </button>
        <h3>{item.direction === 'UP' ? '向上线段' : '向下线段'}判定</h3>
        <div className="explanation-meta">
          <span>{formatDisplayTime(item.startTime)} 至 {formatDisplayTime(item.endTime)}</span>
          <span>{formatPrice(item.startPrice)} 至 {formatPrice(item.endPrice)}</span>
          <span>{item.biCount} 笔</span>
          <span>{item.confirmed ? '已确认' : '未确认'}</span>
          <span>{formatBreakType(item.breakType)}</span>
        </div>
        {item.featureSequence.length > 0 && (
          <table className="feature-sequence-table">
            <thead>
              <tr>
                <th>元素</th>
                <th>高</th>
                <th>低</th>
                <th>来源笔</th>
                <th>前缺口</th>
              </tr>
            </thead>
            <tbody>
              {item.featureSequence.map((element, index) => (
                <tr key={`${element.startBiIndex}-${element.endBiIndex}`}>
                  <td>{index + 1}</td>
                  <td>{formatPrice(element.high)}</td>
                  <td>{formatPrice(element.low)}</td>
                  <td>{formatBiIndices(element.sourceBiIndices)}</td>
                  <td>{element.gapFromPrevious ? '有' : '无'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <ReasonList reasons={item.reasons} />
        <MomentumPanel item={item.momentum} />
      </div>
    );
  }

  const item = selected.item;
  return (
    <div className="explanation-panel">
      <button type="button" className="explanation-close" onClick={onClose} aria-label="关闭说明">
        ×
      </button>
      <h3>{item.direction === 'UP' ? '向上笔' : '向下笔'}判定</h3>
      <div className="explanation-meta">
        <span>{formatDisplayTime(item.startTime)} 至 {formatDisplayTime(item.endTime)}</span>
        <span>{formatPrice(item.startPrice)} 至 {formatPrice(item.endPrice)}</span>
        <span>{item.confirmed ? '已确认' : '未确认'}</span>
      </div>
      <ReasonList reasons={item.reasons} />
      <MomentumPanel item={item.momentum} />
    </div>
  );
}

function MomentumPanel({ item }: { item: Momentum | null }) {
  if (!item) return null;
  return <div className="momentum-panel"><h4>动能：{strengthLabel(item.grade)}</h4><p>{item.barCount} 根K线 · 幅度 {item.amplitudePercent.toFixed(2)}% · 每根速度 {item.velocity.toFixed(3)}%<br />MACD同向面积 {item.macdArea.toFixed(4)} / 峰值 {item.macdPeak.toFixed(4)}<br />前同向面积比 {item.relativeArea?.toFixed(3) ?? '无法比较'} · {item.warmupComplete ? '预热完成' : '预热不足'}<br />成交量 {formatVolume(item.volumeSum)}</p><p>强弱为同向动能比较，不是胜率。</p></div>;
}

function displaySignalZone(zone: SignalZone): CentralZone {
  return { ...zone, startSegmentIndex: zone.startUnitIndex, endSegmentIndex: zone.endUnitIndex,
    segmentCount: zone.memberIndices.length, sourceSegmentIndices: zone.memberIndices, reasons: [] };
}

function ReasonList({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) {
    return <p className="explanation-empty">旧数据暂无判定说明，重新计算后会生成。</p>;
  }
  return (
    <ul>
      {reasons.map((reason) => (
        <li key={reason}>{reason}</li>
      ))}
    </ul>
  );
}

function findNearestLine<T extends Bi | Segment>(
  lines: T[],
  point: { x: number; y: number },
  chart: ReturnType<typeof createChart>,
  candleSeries: ReturnType<ReturnType<typeof createChart>['addCandlestickSeries']>,
  threshold: number,
): T | null {
  let nearest: { line: T; distance: number } | null = null;
  for (const line of lines) {
    const x1 = chart.timeScale().timeToCoordinate(toChartTime(line.startTime));
    const x2 = chart.timeScale().timeToCoordinate(toChartTime(line.endTime));
    const y1 = candleSeries.priceToCoordinate(line.startPrice);
    const y2 = candleSeries.priceToCoordinate(line.endPrice);
    if (x1 === null || x2 === null || y1 === null || y2 === null) {
      continue;
    }
    const distance = distanceToSegment(point, { x: x1, y: y1 }, { x: x2, y: y2 });
    if (distance <= threshold && (!nearest || distance < nearest.distance)) {
      nearest = { line, distance };
    }
  }
  return nearest?.line ?? null;
}

function findCentralZone(
  zones: CentralZone[],
  point: { x: number; y: number },
  chart: ReturnType<typeof createChart>,
  candleSeries: ReturnType<ReturnType<typeof createChart>['addCandlestickSeries']>,
  firstKlineTime?: string,
  lastKlineTime?: string,
): CentralZone | null {
  for (const zone of [...zones].reverse()) {
    const bounds = centralZoneBounds(zone, chart, candleSeries, firstKlineTime, lastKlineTime);
    if (
      bounds
      && point.x >= bounds.left - 4
      && point.x <= bounds.left + bounds.width + 4
      && point.y >= bounds.top - 4
      && point.y <= bounds.top + bounds.height + 4
    ) {
      return zone;
    }
  }
  return null;
}

function centralZoneBounds(
  zone: CentralZone,
  chart: ReturnType<typeof createChart>,
  candleSeries: ReturnType<ReturnType<typeof createChart>['addCandlestickSeries']>,
  firstKlineTime?: string,
  lastKlineTime?: string,
): { left: number; top: number; width: number; height: number } | null {
  if (!firstKlineTime || !lastKlineTime) {
    return null;
  }
  const visibleStartTime = zone.startTime < firstKlineTime ? firstKlineTime : zone.startTime;
  const visibleEndTime = zone.endTime > lastKlineTime ? lastKlineTime : zone.endTime;
  const startX = chart.timeScale().timeToCoordinate(toChartTime(visibleStartTime));
  const endX = chart.timeScale().timeToCoordinate(toChartTime(visibleEndTime));
  const topY = candleSeries.priceToCoordinate(zone.zg);
  const bottomY = candleSeries.priceToCoordinate(zone.zd);
  if (startX === null || endX === null || topY === null || bottomY === null) {
    return null;
  }
  return {
    left: Math.min(startX, endX),
    top: Math.min(topY, bottomY),
    width: Math.max(2, Math.abs(endX - startX)),
    height: Math.max(2, Math.abs(bottomY - topY)),
  };
}

function distanceToSegment(point: { x: number; y: number }, start: { x: number; y: number }, end: { x: number; y: number }) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (dx === 0 && dy === 0) {
    return Math.hypot(point.x - start.x, point.y - start.y);
  }
  const t = Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / (dx * dx + dy * dy)));
  const projection = { x: start.x + t * dx, y: start.y + t * dy };
  return Math.hypot(point.x - projection.x, point.y - projection.y);
}

function formatChartTime(time: Time): string {
  if (typeof time === 'string') {
    return time;
  }
  if (typeof time === 'number') {
    return new Date(time * 1000).toISOString().slice(0, 19);
  }
  return `${time.year}-${String(time.month).padStart(2, '0')}-${String(time.day).padStart(2, '0')}`;
}

function toChartTime(value: string): Time {
  if (!value.includes('T')) {
    return value as Time;
  }
  const [datePart, timePart] = value.split('T');
  const [year, month, day] = datePart.split('-').map(Number);
  const [hour, minute, second = 0] = timePart.split(':').map(Number);
  return Math.floor(Date.UTC(year, month - 1, day, hour, minute, second) / 1000) as Time;
}

function chartTimeKey(value: string): string {
  return value.includes('T') ? value.slice(0, 19) : value;
}

function isIntradayData(data: ChartResponse): boolean {
  return ['hour4', 'minute60', 'minute30', 'minute5', 'minute1'].includes(data.period);
}

function formatPrice(value: number): string {
  return value.toFixed(2);
}

function formatOptionalPrice(value: number | null | undefined): string {
  return value == null ? '--' : formatPrice(value);
}

function formatSourceTimes(sourceTimes: string[] | undefined): string {
  if (!sourceTimes || sourceTimes.length === 0) {
    return '--';
  }
  if (sourceTimes.length === 1) {
    return formatDisplayTime(sourceTimes[0]);
  }
  return `${formatDisplayTime(sourceTimes[0])} 至 ${formatDisplayTime(sourceTimes[sourceTimes.length - 1])}`;
}

function formatDisplayTime(value: string): string {
  return value.includes('T') ? value.slice(0, 16).replace('T', ' ') : value;
}

function formatBiIndices(indices: number[]): string {
  return indices.map((index) => index + 1).join('、');
}

function formatSegmentIndices(indices: number[]): string {
  return indices.map((index) => index + 1).join('、');
}

function formatCentralZoneStatus(status: CentralZone['status']): string {
  if (status === 'LEFT_UP') {
    return '向上离开';
  }
  if (status === 'LEFT_DOWN') {
    return '向下离开';
  }
  return '延伸中';
}

function formatBreakType(type: Segment['breakType']): string {
  if (type === 'NO_GAP') {
    return '无缺口确认';
  }
  if (type === 'GAP_CONFIRMED') {
    return '缺口二次确认';
  }
  return '等待确认';
}

function formatSigned(value: number | null): string {
  if (value === null) {
    return '--';
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}`;
}

function formatPercent(value: number | null): string {
  if (value === null) {
    return '--';
  }
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
}

function formatVolume(value: number): string {
  if (value >= 100000000) {
    return `${(value / 100000000).toFixed(2)}亿`;
  }
  if (value >= 10000) {
    return `${(value / 10000).toFixed(2)}万`;
  }
  return value.toFixed(0);
}
