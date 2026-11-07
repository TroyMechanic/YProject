"""Versioned project conventions, not a claim of a unique Chan interpretation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.models.schemas import Kline, RuleProfile, RuleSettings

RULE_VERSION = "4.3.1"
PRINCIPLES = {
    "K01": "包含按方向合并；不足两根默认向上；时间归右，高低点来源分别保留",
    "F01": "标准K线三元素高低点双严格不等式识别顶底分型",
    "F02": "同类只接受更极端端点；等价保留先出现者",
    "B01": "顶底交替；间隔为中心 mergedIndex 差，不是中间根数",
    "B02": "顶价严格高于底三元素最高，底价严格低于顶三元素最低",
    "B03": "候选端点延伸同步更新前笔；末笔未确认，不把候选当完成结构",
    "S01": "初始化三笔严格重叠且第三笔同向突破第一笔终点；反向笔特征序列包含及分型",
    "S02": "无缺口直接确认；有缺口二次确认；转折边界不跨段包含，首笔破坏及反向第三笔或后续先破终点确认，段端点为方向极值",
    "Z01": "线段重叠中枢：连续三条已确认线段严格重叠，非递归走势中枢",
    "Z02": "核心ZD/ZG固定；DD/GG取全部成员；确认段离开；成员不复用",
    "D01": "全量本地历史分析，日期仅裁剪显示；日内保留完整时间",
    "F04": "成笔消费右支撑已冻结的原始分型；不预先删掉同类历史确认依据",
    "F03": "分型强弱按右收盘/元素极值突破左元素区间分级，不是获利概率",
    "M01": "MACD收盘价EMA；同方向柱面积；预热3倍慢线周期；强弱与前同向单元比较",
    "T01": "笔/线段同层中枢；确认离开回试剔除连接段；包络分离判趋势，核心重叠判扩展、包络接触判扩张",
    "V01": "价格新极值、同向面积衰减、零轴回拉；区分趋势背驰、盘整背驰和局部动能衰减",
    "P01": "一类点要求两同向分离中枢的趋势背驰；二类点取其首次反弹/回落后的不破极值回试",
    "P02": "三类点要求中枢形成后离开及首次有效回试；严格不回核心，不能只标突破",
    "R01": "L0特征序列线段种子；父走势必须有子级中枢，反向离开及首次外侧回试确认完成",
    "R02": "展示周期、基础周期、结构递归层分离；父子及确认依赖ID可追溯，不足层不补造",
    "R03": "递归点保留原端点和观察时间；分钟展示仅映射至覆盖该时刻的周期结束K线，不跨缺失区间，不升级信号级别",
    "P04": "基础笔级观察点与L0/L1独立计算及标注；同一复合快照保存证据，不升级递归确认",
    "P03": "笔/线段级研究点明确层级；确认依赖完成单元，前缀回放首次确认时间与段证据，防止后续延伸改写观察依据",
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
        "signalLevels": [{"id": "bi", "label": "笔级"}, {"id": "segment", "label": "线段级"}],
        "defaults": RuleSettings().model_dump(mode="json", by_alias=True),
    }


def rule_hash(settings: RuleSettings) -> str:
    return digest({"catalog": rule_catalog(), "settings": settings.model_dump(mode="json"), "gap": effective_gap(settings)})


def engine_hash() -> str:
    # Content, not git HEAD: uncommitted algorithm changes must invalidate old results too.
    root = Path(__file__).resolve().parents[1]
    names = ("models/schemas.py", "services/chan_analyzer.py", "services/segment_analyzer.py",
             "services/central_zone_analyzer.py", "services/rule_policy.py",
             "services/chart_service.py", "services/csv_store.py", "services/research_analyzer.py",
             "services/recursive_analyzer.py", "services/hierarchy_service.py", "services/market_data_service.py")
    return digest({name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names})
