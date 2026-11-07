"""One immutable view snapshot containing display and base inputs plus recursion."""
import json
from datetime import datetime, timedelta, timezone
from threading import RLock
from uuid import uuid4

from app.models.schemas import ChartResponse, KlinePeriod
from app.services.chart_service import AnalysisStateError, ChartService
from app.services.csv_store import safe_symbol
from app.services.recursive_analyzer import RecursiveAnalyzer
from app.services.rule_policy import digest
from app.services.stock_info import normalize_stock_symbol

_LOCK=RLock()


def map_time(time,bars,period):
    if not bars: return None
    day=time.date() if isinstance(time,datetime) else time
    if period==KlinePeriod.DAILY:
        return next((b.time for b in bars if (b.time.date() if isinstance(b.time,datetime) else b.time)==day),None)
    if period in (KlinePeriod.WEEKLY,KlinePeriod.MONTHLY):
        # Map to the displayed candle's calendar bucket; retain original times.
        bucket=lambda t:(t.year,t.month) if period==KlinePeriod.MONTHLY else t.isocalendar()[:2]
        return next((b.time for b in bars if bucket(b.time)==bucket(time)),None)
    candidates=[b.time for b in bars if (b.time.date() if isinstance(b.time,datetime) else b.time)==day and b.time>=time]
    if not candidates:
        return None
    candidate=candidates[0]
    minutes={KlinePeriod.MINUTE_1:1,KlinePeriod.MINUTE_5:5,
             KlinePeriod.MINUTE_30:30,KlinePeriod.MINUTE_60:60}.get(period)
    # Intraday bars are stamped at interval end. Never snap a point across a
    # missing interval merely because a later candle exists on the same day.
    if minutes is not None and candidate-time >= timedelta(minutes=minutes):
        return None
    return candidate


