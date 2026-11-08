from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ChartResponse, KlinePeriod, RecalculateRequest, SyncRequest, SyncResponse
from app.services.chart_service import AnalysisStateError, ChartService
from app.services.rule_policy import rule_catalog
from app.services.stock_info import normalize_stock_symbol, resolve_stock_name


router = APIRouter(prefix="/api")
chart_service = ChartService()


@router.get("/chan/rules")
def get_rules() -> dict:
    return rule_catalog()


@router.post("/stocks/{symbol}/sync", response_model=SyncResponse)
def sync_stock(symbol: str, request: SyncRequest) -> SyncResponse:
    try:
        rows = chart_service.sync(symbol, request.period, request.start_date, request.end_date,
                                  request.rule_profile, request.min_kline_gap)
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
        chart = chart_service.recalculate(normalized_symbol, request.period, request.min_kline_gap, request.rule_profile)
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
        "analysis": chart.analysis.model_dump(mode="json", by_alias=True),
    }
