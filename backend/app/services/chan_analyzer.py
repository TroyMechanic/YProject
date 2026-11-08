from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import Bi, BiDirection,  Fractal, FractalElement, FractalType, Kline, Segment
from app.services.segment_analyzer import SegmentAnalyzer


@dataclass(frozen=True)
class MergedKline:
    time: object
    high: float
    low: float
    original_index: int
    source_times: list[object]
    high_source_time: object
    low_source_time: object


class ChanAnalyzer:
    def analyze(
        self,
        klines: list[Kline],
        min_kline_gap: int = 1,
    ) -> tuple[list[Fractal], list[Bi], list[Segment]]:
        if not 1 <= min_kline_gap <= 20:
            raise ValueError("标准K线最小间隔必须在1至20之间")
        if any(left.time >= right.time for left, right in zip(klines, klines[1:])):
            raise ValueError("K线时间必须严格递增且不重复")
        merged = self.merge_include_klines(klines)
        fractals = self.detect_fractals(merged)
        valid_fractals = self.filter_fractals(fractals)
        # The last standard candle can still change through inclusion. A
        # fractal using it as right support cannot lock an earlier stroke yet.
        stable_fractals = self.stroke_fractals(fractals, merged)
        bis = self.build_bis(stable_fractals, min_kline_gap)
        segments = SegmentAnalyzer().build_segments(bis)
        # Preserve evidence as it was first observable, before later inclusions.
        confirmed_segments = {}
        segment_start = None
        final_keys = {(s.start_time, s.end_time) for s in segments if s.confirmed}
        for fractal, strokes in self.bi_updates(stable_fractals, min_kline_gap):
            observed = klines[fractal.elements[-1].kline_index + 1].time
            if len(strokes) >= 2:
                previous = bis[len(strokes) - 2]
                if previous.confirmed_at is None:
                    previous.confirmed_at = observed
            if final_keys:
                for segment in SegmentAnalyzer().build_segments(strokes, segment_start):
                    key = (segment.start_time, segment.end_time)
                    if segment.confirmed and key in final_keys:
                        segment.confirmed_at = observed
                        confirmed_segments[key] = segment
                        final_keys.remove(key)
                        segment_start = segment.end_bi_index + 1
        return valid_fractals, bis, [confirmed_segments.get((s.start_time, s.end_time), s) for s in segments]

    @staticmethod
    def stroke_fractals(fractals: list[Fractal], merged: list[MergedKline]) -> list[Fractal]:
        if not merged:
            return []
        last = merged[-1].original_index
        return [f for f in fractals if f.elements and f.elements[-1].kline_index < last]

    def merge_include_klines(self, klines: list[Kline]) -> list[MergedKline]:
        merged: list[MergedKline] = []
        for index, item in enumerate(klines):
            current = MergedKline(
                time=item.time,
                high=item.high,
                low=item.low,
                original_index=index,
                source_times=[item.time],
                high_source_time=item.time,
                low_source_time=item.time,
            )
            if not merged:
                merged.append(current)
                continue

            last = merged[-1]
            if not self._has_include_relation(last, current):
                merged.append(current)
                continue

            direction = self._detect_direction(merged)
            if direction >= 0:
                high, high_source_time = self._pick_max_high(last, current)
                low, low_source_time = self._pick_max_low(last, current)
                combined = MergedKline(
                    time=current.time,
                    high=high,
                    low=low,
                    original_index=current.original_index,
                    source_times=[*last.source_times, *current.source_times],
                    high_source_time=high_source_time,
                    low_source_time=low_source_time,
                )
            else:
                high, high_source_time = self._pick_min_high(last, current)
                low, low_source_time = self._pick_min_low(last, current)
                combined = MergedKline(
                    time=current.time,
                    high=high,
                    low=low,
                    original_index=current.original_index,
                    source_times=[*last.source_times, *current.source_times],
                    high_source_time=high_source_time,
                    low_source_time=low_source_time,
                )
            merged[-1] = combined
        return merged

    def detect_fractals(self, klines: list[MergedKline]) -> list[Fractal]:
        result: list[Fractal] = []
        for index in range(1, len(klines) - 1):
            prev = klines[index - 1]
            curr = klines[index]
            next_item = klines[index + 1]
            elements = self._build_fractal_elements(prev, curr, next_item)

            if curr.high > prev.high and curr.high > next_item.high and curr.low > prev.low and curr.low > next_item.low:
                element_high = max(prev.high, curr.high, next_item.high)
                element_low = min(prev.low, curr.low, next_item.low)
                result.append(
                    Fractal(
                        time=curr.time,
                        type=FractalType.TOP,
                        price=curr.high,
                        klineIndex=curr.original_index,
                        mergedIndex=index,
                        elementHigh=element_high,
                        elementLow=element_low,
                        elements=elements,
                        reasons=[
                            f"由 {prev.time}、{curr.time}、{next_item.time} 三根标准K线形成",
                            f"中间K线高点 {curr.high:.2f} 同时高于左侧 {prev.high:.2f} 和右侧 {next_item.high:.2f}",
                            f"中间K线低点 {curr.low:.2f} 同时高于左侧 {prev.low:.2f} 和右侧 {next_item.low:.2f}",
                            f"三元素范围：最高 {element_high:.2f}，最低 {element_low:.2f}",
                        ],
                    )
                )
            elif curr.low < prev.low and curr.low < next_item.low and curr.high < prev.high and curr.high < next_item.high:
                element_high = max(prev.high, curr.high, next_item.high)
                element_low = min(prev.low, curr.low, next_item.low)
                result.append(
                    Fractal(
                        time=curr.time,
                        type=FractalType.BOTTOM,
                        price=curr.low,
                        klineIndex=curr.original_index,
                        mergedIndex=index,
                        elementHigh=element_high,
                        elementLow=element_low,
                        elements=elements,
                        reasons=[
                            f"由 {prev.time}、{curr.time}、{next_item.time} 三根标准K线形成",
                            f"中间K线低点 {curr.low:.2f} 同时低于左侧 {prev.low:.2f} 和右侧 {next_item.low:.2f}",
                            f"中间K线高点 {curr.high:.2f} 同时低于左侧 {prev.high:.2f} 和右侧 {next_item.high:.2f}",
                            f"三元素范围：最高 {element_high:.2f}，最低 {element_low:.2f}",
                        ],
                    )
                )
        return result

    def filter_fractals(self, fractals: list[Fractal]) -> list[Fractal]:
        filtered: list[Fractal] = []
        for item in fractals:
            if not filtered:
                filtered.append(item)
                continue

            last = filtered[-1]
            if item.type != last.type:
                filtered.append(item)
                continue

            if self._is_more_extreme(item, last):
                filtered[-1] = item
        return filtered

    def build_bis(self, fractals: list[Fractal], min_kline_gap: int = 1) -> list[Bi]:
        bis: list[Bi] = []
        for _, bis in self.bi_updates(fractals, min_kline_gap):
            pass
        if bis:
            bis[-1].reasons.append("当前笔已成立，终点可随新极值延伸，待下一笔成立时锁定")
        return bis

    def bi_updates(self, fractals: list[Fractal], min_kline_gap: int):
        """Yield the current strokes whenever a finalized fractal changes their geometry."""
        bis: list[Bi] = []
        last: Fractal | None = None
        last_start: Fractal | None = None

        for item in fractals:
            if last is None:
                last = item
                continue

            if item.type == last.type:
                if self._is_more_extreme(item, last):
                    if bis and last_start is not None:
                        if not self._satisfies_bi_range_rule(last_start, item):
                            continue
                        previous = bis[-1]
                        previous.end_time = item.time
                        previous.end_price = item.price
                        previous.end_index = item.kline_index
                        previous.reasons = self._build_bi_reasons(last_start, item, min_kline_gap, previous.direction)
                    last = item
                    if bis:
                        yield item, bis
                continue

            if self._merged_gap(last, item) < min_kline_gap:
                continue

            if not self._satisfies_bi_range_rule(last, item):
                continue

            direction = BiDirection.UP if last.type == FractalType.BOTTOM else BiDirection.DOWN
            bi = Bi(
                startTime=last.time,
                endTime=item.time,
                startPrice=last.price,
                endPrice=item.price,
                direction=direction,
                startIndex=last.kline_index,
                endIndex=item.kline_index,
                confirmed=False,
                reasons=self._build_bi_reasons(last, item, min_kline_gap, direction),
            )
            if bis:
                bis[-1].confirmed = True
            bis.append(bi)
            last_start = last
            last = item
            yield item, bis

    def _build_bi_reasons(
        self,
        left: Fractal,
        right: Fractal,
        min_kline_gap: int,
        direction: BiDirection,
    ) -> list[str]:
        top = left if left.type == FractalType.TOP else right
        bottom = left if left.type == FractalType.BOTTOM else right
        top_element_low = top.element_low if top.element_low is not None else top.price
        bottom_element_high = bottom.element_high if bottom.element_high is not None else bottom.price
        return [
            f"{left.type.value} 与 {right.type.value} 顶底交替",
            f"分型间隔 {self._merged_gap(left, right)} 根标准K线，满足最小间隔 {min_kline_gap}",
            f"方向判定为 {'向上笔' if direction == BiDirection.UP else '向下笔'}",
            f"顶分型最高点 {top.price:.2f} > 底分型三元素最高点 {bottom_element_high:.2f}",
            f"底分型最低点 {bottom.price:.2f} < 顶分型三元素最低点 {top_element_low:.2f}",
        ]

    @staticmethod
    def _build_fractal_elements(left: MergedKline, middle: MergedKline, right: MergedKline) -> list[FractalElement]:
        return [
            FractalElement(
                time=item.time,
                klineIndex=item.original_index,
                high=item.high,
                low=item.low,
                sourceTimes=item.source_times,
                highSourceTime=item.high_source_time,
                lowSourceTime=item.low_source_time,
            )
            for item in (left, middle, right)
        ]

    @staticmethod
    def _pick_max_high(left: MergedKline, right: MergedKline) -> tuple[float, object]:
        return (left.high, left.high_source_time) if left.high >= right.high else (right.high, right.high_source_time)

    @staticmethod
    def _pick_max_low(left: MergedKline, right: MergedKline) -> tuple[float, object]:
        return (left.low, left.low_source_time) if left.low >= right.low else (right.low, right.low_source_time)

    @staticmethod
    def _pick_min_high(left: MergedKline, right: MergedKline) -> tuple[float, object]:
        return (left.high, left.high_source_time) if left.high <= right.high else (right.high, right.high_source_time)

    @staticmethod
    def _pick_min_low(left: MergedKline, right: MergedKline) -> tuple[float, object]:
        return (left.low, left.low_source_time) if left.low <= right.low else (right.low, right.low_source_time)

    @staticmethod
    def _has_include_relation(left: MergedKline, right: MergedKline) -> bool:
        return (left.high >= right.high and left.low <= right.low) or (left.high <= right.high and left.low >= right.low)

    @staticmethod
    def _detect_direction(merged: list[MergedKline]) -> int:
        if len(merged) < 2:
            return 1
        prev = merged[-2]
        last = merged[-1]
        if last.high > prev.high and last.low > prev.low:
            return 1
        if last.high < prev.high and last.low < prev.low:
            return -1
        return 1

    @staticmethod
    def _is_more_extreme(current: Fractal, last: Fractal) -> bool:
        if current.type == FractalType.TOP:
            return current.price > last.price
        return current.price < last.price

    @staticmethod
    def _satisfies_bi_range_rule(left: Fractal, right: Fractal) -> bool:
        top = left if left.type == FractalType.TOP else right
        bottom = left if left.type == FractalType.BOTTOM else right
        top_element_low = top.element_low if top.element_low is not None else top.price
        bottom_element_high = bottom.element_high if bottom.element_high is not None else bottom.price
        return top.price > bottom_element_high and bottom.price < top_element_low

    @staticmethod
    def _merged_gap(left: Fractal, right: Fractal) -> int:
        return right.merged_index - left.merged_index
