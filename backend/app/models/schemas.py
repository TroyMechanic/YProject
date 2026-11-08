from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Optional, Union

from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class FractalType(str, Enum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"


class BiDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class SegmentBreakType(str, Enum):
    PIVOT_BREAK = "PIVOT_BREAK"
    NO_GAP = "NO_GAP"
    GAP_CONFIRMED = "GAP_CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"


class KlinePeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    HOUR_4 = "hour4"
    MINUTE_60 = "minute60"
    MINUTE_30 = "minute30"
    MINUTE_5 = "minute5"
    MINUTE_1 = "minute1"


class RuleProfile(str, Enum):
    LEGACY = "legacy"
    SEPARATED = "separated"


class RuleSettings(ApiModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    rule_profile: RuleProfile = Field(default=RuleProfile.LEGACY, alias="ruleProfile")
    min_kline_gap: int = Field(default=1, ge=1, le=20, strict=True, alias="minKlineGap")
class SyncRequest(ApiModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    start_date: Optional[date] = Field(default=None, alias="startDate")
    end_date: Optional[date] = Field(default=None, alias="endDate")
    period: KlinePeriod = KlinePeriod.DAILY
    rule_profile: Optional[RuleProfile] = Field(default=None, alias="ruleProfile")
    min_kline_gap: Optional[int] = Field(default=None, ge=1, le=20, strict=True, alias="minKlineGap")

    @model_validator(mode="after")
    def validate_range(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        return self


class RecalculateRequest(SyncRequest):
    pass


class Kline(ApiModel):
    time: Union[datetime, date]
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    amount: float = 0

    @model_validator(mode="after")
    def validate_prices(self):
        values = (self.open, self.high, self.low, self.close, self.volume, self.amount)
        if not all(isfinite(value) for value in values):
            raise ValueError("行情必须是有限数值")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("OHLC 必须满足 low <= open/close <= high")
        if self.volume < 0 or self.amount < 0:
            raise ValueError("成交量和成交额不能为负")
        return self


class FractalElement(ApiModel):
    time: Union[datetime, date]
    kline_index: int = Field(alias="klineIndex")
    high: float
    low: float
    source_times: list[Union[datetime, date]] = Field(default_factory=list, alias="sourceTimes")
    high_source_time: Optional[Union[datetime, date]] = Field(default=None, alias="highSourceTime")
    low_source_time: Optional[Union[datetime, date]] = Field(default=None, alias="lowSourceTime")


class Fractal(ApiModel):
    time: Union[datetime, date]
    type: FractalType
    price: float
    kline_index: int = Field(alias="klineIndex")
    merged_index: int = Field(default=0, alias="mergedIndex")
    element_high: Optional[float] = Field(default=None, alias="elementHigh")
    element_low: Optional[float] = Field(default=None, alias="elementLow")
    elements: list[FractalElement] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class Bi(ApiModel):
    start_time: Union[datetime, date] = Field(alias="startTime")
    end_time: Union[datetime, date] = Field(alias="endTime")
    start_price: float = Field(alias="startPrice")
    end_price: float = Field(alias="endPrice")
    direction: BiDirection
    start_index: int = Field(alias="startIndex")
    end_index: int = Field(alias="endIndex")
    confirmed: bool = True
    reasons: list[str] = Field(default_factory=list)
    confirmed_at: Optional[Union[datetime, date]] = Field(default=None, alias="confirmedAt")


class FeatureSequenceElement(ApiModel):
    high: float
    low: float
    start_bi_index: int = Field(alias="startBiIndex")
    end_bi_index: int = Field(alias="endBiIndex")
    source_bi_indices: list[int] = Field(default_factory=list, alias="sourceBiIndices")
    high_source_bi_index: int = Field(alias="highSourceBiIndex")
    low_source_bi_index: int = Field(alias="lowSourceBiIndex")
    gap_from_previous: bool = Field(default=False, alias="gapFromPrevious")


class Segment(ApiModel):
    start_time: Union[datetime, date] = Field(alias="startTime")
    end_time: Union[datetime, date] = Field(alias="endTime")
    start_price: float = Field(alias="startPrice")
    end_price: float = Field(alias="endPrice")
    direction: BiDirection
    start_bi_index: int = Field(alias="startBiIndex")
    end_bi_index: int = Field(alias="endBiIndex")
    bi_count: int = Field(alias="biCount")
    confirmed: bool
    break_type: SegmentBreakType = Field(alias="breakType")
    feature_sequence: list[FeatureSequenceElement] = Field(default_factory=list, alias="featureSequence")
    reasons: list[str] = Field(default_factory=list)
    confirmation_bi_index: Optional[int] = Field(default=None, alias="confirmationBiIndex")
    confirmed_at: Optional[Union[datetime, date]] = Field(default=None, alias="confirmedAt")


class AnalysisMetadata(ApiModel):
    run_id: str = Field(alias="runId")
    generated_at: datetime = Field(alias="generatedAt")
    rule_version: str = Field(alias="ruleVersion")
    settings: RuleSettings
    effective_min_kline_gap: int = Field(alias="effectiveMinKlineGap")
    input_hash: str = Field(alias="inputHash")
    engine_hash: str = Field(alias="engineHash")
    rule_hash: str = Field(alias="ruleHash")
    result_hash: str = Field(alias="resultHash")
    source_count: int = Field(alias="sourceCount")
    source_start: Optional[Union[datetime, date]] = Field(default=None, alias="sourceStart")
    source_end: Optional[Union[datetime, date]] = Field(default=None, alias="sourceEnd")
    principle_ids: list[str] = Field(alias="principleIds")
    rule_catalog: dict = Field(alias="ruleCatalog")


class MacdPoint(ApiModel):
    time: Union[datetime, date]
    dif: float
    dea: float
    histogram: float


class ChartResponse(ApiModel):
    macd: list[MacdPoint] = Field(default_factory=list)
    symbol: str
    name: str = ""
    period: KlinePeriod
    klines: list[Kline]
    fractals: list[Fractal]
    bis: list[Bi]
    segments: list[Segment] = Field(default_factory=list)
    analysis: Optional[AnalysisMetadata] = None


class SyncResponse(ApiModel):
    symbol: str
    name: str = ""
    period: KlinePeriod
    rows: int
    message: str
