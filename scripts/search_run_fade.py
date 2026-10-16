#!/usr/bin/env python3
"""Round 2: fine grid around the 'fade the candle run' family."""
from __future__ import annotations

import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import data as D, hwr  # noqa: E402
from search_high_winrate import load, stats  # noqa: E402

PERIODS = {"q4_2024": ("2024-10-01", "2025-01-01"), "2025": ("2025-01-01", "2026-01-01"),
           "2026": ("2026-01-01", "2027-01-01")}
GRID = [dict(run_len=r, min_move_atr=m, tp_atr=tp, sl_atr=s, max_bars=mb)
        for r, m, tp, s, mb in itertools.product((3, 4, 5, 6), (1.5, 2.0, 2.5, 3.0, 3.5),
                                                  (0.3, 0.5, 0.75, 1.0), (2.0, 3.0, 4.0), (10, 30))]


def job(args):
    sym, tf = args
    df = load(sym, tf)
    cost = D.EXNESS_STANDARD_SPREAD[sym]
    rows = []
    for p in GRID:
        t = hwr.run(df, hwr.run_fade(df, **p), cost)
        row = {"market": sym, "tf": tf, **p}
        for k, (a, b) in PERIODS.items():
            row.update({f"{k}_{m}": v for m, v in stats(t[(t.entry_time >= a) & (t.entry_time < b)]).items()})
        rows.append(row)
    return rows


if __name__ == "__main__":
    jobs = [(m, tf) for m in ("BTCUSD", "XAUUSD", "US30", "NAS100") for tf in ("30min", "1h", "2h", "4h")]
    out = []
    with ProcessPoolExecutor(4) as ex:
        for r in ex.map(job, jobs):
            out += r
            print("done", r[0]["market"], r[0]["tf"], flush=True)
    pd.DataFrame(out).to_csv(ROOT / "results" / "high_winrate" / "run_fade_grid.csv", index=False)
