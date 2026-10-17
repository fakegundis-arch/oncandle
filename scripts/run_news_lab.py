#!/usr/bin/env python3
"""Search news strategies built from scratch (see backtester/news_lab.py).

    python scripts/run_news_lab.py            # -> results/news_lab/grid.parquet

Every entry family x wait x spike size x verdict filter x event scope x stop x exit x max hold, scored for
every market alone, for "all markets of the event" (risk split equally) and "best" (largest spike only).
Per year: trades, win rate, avg R, PF, $1,000 at 10% risk, and the risk f* (from a grid) that maximises 2025 growth.
Costs: Exness spread x 5 if the entry is < 3 min after the release, x 3 if < 10 min, else x 2.
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
from backtester import data as D, indicators as ind, news_lab as L  # noqa: E402
from backtester.engine import njit  # noqa: E402

MARKETS = list(L.USD_BULL_DIRECTION)
FAMILIES = {"cont": 0, "fade": 1, "news": 2, "retest": 3}
FILTS = {"any": 0, "agree": 1, "disagree": 2}
ENTRY_GRID = dict(family=tuple(FAMILIES), w=(1, 2, 3, 5, 10, 15, 30, 60), k=(0.0, 1.0, 3.0, 6.0, 10.0),
                  filt=tuple(FILTS), scope=("all", "usd", "high", "tier1"))
STOPS = (3.0, 6.0, 12.0, 24.0, -1.0)          # x a; -1 = 0.75 x the spike (at least 3 a)
EXITS = [(rr, be, 0.0) for rr in (1.0, 2.0, 3.0, 5.0) for be in (0.0, 1.0)] + [(0.0, 0.0, 1.0), (0.0, 0.0, 2.0)]
MAX_BARS = (30, 240, 1440)
FGRID = np.array([0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5])
YEARS = {"y24": ("2024-11-01", "2025-01-01"), "y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}
PICKS = ["all", "best"] + MARKETS

SURPRISE_GRID = dict(family=tuple(FAMILIES), w=(1, 3, 5, 15, 30, 60), k=(0.0, 3.0), filt=("agree", "disagree"),
                     scope=("all", "usd"), zmin=(1.0, 2.0, 3.0))

_M = {}


def calendar():
    """Main calendar plus older history (only used to size surprises from past releases)."""
    cd = ROOT / "data" / "calendar"
    cal = pd.read_csv(cd / "ff_calendar.csv", parse_dates=["time_utc"])
    old = cd / "ff_calendar_2022_2024.csv"
    if old.exists():
        o = pd.read_csv(old, parse_dates=["time_utc"])
        both = pd.concat([o[o.time_utc < cal.time_utc.min()], cal], ignore_index=True)
        both["z"] = L.surprises(both)
        cal = both[both.time_utc >= cal.time_utc.min()].reset_index(drop=True)
    else:
        cal["z"] = L.surprises(cal)
    return cal


def load():
    if _M:
        return _M
    ev = L.events(calendar())
    ev["eid"] = np.arange(len(ev))
    for m in MARKETS:
        m1 = D.load_csv(ROOT / "data" / f"{m}_M1.csv").drop(columns="spread", errors="ignore")
        tr = ind.true_range(m1).rolling(240).mean().shift().to_numpy()
        p = L.pairs(ev, m, m1, tr).merge(ev[["time_utc", "currency", "eid"]], left_on=["time", "currency"],
                                         right_on=["time_utc", "currency"])
        arr = tuple(m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
        _M[m] = (p, arr)
    _M["_ev"] = ev
    return _M


@njit(cache=True)
def growth(r, f):
    eq = 1.0
    peak = 1.0
    dd = 0.0
    for x in r:
        eq = max(eq * (1 + f * x), 0.0)
        peak = max(peak, eq)
        if peak > 0:
            dd = min(dd, eq / peak - 1)
    return eq, dd


def year_stats(t_ev, r, pre):
    out = {}
    for k, (a, b) in YEARS.items():
        sel = (t_ev >= np.datetime64(a)) & (t_ev < np.datetime64(b))
        x = r[sel]
        n = len(x)
        out[f"{k}_n"] = n
        if n == 0:
            continue
        loss = -x[x < 0].sum()
        out[f"{k}_win"] = (x > 0).mean()
        out[f"{k}_avg"] = x.mean()
        out[f"{k}_pf"] = x[x > 0].sum() / loss if loss > 0 else 99.0
        eq, dd = growth(x, 0.10)
        out[f"{k}_usd10"] = 1000 * eq
        out[f"{k}_dd10"] = dd
        if k == "y25":
            gs = [growth(x, f)[0] for f in FGRID]
            pre["f"] = FGRID[int(np.argmax(gs))]
    if "f" in pre:
        for k in ("y25", "y26"):
            a, b = YEARS[k]
            x = r[(t_ev >= np.datetime64(a)) & (t_ev < np.datetime64(b))]
            if len(x):
                eq, dd = growth(x, pre["f"])
                out[f"{k}_usdf"] = 1000 * eq
                out[f"{k}_ddf"] = dd
        out["f"] = pre["f"]
    return out


def job(ekw):
    M = load()
    fam, filt = FAMILIES[ekw["family"]], FILTS[ekw["filt"]]
    if fam == 2 and filt != (1 if ekw.get("zmin") else 0):
        return pd.DataFrame()
    per_m = []
    for m in MARKETS:
        p, (o, h, l, c) = M[m]
        if ekw["scope"] == "usd":
            p = p[p.currency == "USD"]
        elif ekw["scope"] == "high":
            p = p[p.high == 1]
        elif ekw["scope"] == "tier1":
            p = p[p.tier1 == 1]
        if p.empty:
            continue
        nd = p.news_dir.to_numpy(np.int64)
        if ekw.get("zmin"):
            z = p.zdir.to_numpy()
            nd = np.where(np.abs(np.nan_to_num(z)) >= ekw["zmin"], np.sign(np.nan_to_num(z)), 0).astype(np.int64)
            keep = nd != 0
            p, nd = p[keep], nd[keep]
            if p.empty:
                continue
        rel = p.i.to_numpy(np.int64)
        a = p.a.to_numpy()
        ent, dr, spk = L.signals(o, h, l, c, rel, a, nd, fam, ekw["w"], ekw["k"], filt, 30)
        ok = ent >= 0
        if not ok.any():
            continue
        lag = ent - rel
        sp = D.EXNESS_STANDARD_SPREAD[m]
        cost = np.where(lag < 3, 5 * sp, np.where(lag < 10, 3 * sp, 2 * sp))
        per_m.append((m, o, h, l, c, ent[ok], dr[ok], spk[ok], a[ok], cost[ok], p.eid.to_numpy()[ok],
                      p.time.to_numpy()[ok]))
    if not per_m:
        return pd.DataFrame()
    EID = np.concatenate([x[10] for x in per_m])
    T = np.concatenate([x[11] for x in per_m]).astype("datetime64[ns]")
    MK = np.concatenate([np.full(len(x[5]), x[0]) for x in per_m])
    SPK = np.concatenate([x[7] for x in per_m])
    order = np.lexsort((-SPK, EID))
    first = np.r_[True, EID[order][1:] != EID[order][:-1]]
    BEST = order[first]
    _, INV = np.unique(EID, return_inverse=True)
    CNT = np.bincount(INV)
    T_ALL = T[np.unique(INV, return_index=True)[1]]
    rows = []
    for s, (rr, be, tk), mb in itertools.product(STOPS, EXITS, MAX_BARS):
        R_all = []
        for k_m, (m, o, h, l, c, ent, dr, spk, a, cost, eid, tm) in enumerate(per_m):
            sl = s * a if s > 0 else np.maximum(0.75 * spk * a, 3 * a)
            R, _ = L.simulate(o, h, l, c, ent, dr, sl, rr, tk * sl, be, mb, cost)
            R_all.append(R)
        r = np.concatenate(R_all)
        for pick in PICKS:
            if pick == "all":
                rr_ = np.bincount(INV, weights=r) / CNT
                tt = T_ALL
            elif pick == "best":
                tt, rr_ = T[BEST], r[BEST]
            else:
                sel = MK == pick
                if not sel.any():
                    continue
                tt, rr_ = T[sel], r[sel]
            if len(rr_) < 10:
                continue
            o_ = np.argsort(tt, kind="stable")
            st = year_stats(tt[o_], rr_[o_], {})
            rows.append({**ekw, "stop": s, "rr": rr, "be": be, "trail": tk, "max_bars": mb, "pick": pick, **st})
    df = pd.DataFrame(rows)
    for col in df.select_dtypes("float64"):
        df[col] = df[col].astype("float32")
    return df


def main():
    surprise = "--surprise" in sys.argv
    grid = SURPRISE_GRID if surprise else ENTRY_GRID
    jobs = [dict(zip(grid, v)) for v in itertools.product(*grid.values())]
    out = ROOT / "results" / "news_lab"
    out.mkdir(parents=True, exist_ok=True)
    parts, n = [], 0
    with ProcessPoolExecutor(4) as ex:
        for i, r in enumerate(ex.map(job, jobs, chunksize=4)):
            if len(r):
                parts.append(r)
                n += len(r)
            if i % 100 == 0:
                print(f"{i}/{len(jobs)} rows={n}", flush=True)
    df = pd.concat(parts, ignore_index=True)
    for col in ("family", "filt", "scope", "pick"):
        df[col] = df[col].astype("category")
    f = out / ("grid_surprise.parquet" if surprise else "grid.parquet")
    df.to_parquet(f, index=False)
    print(len(df), "rows ->", f)


if __name__ == "__main__":
    main()
