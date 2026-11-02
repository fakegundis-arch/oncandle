"""Agent lab, agent A (built on Jan-Jun 2026, passed its first Jul-Oct check): H1 fair-value-gap (FVG) retest on gold
(XAUUSD, M1 bid bars, server time UTC).

RULES (BEST cfg below)
  * H1 bars on the UTC grid (`off` minutes shift; 0 = bars start on the hour).
  * Bullish FVG at H1 bar i (known at its close): low[i] > high[i-2], and the middle bar i-1 is a displacement candle:
    range >= `disp` x ATR14 (simple mean of true range) of bar i-2, body >= half its range, closing up. Bearish mirror.
  * At bar i's close place a limit order `entry` (25%) of the way into the gap from its proximal edge (low[i] for longs,
    high[i] for shorts), valid `age` H1 bars; only the FIRST touch counts (a touch while already in a position, in the
    first 15 minutes after a market reopen, on a US holiday / early-close trading day, or one that gaps through the
    stop cancels the zone).
  * Stop at the displacement origin: min(low[i-1], low[i-2]) for longs (max of highs for shorts) +/- `buf` x ATR.
    Target `rr` (0.75) x the risk. Stop is checked before target within a minute; the fill minute can only stop out.
  * One position at a time; at most `mld` losing trades per trading day; every position is closed at 20:45 UTC (before
    the 20:59/21:59 UTC daily break, so nothing is held across weekends); no entries in the last 15 minutes before that.
  * Fills: longs buy at the ask (bid + cost) and exit on the bid; shorts sell at the bid and exit at bid + cost.
make_trades(cfg, cost, m1) -> DataFrame(entry_time, exit_time, dir, r). Trades are only generated from 2026-01-01 on
(earlier bars are indicator warm-up).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

try:
    from numba import njit
except ImportError:  # pragma: no cover
    def njit(*a, **k):
        return (lambda f: f) if not (a and callable(a[0])) else a[0]

BEST = dict(tf=60, off=0, disp=2.25, entry=0.25, buf=0.0, rr=0.75, age=40, mld=2, min_stop=1.0, flat_at=22.75)

# US market holidays / early-close days (exchange calendar, known in advance): no trading on these trading days.
HOLIDAYS = ["2025-11-27", "2025-11-28", "2025-12-24", "2025-12-25", "2025-12-26", "2025-12-31", "2026-01-01",
            "2026-01-02", "2026-01-19", "2026-02-16", "2026-04-02", "2026-04-03", "2026-05-25", "2026-06-19",
            "2026-07-03", "2026-09-07", "2026-11-26", "2026-11-27", "2026-12-24", "2026-12-25", "2026-12-31"]
START = "2026-01-01"


def _masks(m1, flat_at):
    """Trading-day clock t2 = UTC + 2h (the 22:00 UTC reopen is 00:00). flat_at 22.75 = 20:45 UTC."""
    idx = m1.index
    t2 = idx + pd.Timedelta(hours=2)
    hr2 = (t2.hour + t2.minute / 60.0).to_numpy()
    tm = idx.to_numpy("datetime64[m]").astype(np.int64)
    first = np.concatenate([[True], np.diff(tm) > 30])
    last_open = np.maximum.accumulate(np.where(first, tm, np.iinfo(np.int64).min))
    reopen = (tm - last_open) < 15
    hol = np.isin(t2.normalize().to_numpy(), pd.to_datetime(HOLIDAYS).to_numpy())
    noentry = reopen | hol | (hr2 >= flat_at - 0.25)
    flat = (hr2 >= flat_at) | hol
    gapnext = np.concatenate([np.diff(tm) > 30, [True]])
    dayid = (t2.year * 10000 + t2.month * 100 + t2.day).to_numpy(np.int64)
    return noentry, flat, gapnext, dayid


@njit(cache=True)
def _fills(o, h, l, start, exp, d, lvl, stop, noentry, cost):
    nz = len(start)
    fi = np.full(nz, -1, np.int64)
    fp = np.full(nz, np.nan)
    n = len(o)
    for z in range(nz):
        for k in range(start[z], min(exp[z], n)):
            px = np.nan
            if d[z] == 1:
                if o[k] + cost <= lvl[z]:
                    px = o[k] + cost
                elif l[k] + cost <= lvl[z]:
                    px = lvl[z]
            else:
                if o[k] >= lvl[z]:
                    px = o[k]
                elif h[k] >= lvl[z]:
                    px = lvl[z]
            if px == px:
                if noentry[k] or d[z] * (px - stop[z]) <= 0:
                    fi[z] = -2
                else:
                    fi[z] = k
                    fp[z] = px
                break
    return fi, fp


@njit(cache=True)
def _sim(o, h, l, c, flat, gapnext, dayid, fi, fp, d, stop0, rr, min_stop, cost, max_loss_day):
    nz = len(fi)
    order = np.argsort(fi, kind="mergesort")
    n = len(o)
    out_in = np.zeros(nz, np.int64); out_ex = np.zeros(nz, np.int64); out_d = np.zeros(nz, np.int64)
    out_r = np.zeros(nz)
    nt = 0; busy = -1; cur_day = -1; nld = 0
    for q in range(nz):
        z = order[q]
        j = fi[z]
        if j < 0 or j <= busy:
            continue
        if dayid[j] != cur_day:
            cur_day = dayid[j]; nld = 0
        if nld >= max_loss_day:
            continue
        dz = d[z]; entry = fp[z]
        R = max(dz * (entry - stop0[z]), min_stop)
        stop = entry - dz * R
        tgt = entry + dz * rr * R
        px = np.nan; k = j
        while k < n:
            bo = o[k] if dz == 1 else o[k] + cost
            bh = h[k] if dz == 1 else h[k] + cost
            bl = l[k] if dz == 1 else l[k] + cost
            bc = c[k] if dz == 1 else c[k] + cost
            if k > j and flat[k]:
                px = bo
                break
            if dz == 1:
                if bl <= stop:
                    px = min(bo, stop) if k > j else stop
                    break
                if k > j and bh >= tgt:
                    px = max(bo, tgt)
                    break
            else:
                if bh >= stop:
                    px = max(bo, stop) if k > j else stop
                    break
                if k > j and bl <= tgt:
                    px = min(bo, tgt)
                    break
            if gapnext[k]:  # safety: never hold across a market break (not reached with flat_at)
                px = bc
                break
            k += 1
        if k >= n:
            k = n - 1
            px = c[k] if dz == 1 else c[k] + cost
        r = dz * (px - entry) / R
        out_in[nt] = j; out_ex[nt] = k; out_d[nt] = dz; out_r[nt] = r
        nt += 1
        busy = k
        if r < 0:
            nld += 1
    return out_in[:nt], out_ex[:nt], out_d[:nt], out_r[:nt]


def fvg_signals(m1, c):
    tf, off = c["tf"], c["off"]
    b = m1.resample(f"{tf}min", offset=f"{off}min").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    o, h, l, cl = (b[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    pc = np.concatenate([[np.nan], cl[:-1]])
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    atr = pd.Series(tr).rolling(14).mean().to_numpy()
    a2 = np.roll(atr, 2)
    rng1 = np.roll(h - l, 1); body1 = np.roll(cl - o, 1)
    bull = (l > np.roll(h, 2)) & (rng1 >= c["disp"] * a2) & (body1 >= 0.5 * rng1)
    bear = (h < np.roll(l, 2)) & (rng1 >= c["disp"] * a2) & (-body1 >= 0.5 * rng1)
    bull[:3] = False; bear[:3] = False
    ib, isb = np.where(bull)[0], np.where(bear)[0]
    bi = np.concatenate([ib, isb])
    d = np.concatenate([np.ones(len(ib), np.int64), -np.ones(len(isb), np.int64)])
    prox = np.concatenate([l[ib], h[isb]])
    dist = np.concatenate([h[ib - 2], l[isb - 2]])
    orig = np.concatenate([np.minimum(l[ib - 1], l[ib - 2]), np.maximum(h[isb - 1], h[isb - 2])])
    a = a2[bi]
    srt = np.argsort(bi, kind="mergesort")
    bi, d, prox, dist, orig, a = bi[srt], d[srt], prox[srt], dist[srt], orig[srt], a[srt]
    ok = np.isfinite(a) & (a > 0)
    bi, d, prox, dist, orig, a = bi[ok], d[ok], prox[ok], dist[ok], orig[ok], a[ok]
    t_close = b.index[bi] + pd.Timedelta(minutes=tf)
    start = m1.index.searchsorted(t_close)
    exp = m1.index.searchsorted(t_close + pd.Timedelta(minutes=c["age"] * tf))
    lvl = prox - c["entry"] * (prox - dist)
    stop = orig - d * c["buf"] * a
    keep = start >= m1.index.searchsorted(pd.Timestamp(START))
    return start[keep], exp[keep], d[keep], lvl[keep], stop[keep]


def make_trades(cfg, cost, m1):
    c = {**BEST, **(cfg or {})}
    start, exp, d, lvl, stop = fvg_signals(m1, c)
    empty = pd.DataFrame({"entry_time": pd.DatetimeIndex([]), "exit_time": pd.DatetimeIndex([]), "dir": [], "r": []})
    if len(start) == 0:
        return empty
    noentry, flat, gapnext, dayid = _masks(m1, c["flat_at"])
    o, h, l, cl = (m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    fi, fp = _fills(o, h, l, start.astype(np.int64), exp.astype(np.int64), d, lvl, stop, noentry, float(cost))
    ti, tx, td, tr = _sim(o, h, l, cl, flat, gapnext, dayid, fi, fp, d, stop, float(c["rr"]), float(c["min_stop"]),
                          float(cost), int(c["mld"]))
    return pd.DataFrame({"entry_time": m1.index[ti], "exit_time": m1.index[tx], "dir": td, "r": tr})


if __name__ == "__main__":
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import agent_lab as AL
    m1 = AL.train_data()
    t25, t40 = make_trades(BEST, 0.25, m1), make_trades(BEST, 0.40, m1)
    m25, m40 = AL.evaluate_train(t25), AL.evaluate_train(t40)
    print({k: v for k, v in m25.items() if k != "months"})
    print(AL.passes_train(m25, m40))
