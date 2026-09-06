from datetime import date, datetime
from enum import Enum
from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class FractalType(str, Enum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"


class BiDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class SegmentBreakType(str, Enum):
    NO_GAP = "NO_GAP"
    GAP_CONFIRMED = "GAP_CONFIRMED"
    UNCONFIRMED = "UNCONFIRMED"


class CentralZoneStatus(str, Enum):
    EXTENDING = "EXTENDING"
    LEFT_UP = "LEFT_UP"
    LEFT_DOWN = "LEFT_DOWN"


class KlinePeriod(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    HOUR_4 = "hour4"
    MINUTE_60 = "minute60"
    MINUTE_30 = "minute30"
    MINUTE_1 = "minute1"


class SyncRequest(ApiModel):
    start_date: Optional[date] = Field(default=None, alias="startDate")
    end_date: Optional[date] = Field(default=None, alias="endDate")
    period: KlinePeriod = KlinePeriod.DAILY


class RecalculateRequest(ApiModel):
    start_date: Optional[date] = Field(default=None, alias="startDate")
    end_date: Optional[date] = Field(default=None, alias="endDate")
    period: KlinePeriod = KlinePeriod.DAILY
    min_kline_gap: int = Field(default=1, ge=1, alias="minKlineGap")


class Kline(ApiModel):
    time: Union[datetime, date]
    open: float
    high: float
    low: float
    close: float
    volume: float = 0
    amount: float = 0


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


class CentralZone(ApiModel):
    start_time: Union[datetime, date] = Field(alias="startTime")
    end_time: Union[datetime, date] = Field(alias="endTime")
    zd: float
    zg: float
    dd: float
    gg: float
    start_segment_index: int = Field(alias="startSegmentIndex")
    end_segment_index: int = Field(alias="endSegmentIndex")
    segment_count: int = Field(alias="segmentCount")
    status: CentralZoneStatus
    source_segment_indices: list[int] = Field(default_factory=list, alias="sourceSegmentIndices")
    reasons: list[str] = Field(default_factory=list)


class ChartResponse(ApiModel):
    symbol: str
    name: str = ""
    period: KlinePeriod
    klines: list[Kline]
    fractals: list[Fractal]
    bis: list[Bi]
    segments: list[Segment] = Field(default_factory=list)
    central_zones: list[CentralZone] = Field(default_factory=list, alias="centralZones")


class SyncResponse(ApiModel):
    symbol: str
    name: str = ""
    period: KlinePeriod
    rows: int
    message: str
