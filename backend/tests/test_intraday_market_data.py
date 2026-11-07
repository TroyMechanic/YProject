from datetime import datetime
from pathlib import Path

from app.models.schemas import Kline, KlinePeriod
from app.services.csv_store import CsvStore
from app.services.market_data_service import INTRADAY_LOOKBACK_DAYS, MarketDataService


def make_intraday(time: str, open_price: float, high: float, low: float, close: float, volume: float) -> Kline:
    return Kline(
        time=datetime.fromisoformat(time),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


def test_parse_tencent_minute_kline_preserves_datetime() -> None:
    item = MarketDataService._parse_tencent_minute_kline(
        ["202608281030", "57.10", "57.20", "57.50", "56.90", "1234", {}, "0.2"]
    )

    assert item.time == datetime(2026, 8, 28, 10, 30)
    assert item.open == 57.10
    assert item.high == 57.50
    assert item.low == 56.90
    assert item.close == 57.20
    assert item.volume == 123400


def test_five_minute_source_preserves_share_volume_and_filters_dates(monkeypatch):
    from datetime import date
    import requests
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return [{'day': f'2026-09-{d:02d} 10:00:00', 'open':'10', 'high':'12',
                     'low':'9', 'close':'11', 'volume':'1234', 'amount':'13574'} for d in (1,2,3)]
    calls=[]
    def get(url,**kwargs):
        calls.append((url,kwargs)); return Response()
    monkeypatch.setattr(requests,'get',get)
    rows=MarketDataService().fetch('002475.SZ',KlinePeriod.MINUTE_5,date(2026,9,2),date(2026,9,2))
    assert len(rows)==1 and rows[0].time==datetime(2026,9,2,10)
    assert rows[0].volume==1234 and rows[0].amount==13574
    assert calls[0][1]['params']['datalen']==1023
    assert calls[0][1]['params']['symbol']=='sz002475'


def test_four_hour_period_aggregates_one_a_share_trading_day() -> None:
    rows = [
        make_intraday("2026-08-28T10:30:00", 10, 12, 9, 11, 100),
        make_intraday("2026-08-28T11:30:00", 11, 13, 10, 12, 200),
        make_intraday("2026-08-28T14:00:00", 12, 14, 8, 9, 300),
        make_intraday("2026-08-28T15:00:00", 9, 15, 7, 14, 400),
    ]

    result = MarketDataService._aggregate_trading_days(rows)

    assert len(result) == 1
    assert result[0].time == datetime(2026, 8, 28, 15, 0)
    assert result[0].open == 10
    assert result[0].high == 15
    assert result[0].low == 7
    assert result[0].close == 14
    assert result[0].volume == 1000


def test_four_hour_default_range_is_longer_than_minute_periods() -> None:
    assert INTRADAY_LOOKBACK_DAYS[KlinePeriod.HOUR_4] == 120
    assert INTRADAY_LOOKBACK_DAYS[KlinePeriod.MINUTE_60] == 10
    assert INTRADAY_LOOKBACK_DAYS[KlinePeriod.MINUTE_30] == 10
    assert INTRADAY_LOOKBACK_DAYS[KlinePeriod.MINUTE_1] == 10


def test_four_hour_upsert_replaces_incomplete_bar_for_same_trading_day(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = CsvStore()
    path = tmp_path / "hour4.csv"
    monkeypatch.setattr(store, "_kline_path", lambda _symbol, _period: path)

    store.upsert_klines(
        "002475.SZ",
        KlinePeriod.HOUR_4,
        [make_intraday("2026-08-28T11:30:00", 10, 12, 9, 11, 100)],
    )
    store.upsert_klines(
        "002475.SZ",
        KlinePeriod.HOUR_4,
        [make_intraday("2026-08-28T15:00:00", 10, 14, 8, 13, 300)],
    )

    rows = store.load_klines("002475.SZ", KlinePeriod.HOUR_4)
    assert len(rows) == 1
    assert rows[0].time == datetime(2026, 8, 28, 15, 0)
    assert rows[0].close == 13
