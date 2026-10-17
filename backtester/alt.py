"""Non-trend strategy families: pairs mean reversion, time-of-day seasonality, RSI(2) snap-back, gap fade.

Every family returns a trade table (entry_time, exit_time, market, r) with r in R multiples after costs.
Signals use only completed bars; fills are at the next bar's open (pairs: the next bar's close).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import data as D, indicators as ind
from .engine import njit
from .news_lab import simulate

ROOT = Path(__file__).resolve().parents[1]
AGG = {"open": "first", "high": "max", "low": "min", "close": "last"}


def bars(market: str, rule: str) -> pd.DataFrame:
    """M1 -> `rule` bars (cached as parquet under data/bars/)."""
    f = ROOT / "data" / "bars" / f"{market}_{rule}.parquet"
    if f.exists():
        return pd.read_parquet(f)
    m1 = D.load_csv(ROOT / "data" / f"{market}_M1.csv").drop(columns="spread", errors="ignore")
    out = m1.resample(rule).agg(AGG).dropna()
    f.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(f)
    return out


def _trades(df, market, ent, R, X):
    ok = ent >= 0
    return pd.DataFrame({"entry_time": df.index[ent[ok]], "exit_time": df.index[np.clip(X[ok], 0, len(df) - 1)],
                         "market": market, "r": R[ok]})


# ---------------------------------------------------------------- pairs
@njit(cache=True)
def _pairs(la, lb, beta, s, mu, sd, zin, zstop, zexit, max_bars, cost):
    """The hedge ratio is frozen at the signal bar: the position is +1 A / -beta B (in log-return terms), so P&L and
    exits use that fixed-beta spread."""
    n = len(s)
    ent = np.full(n, -1, np.int64)
    ex = np.full(n, -1, np.int64)
    R = np.full(n, np.nan)
    i = 0
    while i < n - 2:
        if not (sd[i] > 0) or not np.isfinite(beta[i]):
            i += 1
            continue
        z = (s[i] - mu[i]) / sd[i]
        if abs(z) < zin or abs(z) >= zstop:
            i += 1
            continue
        d = -1.0 if z > 0 else 1.0
        b0, s0 = beta[i], sd[i]
        m0 = (la[i] - b0 * lb[i]) - z * s0                  # mean level expressed in the frozen-beta spread
        e = i + 1
        se = la[e] - b0 * lb[e]
        risk = (zstop - zin) * s0
        stop = se - d * risk
        j = e + 1
        out = -1
        while j < n and j - e <= max_bars:
            sj = la[j] - b0 * lb[j]
            zz = (sj - m0) / s0
            if (d > 0 and sj <= stop) or (d < 0 and sj >= stop) or abs(zz) <= zexit or d * zz > 0:
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


def pairs_trades(a: str, b: str, rule="15min", L=96 * 5, zin=2.0, zstop=4.0, zexit=0.0, max_bars=96 * 2, slip=1.5):
    A, B = bars(a, rule).close, bars(b, rule).close
    j = pd.concat([A.rename("a"), B.rename("b")], axis=1, join="inner").dropna()
    la, lb = np.log(j.a), np.log(j.b)
    # rolling OLS la = alpha + beta lb over the previous L bars (shifted: no look-ahead)
    ma, mb = la.rolling(L).mean().shift(), lb.rolling(L).mean().shift()
    va, vb = la.rolling(L).var().shift(), lb.rolling(L).var().shift()
    cov = la.rolling(L).cov(lb).shift()
    beta = cov / vb
    s = la - beta * lb
    mu = ma - beta * mb
    sd = np.sqrt((va - beta * cov).clip(lower=0))
    cost = slip * (D.EXNESS_STANDARD_SPREAD[a] / j.a.median() + abs(beta.median()) * D.EXNESS_STANDARD_SPREAD[b] / j.b.median())
    ent, ex, R = _pairs(la.to_numpy(), lb.to_numpy(), beta.to_numpy(), s.to_numpy(), mu.to_numpy(), sd.to_numpy(),
                        zin, zstop, zexit, max_bars, cost)
    ok = ent >= 0
    return pd.DataFrame({"entry_time": j.index[ent[ok]], "exit_time": j.index[ex[ok]], "market": f"{a}/{b}", "r": R[ok]})


# ---------------------------------------------------------------- time-of-day seasonality
def hour_returns(market: str, stop_atr=1.5) -> pd.DataFrame:
    """One row per H1 bar: hour (UTC), weekday, R if bought at the open and closed at the close with a stop of
    stop_atr x ATR(14) (stop checked on the bar's low/high; long and short versions)."""
    h = bars(market, "1h")
    atr = ind.atr(h, 14).shift().to_numpy()
    o, hi, lo, c = (h[x].to_numpy() for x in ("open", "high", "low", "close"))
    cost = 1.5 * D.EXNESS_STANDARD_SPREAD[market]
    risk = stop_atr * atr
    long_r = np.where(lo <= o - risk, -1.0, (c - o) / risk) - cost / risk
    short_r = np.where(hi >= o + risk, -1.0, (o - c) / risk) - cost / risk
    return pd.DataFrame({"hour": h.index.hour, "wd": h.index.weekday, "long": long_r, "short": short_r,
                         "market": market}, index=h.index).dropna()


# ---------------------------------------------------------------- RSI(2) snap-back
def rsi(close: pd.Series, n=2) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / dn.replace(0, np.nan))


