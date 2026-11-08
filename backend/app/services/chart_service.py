from __future__ import annotations

from collections import defaultdict
import json
import re
from datetime import date, datetime, timezone
from threading import RLock
from uuid import uuid4

from app.models.schemas import MacdPoint, AnalysisMetadata, ChartResponse, Kline, KlinePeriod, RuleProfile, RuleSettings
from app.services.chan_analyzer import ChanAnalyzer
from app.services.csv_store import CsvStore
from app.services.market_data_service import MarketDataService
from app.services.rule_policy import PRINCIPLES, RULE_VERSION, digest, effective_gap, engine_hash, input_hash, rule_catalog, rule_hash
from app.services.stock_info import normalize_stock_symbol, resolve_stock_name

_LOCKS: dict[tuple[str, str, str], RLock] = defaultdict(RLock)


class AnalysisStateError(ValueError):
    """An unreadable result must never be silently relabelled with default rules."""


def calculate_macd(klines: list[Kline]) -> list[MacdPoint]:
    if not klines:
        return []
    fast = slow = klines[0].close
    dea = 0.0
    points = []
    for bar in klines:
        fast += (bar.close - fast) * (2 / 13)
        slow += (bar.close - slow) * (2 / 27)
        dif = fast - slow
        dea += (dif - dea) * (2 / 10)
        points.append(MacdPoint(time=bar.time, dif=dif, dea=dea, histogram=2 * (dif - dea)))
    return points


