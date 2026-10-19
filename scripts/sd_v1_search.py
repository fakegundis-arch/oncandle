#!/usr/bin/env python3
"""Supply & demand v1 search on gold (XAUUSD, Exness spread $0.25 on every trade), chosen on 2026 ONLY.

Grid (one position at a time; zone rules in backtester/sd.py):
  tf       zone bar size (minutes)                    15, 30, 60, 240
  base     base candle max range (x ATR)               0.5, 0.75, 1.0
  nbase    max base candles                            1, 2, 3
  leg      leg-out min range (x ATR)                   1.25, 1.75, 2.5
  hmax     max zone height (x ATR)                     0.75, 1.5, 3.0
  entry    limit at the proximal line / zone middle    prox, mid
  buf      stop beyond the distal line (x ATR)         0.05, 0.25
  rr       target (x risk)                             1.5, 2, 3, 4
  be       stop to entry + 0.1R after +1R              off, on
  trend    trade with: nothing / EMA(200) of the zone bars / yesterday's daily close vs EMA(20)
  session  first touch at any hour / 07:00-20:00 UTC only
  age      order valid for this many zone bars          24, 96, 384
  pattern  all / reversal (drop-base-rally, rally-base-drop) / continuation (rally-base-rally, drop-base-drop)
Metrics in R per period (one continuous run, periods by fill time): trades, total R, profit factor, max R drawdown.
2026 (full, Jan-May, Jun-Oct) -> results/sd/v1_search.npz; 2025 and 15 Nov - 31 Dec 2024 -> results/sd/v1_sealed.npz.
    python scripts/sd_v1_search.py
"""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import gold as G, sd as SD  # noqa: E402
from backtester.engine import njit  # noqa: E402

COST, MIN_STOP, BE_BUF = 0.25, 1.5, 0.1
OUT = ROOT / "results/sd"
SEL = {"y26": ("2026-01-01", "2026-10-16"), "h1": ("2026-01-01", "2026-06-01"), "h2": ("2026-06-01", "2026-10-16")}
SEALED = {"y25": ("2025-01-01", "2026-01-01"), "late24": ("2024-11-15", "2025-01-01")}

ZONE = dict(tf=[15, 30, 60, 240], base=[0.5, 0.75, 1.0])
SIM = dict(entry=["prox", "mid"], buf=[0.05, 0.25], rr=[1.5, 2.0, 3.0, 4.0], be=[0.0, 1.0])
MASK = dict(nbase=[1, 2, 3], leg=[1.25, 1.75, 2.5], hmax=[0.75, 1.5, 3.0], trend=["none", "tf", "d1"],
            session=["all", "07-20"], age=[24, 96, 384], pattern=["all", "rev", "cont"])
DIMS = {**ZONE, **SIM, **MASK}
METRICS = ("n", "R", "pf", "dd")


@njit(cache=True)
def greedy(order, fi, xi, r, mask, lo, hi):
    """Take zones in fill order, one position at a time; per period [lo, hi) of fill minutes: trades, total R,
    gross win, gross loss, max drawdown of cumulative R."""
    npr = len(lo)
    n = np.zeros(npr); s = np.zeros(npr); gw = np.zeros(npr); gl = np.zeros(npr); dd = np.zeros(npr)
    pk = np.zeros(npr)
    busy = -1
    for z in order:
        if not mask[z] or fi[z] <= busy:
            continue
        busy = xi[z]
        for p in range(npr):
            if lo[p] <= fi[z] < hi[p]:
                n[p] += 1; s[p] += r[z]
                if r[z] > 0:
                    gw[p] += r[z]
                else:
                    gl[p] -= r[z]
                pk[p] = max(pk[p], s[p]); dd[p] = min(dd[p], s[p] - pk[p])
    return n, s, gw, gl, dd


def zone_set(m1, tf, base):
    """Zones of one bar size / base setting with their fill minute for both entry levels (longest age) and the
    minute each age runs out."""
    bars = G.data(ROOT)[1] if tf == 15 else SD.resample(m1, tf)
    z = SD.zones(bars, tf, base, min(MASK["leg"]))
    idx = m1.index
    pos = bars.index.get_indexer(z.t_make - pd.Timedelta(minutes=tf))          # leg-out bar position
    start = idx.searchsorted(z.t_make.to_numpy())
    ends = {}
    for a in MASK["age"]:
        k = np.minimum(pos + 1 + a, len(bars) - 1)
        ends[a] = idx.searchsorted(bars.index[k].to_numpy())
    o, h, l = (m1[c].to_numpy(np.float64) for c in ("open", "high", "low"))
    d = z.dir.to_numpy(np.int64)
    lv = {"prox": z.prox.to_numpy(), "mid": ((z.prox + z.dist) / 2).to_numpy()}
    fl = {e: SD.fills(o, h, l, start, ends[max(MASK["age"])], d, lv[e], COST) for e in SIM["entry"]}
    return z, ends, fl


def zone_mask(z, tr, pat, fi, ends, in_ses, nb, lg, hm, t, s, a, pt):
    return ((z.n_base.to_numpy() <= nb) & (z.leg.to_numpy() >= lg) & (z.height.to_numpy() <= hm) & tr[t] & pat[pt]
            & (fi < ends[a]) & (in_ses if s == "07-20" else True))


@njit(cache=True)
def taken(order, fi, xi, mask):
    """Zones actually traded (fill order, one position at a time)."""
    out = np.empty(len(order), np.int64); m = 0; busy = -1
    for z in order:
        if mask[z] and fi[z] > busy:
            out[m] = z; m += 1; busy = xi[z]
    return out[:m]


