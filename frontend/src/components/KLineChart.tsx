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
import type { Bi, ChartResponse, Fractal, Segment } from '../types/chart';
import { buildTimeline, visibleCandleRange } from '../utils/chartTimeline';
import { makeWheelFocus, wheelLogicalRange, ZOOM_IN_SPACING, ZOOM_OUT_SPACING, RETURN_EXPANSION } from '../utils/wheelNavigation';
import type { WheelFocus, ZoomDirection } from '../utils/wheelNavigation';
import { periodButtonRange } from '../utils/wheelNavigation';
import type { PeriodViewport } from '../utils/wheelNavigation';

interface Props {
  data: ChartResponse;
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

type SelectedExplanation =
  | { kind: 'fractal'; item: Fractal }
  | { kind: 'bi'; item: Bi }
  | { kind: 'segment'; item: Segment }
  | null;

export function KLineChart({ data, wheelFocus, wheelCanReturn, onWheelNavigate, periodViewport, readViewport }: Props) {
  const shellRef = useRef<HTMLDivElement | null>(null);
  const macdRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [hoverKline, setHoverKline] = useState<HoverKline | null>(null);
  const [selected, setSelected] = useState<SelectedExplanation>(null);
  const [showBis, setShowBis] = useState(true);
  const [showSegments, setShowSegments] = useState(true);
  const [showFractals, setShowFractals] = useState(false);
  const [autoPeriod, setAutoPeriod] = useState(true);
  const wheelOptions = useRef({ onWheelNavigate, wheelCanReturn, autoPeriod });
  wheelOptions.current = { onWheelNavigate, wheelCanReturn, autoPeriod };
  const wheelState = useRef({ busy: false, lastEvent: 0, switched: false, blocked: '' });
  useEffect(() => {
    if (periodViewport) wheelState.current = { busy: false, lastEvent: 0, switched: false, blocked: '' };
  }, [periodViewport]);

  useEffect(() => {
    wheelState.current.blocked = '';
  }, [data.symbol, data.period, data.klines]);

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
    if (!containerRef.current || !macdRef.current) return;
    setSelected(null);
    setHoverKline(null);
    const timeline = buildTimeline(data.klines, [
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
    candleSeries.setMarkers(markers);


    if (showBis) {
      data.bis.forEach((bi) => {
        const line = chart.addLineSeries({
          color: '#2563eb',
          lineWidth: 2,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        line.setData(toBiLineData(bi));
        if (!bi.confirmed) {
          line.setMarkers([{ time: toChartTime(bi.endTime), position: 'belowBar',
            shape: 'circle', size: 0.6, color: '#2563eb', text: '笔终点待定' }]);
        }
      });
    }

    if (showSegments) {
      data.segments.forEach((segment) => {
        const line = chart.addLineSeries({
          color: '#dc2626',
          lineWidth: 4,
          pointMarkersVisible: true,
          pointMarkersRadius: 4,
          priceLineVisible: false,
          lastValueVisible: false,
        });
        line.setData(toSegmentLineData(segment));
        if (!segment.confirmed) {
          line.setMarkers([{ time: toChartTime(segment.endTime), position: 'aboveBar',
            shape: 'circle', size: 0.6, color: '#dc2626', text: '段终点待定' }]);
        }
      });
    }

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

      const clickedFractal = fractalByTime.get(formatChartTime(param.time));
      if (clickedFractal) {
        setSelected({ kind: 'fractal', item: clickedFractal });
      }
    });

    const indicatorChart = createChart(macdRef.current, {
      width: containerRef.current.clientWidth, height: 180,
      layout: chart.options().layout,
      grid: chart.options().grid,
      rightPriceScale: { minimumWidth: 96 },
      timeScale: { timeVisible: isIntradayData(data), secondsVisible: false },
    });
    const seriesOptions = { priceLineVisible: false, lastValueVisible: false };
    const histogram = indicatorChart.addHistogramSeries(seriesOptions);
    const dif = indicatorChart.addLineSeries({ ...seriesOptions, color: '#2563eb', lineWidth: 1 });
    const dea = indicatorChart.addLineSeries({ ...seriesOptions, color: '#d97706', lineWidth: 1 });
    const points = new Map(data.macd.map((item) => [chartTimeKey(item.time), item]));
    const rows = (field: 'histogram' | 'dif' | 'dea') => timeline.map((stamp) => {
      const point = points.get(stamp);
      const time = toChartTime(stamp);
      if (!point) return { time };
      if (field === 'histogram') return { time, value: point.histogram, color: point.histogram >= 0 ? '#dc2626' : '#047857' };
      return { time, value: point[field] };
    });
    histogram.setData(rows('histogram'));
    dif.setData(rows('dif'));
    dea.setData(rows('dea'));

    const syncRange = (target: typeof chart) => (range: { from: number; to: number } | null) => {
      if (!range) return;
      const current = target.timeScale().getVisibleLogicalRange();
      if (!current || Math.abs(current.from - range.from) > 0.001 || Math.abs(current.to - range.to) > 0.001)
        target.timeScale().setVisibleLogicalRange(range);
    };
    const toIndicator = syncRange(indicatorChart);
    const toPrice = syncRange(chart);
    chart.timeScale().subscribeVisibleLogicalRangeChange(toIndicator);
    indicatorChart.timeScale().subscribeVisibleLogicalRangeChange(toPrice);
    chart.subscribeCrosshairMove(({ time }) => {
      const point = time && points.get(formatChartTime(time));
      if (time && point) indicatorChart.setCrosshairPosition(point.dif, time, dif);
      else indicatorChart.clearCrosshairPosition();
    });
    indicatorChart.subscribeCrosshairMove(({ time }) => {
      const candle = time && candlesByTime.get(formatChartTime(time));
      if (time && candle) chart.setCrosshairPosition(candle.close, time, candleSeries);
      else chart.clearCrosshairPosition();
    });

    const initialCandleRange = periodViewport ? periodButtonRange(timeline, data.klines, data.period, chart.timeScale().width(), periodViewport)
      : wheelFocus ? wheelLogicalRange(timeline, data.klines, data.period, wheelFocus)
      : visibleCandleRange(timeline, data.klines);
    if (initialCandleRange) chart.timeScale().setVisibleLogicalRange(initialCandleRange);
    else chart.timeScale().fitContent();
    toIndicator(chart.timeScale().getVisibleLogicalRange());
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
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
        indicatorChart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener('resize', handleResize);

    const initialCount = initialCandleRange ? initialCandleRange.to - initialCandleRange.from + 1 : 0;
    const wheelSurface = shellRef.current;
    const handleWheel = (event: WheelEvent) => {
      if (!event.deltaY || Math.abs(event.deltaX) > Math.abs(event.deltaY)) return;
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
      window.removeEventListener('resize', handleResize);
      wheelSurface?.removeEventListener('wheel', handleWheel, true);
      if (readViewport) readViewport.current = null;
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(toIndicator);
      indicatorChart.timeScale().unsubscribeVisibleLogicalRangeChange(toPrice);
      indicatorChart.remove();
      chart.remove();
    };
  }, [data, wheelFocus, periodViewport, readViewport, fractalByTime, klineByTime, showBis, showSegments, showFractals]);

  return (
    <>
        <label className="wheel-toggle"><input type="checkbox" checked={autoPeriod} onChange={(event) => setAutoPeriod(event.target.checked)} />滚轮自动切换周期</label>
    <div ref={shellRef} className="chart-shell">
      {hoverKline && <KlineHoverPanel item={hoverKline} />}
      {selected && <ExplanationPanel selected={selected} onClose={() => setSelected(null)} />}
      <div className="chart-layer-controls">
        <label><input type="checkbox" checked={showFractals} onChange={(event) => setShowFractals(event.target.checked)} /><span>分型</span></label>
        <label>
          <input type="checkbox" checked={showBis} onChange={(event) => setShowBis(event.target.checked)} />
          <span>笔（蓝线）</span>
        </label>
        <label>
          <input type="checkbox" checked={showSegments} onChange={(event) => setShowSegments(event.target.checked)} />
          <span>线段（红线）</span>
        </label>
      </div>
      <div className="chart-surface" ref={containerRef} />
      <div className="macd-caption">MACD（12, 26, 9） · DIF 蓝线 · DEA 橙线</div>
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
          <span>{item.confirmed ? '终点已确认' : '终点待定'}</span>
          {item.confirmed && <span>{formatBreakType(item.breakType)}</span>}
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
        <span>{item.confirmed ? '终点已确认' : '终点待定'}</span>
      </div>
      <ReasonList reasons={item.reasons} />
    </div>
  );
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

function formatBreakType(type: Segment['breakType']): string {
  if (type === 'PIVOT_BREAK') return '反向笔突破前高／前低';
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
