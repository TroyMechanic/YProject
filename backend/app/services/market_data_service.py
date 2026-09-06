from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import requests
import yfinance as yf

from app.models.schemas import Kline, KlinePeriod


YAHOO_INTERVALS = {
    KlinePeriod.DAILY: "1d",
    KlinePeriod.WEEKLY: "1wk",
    KlinePeriod.MONTHLY: "1mo",
}

TENCENT_PERIOD_KEYS = {
    KlinePeriod.DAILY: "day",
    KlinePeriod.WEEKLY: "week",
    KlinePeriod.MONTHLY: "month",
}

TENCENT_MINUTE_KEYS = {
    KlinePeriod.MINUTE_1: "m1",
    KlinePeriod.MINUTE_30: "m30",
    KlinePeriod.MINUTE_60: "m60",
}

INTRADAY_LOOKBACK_DAYS = {
    KlinePeriod.HOUR_4: 120,
    KlinePeriod.MINUTE_60: 10,
    KlinePeriod.MINUTE_30: 10,
    KlinePeriod.MINUTE_1: 10,
}


def is_intraday_period(period: KlinePeriod) -> bool:
    return period in {
        KlinePeriod.HOUR_4,
        KlinePeriod.MINUTE_60,
        KlinePeriod.MINUTE_30,
        KlinePeriod.MINUTE_1,
    }


def normalize_yahoo_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if normalized.endswith(".SH"):
        return normalized[:-3] + ".SS"
    return normalized


def is_a_share_symbol(symbol: str) -> bool:
    return symbol.endswith((".SZ", ".SH", ".BJ"))


def normalize_tencent_symbol(symbol: str) -> str:
    code, market = symbol.split(".", maxsplit=1)
    return f"{market.lower()}{code}"


