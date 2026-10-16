#!/usr/bin/env python3
"""Backtest the Trend Rider M1 strategy on BTC, gold, Nasdaq and Dow.

    python scripts/run_trend_rider.py                      # every data/*_M1.csv
    python scripts/run_trend_rider.py --risk 0.01 --out results/trend_rider

Data: export M1 bars from MT5 (View > Symbols > Bars > M1 > Export) as
data/BTCUSD_M1.csv, data/XAUUSD_M1.csv, data/NAS100_M1.csv, data/US30_M1.csv
(broker names like USTEC, US100, DJ30, GOLD are recognised).  MT5 exports
include the real per-bar spread, which the backtest charges.

Besides the rules as specified, a few one-change variants are run to show
whether each rule actually earns its keep (break-even on/off, consolidation
filter on/off, 1:2 vs 1:3, ...).  The last 30% of each history is also
reported separately as an unseen hold-out period.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtester import data as D  # noqa: E402
from backtester import trend_rider as tr  # noqa: E402
from backtester.metrics import daily_returns, summarize  # noqa: E402

BASE = tr.Params()
VARIANTS = {
    "As specified (1:3, BE at 1R)": BASE,
    "No break-even": replace(BASE, be_trigger=0.0),
    "BE at 1.5R": replace(BASE, be_trigger=1.5),
    "1:2 R:R, BE at 1R": replace(BASE, rr=2.0),
    "No consolidation filter": replace(BASE, adx_min=0.0, chop_max=100.0),
    "Stricter filter (ADX>30, CHOP<45)": replace(BASE, adx_min=30.0, chop_max=45.0),
    "US session only (13-20 UTC)": replace(BASE, session_utc=(13, 20)),
}


def load(data_dir: Path, pattern: str):
    out = {}
    for p in sorted(data_dir.glob(pattern)):
        sym = D.normalise_symbol(p.stem.split("_")[0])
        out[sym] = D.load_csv(p)
    return out


def stats(trades: pd.DataFrame, equity: pd.Series) -> dict:
    s = summarize(daily_returns(equity), trades.r.to_numpy())
    days = max((equity.index[-1] - equity.index[0]).days, 1)
    s.update({
        "trades_per_day": len(trades) / days,
        "target_pct": (trades.exit == "target").mean() if len(trades) else np.nan,
        "breakeven_pct": (trades.exit == "breakeven").mean() if len(trades) else np.nan,
        "stop_pct": (trades.exit == "stop").mean() if len(trades) else np.nan,
        "total_r": trades.r.sum(),
    })
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--pattern", default="*_M1.csv")
    ap.add_argument("--risk", type=float, default=0.005, help="fraction of equity risked per trade")
    ap.add_argument("--holdout", type=float, default=0.3)
    ap.add_argument("--costs", choices=["data", "typical"], default="data",
                    help="data: charge max(per-bar spread in the file, typical cost); "
                         "typical: ignore the file's spread, use backtester/data.py defaults")
    ap.add_argument("--out", default=str(ROOT / "results" / "trend_rider"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    uni = load(Path(a.data), a.pattern)
    if a.costs == "typical":
        uni = {k: v.drop(columns="spread", errors="ignore") for k, v in uni.items()}
    if not uni:
        sys.exit(f"no {a.pattern} files in {a.data} - export M1 bars from MT5 first (see docstring)")
    for s, d in uni.items():
        sp = f", median spread {d['spread'].median():g}" if "spread" in d else ""
        print(f"{s}: {len(d):,} bars {d.index[0]:%Y-%m-%d} -> {d.index[-1]:%Y-%m-%d}{sp}")

    rows, curves, base_trades = [], {}, {}
    for vname, p in VARIANTS.items():
        port = []
        all_tr = []
        for sym, df in uni.items():
            cost = D.DEFAULT_COST_PRICE.get(sym, D.cost_pips(sym) * D.pip_size(sym))
            res = tr.backtest(df, p, cost, risk=a.risk)
            t = res.trades.assign(symbol=sym)
            all_tr.append(t)
            port.append(daily_returns(res.equity).rename(sym))
            cut = df.index[int(len(df) * (1 - a.holdout))]
            ho_t = t[t.entry_time >= cut]
            ho_eq = res.equity[res.equity.index >= cut]
            for period, tt, ee in (("full", t, res.equity), ("holdout", ho_t, ho_eq / ho_eq.iloc[0])):
                rows.append({"variant": vname, "symbol": sym, "period": period, **stats(tt, ee)})
            if vname == next(iter(VARIANTS)):
                curves[sym] = res.equity
        pr = pd.concat(port, axis=1).fillna(0.0).sum(axis=1)
        trades = pd.concat(all_tr)
        eq = (1 + pr).cumprod()
        rows.append({"variant": vname, "symbol": "PORTFOLIO", "period": "full", **stats(trades, eq)})
        if vname == next(iter(VARIANTS)):
            curves["PORTFOLIO"] = eq
            base_trades = trades

    res = pd.DataFrame(rows)
    res.to_csv(out / "results.csv", index=False)
    base_trades.to_csv(out / "trades_as_specified.csv", index=False)

    # monthly returns of the portfolio, rules as specified
    pe = curves["PORTFOLIO"]
    monthly = pe.resample("ME").last().pct_change().fillna(pe.resample("ME").last().iloc[0] - 1)

    fig, ax = plt.subplots(figsize=(10, 5))
    for k, e in curves.items():
        e = e.resample("1h").last().dropna() if k != "PORTFOLIO" else e
        ax.plot(e.index, (e - 1) * 100, label=k, linewidth=2.2 if k == "PORTFOLIO" else 1.1)
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.set_ylabel(f"Return, % (risk {a.risk:.1%} per trade)")
    ax.set_title("Trend Rider M1 - rules as specified")
    ax.legend(frameon=False)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(out / "equity.png", dpi=120)

    def fmt(d, cols):
        t = d[cols].copy()
        for c in t.columns:
            if c in ("total_return", "cagr", "max_dd", "win_rate", "target_pct", "breakeven_pct", "stop_pct"):
                t[c] = (t[c] * 100).map("{:.1f}%".format)
            elif t[c].dtype.kind == "f":
                t[c] = t[c].map("{:.2f}".format)
        return t.to_markdown(index=False)

    cols = ["symbol", "trades", "trades_per_day", "target_pct", "breakeven_pct", "stop_pct", "avg_r",
            "profit_factor", "total_r", "total_return", "max_dd", "sharpe"]
    spec = res[(res.variant == next(iter(VARIANTS)))]
    var = res[(res.symbol == "PORTFOLIO")]
    md = ["# Trend Rider (M1) - backtest", "",
          f"Risk {a.risk:.1%} of equity per trade, all markets traded together. Costs: per-bar MT5 spread "
          "where available, otherwise the defaults in `backtester/data.py`.", "",
          "## Rules as specified - full history", "", fmt(spec[spec.period != "holdout"], cols), "",
          f"## Rules as specified - hold-out (last {a.holdout:.0%} of each market)", "",
          fmt(spec[spec.period == "holdout"], cols), "",
          "## Does each rule help? (portfolio, full history)", "",
          fmt(var, ["variant"] + cols[1:]), "",
          "## Monthly portfolio returns", "",
          monthly.map("{:.1%}".format).to_frame("return").to_markdown(), "",
          "![equity](equity.png)", ""]
    (out / "REPORT.md").write_text("\n".join(md))
    print(fmt(spec, ["period"] + cols))
    print()
    print(fmt(var, ["variant"] + cols[1:]))
    print(f"\nwrote {out / 'REPORT.md'}")


if __name__ == "__main__":
    main()
