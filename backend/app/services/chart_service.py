from __future__ import annotations

from datetime import date

from app.models.schemas import ChartResponse, Kline, KlinePeriod
from app.services.chan_analyzer import ChanAnalyzer
from app.services.csv_store import CsvStore
from app.services.market_data_service import MarketDataService
from app.services.stock_info import normalize_stock_symbol, resolve_stock_name


class ChartService:
    def __init__(self) -> None:
        self.store = CsvStore()
        self.market_data = MarketDataService()
        self.analyzer = ChanAnalyzer()

    def sync(
        self,
        symbol: str,
        period: KlinePeriod,
        start_date: date | None,
        end_date: date | None,
    ) -> int:
        normalized_symbol = normalize_stock_symbol(symbol)
        klines = self.market_data.fetch(normalized_symbol, period, start_date, end_date)
        total_rows = self.store.upsert_klines(normalized_symbol, period, klines)
        all_klines = self.store.load_klines(normalized_symbol, period)
        self.recalculate(normalized_symbol, period, all_klines, min_kline_gap=1)
        return total_rows

    def sync_daily(self, symbol: str, start_date: date | None, end_date: date | None) -> int:
        return self.sync(symbol, KlinePeriod.DAILY, start_date, end_date)

    def get_chart(
        self,
        symbol: str,
        period: KlinePeriod,
        start_date: date | None,
        end_date: date | None,
    ) -> ChartResponse:
        normalized_symbol = normalize_stock_symbol(symbol)
        klines = self.store.load_klines(normalized_symbol, period, start_date, end_date)
        fractals = self.store.load_fractals(normalized_symbol, period, start_date, end_date)
        bis = self.store.load_bis(normalized_symbol, period, start_date, end_date)
        segments = self.store.load_segments(normalized_symbol, period, start_date, end_date)
        central_zones = self.store.load_central_zones(normalized_symbol, period, start_date, end_date)
        return ChartResponse(
            symbol=normalized_symbol,
            name=resolve_stock_name(normalized_symbol),
            period=period,
            klines=klines,
            fractals=fractals,
            bis=bis,
            segments=segments,
            centralZones=central_zones,
        )

    def recalculate(
        self,
        symbol: str,
        period: KlinePeriod,
        klines: list[Kline] | None = None,
        min_kline_gap: int = 1,
    ) -> tuple[int, int, int, int]:
        normalized_symbol = normalize_stock_symbol(symbol)
        source_klines = klines if klines is not None else self.store.load_klines(normalized_symbol, period)
        fractals, bis, segments, central_zones = self.analyzer.analyze(source_klines, min_kline_gap)
        self.store.save_fractals(normalized_symbol, period, fractals)
        self.store.save_bis(normalized_symbol, period, bis)
        self.store.save_segments(normalized_symbol, period, segments)
        self.store.save_central_zones(normalized_symbol, period, central_zones)
        return len(fractals), len(bis), len(segments), len(central_zones)
