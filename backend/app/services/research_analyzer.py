"""Explicit, causal engineering definitions of Chan structure research signals.

A unit is a stroke or a segment, not a proven recursively completed movement.
MACD is an auxiliary measurement; the model never estimates a success probability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Union

from app.models.schemas import (
    BiDirection, CentralZoneStatus, ChartResponse, Divergence, IndicatorPoint, Momentum,
    RuleSettings, SignalLevel, SignalZone, StrengthAssessment, TradingPoint, TrendSummary, ZoneRelation,
)

Time = Union[date, datetime]


@dataclass
class Unit:
    index: int
    start_time: Time
    end_time: Time
    start_price: float
    end_price: float
    start_index: int
    end_index: int
    direction: BiDirection
    confirmed: bool
    observed_at: Time
    momentum: Momentum

    @property
    def high(self):
        return max(self.start_price, self.end_price)

    @property
    def low(self):
        return min(self.start_price, self.end_price)


def macd(klines, settings: RuleSettings) -> list[IndicatorPoint]:
    if not klines:
        return []
    fast = slow = klines[0].close
    dea = 0.0
    result = []
    for index, bar in enumerate(klines):
        fast += 2 / (settings.macd_fast + 1) * (bar.close - fast)
        slow += 2 / (settings.macd_slow + 1) * (bar.close - slow)
        dif = fast - slow
        dea += 2 / (settings.macd_signal + 1) * (dif - dea)
        result.append(IndicatorPoint(time=bar.time, dif=dif, dea=dea, histogram=2*(dif-dea),
                                     ready=index >= settings.macd_slow*3-1))
    return result


def momentum(klines, indicators, start, end, direction, start_price, end_price) -> Momentum:
    # (start, end] avoids counting the shared endpoint of adjacent units twice.
    bars = klines[start+1:end+1]
    points = indicators[start+1:end+1]
    signs = [max(0.0, p.histogram if direction == BiDirection.UP else -p.histogram) for p in points]
    amplitude = abs(end_price-start_price)/abs(start_price)*100 if start_price else 0
    return Momentum(barCount=len(bars), amplitudePercent=amplitude, velocity=amplitude/max(1,len(bars)),
                    macdArea=sum(signs), macdPeak=max(signs,default=0), volumeSum=sum(b.volume for b in bars),
                    warmupComplete=bool(points) and all(p.ready for p in points))


def zones_for(units: list[Unit], level: SignalLevel) -> list[SignalZone]:
    result = []
    start = 0
    while start+2 < len(units):
        initial = units[start:start+3]
        if not all(u.confirmed for u in initial):
            break
        zd = max(u.low for u in initial)
        zg = min(u.high for u in initial)
        if zd >= zg:
            start += 1
            continue
        end = start+2
        departure = None
        while end+1 < len(units):
            following = units[end+1]
            if not following.confirmed or following.low >= zg or following.high <= zd:
                break
            # An exit leg starts inside the core, so interval intersection alone would
            # wrongly include its outside extreme in the old zone forever. A completed
            # first outside retest separates that exit leg from the old zone's envelope.
            if end+2 < len(units):
                retest=units[end+2]
                exits_up=following.direction==BiDirection.UP and following.end_price>zg and retest.low>zg
                exits_down=following.direction==BiDirection.DOWN and following.end_price<zd and retest.high<zd
                if retest.confirmed and retest.direction!=following.direction and (exits_up or exits_down):
                    departure=end+1
                    break
            end += 1
        members = units[start:end+1]
        status = CentralZoneStatus.EXTENDING
        if departure is not None:
            status=CentralZoneStatus.LEFT_UP if units[departure].direction==BiDirection.UP else CentralZoneStatus.LEFT_DOWN
        elif end+1 < len(units) and units[end+1].confirmed:
            outside = units[end+1]
            if outside.low >= zg:
                status = CentralZoneStatus.LEFT_UP
            elif outside.high <= zd:
                status = CentralZoneStatus.LEFT_DOWN
        result.append(SignalZone(
            id=f'{level.value}:zone:{units[start].start_time.isoformat()}', level=level,
            startUnitIndex=start, endUnitIndex=end, startTime=members[0].start_time, endTime=members[-1].end_time,
            formedAt=max(u.observed_at for u in initial), zd=zd,zg=zg,
            closedAt=max(units[departure].observed_at,units[departure+1].observed_at) if departure is not None else None,
            departureUnitIndex=departure,
            dd=min(u.low for u in members),gg=max(u.high for u in members),
            memberIndices=list(range(start,end+1)),status=status,
        ))
        start=departure+1 if departure is not None else end+1
    return result


def relation(previous: SignalZone, current: SignalZone) -> str:
    if current.dd > previous.gg:
        return 'TREND_UP'
    if current.gg < previous.dd:
        return 'TREND_DOWN'
    if max(previous.zd,current.zd) < min(previous.zg,current.zg):
        return 'CORE_OVERLAP'
    return 'EXPANSION'  # Core separated/contact but member envelopes overlap/contact.


class ResearchAnalyzer:
    def enrich(self, chart: ChartResponse, settings: RuleSettings) -> None:
        if not chart.klines:
            chart.trend = TrendSummary(level=settings.signal_level, reasons=['本地没有该周期行情'])
            return
        chart.indicators = macd(chart.klines,settings)
        time_index = {b.time:i for i,b in enumerate(chart.klines)}
        for fractal in chart.fractals:
            if len(fractal.elements) != 3:
                continue
            left,middle,right = fractal.elements
            right_close=chart.klines[time_index[right.time]].close
            if fractal.type.value == 'TOP':
                strong = right_close < left.low
                normal = right.low < left.low
                comparison='强：右侧原始K线收盘跌破左元素低点；中：右元素低点跌破左元素低点；否则弱'
            else:
                strong = right_close > left.high
                normal = right.high > left.high
                comparison='强：右侧原始K线收盘突破左元素高点；中：右元素高点突破左元素高点；否则弱'
            fractal.strength=StrengthAssessment(grade='STRONG' if strong else 'NORMAL' if normal else 'WEAK',
                reasons=[comparison, f'左区间[{left.low:g},{left.high:g}]；中区间[{middle.low:g},{middle.high:g}]；右区间[{right.low:g},{right.high:g}]',
                         '只衡量三元素的反向突破力度，不表示交易成功概率'])

        # Replaying observation prefixes avoids assigning the latest extended
        # endpoint of the following stroke as a historical confirmation time.
        from app.services.chan_analyzer import ChanAnalyzer
        from app.services.rule_policy import effective_gap
        from app.services.segment_analyzer import SegmentAnalyzer
        analyzer=ChanAnalyzer()
        key=lambda b:(b.start_time,b.end_time,b.start_price,b.end_price)
        pending={key(b) for b in chart.bis if b.confirmed}
        pending_segments={key(s) for s in chart.segments if s.confirmed}
        first_seen={}
        segment_seen={}
        canonical_segments={}
        for count in range(3,len(chart.klines)+1):
            if not pending and not pending_segments:
                break
            merged=analyzer.merge_include_klines(chart.klines[:count])
            detected=analyzer.stroke_fractals(analyzer.detect_fractals(merged),merged)
            strokes=analyzer.build_bis(detected,effective_gap(settings))
            for stroke in strokes:
                identity=key(stroke)
                if stroke.confirmed and identity in pending:
                    first_seen[identity]=chart.klines[count-1].time
                    pending.remove(identity)
            if pending_segments:
                for segment in SegmentAnalyzer().build_segments(strokes):
                    identity=key(segment)
                    if segment.confirmed and identity in pending_segments:
                        segment_seen[identity]=chart.klines[count-1].time
                        canonical_segments[identity]=segment
                        pending_segments.remove(identity)
        # Freeze the feature sources and confirmation dependency together with
        # their first observable geometry; later inclusion may extend evidence.
        chart.segments=[canonical_segments.get(key(s),s) for s in chart.segments]

        for index,bi in enumerate(chart.bis):
            bi.momentum=momentum(chart.klines,chart.indicators,time_index[bi.start_time],time_index[bi.end_time],bi.direction,bi.start_price,bi.end_price)
            if bi.confirmed:
                bi.confirmed_at=first_seen.get(key(bi))
        for segment in chart.segments:
            segment.momentum=momentum(chart.klines,chart.indicators,time_index[segment.start_time],time_index[segment.end_time],segment.direction,segment.start_price,segment.end_price)
            dependency=segment.confirmation_bi_index
            if segment.confirmed and dependency is not None and dependency < len(chart.bis):
                segment.confirmed_at=segment_seen.get(key(segment))

        for collection in [chart.bis,chart.segments]:
            previous={}
            for item in collection:
                earlier=previous.get(item.direction)
                metric=item.momentum
                if earlier and earlier.warmup_complete and metric.warmup_complete and earlier.macd_area > 1e-12:
                    metric.relative_area=metric.macd_area/earlier.macd_area
                    metric.grade='STRONG' if metric.relative_area > 1/settings.divergence_ratio else 'WEAK' if metric.relative_area <= settings.divergence_ratio else 'NORMAL'
                previous[item.direction]=metric

        collection=chart.bis if settings.signal_level == SignalLevel.BI else chart.segments
        units=[Unit(i,u.start_time,u.end_time,u.start_price,u.end_price,time_index[u.start_time],time_index[u.end_time],
                    u.direction,u.confirmed and u.confirmed_at is not None,u.confirmed_at or chart.klines[-1].time,u.momentum)
               for i,u in enumerate(collection)]
        chart.signal_zones=zones_for(units,settings.signal_level)
        chart.zone_relations=[ZoneRelation(previousZoneId=a.id,currentZoneId=b.id,type=relation(a,b),
            observedAt=max(b.formed_at,a.closed_at or a.formed_at,b.closed_at or b.formed_at,units[a.end_unit_index].observed_at,units[b.end_unit_index].observed_at),
            reasons=[f'前包络[{a.dd:g},{a.gg:g}]，后包络[{b.dd:g},{b.gg:g}]',
                     '严格包络分离判方向趋势；核心重叠判扩展；其余包络接触/重叠判扩张候选'])
            for a,b in zip(chart.signal_zones,chart.signal_zones[1:])]
        latest_relation=chart.zone_relations[-1].type if chart.zone_relations else None
        chart.trend=TrendSummary(level=settings.signal_level,
            type=latest_relation if latest_relation in ('TREND_UP','TREND_DOWN') else 'CONSOLIDATION' if chart.signal_zones else 'INSUFFICIENT',
            zoneIds=[z.id for z in chart.signal_zones[-2:]],
            reasons=['按当前选择的结构层级及最近中枢关系分类；没有跨周期递归证明',
                     '至少两个同向严格分离包络才判趋势；有中枢但未形成方向趋势判盘整'])
        chart.divergences=self.divergences(units,chart.indicators,chart.klines,settings)
        chart.trading_points=self.points(units,chart.signal_zones,chart.divergences,settings)

    def divergences(self, units, indicators, klines, settings):
        result=[]
        for i,current in enumerate(units):
            if i < 2 or not current.momentum.warmup_complete:
                continue
            # Only already-formed prefix zones; never use the final zone envelope for a past point.
            prefix_zones=zones_for(units[:i],settings.signal_level)
            latest=prefix_zones[-1] if prefix_zones else None
            previous=None
            kind='LOCAL'
            zone_ids=[]
            dependency_time=current.observed_at
            if latest and i > latest.start_unit_index+2:
                entering=[u for u in units[:latest.start_unit_index] if u.direction==current.direction]
                if entering:
                    previous=entering[-1]
                    kind='CONSOLIDATION'
                    zone_ids=[latest.id]
                    dependency_time=max(dependency_time,latest.formed_at,units[latest.end_unit_index].observed_at)
                    dependency_time=max(dependency_time,latest.closed_at or latest.formed_at)
                    if len(prefix_zones)>=2:
                        earlier=prefix_zones[-2]
                        dependency_time=max(dependency_time,earlier.closed_at or earlier.formed_at)
                        expected='TREND_UP' if current.direction==BiDirection.UP else 'TREND_DOWN'
                        if relation(earlier,latest)==expected and previous.index >= earlier.end_unit_index:
                            beyond=current.end_price>latest.gg if current.direction==BiDirection.UP else current.end_price<latest.dd
                            kind='TREND' if beyond else 'CONSOLIDATION'
                            zone_ids=[earlier.id,latest.id]
            if previous is None:
                previous=units[i-2]
            if previous.direction != current.direction or not previous.confirmed or not previous.momentum.warmup_complete:
                continue
            new_extreme=current.end_price>previous.end_price if current.direction==BiDirection.UP else current.end_price<previous.end_price
            area=previous.momentum.macd_area
            if not new_extreme or area<=1e-12:
                continue
            ratio=current.momentum.macd_area/area
            if ratio > settings.divergence_ratio:
                continue
            if kind != 'LOCAL':
                lo=units[latest.start_unit_index].start_index
                hi=units[latest.end_unit_index].end_index
                # Both lines must return to the configured fraction of price, using prefix data only.
                zero_return=any(p.ready and max(abs(p.dif),abs(p.dea)) <= settings.zero_axis_tolerance*abs(klines[j].close)
                                for j,p in enumerate(indicators[lo:hi+1],start=lo))
                if not zero_return:
                    kind='LOCAL'
                    zone_ids=[]
            result.append(Divergence(
                id=f'{settings.signal_level.value}:div:{current.start_time.isoformat()}:{current.end_time.isoformat()}',
                level=settings.signal_level,direction=current.direction,type=kind,time=current.end_time,
                observedAt=dependency_time,confirmed=current.confirmed,
                previousUnitIndex=previous.index,currentUnitIndex=i,previousArea=area,currentArea=current.momentum.macd_area,
                ratio=ratio,zoneIds=zone_ids,reasons=[f'价格创同向新极值：{previous.end_price:g} → {current.end_price:g}',
                    f'同向MACD柱面积比 {ratio:.4f} ≤ 阈值 {settings.divergence_ratio:g}',
                    f'比较单元 {previous.index+1} 与 {i+1}；类型 {kind}',
                    '趋势/盘整背驰要求中枢内DIF与DEA回拉零轴；缺条件只记局部动能衰减',
                    'MACD辅助研究定义，不是精确递归走势背驰证明'],
            ))
        return result

    def points(self,units,zones,divergences,settings):
        points=[]

        def add(kind,unit,zone_ids,dependencies,reason,parent=None,divergence=None,invalidation=None):
            side='BUY' if kind.startswith('B') else 'SELL'
            known=all(u.confirmed for u in dependencies)
            observed=max(u.observed_at for u in dependencies)
            if divergence:
                observed=max(observed,divergence.observed_at)
                known=known and divergence.confirmed
            if parent:
                observed=max(observed,parent.observed_at)
                known=known and parent.confirmed
            point=TradingPoint(id=f'{settings.signal_level.value}:{kind}:{unit.start_time.isoformat()}:{unit.end_time.isoformat()}',
                type=kind,side=side,level=settings.signal_level,time=unit.end_time,price=unit.end_price,
                observedAt=observed,confirmed=known,unitIndex=unit.index,zoneIds=zone_ids,
                parentId=parent.id if parent else None,divergenceId=divergence.id if divergence else None,
                invalidationPrice=invalidation if invalidation is not None else unit.end_price,
                reasons=[reason, f'结构端点 {unit.end_time.isoformat()}，最早可观察时间 {observed.isoformat()}',
                         '结构单元已确认' if known else '候选：当前单元未完成，可延伸或消失',
                         '笔/线段级模型点，不等同于已证明的递归走势级别买卖点'],
            )
            if not any(p.id==point.id for p in points):
                points.append(point)
            return point

        for divergence in divergences:
            if divergence.type != 'TREND':
                continue
            current=units[divergence.current_unit_index]
            first=add('B1' if current.direction==BiDirection.DOWN else 'S1',current,divergence.zone_ids,
                [current,units[divergence.previous_unit_index]],'两同向分离中枢背景，离开段创新极值且同向动能衰减，满足模型一类点',divergence=divergence)
            if not first.confirmed or current.index+2 >= len(units):
                continue
            rebound=units[current.index+1]
            retest=units[current.index+2]
            holds=retest.end_price>current.end_price if first.side=='BUY' else retest.end_price<current.end_price
            if rebound.direction==current.direction or retest.direction!=current.direction or not holds:
                continue
            add('B2' if first.side=='BUY' else 'S2',retest,first.zone_ids,[current,rebound,retest],
                '已确认一类点后，首次反向单元及首次回试；回试严格不破一类点极值',
                parent=first,invalidation=current.end_price)

        for zone in zones:
            succeeded=set()
            for j in range(zone.start_unit_index+3,min(len(units)-1,zone.end_unit_index+2)):
                leaving,retest=units[j],units[j+1]
                side='BUY' if leaving.direction==BiDirection.UP else 'SELL'
                if side in succeeded or retest.direction==leaving.direction:
                    continue
                outside=leaving.end_price>zone.zg if side=='BUY' else leaving.end_price<zone.zd
                holds=retest.low>zone.zg if side=='BUY' else retest.high<zone.zd
                if not outside or not holds:
                    continue
                dependencies=units[zone.start_unit_index:zone.start_unit_index+3]+[leaving,retest]
                if not leaving.confirmed:
                    continue
                add('B3' if side=='BUY' else 'S3',retest,[zone.id],dependencies,
                    f'已形成中枢[{zone.zd:g},{zone.zg:g}]；离开后首次有效回试严格不回核心',
                    invalidation=zone.zg if side=='BUY' else zone.zd)
                succeeded.add(side)
        return sorted(points,key=lambda p:(p.observed_at,p.time,p.type))
