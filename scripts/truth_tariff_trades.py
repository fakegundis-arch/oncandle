#!/usr/bin/env python3
"""Trade list for the Truth Social tariff-tone setting picked on 2025 (Dow, US30).

    python scripts/truth_tariff_trades.py   # -> results/truth/tariff_us30_trades.csv
Rules: a Truth Social post mentioning tariffs (first in 60 min; endorsements excluded); tone = sign(#risk-on words -
#risk-off words) from backtester/truth.py (a plain tariff threat = risk-off = SELL the Dow, "deal / pause / exempt..." =
BUY).  The bot acts 2 min after the post's minute, waits 5 min, then enters in the tone direction at the next M1 open.
Stop 12 x the pre-post M1 average range, target 3R, stop to +0.1R at +1R, close after 60 min.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtester import data as D, indicators as ind, news_lab as L, truth as T  # noqa: E402

M, DELAY, W, S, RR, BE, HOLD = "US30", 2, 5, 12.0, 3.0, 1.0, 60


def main():
    posts = pd.read_csv(ROOT / "data" / "truth" / "posts.csv")
    posts["time_utc"] = pd.to_datetime(posts.time_utc, format="mixed")
    ev = T.events(T.classify(posts[posts.time_utc >= "2024-10-01"]))
    ev = ev[ev.topic == "tariff"].reset_index(drop=True)
    m1 = D.load_csv(ROOT / "data" / f"{M}_M1.csv").drop(columns="spread", errors="ignore")
    tr = ind.true_range(m1).rolling(240).mean().shift().to_numpy()
    t_act = ev.time_utc.dt.floor("1min") + pd.Timedelta(minutes=DELAY)
    i = m1.index.searchsorted(t_act)
    ok = (i >= 240) & (i < len(m1) - 1500)
    ok[ok] &= (m1.index[i[ok]] - t_act[ok].to_numpy()) <= pd.Timedelta("2min")
    e, i0 = ev[ok].reset_index(drop=True), i[ok].astype(np.int64)
    a = tr[i0]
    o, h, l, c = (m1[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    nd = (e.tone.to_numpy() * T.RISK_ON_DIR[M]).astype(np.int64)
    ent, dr, _ = L.signals(o, h, l, c, i0, a, nd, 2, W, 0.0, 0, 30)
    cost = 3 * D.EXNESS_STANDARD_SPREAD[M]
    R, X = L.simulate(o, h, l, c, ent, dr, S * a, RR, np.zeros(len(a)), BE, HOLD, np.full(len(a), cost))
    k = ent >= 0
    entry = np.where(dr == 1, o[np.maximum(ent, 0)] + cost, o[np.maximum(ent, 0)])
    t = pd.DataFrame({"post_utc": e.time_utc[k].to_numpy(), "post": e.content[k].str[:140].to_numpy(),
                      "side": np.where(dr[k] == 1, "BUY", "SELL"), "entry_utc": m1.index[ent[k]],
                      "entry": entry[k].round(1), "stop_pts": (S * a[k]).round(1), "exit_utc": m1.index[X[k]],
                      "r": R[k].round(2)})
    out = ROOT / "results" / "truth" / "tariff_us30_trades.csv"
    t.to_csv(out, index=False)
    for y in (2025, 2026):
        x = t[t.entry_utc.dt.year == y].r.to_numpy()
        for risk in (0.05, 0.10, 0.20, 0.30):
            eq = 1000 * np.cumprod(np.maximum(1 + risk * x, 0))
            print(f"{y} risk {risk:.0%}: {len(x)} trades, win {(x > 0).mean():.0%}, PF {x[x > 0].sum() / -x[x < 0].sum():.2f},"
                  f" $1000 -> ${eq[-1]:,.0f}, max DD {(eq / np.maximum.accumulate(eq) - 1).min():.0%}")
    print(t.side.value_counts().to_dict())
    print(out)


if __name__ == "__main__":
    main()