def trades_for(cfg):
    """Trade list of one setting (dict over DIMS): fill time, exit time, dir, R, stop distance in $."""
    m1 = G.data(ROOT)[0]
    o, h, l, c = (m1[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    z, ends, fl = zone_set(m1, cfg["tf"], cfg["base"])
    d = z.dir.to_numpy(np.int64)
    fi, fp = fl[cfg["entry"]]
    stop_lvl = (z.dist - z.dir * cfg["buf"] * z.atr).to_numpy()
    xi, r = SD.outcomes(o, h, l, c, fi, fp, d, stop_lvl, cfg["rr"], cfg["be"], BE_BUF, COST, MIN_STOP)
    filled = fi >= 0
    hours = m1.index.hour.to_numpy()
    in_ses = filled & (hours[np.maximum(fi, 0)] >= 7) & (hours[np.maximum(fi, 0)] < 20)
    tr = {"none": np.ones(len(z), bool), "tf": (z.tr_tf == z.dir).to_numpy(), "d1": (z.tr_d1 == z.dir).to_numpy()}
    pat = {"all": np.ones(len(z), bool), "rev": (z.pattern == 1).to_numpy(), "cont": (z.pattern == 2).to_numpy()}
    m = filled & zone_mask(z, tr, pat, fi, ends, in_ses, *(cfg[k] for k in MASK))
    order = np.argsort(np.where(filled, fi, np.iinfo(np.int64).max), kind="mergesort").astype(np.int64)
    k = taken(order, fi, xi, m)
    R = np.maximum(d[k] * (fp[k] - stop_lvl[k]), MIN_STOP)
    return pd.DataFrame({"entry_time": m1.index[fi[k]], "exit_time": m1.index[xi[k]], "dir": d[k], "r": r[k],
                         "entry": fp[k], "risk_usd": R, "zone_made": z.t_make.to_numpy()[k]})


def job(key):
    tf, base = key
    m1 = G.data(ROOT)[0]
    o, h, l, c = (m1[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    z, ends, fl = zone_set(m1, tf, base)
    d = z.dir.to_numpy(np.int64)
    hours = m1.index.hour.to_numpy()
    per = {**SEL, **SEALED}
    lo = np.array([m1.index.searchsorted(pd.Timestamp(a)) for a, b in per.values()], np.int64)
    hi = np.array([m1.index.searchsorted(pd.Timestamp(b)) for a, b in per.values()], np.int64)
    # zone masks (independent of the exit settings)
    tr = {"none": np.ones(len(z), bool), "tf": (z.tr_tf == z.dir).to_numpy(), "d1": (z.tr_d1 == z.dir).to_numpy()}
    pat = {"all": np.ones(len(z), bool), "rev": (z.pattern == 1).to_numpy(), "cont": (z.pattern == 2).to_numpy()}
    shape = [len(v) for v in SIM.values()] + [len(v) for v in MASK.values()]
    res = {f"{p}_{m}": np.zeros(shape, np.float32) for p in per for m in METRICS}
    for (ie, e), (ib, buf), (ir, rr), (ix, be) in itertools.product(*(enumerate(v) for v in SIM.values())):
        fi, fp = fl[e]
        stop_lvl = (z.dist - z.dir * buf * z.atr).to_numpy()
        xi, r = SD.outcomes(o, h, l, c, fi, fp, d, stop_lvl, rr, be, BE_BUF, COST, MIN_STOP)
        filled = fi >= 0
        order = np.argsort(np.where(filled, fi, np.iinfo(np.int64).max), kind="mergesort").astype(np.int64)
        in_ses = filled & (hours[np.maximum(fi, 0)] >= 7) & (hours[np.maximum(fi, 0)] < 20)
        for mi, combo in enumerate(itertools.product(*MASK.values())):
            m = filled & zone_mask(z, tr, pat, fi, ends, in_ses, *combo)
            n, sR, gw, gl, dd = greedy(order, fi, xi, r, m, lo, hi)
            cell = (ie, ib, ir, ix) + np.unravel_index(mi, [len(v) for v in MASK.values()])
            for p_i, p in enumerate(per):
                res[f"{p}_n"][cell] = n[p_i]; res[f"{p}_R"][cell] = sR[p_i]
                res[f"{p}_pf"][cell] = gw[p_i] / gl[p_i] if gl[p_i] > 0 else (99.0 if gw[p_i] > 0 else 0.0)
                res[f"{p}_dd"][cell] = dd[p_i]
    return key, len(z), res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    keys = list(itertools.product(*ZONE.values()))
    shape = [len(v) for v in DIMS.values()]
    print(f"{int(np.prod(shape)):,} combinations", flush=True)
    full = {f"{p}_{m}": np.zeros(shape, np.float32) for p in {**SEL, **SEALED} for m in METRICS}
    with ProcessPoolExecutor(4) as ex:
        for key, nz, res in ex.map(job, keys):
            it, ib = ZONE["tf"].index(key[0]), ZONE["base"].index(key[1])
            for k, v in res.items():
                full[k][it, ib] = v
            print(f"  tf {key[0]:>3} base {key[1]}: {nz:,} zones", flush=True)
    np.savez_compressed(OUT / "v1_search.npz", shape=np.array(shape), **{k: v for k, v in full.items() if k.split("_")[0] in SEL})
    np.savez_compressed(OUT / "v1_sealed.npz", shape=np.array(shape), **{k: v for k, v in full.items() if k.split("_")[0] in SEALED})
    print("2026 -> results/sd/v1_search.npz | 2025 and late 2024 sealed -> results/sd/v1_sealed.npz")


if __name__ == "__main__":
    main()
