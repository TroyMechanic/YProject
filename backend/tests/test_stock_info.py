from app.services.stock_info import normalize_stock_symbol, resolve_stock_name


def test_normalizes_bare_a_share_symbol_to_default_market() -> None:
    assert normalize_stock_symbol("002475") == "002475.SZ"
    assert normalize_stock_symbol("600519") == "600519.SH"


def test_resolves_known_a_share_name() -> None:
    assert resolve_stock_name("002475") == "立讯精密"
