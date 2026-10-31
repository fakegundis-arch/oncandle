"""Supply & demand v2 (family 'structure_trend', found by an explorer agent and confirmed by an independent auditor):
market-structure aligned fair-value-gap zones on gold. Chosen on 2026 only (scripts/sd_v2_eval.py protocol).

Rules (cfg = BEST), all on Exness XAUUSD M1 bid bars (UTC), longs at the ask = bid + cost:
  1. Zone timeframe `ztf` (15 min). A bullish fair-value gap (FVG) exists at bar i when low[i] > high[i-2] (candle 1 high
     below candle 3 low); bearish mirror: high[i] < low[i-2]. ATR = ATR(14) (simple mean of true range) of bar i-3.
     Demand zone: proximal = low[i] (top of the gap), distal = low[i-2] (candle-1 low). Supply: proximal = high[i],
     distal = high[i-2]. Zone height = |proximal - distal| / ATR must be <= `hmax`; gap size / ATR >= `gmin`.
  2. Impulse broke structure (`bos` = 'zL'): swing highs / lows on the zone timeframe are fractal pivots with L bars on
     each side (strictly higher than the L bars before, >= the L bars after), known L bars after the pivot. Take the last
     swing high that was still unbroken (no close above it since it was confirmed) as of bar i-2's close. The zone
     activates at the first close above that level among bars i-1 .. i+`w` (not before bar i's close); if there is no
     such close, or no unbroken swing high existed, the zone is discarded. Supply mirrors with swing lows / closes below.
  3. Higher-timeframe structure (`htf` = 'stf_L_type_fill'): daily (1440-min, 00:00 UTC) bars, fractal pivots with L
     bars each side. 'hhhl' = last two confirmed swing highs rising AND last two confirmed swing lows rising (falling for
     downtrend). 'bos' = direction of the last close beyond the last unbroken swing high / low. 'both' = hhhl and bos
     agree. Evaluated from the last COMPLETED daily bar at the minute the order fills; must equal the zone direction.
  4. Entry: limit order at distal + f x (proximal - distal) (f = 1: the proximal line, i.e. the gap edge) from the
     activation bar's close, valid for `age` zone bars after the activation bar. A touch before activation kills the zone. Only the first touch counts (zone is then used up,
     whether or not it is traded). A fill needs the ask low (bid low + cost) to reach the level (shorts: bid high); if
     the minute opens beyond the level the fill is at the open. Fills inside the first 15 minutes after a market reopen
     (pause > 30 min) or beyond the distal line are cancelled. One position at a time: a touch while a position is open
     (or in the minute the previous trade closed) is skipped. Optional session filter on the fill hour (`ses`).
  5. Exits: R = max(|limit level - (distal -/+ buf x ATR)|, $1.5); stop = level -/+ R; target = level +/- `tgt` x R
     (filled at exactly the target, never better). Stop checked before target in each minute; the fill minute can only
     stop out. After the best price reaches +`be` R the stop moves to entry + 0.1 R (from the next minute). Gapped
     stops fill at the open. Result r = (exit - fill) / R in the trade direction (costs included via bid/ask).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from backtester import gold as G, sd as SD, indicators as ind  # noqa: E402

MIN_STOP = 1.5
BE_BUF = 0.1

BEST = {"ztf": 15, "bos": "z3", "w": 12, "f": 1.0, "buf": 0.25, "tgt": "r12", "be": 1.0,
        "htf": "1440_4_both_fill", "gmin": 0.0, "hmax": 1.0, "ses": "all", "age": 96}

# The grid searched (pass 5); one-step neighbours are adjacent values in these ordered lists. For bos, 'none' is a
# separate option (no neighbour of z-values); htf moves one step in stf, L or type (hhhl <-> both).
GRID = {"ztf": [10, 15, 20], "bos": ["none", "z2", "z3", "z4", "z5"], "w": [0, 4, 12], "f": [1.0, 0.75],
        "buf": [0.1, 0.25, 0.5, 0.75], "tgt": ["r8", "r10", "r12", "r16", "r20", "r30"],
        "be": [0, 0.75, 1.0, 1.5, 2.0], "gmin": [0.0, 0.15, 0.3], "hmax": [0.75, 1.0, 1.25, 1.5, 2.5, 99.0],
        "ses": ["all", "07-20"], "age": [48, 96, 192],
        "htf_stf": [240, 480, 1440], "htf_L": [2, 3, 4, 5, 6], "htf_type": ["hhhl", "both"]}


def neighbours(cfg: dict) -> list[dict]:
    out = []
    for k, vals in GRID.items():
        if k.startswith("htf_"):
            continue
        if k == "w" and cfg["bos"] == "none":
            continue
        if k == "bos":
            vals = [v for v in vals if v != "none"] if cfg["bos"] != "none" else []
        if cfg[k] not in vals:
            continue
        p = vals.index(cfg[k])
        for q in (p - 1, p + 1):
            if 0 <= q < len(vals):
                out.append({**cfg, k: vals[q]})
    if cfg["htf"] != "none":
        stf, L, typ, when = cfg["htf"].split("_")
        parts = {"htf_stf": int(stf), "htf_L": int(L), "htf_type": typ}
        for k, vals in (("htf_stf", GRID["htf_stf"]), ("htf_L", GRID["htf_L"]), ("htf_type", GRID["htf_type"])):
            p = vals.index(parts[k])
            for q in (p - 1, p + 1):
                if 0 <= q < len(vals):
                    pp = {**parts, k: vals[q]}
                    out.append({**cfg, "htf": f"{pp['htf_stf']}_{pp['htf_L']}_{pp['htf_type']}_{when}"})
    return out


NEIGHBOURS = neighbours(BEST)


# ----------------------------------------------------------------------------------------------------------- kernels
@njit(cache=True)
def _structure(h, l, c, L):
    n = len(h)
    trend = np.zeros(n, np.int64); hhhl = np.zeros(n, np.int64)
    open_sh = np.full(n, np.nan); open_sl = np.full(n, np.nan)
    lastSH = np.nan; prevSH = np.nan; lastSL = np.nan; prevSL = np.nan
    brokeH = True; brokeL = True; tr = 0
    for b in range(n):
        j = b - L
        if j >= L:
            isH = True; isL = True
            for q in range(j - L, j + L + 1):
                if q == j:
                    continue
                if h[q] > h[j] or (q < j and h[q] == h[j]):
                    isH = False
                if l[q] < l[j] or (q < j and l[q] == l[j]):
                    isL = False
            if isH:
                prevSH = lastSH; lastSH = h[j]; brokeH = False
            if isL:
                prevSL = lastSL; lastSL = l[j]; brokeL = False
        if (not brokeH) and c[b] > lastSH:
            tr = 1; brokeH = True
        if (not brokeL) and c[b] < lastSL:
            tr = -1; brokeL = True
        trend[b] = tr
        if lastSH > prevSH and lastSL > prevSL:
            hhhl[b] = 1
        elif lastSH < prevSH and lastSL < prevSL:
            hhhl[b] = -1
        if not brokeH:
            open_sh[b] = lastSH
        if not brokeL:
            open_sl[b] = lastSL
    return trend, hhhl, open_sh, open_sl


@njit(cache=True)
def _fvg(h, l, atr):
    n = len(h)
    zi = np.empty(n, np.int64); zd = np.empty(n, np.int64); zg = np.empty(n); za = np.empty(n)
    zp = np.empty(n); zs = np.empty(n)
    m = 0
    for i in range(4, n):
        a = atr[i - 3]
        if not (a > 0):
            continue
        if l[i] > h[i - 2]:
            zi[m] = i; zd[m] = 1; zg[m] = (l[i] - h[i - 2]) / a; zp[m] = l[i]; zs[m] = l[i - 2]
        elif h[i] < l[i - 2]:
            zi[m] = i; zd[m] = -1; zg[m] = (l[i - 2] - h[i]) / a; zp[m] = h[i]; zs[m] = h[i - 2]
        else:
            continue
        za[m] = a
        m += 1
    return zi[:m], zd[:m], zg[:m], za[:m], zp[:m], zs[:m]


@njit(cache=True)
def _activate(zi, zd, ref, c, w):
    out = np.full(len(zi), -1, np.int64)
    for z in range(len(zi)):
        lv = ref[z]
        if not (lv == lv):
            continue
        i = zi[z]
        for k in range(i - 1, min(i + w + 1, len(c))):
            if zd[z] * (c[k] - lv) > 0:
                out[z] = max(k, i)
                break
    return out


@njit(cache=True)
def _fill(o, h, l, k_make, k_act, k_end, d, lvl, dist, reopen, cost, k_lo, pen):
    """First touch of each zone's level: -1 none, -2 cancelled (reopen / beyond distal), -3 touched before activation,
    -4 before k_lo (not simulated). `pen` > 0 demands the price trade through the level by that many $."""
    nz = len(lvl)
    fi = np.full(nz, -1, np.int64); fp = np.full(nz, np.nan)
    for z in range(nz):
        if k_act[z] < 0:
            continue
        for k in range(k_make[z], min(k_end[z], len(o))):
            px = np.nan
            if d[z] == 1:
                if o[k] + cost <= lvl[z] - pen:
                    px = o[k] + cost
                elif l[k] + cost <= lvl[z] - pen:
                    px = lvl[z]
            else:
                if o[k] >= lvl[z] + pen:
                    px = o[k]
                elif h[k] >= lvl[z] + pen:
                    px = lvl[z]
            if px == px:
                if k < k_act[z]:
                    fi[z] = -3
                elif k < k_lo:
                    fi[z] = -4
                elif reopen[k] or d[z] * (px - dist[z]) <= 0:
                    fi[z] = -2
                else:
                    fi[z] = k; fp[z] = px
                break
    return fi, fp


@njit(cache=True)
def _outcome(o, h, l, c, fi, fp, d, lvl, stop_lvl, rr, be, cost):
    nz = len(fi)
    xi = np.full(nz, -1, np.int64); res = np.zeros(nz)
    n = len(o)
    for z in range(nz):
        j = fi[z]
        if j < 0:
            continue
        dz = d[z]; entry = fp[z]
        R = max(dz * (lvl[z] - stop_lvl[z]), MIN_STOP)
        stop = lvl[z] - dz * R; tgt = lvl[z] + dz * rr * R
        best = entry; moved = False; px = np.nan; k = j
        while k < n:
            if dz == 1:
                bo = o[k]; bh = h[k]; bl = l[k]
                if bl <= stop:
                    px = min(bo, stop) if k > j else stop
                    break
                if k > j and bh >= tgt:
                    px = tgt
                    break
                if k > j:
                    best = max(best, bh)
            else:
                bo = o[k] + cost; bh = h[k] + cost; bl = l[k] + cost
                if bh >= stop:
                    px = max(bo, stop) if k > j else stop
                    break
                if k > j and bl <= tgt:
                    px = tgt
                    break
                if k > j:
                    best = min(best, bl)
            if be > 0 and not moved and dz * (best - entry) >= be * R:
                stop = entry + dz * BE_BUF * R
                moved = True
            k += 1
        if k >= n:
            k = n - 1
            px = c[k] if dz == 1 else c[k] + cost
        xi[z] = k
        res[z] = dz * (px - entry) / R
    return xi, res


@njit(cache=True)
def _taken(order, fi, xi, mask):
    out = np.empty(len(order), np.int64); m = 0; busy = -1
    for z in order:
        if fi[z] < 0:
            break
        if mask[z] and fi[z] > busy:
            out[m] = z; m += 1; busy = xi[z]
    return out[:m]


# ------------------------------------------------------------------------------------------------------------- driver
_CACHE: dict = {}


def _m1():
    return G.data(ROOT)[0]


def _bars(tf):
    if ("bars", tf) not in _CACHE:
        m1 = _m1()
        b = SD.resample(m1, tf).copy()
        b["atr"] = ind.atr(b, 14)
        b["k_close"] = m1.index.searchsorted((b.index + pd.Timedelta(minutes=tf)).to_numpy())
        _CACHE[("bars", tf)] = b
    return _CACHE[("bars", tf)]


def _struct(tf, L):
    if ("st", tf, L) not in _CACHE:
        b = _bars(tf)
        tr, hh, osh, osl = _structure(*(b[k].to_numpy(np.float64) for k in ("high", "low", "close")), L)
        _CACHE[("st", tf, L)] = dict(kc=b.k_close.to_numpy(np.int64), trend=tr, hhhl=hh, osh=osh, osl=osl)
    return _CACHE[("st", tf, L)]


def _at(st, name, k):
    pos = np.searchsorted(st["kc"], k, side="right") - 1
    v = st[name][np.maximum(pos, 0)]
    return np.where(pos >= 0, v, 0)


def make_trades(cfg: dict, cost: float, start=None, pen: float = 0.0) -> pd.DataFrame:
    """Trades of `cfg` over all data (or only fills from `start`), one position at a time:
    entry_time, exit_time, dir, r."""
    m1 = _m1()
    o, h, l, c = (m1[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    if "reopen" not in _CACHE:
        _CACHE["reopen"] = SD.reopen_mask(m1.index)
    reo = _CACHE["reopen"]
    k_lo = 0 if start is None else int(m1.index.searchsorted(pd.Timestamp(start)))
    ztf = cfg["ztf"]
    b = _bars(ztf)
    kc = b.k_close.to_numpy(np.int64)
    zi, d, gap, atr, prox, dist = _fvg(b.high.to_numpy(np.float64), b.low.to_numpy(np.float64),
                                       b.atr.to_numpy(np.float64))
    # activation: the impulse broke the last unbroken zone-TF swing level
    if cfg["bos"] == "none":
        a = zi.copy()
    else:
        st = _struct(ztf, int(cfg["bos"][1:]))
        ref = np.where(d == 1, st["osh"][zi - 2], st["osl"][zi - 2])
        a = _activate(zi, d, ref, b.close.to_numpy(np.float64), cfg["w"])
    k_act = np.where(a >= 0, kc[np.maximum(a, 0)], -1).astype(np.int64)
    end_bar = np.maximum(a, 0) + cfg["age"]
    k_end = np.where(end_bar < len(kc), kc[np.minimum(end_bar, len(kc) - 1)], len(m1)).astype(np.int64)
    lvl = dist + cfg["f"] * (prox - dist)
    stop = dist - d * cfg["buf"] * atr
    height = np.abs(prox - dist) / atr
    fi, fp = _fill(o, h, l, kc[zi], k_act, k_end, d, lvl, dist, reo, cost, k_lo, pen)
    xi, r = _outcome(o, h, l, c, fi, np.nan_to_num(fp), d, lvl, stop, float(cfg["tgt"][1:]), float(cfg["be"]), cost)
    ok = (fi >= 0) & (gap >= cfg["gmin"]) & (height <= cfg["hmax"])
    if cfg["ses"] != "all":
        s0, s1 = (int(x) for x in cfg["ses"].split("-"))
        hr = m1.index.hour.to_numpy()[np.maximum(fi, 0)]
        ok &= (hr >= s0) & (hr < s1)
    if cfg["htf"] != "none":
        stf, L, typ, when = cfg["htf"].split("_")
        st = _struct(int(stf), int(L))
        kk = np.maximum(fi, 0) if when == "fill" else k_act
        if typ == "both":
            ok &= (_at(st, "trend", kk) == d) & (_at(st, "hhhl", kk) == d)
        else:
            ok &= _at(st, "trend" if typ == "bos" else "hhhl", kk) == d
    order = np.argsort(np.where(fi >= 0, fi, np.iinfo(np.int64).max), kind="mergesort").astype(np.int64)
    k = _taken(order, fi, xi, ok)
    return pd.DataFrame({"entry_time": m1.index[fi[k]], "exit_time": m1.index[xi[k]], "dir": d[k], "r": r[k]})
