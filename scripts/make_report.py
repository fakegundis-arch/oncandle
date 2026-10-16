#!/usr/bin/env python3
"""Turn results/<run>/ranking.csv + oos_equity.csv into REPORT.md and a chart.

    python scripts/make_report.py results/<run>
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

MIN_TRADES = 30


def score(df: pd.DataFrame) -> pd.Series:
    """Composite: 50% walk-forward OOS Sharpe, 25% OOS MAR (CAGR/MaxDD),
    25% robustness (share of parameter sets that are profitable).  Each
    component is rank-normalised so no single metric dominates."""
    r = lambda s: s.rank(pct=True)
    return 0.5 * r(df.oos_sharpe) + 0.25 * r(df.oos_mar.fillna(0)) + 0.25 * r(df.combos_profitable)


def main(run: Path):
    df = pd.read_csv(run / "ranking.csv")
    df["score"] = score(df)
    df["reliable"] = df.oos_trades >= MIN_TRADES
    df = df.sort_values(["reliable", "score"], ascending=False).reset_index(drop=True)
    df.index += 1
    df.to_csv(run / "ranking_scored.csv", index_label="rank")

    # Best timeframe per strategy -> overall strategy ranking.
    best = df.groupby("strategy", sort=False).head(1).reset_index(drop=True)
    best.index += 1

    eq = pd.read_csv(run / "oos_equity.csv", index_col=0, parse_dates=True)
    top = [f"{s} | {t}" for s, t in zip(best.strategy.head(5), best.timeframe.head(5))]
    fig, ax = plt.subplots(figsize=(10, 5))
    for k in top:
        ax.plot(eq.index, (eq[k] - 1) * 100, label=k, linewidth=1.4)
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.set_ylabel("Walk-forward out-of-sample return, %")
    ax.set_title("Top 5 strategies - stitched out-of-sample equity")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(run / "top5_oos_equity.png", dpi=120)

    def table(d):
        cols = ["strategy", "timeframe", "score", "oos_sharpe", "oos_cagr", "oos_max_dd", "oos_mar",
                "oos_profit_factor", "oos_win_rate", "oos_trades", "combos_profitable", "oos_pairs_profitable"]
        t = d[cols].copy()
        for c in ["oos_cagr", "oos_max_dd", "oos_win_rate", "combos_profitable", "oos_pairs_profitable"]:
            t[c] = (t[c] * 100).map("{:.1f}%".format)
        for c in ["score", "oos_sharpe", "oos_mar", "oos_profit_factor"]:
            t[c] = t[c].map("{:.2f}".format)
        t.columns = ["Strategy", "TF", "Score", "Sharpe", "CAGR", "Max DD", "MAR", "PF", "Win %",
                     "Trades", "Param sets profitable", "Pairs profitable"]
        return t.to_markdown()

    w = best.iloc[0]
    md = [f"# Trend-following backtest report - `{run.name}`", "",
          "All numbers are **walk-forward out-of-sample**: parameters were picked using only data that came "
          "before each test period. Risk is 0.5% of equity per trade per pair, with costs included.", "",
          f"**Winner: {w.strategy} on {w.timeframe}**, with OOS Sharpe {w.oos_sharpe:.2f}, CAGR {w.oos_cagr:.1%}, "
          f"max drawdown {w.oos_max_dd:.1%} and profit factor {w.oos_profit_factor:.2f} over {int(w.oos_trades)} trades.",
          f"Parameters the walk-forward chose in each fold: `{w.wf_params}`", "",
          "## Strategy ranking (best timeframe for each)", "", table(best), "",
          f"Rows with fewer than {MIN_TRADES} OOS trades are ranked last because they are not statistically meaningful.", "",
          "![equity](top5_oos_equity.png)", "",
          "## Every strategy and timeframe", "", table(df), ""]
    (run / "REPORT.md").write_text("\n".join(md))
    print(f"wrote {run / 'REPORT.md'}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
