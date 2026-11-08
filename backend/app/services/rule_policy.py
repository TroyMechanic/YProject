"""Versioned project conventions, not a claim of a unique Chan interpretation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.models.schemas import Kline, RuleProfile, RuleSettings

RULE_VERSION = "5.1.0"
PRINCIPLES = {
    "K01": "包含按方向合并；不足两根默认向上；时间归右，高低点来源分别保留",
    "F01": "标准K线三元素高低点双严格不等式识别顶底分型",
    "F02": "同类只接受更极端端点；等价保留先出现者",
    "B01": "顶底交替；间隔为中心 mergedIndex 差，不是中间根数",
    "B02": "顶价严格高于底三元素最高，底价严格低于顶三元素最低",
    "B03": "候选端点延伸同步更新前笔；末笔未确认，不把候选当完成结构",
    "S01": "同级笔高低点同步抬高或降低形成方向",
    "S02": "特征序列分型及缺口确认，跨边界包含待严格突破",
    "D01": "全量本地历史分析，日期仅裁剪显示；日内保留完整时间",
    "F04": "成笔消费右支撑已冻结的原始分型；不预先删掉同类历史确认依据",
}
PROFILES = {
    RuleProfile.LEGACY: {
        "label": "兼容方案",
        "minimumCenterGap": 1,
        "description": "保留原间隔口径，允许分型元素共用；不是老笔/新笔的完整定义。",
    },
    RuleProfile.SEPARATED: {
        "label": "独立分型方案",
        "minimumCenterGap": 4,
        "description": "两个三元素分型不共用标准K线，之间至少留一根；中心差至少4。",
    },
}


def effective_gap(settings: RuleSettings) -> int:
    return max(settings.min_kline_gap, PROFILES[settings.rule_profile]["minimumCenterGap"])


def digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def input_hash(klines: list[Kline]) -> str:
    return digest([item.model_dump(mode="json", by_alias=True) for item in klines])


def rule_catalog() -> dict:
    return {
        "version": RULE_VERSION,
        "defaultProfile": RuleProfile.LEGACY.value,
        "recommendedProfile": RuleProfile.SEPARATED.value,
        "profiles": [{"id": key.value, **value} for key, value in PROFILES.items()],
        "principles": [{"id": key, "text": value} for key, value in PRINCIPLES.items()],
        "defaults": RuleSettings().model_dump(mode="json", by_alias=True),
    }


def rule_hash(settings: RuleSettings) -> str:
    return digest({"catalog": rule_catalog(), "settings": settings.model_dump(mode="json"), "gap": effective_gap(settings)})


def engine_hash() -> str:
    # Content, not git HEAD: uncommitted algorithm changes must invalidate old results too.
    root = Path(__file__).resolve().parents[1]
    names = ("models/schemas.py", "services/chan_analyzer.py", "services/segment_analyzer.py",
             "services/rule_policy.py", "services/chart_service.py", "services/csv_store.py",
             "services/market_data_service.py")
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names})
