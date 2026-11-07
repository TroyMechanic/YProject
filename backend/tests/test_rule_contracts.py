import json
import random
from datetime import date, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.schemas import Fractal, Kline, RuleProfile, RuleSettings, SyncRequest
from app.services.chan_analyzer import ChanAnalyzer
from app.services.rule_policy import RULE_VERSION, effective_gap
from app.services.segment_analyzer import SegmentAnalyzer
from test_segment_analyzer import make_bis


def bars(ranges):
    return [Kline(time=date(2024, 1, 1) + timedelta(days=i), open=low, high=high, low=low, close=high)
            for i, (high, low) in enumerate(ranges)]


@pytest.mark.parametrize('profile', list(RuleProfile))
def test_hand_checked_rule_baseline(profile):
    fixture = json.loads((Path(__file__).parent / 'fixtures/rule_baseline.json').read_text())
    assert fixture['ruleVersion'] == RULE_VERSION
    settings = RuleSettings(ruleProfile=profile)
    fractals, bis, segments, zones = ChanAnalyzer().analyze(bars(fixture['ranges']), effective_gap(settings))
    actual = {
        'fractals': [[f.kline_index, f.type.value, f.price] for f in fractals],
        'bis': [[b.start_index, b.end_index, b.start_price, b.end_price, b.direction.value, b.confirmed] for b in bis],
        'segments': len(segments), 'centralZones': len(zones),
    }
    assert actual == fixture['expected'][profile.value]


def test_profile_floor_is_explicit_and_override_only_tightens():
    assert effective_gap(RuleSettings(ruleProfile='legacy', minKlineGap=1)) == 1
    assert effective_gap(RuleSettings(ruleProfile='separated', minKlineGap=1)) == 4
    assert effective_gap(RuleSettings(ruleProfile='separated', minKlineGap=6)) == 6


def test_candidate_extension_keeps_adjacent_strokes_connected():
    def fractal(i, kind, price, high, low):
        return Fractal(time=date(2024, 1, 1) + timedelta(days=i), type=kind, price=price,
                       klineIndex=i, mergedIndex=i, elementHigh=high, elementLow=low)
    source = [fractal(0, 'BOTTOM', 1, 3, 1), fractal(4, 'TOP', 10, 10, 5),
              fractal(5, 'BOTTOM', 6, 11, 6),  # rejected reversal
              fractal(8, 'TOP', 12, 12, 7), fractal(12, 'BOTTOM', 2, 8, 2)]
    bis = ChanAnalyzer().build_bis(source)
    assert len(bis) == 2
    assert bis[0].end_price == bis[1].start_price == 12
    assert bis[0].end_time == bis[1].start_time == source[3].time
    assert bis[0].end_index == bis[1].start_index == 8
    assert any('12.00' in reason for reason in bis[0].reasons)


def test_extension_cannot_invalidate_previous_stroke_range():
    source = [Fractal(time=date(2024, 1, 1) + timedelta(days=i), type=kind, price=price,
                      klineIndex=i, mergedIndex=i, elementHigh=high, elementLow=low)
              for i, kind, price, high, low in [(0,'BOTTOM',1,3,1),(4,'TOP',10,10,5),(8,'TOP',12,12,0)]]
    bis = ChanAnalyzer().build_bis(source)
    assert len(bis) == 1 and bis[0].end_price == 10


@pytest.mark.parametrize('direction', [1, -1])
def test_inclusion_direction_right_ownership_and_source(direction):
    ranges = [(10,5),(12,7),(11,8)] if direction == 1 else [(12,7),(10,5),(9,6)]
    source = bars(ranges)
    merged = ChanAnalyzer().merge_include_klines(source)
    assert len(merged) == 2
    assert (merged[-1].high, merged[-1].low) == ((12,8) if direction == 1 else (9,5))
    assert merged[-1].time == source[-1].time
    assert merged[-1].source_times == [source[1].time, source[2].time]
    assert merged[-1].high_source_time == source[1 if direction == 1 else 2].time
    assert merged[-1].low_source_time == source[2 if direction == 1 else 1].time


def test_equal_fractal_keeps_earlier_one():
    for kind in ['TOP', 'BOTTOM']:
        source = [Fractal(time=date(2024,1,1)+timedelta(days=i), type=kind, price=10, klineIndex=i) for i in [0,2]]
        assert ChanAnalyzer().filter_fractals(source) == [source[0]]


@pytest.mark.parametrize('kwargs', [{'ruleProfile':'unknown'}, {'minKlineGap':0}, {'minKlineGap':21},
                                    {'minKlineGap':1.5}, {'minKlineGap':True}, {'minKlineGapp':4}])
def test_unknown_or_invalid_rule_settings_are_rejected(kwargs):
    with pytest.raises(ValidationError):
        RuleSettings(**kwargs)


def test_invalid_ranges_and_market_data_are_rejected():
    with pytest.raises(ValidationError):
        SyncRequest(startDate='2024-02-01', endDate='2024-01-01')
    for high, low, close in [(10,5,11),(float('nan'),5,8),(10,5,float('inf'))]:
        with pytest.raises(ValidationError):
            Kline(time=date(2024,1,1), open=8, high=high, low=low, close=close)
    with pytest.raises(ValueError, match='严格递增'):
        ChanAnalyzer().analyze(bars([(10,5),(12,7)])[::-1])


def test_seeded_histories_preserve_stroke_continuity_and_confirmed_prefix():
    for seed in range(12):
        rng = random.Random(seed)
        source = bars([(value + 2, value - 2) for value in [rng.randint(10,80) for _ in range(70)]])
        for gap in [1,4]:
            previous = []
            for n in range(3, len(source)+1):
                _, bis, _, _ = ChanAnalyzer().analyze(source[:n], gap)
                for left, right in zip(bis, bis[1:]):
                    assert (left.end_time, left.end_price, left.end_index) == (right.start_time, right.start_price, right.start_index)
                    assert left.direction != right.direction
                confirmed = [b.model_dump(exclude={'reasons', 'confirmed'}) for b in bis if b.confirmed]
                assert confirmed[:len(previous)] == previous
                previous = confirmed


def test_confirmed_segment_endpoints_survive_appended_bis():
    for seed in range(15):
        rng = random.Random(seed)
        points = [1]
        for i in range(60):
            points.append(points[-1] + (1 if i % 2 == 0 else -1) * rng.randint(1,12))
        bis = make_bis(points)
        previous = []
        for n in range(3, len(bis)+1):
            segments = SegmentAnalyzer().build_segments(bis[:n])
            for segment in segments:
                assert (segment.end_price > segment.start_price) == (segment.direction.value == 'UP')
                if segment.confirmed:
                    ends=[b.end_price for b in bis[segment.start_bi_index:segment.end_bi_index+1]]
                    assert segment.end_price == (max(ends) if segment.direction.value=='UP' else min(ends))
            confirmed = [(s.start_bi_index,s.end_bi_index,s.start_price,s.end_price,s.break_type) for s in segments if s.confirmed]
            assert confirmed[:len(previous)] == previous
            previous = confirmed


def test_principle_registry_and_documented_version_stay_linked():
    from app.services.rule_policy import PRINCIPLES
    document = (Path(__file__).resolve().parents[2] / 'docs/chan-rules.md').read_text()
    assert RULE_VERSION in document
    for principle in PRINCIPLES:
        assert f'| {principle} |' in document
