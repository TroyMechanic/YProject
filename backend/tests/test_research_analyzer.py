from datetime import date, timedelta

import pytest

from app.models.schemas import (BiDirection, ChartResponse, Divergence, Fractal, FractalElement, IndicatorPoint,
                                Kline, KlinePeriod, Momentum, RuleSettings, SignalLevel)
from app.services.research_analyzer import ResearchAnalyzer, Unit, macd, relation, zones_for


def make_units(points, areas=None):
    result=[]
    for i,(start,end) in enumerate(zip(points,points[1:])):
        metric=Momentum(barCount=5,amplitudePercent=abs(end-start),velocity=1,macdArea=(areas or {}).get(i,10),
                        macdPeak=2,volumeSum=100,warmupComplete=True)
        result.append(Unit(i,date(2024,1,1)+timedelta(days=i),date(2024,1,2)+timedelta(days=i),start,end,
                           i,i+1,BiDirection.UP if end>start else BiDirection.DOWN,True,
                           date(2024,1,4)+timedelta(days=i),metric))
    return result


def test_macd_fixed_input_ema_and_warmup_are_hand_checked():
    settings=RuleSettings(macdFast=2,macdSlow=3,macdSignal=2)
    source=[Kline(time=date(2024,1,1)+timedelta(days=i),open=v,high=v,low=v,close=v) for i,v in enumerate([10,12,14]+[14]*7)]
    indicator=macd(source,settings)
    assert indicator[0].dif==indicator[0].dea==indicator[0].histogram==0
    assert indicator[1].dif==pytest.approx(1/3)
    assert indicator[1].dea==pytest.approx(2/9)
    assert indicator[1].histogram==pytest.approx(2/9)
    assert not indicator[7].ready and indicator[8].ready


@pytest.mark.parametrize('mirror,expected',[(False,'B3'),(True,'S3')])
def test_third_point_needs_leave_and_completed_retest(mirror,expected):
    values=[1,10,5,12,7,16,11,18]
    if mirror: values=[30-v for v in values]
    units=make_units(values)
    zones=zones_for(units,SignalLevel.BI)
    points=ResearchAnalyzer().points(units,zones,[],RuleSettings())
    assert len(points)==1
    point=points[0]
    assert point.type==expected and point.unit_index==5
    assert point.confirmed and point.observed_at==units[5].observed_at
    assert point.observed_at>point.time


@pytest.mark.parametrize('retest',[10,9])
def test_retest_touching_or_entering_zone_is_not_third_buy(retest):
    units=make_units([1,10,5,12,7,16,retest])
    assert ResearchAnalyzer().points(units,zones_for(units,SignalLevel.BI),[],RuleSettings())==[]


def test_breakout_alone_has_no_third_point_and_unfinished_retest_is_candidate():
    units=make_units([1,10,5,12,7,16])
    assert not ResearchAnalyzer().points(units,zones_for(units,SignalLevel.BI),[],RuleSettings())
    units=make_units([1,10,5,12,7,16,11])
    units[-1].confirmed=False
    points=ResearchAnalyzer().points(units,zones_for(units,SignalLevel.BI),[],RuleSettings())
    assert len(points)==1 and points[0].type=='B3' and not points[0].confirmed


def test_first_and_second_points_require_trend_divergence_and_first_retest():
    units=make_units([20,10,16,12,18,13,19])
    divergence=Divergence(id='trend-div',level='bi',direction='DOWN',type='TREND',time=units[0].end_time,
                          observedAt=units[0].observed_at,confirmed=True,previousUnitIndex=0,currentUnitIndex=0,
                          previousArea=10,currentArea=5,ratio=.5,zoneIds=['earlier','current'],reasons=['fixture'])
    points=ResearchAnalyzer().points(units,[],[divergence],RuleSettings())
    assert [p.type for p in points]==['B1','B2']
    assert points[1].unit_index==2 and points[1].parent_id==points[0].id
    assert points[1].invalidation_price==10
    divergence.type='CONSOLIDATION'
    assert ResearchAnalyzer().points(units,[],[divergence],RuleSettings())==[]


