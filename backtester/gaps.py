"""Strategies for the remaining gaps: range-pair mean reversion with a news filter, session-TWAP reversion,
and pairs trading gated by a rolling cointegration (ADF) test.  Mean-reversion setups run on hwr.run.

FX has no real volume, so "VWAP" here is the session time-weighted average price (TWAP) from 22:00 UTC.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import hwr, indicators as ind
from .engine import njit

SESSIONS = {"asian": (22, 6), "london": (7, 16), "newyork": (12, 21), "all": (0, 24)}
CCY = {"EURCHF": ("EUR", "CHF"), "AUDNZD": ("AUD", "NZD"), "EURGBP": ("EUR", "GBP"), "AUDUSD": ("AUD", "USD"),
       "NZDUSD": ("NZD", "USD"), "GBPJPY": ("GBP", "JPY"), "EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"),
       "USDJPY": ("USD", "JPY"), "USDCAD": ("USD", "CAD")}


def session_mask(idx: pd.DatetimeIndex, ses: str) -> np.ndarray:
    a, b = SESSIONS[ses]
    h = idx.hour
    return np.asarray((h >= a) | (h < b)) if a > b else np.asarray((h >= a) & (h < b))


def news_mask(idx: pd.DatetimeIndex, cal: pd.DataFrame, ccys, before=30, after=90) -> np.ndarray:
    """True on bars within [-before, +after] minutes of a high-impact release of any of `ccys`."""
    t = np.sort(cal[cal.currency.isin(ccys) & (cal.impact == "high")].time_utc.to_numpy().astype("datetime64[ns]"))
    x = idx.to_numpy().astype("datetime64[ns]")
    j = np.searchsorted(t, x)
    nxt = np.where(j < len(t), t[np.minimum(j, len(t) - 1)], np.datetime64("NaT"))
    prv = np.where(j > 0, t[np.maximum(j - 1, 0)], np.datetime64("NaT"))
    near_next = (nxt - x) <= np.timedelta64(before, "m")
    near_prev = (x - prv) <= np.timedelta64(after, "m")
    return np.nan_to_num(near_next, nan=False).astype(bool) | np.nan_to_num(near_prev, nan=False).astype(bool)


def _flags(idx, ses, flatten):
    inside = session_mask(idx, ses)
    return (~inside) if (flatten and ses != "all") else np.zeros(len(idx), bool)


def _setup(sig, sl, tp, out, max_bars):
    sig = sig.astype(np.int64)
    sl = np.nan_to_num(np.asarray(sl, np.float64))
    tp = np.nan_to_num(np.asarray(tp, np.float64))
    sig[(sl <= 0) | (tp <= 0)] = 0
    return hwr.Setup(sig, sl, tp, out, out, max_bars, 0.0, 0.0)


def bb_fade(df, n=20, k=2.0, sl_atr=2.0, ses="asian", news=None, target="mid", max_bars=24, flatten=True):
    """Close outside the k-sigma Bollinger band -> fade it; target the middle band (or 1x the band distance)."""
    c = df.close
    mid, sd = c.rolling(n).mean(), c.rolling(n).std()
    atr = ind.atr(df, 14)
    ok = session_mask(df.index, ses) & (np.ones(len(df), bool) if news is None else ~news)
    long_ = (c < mid - k * sd).to_numpy() & ok
    short_ = (c > mid + k * sd).to_numpy() & ok
    sig = np.where(long_, 1, np.where(short_, -1, 0))
    dist = (mid - c).abs().to_numpy() if target == "mid" else (k * sd).to_numpy()
    return _setup(sig, sl_atr * atr.to_numpy(), dist, _flags(df.index, ses, flatten), max_bars)


def rsi_fade(df, n=2, lo=10.0, sl_atr=2.0, ses="asian", news=None, tp_atr=1.0, max_bars=24, flatten=True):
    r = hwr.rsi(df.close, n).to_numpy()
    atr = ind.atr(df, 14).to_numpy()
    ok = session_mask(df.index, ses) & (np.ones(len(df), bool) if news is None else ~news)
    sig = np.where((r < lo) & ok, 1, np.where((r > 100 - lo) & ok, -1, 0))
    return _setup(sig, sl_atr * atr, tp_atr * atr, _flags(df.index, ses, flatten), max_bars)


def twap_fade(df, z=2.0, win=96, sl_atr=2.0, ses="asian", news=None, max_bars=24, flatten=True):
    """Deviation from the running session TWAP (reset 22:00 UTC) beyond z x its rolling std -> fade back to TWAP."""
    key = (df.index - pd.Timedelta("22h")).normalize()
    tp_ = (df.high + df.low + df.close) / 3
    twap = tp_.groupby(key).cumsum() / tp_.groupby(key).cumcount().add(1)
    dev = df.close - twap
    sd = dev.rolling(win).std().shift()
    atr = ind.atr(df, 14).to_numpy()
    ok = session_mask(df.index, ses) & (np.ones(len(df), bool) if news is None else ~news)
    zz = (dev / sd).to_numpy()
    sig = np.where((zz < -z) & ok, 1, np.where((zz > z) & ok, -1, 0))
    return _setup(sig, sl_atr * atr, np.abs(dev.to_numpy()), _flags(df.index, ses, flatten), max_bars)


# ---------------------------------------------------------------- cointegration-gated pairs
def adf_t(e: np.ndarray) -> float:
    """Engle-Granger style ADF t-stat (no lags) of residual series e: regress de_t on e_{t-1}."""
    y, x = np.diff(e), e[:-1] - e[:-1].mean()
    if len(x) < 20 or not np.isfinite(x).all():
        return np.nan
    b = (x @ y) / (x @ x)
    res = y - b * x
    se = np.sqrt((res @ res) / (len(x) - 1) / (x @ x))
    return b / se


def coint_gate(la: pd.Series, lb: pd.Series, L: int, every: int, crit: float) -> np.ndarray:
    """True where the last L bars (re-estimated every `every` bars, past data only) look cointegrated."""
    a, b = la.to_numpy(), lb.to_numpy()
    gate = np.zeros(len(a), bool)
    state = False
    for i in range(L, len(a)):
        if (i - L) % every == 0:
            ya, yb = a[i - L:i], b[i - L:i]
            vb = yb.var()
            if vb > 0:
                beta = np.cov(ya, yb, bias=True)[0, 1] / vb
                t = adf_t(ya - beta * yb)
                state = bool(np.isfinite(t) and t < crit)
        gate[i] = state
    return gate


@njit(cache=True)
def gated_pairs(la, lb, beta, s, mu, sd, gate, zin, zstop, max_bars, cost):
    n = len(s)
    ent = np.full(n, -1, np.int64)
    ex = np.full(n, -1, np.int64)
    R = np.full(n, np.nan)
    i = 0
    while i < n - 2:
        if not gate[i] or not (sd[i] > 0) or not np.isfinite(beta[i]):
            i += 1
            continue
        z = (s[i] - mu[i]) / sd[i]
        if abs(z) < zin or abs(z) >= zstop:
            i += 1
            continue
        d = -1.0 if z > 0 else 1.0
        b0, s0 = beta[i], sd[i]
        m0 = (la[i] - b0 * lb[i]) - z * s0
        e = i + 1
        se = la[e] - b0 * lb[e]
        risk = (zstop - zin) * s0
        stop = se - d * risk
        j = e + 1
        out = -1
        while j < n and j - e <= max_bars:
            sj = la[j] - b0 * lb[j]
            if (d > 0 and sj <= stop) or (d < 0 and sj >= stop) or d * (sj - m0) >= 0 or not gate[j]:
                out = j
                break
            j += 1
        if out < 0:
            out = min(j, n - 1)
        ent[i] = e
        ex[i] = out
        R[i] = (d * ((la[out] - b0 * lb[out]) - se) - cost) / risk
        i = out + 1
    return ent, ex, R