class ChartService:
    def __init__(self, store: CsvStore | None = None) -> None:
        self.store = store or CsvStore()
        self.market_data = MarketDataService()
        self.analyzer = ChanAnalyzer()

    def _lock(self, symbol: str, period: KlinePeriod):
        return _LOCKS[(str(self.store.analyzed_dir.resolve()), symbol, period.value)]

    def _committed(self, symbol: str, period: KlinePeriod) -> ChartResponse | None:
        try:
            payload = self.store.load_analysis_payload(symbol, period)
            if payload is None:
                return None
            raw_settings = payload["analysis"]["settings"]
            # Older snapshots include retired settings in their signed rule hash.
            current_settings = {field.alias: raw_settings[field.alias] for field in RuleSettings.model_fields.values()
                                if field.alias in raw_settings}
            migrated = {**payload, "analysis": {**payload["analysis"], "settings": current_settings}}
            chart = ChartResponse.model_validate_json(json.dumps(migrated))
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            raise AnalysisStateError("分析快照损坏或版本不兼容；请检查备份后恢复，不能猜测原规则") from error
        if chart is not None:
            if chart.symbol != symbol or chart.period != period or chart.analysis is None:
                raise AnalysisStateError("分析快照身份或溯源信息不完整")
            # Validate the original serialized shape before migration defaults are inserted.
            if chart.analysis.result_hash != digest({k:v for k,v in payload.items() if k != 'analysis'}):
                raise AnalysisStateError("分析快照内容校验失败；请恢复备份")
            metadata = chart.analysis
            recorded_settings = {re.sub(r"(?<!^)(?=[A-Z])", "_", key).lower(): value
                                 for key, value in raw_settings.items()}
            recorded_rule_hash = digest({"catalog": metadata.rule_catalog,
                                         "settings": recorded_settings,
                                         "gap": metadata.effective_min_kline_gap})
            if (metadata.rule_hash != recorded_rule_hash or metadata.input_hash != digest(payload["klines"])
                    or metadata.source_count != len(chart.klines)
                    or metadata.rule_version != metadata.rule_catalog.get("version")
                    or metadata.principle_ids != [item["id"] for item in metadata.rule_catalog.get("principles", [])]):
                raise AnalysisStateError("分析快照规则或输入溯源校验失败；请恢复备份")
        return chart

    @staticmethod
    def _settings(previous: ChartResponse | None, profile: RuleProfile | None, gap: int | None) -> RuleSettings:
        saved = previous.analysis.settings if previous and previous.analysis else RuleSettings()
        values=saved.model_dump()
        values.update(rule_profile=profile if profile is not None else saved.rule_profile,
                      min_kline_gap=gap if gap is not None else saved.min_kline_gap)
        return RuleSettings(**values)

    def sync(self, symbol: str, period: KlinePeriod, start_date: date | None, end_date: date | None,
             rule_profile: RuleProfile | None = None, min_kline_gap: int | None = None) -> int:
        symbol = normalize_stock_symbol(symbol)
        klines = self.market_data.fetch(symbol, period, start_date, end_date)
        if not klines:
            return 0
        with self._lock(symbol, period):
            settings = self._settings(self._committed(symbol, period), rule_profile, min_kline_gap)
            rows = self.store.upsert_klines(symbol, period, klines)
            self._build(symbol, period, self.store.load_klines(symbol, period), settings)
            return rows

    def sync_daily(self, symbol: str, start_date: date | None, end_date: date | None) -> int:
        return self.sync(symbol, KlinePeriod.DAILY, start_date, end_date)

    def _build(self, symbol: str, period: KlinePeriod, klines: list[Kline], settings: RuleSettings,
               persist: bool = True) -> ChartResponse:
        fractals, bis, segments = self.analyzer.analyze(klines, effective_gap(settings))
        chart = ChartResponse(symbol=symbol, name=resolve_stock_name(symbol), period=period,
                              klines=klines, macd=calculate_macd(klines), fractals=fractals, bis=bis, segments=segments)
        chart.analysis = AnalysisMetadata(
            runId=str(uuid4()), generatedAt=datetime.now(timezone.utc), ruleVersion=RULE_VERSION,
            settings=settings, effectiveMinKlineGap=effective_gap(settings), inputHash=input_hash(klines),
            engineHash=engine_hash(), ruleHash=rule_hash(settings),
            resultHash=digest(chart.model_dump(mode="json", by_alias=True, exclude={"analysis"})),
            sourceCount=len(klines), sourceStart=klines[0].time if klines else None,
            sourceEnd=klines[-1].time if klines else None, principleIds=list(PRINCIPLES), ruleCatalog=rule_catalog(),
        )
        if persist:
            self.store.save_analysis(chart)
        return chart

    def get_chart(self, symbol: str, period: KlinePeriod, start_date: date | None, end_date: date | None) -> ChartResponse:
        symbol = normalize_stock_symbol(symbol)
        with self._lock(symbol, period):
            klines = self.store.load_klines(symbol, period)
            chart = self._committed(symbol, period)
            settings = self._settings(chart, None, None)
            if (chart is None or chart.analysis.input_hash != input_hash(klines)
                    or chart.analysis.engine_hash != engine_hash()
                    or chart.analysis.rule_hash != rule_hash(settings)):
                # Legacy exports have no trustworthy parameter history; rebuild with labelled defaults.
                chart = self._build(symbol, period, klines, settings, persist=bool(klines) or chart is not None)
            return self._visible(chart, start_date, end_date)

    def recalculate(self, symbol: str, period: KlinePeriod, min_kline_gap: int | None = None,
                    rule_profile: RuleProfile | None = None) -> ChartResponse:
        symbol = normalize_stock_symbol(symbol)
        with self._lock(symbol, period):
            settings = self._settings(self._committed(symbol, period), rule_profile, min_kline_gap)
            return self._build(symbol, period, self.store.load_klines(symbol, period), settings)

    @staticmethod
    def _visible(chart: ChartResponse, start: date | None, end: date | None) -> ChartResponse:
        def day(value):
            return value.date() if isinstance(value, datetime) else value

        def intersects(left, right):
            return (start is None or day(right) >= start) and (end is None or day(left) <= end)

        return chart.model_copy(update={
            "klines": [item for item in chart.klines if intersects(item.time, item.time)],
            "macd": [item for item in chart.macd if intersects(item.time, item.time)],
            "fractals": [item for item in chart.fractals if intersects(item.time, item.time)],
            "bis": [item for item in chart.bis if intersects(item.start_time, item.end_time)],
            "segments": [item for item in chart.segments if intersects(item.start_time, item.end_time)],
        })