@pytest.mark.parametrize('low',[10,9])
def test_second_buy_cannot_touch_or_break_first_low(low):
    units=make_units([20,10,16,low,18])
    divergence=Divergence(id='d',level='bi',direction='DOWN',type='TREND',time=units[0].end_time,
                          observedAt=units[0].observed_at,confirmed=True,previousUnitIndex=0,currentUnitIndex=0,
                          previousArea=10,currentArea=5,ratio=.5,zoneIds=['a','b'],reasons=[])
    assert [p.type for p in ResearchAnalyzer().points(units,[],[divergence],RuleSettings())]==['B1']


def test_repeated_retests_do_not_duplicate_third_point():
    units=make_units([1,10,5,12,7,16,11,18,12,20])
    points=ResearchAnalyzer().points(units,zones_for(units,SignalLevel.BI),[],RuleSettings())
    assert len([p for p in points if p.type=='B3'])==1


def test_divergence_requires_new_price_extreme_area_decay_and_warmup():
    units=make_units([10,20,15,22],{0:10,2:5})
    indicators=[IndicatorPoint(time=date(2024,1,1)+timedelta(days=i),dif=0,dea=0,histogram=0,ready=True) for i in range(4)]
    klines=[Kline(time=p.time,open=10,high=10,low=10,close=10) for p in indicators]
    result=ResearchAnalyzer().divergences(units,indicators,klines,RuleSettings())
    assert len(result)==1 and result[0].type=='LOCAL' and result[0].ratio==.5
    units[2].end_price=20
    assert not ResearchAnalyzer().divergences(units,indicators,klines,RuleSettings())
    units[2].end_price=22
    units[2].momentum.warmup_complete=False
    assert not ResearchAnalyzer().divergences(units,indicators,klines,RuleSettings())


@pytest.mark.parametrize('right_high,right_low,right_close,grade',[(10,4,4,'STRONG'),(10,4,8,'NORMAL'),(10,6,8,'WEAK')])
def test_top_fractal_strength_has_three_distinct_grades(right_high,right_low,right_close,grade):
    ranges=[(10,5,8),(12,7,10),(right_high,right_low,right_close)]
    klines=[Kline(time=date(2024,1,1)+timedelta(days=i),open=low,high=high,low=low,close=close) for i,(high,low,close) in enumerate(ranges)]
    elements=[FractalElement(time=k.time,klineIndex=i,high=k.high,low=k.low) for i,k in enumerate(klines)]
    chart=ChartResponse(symbol='TEST',period=KlinePeriod.DAILY,klines=klines,fractals=[Fractal(time=klines[1].time,type='TOP',price=12,klineIndex=1,elements=elements)],bis=[])
    ResearchAnalyzer().enrich(chart,RuleSettings())
    assert chart.fractals[0].strength.grade==grade


def test_zone_relationship_strict_separation_and_contact():
    a=zones_for(make_units([1,10,5,12]),SignalLevel.BI)[0]
    b=a.model_copy(update={'id':'b','zd':15,'zg':18,'dd':13,'gg':20})
    assert relation(a,b)=='TREND_UP'
    b.dd=12
    assert relation(a,b)=='EXPANSION'
    b.zd=8;b.zg=11
    assert relation(a,b)=='CORE_OVERLAP'


