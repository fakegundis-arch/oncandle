#!/usr/bin/env python3
"""Backtest Candle Run (strategy 3) on BTCUSD M1.

    python scripts/run_candle_run.py --out results/candle_run

Reports the rules as specified plus one-change variants, for the full
history and the current calendar year, with zero cost and with estimated
Exness Standard spreads.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from backtester import candle_run as cr  # noqa: E402
from backtester import data as D  # noqa: E402
from backtester import trend_rider as tr  # noqa: E402
from run_confluence import fmt, stats  # noqa: E402

BASE = cr.Params()
VARIANTS = {
    "As specified (4 candles, >=1.5 ATR move, 1:3, BE at 1R)": BASE,
    "5 candles in a row": replace(BASE, run_len=5),
    "6 candles in a row": replace(BASE, run_len=6),
    "No 'clearly moving' filter": replace(BASE, min_move_atr=0.0),
    "Stronger move (>=2.5 ATR)": replace(BASE, min_move_atr=2.5),
    "Quicker break-even (at 0.5R)": replace(BASE, be_trigger=0.5),
    "1:2 target": replace(BASE, rr=2.0),
    "1:1.5 target": replace(BASE, rr=1.5),
    "Only with the EMA200 trend": replace(BASE, trend_ema=200),
    "Diagnostic: trade AGAINST the run": replace(BASE, fade=True),
}
COSTS = {"no costs": 0.0, "Exness spreads": D.EXNESS_STANDARD_SPREAD["BTCUSD"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data" / "BTCUSD_M1.csv"))
    ap.add_argument("--risk", type=float, default=0.005)
    ap.add_argument("--year", type=int, default=pd.Timestamp.now().year)
    ap.add_argument("--out", default=str(ROOT / "results" / "candle_run"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    df = D.load_csv(a.data).drop(columns="spread", errors="ignore")
    periods = {f"Full history ({df.index[0]:%b %Y} - {df.index[-1]:%b %Y})": df.index[0],
               f"{a.year} only": pd.Timestamp(f"{a.year}-01-01")}
    rows, spec_trades = [], []
    for vname, p in VARIANTS.items():
        sig = cr.signals(df, p)
        bracket = tr.Params(rr=p.rr, be_trigger=p.be_trigger, be_buffer=p.be_buffer)
        for cname, cost in COSTS.items():
            t = tr.backtest(df, bracket, cost, risk=a.risk, sig=sig).trades
            if vname == next(iter(VARIANTS)):
                spec_trades.append(t.assign(costs=cname))
            for pname, p0 in periods.items():
                rows.append({"period": pname, "costs": cname, "variant": vname,
                             **stats(t[t.entry_time >= p0], a.risk)})
        print("done:", vname)

    res = pd.DataFrame(rows)
    res.to_csv(out / "variants.csv", index=False)
    T = pd.concat(spec_trades)
    T.to_csv(out / "trades_as_specified.csv", index=False)

    md = ["# Candle Run (strategy 3) - BTCUSD M1 backtest", "",
          f"Risk {a.risk:.1%} per trade. Signal: N same-colour 1-minute candles in a row that moved "
          ">= 1.5x ATR together; enter in that direction at the next open.", ""]
    for pname in periods:
        for cname in COSTS:
            md += [f"## {pname} - {cname}", "",
                   fmt(res[(res.period == pname) & (res.costs == cname)].drop(columns=["period", "costs"])), ""]
    m = T[(T.costs == "Exness spreads") & (T.entry_time >= periods[list(periods)[1]])]
    if len(m):
        by_month = m.groupby(m.exit_time.dt.to_period("M")).r.agg(trades="count", total_r="sum")
        md += [f"## {a.year} by month - as specified, Exness spreads", "", by_month.round(1).to_markdown(), ""]
    (out / "REPORT.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
