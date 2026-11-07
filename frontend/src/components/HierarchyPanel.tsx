import { useState } from 'react';
import type { HierarchyAnalysis, Movement } from '../types/chart';
import { periodLabel, pointLabel } from '../utils/analysisLabels';

export function HierarchyPanel({ data }: { data: HierarchyAnalysis }) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const movements = new Map(data.layers.flatMap((l) => l.movements.map((m) => [m.id, m] as const)));
  const selected = selectedId ? movements.get(selectedId) : null;
  const biIndex = selectedId?.startsWith('bi:') ? Number(selectedId.slice(3)) : null;
  const bi = biIndex != null ? data.baseBis[biIndex] : null;
  const link = (id: string) => <button type="button" key={id} className="trace-link" onClick={() => setSelectedId(id)}>{id}</button>;
  return <section className="research-tables hierarchy-panel">
    <h2>结构递归与来源</h2>
    <p>基础周期 {periodLabel(data.basePeriod)} · {data.baseAnalysis.sourceCount} 根 · {data.baseAnalysis.sourceStart} 至 {data.baseAnalysis.sourceEnd} · 来源批次 {data.baseAnalysis.runId}</p>
    <p>基础规则 {data.baseAnalysis.ruleVersion} · 面积比 ≤ {data.baseAnalysis.settings.divergenceRatio} · MACD {data.baseAnalysis.settings.macdFast}/{data.baseAnalysis.settings.macdSlow}/{data.baseAnalysis.settings.macdSignal} · 零轴容差 {data.baseAnalysis.settings.zeroAxisTolerance}</p>
    {data.warnings.map((warning) => <p className="hierarchy-warning" key={warning}>{warning}</p>)}
    {data.layers.length === 0 && <p>当前基础数据无法形成递归底座。同步基础数据后重算；不会改用日K或补造结构。</p>}
    {data.layers.map((layer) => <details key={layer.level} open={layer.level === 0}>
      <summary>L{layer.level} · {layer.level === 0 ? '线段种子' : '子级中枢构造走势'} · {layer.movements.filter((m) => m.confirmed).length} 确认 / {layer.movements.filter((m) => !m.confirmed).length} 候选 · {layer.zones.length} 中枢 · {layer.tradingPoints.length} 点</summary>
      <table><thead><tr><th>结构 / 类型</th><th>几何端点</th><th>确认 / 观察</th><th>子结构</th><th>状态</th></tr></thead><tbody>{layer.movements.map((movement) => <tr key={movement.id}>
        <td>{link(movement.id)}<br />{kindLabel(movement)} / {movement.direction === 'UP' ? '上行' : '下行'}</td><td>{movement.startTime} → {movement.endTime}<br />{movement.startPrice.toFixed(2)} → {movement.endPrice.toFixed(2)}</td>
        <td>{movement.observedAt}</td><td>{movement.childIds.length} 个 · 点击结构展开</td><td>{movement.confirmed ? '结构确认' : '候选'}</td>
      </tr>)}</tbody></table>
      <details><summary>本层中枢与买卖点</summary><ul>{layer.zones.map((zone) => <li key={zone.id}>{zone.id} · 核心 {zone.zd.toFixed(2)}—{zone.zg.toFixed(2)} · 成员 {zone.memberIndices.map((i) => layer.movements[i]?.id ?? i).join('、')} · 形成 {zone.formedAt}</li>)}</ul>
        <ul>{layer.tradingPoints.map((point) => <li key={point.id}>{pointLabel(point.type)} · {point.time} · 可观察 {point.observedAt} · {point.confirmed ? '确认' : '候选'} · {point.unitId ? link(point.unitId) : null}</li>)}</ul>
        <ul>{layer.divergences.map((d) => <li key={d.id}>{d.type} · {d.time} · 比值 {d.ratio.toFixed(3)} · {d.reasons.join('；')}</li>)}</ul>
      </details>
    </details>)}
    {selected && <div className="trace-detail"><h3>{selected.id} / {kindLabel(selected)}</h3>
      <p>原始端点 {selected.startTime} → {selected.endTime}；可观察 {selected.observedAt}；{selected.confirmed ? '已确认' : '候选'}</p>
      <p>组成结构：{selected.childIds.map(link)}</p><p>确认依赖：{selected.confirmationIds.map(link)}</p>
      <ul>{selected.childZones.map((zone) => <li key={zone.id}>{zone.id} · {zone.zd.toFixed(2)}—{zone.zg.toFixed(2)} · 子级成员 {zone.memberIndices.join('、')}</li>)}</ul>
      <ul>{selected.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
    </div>}
    {bi && <div className="trace-detail"><h3>基础笔 {biIndex}</h3><p>{bi.startTime} → {bi.endTime} · {bi.startPrice.toFixed(2)} → {bi.endPrice.toFixed(2)} · {bi.confirmed ? '确认' : '候选'}</p>
      <p>确认时间 {bi.confirmedAt ?? '未确认'}；来源原始K线序号 {bi.startIndex}—{bi.endIndex}</p><ul>{bi.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
    </div>}
  </section>;
}

function kindLabel(movement: Movement) { return ({ SEED: '最低结构种子', TREND: '趋势', CONSOLIDATION: '盘整' } as Record<string,string>)[movement.kind] ?? movement.kind; }
