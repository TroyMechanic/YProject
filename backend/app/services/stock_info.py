from __future__ import annotations

import re


A_SHARE_NAME_MAP = {
    "002475.SZ": "立讯精密",
    "002156.SZ": "通富微电",
}


def normalize_stock_symbol(symbol: str) -> str:
    value = symbol.strip().upper()
    if value == "DEMO":
        return value
    if "." in value:
        return value
    if re.fullmatch(r"\d{6}", value):
        if value.startswith(("0", "2", "3")):
            return f"{value}.SZ"
        if value.startswith("6"):
            return f"{value}.SH"
        if value.startswith(("4", "8", "9")):
            return f"{value}.BJ"
    return value


def resolve_stock_name(symbol: str) -> str:
    normalized = normalize_stock_symbol(symbol)
    if normalized == "DEMO":
        return "演示数据"
    return A_SHARE_NAME_MAP.get(normalized, "")
