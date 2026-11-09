"""per 5-min bucket features for the open-interest-drop signal family (loose thresholds) -> sig.parquet"""
import numpy as np
import pandas as pd

import lab
from lab import bc


def build(L, oi_th=-0.002, mv_th=0.0015):
    m = L.metrics
    ts = m.ts.to_numpy()
    oi = m.sum_open_interest.to_numpy()
    prev_ok = np.r_[False, np.diff(ts) == 300]
    doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]
    doi[~prev_ok] = np.nan
    prev2 = np.r_[False, False, (ts[2:] - ts[:-2]) == 600]
    doi2 = np.r_[np.nan, np.nan, oi[2:] / oi[:-2] - 1]
    doi2[~prev2] = np.nan
    i = ts - L.t0
    ok = (i >= 3600 * 26) & (i + 60 < L.n)
    px = lambda k: L.c[np.clip(k, 0, L.n - 1)]
    mv = px(i) / px(i - 300) - 1
    sel = ok & (doi <= oi_th) & (np.abs(mv) >= mv_th)
    idx = np.flatnonzero(sel)
    i = i[idx]
    T = ts[idx]
    d = np.sign(mv[idx]).astype(int)
    dec = T + 60
    f = pd.DataFrame(dict(T=T, dec=dec, dir=d, doi=doi[idx], doi2=doi2[idx], mv=mv[idx]))
    f["mv_abs"] = np.abs(f.mv)
    f["mv_pre"] = d * (px(i - 300) / px(i - 600) - 1)          # previous bucket move, in direction
    f["mv_post"] = d * (px(i + 59) / px(i) - 1)                 # T -> decision (known at dec)
    f["mv_1h"] = d * (px(i) / px(i - 3600) - 1)
    f["mv_4h"] = d * (px(i) / px(i - 4 * 3600) - 1)
    f["mv_24h"] = d * (px(i) / px(i - 24 * 3600) - 1)
    CB = np.r_[0.0, np.cumsum(L.bq, dtype=np.float64)]
    CS = np.r_[0.0, np.cumsum(L.sq, dtype=np.float64)]
    b5 = CB[i] - CB[i - 300]
    s5 = CS[i] - CS[i - 300]
    f["net"] = d * (b5 - s5)
    f["tot"] = b5 + s5
    f["netr"] = f.net / f.tot.clip(lower=1e-9)
    bp = CB[i + 59] - CB[i]
    sp_ = CS[i + 59] - CS[i]
    f["net_post"] = d * (bp - sp_)
    tot1h = (CB[i] - CB[i - 3600]) + (CS[i] - CS[i - 3600])
    f["totrel"] = f.tot / np.maximum(tot1h / 12, 1e-9)          # bucket volume vs mean bucket of last hour
    f["vol"] = L.vol_at(dec)
    f["price"] = px(i + 59)
    f["mv_vol"] = f.mv_abs * f.price / f.vol                    # move size in vol units
    # vol regime: vol now vs vol 24h average (past)
    mvs = pd.Series(L.mv).rolling(1440, min_periods=600).mean().to_numpy()
    sm = (dec - L.t0) // 60 - 1
    f["vol24"] = mvs[np.clip(sm, 0, len(mvs) - 1)]
    f["volrel"] = f.vol / f.vol24
    # bucket extremes (Binance) over [T-300, dec)
    hh = np.empty(len(i))
    ll = np.empty(len(i))
    hh15 = np.empty(len(i))
    ll15 = np.empty(len(i))
    for k, ii in enumerate(i):
        hh[k] = np.nanmax(L.h[ii - 300: ii + 59])
        ll[k] = np.nanmin(L.l[ii - 300: ii + 59])
        hh15[k] = np.nanmax(L.h[ii - 900: ii + 59])
        ll15[k] = np.nanmin(L.l[ii - 900: ii + 59])
    p = f.price.to_numpy()
    # distance from current price back to the far side of the move (swing), $ ; and continuation room
    f["swing5"] = np.where(d > 0, p - ll, hh - p)
    f["swing15"] = np.where(d > 0, p - ll15, hh15 - p)
    f["ext5"] = np.where(d > 0, hh - p, p - ll)                 # how far price has come off the extreme in dir
    # Exness spread at last quote before dec
    T_ = L.tk["t"]
    q = np.searchsorted(T_, dec) - 1
    f["spread"] = L.tk["ask_last"][q] - L.tk["bid_last"][q]
    f["qage"] = dec - T_[q]
    # time
    dt = pd.to_datetime(dec, unit="s")
    f["hour"] = dt.hour
    f["dow"] = dt.dayofweek
    f["mins_to_midnight"] = (86400 - (dec % 86400)) / 60
    # daily levels (UTC day): open, high/low so far, previous day's high/low
    day = (L.t0 + np.arange(0, L.n, 60)) // 86400
    mcl = L.mc
    dfm = pd.DataFrame(dict(day=day[:len(mcl)], c=mcl))
    g = dfm.groupby("day").c
    dopen = g.transform("first").to_numpy()
    dhi = g.cummax().to_numpy()
    dlo = g.cummin().to_numpy()
    dayhl = dfm.groupby("day").c.agg(["max", "min"])
    prevh = dfm.day.map(dayhl["max"].shift(1)).to_numpy()
    prevl = dfm.day.map(dayhl["min"].shift(1)).to_numpy()
    mi = np.clip(sm, 0, len(mcl) - 1)
    f["d_open"] = d * (p / dopen[mi] - 1)
    f["d_hi"] = (dhi[mi] - p) / f.vol                         # vol units to day high so far
    f["d_lo"] = (p - dlo[mi]) / f.vol
    f["to_break"] = np.where(d > 0, (prevh[mi] - p), (p - prevl[mi])) / f.vol   # distance to prev-day extreme in dir
    f["beyond_prev"] = np.where(d > 0, p > prevh[mi], p < prevl[mi]).astype(int)
    # metrics row values
    mm = m.iloc[idx].reset_index(drop=True)
    f["ttls"] = mm.sum_toptrader_long_short_ratio.to_numpy()
    f["ls"] = mm.count_long_short_ratio.to_numpy()
    f["takr"] = mm.sum_taker_long_short_vol_ratio.to_numpy()
    prevm = m.iloc[np.maximum(idx - 1, 0)].reset_index(drop=True)
    f["dls"] = d * (f.ls.to_numpy() - prevm.count_long_short_ratio.to_numpy())
    # ETH OI change in same bucket
    e = L.eth.set_index("ts").sum_open_interest
    eprev = e.shift(1)
    eo = (e / eprev - 1).reindex(T).to_numpy()
    f["eth_doi"] = eo
    # funding last known
    fts = L.funding.ts.to_numpy()
    fk = np.searchsorted(fts, dec, side="right") - 1
    f["funding"] = np.where(fk >= 0, L.funding.last_funding_rate.to_numpy()[np.maximum(fk, 0)], np.nan) * d
    # premium last known minute close
    pk = np.searchsorted(L.premium.known_ts.to_numpy(), dec, side="right") - 1
    f["prem"] = L.premium.close.to_numpy()[np.maximum(pk, 0)] * d
    # repeats: number of earlier qualifying buckets in last 30 / 60 min (v2-like definition) computed later
    return f


if __name__ == "__main__":
    L = lab.Lab()
    f = build(L)
    f.to_parquet("sig.parquet")
    print(f.shape)
    print(f.describe().T.to_string())
