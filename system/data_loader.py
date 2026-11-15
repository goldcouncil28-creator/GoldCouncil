"""خط البيانات — XAUUSD H1 من Dukascopy (مجاني) مع تخزين مؤقت.

الواجهة: load_xauusd_h1(start, end, refresh) -> DataFrame بأعمدة
open/high/low/close/volume وفهرس زمني UTC.
+ load_dxy_proxy: مؤشر الدولار محسوبًا من 6 أزواج (بلا مفاتيح).
+ load_oil: خام غرب تكساس (أفضل جهد).
"""
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from dukascopy_python import fetch, INTERVAL_HOUR_1, OFFER_SIDE_BID

DATA = Path(__file__).parent / "data"
CACHE = DATA / "xauusd_h1.parquet"


def fetch_range(start: datetime, end: datetime) -> pd.DataFrame:
    df = fetch("xau/usd", INTERVAL_HOUR_1, OFFER_SIDE_BID, start, end)
    df = df.rename(columns=str.lower)
    df.index = pd.to_datetime(df.index, utc=True)
    return df[["open", "high", "low", "close", "volume"]].sort_index()


def load_xauusd_h1(start: datetime | None = None,
                   end: datetime | None = None,
                   refresh: bool = False) -> pd.DataFrame:
    end = end or datetime.now(timezone.utc)
    start = start or datetime(2026, 4, 12, tzinfo=timezone.utc)

    if CACHE.exists() and not refresh:
        df = pd.read_parquet(CACHE)
        if df.index[-1] >= end - pd.Timedelta(hours=6):
            return df[(df.index >= start) & (df.index <= end)]

    df = fetch_range(start, end)
    DATA.mkdir(parents=True, exist_ok=True)
    df.to_parquet(CACHE)
    return df


def _load_close(instrument: str, cache_name: str,
                start: datetime, end: datetime) -> pd.Series:
    p = DATA / f"{cache_name}.parquet"
    if p.exists():
        s = pd.read_parquet(p).iloc[:, 0]
        s.index = pd.to_datetime(s.index, utc=True)
        if s.index[-1] >= end - pd.Timedelta(hours=6):
            return s.sort_index()
    df = fetch(instrument, INTERVAL_HOUR_1, OFFER_SIDE_BID, start, end)
    s = df["close"]
    s.index = pd.to_datetime(s.index, utc=True)
    s = s.sort_index()
    DATA.mkdir(parents=True, exist_ok=True)
    s.to_frame("close").to_parquet(p)
    return s


# أوزان مؤشر الدولار الرسمية
DXY_W = {"eur/usd": -0.576, "usd/jpy": 0.136, "gbp/usd": -0.119,
         "usd/cad": 0.091, "usd/sek": 0.042, "usd/chf": 0.036}


def load_dxy_proxy(start: datetime | None = None,
                   end: datetime | None = None) -> pd.Series:
    """مؤشر الدولار محسوبًا من الأزواج الستة — بلا أي مفتاح."""
    end = end or datetime.now(timezone.utc)
    start = start or datetime(2026, 4, 12, tzinfo=timezone.utc)
    closes = {k: _load_close(k, "dxy_" + k.replace("/", ""), start, end)
              for k in DXY_W}
    df = pd.DataFrame(closes).dropna()
    dxy = 50.14348112
    for k, w in DXY_W.items():
        dxy = dxy * (df[k] ** w)
    dxy.name = "dxy"
    return dxy


def load_oil(start: datetime | None = None,
             end: datetime | None = None) -> pd.Series | None:
    """خام غرب تكساس — أفضل جهد، None لو غير متاح."""
    end = end or datetime.now(timezone.utc)
    start = start or datetime(2026, 4, 12, tzinfo=timezone.utc)
    for inst in ("wti/usd", "usoil"):
        try:
            return _load_close(inst, "oil", start, end).rename("oil")
        except Exception:
            continue
    return None