@pytest.mark.parametrize('mirror,first,second',[(False,'S1','S2'),(True,'B1','B2')])
def test_actual_two_zone_trend_divergence_produces_first_and_second(mirror,first,second):
    values=[100,92,108,92,104,86,95,77,85,75,78,75,89,73,78,71,81,71,75,59,75,58,62,49,67,61,75,72,79,74,80,76,79]
    if mirror: values=[200-v for v in values]
    units=make_units(values,{i:20 if i<27 else 5 for i in range(32)})
    indicators=[IndicatorPoint(time=date(2024,1,1)+timedelta(days=i),dif=0,dea=0,histogram=0,ready=True) for i in range(len(values))]
    klines=[Kline(time=p.time,open=100,high=100,low=100,close=100) for p in indicators]
    analyzer=ResearchAnalyzer()
    divergences=analyzer.divergences(units,indicators,klines,RuleSettings())
    found=next(d for d in divergences if d.current_unit_index==29)
    assert found.type=='TREND' and found.previous_unit_index==25 and found.ratio==.25
    points=analyzer.points(units,zones_for(units,SignalLevel.BI),divergences,RuleSettings())
    one=next(p for p in points if p.type==first and p.unit_index==29)
    two=next(p for p in points if p.type==second and p.unit_index==31)
    assert one.confirmed and two.confirmed and two.parent_id==one.id
    assert two.observed_at>=one.observed_at>one.time
    for p in indicators: p.dif=p.dea=100
    assert all(d.type=='LOCAL' for d in analyzer.divergences(units,indicators,klines,RuleSettings()))


def test_zone_departure_confirmation_is_recorded_and_bridge_excluded():
    units=make_units([1,10,5,12,7,16,11,18])
    zone=zones_for(units,SignalLevel.BI)[0]
    assert zone.departure_unit_index==4
    assert zone.member_indices==[0,1,2,3]
    assert zone.gg==12 and zone.zg==10
    assert zone.closed_at==units[5].observed_at>zone.formed_at


def test_confirmed_points_survive_incremental_append():
    import random
    analyzer=ResearchAnalyzer()
    for seed in range(20):
        rng=random.Random(seed)
        values=[100]
        for i in range(60): values.append(values[-1]+(1 if i%2==0 else -1)*rng.randint(2,20))
        units=make_units(values,{i:rng.randint(1,20) for i in range(60)})
        indicators=[IndicatorPoint(time=date(2024,1,1)+timedelta(days=i),dif=0,dea=0,histogram=0,ready=True) for i in range(61)]
        bars=[Kline(time=p.time,open=100,high=100,low=100,close=100) for p in indicators]
        previous={}
        for count in range(4,61):
            prefix=units[:count]
            divergences=analyzer.divergences(prefix,indicators,bars,RuleSettings())
            points=analyzer.points(prefix,zones_for(prefix,SignalLevel.BI),divergences,RuleSettings())
            current={p.id:p.model_dump() for p in points if p.confirmed}
            assert all(current.get(key)==value for key,value in previous.items()), (seed,count)
            previous=current


@pytest.mark.parametrize('settings',[{'macdFast':26,'macdSlow':12},{'signalLevel':'fake'},{'divergenceRatio':1}, {'zeroAxisTolerance':0}])
def test_research_invalid_parameters_rejected(settings):
    from pydantic import ValidationError
    with pytest.raises(ValidationError): RuleSettings(**settings)


def test_complete_analysis_confirmed_points_stable_on_appended_raw_bars():
    import random
    from app.services.chan_analyzer import ChanAnalyzer
    settings=RuleSettings(macdFast=2,macdSlow=3,macdSignal=2)
    for seed in range(5):
        rng=random.Random(seed)
        prices=[rng.randint(30,90) for _ in range(95)]
        bars=[Kline(time=date(2024,1,1)+timedelta(days=i),open=v,high=v+2,low=v-2,close=v) for i,v in enumerate(prices)]
        previous={}
        for count in range(10,len(bars)+1):
            fractals,bis,segments,zones=ChanAnalyzer().analyze(bars[:count])
            chart=ChartResponse(symbol='TEST',period='daily',klines=bars[:count],fractals=fractals,bis=bis,segments=segments,centralZones=zones)
            ResearchAnalyzer().enrich(chart,settings)
            current={p.id:p.model_dump() for p in chart.trading_points if p.confirmed}
            assert all(current.get(key)==value for key,value in previous.items()),(seed,count)
            assert all(p.observed_at<=bars[count-1].time for p in chart.trading_points)
            previous=current
