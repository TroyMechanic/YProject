from datetime import date,timedelta
import json
import random

import pytest

from app.models.schemas import IndicatorPoint,Kline,KlinePeriod,Movement
from app.services.chart_service import ChartService,AnalysisStateError
from app.services.csv_store import CsvStore
from app.services.hierarchy_service import HierarchyService,map_time
from app.services.recursive_analyzer import RecursiveAnalyzer
from app.services.rule_policy import digest
from test_research_analyzer import make_units


def fixture(values,level=0):
    units=make_units(values)
    movements=[Movement(id=f'L{level}:{u.index}',level=level,kind='SEED' if level==0 else 'CONSOLIDATION',direction=u.direction,
        startTime=u.start_time,endTime=u.end_time,startPrice=u.start_price,endPrice=u.end_price,high=u.high,low=u.low,
        confirmed=True,observedAt=u.observed_at,childIds=[],momentum=u.momentum,reasons=[]) for u in units]
    times=[units[0].start_time]+[u.end_time for u in units]
    bars=[Kline(time=t,open=100,high=100,low=100,close=100) for t in times]
    indicators=[IndicatorPoint(time=t,dif=0,dea=0,histogram=1,ready=True) for t in times]
    return movements,bars,indicators


VALUES=[101,110,105,112,107,116,111,118,108,113,104,109,102,108,103,110,105,112,101,106,98,104]


def test_real_month_snapshot_produces_traceable_sell_point_without_future_data(tmp_path):
    from pathlib import Path
    from datetime import datetime
    from app.models.schemas import RuleSettings
    sample=json.loads((Path(__file__).parent/'fixtures/luxshare_5m_20260930.json').read_text())
    bars=[Kline(time=datetime.fromisoformat(r['day']),open=r['open'],high=r['high'],
                low=r['low'],close=r['close'],volume=r['volume'],amount=r.get('amount',0))
          for r in sample['rows']]
    charts=ChartService(CsvStore(tmp_path/'raw',tmp_path/'analysis'))
    def points(rows):
        base=charts._build('002475.SZ',KlinePeriod.MINUTE_5,rows,RuleSettings(),persist=False)
        h=RecursiveAnalyzer().analyze(base,base.analysis.settings,4)
        return base,[p for layer in h.layers for p in layer.trading_points]
    base,full=points(bars)
    # Accepted geometry change in decision 0005: ambiguous opening triplet is skipped.
    assert sum(s.confirmed for s in base.segments)==14
    assert all((s.end_price>s.start_price)==(s.direction.value=='UP') for s in base.segments)
    assert [(p.type,p.time,p.observed_at) for p in full]==[
        ('S3',datetime(2026,9,16,11,30),datetime(2026,9,21,15)),
        ('S3',datetime(2026,9,29,9,55),datetime(2026,9,29,13,10))]
    for target in full:
        cutoff=target.observed_at
        _,before=points([b for b in bars if b.time<cutoff])
        assert not any(p.id==target.id and p.confirmed for p in before)
        _,observed=points([b for b in bars if b.time<=cutoff])
        assert next(p.model_dump() for p in observed if p.id==target.id)==target.model_dump()


def test_tongfu_real_snapshot_initialization_recovers_structures_and_causal_signal(tmp_path):
    from pathlib import Path
    from datetime import datetime
    from app.models.schemas import RuleSettings
    sample=json.loads((Path(__file__).parent/'fixtures/tongfu_5m_20260930.json').read_text())
    bars=[Kline.model_validate(b) for b in sample['klines']]
    charts=ChartService(CsvStore(tmp_path/'raw',tmp_path/'analysis'))
    def analyze(rows):
        base=charts._build('002156.SZ',KlinePeriod.MINUTE_5,rows,RuleSettings(),persist=False)
        return base,RecursiveAnalyzer().analyze(base,base.analysis.settings,4)
    base,h=analyze(bars)
    assert len(base.bis)==75 and base.segments[0].start_bi_index==1
    assert sum(s.confirmed for s in base.segments)==10
    assert len(h.layers[0].zones)==2
    assert len(h.layers)==2 and sum(m.confirmed for m in h.layers[1].movements)==1
    buys=[p for p in base.trading_points if p.side=='BUY' and p.confirmed]
    assert [(p.type,p.time,p.observed_at,p.price) for p in buys]==[
        ('B3',datetime(2026,9,29,10,10),datetime(2026,9,29,10,30),60.03)]
    observation_buys=[p for p in h.base_trading_points if p.side=='BUY' and p.confirmed]
    assert len(observation_buys)==1 and observation_buys[0].source_period==KlinePeriod.MINUTE_5
    assert observation_buys[0].structural_level is None and observation_buys[0].unit_id.startswith('bi:')
    assert set(observation_buys[0].zone_ids)<={z.id for z in h.base_signal_zones}
    points=[p for layer in h.layers for p in layer.trading_points]
    assert [(p.type,p.time,p.observed_at) for p in points]==[
        ('S3',datetime(2026,9,15,10,35),datetime(2026,9,16,10,10))]
    cutoff=points[0].observed_at
    _,before=analyze([b for b in bars if b.time<cutoff])
    # The provisional S3 may already be visible, but cannot claim confirmation.
    assert not any(p.id==points[0].id and p.confirmed for layer in before.layers for p in layer.trading_points)
    prefix_base,observed=analyze([b for b in bars if b.time<=cutoff])
    assert next(p.model_dump() for layer in observed.layers for p in layer.trading_points
                if p.id==points[0].id)==points[0].model_dump()
    for segment in prefix_base.segments:
        if not segment.confirmed:
            continue
        final=next(s for s in base.segments if s.start_time==segment.start_time and s.end_time==segment.end_time)
        assert final.model_dump()==segment.model_dump()
        dependencies={i for f in final.feature_sequence for i in f.source_bi_indices}
        dependencies.add(final.confirmation_bi_index)
        assert all(base.bis[i].confirmed_at<=final.confirmed_at for i in dependencies)


