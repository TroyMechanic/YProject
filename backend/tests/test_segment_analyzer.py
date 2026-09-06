from datetime import date, timedelta

from app.models.schemas import Bi, BiDirection, SegmentBreakType
from app.services.segment_analyzer import SegmentAnalyzer


def make_bis(points: list[float]) -> list[Bi]:
    result: list[Bi] = []
    for index, (start, end) in enumerate(zip(points, points[1:])):
        result.append(
            Bi(
                startTime=date(2024, 1, 1) + timedelta(days=index),
                endTime=date(2024, 1, 2) + timedelta(days=index),
                startPrice=start,
                endPrice=end,
                direction=BiDirection.UP if end > start else BiDirection.DOWN,
                startIndex=index,
                endIndex=index + 1,
                confirmed=True,
            )
        )
    return result


def test_no_gap_feature_fractal_confirms_segment() -> None:
    bis = make_bis([1, 10, 5, 12, 8, 11, 7])

    segments = SegmentAnalyzer().build_segments(bis)

    assert len(segments) == 2
    assert segments[0].direction == BiDirection.UP
    assert segments[0].start_bi_index == 0
    assert segments[0].end_bi_index == 2
    assert segments[0].end_price == 12
    assert segments[0].confirmed is True
    assert segments[0].break_type == SegmentBreakType.NO_GAP
    assert segments[1].direction == BiDirection.DOWN
    assert segments[1].confirmed is False


def test_gap_feature_fractal_requires_reverse_confirmation() -> None:
    bis = make_bis([1, 10, 5, 15, 12, 14, 7, 11, 9, 12])

    segments = SegmentAnalyzer().build_segments(bis)

    assert segments[0].direction == BiDirection.UP
    assert segments[0].end_price == 15
    assert segments[0].confirmed is True
    assert segments[0].break_type == SegmentBreakType.GAP_CONFIRMED
    assert any("二次确认" in reason for reason in segments[0].reasons)


def test_gap_feature_fractal_stays_unconfirmed_without_reverse_fractal() -> None:
    bis = make_bis([1, 10, 5, 15, 12, 14, 7])

    segments = SegmentAnalyzer().build_segments(bis)

    assert len(segments) == 1
    assert segments[0].direction == BiDirection.UP
    assert segments[0].confirmed is False
    assert segments[0].break_type == SegmentBreakType.UNCONFIRMED


def test_later_feature_inclusion_does_not_rewrite_confirmed_segment() -> None:
    bis = make_bis([1, 10, 5, 12, 8, 11, 7, 13, 6])

    segments = SegmentAnalyzer().build_segments(bis)

    assert segments[0].confirmed is True
    assert segments[0].break_type == SegmentBreakType.NO_GAP
    assert segments[0].end_price == 12


def test_three_bis_without_price_overlap_do_not_form_segment() -> None:
    bis = make_bis([1, 3, 4, 6])

    assert SegmentAnalyzer().build_segments(bis) == []
