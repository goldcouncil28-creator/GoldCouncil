"""R1 — راوتر الأزواج: يحدد أي رمز يعمل عليه خط الوكلاء.

الآن: XAUUSD فقط (قرار مُثبت). البنية جاهزة لـ EURUSD/GBPUSD عبر config
دون تغيير أي وكيل — كل وكيل يعمل على df الرمز الموجَّه.
"""


def route(config: dict | None = None) -> dict:
    cfg = config or {}
    universe = cfg.get("universe", ["XAUUSD"])
    symbol = cfg.get("symbol", universe[0] if universe else "XAUUSD")
    if symbol not in universe:
        universe = [symbol] + universe
    return {"agent": "R1", "symbol": symbol, "universe": list(universe)}