@pytest.mark.parametrize('level',[0,1,2])
def test_parent_requires_child_zone_and_reverse_outside_retest(level):
    children,bars,indicators=fixture(VALUES,level)
    parents=RecursiveAnalyzer().parents(children,bars,indicators,level+1)
    first=parents[0]
    assert first.confirmed and first.level==level+1 and first.end_price==118
    assert first.child_ids==[f'L{level}:{i}' for i in range(7)]
    assert first.confirmation_ids==[f'L{level}:{i}' for i in range(7,11)]
    assert first.observed_at==children[10].observed_at>first.end_time
    assert first.child_zones and set(first.zone_ids)=={z.id for z in first.child_zones}
    assert parents[1].start_time==first.end_time and parents[1].start_price==first.end_price
    assert not parents[1].confirmed


def test_touching_core_does_not_confirm_parent_and_unconfirmed_evidence_is_not_accepted():
    children,bars,indicators=fixture(VALUES[:12])
    children[10].confirmed=False
    parents=RecursiveAnalyzer().parents(children,bars,indicators,1)
    assert not any(p.confirmed for p in parents)
    children,bars,indicators=fixture([100,110,105,112,107,109,106,108])
    assert not any(p.confirmed for p in RecursiveAnalyzer().parents(children,bars,indicators,1))


def test_confirmed_parent_geometry_children_and_time_survive_append():
    analyzer=RecursiveAnalyzer()
    for seed in range(10):
        rng=random.Random(seed)
        values=[100]
        for i in range(50):values.append(values[-1]+(1 if i%2==0 else -1)*rng.randint(2,20))
        children,bars,indicators=fixture(values)
        previous={}
        for count in range(4,len(children)+1):
            parents=analyzer.parents(children[:count],bars,indicators,1)
            current={m.id:m.model_dump() for m in parents if m.confirmed}
            assert all(current.get(k)==v for k,v in previous.items()),(seed,count)
            previous=current


def test_display_mapping_preserves_intraday_point_time_and_calendar_bucket():
    from datetime import datetime
    time=datetime(2026,9,30,10,35)
    daily=[Kline(time=date(2026,9,30),open=10,high=10,low=10,close=10)]
    assert map_time(time,daily,KlinePeriod.DAILY)==date(2026,9,30)
    assert time.hour==10 and time.minute==35
    assert map_time(datetime(2026,9,29,10),daily,KlinePeriod.DAILY) is None


@pytest.mark.parametrize('period,minutes',[(KlinePeriod.MINUTE_1,1),(KlinePeriod.MINUTE_5,5),
                                        (KlinePeriod.MINUTE_30,30),(KlinePeriod.MINUTE_60,60)])
def test_minute_mapping_requires_the_candle_to_cover_the_original_time(period,minutes):
    from datetime import datetime
    close=datetime(2026,9,29,14)
    bars=[Kline(time=close,open=10,high=10,low=10,close=10)]
    assert map_time(close,bars,period)==close
    assert map_time(close-timedelta(minutes=minutes)+timedelta(seconds=1),bars,period)==close
    assert map_time(close-timedelta(minutes=minutes),bars,period) is None
    assert map_time(datetime(2026,9,29,10,30),bars,period) is None
    assert map_time(close+timedelta(minutes=1),bars,period) is None


