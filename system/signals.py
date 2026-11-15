"""Precompute-once: إشارات الوكلاء تُحسب مرة واحدة لكل شمعة، ثم كل
التحليلات (E2 vectorized + الباكتست lookup) فوقها — بلا إعادة حساب.

المعمارية: compute (مرة واحدة، multiprocessing) → analyze (فوري).
"""
import hashlib
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

DATA = Path(__file__).parent / "data"
_G = {}


def _init(df, dxy, oil, h4, roster):
    _G.update(df=df, dxy=dxy, oil=oil, h4=h4, roster=roster)


def _bar(i):
    df, dxy, oil, h4, roster = (_G["df"], _G["dxy"], _G["oil"], _G["h4"], _G["roster"])
    d = df.iloc[:i]
    ctx = {"dxy": dxy.iloc[:i] if dxy is not None else None,
           "oil": oil.iloc[:i] if oil is not None else None,
           "gold": d["close"],
           "h4": h4.iloc[:i // 4] if (h4 is not None and len(h4)) else h4,
           "now": None, "llm": None}
    row = {}
    for name, fn in roster.items():
        try:
            r = fn(d, ctx)
            row[name] = int(r.get("signal", 0)) if isinstance(r, dict) else 0
            row[name + "_c"] = int(r.get("confidence", 0)) if isinstance(r, dict) else 0
        except Exception:
            row[name] = 0
            row[name + "_c"] = 0
    return i, row


def _key(df) -> str:
    h = hashlib.md5(f"{len(df)}_{df.index[-1]}".encode()).hexdigest()[:10]
    return DATA / f"agent_signals_{h}.parquet"


def compute_agent_signals(df, dxy=None, oil=None, h4=None,
                          start_bar: int = 260, workers: int = 1) -> pd.DataFrame:
    """يرجع DataFrame: لكل شمعة إشارة وثقة كل وكيل (25×2 عمود).

    workers=1 افتراضيًا: الصندوق شحيح الذاكرة (fork يضاعف الضغط).
    """
    from pipeline import build_roster
    key = _key(df)
    if key.exists():
        return pd.read_parquet(key)

    roster = build_roster()
    idxs = list(range(start_bar, len(df)))
    rows = {}
    if workers <= 1:
        from pipeline import build_ctx as _bc  # noqa
        _init(df, dxy, oil, h4, roster)
        for j, i in enumerate(idxs):
            _, row = _bar(i)
            rows[i] = row
            if j % 500 == 0:
                print(f"signals: {j}/{len(idxs)}", flush=True)
    else:
        with ProcessPoolExecutor(max_workers=workers,
                                 initializer=_init,
                                 initargs=(df, dxy, oil, h4, roster)) as ex:
            for i, row in ex.map(_bar, idxs, chunksize=64):
                rows[i] = row
    sig = pd.DataFrame.from_dict(rows, orient="index").sort_index()
    # الإشارة محسوبة على df.iloc[:i] أي حتى إغلاق الشمعة i-1 → تُوسم بتاريخها
    sig.index = df.index[sig.index - 1]
    DATA.mkdir(parents=True, exist_ok=True)
    sig.to_parquet(key)
    return sig
