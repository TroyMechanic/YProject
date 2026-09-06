from datetime import date, timedelta

from app.models.schemas import Fractal, FractalType, Kline
from app.services.chan_analyzer import ChanAnalyzer


def make_kline(index: int, high: float, low: float) -> Kline:
    return Kline(
        time=date(2024, 1, 1) + timedelta(days=index),
        open=low,
        high=high,
        low=low,
        close=high,
        volume=100,
    )


def test_detects_fractals_and_builds_bis() -> None:
    klines = [
        make_kline(0, 10, 7),
        make_kline(1, 12, 9),
        make_kline(2, 11, 8),
        make_kline(3, 9, 6),
        make_kline(4, 8, 4),
        make_kline(5, 10, 6),
        make_kline(6, 12, 8),
        make_kline(7, 13, 10),
        make_kline(8, 11, 9),
    ]

    fractals, bis, segments, central_zones = ChanAnalyzer().analyze(klines, min_kline_gap=3)

    assert [item.type for item in fractals] == [FractalType.TOP, FractalType.BOTTOM, FractalType.TOP]
    assert len(bis) == 2
    assert segments == []
    assert central_zones == []
    assert bis[0].direction == "DOWN"
    assert bis[1].direction == "UP"
    assert bis[-1].confirmed is False


def test_continuous_same_type_keeps_more_extreme_fractal() -> None:
    analyzer = ChanAnalyzer()
    fractals = [
        Fractal(time=date(2024, 1, 2), type=FractalType.TOP, price=12, klineIndex=1, mergedIndex=1),
        Fractal(time=date(2024, 1, 4), type=FractalType.TOP, price=13, klineIndex=3, mergedIndex=3),
    ]

    filtered = analyzer.filter_fractals(fractals)

    assert len(filtered) == 1
    assert filtered[0].type == FractalType.TOP
    assert filtered[0].price == 13


def test_top_fractal_elements_must_not_break_bottom_low() -> None:
    analyzer = ChanAnalyzer()
    fractals = [
        Fractal(time=date(2024, 1, 1), type=FractalType.BOTTOM, price=10, klineIndex=0, mergedIndex=0, elementHigh=12, elementLow=10),
        Fractal(time=date(2024, 1, 6), type=FractalType.TOP, price=20, klineIndex=5, mergedIndex=5, elementHigh=20, elementLow=9),
        Fractal(time=date(2024, 1, 10), type=FractalType.TOP, price=21, klineIndex=9, mergedIndex=9, elementHigh=21, elementLow=11),
    ]

    bis = analyzer.build_bis(fractals, min_kline_gap=3)

    assert len(bis) == 1
    assert bis[0].end_price == 21


def test_bottom_fractal_elements_must_not_break_top_high() -> None:
    analyzer = ChanAnalyzer()
    fractals = [
        Fractal(time=date(2024, 1, 1), type=FractalType.TOP, price=20, klineIndex=0, mergedIndex=0, elementHigh=20, elementLow=18),
        Fractal(time=date(2024, 1, 6), type=FractalType.BOTTOM, price=10, klineIndex=5, mergedIndex=5, elementHigh=21, elementLow=10),
        Fractal(time=date(2024, 1, 10), type=FractalType.BOTTOM, price=9, klineIndex=9, mergedIndex=9, elementHigh=19, elementLow=9),
    ]

    bis = analyzer.build_bis(fractals, min_kline_gap=3)

    assert len(bis) == 1
    assert bis[0].end_price == 9


def test_bi_range_rule_requires_strict_price_break() -> None:
    analyzer = ChanAnalyzer()
    equal_high_fractals = [
        Fractal(time=date(2024, 1, 1), type=FractalType.BOTTOM, price=10, klineIndex=0, mergedIndex=0, elementHigh=20, elementLow=10),
        Fractal(time=date(2024, 1, 6), type=FractalType.TOP, price=20, klineIndex=5, mergedIndex=5, elementHigh=20, elementLow=11),
    ]
    equal_low_fractals = [
        Fractal(time=date(2024, 1, 1), type=FractalType.TOP, price=20, klineIndex=0, mergedIndex=0, elementHigh=20, elementLow=10),
        Fractal(time=date(2024, 1, 6), type=FractalType.BOTTOM, price=10, klineIndex=5, mergedIndex=5, elementHigh=19, elementLow=10),
    ]

    assert analyzer.build_bis(equal_high_fractals, min_kline_gap=1) == []
    assert analyzer.build_bis(equal_low_fractals, min_kline_gap=1) == []


def test_bi_gap_uses_merged_kline_index() -> None:
    analyzer = ChanAnalyzer()
    fractals = [
        Fractal(time=date(2024, 1, 1), type=FractalType.BOTTOM, price=10, klineIndex=0, mergedIndex=0, elementHigh=12, elementLow=10),
        Fractal(time=date(2024, 1, 10), type=FractalType.TOP, price=20, klineIndex=9, mergedIndex=1, elementHigh=20, elementLow=11),
    ]

    assert analyzer.build_bis(fractals, min_kline_gap=2) == []
    assert len(analyzer.build_bis(fractals, min_kline_gap=1)) == 1
