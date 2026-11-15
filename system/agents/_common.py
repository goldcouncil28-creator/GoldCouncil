"""دوال مؤشرات مشتركة للوكلاء — كود خالص، بلا LLM."""
import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["high"], df["low"], df["close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    g = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    rs = g / loss.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9):
    m = ema(close, fast) - ema(close, slow)
    s = ema(m, sig)
    return m, s, m - s


def stochastic(df: pd.DataFrame, k: int = 14, d: int = 3):
    hh = df["high"].rolling(k).max()
    ll = df["low"].rolling(k).min()
    kk = 100 * (df["close"] - ll) / (hh - ll).replace(0, np.nan)
    return kk, kk.rolling(d).mean()


def bollinger(close: pd.Series, n: int = 20, mult: float = 2.0):
    mid = sma(close, n)
    sd = close.rolling(n).std()
    return mid, mid + mult * sd, mid - mult * sd


def hurst_exponent(series: pd.Series, max_lag: int = 20) -> float:
    """Hurst عبر Rescaled Range على اللوغاريتم العوائد."""
    x = np.log(series / series.shift(1)).dropna().values
    if len(x) < max_lag * 2:
        return 0.5
    lags = range(2, max_lag + 1)
    tau = []
    for lag in lags:
        chunks = len(x) // lag
        rs = []
        for i in range(chunks):
            seg = x[i * lag:(i + 1) * lag]
            m = seg.mean()
            dev = np.cumsum(seg - m)
            r = dev.max() - dev.min()
            s = seg.std()
            if s > 0:
                rs.append(r / s)
        if rs:
            tau.append(np.mean(rs))
    if len(tau) < 3:
        return 0.5
    poly = np.polyfit(np.log(list(lags)[:len(tau)]), np.log(tau), 1)
    return float(np.clip(poly[0], 0.05, 0.95))
