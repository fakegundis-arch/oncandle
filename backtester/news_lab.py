"""News lab: event-driven news strategies on M1 bars, built from scratch.

Every Forex Factory medium/high release of USD, EUR, GBP, JPY or CAD becomes an *event* (releases of
one currency in the same minute are merged).  Each event is paired with the markets it moves:

    USD -> all 11 markets (direction map in news_open.USD_BULL_DIRECTION)
    EUR -> EURUSD (+1), GBP -> GBPUSD (+1), JPY -> USDJPY (-1), CAD -> USDCAD (-1)

`score` = sum over the merged releases of (+1 better / -1 worse, per FF's own verdict) x (2 high, 1 medium);
`news_dir` = sign(score) x the market's direction for "currency good".  `a` = the market's mean M1 true range
over the 240 minutes before the release (known before the event), used to size every distance.

Strategy families (all enter at the open of an M1 bar *after* the information is known):
    cont    - wait `w` minutes, follow the spike if it moved >= k x a
    fade    - wait `w` minutes, fade the spike if it moved >= k x a
    news    - wait `w` minutes, trade the FF verdict direction
    retest  - wait `w` minutes, then wait up to 30 min for a 50% retrace of the spike, join the spike direction
A `filt` of "agree" keeps only spikes that went the way the FF verdict says, "disagree" the opposite.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .engine import njit
from .news_open import USD_BULL_DIRECTION

CURRENCY_MARKETS = {"USD": USD_BULL_DIRECTION, "EUR": {"EURUSD": 1}, "GBP": {"GBPUSD": 1},
                    "JPY": {"USDJPY": -1}, "CAD": {"USDCAD": -1}}
TIER1 = ("Non-Farm", "CPI", "Federal Funds Rate", "FOMC Statement", "FOMC Press", "PCE", "Retail Sales",
         "ISM", "GDP", "Unemployment Rate", "Average Hourly", "PPI", "JOLTS", "Main Refinancing", "Official Bank Rate",
         "BOJ Policy Rate", "Overnight Rate", "Claimant", "Employment Change")


def events(cal: pd.DataFrame) -> pd.DataFrame:
    c = cal[cal.currency.isin(list(CURRENCY_MARKETS)) & cal.impact.isin(["high", "medium"])].copy()
    c = c[c.time_label.fillna("").str.contains(r"\d", regex=True)]          # drop All Day / Tentative
    bw = c.better_worse.fillna(0)
    c["s"] = np.where(bw == 1, 1, np.where(bw == 2, -1, 0)) * np.where(c.impact == "high", 2, 1)
    c["hi"] = (c.impact == "high").astype(int)
    c["t1"] = c.name.str.contains("|".join(TIER1), regex=True).astype(int)
    if "z" not in c:
        c["z"] = np.nan
    c["wz"] = c.z.clip(-5, 5) * np.where(c.impact == "high", 2, 1)
    c["wn"] = np.where(c.z.notna(), np.where(c.impact == "high", 2, 1), 0)
    g = c.groupby(["time_utc", "currency"])
    ev = g.agg(score=("s", "sum"), high=("hi", "max"), tier1=("t1", "max"), wz=("wz", "sum"), wn=("wn", "sum"),
               names=("name", lambda x: "; ".join(x))).reset_index()
    ev["z"] = np.where(ev.wn > 0, ev.wz / ev.wn.where(ev.wn > 0, 1), np.nan)
    ev = ev.drop(columns=["wz", "wn"])
    return ev.sort_values("time_utc").reset_index(drop=True)


def pairs(ev: pd.DataFrame, market: str, m1: pd.DataFrame, tr_mean: np.ndarray) -> pd.DataFrame:
    """Events relevant to `market` with the M1 index of the release bar and the pre-release unit."""
    rows = []
    idx = m1.index
    for e in ev.itertuples():
        beta = CURRENCY_MARKETS[e.currency].get(market)
        if beta is None:
            continue
        i = idx.searchsorted(e.time_utc)
        if i < 240 or i + 60 >= len(idx) or idx[i] != e.time_utc:
            continue
        a = tr_mean[i]
        if not np.isfinite(a) or a <= 0:
            continue
        rows.append((e.time_utc, e.currency, market, i, a, int(np.sign(e.score)) * beta, e.score, e.high, e.tier1,
                     e.z * beta, e.names))
    return pd.DataFrame(rows, columns=["time", "currency", "market", "i", "a", "news_dir", "score", "high", "tier1",
                                       "zdir", "names"])


@njit(cache=True)
def signals(o, h, l, c, rel, a, news_dir, family, w, k, filt, wait_max):
    """family 0 cont, 1 fade, 2 news, 3 retest; filt 0 any, 1 agree, 2 disagree.
    Returns entry index (-1 = no trade), direction, spike size (in a units)."""
    n = len(rel)
    ent = np.full(n, -1, np.int64)
    dr = np.zeros(n, np.int64)
    spk = np.zeros(n)
    for q in range(n):
        i = rel[q]
        j = i + w
        if j + 1 >= len(o):
            continue
        mv = c[j - 1] - o[i]
        sm = np.sign(mv)
        spk[q] = abs(mv) / a[q]
        if filt == 1 and (news_dir[q] == 0 or sm != news_dir[q]):
            continue
        if filt == 2 and (news_dir[q] == 0 or sm != -news_dir[q]):
            continue
        if family == 2:
            if news_dir[q] == 0 or spk[q] < k:
                continue
            ent[q] = j
            dr[q] = news_dir[q]
            continue
        if spk[q] < k or sm == 0:
            continue
        if family == 0:
            ent[q] = j
            dr[q] = int(sm)
        elif family == 1:
            ent[q] = j
            dr[q] = -int(sm)
        else:
            lvl = o[i] + 0.5 * mv
            for t in range(j, min(j + wait_max, len(o) - 1)):
                if (sm > 0 and l[t] <= lvl) or (sm < 0 and h[t] >= lvl):
                    ent[q] = t + 1
                    dr[q] = int(sm)
                    break
    return ent, dr, spk


@njit(cache=True)
def simulate(o, h, l, c, ent, dr, sl, rr, trail, be, max_bars, cost):
    """R multiple and exit index per trade.  Long fills at ask (= bid + cost), stops/targets checked on bid
    for longs and ask for shorts; stop first when both are inside one bar.  trail[q] > 0: chandelier stop at
    `trail[q]` price units from the best extreme (no target when rr == 0)."""
    n = len(ent)
    R = np.full(n, np.nan)
    X = np.full(n, -1, np.int64)
    for q in range(n):
        e = ent[q]
        if e < 0:
            continue
        d = dr[q]
        cs = cost[q]
        entry = o[e] + cs if d == 1 else o[e]
        risk = sl[q]
        stop = entry - d * risk
        tgt = entry + d * rr * risk if rr > 0 else 0.0
        best = entry
        moved = False
        last = min(len(o), e + max_bars)
        done = False
        for j in range(e, last):
            bo = o[j] if d == 1 else o[j] + cs
            bh = h[j] if d == 1 else h[j] + cs
            bl = l[j] if d == 1 else l[j] + cs
            if d == 1:
                if bl <= stop:
                    R[q] = (min(bo, stop) - entry) / risk; X[q] = j; done = True; break
                if rr > 0 and bh >= tgt:
                    R[q] = (max(bo, tgt) - entry) / risk; X[q] = j; done = True; break
                best = max(best, bh)
            else:
                if bh >= stop:
                    R[q] = (entry - max(bo, stop)) / risk; X[q] = j; done = True; break
                if rr > 0 and bl <= tgt:
                    R[q] = (entry - min(bo, tgt)) / risk; X[q] = j; done = True; break
                best = min(best, bl)
            if be > 0 and not moved and d * (best - entry) >= be * risk:
                stop = entry + d * 0.1 * risk
                moved = True
            if trail[q] > 0:
                ts = best - d * trail[q]
                if d == 1 and ts > stop:
                    stop = ts
                if d == -1 and ts < stop:
                    stop = ts
        if not done:
            j = last - 1
            px = c[j] if d == 1 else c[j] + cs
            R[q] = d * (px - entry) / risk
            X[q] = j
    return R, X


@dataclass
class Book:
    """Compounding with overlapping trades: each trade risks `risk` x equity at its entry time."""
    risk: float = 0.10

    def run(self, t_in: np.ndarray, t_out: np.ndarray, r: np.ndarray, start=1000.0):
        order = np.argsort(t_in, kind="stable")
        eq = start
        open_ = []                                         # (t_out, stake, r)
        curve = [start]
        for q in order:
            open_.sort()
            while open_ and open_[0][0] <= t_in[q]:
                _, stake, rr = open_.pop(0)
                eq = max(eq + stake * rr, 0.0)
                curve.append(eq)
            open_.append((t_out[q], self.risk * eq, r[q]))
        for _, stake, rr in sorted(open_):
            eq = max(eq + stake * rr, 0.0)
            curve.append(eq)
        cv = np.asarray(curve)
        return eq, (cv / np.maximum.accumulate(cv) - 1).min()


_MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_value(s) -> float:
    if not isinstance(s, str) or not s.strip():
        return np.nan
    s = s.strip().replace(",", "").replace("%", "").replace("|", "")
    mult = _MULT.get(s[-1:].upper(), 1.0)
    if s[-1:].upper() in _MULT:
        s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return np.nan


def surprises(cal: pd.DataFrame, min_hist: int = 4) -> pd.Series:
    """Surprise z per release: (actual - forecast) / std of this indicator's past surprises (only past releases),
    signed so that + = better for the currency (FF's verdict decides the sign convention of each indicator)."""
    c = cal.sort_values("time_utc").copy()
    c["sur"] = c.actual.map(parse_value) - c.forecast.map(parse_value)
    # sign: FF says better (1) / worse (2); use it to learn whether "higher" is good for each indicator
    good_up = {}
    z = np.full(len(c), np.nan)
    hist: dict = {}
    for n, (eid, sur, bw) in enumerate(zip(c.ebase_id, c.sur, c.better_worse)):
        if not np.isfinite(sur):
            continue
        if bw in (1, 2) and sur != 0:
            good_up.setdefault(eid, []).append(np.sign(sur) * (1 if bw == 1 else -1))
        h = hist.get(eid, [])
        sgn = np.sign(np.sum(good_up.get(eid, [0])))
        if len(h) >= min_hist and sgn != 0:
            sd = np.std(h)
            if sd > 0:
                z[n] = sgn * sur / sd
        hist.setdefault(eid, []).append(sur)
    return pd.Series(z, index=c.index).reindex(cal.index)
