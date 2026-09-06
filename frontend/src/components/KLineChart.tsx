import { useEffect, useMemo, useRef, useState } from 'react';
import {
  CandlestickData,
  ColorType,
  createChart,
  LineData,
  Time,
} from 'lightweight-charts';
import type { Bi, CentralZone, ChartResponse, Fractal, Segment } from '../types/chart';

interface Props {
  data: ChartResponse;
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
}

type SelectedExplanation =
  | { kind: 'fractal'; item: Fractal }
  | { kind: 'bi'; item: Bi }
  | { kind: 'segment'; item: Segment }
  | { kind: 'centralZone'; item: CentralZone }
  | null;

export function KLineChart({ data }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<ReturnType<typeof createChart> | null>(null);
  const [hoverKline, setHoverKline] = useState<HoverKline | null>(null);
  const [selected, setSelected] = useState<SelectedExplanation>(null);
  const [centralZoneRects, setCentralZoneRects] = useState<CentralZoneRect[]>([]);
  const [showBis, setShowBis] = useState(true);
  const [showSegments, setShowSegments] = useState(true);
  const [showCentralZones, setShowCentralZones] = useState(true);

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
    const candleData: CandlestickData[] = data.klines.map((item) => ({
      time: toChartTime(item.time),
      open: item.open,
      high: item.high,
      low: item.low,
      close: item.close,
    }));
    candleSeries.setData(candleData);
    candleSeries.setMarkers(
      data.fractals.map((item) => ({
        time: toChartTime(item.time),
        position: item.type === 'TOP' ? 'aboveBar' : 'belowBar',
        color: item.type === 'TOP' ? '#b91c1c' : '#047857',
        shape: item.type === 'TOP' ? 'arrowDown' : 'arrowUp',
        text: item.type === 'TOP' ? '顶' : '底',
      })),
    );

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
      if (!showCentralZones) {
        setCentralZoneRects([]);
        return;
      }
      setCentralZoneRects(
        data.centralZones.flatMap((zone, index) => {
          const bounds = centralZoneBounds(
            zone,
            chart,
            candleSeries,
            data.klines[0]?.time,
            data.klines[data.klines.length - 1]?.time,
          );
          return bounds ? [{ zone, index, ...bounds }] : [];
        }),
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

      const clickedFractal = fractalByTime.get(formatChartTime(param.time));
      if (clickedFractal) {
        setSelected({ kind: 'fractal', item: clickedFractal });
      }
    });

    chart.timeScale().fitContent();
    chart.timeScale().subscribeVisibleLogicalRangeChange(updateCentralZoneRects);
    requestAnimationFrame(updateCentralZoneRects);
    const initialZoneRenderTimer = window.setTimeout(updateCentralZoneRects, 100);
    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
        requestAnimationFrame(updateCentralZoneRects);
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      window.clearTimeout(initialZoneRenderTimer);
      window.removeEventListener('resize', handleResize);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(updateCentralZoneRects);
      chartRef.current = null;
      chart.remove();
    };
  }, [data, fractalByTime, klineByTime, showBis, showCentralZones, showSegments]);

  return (
    <div className="chart-shell">
      {hoverKline && <KlineHoverPanel item={hoverKline} />}
      {selected && <ExplanationPanel selected={selected} onClose={() => setSelected(null)} />}
      <div className="chart-layer-controls">
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
          <span>中枢</span>
        </label>
      </div>
      <div className="chart-surface" ref={containerRef} />
      <div className="central-zone-layer">
        {centralZoneRects.map(({ zone, index, left, top, width, height }) => (
          <div
            key={`${zone.startTime}-${zone.endTime}-${zone.startSegmentIndex}`}
            className={`central-zone-box ${zone.status === 'EXTENDING' ? 'extending' : 'left'}`}
            style={{ left, top, width, height }}
            onClick={() => setSelected({ kind: 'centralZone', item: zone })}
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
              中枢 {index + 1} ZG {formatPrice(zone.zg)} / ZD {formatPrice(zone.zd)}
            </button>
          </div>
        ))}
      </div>
    </div>
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
  return ['hour4', 'minute60', 'minute30', 'minute1'].includes(data.period);
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