class MarketDataService:
    def fetch(
        self,
        symbol: str,
        period: KlinePeriod = KlinePeriod.DAILY,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Kline]:
        if symbol.strip().upper() == "DEMO":
            return self._demo(start_date, end_date, period)

        normalized_symbol = symbol.strip().upper()
        if is_intraday_period(period):
            if not is_a_share_symbol(normalized_symbol):
                return []
            return self._fetch_tencent_intraday(normalized_symbol, period, start_date, end_date)

        if is_a_share_symbol(normalized_symbol):
            try:
                rows = self._fetch_tencent_a_share(normalized_symbol, period, start_date, end_date)
                if rows:
                    return rows
            except Exception:
                pass

        source_symbol = normalize_yahoo_symbol(normalized_symbol)
        start = start_date or date.today() - timedelta(days=365 * 3)
        end = (end_date or date.today()) + timedelta(days=1)
        interval = YAHOO_INTERVALS[period]

        try:
            frame = yf.download(
                source_symbol,
                start=start.isoformat(),
                end=end.isoformat(),
                interval=interval,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
        except Exception:
            frame = pd.DataFrame()

        if frame.empty:
            return self._fetch_yahoo_chart(source_symbol, start_date, end_date, interval)

        return self._frame_to_klines(frame)

    def fetch_daily(
        self,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Kline]:
        return self.fetch(symbol, KlinePeriod.DAILY, start_date, end_date)

    @staticmethod
    def _fetch_tencent_a_share(
        symbol: str,
        period: KlinePeriod,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Kline]:
        start = start_date or date.today() - timedelta(days=365 * 3)
        end = end_date or date.today()
        if period == KlinePeriod.DAILY and (end - start).days > 730:
            rows_by_date: dict[date, Kline] = {}
            cursor = start
            while cursor <= end:
                chunk_end = min(cursor + timedelta(days=730), end)
                for item in MarketDataService._fetch_tencent_a_share_window(
                    symbol,
                    period,
                    cursor,
                    chunk_end,
                    include_current=chunk_end == end,
                ):
                    rows_by_date[item.time] = item
                cursor = chunk_end + timedelta(days=1)
            return [rows_by_date[item] for item in sorted(rows_by_date)]

        return MarketDataService._fetch_tencent_a_share_window(symbol, period, start, end, include_current=True)

    @staticmethod
    def _fetch_tencent_a_share_window(
        symbol: str,
        period: KlinePeriod,
        start: date,
        end: date,
        include_current: bool,
    ) -> list[Kline]:
        tencent_symbol = normalize_tencent_symbol(symbol)
        period_key = TENCENT_PERIOD_KEYS[period]
        fq_key = f"qfq{period_key}"
        response = requests.get(
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            params={
                "param": f"{tencent_symbol},{period_key},{start.isoformat()},{end.isoformat()},{MarketDataService._tencent_count(start, end, period)},qfq",
            },
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data", {})
        if not isinstance(data, dict):
            return []
        stock_data = data.get(tencent_symbol, {})
        rows = [
            MarketDataService._parse_tencent_kline(item)
            for item in stock_data.get(fq_key, [])
        ]

        if period == KlinePeriod.DAILY and include_current:
            current = MarketDataService._parse_tencent_current_kline(stock_data.get("qt", {}).get(tencent_symbol))
            if current and start <= current.time <= end:
                rows = [item for item in rows if item.time != current.time]
                rows.append(current)

        rows = [item for item in rows if MarketDataService._is_valid_kline(item)]
        return sorted(rows, key=lambda item: item.time)

    @staticmethod
    def _parse_tencent_kline(values: list[str]) -> Kline:
        return Kline(
            time=pd.to_datetime(values[0]).date(),
            open=round(float(values[1]), 4),
            close=round(float(values[2]), 4),
            high=round(float(values[3]), 4),
            low=round(float(values[4]), 4),
            volume=round(float(values[5]) * 100, 4),
            amount=0,
        )

    @staticmethod
    def _tencent_count(start: date, end: date, period: KlinePeriod) -> int:
        days = max((end - start).days + 1, 1)
        if period == KlinePeriod.DAILY:
            return min(max(days, 20), 800)
        if period == KlinePeriod.WEEKLY:
            return min(max(days // 7 + 4, 20), 800)
        return min(max(days // 31 + 4, 20), 800)

    @staticmethod
    def _parse_tencent_current_kline(values: list[str] | None) -> Kline | None:
        if not values or len(values) < 38 or not values[30]:
            return None
        return Kline(
            time=datetime.strptime(values[30][:8], "%Y%m%d").date(),
            open=round(float(values[5]), 4),
            high=round(float(values[33]), 4),
            low=round(float(values[34]), 4),
            close=round(float(values[3]), 4),
            volume=round(float(values[36]) * 100, 4),
            amount=round(float(values[57]) * 10000, 4) if len(values) > 57 and values[57] else 0,
        )

    @staticmethod
    def _fetch_tencent_intraday(
        symbol: str,
        period: KlinePeriod,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Kline]:
        source_period = KlinePeriod.MINUTE_60 if period == KlinePeriod.HOUR_4 else period
        minute_key = TENCENT_MINUTE_KEYS[source_period]
        tencent_symbol = normalize_tencent_symbol(symbol)
        response = requests.get(
            "https://ifzq.gtimg.cn/appstock/app/kline/mkline",
            params={"param": f"{tencent_symbol},{minute_key},,320"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        stock_data = response.json().get("data", {}).get(tencent_symbol, {})
        rows = [
            MarketDataService._parse_tencent_minute_kline(values)
            for values in stock_data.get(minute_key, [])
        ]
        rows = [item for item in rows if MarketDataService._is_valid_kline(item)]

        start = start_date or date.today() - timedelta(days=INTRADAY_LOOKBACK_DAYS[period] - 1)
        end = end_date or date.today()
        rows = [item for item in rows if start <= item.time.date() <= end]
        if period == KlinePeriod.HOUR_4:
            return MarketDataService._aggregate_trading_days(rows)
        return rows

    @staticmethod
    def _parse_tencent_minute_kline(values: list[object]) -> Kline:
        return Kline(
            time=datetime.strptime(str(values[0]), "%Y%m%d%H%M"),
            open=round(float(values[1]), 4),
            close=round(float(values[2]), 4),
            high=round(float(values[3]), 4),
            low=round(float(values[4]), 4),
            volume=round(float(values[5]) * 100, 4),
            amount=0,
        )

    @staticmethod
    def _aggregate_trading_days(rows: list[Kline]) -> list[Kline]:
        by_date: dict[date, list[Kline]] = {}
        for item in rows:
            by_date.setdefault(item.time.date(), []).append(item)

        result: list[Kline] = []
        for trade_date in sorted(by_date):
            day_rows = sorted(by_date[trade_date], key=lambda item: item.time)
            result.append(
                Kline(
                    time=day_rows[-1].time,
                    open=day_rows[0].open,
                    high=max(item.high for item in day_rows),
                    low=min(item.low for item in day_rows),
                    close=day_rows[-1].close,
                    volume=sum(item.volume for item in day_rows),
                    amount=sum(item.amount for item in day_rows),
                )
            )
        return result

    def _frame_to_klines(self, frame: pd.DataFrame) -> list[Kline]:
        frame = self._flatten_columns(frame).reset_index()
        date_column = "Date" if "Date" in frame.columns else "Datetime"
        result: list[Kline] = []
        for row in frame.itertuples(index=False):
            row_data = row._asdict()
            trade_date = pd.Timestamp(row_data[date_column]).date()
            item = Kline(
                time=trade_date,
                open=float(row_data["Open"]),
                high=float(row_data["High"]),
                low=float(row_data["Low"]),
                close=float(row_data["Close"]),
                volume=float(row_data.get("Volume", 0) or 0),
                amount=0,
            )
            if self._is_valid_kline(item):
                result.append(item)
        return result

    @staticmethod
    def _flatten_columns(frame: pd.DataFrame) -> pd.DataFrame:
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = [col[0] for col in frame.columns]
        return frame

    @staticmethod
    def _fetch_yahoo_chart(
        source_symbol: str,
        start_date: date | None,
        end_date: date | None,
        interval: str,
    ) -> list[Kline]:
        start = start_date or date.today() - timedelta(days=365 * 3)
        end = end_date or date.today()
        params = {
            "period1": int(datetime.combine(start, time.min, tzinfo=timezone.utc).timestamp()),
            "period2": int(datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc).timestamp()),
            "interval": interval,
            "events": "history",
            "includeAdjustedClose": "true",
        }
        response = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{source_symbol}",
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("chart", {}).get("result") or []
        if not results:
            return []

        result = results[0]
        timestamps = result.get("timestamp") or []
        quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
        opens = quotes.get("open") or []
        highs = quotes.get("high") or []
        lows = quotes.get("low") or []
        closes = quotes.get("close") or []
        volumes = quotes.get("volume") or []

        rows: list[Kline] = []
        for index, timestamp in enumerate(timestamps):
            open_price = opens[index] if index < len(opens) else None
            high_price = highs[index] if index < len(highs) else None
            low_price = lows[index] if index < len(lows) else None
            close_price = closes[index] if index < len(closes) else None
            if None in (open_price, high_price, low_price, close_price):
                continue

            trade_date = pd.to_datetime(timestamp, unit="s", utc=True).tz_convert("Asia/Shanghai").date()
            if start_date and trade_date < start_date:
                continue
            if end_date and trade_date > end_date:
                continue

            item = Kline(
                time=trade_date,
                open=round(float(open_price), 4),
                high=round(float(high_price), 4),
                low=round(float(low_price), 4),
                close=round(float(close_price), 4),
                volume=float(volumes[index] or 0) if index < len(volumes) else 0,
                amount=0,
            )
            if MarketDataService._is_valid_kline(item):
                rows.append(item)
        return rows

    @staticmethod
    def _is_valid_kline(item: Kline) -> bool:
        return item.low <= item.open <= item.high and item.low <= item.close <= item.high

    @staticmethod
    def _demo(start_date: date | None, end_date: date | None, period: KlinePeriod) -> list[Kline]:
        if is_intraday_period(period):
            return []
        daily = MarketDataService._demo_daily(start_date, end_date)
        if period == KlinePeriod.DAILY:
            return daily
        rule = "W-FRI" if period == KlinePeriod.WEEKLY else "ME"
        return MarketDataService._resample(daily, rule)

    @staticmethod
    def _demo_daily(start_date: date | None, end_date: date | None) -> list[Kline]:
        start = start_date or date.today() - timedelta(days=240)
        end = end_date or date.today()
        rows: list[Kline] = []
        current = start
        index = 0

        while current <= end:
            if current.weekday() < 5:
                wave = (index % 20) - 10
                trend = index * 0.08
                center = 100 + trend + abs(wave) * (1 if (index // 20) % 2 == 0 else -1)
                spread = 1.8 + (index % 5) * 0.2
                open_price = center - 0.4
                close_price = center + (0.6 if index % 2 == 0 else -0.6)
                rows.append(
                    Kline(
                        time=current,
                        open=round(open_price, 2),
                        high=round(max(open_price, close_price) + spread, 2),
                        low=round(min(open_price, close_price) - spread, 2),
                        close=round(close_price, 2),
                        volume=1000000 + index * 2300,
                        amount=0,
                    )
                )
                index += 1
            current += timedelta(days=1)

        return rows

    @staticmethod
    def _resample(klines: list[Kline], rule: str) -> list[Kline]:
        if not klines:
            return []
        frame = pd.DataFrame(
            [
                {
                    "trade_date": item.time,
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                    "amount": item.amount,
                }
                for item in klines
            ]
        )
        frame["trade_date"] = pd.to_datetime(frame["trade_date"])
        resampled = (
            frame.set_index("trade_date")
            .resample(rule)
            .agg(
                {
                    "open": "first",
                    "high": "max",
                    "low": "min",
                    "close": "last",
                    "volume": "sum",
                    "amount": "sum",
                }
            )
            .dropna(subset=["open", "high", "low", "close"])
            .reset_index()
        )
        return [
            Kline(
                time=row.trade_date.date(),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume or 0),
                amount=float(row.amount or 0),
            )
            for row in resampled.itertuples(index=False)
        ]
