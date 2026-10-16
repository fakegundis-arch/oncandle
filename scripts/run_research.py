#!/usr/bin/env python3
"""Backtest every strategy x parameter set x pair x timeframe, then rank the
strategies by walk-forward out-of-sample performance.

    python scripts/run_research.py                     # all CSVs in data/
    python scripts/run_research.py --timeframes H4 D1 --folds 5

Method
------
1. Full-sample backtest of every combination at 0.5 % risk per trade, with
   realistic per-pair costs (backtester/data.py: DEFAULT_COST_PIPS).
2. Portfolio = sum of the per-pair daily returns (equal risk on every pair).
3. Anchored walk-forward: the time span is cut into folds+1 equal chunks.
   For each fold the parameter set with the best in-sample portfolio Sharpe
   (all data *before* the fold) is chosen and traded on the fold, unseen.
   The stitched out-of-sample folds are the headline result: they show what
   you would have earned picking parameters with only the past available.
4. Robustness: share of all parameter sets (full sample) that make money,
   and share of pairs that are profitable out-of-sample.
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtester import data as D  # noqa: E402
from backtester import indicators as ind  # noqa: E402
from backtester.engine import backtest  # noqa: E402
from backtester.metrics import daily_returns, summarize  # noqa: E402
from backtester.strategies import STRATEGIES  # noqa: E402

RISK = 0.005
MIN_BARS = {"H1": 2000, "H4": 1500, "D1": 750}


def load_universe(data_dir: Path) -> dict[str, pd.DataFrame]:
    out = {}
    for p in sorted(data_dir.glob("*.csv")):
        sym = p.stem.split("_")[0].upper()
        out[sym] = D.load_csv(p)
    return out


def run_strategy(args):
    """Worker: all combos of one strategy on one timeframe."""
    name, tf, universe = args
    fn, sig_grid, risk_grid = STRATEGIES[name]
    combos = []
    for sp in sig_grid:
        sigs = {sym: fn(df, **sp) for sym, df in universe.items()}
        for rp in risk_grid:
            pair_rets, pair_trades = {}, {}
            for sym, df in universe.items():
                cost = D.cost_pips(sym) * D.pip_size(sym)
                res = backtest(df, sigs[sym], ind.atr(df, 14), cost, risk=RISK, **rp)
                pair_rets[sym] = daily_returns(res.equity)
                pair_trades[sym] = res.trades
            combos.append({"params": {**sp, **rp},
                           "rets": pd.DataFrame(pair_rets).fillna(0.0),
                           "trades": pair_trades})
    return name, tf, combos


def sharpe(r: pd.Series) -> float:
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(260)) if sd > 0 and len(r) > 20 else -np.inf


def trades_between(trades: dict, a, b) -> np.ndarray:
    rs = [t.loc[(t.exit_time >= a) & (t.exit_time < b), "r"].to_numpy() for t in trades.values()]
    return np.concatenate(rs) if rs else np.array([])


def walk_forward(combos, folds: int):
    idx = combos[0]["rets"].index
    edges = pd.date_range(idx[0], idx[-1], periods=folds + 2)
    oos_rets, oos_r, chosen, pair_oos = [], [], [], []
    for j in range(1, folds + 1):
        is_a, is_b, oos_b = edges[0], edges[j], edges[j + 1]
        best = max(combos, key=lambda c: sharpe(c["rets"].loc[is_a:is_b].sum(axis=1)))
        seg = best["rets"].loc[(best["rets"].index > is_b) & (best["rets"].index <= oos_b)]
        oos_rets.append(seg.sum(axis=1))
        pair_oos.append(seg)
        oos_r.append(trades_between(best["trades"], is_b, oos_b))
        chosen.append(best["params"])
    rets = pd.concat(oos_rets)
    pair = pd.concat(pair_oos)
    return rets, np.concatenate(oos_r), chosen, pair


def evaluate(name, tf, combos, folds):
    full = []
    for c in combos:
        port = c["rets"].sum(axis=1)
        r = np.concatenate([t["r"].to_numpy() for t in c["trades"].values()])
        full.append({**summarize(port, r), "params": c["params"]})
    full_df = pd.DataFrame(full)
    wf_rets, wf_r, chosen, pair_oos = walk_forward(combos, folds)
    wf = summarize(wf_rets, wf_r)
    pair_pos = float(((1 + pair_oos).prod() > 1).mean())
    best_full = full_df.sort_values("sharpe", ascending=False).iloc[0]
    row = {
        "strategy": name, "timeframe": tf,
        **{f"oos_{k}": v for k, v in wf.items()},
        "oos_pairs_profitable": pair_pos,
        "combos": len(combos),
        "combos_profitable": float((full_df.total_return > 0).mean()),
        "median_combo_sharpe": float(full_df.sharpe.median()),
        "best_full_sharpe": float(best_full.sharpe),
        "best_full_params": json.dumps(best_full.params),
        "wf_params": json.dumps(chosen),
    }
    return row, wf_rets, full_df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--timeframes", nargs="+", default=["H1", "H4", "D1"])
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--strategies", nargs="*", default=list(STRATEGIES))
    ap.add_argument("--out", default=str(ROOT / "results"))
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    (out / "all_combos.csv").unlink(missing_ok=True)
    raw = load_universe(Path(a.data))
    if not raw:
        sys.exit("no CSV files in data/ - run scripts/fetch_dukascopy.py first")
    print("Universe:", ", ".join(f"{s} ({d.index[0]:%Y-%m}..{d.index[-1]:%Y-%m})" for s, d in raw.items()))

    jobs = []
    for tf in a.timeframes:
        uni = {s: D.resample(d, tf) for s, d in raw.items()}
        uni = {s: d for s, d in uni.items() if len(d) >= MIN_BARS[tf]}
        if not uni:
            print(f"skip {tf}: not enough bars")
            continue
        jobs += [(n, tf, uni) for n in a.strategies]

    rows, curves = [], {}
    with ProcessPoolExecutor(a.workers) as ex:
        for name, tf, combos in ex.map(run_strategy, jobs):
            row, wf_rets, full_df = evaluate(name, tf, combos, a.folds)
            rows.append(row)
            curves[f"{name} | {tf}"] = wf_rets
            full_df.assign(strategy=name, timeframe=tf).to_csv(
                out / "all_combos.csv", mode="a", index=False,
                header=not (out / "all_combos.csv").exists())
            print(f"{name:20s} {tf}  OOS sharpe {row['oos_sharpe']:6.2f}  CAGR {row['oos_cagr']:7.1%}  "
                  f"maxDD {row['oos_max_dd']:7.1%}  PF {row['oos_profit_factor']:5.2f}  "
                  f"trades {row['oos_trades']:5d}  robust {row['combos_profitable']:.0%}")

    res = pd.DataFrame(rows).sort_values("oos_sharpe", ascending=False)
    res.to_csv(out / "ranking.csv", index=False)
    pd.DataFrame(curves).fillna(0.0).add(1).cumprod().to_csv(out / "oos_equity.csv")
    print(f"\nwrote {out / 'ranking.csv'}")


if __name__ == "__main__":
    main()
