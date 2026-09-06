from datetime import date, timedelta

from app.models.schemas import BiDirection, CentralZoneStatus, Segment, SegmentBreakType
from app.services.central_zone_analyzer import CentralZoneAnalyzer


def make_segment(index: int, start: float, end: float, confirmed: bool = True) -> Segment:
    return Segment(
        startTime=date(2024, 1, 1) + timedelta(days=index),
        endTime=date(2024, 1, 2) + timedelta(days=index),
        startPrice=start,
        endPrice=end,
        direction=BiDirection.UP if end > start else BiDirection.DOWN,
        startBiIndex=index * 3,
        endBiIndex=index * 3 + 2,
        biCount=3,
        confirmed=confirmed,
        breakType=SegmentBreakType.NO_GAP if confirmed else SegmentBreakType.UNCONFIRMED,
    )


def test_three_confirmed_segments_form_strict_central_zone() -> None:
    segments = [
        make_segment(0, 1, 10),
        make_segment(1, 10, 5),
        make_segment(2, 5, 12),
    ]

    zones = CentralZoneAnalyzer().build_central_zones(segments)

    assert len(zones) == 1
    assert zones[0].zd == 5
    assert zones[0].zg == 10
    assert zones[0].dd == 1
    assert zones[0].gg == 12
    assert zones[0].status == CentralZoneStatus.EXTENDING


def test_zone_extension_keeps_initial_zd_and_zg() -> None:
    segments = [
        make_segment(0, 1, 10),
        make_segment(1, 10, 5),
        make_segment(2, 5, 12),
        make_segment(3, 12, 7),
        make_segment(4, 7, 14),
        make_segment(5, 14, 11),
    ]

    zones = CentralZoneAnalyzer().build_central_zones(segments)

    assert len(zones) == 1
    assert zones[0].zd == 5
    assert zones[0].zg == 10
    assert zones[0].dd == 1
    assert zones[0].gg == 14
    assert zones[0].segment_count == 5
    assert zones[0].status == CentralZoneStatus.LEFT_UP


def test_point_contact_does_not_form_central_zone() -> None:
    segments = [
        make_segment(0, 1, 5),
        make_segment(1, 10, 5),
        make_segment(2, 3, 5),
    ]

    assert CentralZoneAnalyzer().build_central_zones(segments) == []


def test_unconfirmed_segment_cannot_confirm_central_zone() -> None:
    segments = [
        make_segment(0, 1, 10),
        make_segment(1, 10, 5),
        make_segment(2, 5, 12, confirmed=False),
    ]

    assert CentralZoneAnalyzer().build_central_zones(segments) == []


def test_confirmed_segment_can_leave_zone_downward() -> None:
    segments = [
        make_segment(0, 4, 12),
        make_segment(1, 12, 7),
        make_segment(2, 7, 14),
        make_segment(3, 6, 1),
    ]

    zones = CentralZoneAnalyzer().build_central_zones(segments)

    assert len(zones) == 1
    assert zones[0].status == CentralZoneStatus.LEFT_DOWN

