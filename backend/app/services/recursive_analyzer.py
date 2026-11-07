"""Versioned structural recursion. L0 seeds are confirmed feature-sequence segments.

Parents need a child-level zone; a reverse departure plus first outside retest
confirms a boundary. This is an explicit engineering completion convention.
"""
from dataclasses import dataclass

from app.models.schemas import BiDirection, HierarchyAnalysis, Movement, SignalLevel, StructureLayer
from app.services.research_analyzer import ResearchAnalyzer, Unit, momentum, relation, zones_for


@dataclass
class MovementUnit(Unit):
    range_high: float = 0
    range_low: float = 0

    @property
    def high(self):
        return self.range_high

    @property
    def low(self):
        return self.range_low


def units_for(movements, bars):
    indices={b.time:i for i,b in enumerate(bars)}
    return [MovementUnit(i,m.start_time,m.end_time,m.start_price,m.end_price,indices[m.start_time],indices[m.end_time],
                         m.direction,m.confirmed,m.observed_at,m.momentum,m.high,m.low)
            for i,m in enumerate(movements)]


class RecursiveAnalyzer:
    @staticmethod
    def namespaced_zones(units, level):
        zones=zones_for(units,SignalLevel.SEGMENT)
        for zone in zones: zone.id=f'L{level}:{zone.id}'
        return zones

    def parents(self, children, bars, indicators, level):
        """Sequential earliest-boundary scan; future children never revise a locked parent."""
        units=units_for(children,bars)
        parents=[]
        start=0
        while start+2<len(units):
            direction=units[start].direction
            boundary=None
            used_zones=[]
            for j in range(start+3,len(units)-1):
                prefix=units[start:j]
                if not all(u.confirmed for u in prefix): break
                zones=self.namespaced_zones(prefix,level-1)
                if not zones: continue
                zone=zones[-1]
                leaving,retest=units[j],units[j+1]
                if not leaving.confirmed or not retest.confirmed: continue
                if leaving.direction==direction or retest.direction==leaving.direction: continue
                outside=(leaving.end_price<zone.zd and retest.high<zone.zd) if direction==BiDirection.UP else (leaving.end_price>zone.zg and retest.low>zone.zg)
                if not outside: continue
                # Parent geometry ends at its last directional extreme; confirmation
                # children lie after that endpoint and are tracked separately.
                eligible=[i for i in range(start,j) if units[i].direction==direction]
                endpoint=max(eligible,key=lambda i:units[i].end_price) if direction==BiDirection.UP else min(eligible,key=lambda i:units[i].end_price)
                if endpoint-start<2: continue
                # A zone must exist within the parent's actual geometry, not merely
                # in later confirmation evidence.
                geometric=self.namespaced_zones(units[start:endpoint+1],level-1)
                if not geometric: continue
                boundary=(endpoint,j,j+1)
                used_zones=geometric
                break
            if boundary is None:
                confirmed_prefix=[]
                for unit in units[start:]:
                    if not unit.confirmed: break
                    confirmed_prefix.append(unit)
                used_zones=self.namespaced_zones(confirmed_prefix,level-1)
                if not used_zones: break
                eligible=[i for i in range(start,len(units)) if units[i].direction==direction]
                endpoint=max(eligible,key=lambda i:units[i].end_price) if direction==BiDirection.UP else min(eligible,key=lambda i:units[i].end_price)
                if endpoint-start<2: break
                evidence=list(range(start,len(units)))
            else:
                endpoint,departure,retest=boundary
                evidence=list(range(start,retest+1))
            members=children[start:endpoint+1]
            time=max(children[i].observed_at for i in evidence)
            relationships=[relation(a,b) for a,b in zip(used_zones,used_zones[1:])]
            expected='TREND_UP' if direction==BiDirection.UP else 'TREND_DOWN'
            kind='TREND' if expected in relationships else 'CONSOLIDATION'
            first,last=members[0],members[-1]
            indices={b.time:i for i,b in enumerate(bars)}
            metric=momentum(bars,indicators,indices[first.start_time],indices[last.end_time],direction,first.start_price,last.end_price)
            for zone in used_zones:
                zone.start_unit_index+=start
                zone.end_unit_index+=start
                zone.member_indices=[i+start for i in zone.member_indices]
                if zone.departure_unit_index is not None: zone.departure_unit_index+=start
            parents.append(Movement(
                id=f'L{level}:{first.start_time.isoformat()}:{direction.value}',level=level,kind=kind,direction=direction,
                startTime=first.start_time,endTime=last.end_time,startPrice=first.start_price,endPrice=last.end_price,
                high=max(m.high for m in members),low=min(m.low for m in members),confirmed=boundary is not None,
                observedAt=time,childIds=[m.id for m in members],confirmationIds=[children[i].id for i in evidence if i>endpoint],
                zoneIds=[z.id for z in used_zones],childZones=used_zones,momentum=metric,
                reasons=['至少一个已形成子级中枢，两个同向分离枢判趋势，否则盘整',
                         '反向离开末枢与首次外侧回试都确认后锁定父走势；几何端点取此前方向极值',
                         '父走势完成口径是项目工程约定；不把图表周期等同于递归级别'],
            ))
            if boundary is None: break
            start=endpoint+1
        return parents

    def analyze(self, base, settings, max_level):
        settings=settings.model_copy(update={"signal_level":SignalLevel.SEGMENT})
        bars=base.klines
        seeds=[]
        for index,segment in enumerate(base.segments):
            members=base.bis[segment.start_bi_index:segment.end_bi_index+1]
            known=segment.confirmed and segment.confirmed_at is not None
            seeds.append(Movement(id=f'L0:segment:{segment.start_time.isoformat()}',level=0,kind='SEED',direction=segment.direction,
                startTime=segment.start_time,endTime=segment.end_time,startPrice=segment.start_price,endPrice=segment.end_price,
                high=max([segment.start_price,segment.end_price]+[max(b.start_price,b.end_price) for b in members]),
                low=min([segment.start_price,segment.end_price]+[min(b.start_price,b.end_price) for b in members]),
                confirmed=known,observedAt=segment.confirmed_at or (bars[-1].time if bars else segment.end_time),
                childIds=[f'bi:{i}' for i in range(segment.start_bi_index,segment.end_bi_index+1)],
                confirmationIds=[f'bi:{segment.confirmation_bi_index}'] if segment.confirmation_bi_index is not None else [],
                momentum=segment.momentum,reasons=['L0以特征序列线段初始化，不使用三笔交集充当递归中枢',*segment.reasons]))
        layers=[]
        movements=seeds
        for level in range(max_level+1):
            if not movements: break
            units=units_for(movements,bars)
            zones=self.namespaced_zones(units,level)
            research=ResearchAnalyzer()
            divergences=research.divergences(units,base.indicators,bars,settings)
            # IDs are remapped consistently: points depend on divergence and zones.
            for d in divergences:
                d.id=f'L{level}:{d.id}'
                d.zone_ids=[f'L{level}:{z}' for z in d.zone_ids]
            points=research.points(units,zones,divergences,settings)
            for point in points:
                point.id=f'L{level}:{point.id}'
                if point.parent_id: point.parent_id=f'L{level}:{point.parent_id}'
                point.structural_level=level
                point.source_period=base.period
                point.unit_id=movements[point.unit_index].id
                point.reasons+=['来源周期 '+base.period.value+'；结构层 L'+str(level)]
            layers.append(StructureLayer(level=level,movements=movements,zones=zones,divergences=divergences,tradingPoints=points))
            movements=self.parents(movements,bars,base.indicators,level+1) if level<max_level else []
        warnings=['最低走势种子采用已确认线段；上层完成由反向离开及外侧回试确认，是公开工程口径。',
                  '递归级别L0/L1…由结构形成，不对应固定1m/5m/30m时间比例；点数不是准确率。']
        if len(bars)<settings.macd_slow*3: warnings.append('基础历史不足MACD预热长度，背驰点不可靠或不可判定。')
        if len(layers)<=max_level: warnings.append('当前输入不能形成全部请求层级；只展示实际生成的层，不补造结构。')
        if base.period.value.startswith('minute'):
            warnings.append('5m来源为新浪，单次最多1023根；其他分钟源为腾讯，单次最多320根。历史只覆盖实际来源范围，不能代表全年。')
        indices={b.time:i for i,b in enumerate(bars)}
        bi_settings=settings.model_copy(update={'signal_level':SignalLevel.BI})
        observation_units=[Unit(i,b.start_time,b.end_time,b.start_price,b.end_price,
            indices[b.start_time],indices[b.end_time],b.direction,b.confirmed and b.confirmed_at is not None,
            b.confirmed_at or bars[-1].time,b.momentum) for i,b in enumerate(base.bis)]
        research=ResearchAnalyzer()
        observation_zones=zones_for(observation_units,SignalLevel.BI)
        observation_divergences=research.divergences(observation_units,base.indicators,bars,bi_settings)
        observation_points=research.points(observation_units,observation_zones,observation_divergences,bi_settings)
        for point in observation_points:
            point.source_period=base.period
            point.unit_id=f'bi:{point.unit_index}'
            point.reasons+=['基础周期笔级观察点，与L0/L1递归点分开；不升级为高层确认']
        return HierarchyAnalysis(basePeriod=base.period,maxLevel=max_level,baseAnalysis=base.analysis,
            baseKlines=bars,baseFractals=base.fractals,baseBis=base.bis,baseSegments=base.segments,
            baseTradingPoints=observation_points,baseSignalZones=observation_zones,baseDivergences=observation_divergences,
            layers=layers,warnings=warnings)
