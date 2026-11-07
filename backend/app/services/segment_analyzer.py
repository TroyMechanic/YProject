from __future__ import annotations

from dataclasses import dataclass

from app.models.schemas import (
    Bi,
    BiDirection,
    FeatureSequenceElement,
    Segment,
    SegmentBreakType,
)


@dataclass(frozen=True)
class _Feature:
    high: float
    low: float
    start_bi_index: int
    end_bi_index: int
    source_bi_indices: tuple[int, ...]
    high_source_bi_index: int
    low_source_bi_index: int


@dataclass(frozen=True)
class _SegmentEnd:
    turn_bi_index: int
    break_type: SegmentBreakType
    features: list[_Feature]
    feature_middle_index: int
    confirmation_bi_index: int
    boundary_inclusion: bool = False


class SegmentAnalyzer:
    def build_segments(self, bis: list[Bi]) -> list[Segment]:
        if len(bis) < 3:
            return []

        segments: list[Segment] = []
        start_bi_index = self._find_initial_start(bis, 0)

        while start_bi_index is not None and start_bi_index + 2 < len(bis):
            direction = bis[start_bi_index].direction
            segment_end = self._find_confirmed_end(bis, start_bi_index, direction)
            if segment_end is None:
                segments.append(self._build_unconfirmed_segment(bis, start_bi_index, direction))
                break

            segment = self._build_confirmed_segment(bis, start_bi_index, direction, segment_end)
            segments.append(segment)
            start_bi_index = segment_end.turn_bi_index

            if not self._valid_initial_triplet(bis, start_bi_index):
                break

        return segments

    def _find_confirmed_end(
        self,
        bis: list[Bi],
        start_bi_index: int,
        direction: BiDirection,
    ) -> _SegmentEnd | None:
        features: list[_Feature] = []
        for raw_feature in self._raw_features(bis, start_bi_index, direction):
            boundary = self._boundary_inclusion_end(
                bis, start_bi_index, direction, raw_feature.end_bi_index
            )
            if boundary is not None:
                return boundary
            self._append_standardized_feature(features, raw_feature, direction)
            for middle_index in self._feature_fractal_indices(features, direction):
                left = features[middle_index - 1]
                middle = features[middle_index]
                right = features[middle_index + 1]
                turn_bi_index = (
                    middle.high_source_bi_index
                    if direction == BiDirection.UP
                    else middle.low_source_bi_index
                )
                if turn_bi_index - start_bi_index < 3:
                    continue
                prices = [b.start_price for b in bis[start_bi_index:turn_bi_index + 1]]
                if direction == BiDirection.UP and (bis[turn_bi_index].start_price != max(prices)
                                                     or bis[turn_bi_index].start_price <= bis[start_bi_index].start_price):
                    continue
                if direction == BiDirection.DOWN and (bis[turn_bi_index].start_price != min(prices)
                                                       or bis[turn_bi_index].start_price >= bis[start_bi_index].start_price):
                    continue
                if not self._features_confirmed(bis, (left, middle, right)):
                    continue
                if not self._valid_initial_triplet(bis, turn_bi_index):
                    continue

                has_gap = self._has_gap(left, middle, direction)
                if not has_gap:
                    return _SegmentEnd(
                        turn_bi_index=turn_bi_index,
                        break_type=SegmentBreakType.NO_GAP,
                        features=features[: middle_index + 2],
                        feature_middle_index=middle_index,
                        confirmation_bi_index=max(max(f.source_bi_indices) for f in (left, middle, right)),
                    )

                reverse_confirmation = self._reverse_confirmation_index(bis, turn_bi_index, direction)
                if reverse_confirmation is not None:
                    return _SegmentEnd(
                        turn_bi_index=turn_bi_index,
                        break_type=SegmentBreakType.GAP_CONFIRMED,
                        features=features[: middle_index + 2],
                        feature_middle_index=middle_index,
                        confirmation_bi_index=max(reverse_confirmation, max(max(f.source_bi_indices) for f in (left, middle, right))),
                    )
                # The earliest valid gap candidate owns the decision. Confirming a later
                # no-gap candidate now would rewrite history when this gap confirms later.
                return None
        return None

    def _boundary_inclusion_end(
        self, bis: list[Bi], start: int, direction: BiDirection, available: int
    ) -> _SegmentEnd | None:
        """Lesson 71: do not merge across a hypothesized segment boundary.

        A first reverse stroke breaking the last feature, followed by an
        overlapping reverse triplet and a further reverse extreme (possibly
        after a contained third stroke), confirms that boundary. Only completed
        strokes in the observed prefix are used.
        """
        for turn in range(start + 3, available - 1, 2):
            if not self._valid_initial_triplet(bis, turn):
                continue
            before = self._standardize_features(bis[:turn], start, direction)
            if not before:
                continue
            left = before[-1]
            middle = self._feature_from_bi(bis[turn], turn)
            if not self._has_include_relation(left, middle):
                continue
            if direction == BiDirection.UP:
                valid = (middle.high > left.high and middle.low < left.low
                         and middle.high == max(b.start_price for b in bis[start:turn + 1]))
            else:
                valid = (middle.low < left.low and middle.high > left.high
                         and middle.low == min(b.start_price for b in bis[start:turn + 1]))
            if not valid:
                continue
            # A contained third stroke is undecided: continue until the first
            # reverse extreme is broken, or the original direction resumes.
            for index in range(turn + 1, available + 1):
                endpoint = bis[index].end_price
                resumed = endpoint > middle.high if direction == BiDirection.UP else endpoint < middle.low
                if resumed:
                    break
                broken = endpoint < middle.low if direction == BiDirection.UP else endpoint > middle.high
                if index >= turn + 2 and broken:
                    if all(b.confirmed for b in bis[start:index + 1]):
                        right = self._feature_from_bi(bis[index], index)
                        return _SegmentEnd(turn, SegmentBreakType.NO_GAP,
                                           before + [middle, right], len(before), index, True)
                    break
        return None

    def _reverse_confirmation_index(
        self,
        bis: list[Bi],
        turn_bi_index: int,
        original_direction: BiDirection,
    ) -> int | None:
        if not self._valid_initial_triplet(bis, turn_bi_index):
            return None

        reverse_direction = self._opposite(original_direction)
        reverse_features: list[_Feature] = []
        for raw_feature in self._raw_features(bis, turn_bi_index, reverse_direction):
            self._append_standardized_feature(reverse_features, raw_feature, reverse_direction)
            for middle_index in self._feature_fractal_indices(reverse_features, reverse_direction):
                triple = (
                    reverse_features[middle_index - 1],
                    reverse_features[middle_index],
                    reverse_features[middle_index + 1],
                )
                if self._features_confirmed(bis, triple):
                    return max(max(f.source_bi_indices) for f in triple)
        return None

    def _build_confirmed_segment(
        self,
        bis: list[Bi],
        start_bi_index: int,
        direction: BiDirection,
        segment_end: _SegmentEnd,
    ) -> Segment:
        turn_bi = bis[segment_end.turn_bi_index]
        overlap_low, overlap_high = self._triplet_overlap(bis, start_bi_index)
        feature_type = "顶分型" if direction == BiDirection.UP else "底分型"
        reasons = [
            f"由第 {start_bi_index + 1} 至第 {segment_end.turn_bi_index} 笔构成，共 {segment_end.turn_bi_index - start_bi_index} 笔",
            f"前三笔存在价格重叠区间 {overlap_low:.2f} 至 {overlap_high:.2f}",
            f"{'向上' if direction == BiDirection.UP else '向下'}线段取"
            f"{'向下' if direction == BiDirection.UP else '向上'}笔组成特征序列",
            ("转折边界不做跨段包含合并；反向前三笔重叠，第三笔或后续笔先突破第一笔终点"
             if segment_end.boundary_inclusion else f"标准特征序列形成{feature_type}"),
        ]
        if segment_end.break_type == SegmentBreakType.NO_GAP:
            reasons.append("边界元素无缺口，反向线段确认形成" if segment_end.boundary_inclusion
                           else "特征序列分型第一、第二元素之间无缺口，线段在分型极值处确认结束")
        else:
            reasons.append("特征序列分型第一、第二元素之间存在缺口")
            reasons.append("反向候选线段的标准特征序列已形成对应分型，完成二次确认")

        return Segment(
            startTime=bis[start_bi_index].start_time,
            endTime=turn_bi.start_time,
            startPrice=bis[start_bi_index].start_price,
            endPrice=turn_bi.start_price,
            direction=direction,
            startBiIndex=start_bi_index,
            endBiIndex=segment_end.turn_bi_index - 1,
            biCount=segment_end.turn_bi_index - start_bi_index,
            confirmed=True,
            breakType=segment_end.break_type,
            featureSequence=self._to_schema_features(segment_end.features, direction),
            reasons=reasons,
            confirmationBiIndex=segment_end.confirmation_bi_index,
        )

    def _build_unconfirmed_segment(
        self,
        bis: list[Bi],
        start_bi_index: int,
        direction: BiDirection,
    ) -> Segment:
        same_direction_indices = [
            index
            for index in range(start_bi_index, len(bis))
            if bis[index].direction == direction
        ]
        if direction == BiDirection.UP:
            end_bi_index = max(same_direction_indices, key=lambda index: bis[index].end_price)
        else:
            end_bi_index = min(same_direction_indices, key=lambda index: bis[index].end_price)

        overlap_low, overlap_high = self._triplet_overlap(bis, start_bi_index)
        features = self._standardize_features(bis, start_bi_index, direction)
        return Segment(
            startTime=bis[start_bi_index].start_time,
            endTime=bis[end_bi_index].end_time,
            startPrice=bis[start_bi_index].start_price,
            endPrice=bis[end_bi_index].end_price,
            direction=direction,
            startBiIndex=start_bi_index,
            endBiIndex=end_bi_index,
            biCount=end_bi_index - start_bi_index + 1,
            confirmed=False,
            breakType=SegmentBreakType.UNCONFIRMED,
            featureSequence=self._to_schema_features(features, direction),
            reasons=[
                f"候选线段前三笔存在价格重叠区间 {overlap_low:.2f} 至 {overlap_high:.2f}",
                "尚未出现满足严格特征序列规则的确认破坏",
                "后续笔可能延伸当前线段或确认新的反向线段",
            ],
        )

    def _standardize_features(
        self,
        bis: list[Bi],
        start_bi_index: int,
        segment_direction: BiDirection,
    ) -> list[_Feature]:
        standardized: list[_Feature] = []
        for current in self._raw_features(bis, start_bi_index, segment_direction):
            self._append_standardized_feature(standardized, current, segment_direction)
        return standardized

    def _raw_features(
        self,
        bis: list[Bi],
        start_bi_index: int,
        segment_direction: BiDirection,
    ) -> list[_Feature]:
        feature_direction = self._opposite(segment_direction)
        return [
            self._feature_from_bi(bi, index)
            for index, bi in enumerate(bis[start_bi_index + 1 :], start=start_bi_index + 1)
            if bi.direction == feature_direction
        ]

    def _append_standardized_feature(
        self,
        standardized: list[_Feature],
        current: _Feature,
        segment_direction: BiDirection,
    ) -> None:
        if not standardized or not self._has_include_relation(standardized[-1], current):
            standardized.append(current)
            return
        standardized[-1] = self._merge_feature(standardized[-1], current, segment_direction)

    @staticmethod
    def _feature_from_bi(bi: Bi, bi_index: int) -> _Feature:
        high = max(bi.start_price, bi.end_price)
        low = min(bi.start_price, bi.end_price)
        return _Feature(
            high=high,
            low=low,
            start_bi_index=bi_index,
            end_bi_index=bi_index,
            source_bi_indices=(bi_index,),
            high_source_bi_index=bi_index,
            low_source_bi_index=bi_index,
        )

    def _merge_feature(
        self,
        left: _Feature,
        right: _Feature,
        segment_direction: BiDirection,
    ) -> _Feature:
        if segment_direction == BiDirection.UP:
            high, high_source = (
                (left.high, left.high_source_bi_index)
                if left.high >= right.high
                else (right.high, right.high_source_bi_index)
            )
            low, low_source = (
                (left.low, left.low_source_bi_index)
                if left.low >= right.low
                else (right.low, right.low_source_bi_index)
            )
        else:
            high, high_source = (
                (left.high, left.high_source_bi_index)
                if left.high <= right.high
                else (right.high, right.high_source_bi_index)
            )
            low, low_source = (
                (left.low, left.low_source_bi_index)
                if left.low <= right.low
                else (right.low, right.low_source_bi_index)
            )
        return _Feature(
            high=high,
            low=low,
            start_bi_index=left.start_bi_index,
            end_bi_index=right.end_bi_index,
            source_bi_indices=left.source_bi_indices + right.source_bi_indices,
            high_source_bi_index=high_source,
            low_source_bi_index=low_source,
        )

    def _to_schema_features(
        self,
        features: list[_Feature],
        direction: BiDirection,
    ) -> list[FeatureSequenceElement]:
        result: list[FeatureSequenceElement] = []
        for index, item in enumerate(features):
            gap = index > 0 and self._has_gap(features[index - 1], item, direction)
            result.append(
                FeatureSequenceElement(
                    high=item.high,
                    low=item.low,
                    startBiIndex=item.start_bi_index,
                    endBiIndex=item.end_bi_index,
                    sourceBiIndices=list(item.source_bi_indices),
                    highSourceBiIndex=item.high_source_bi_index,
                    lowSourceBiIndex=item.low_source_bi_index,
                    gapFromPrevious=gap,
                )
            )
        return result

    @staticmethod
    def _feature_fractal_indices(
        features: list[_Feature],
        segment_direction: BiDirection,
    ) -> list[int]:
        result: list[int] = []
        for index in range(1, len(features) - 1):
            left = features[index - 1]
            middle = features[index]
            right = features[index + 1]
            if segment_direction == BiDirection.UP:
                if (
                    middle.high > left.high
                    and middle.high > right.high
                    and middle.low > left.low
                    and middle.low > right.low
                ):
                    result.append(index)
            elif (
                middle.low < left.low
                and middle.low < right.low
                and middle.high < left.high
                and middle.high < right.high
            ):
                result.append(index)
        return result

    @staticmethod
    def _has_gap(left: _Feature, right: _Feature, direction: BiDirection) -> bool:
        if direction == BiDirection.UP:
            return right.low > left.high
        return right.high < left.low

    @staticmethod
    def _has_include_relation(left: _Feature, right: _Feature) -> bool:
        return (left.high >= right.high and left.low <= right.low) or (
            left.high <= right.high and left.low >= right.low
        )

    @staticmethod
    def _features_confirmed(bis: list[Bi], features: tuple[_Feature, _Feature, _Feature]) -> bool:
        return all(bis[index].confirmed for feature in features for index in feature.source_bi_indices)

    def _find_initial_start(self, bis: list[Bi], start: int) -> int | None:
        for index in range(start, len(bis) - 2):
            if not self._valid_initial_triplet(bis, index):
                continue
            first, third = bis[index], bis[index + 2]
            advances = (third.end_price > first.end_price if first.direction == BiDirection.UP
                        else third.end_price < first.end_price)
            if advances:
                return index
        return None

    def _valid_initial_triplet(self, bis: list[Bi], start_bi_index: int) -> bool:
        if start_bi_index + 2 >= len(bis):
            return False
        first = bis[start_bi_index]
        third = bis[start_bi_index + 2]
        if first.direction != third.direction:
            return False
        overlap_low, overlap_high = self._triplet_overlap(bis, start_bi_index)
        return overlap_low < overlap_high

    @staticmethod
    def _triplet_overlap(bis: list[Bi], start_bi_index: int) -> tuple[float, float]:
        intervals = [
            (min(item.start_price, item.end_price), max(item.start_price, item.end_price))
            for item in bis[start_bi_index : start_bi_index + 3]
        ]
        return max(item[0] for item in intervals), min(item[1] for item in intervals)

    @staticmethod
    def _opposite(direction: BiDirection) -> BiDirection:
        return BiDirection.DOWN if direction == BiDirection.UP else BiDirection.UP
