from __future__ import annotations

from app.models.schemas import CentralZone, CentralZoneStatus, Segment


class CentralZoneAnalyzer:
    def build_central_zones(self, segments: list[Segment]) -> list[CentralZone]:
        zones: list[CentralZone] = []
        start_index = 0

        while start_index + 2 < len(segments):
            initial = segments[start_index : start_index + 3]
            if not all(item.confirmed for item in initial):
                break

            zd, zg = self._overlap(initial)
            if zd >= zg:
                start_index += 1
                continue

            end_index = start_index + 2
            while end_index + 1 < len(segments):
                next_segment = segments[end_index + 1]
                if not next_segment.confirmed or not self._overlaps_zone(next_segment, zd, zg):
                    break
                end_index += 1

            members = segments[start_index : end_index + 1]
            status = self._status_after_zone(segments, end_index, zd, zg)
            zones.append(
                CentralZone(
                    startTime=members[0].start_time,
                    endTime=members[-1].end_time,
                    zd=zd,
                    zg=zg,
                    dd=min(self._low(item) for item in members),
                    gg=max(self._high(item) for item in members),
                    startSegmentIndex=start_index,
                    endSegmentIndex=end_index,
                    segmentCount=len(members),
                    status=status,
                    sourceSegmentIndices=list(range(start_index, end_index + 1)),
                    reasons=self._build_reasons(start_index, end_index, zd, zg, status),
                )
            )

            start_index = end_index + 1

        return zones

    @staticmethod
    def _overlap(segments: list[Segment]) -> tuple[float, float]:
        zd = max(CentralZoneAnalyzer._low(item) for item in segments)
        zg = min(CentralZoneAnalyzer._high(item) for item in segments)
        return zd, zg

    @staticmethod
    def _overlaps_zone(segment: Segment, zd: float, zg: float) -> bool:
        return CentralZoneAnalyzer._low(segment) < zg and CentralZoneAnalyzer._high(segment) > zd

    @staticmethod
    def _status_after_zone(
        segments: list[Segment],
        end_index: int,
        zd: float,
        zg: float,
    ) -> CentralZoneStatus:
        if end_index + 1 >= len(segments):
            return CentralZoneStatus.EXTENDING

        next_segment = segments[end_index + 1]
        if not next_segment.confirmed:
            return CentralZoneStatus.EXTENDING
        if CentralZoneAnalyzer._low(next_segment) >= zg:
            return CentralZoneStatus.LEFT_UP
        if CentralZoneAnalyzer._high(next_segment) <= zd:
            return CentralZoneStatus.LEFT_DOWN
        return CentralZoneStatus.EXTENDING

    @staticmethod
    def _build_reasons(
        start_index: int,
        end_index: int,
        zd: float,
        zg: float,
        status: CentralZoneStatus,
    ) -> list[str]:
        reasons = [
            f"第 {start_index + 1} 至第 {start_index + 3} 条已确认线段存在严格价格重叠",
            f"中枢区间：ZD {zd:.2f} < ZG {zg:.2f}",
        ]
        if end_index > start_index + 2:
            reasons.append(f"后续 {end_index - start_index - 2} 条已确认线段继续与中枢区间重叠，中枢发生延伸")
        if status == CentralZoneStatus.LEFT_UP:
            reasons.append("后一条已确认线段的最低点不低于 ZG，中枢向上离开")
        elif status == CentralZoneStatus.LEFT_DOWN:
            reasons.append("后一条已确认线段的最高点不高于 ZD，中枢向下离开")
        else:
            reasons.append("尚无已确认线段完全离开中枢区间，中枢仍在延伸或等待确认")
        return reasons

    @staticmethod
    def _high(segment: Segment) -> float:
        return max(segment.start_price, segment.end_price)

    @staticmethod
    def _low(segment: Segment) -> float:
        return min(segment.start_price, segment.end_price)

