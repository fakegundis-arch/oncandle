"""Supply and demand zones, M1-exact.

Zone (on a chosen bar size): a BASE of 1+ consecutive small candles (range <= `base_atr` x ATR) followed by one LEG-OUT
candle (range >= `leg_min` x ATR, body >= half its range) that closes beyond the base. ATR is ATR(14) of the bar before
the leg-out, so the leg-out's own size does not inflate it.
  demand (leg-out up)  : proximal = highest base body (max of open/close), distal = lowest low of base + leg-out
  supply (leg-out down): proximal = lowest base body, distal = highest high of base + leg-out
The zone is known at the leg-out candle's close and is traded once: a limit order at the proximal line (or the zone's
middle) waits for the FIRST touch, at most `age` bars. Longs buy at the ask (bid + cost), shorts sell at the bid; the
stop sits `buf` x ATR beyond the distal line (at least `min_stop` away), the target `rr` x the risk. Stops are checked
before targets in a minute, and the fill minute itself can only stop out.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .engine import njit
from . import indicators as ind

COLS = ("t_make", "dir", "prox", "dist", "atr", "n_base", "leg", "height", "pattern", "tr_tf", "tr_d1")


@njit(cache=True)
def _find(o, h, l, c, atr, base_atr, leg_min, n_cap):
    """Indices and levels of every zone. Returns arrays: leg bar index, dir, proximal, distal, atr, base count, leg
    strength (range / ATR), pattern (1 = reversal: leg-in candle against the leg-out; 2 = continuation; 0 = flat)."""
    n = len(o)
    out_i = np.empty(n, np.int64); out_d = np.empty(n, np.int64); out_p = np.empty(n); out_s = np.empty(n)
    out_a = np.empty(n); out_n = np.empty(n, np.int64); out_g = np.empty(n); out_k = np.empty(n, np.int64)
    m = 0
    for i in range(n_cap + 2, n):
        a = atr[i - 1]
        if not (a > 0):
            continue
        rng = h[i] - l[i]
        if rng < leg_min * a or abs(c[i] - o[i]) < 0.5 * rng:
            continue
        d = 1 if c[i] > o[i] else -1
        cnt = 0
        j = i - 1
        while j >= 0 and cnt <= n_cap and h[j] - l[j] <= base_atr * a:
            cnt += 1
            j -= 1
        if cnt == 0 or cnt > n_cap:
            continue
        hi = -1e18; lo = 1e18; btop = -1e18; bbot = 1e18
        for q in range(i - cnt, i):
            hi = max(hi, h[q]); lo = min(lo, l[q])
            btop = max(btop, max(o[q], c[q])); bbot = min(bbot, min(o[q], c[q]))
        if d == 1:
            if c[i] <= hi:
                continue
            prox = btop; dist = min(lo, l[i])
        else:
            if c[i] >= lo:
                continue
            prox = bbot; dist = max(hi, h[i])
        if d * (prox - dist) <= 0:
            continue
        k = i - cnt - 1
        din = 0 if c[k] == o[k] else (1 if c[k] > o[k] else -1)
        out_i[m] = i; out_d[m] = d; out_p[m] = prox; out_s[m] = dist; out_a[m] = a; out_n[m] = cnt
        out_g[m] = rng / a; out_k[m] = 0 if din == 0 else (2 if din == d else 1)
        m += 1
    return out_i[:m], out_d[:m], out_p[:m], out_s[:m], out_a[:m], out_n[:m], out_g[:m], out_k[:m]


def zones(bars: pd.DataFrame, minutes: int, base_atr: float, leg_min: float, n_cap: int = 6) -> pd.DataFrame:
    """All zones of `bars` (bar size `minutes`), with the trend states known at the leg-out close:
    tr_tf = side of the close vs EMA(200) of these bars; tr_d1 = yesterday's daily close vs its EMA(20)."""
    o, h, l, c = (bars[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    atr = ind.atr(bars, 14).to_numpy(np.float64)
    i, d, p, s, a, nb, g, k = _find(o, h, l, c, atr, base_atr, leg_min, n_cap)
    ema = bars.close.ewm(span=200, adjust=False).mean().to_numpy()
    t_make = bars.index[i] + pd.Timedelta(minutes=minutes)
    d1 = bars.close.resample("1D").last().dropna()
    d1e = d1.ewm(span=20, adjust=False).mean()
    prev = (np.sign(d1 - d1e)).shift().reindex(pd.DatetimeIndex(bars.index[i].normalize())).to_numpy()
    return pd.DataFrame({"t_make": t_make, "dir": d, "prox": p, "dist": s, "atr": a, "n_base": nb, "leg": g,
                         "height": np.abs(p - s) / a, "pattern": k,
                         "tr_tf": np.sign(c[i] - ema[i]).astype(np.int64), "tr_d1": np.nan_to_num(prev).astype(np.int64)})


@njit(cache=True)
def fills(o, h, l, start, stop_k, d, lvl, cost):
    """First touch of each zone's limit level inside [start, stop_k): (minute index or -1, fill price)."""
    nz = len(start)
    fi = np.full(nz, -1, np.int64); fp = np.full(nz, np.nan)
    for z in range(nz):
        for k in range(start[z], min(stop_k[z], len(o))):
            if d[z] == 1:
                if o[k] + cost <= lvl[z]:
                    fi[z] = k; fp[z] = o[k] + cost; break
                if l[k] + cost <= lvl[z]:
                    fi[z] = k; fp[z] = lvl[z]; break
            else:
                if o[k] >= lvl[z]:
                    fi[z] = k; fp[z] = o[k]; break
                if h[k] >= lvl[z]:
                    fi[z] = k; fp[z] = lvl[z]; break
    return fi, fp


@njit(cache=True)
def outcomes(o, h, l, c, fi, fp, d, stop_lvl, rr, be, be_buf, cost, min_stop):
    """Exit minute and R of each filled zone (fi >= 0). The fill minute can only stop out (its high / low may come
    before the fill); from the next minute on, stop first, then target; break-even after `be` R (0 = off)."""
    nz = len(fi)
    xi = np.full(nz, -1, np.int64); rr_out = np.zeros(nz)
    n = len(o)
    for z in range(nz):
        j = fi[z]
        if j < 0:
            continue
        dz = d[z]; entry = fp[z]
        R = max(dz * (entry - stop_lvl[z]), min_stop)
        stop = entry - dz * R; tgt = entry + dz * rr * R
        best = entry; moved = False; px = np.nan; k = j
        while k < n:
            bo = o[k] if dz == 1 else o[k] + cost
            bh = h[k] if dz == 1 else h[k] + cost
            bl = l[k] if dz == 1 else l[k] + cost
            if dz == 1:
                if bl <= stop:
                    px = min(bo, stop) if k > j else stop
                    break
                if k > j and bh >= tgt:
                    px = max(bo, tgt)
                    break
                if k > j:
                    best = max(best, bh)
            else:
                if bh >= stop:
                    px = max(bo, stop) if k > j else stop
                    break
                if k > j and bl <= tgt:
                    px = min(bo, tgt)
                    break
                if k > j:
                    best = min(best, bl)
            if be > 0 and not moved and dz * (best - entry) >= be * R:
                stop = entry + dz * be_buf * R
                moved = True
            k += 1
        if k >= n:
            k = n - 1
            px = c[k] if dz == 1 else c[k] + cost
        xi[z] = k
        rr_out[z] = dz * (px - entry) / R
    return xi, rr_out


def resample(m1: pd.DataFrame, minutes: int) -> pd.DataFrame:
    return m1.resample(f"{minutes}min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
