from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ChartResponse, HierarchyRequest, KlinePeriod, RecalculateRequest, SyncRequest, SyncResponse
from app.services.hierarchy_service import HierarchyService
from app.services.chart_service import AnalysisStateError, ChartService
from app.services.rule_policy import rule_catalog
from app.services.stock_info import normalize_stock_symbol, resolve_stock_name


router = APIRouter(prefix="/api")
chart_service = ChartService()


def research_options(request: SyncRequest) -> dict:
    return {key:getattr(request,key) for key in ('signal_level','divergence_ratio','zero_axis_tolerance',
                                               'macd_fast','macd_slow','macd_signal') if getattr(request,key) is not None}


@router.get("/chan/rules")
def get_rules() -> dict:
    return rule_catalog()


@router.post("/stocks/{symbol}/sync", response_model=SyncResponse)
def sync_stock(symbol: str, request: SyncRequest) -> SyncResponse:
    try:
        rows = chart_service.sync(symbol, request.period, request.start_date, request.end_date,
                                  request.rule_profile, request.min_kline_gap, **research_options(request))
    except AnalysisStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if rows == 0:
        raise HTTPException(status_code=404, detail=f"No {request.period.value} kline data found for {symbol}")
    normalized_symbol = normalize_stock_symbol(symbol)
    return SyncResponse(
        symbol=normalized_symbol,
        name=resolve_stock_name(normalized_symbol),
        period=request.period,
        rows=rows,
        message="synced",
    )


@router.get("/stocks/{symbol}/chart", response_model=ChartResponse)
def get_chart(
    symbol: str,
    period: KlinePeriod = Query(default=KlinePeriod.DAILY),
    start_date: Optional[date] = Query(default=None, alias="startDate"),
    end_date: Optional[date] = Query(default=None, alias="endDate"),
) -> ChartResponse:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="开始日期不能晚于结束日期")
    try:
        return chart_service.get_chart(symbol, period, start_date, end_date)
    except AnalysisStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/stocks/{symbol}/chan/recalculate")
def recalculate(symbol: str, request: RecalculateRequest) -> dict:
    normalized_symbol = normalize_stock_symbol(symbol)
    try:
        chart = chart_service.recalculate(normalized_symbol, request.period, request.min_kline_gap, request.rule_profile,
                                          **research_options(request))
    except AnalysisStateError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "symbol": normalized_symbol,
        "name": resolve_stock_name(normalized_symbol),
        "period": request.period.value,
        "fractalCount": len(chart.fractals),
        "biCount": len(chart.bis),
        "segmentCount": len(chart.segments),
        "centralZoneCount": len(chart.central_zones),
        "tradingPointCount": len(chart.trading_points),
        "divergenceCount": len(chart.divergences),
        "analysis": chart.analysis.model_dump(mode="json", by_alias=True),
    }


@router.get("/stocks/{symbol}/structure/chart", response_model=ChartResponse)
def hierarchy_chart(symbol: str, period: KlinePeriod = KlinePeriod.DAILY,
                    base_period: Optional[KlinePeriod] = Query(default=None, alias="basePeriod"),
                    max_level: Optional[int] = Query(default=None, ge=1, le=8, alias="maxLevel"),
                    start: Optional[date] = Query(default=None, alias="startDate"),
                    end: Optional[date] = Query(default=None, alias="endDate")):
    if start and end and start>end: raise HTTPException(status_code=422,detail="开始日期不能晚于结束日期")
    try:
        return HierarchyService(chart_service).get(symbol,period,base_period,max_level,start,end)
    except AnalysisStateError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422,detail=str(error)) from error


@router.post("/stocks/{symbol}/structure/recalculate", response_model=ChartResponse)
def hierarchy_recalculate(symbol: str, request: HierarchyRequest):
    try:
        return HierarchyService(chart_service).operate(symbol,request)
    except AnalysisStateError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422,detail=str(error)) from error


@router.post("/stocks/{symbol}/structure/sync", response_model=ChartResponse)
def hierarchy_sync(symbol: str, request: HierarchyRequest):
    try:
        return HierarchyService(chart_service).operate(symbol,request,sync=True)
    except AnalysisStateError as error:
        raise HTTPException(status_code=409,detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422,detail=str(error)) from error
