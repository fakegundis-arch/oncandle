"""Vectorised indicators.  Definitions follow the MT5 built-ins
(iMA, iATR, iADX/Wilder, iMACD, iBands, iSAR, iIchimoku) so the EAs in
mt5/ reproduce the same signals."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def rma(s: pd.Series, n: int) -> pd.Series:
    """Wilder's smoothing."""
    return s.ewm(alpha=1.0 / n, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    pc = df["close"].shift()
    return pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()],
                     axis=1).max(axis=1)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    # MT5 iATR is a simple moving average of true range.
    return true_range(df).rolling(n).mean()


def donchian(df: pd.DataFrame, n: int):
    """Highest high / lowest low of the previous n bars (excluding current)."""
    return df["high"].rolling(n).max().shift(), df["low"].rolling(n).min().shift()


def adx(df: pd.DataFrame, n: int = 14):
    up = df["high"].diff()
    dn = -df["low"].diff()
    plus_dm = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    tr = rma(true_range(df), n)
    pdi = 100 * rma(pd.Series(plus_dm, df.index), n) / tr
    mdi = 100 * rma(pd.Series(minus_dm, df.index), n) / tr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    return pdi, mdi, rma(dx.fillna(0), n)


def macd(s: pd.Series, fast=12, slow=26, signal=9):
    m = ema(s, fast) - ema(s, slow)
    return m, sma(m, signal)  # MT5 iMACD signal line is an SMA


def bollinger(s: pd.Series, n=20, k=2.0):
    mid = sma(s, n)
    sd = s.rolling(n).std(ddof=0)
    return mid, mid + k * sd, mid - k * sd


def supertrend(df: pd.DataFrame, n=10, mult=3.0) -> pd.Series:
    """Returns +1 / -1 trend direction."""
    a = atr(df, n).to_numpy()
    hl2 = ((df["high"] + df["low"]) / 2).to_numpy()
    c = df["close"].to_numpy()
    ub = hl2 + mult * a
    lb = hl2 - mult * a
    fub, flb = ub.copy(), lb.copy()
    d = np.ones(len(c))
    for i in range(1, len(c)):
        if np.isnan(a[i]):
            continue
        fub[i] = ub[i] if (ub[i] < fub[i - 1] or c[i - 1] > fub[i - 1] or np.isnan(fub[i - 1])) else fub[i - 1]
        flb[i] = lb[i] if (lb[i] > flb[i - 1] or c[i - 1] < flb[i - 1] or np.isnan(flb[i - 1])) else flb[i - 1]
        if d[i - 1] == 1:
            d[i] = -1 if c[i] < flb[i] else 1
        else:
            d[i] = 1 if c[i] > fub[i] else -1
    d[np.isnan(a)] = 0
    return pd.Series(d, df.index)


def psar(df: pd.DataFrame, step=0.02, maxstep=0.2) -> pd.Series:
    """Returns +1 when SAR is below price (uptrend), -1 otherwise."""
    h, l = df["high"].to_numpy(), df["low"].to_numpy()
    n = len(h)
    d = np.zeros(n)
    if n < 3:
        return pd.Series(d, df.index)
    up = True
    sar, ep, af = l[0], h[0], step
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if up:
            sar = min(sar, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar:
                up, sar, ep, af = False, ep, l[i], step
            elif h[i] > ep:
                ep, af = h[i], min(af + step, maxstep)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar:
                up, sar, ep, af = True, ep, h[i], step
            elif l[i] < ep:
                ep, af = l[i], min(af + step, maxstep)
        d[i] = 1 if up else -1
    return pd.Series(d, df.index)


def ichimoku(df: pd.DataFrame, t=9, k=26, s=52):
    hh = lambda n: df["high"].rolling(n).max()
    ll = lambda n: df["low"].rolling(n).min()
    tenkan = (hh(t) + ll(t)) / 2
    kijun = (hh(k) + ll(k)) / 2
    # Cloud value *at the current bar* was computed k bars ago.
    span_a = ((tenkan + kijun) / 2).shift(k)
    span_b = ((hh(s) + ll(s)) / 2).shift(k)
    return tenkan, kijun, span_a, span_b


def kama(s: pd.Series, n=10, fast=2, slow=30) -> pd.Series:
    x = s.to_numpy()
    out = np.full(len(x), np.nan)
    fsc, ssc = 2 / (fast + 1), 2 / (slow + 1)
    if len(x) <= n:
        return pd.Series(out, s.index)
    out[n] = x[n]
    vol = np.abs(np.diff(x, prepend=x[0]))
    for i in range(n + 1, len(x)):
        change = abs(x[i] - x[i - n])
        v = vol[i - n + 1:i + 1].sum()
        er = change / v if v else 0
        sc = (er * (fsc - ssc) + ssc) ** 2
        out[i] = out[i - 1] + sc * (x[i] - out[i - 1])
    return pd.Series(out, s.index)