@njit(cache=True)
def _rsi_exit(o, h, l, c, sma5, ent, dr, sl, max_bars, cost):
    n = len(ent)
    R = np.full(n, np.nan)
    X = np.full(n, -1, np.int64)
    for q in range(n):
        e = ent[q]
        d = dr[q]
        entry = o[e] + cost if d == 1 else o[e]
        stop = entry - d * sl[q]
        for j in range(e, min(e + max_bars, len(o))):
            bl = l[j] if d == 1 else l[j] + cost
            bh = h[j] if d == 1 else h[j] + cost
            if (d == 1 and bl <= stop) or (d == -1 and bh >= stop):
                px = min(o[j], stop) if d == 1 else max(o[j] + cost, stop)
                R[q] = d * (px - entry) / sl[q]; X[q] = j
                break
            if (d == 1 and c[j] > sma5[j]) or (d == -1 and c[j] < sma5[j]):
                px = c[j] if d == 1 else c[j] + cost
                R[q] = d * (px - entry) / sl[q]; X[q] = j
                break
        if X[q] < 0:
            j = min(e + max_bars, len(o)) - 1
            px = c[j] if d == 1 else c[j] + cost
            R[q] = d * (px - entry) / sl[q]; X[q] = j
    return R, X


def rsi2_trades(market, rule="1h", lo=10.0, stop_atr=3.0, filt=True, max_bars=10, both=True):
    df = bars(market, rule)
    r2 = rsi(df.close).to_numpy()
    sma200 = df.close.rolling(200).mean().to_numpy()
    sma5 = df.close.rolling(5).mean().to_numpy()
    atr = ind.atr(df, 14).to_numpy()
    c = df.close.to_numpy()
    longs = (r2 < lo) & ((c > sma200) if filt else True)
    shorts = (r2 > 100 - lo) & ((c < sma200) if filt else True) & both
    sig = np.where(longs, 1, np.where(shorts, -1, 0))
    sig[:200] = 0
    # one position at a time
    ent, dr = [], []
    i, n = 0, len(c)
    o, h, l = (df[x].to_numpy() for x in ("open", "high", "low"))
    cost = 1.5 * D.EXNESS_STANDARD_SPREAD[market]
    E, Dd, SL = [], [], []
    while i < n - 2:
        if sig[i] != 0 and np.isfinite(atr[i]):
            R, X = _rsi_exit(o, h, l, c, sma5, np.array([i + 1]), np.array([sig[i]]), np.array([stop_atr * atr[i]]),
                             max_bars, cost)
            E.append(i + 1); Dd.append(sig[i]); SL.append((R[0], X[0]))
            i = X[0] + 1
        else:
            i += 1
    if not E:
        return pd.DataFrame(columns=["entry_time", "exit_time", "market", "r"])
    E = np.array(E)
    return pd.DataFrame({"entry_time": df.index[E], "exit_time": df.index[[x for _, x in SL]], "market": market,
                         "r": [r for r, _ in SL]})


# ---------------------------------------------------------------- gap fade
def gap_trades(market, rule="15min", min_gap_min=30, g=1.0, stop_atr=2.0, max_bars=16, delay=0, cost_mult=2.0):
    """After a trading break of >= min_gap_min minutes, fade an opening gap of >= g x ATR back to the prior close."""
    df = bars(market, rule)
    atr = ind.atr(df, 14).shift().to_numpy()
    o, h, l, c = (df[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    t = df.index.asi8
    step = (t[1:] - t[:-1]) / 60e9 if t[0] > 1e17 else (t[1:] - t[:-1]) / 60e6
    brk = np.r_[False, step >= min_gap_min + pd.Timedelta(rule).total_seconds() / 60]
    gap = o - np.r_[np.nan, c[:-1]]
    sel = brk & (np.abs(gap) >= g * atr) & np.isfinite(atr)
    idx = np.flatnonzero(sel)
    if len(idx) == 0:
        return pd.DataFrame(columns=["entry_time", "exit_time", "market", "r"])
    dr = -np.sign(gap[idx]).astype(np.int64)
    prev_c = c[idx - 1]
    sl = stop_atr * atr[idx]
    idx = idx + delay                                       # optional: enter `delay` bars after the open
    keep = idx < len(o) - 1
    idx, dr, sl, prev_c = idx[keep], dr[keep], sl[keep], prev_c[keep]
    tgt_r = (prev_c - o[idx]) * dr / sl                     # target = full gap fill (prior close), in R
    ok = tgt_r > 0.05                                       # gap already filled before the delayed entry: skip
    idx, dr, sl, tgt_r = idx[ok], dr[ok], sl[ok], tgt_r[ok]
    cost = np.full(len(idx), cost_mult * D.EXNESS_STANDARD_SPREAD[market])
    R = np.empty(len(idx)); X = np.empty(len(idx), np.int64)
    for q in range(len(idx)):                                # per-trade target ratio
        rq, xq = simulate(o, h, l, c, idx[q:q + 1], dr[q:q + 1], sl[q:q + 1], float(tgt_r[q]), np.zeros(1), 0.0,
                          max_bars, cost[q:q + 1])
        R[q], X[q] = rq[0], xq[0]
    return _trades(df, market, idx, R, X)


YEARS = {"q4_24": ("2024-10-01", "2025-01-01"), "y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}


def stats(t: pd.DataFrame, risk=0.10) -> dict:
    out = {}
    for k, (a, b) in YEARS.items():
        x = t[(t.entry_time >= a) & (t.entry_time < b)].sort_values("entry_time").r.to_numpy()
        out[f"{k}_n"] = len(x)
        if len(x) == 0:
            continue
        loss = -x[x < 0].sum()
        eq = 1000 * np.cumprod(np.maximum(1 + risk * x, 0))
        out.update({f"{k}_win": (x > 0).mean(), f"{k}_avg": x.mean(), f"{k}_pf": x[x > 0].sum() / loss if loss > 0 else 99,
                    f"{k}_usd": eq[-1], f"{k}_dd": (eq / np.maximum.accumulate(eq) - 1).min()})
    return out
