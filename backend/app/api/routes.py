from __future__ import annotations

from datetime import date
from typing import Optional, Union

from fastapi import APIRouter, HTTPException, Query

from app.models.schemas import ChartResponse, KlinePeriod, RecalculateRequest, SyncRequest, SyncResponse
from app.services.chart_service import ChartService
from app.services.stock_info import normalize_stock_symbol, resolve_stock_name


router = APIRouter(prefix="/api")
chart_service = ChartService()


@router.post("/stocks/{symbol}/sync", response_model=SyncResponse)
def sync_stock(symbol: str, request: SyncRequest) -> SyncResponse:
    rows = chart_service.sync(symbol, request.period, request.start_date, request.end_date)
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
    return chart_service.get_chart(symbol, period, start_date, end_date)


@router.post("/stocks/{symbol}/chan/recalculate")
def recalculate(symbol: str, request: RecalculateRequest) -> dict[str, Union[int, str]]:
    normalized_symbol = normalize_stock_symbol(symbol)
    klines = chart_service.store.load_klines(normalized_symbol, request.period, request.start_date, request.end_date)
    fractal_count, bi_count, segment_count, central_zone_count = chart_service.recalculate(
        normalized_symbol,
        request.period,
        klines,
        request.min_kline_gap,
    )
    return {
        "symbol": normalized_symbol,
        "name": resolve_stock_name(normalized_symbol),
        "period": request.period.value,
        "fractalCount": fractal_count,
        "biCount": bi_count,
        "segmentCount": segment_count,
        "centralZoneCount": central_zone_count,
    }