def test_minute_tail_does_not_move_morning_buy_into_afternoon():
    from datetime import datetime
    # Regression for the observed Tongfu tail starting at 13:42. Synthetic OHLC
    # is immaterial here: only candle coverage, never prices, determines mapping.
    first=Kline(time=datetime(2026,9,29,13,42),open=60,high=61,low=59,close=60)
    assert map_time(datetime(2026,9,29,10,30),[first],KlinePeriod.MINUTE_1) is None
    assert map_time(first.time,[first],KlinePeriod.MINUTE_1)==first.time


def test_compound_snapshot_empty_base_does_not_fallback_and_restores_saved_options(tmp_path):
    charts=ChartService(CsvStore(tmp_path/'raw',tmp_path/'analysis'))
    service=HierarchyService(charts)
    chart=service.get('002475',KlinePeriod.DAILY,KlinePeriod.MINUTE_5,3)
    assert chart.hierarchy.base_period==KlinePeriod.MINUTE_5 and not chart.hierarchy.layers
    assert any('没有本地行情' in w for w in chart.hierarchy.warnings)
    assert not chart.trading_points
    saved=service.get('002475',KlinePeriod.DAILY)
    assert saved.hierarchy.max_level==3 and saved.analysis.run_id==chart.analysis.run_id
    raw=json.loads(service.path('002475.SZ',KlinePeriod.DAILY).read_text())
    assert raw['analysis']['resultHash']==digest({k:v for k,v in raw.items() if k!='analysis'})
    raw['hierarchy']['maxLevel']=8
    service.path('002475.SZ',KlinePeriod.DAILY).write_text(json.dumps(raw))
    with pytest.raises(AnalysisStateError):service.get('002475',KlinePeriod.DAILY)


def test_upper_period_is_not_a_permitted_recursion_base(tmp_path):
    service=HierarchyService(ChartService(CsvStore(tmp_path/'raw',tmp_path/'analysis')))
    with pytest.raises(ValueError,match='基础周期'):service.get('002475',KlinePeriod.DAILY,KlinePeriod.DAILY)


def test_layers_are_built_from_previous_layer_and_point_ids_are_namespaced(tmp_path):
    from app.models.schemas import Segment,RuleSettings
    children,bars,indicators=fixture(VALUES)
    charts=ChartService(CsvStore(tmp_path/'raw',tmp_path/'analysis'))
    base=charts._build('TEST',KlinePeriod.MINUTE_5,bars,RuleSettings(),persist=False)
    base.indicators=indicators
    base.segments=[Segment(startTime=m.start_time,endTime=m.end_time,startPrice=m.start_price,endPrice=m.end_price,
        direction=m.direction,startBiIndex=0,endBiIndex=0,biCount=3,confirmed=m.confirmed,breakType='NO_GAP',
        confirmedAt=m.observed_at,momentum=m.momentum) for m in children]
    base.bis=[]
    result=RecursiveAnalyzer().analyze(base,RuleSettings(),4)
    assert any(layer.trading_points for layer in result.layers)
    assert len(result.layers)==2
    assert result.layers[0].level==0 and result.layers[1].level==1
    assert result.layers[1].movements[0].confirmed
    previous_ids={m.id for m in result.layers[0].movements}
    assert all(set(m.child_ids+m.confirmation_ids)<=previous_ids for m in result.layers[1].movements)
    for layer in result.layers:
        ids={m.id for m in layer.movements}
        for point in layer.trading_points:
            assert point.unit_id in ids and point.structural_level==layer.level
            assert point.id.startswith(f'L{layer.level}:')
            if point.divergence_id: assert point.divergence_id in {d.id for d in layer.divergences}
            if point.parent_id: assert point.parent_id in {p.id for p in layer.trading_points}


def test_trading_calendar_gap_stops_recursion_but_exchange_holiday_does_not(tmp_path):
    from datetime import datetime
    store=CsvStore(tmp_path/'raw',tmp_path/'analysis')
    charts=ChartService(store)
    base=[Kline(time=datetime(2024,2,d,15),open=10,high=10,low=10,close=10) for d in (8,19)]
    store.upsert_klines('002475.SZ',KlinePeriod.MINUTE_5,base)
    daily=[Kline(time=date(2024,2,d),open=10,high=10,low=10,close=10) for d in (8,19)]
    store.upsert_klines('002475.SZ',KlinePeriod.DAILY,daily)
    service=HierarchyService(charts)
    view=service.get('002475',KlinePeriod.DAILY)
    assert not any('缺少' in w for w in view.hierarchy.warnings)
    store.upsert_klines('002475.SZ',KlinePeriod.DAILY,[Kline(time=date(2024,2,9),open=10,high=10,low=10,close=10)])
    view=service.get('002475',KlinePeriod.DAILY)
    assert not view.hierarchy.layers and not view.trading_points
    assert any('缺少1个交易日' in w for w in view.hierarchy.warnings)
