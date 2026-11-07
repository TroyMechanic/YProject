from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

import pandas as pd

from app.models.schemas import Bi, CentralZone, ChartResponse, Fractal, Kline, KlinePeriod, Segment
from app.services.market_data_service import is_intraday_period


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
ANALYZED_DIR = DATA_DIR / "analyzed"


def safe_symbol(symbol: str) -> str:
    return symbol.upper().replace("/", "_").replace("\\", "_").replace(":", "_")


def safe_period(period: KlinePeriod | str) -> str:
    return period.value if isinstance(period, KlinePeriod) else period


class CsvStore:
    def __init__(self, raw_dir: Path = RAW_DIR, analyzed_dir: Path = ANALYZED_DIR) -> None:
        self.raw_dir = raw_dir
        self.analyzed_dir = analyzed_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.analyzed_dir.mkdir(parents=True, exist_ok=True)

    def load_analysis(self, symbol: str, period: KlinePeriod) -> ChartResponse | None:
        payload = self.load_analysis_payload(symbol, period)
        return ChartResponse.model_validate_json(json.dumps(payload)) if payload is not None else None

    def load_analysis_payload(self, symbol: str, period: KlinePeriod) -> dict | None:
        path = self._analysis_path(symbol, period)
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def save_analysis(self, chart: ChartResponse) -> None:
        # CSVs remain human-readable exports. API reads one atomic committed bundle.
        self.save_fractals(chart.symbol, chart.period, chart.fractals)
        self.save_bis(chart.symbol, chart.period, chart.bis)
        self.save_segments(chart.symbol, chart.period, chart.segments)
        self.save_central_zones(chart.symbol, chart.period, chart.central_zones)
        self.save_research(chart)
        path = self._analysis_path(chart.symbol, chart.period)
        archive = self.analyzed_dir / "runs" / f"{safe_symbol(chart.symbol)}_{safe_period(chart.period)}"
        archive.mkdir(parents=True, exist_ok=True)
        # Unique run IDs preserve prior inputs, outputs and rule catalog for manual comparison.
        archive_path = archive / f"{chart.analysis.run_id}.json"
        payload = chart.model_dump_json(by_alias=True, indent=2)
        self._atomic_text(archive_path, payload)
        self._atomic_text(path, payload)

    @staticmethod
    def _atomic_text(path: Path, payload: str) -> None:
        with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as tmp:
            tmp_path = Path(tmp.name)
            try:
                tmp.write(payload)
            except BaseException:
                tmp_path.unlink(missing_ok=True)
                raise
        try:
            tmp_path.replace(path)
        finally:
            tmp_path.unlink(missing_ok=True)

    def _analysis_path(self, symbol: str, period: KlinePeriod) -> Path:
        return self.analyzed_dir / f"{safe_symbol(symbol)}_{safe_period(period)}_analysis.json"

    def save_research(self, chart: ChartResponse) -> None:
        prefix=f"{safe_symbol(chart.symbol)}_{safe_period(chart.period)}"
        collections={"indicators":chart.indicators,"signal_zones":chart.signal_zones,
                     "divergences":chart.divergences,"trading_points":chart.trading_points,
                     "zone_relations":chart.zone_relations}
        for name,collection in collections.items():
            rows=[]
            for item in collection:
                values=item.model_dump(mode="json",by_alias=True)
                rows.append({key:json.dumps(value,ensure_ascii=False) if isinstance(value,(dict,list)) else value
                             for key,value in values.items()})
            self._atomic_write(self.analyzed_dir/f"{prefix}_{name}.csv",pd.DataFrame(rows))
        rows=[]
        for level,collection in (("bi",chart.bis),("segment",chart.segments)):
            rows.extend({"level":level,"index":index,"startTime":item.start_time,"endTime":item.end_time,
                         **item.momentum.model_dump(by_alias=True)}
                        for index,item in enumerate(collection) if item.momentum is not None)
        self._atomic_write(self.analyzed_dir/f"{prefix}_momentum.csv",pd.DataFrame(rows))
        rows=[{"time":f.time,"type":f.type.value,"grade":f.strength.grade,
               "reasons":json.dumps(f.strength.reasons,ensure_ascii=False)} for f in chart.fractals if f.strength]
        self._atomic_write(self.analyzed_dir/f"{prefix}_fractal_strength.csv",pd.DataFrame(rows))

    def load_klines(
        self,
        symbol: str,
        period: KlinePeriod = KlinePeriod.DAILY,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Kline]:
        path = self._kline_path(symbol, period)
        if not path.exists():
            return []

        df = pd.read_csv(path, parse_dates=["trade_date"])
        if df.empty:
            return []

        df = self._filter_date_range(df, start_date, end_date)
        return [
            Kline(
                time=self._to_period_time(row.trade_date, period),
                open=float(row.open),
                high=float(row.high),
                low=float(row.low),
                close=float(row.close),
                volume=float(row.volume or 0),
                amount=float(row.amount or 0),
            )
            for row in df.itertuples(index=False)
        ]

    def upsert_klines(self, symbol: str, period: KlinePeriod, klines: list[Kline]) -> int:
        path = self._kline_path(symbol, period)
        existing = pd.read_csv(path, parse_dates=["trade_date"]) if path.exists() else pd.DataFrame()
        incoming = pd.DataFrame(
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

        merged = pd.concat([existing, incoming], ignore_index=True)
        if merged.empty:
            self._atomic_write(path, self._empty_kline_frame())
            return 0

        merged["trade_date"] = pd.to_datetime(merged["trade_date"])
        if period == KlinePeriod.HOUR_4:
            merged["_trade_day"] = merged["trade_date"].dt.date
            merged = merged.drop_duplicates(subset=["_trade_day"], keep="last").drop(columns=["_trade_day"])
        else:
            merged = merged.drop_duplicates(subset=["trade_date"], keep="last")
        merged = merged.sort_values("trade_date").reset_index(drop=True)
        self._atomic_write(path, merged)
        return len(merged)

    def save_fractals(self, symbol: str, period: KlinePeriod, fractals: list[Fractal]) -> None:
        columns = [
            "trade_date",
            "type",
            "price",
            "kline_index",
            "merged_index",
            "element_high",
            "element_low",
            "elements",
            "reasons",
        ]
        frame = pd.DataFrame(
            [
                {
                    "trade_date": item.time,
                    "type": item.type.value,
                    "price": item.price,
                    "kline_index": item.kline_index,
                    "merged_index": item.merged_index,
                    "element_high": item.element_high,
                    "element_low": item.element_low,
                    "elements": json.dumps([element.model_dump(by_alias=True, mode="json") for element in item.elements], ensure_ascii=False),
                    "reasons": json.dumps(item.reasons, ensure_ascii=False),
                }
                for item in fractals
            ],
            columns=columns,
        )
        self._atomic_write(self._fractal_path(symbol, period), frame)

    def load_fractals(
        self,
        symbol: str,
        period: KlinePeriod = KlinePeriod.DAILY,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Fractal]:
        path = self._fractal_path(symbol, period)
        if not path.exists() or path.stat().st_size <= 1:
            return []
        df = pd.read_csv(path, parse_dates=["trade_date"])
        if df.empty:
            return []
        df = self._filter_date_range(df, start_date, end_date)
        return [
            Fractal(
                time=self._to_period_time(row.trade_date, period),
                type=row.type,
                price=float(row.price),
                klineIndex=int(row.kline_index),
                mergedIndex=int(row.merged_index) if hasattr(row, "merged_index") and not pd.isna(row.merged_index) else int(row.kline_index),
                elementHigh=float(row.element_high) if hasattr(row, "element_high") and not pd.isna(row.element_high) else None,
                elementLow=float(row.element_low) if hasattr(row, "element_low") and not pd.isna(row.element_low) else None,
                elements=self._parse_elements(row.elements) if hasattr(row, "elements") else [],
                reasons=self._parse_reasons(row.reasons) if hasattr(row, "reasons") else [],
            )
            for row in df.itertuples(index=False)
        ]

    def save_bis(self, symbol: str, period: KlinePeriod, bis: list[Bi]) -> None:
        columns = [
            "start_date",
            "end_date",
            "start_price",
            "end_price",
            "direction",
            "start_index",
            "end_index",
            "confirmed",
            "reasons",
        ]
        frame = pd.DataFrame(
            [
                {
                    "start_date": item.start_time,
                    "end_date": item.end_time,
                    "start_price": item.start_price,
                    "end_price": item.end_price,
                    "direction": item.direction.value,
                    "start_index": item.start_index,
                    "end_index": item.end_index,
                    "confirmed": item.confirmed,
                    "reasons": json.dumps(item.reasons, ensure_ascii=False),
                }
                for item in bis
            ],
            columns=columns,
        )
        self._atomic_write(self._bi_path(symbol, period), frame)

    def load_bis(
        self,
        symbol: str,
        period: KlinePeriod = KlinePeriod.DAILY,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Bi]:
        path = self._bi_path(symbol, period)
        if not path.exists() or path.stat().st_size <= 1:
            return []
        df = pd.read_csv(path, parse_dates=["start_date", "end_date"])
        if df.empty:
            return []
        if start_date:
            df = df[df["end_date"].dt.date >= start_date]
        if end_date:
            df = df[df["start_date"].dt.date <= end_date]
        return [
            Bi(
                startTime=self._to_period_time(row.start_date, period),
                endTime=self._to_period_time(row.end_date, period),
                startPrice=float(row.start_price),
                endPrice=float(row.end_price),
                direction=row.direction,
                startIndex=int(row.start_index),
                endIndex=int(row.end_index),
                confirmed=bool(row.confirmed),
                reasons=self._parse_reasons(row.reasons) if hasattr(row, "reasons") else [],
            )
            for row in df.itertuples(index=False)
        ]

    def save_segments(self, symbol: str, period: KlinePeriod, segments: list[Segment]) -> None:
        columns = [
            "start_date",
            "end_date",
            "start_price",
            "end_price",
            "direction",
            "start_bi_index",
            "end_bi_index",
            "bi_count",
            "confirmed",
            "break_type",
            "feature_sequence",
            "reasons",
        ]
        frame = pd.DataFrame(
            [
                {
                    "start_date": item.start_time,
                    "end_date": item.end_time,
                    "start_price": item.start_price,
                    "end_price": item.end_price,
                    "direction": item.direction.value,
                    "start_bi_index": item.start_bi_index,
                    "end_bi_index": item.end_bi_index,
                    "bi_count": item.bi_count,
                    "confirmed": item.confirmed,
                    "break_type": item.break_type.value,
                    "feature_sequence": json.dumps(
                        [element.model_dump(by_alias=True, mode="json") for element in item.feature_sequence],
                        ensure_ascii=False,
                    ),
                    "reasons": json.dumps(item.reasons, ensure_ascii=False),
                }
                for item in segments
            ],
            columns=columns,
        )
        self._atomic_write(self._segment_path(symbol, period), frame)

    def load_segments(
        self,
        symbol: str,
        period: KlinePeriod = KlinePeriod.DAILY,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[Segment]:
        path = self._segment_path(symbol, period)
        if not path.exists() or path.stat().st_size <= 1:
            return []
        df = pd.read_csv(path, parse_dates=["start_date", "end_date"])
        if df.empty:
            return []
        if start_date:
            df = df[df["end_date"].dt.date >= start_date]
        if end_date:
            df = df[df["start_date"].dt.date <= end_date]
        return [
            Segment(
                startTime=self._to_period_time(row.start_date, period),
                endTime=self._to_period_time(row.end_date, period),
                startPrice=float(row.start_price),
                endPrice=float(row.end_price),
                direction=row.direction,
                startBiIndex=int(row.start_bi_index),
                endBiIndex=int(row.end_bi_index),
                biCount=int(row.bi_count),
                confirmed=self._parse_bool(row.confirmed),
                breakType=row.break_type,
                featureSequence=self._parse_json_list(row.feature_sequence),
                reasons=self._parse_reasons(row.reasons),
            )
            for row in df.itertuples(index=False)
        ]

    def save_central_zones(self, symbol: str, period: KlinePeriod, zones: list[CentralZone]) -> None:
        columns = [
            "start_date",
            "end_date",
            "zd",
            "zg",
            "dd",
            "gg",
            "start_segment_index",
            "end_segment_index",
            "segment_count",
            "status",
            "source_segment_indices",
            "reasons",
        ]
        frame = pd.DataFrame(
            [
                {
                    "start_date": item.start_time,
                    "end_date": item.end_time,
                    "zd": item.zd,
                    "zg": item.zg,
                    "dd": item.dd,
                    "gg": item.gg,
                    "start_segment_index": item.start_segment_index,
                    "end_segment_index": item.end_segment_index,
                    "segment_count": item.segment_count,
                    "status": item.status.value,
                    "source_segment_indices": json.dumps(item.source_segment_indices),
                    "reasons": json.dumps(item.reasons, ensure_ascii=False),
                }
                for item in zones
            ],
            columns=columns,
        )
        self._atomic_write(self._central_zone_path(symbol, period), frame)

    def load_central_zones(
        self,
        symbol: str,
        period: KlinePeriod = KlinePeriod.DAILY,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[CentralZone]:
        path = self._central_zone_path(symbol, period)
        if not path.exists() or path.stat().st_size <= 1:
            return []
        df = pd.read_csv(path, parse_dates=["start_date", "end_date"])
        if df.empty:
            return []
        if start_date:
            df = df[df["end_date"].dt.date >= start_date]
        if end_date:
            df = df[df["start_date"].dt.date <= end_date]
        return [
            CentralZone(
                startTime=self._to_period_time(row.start_date, period),
                endTime=self._to_period_time(row.end_date, period),
                zd=float(row.zd),
                zg=float(row.zg),
                dd=float(row.dd),
                gg=float(row.gg),
                startSegmentIndex=int(row.start_segment_index),
                endSegmentIndex=int(row.end_segment_index),
                segmentCount=int(row.segment_count),
                status=row.status,
                sourceSegmentIndices=self._parse_int_list(row.source_segment_indices),
                reasons=self._parse_reasons(row.reasons),
            )
            for row in df.itertuples(index=False)
        ]

    def _kline_path(self, symbol: str, period: KlinePeriod) -> Path:
        return self.raw_dir / f"{safe_symbol(symbol)}_{safe_period(period)}.csv"

    def _fractal_path(self, symbol: str, period: KlinePeriod) -> Path:
        suffix = "" if period == KlinePeriod.DAILY else f"_{safe_period(period)}"
        return self.analyzed_dir / f"{safe_symbol(symbol)}{suffix}_fractals.csv"

    def _bi_path(self, symbol: str, period: KlinePeriod) -> Path:
        suffix = "" if period == KlinePeriod.DAILY else f"_{safe_period(period)}"
        return self.analyzed_dir / f"{safe_symbol(symbol)}{suffix}_bis.csv"

    def _segment_path(self, symbol: str, period: KlinePeriod) -> Path:
        suffix = "" if period == KlinePeriod.DAILY else f"_{safe_period(period)}"
        return self.analyzed_dir / f"{safe_symbol(symbol)}{suffix}_segments.csv"

    def _central_zone_path(self, symbol: str, period: KlinePeriod) -> Path:
        suffix = "" if period == KlinePeriod.DAILY else f"_{safe_period(period)}"
        return self.analyzed_dir / f"{safe_symbol(symbol)}{suffix}_central_zones.csv"

    @staticmethod
    def _filter_date_range(df: pd.DataFrame, start_date: date | None, end_date: date | None) -> pd.DataFrame:
        if start_date:
            df = df[df["trade_date"].dt.date >= start_date]
        if end_date:
            df = df[df["trade_date"].dt.date <= end_date]
        return df.sort_values("trade_date").reset_index(drop=True)

    @staticmethod
    def _empty_kline_frame() -> pd.DataFrame:
        return pd.DataFrame(columns=["trade_date", "open", "high", "low", "close", "volume", "amount"])

    @staticmethod
    def _atomic_write(path: Path, frame: pd.DataFrame) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", delete=False, dir=path.parent, suffix=".tmp") as tmp:
            tmp_path = Path(tmp.name)
            frame.to_csv(tmp_path, index=False)
        tmp_path.replace(path)

    @staticmethod
    def _parse_reasons(value: object) -> list[str]:
        if value is None or pd.isna(value):
            return []
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return [str(value)]
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _parse_elements(value: object) -> list[dict]:
        if value is None or pd.isna(value):
            return []
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _parse_json_list(value: object) -> list[dict]:
        if value is None or pd.isna(value):
            return []
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _parse_bool(value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return bool(value)

    @staticmethod
    def _parse_int_list(value: object) -> list[int]:
        if value is None or pd.isna(value):
            return []
        try:
            parsed = json.loads(str(value))
        except json.JSONDecodeError:
            return []
        return [int(item) for item in parsed] if isinstance(parsed, list) else []

    @staticmethod
    def _to_period_time(value: object, period: KlinePeriod) -> object:
        timestamp = pd.Timestamp(value)
        return timestamp.to_pydatetime() if is_intraday_period(period) else timestamp.date()
