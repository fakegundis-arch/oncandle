#!/usr/bin/env python3
"""Backtest trading Trump's Truth Social posts (backtester/truth.py) on 11 markets.

    python scripts/fetch_truth_posts.py && python scripts/run_truth.py      # -> results/truth/grid.parquet

The bot reacts `delay` minutes after the minute of the post (delay 1 = the next full minute).
Families: straddle (OCO stops), cont (follow the first move after w min), fade, tone (risk-on/off words).
2025 = discovery, 2026 = validation; $ at 10% risk; spreads x3.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import data as D, indicators as ind, news_lab as L, speech as S, truth as T  # noqa: E402

MARKETS = list(T.RISK_ON_DIR)
TOPICS = ("all",) + tuple(T.TOPICS)
COST_X = 3.0
YEARS = {"y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2027-01-01")}
STRADDLE = dict(k=(1.0, 2.0, 3.0, 5.0), s=(0.5, 1.0, 2.0), rr=(1.0, 2.0, 3.0), be=(0.0, 1.0), expiry=(5, 30, 120),
                hold=(60, 240))
DIRECTIONAL = dict(family=("cont", "fade", "tone"), w=(1, 5, 15, 30), k=(0.0, 2.0, 5.0), stop=(3.0, 6.0, 12.0),
                   rr=(1.0, 2.0, 3.0), be=(0.0, 1.0), max_bars=(60, 240, 1440))
FAM = {"cont": 0, "fade": 1, "tone": 2}


def stats(t, r):
    out = {}
    ok = np.isfinite(r)
    t, r = t[ok], r[ok]
    for k, (a, b) in YEARS.items():
        x = r[(t >= np.datetime64(a)) & (t < np.datetime64(b))]
        out[f"{k}_n"] = len(x)
        if len(x) == 0:
            continue
        loss = -x[x < 0].sum()
        eq = 1000 * np.cumprod(np.maximum(1 + 0.10 * x, 0))
        out.update({f"{k}_win": (x > 0).mean(), f"{k}_avg": x.mean(), f"{k}_pf": x[x > 0].sum() / loss if loss > 0 else 99,
                    f"{k}_usd": eq[-1], f"{k}_dd": (eq / np.maximum.accumulate(eq) - 1).min()})
    return out


def main():
    posts = pd.read_csv(ROOT / "data" / "truth" / "posts.csv")
    posts["time_utc"] = pd.to_datetime(posts.time_utc, format="mixed")
    ev = T.events(T.classify(posts[posts.time_utc >= "2024-10-01"]))
    out = ROOT / "results" / "truth"
    out.mkdir(parents=True, exist_ok=True)
    ev.to_csv(out / "events.csv", index=False)
    print(ev.groupby([ev.time_utc.dt.year, "topic"]).size().unstack().fillna(0).astype(int), flush=True)
    rows = []
    for delay in (1, 2, 5):
        per = {}
        for m in MARKETS:
            m1 = D.load_csv(ROOT / "data" / f"{m}_M1.csv").drop(columns="spread", errors="ignore")
            tr = ind.true_range(m1).rolling(240).mean().shift().to_numpy()
            t_act = ev.time_utc.dt.floor("1min") + pd.Timedelta(minutes=delay)
            i = m1.index.searchsorted(t_act)
            ok = (i >= 240) & (i < len(m1) - 1500)
            ok[ok] &= (m1.index[i[ok]] - t_act[ok].to_numpy()) <= pd.Timedelta("2min")   # market open at that time
            e = ev[ok].reset_index(drop=True)
            i0 = i[ok].astype(np.int64)
            arr = tuple(m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
            per[m] = (e, i0, tr[i0], arr, (e.tone.to_numpy() * T.RISK_ON_DIR[m]).astype(np.int64))
        cost = {m: COST_X * D.EXNESS_STANDARD_SPREAD[m] for m in MARKETS}

        def add(kw, m, e, R):
            for tp in TOPICS:
                sel = np.ones(len(e), bool) if tp == "all" else (e.topic == tp).to_numpy()
                rows.append({"delay": delay, **kw, "topic": tp, "pick": m, **stats(e.time_utc.to_numpy()[sel], R[sel])})

        for v in itertools.product(*STRADDLE.values()):
            kw = {"family": "straddle", **dict(zip(STRADDLE, v))}
            for m, (e, i0, a, (o, h, l, c), _) in per.items():
                R, _ = S.straddle(o, h, l, c, i0, a, kw["k"], kw["s"], kw["rr"], kw["be"], kw["expiry"], kw["hold"], cost[m])
                add(kw, m, e, R)
        for fam, w, k in itertools.product(DIRECTIONAL["family"], DIRECTIONAL["w"], DIRECTIONAL["k"]):
            sig = {}
            for m, (e, i0, a, (o, h, l, c), nd) in per.items():
                if fam == "tone" and T.RISK_ON_DIR[m] == 0:
                    continue
                ent, dr, spk = L.signals(o, h, l, c, i0, a, nd, FAM[fam], w, k, 0, 30)
                sig[m] = (ent, dr, a)
            for st, rr, be, mb in itertools.product(DIRECTIONAL["stop"], DIRECTIONAL["rr"], DIRECTIONAL["be"],
                                                    DIRECTIONAL["max_bars"]):
                kw = {"family": fam, "w": w, "k": k, "s": st, "rr": rr, "be": be, "hold": mb}
                for m, (ent, dr, a) in sig.items():
                    e, _, _, (o, h, l, c), _ = per[m]
                    R, _ = L.simulate(o, h, l, c, ent, dr, st * a, rr, np.zeros(len(a)), be, mb,
                                      np.full(len(a), cost[m]))
                    add(kw, m, e, R)
        print("delay", delay, "rows", len(rows), flush=True)
    df = pd.DataFrame(rows)
    for col in df.select_dtypes("float64"):
        df[col] = df[col].astype("float32")
    df.to_parquet(out / "grid.parquet", index=False)
    print(len(df), "rows")


if __name__ == "__main__":
    main()
