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
    MINUTE_5 = "minute5"
    MINUTE_1 = "minute1"


class RuleProfile(str, Enum):
    LEGACY = "legacy"
    SEPARATED = "separated"


class SignalLevel(str, Enum):
    BI = "bi"
    SEGMENT = "segment"


class RuleSettings(ApiModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    rule_profile: RuleProfile = Field(default=RuleProfile.LEGACY, alias="ruleProfile")
    min_kline_gap: int = Field(default=1, ge=1, le=20, strict=True, alias="minKlineGap")
    signal_level: SignalLevel = Field(default=SignalLevel.BI, alias="signalLevel")
    divergence_ratio: float = Field(default=0.8, ge=0.1, le=0.99, alias="divergenceRatio")
    zero_axis_tolerance: float = Field(default=0.01, ge=0.001, le=0.1, alias="zeroAxisTolerance")
    macd_fast: int = Field(default=12, ge=2, le=100, strict=True, alias="macdFast")
    macd_slow: int = Field(default=26, ge=3, le=200, strict=True, alias="macdSlow")
    macd_signal: int = Field(default=9, ge=2, le=100, strict=True, alias="macdSignal")

    @model_validator(mode="after")
    def validate_macd(self):
        if self.macd_fast >= self.macd_slow:
            raise ValueError("MACD快线周期必须小于慢线周期")
        return self


class SyncRequest(ApiModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    start_date: Optional[date] = Field(default=None, alias="startDate")
    end_date: Optional[date] = Field(default=None, alias="endDate")
    period: KlinePeriod = KlinePeriod.DAILY
    rule_profile: Optional[RuleProfile] = Field(default=None, alias="ruleProfile")
    min_kline_gap: Optional[int] = Field(default=None, ge=1, le=20, strict=True, alias="minKlineGap")
    signal_level: Optional[SignalLevel] = Field(default=None, alias="signalLevel")
    divergence_ratio: Optional[float] = Field(default=None, ge=0.1, le=0.99, alias="divergenceRatio")
    zero_axis_tolerance: Optional[float] = Field(default=None, ge=0.001, le=0.1, alias="zeroAxisTolerance")
    macd_fast: Optional[int] = Field(default=None, ge=2, le=100, strict=True, alias="macdFast")
    macd_slow: Optional[int] = Field(default=None, ge=3, le=200, strict=True, alias="macdSlow")
    macd_signal: Optional[int] = Field(default=None, ge=2, le=100, strict=True, alias="macdSignal")

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


class StrengthAssessment(ApiModel):
    grade: str
    reasons: list[str]


class Momentum(ApiModel):
    bar_count: int = Field(alias="barCount")
    amplitude_percent: float = Field(alias="amplitudePercent")
    velocity: float
    macd_area: float = Field(alias="macdArea")
    macd_peak: float = Field(alias="macdPeak")
    volume_sum: float = Field(alias="volumeSum")
    warmup_complete: bool = Field(alias="warmupComplete")
    relative_area: Optional[float] = Field(default=None, alias="relativeArea")
    grade: str = "UNAVAILABLE"


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
    strength: Optional[StrengthAssessment] = None


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
    momentum: Optional[Momentum] = None


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
    momentum: Optional[Momentum] = None


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


class IndicatorPoint(ApiModel):
    time: Union[datetime, date]
    dif: float
    dea: float
    histogram: float
    ready: bool


class SignalZone(ApiModel):
    id: str
    level: SignalLevel
    start_unit_index: int = Field(alias="startUnitIndex")
    end_unit_index: int = Field(alias="endUnitIndex")
    start_time: Union[datetime, date] = Field(alias="startTime")
    end_time: Union[datetime, date] = Field(alias="endTime")
    formed_at: Union[datetime, date] = Field(alias="formedAt")
    closed_at: Optional[Union[datetime, date]] = Field(default=None, alias="closedAt")
    departure_unit_index: Optional[int] = Field(default=None, alias="departureUnitIndex")
    zd: float
    zg: float
    dd: float
    gg: float
    member_indices: list[int] = Field(alias="memberIndices")
    status: CentralZoneStatus


class ZoneRelation(ApiModel):
    previous_zone_id: str = Field(alias="previousZoneId")
    current_zone_id: str = Field(alias="currentZoneId")
    type: str
    observed_at: Union[datetime, date] = Field(alias="observedAt")
    reasons: list[str]


class Divergence(ApiModel):
    id: str
    level: SignalLevel
    direction: BiDirection
    type: str
    time: Union[datetime, date]
    observed_at: Union[datetime, date] = Field(alias="observedAt")
    confirmed: bool
    previous_unit_index: int = Field(alias="previousUnitIndex")
    current_unit_index: int = Field(alias="currentUnitIndex")
    previous_area: float = Field(alias="previousArea")
    current_area: float = Field(alias="currentArea")
    ratio: float
    zone_ids: list[str] = Field(alias="zoneIds")
    reasons: list[str]


class TradingPoint(ApiModel):
    id: str
    type: str
    side: str
    level: SignalLevel
    time: Union[datetime, date]
    price: float
    observed_at: Union[datetime, date] = Field(alias="observedAt")
    confirmed: bool
    unit_index: int = Field(alias="unitIndex")
    zone_ids: list[str] = Field(default_factory=list, alias="zoneIds")
    divergence_id: Optional[str] = Field(default=None, alias="divergenceId")
    parent_id: Optional[str] = Field(default=None, alias="parentId")
    invalidation_price: float = Field(alias="invalidationPrice")
    reasons: list[str]
    structural_level: Optional[int] = Field(default=None, alias="structuralLevel")
    source_period: Optional[KlinePeriod] = Field(default=None, alias="sourcePeriod")
    unit_id: Optional[str] = Field(default=None, alias="unitId")
    display_time: Optional[Union[datetime, date]] = Field(default=None, alias="displayTime")
    display_endpoint_time: Optional[Union[datetime, date]] = Field(default=None, alias="displayEndpointTime")


class Movement(ApiModel):
    id: str
    level: int
    kind: str
    direction: BiDirection
    start_time: Union[datetime, date] = Field(alias="startTime")
    end_time: Union[datetime, date] = Field(alias="endTime")
    start_price: float = Field(alias="startPrice")
    end_price: float = Field(alias="endPrice")
    high: float
    low: float
    confirmed: bool
    observed_at: Union[datetime, date] = Field(alias="observedAt")
    child_ids: list[str] = Field(alias="childIds")
    confirmation_ids: list[str] = Field(default_factory=list, alias="confirmationIds")
    zone_ids: list[str] = Field(default_factory=list, alias="zoneIds")
    momentum: Momentum
    child_zones: list[SignalZone] = Field(default_factory=list, alias="childZones")
    reasons: list[str]


class StructureLayer(ApiModel):
    level: int
    movements: list[Movement]
    zones: list[SignalZone]
    divergences: list[Divergence]
    trading_points: list[TradingPoint] = Field(alias="tradingPoints")


class HierarchyAnalysis(ApiModel):
    base_period: KlinePeriod = Field(alias="basePeriod")
    max_level: int = Field(alias="maxLevel")
    base_analysis: AnalysisMetadata = Field(alias="baseAnalysis")
    base_klines: list[Kline] = Field(alias="baseKlines")
    base_fractals: list[Fractal] = Field(alias="baseFractals")
    base_bis: list[Bi] = Field(alias="baseBis")
    base_segments: list[Segment] = Field(alias="baseSegments")
    base_trading_points: list[TradingPoint] = Field(default_factory=list, alias="baseTradingPoints")
    base_signal_zones: list[SignalZone] = Field(default_factory=list, alias="baseSignalZones")
    base_divergences: list[Divergence] = Field(default_factory=list, alias="baseDivergences")
    layers: list[StructureLayer]
    warnings: list[str]


class TrendSummary(ApiModel):
    level: SignalLevel = SignalLevel.BI
    type: str = "INSUFFICIENT"
    zone_ids: list[str] = Field(default_factory=list, alias="zoneIds")
    reasons: list[str] = Field(default_factory=list)


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


class ChartResponse(ApiModel):
    symbol: str
    name: str = ""
    period: KlinePeriod
    klines: list[Kline]
    fractals: list[Fractal]
    bis: list[Bi]
    segments: list[Segment] = Field(default_factory=list)
    central_zones: list[CentralZone] = Field(default_factory=list, alias="centralZones")
    indicators: list[IndicatorPoint] = Field(default_factory=list)
    signal_zones: list[SignalZone] = Field(default_factory=list, alias="signalZones")
    zone_relations: list[ZoneRelation] = Field(default_factory=list, alias="zoneRelations")
    divergences: list[Divergence] = Field(default_factory=list)
    trading_points: list[TradingPoint] = Field(default_factory=list, alias="tradingPoints")
    trend: TrendSummary = Field(default_factory=TrendSummary)
    analysis: Optional[AnalysisMetadata] = None
    hierarchy: Optional[HierarchyAnalysis] = None


class HierarchyRequest(RecalculateRequest):
    base_period: Optional[KlinePeriod] = Field(default=None, alias="basePeriod")
    max_level: Optional[int] = Field(default=None, ge=1, le=8, strict=True, alias="maxLevel")


class SyncResponse(ApiModel):
    symbol: str
    name: str = ""
    period: KlinePeriod
    rows: int
    message: str