class HierarchyService:
    def __init__(self, charts=None):
        self.charts=charts or ChartService()

    def path(self,symbol,display):
        return self.charts.store.analyzed_dir/f'{safe_symbol(symbol)}_{display.value}_hierarchy.json'

    def saved(self,symbol,display):
        path=self.path(symbol,display)
        if not path.exists(): return None
        try:
            payload=json.loads(path.read_text())
            chart=ChartResponse.model_validate_json(json.dumps(payload))
            if chart.symbol!=symbol or chart.period!=display or not chart.hierarchy or not chart.analysis:
                raise ValueError('identity')
            if digest({k:v for k,v in payload.items() if k!='analysis'})!=chart.analysis.result_hash:
                raise ValueError('checksum')
            if (digest(payload['klines'])!=chart.analysis.input_hash
                    or digest(payload['hierarchy']['baseKlines'])!=chart.hierarchy.base_analysis.input_hash
                    or len(chart.hierarchy.base_klines)!=chart.hierarchy.base_analysis.source_count):
                raise ValueError('source checksum')
            return chart
        except (ValueError,TypeError) as error:
            raise AnalysisStateError('递归快照校验失败；请检查备份后恢复') from error

    def get(self,symbol,display,base_period=None,max_level=None,start=None,end=None):
        symbol=normalize_stock_symbol(symbol)
        with _LOCK:
            saved=self.saved(symbol,display)
            base_period=base_period or (saved.hierarchy.base_period if saved else KlinePeriod.MINUTE_5)
            max_level=max_level if max_level is not None else (saved.hierarchy.max_level if saved else 4)
            if base_period not in (KlinePeriod.MINUTE_1,KlinePeriod.MINUTE_5,KlinePeriod.MINUTE_30,KlinePeriod.MINUTE_60):
                raise ValueError('递归基础周期限1m/5m/30m/60m，不能用高周期补造低周期')
            if not 1<=max_level<=8: raise ValueError('最大递归层必须在1至8之间')
            background=self.charts.get_chart(symbol,display,None,None)
            base=self.charts.get_chart(symbol,base_period,None,None)
            fingerprint=lambda c:(c.analysis.input_hash,c.analysis.engine_hash,c.analysis.rule_hash)
            if (saved and saved.hierarchy.base_period==base_period and saved.hierarchy.max_level==max_level
                    and fingerprint(saved)==fingerprint(background)
                    and (saved.hierarchy.base_analysis.input_hash,saved.hierarchy.base_analysis.engine_hash,
                         saved.hierarchy.base_analysis.rule_hash)==fingerprint(base)):
                return self.visible(saved,start,end)
            chart=background.model_copy(deep=True)
            chart.hierarchy=RecursiveAnalyzer().analyze(base,base.analysis.settings,max_level)
            # Use actual daily candles as the trading calendar, not weekdays: long
            # exchange holidays must not be mistaken for missing observations.
            dates=sorted({b.time.date() if isinstance(b.time,datetime) else b.time for b in base.klines})
            expected={b.time.date() if isinstance(b.time,datetime) else b.time for b in background.klines} if display==KlinePeriod.DAILY else set()
            missing={d for d in expected if dates and dates[0]<d<dates[-1]}-set(dates)
            if missing:
                chart.hierarchy.layers=[]
                chart.hierarchy.base_trading_points=[]
                chart.hierarchy.base_signal_zones=[]
                chart.hierarchy.base_divergences=[]
                chart.hierarchy.warnings.append(f'按日K交易日核对，基础历史缺少{len(missing)}个交易日；停止递归，请补齐或选择连续数据。')
            if display!=KlinePeriod.DAILY:
                chart.hierarchy.warnings.append('当前展示周期不是日K，尚未用逐日交易日历核对分钟历史完整性。')
            if not base.klines: chart.hierarchy.warnings.append('基础周期没有本地行情，请同步基础数据；不回退到日K推算。')
            chart.trading_points=[]
            for layer in chart.hierarchy.layers:
                for point in layer.trading_points:
                    point.display_time=map_time(point.observed_at,chart.klines,display)
                    point.display_endpoint_time=map_time(point.time,chart.klines,display)
                    chart.trading_points.append(point)
            chart.trading_points.sort(key=lambda p:(p.observed_at,p.structural_level,p.type))
            for point in chart.hierarchy.base_trading_points:
                point.display_time=map_time(point.observed_at,chart.klines,display)
                point.display_endpoint_time=map_time(point.time,chart.klines,display)
            chart.signal_zones=[]
            chart.divergences=[]  # Layer-specific context lives under hierarchy.layers.
            chart.zone_relations=[]
            chart.analysis=background.analysis.model_copy(update={'run_id':str(uuid4()),'generated_at':datetime.now(timezone.utc)})
            chart.analysis.result_hash=digest(chart.model_dump(mode='json',by_alias=True,exclude={'analysis'}))
            payload=chart.model_dump_json(by_alias=True,indent=2)
            archive=self.charts.store.analyzed_dir/'runs'/f'{safe_symbol(symbol)}_{display.value}_hierarchy'
            archive.mkdir(parents=True,exist_ok=True)
            self.charts.store._atomic_text(archive/f'{chart.analysis.run_id}.json',payload)
            self.charts.store._atomic_text(self.path(symbol,display),payload)
            return self.visible(chart,start,end)

    def operate(self,symbol,request,sync=False):
        symbol=normalize_stock_symbol(symbol)
        from app.api.routes import research_options
        with _LOCK:
            saved=self.saved(symbol,request.period)
            base=request.base_period or (saved.hierarchy.base_period if saved else KlinePeriod.MINUTE_5)
            if base not in (KlinePeriod.MINUTE_1,KlinePeriod.MINUTE_5,KlinePeriod.MINUTE_30,KlinePeriod.MINUTE_60):
                raise ValueError('递归基础周期限1m/5m/30m/60m')
            if sync:
                count=self.charts.sync(symbol,base,None,request.end_date,request.rule_profile,request.min_kline_gap,**research_options(request))
                if not count: raise ValueError('行情源没有返回基础周期数据；保留原结果')
                if base!=request.period:
                    self.charts.sync(symbol,request.period,request.start_date,request.end_date)
            else:
                self.charts.recalculate(symbol,base,request.min_kline_gap,request.rule_profile,**research_options(request))
            return self.get(symbol,request.period,base,request.max_level,request.start_date,request.end_date)

    @staticmethod
    def visible(chart,start,end):
        view=ChartService._visible(chart,start,end)
        if chart.hierarchy:
            observations=ChartService._visible(chart.model_copy(update={'trading_points':chart.hierarchy.base_trading_points}),start,end)
            view.hierarchy=chart.hierarchy.model_copy(update={'base_trading_points':observations.trading_points})
        # Full lower-level evidence is deliberately retained for child-ID drilldown.
        return view
