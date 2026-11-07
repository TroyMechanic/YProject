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


def test_boundary_inclusion_does_not_swallow_reverse_segment() -> None:
    # The second down feature engulfs the first across the hypothesized peak.
    # Conventional max/max merging loses the left support entirely.
    for sign in (1, -1):
        bis = make_bis([sign * v for v in [54.05, 55.63, 55.32, 55.79, 54.88, 55.26, 54.69]])
        result = SegmentAnalyzer().build_segments(bis)
        assert result[0].confirmed
        assert result[0].end_price == sign * 55.79
        assert result[0].confirmation_bi_index == 5
        assert result[0].feature_sequence[0].source_bi_indices == [1]
        assert result[0].feature_sequence[1].source_bi_indices == [3]
        assert any('跨段包含' in r for r in result[0].reasons)
        bis[-1].confirmed = False
        assert not SegmentAnalyzer().build_segments(bis)[0].confirmed


def test_boundary_first_break_alone_does_not_confirm_a_segment() -> None:
    for last in (54.88, 54.95):  # Touching and inside the first reverse stroke.
        bis = make_bis([54.05, 55.63, 55.32, 55.79, 54.88, 55.26, last])
        assert not SegmentAnalyzer().build_segments(bis)[0].confirmed


def test_contained_reverse_third_waits_for_later_break_or_original_resumption():
    for sign in (1,-1):
        bis=make_bis([sign*v for v in [1,10,9,12,7,11,8,10,6]])
        result=SegmentAnalyzer().build_segments(bis)
        assert result[0].confirmed and result[0].end_price==sign*12
        assert result[0].confirmation_bi_index==7
        assert not SegmentAnalyzer().build_segments(bis[:6])[0].confirmed
        resumed=make_bis([sign*v for v in [1,10,9,12,7,11,8,13,6]])
        assert not SegmentAnalyzer().build_segments(resumed)[0].confirmed


def test_initial_overlap_without_directional_extension_does_not_seed_wrong_segment():
    for sign in (1,-1):
        # Real Tongfu opening fragment: the third up stroke misses the first high.
        bis=make_bis([sign*v for v in [61.86,62.57,61.3,62.42,59.54]])
        result=SegmentAnalyzer().build_segments(bis)
        assert len(result)==1 and result[0].start_bi_index==1
        assert result[0].direction==(BiDirection.DOWN if sign==1 else BiDirection.UP)
        assert result[0].end_price==sign*59.54
        for endpoint in (10,9):
            assert SegmentAnalyzer().build_segments(make_bis([sign*v for v in [1,10,5,endpoint]]))==[]
