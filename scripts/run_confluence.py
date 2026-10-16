#!/usr/bin/env python3
"""Backtest Confluence Rider (strategy 2) against Trend Rider (strategy 1).

    python scripts/run_confluence.py --out results/confluence

Reads data/*_M1.csv (BTCUSD, XAUUSD, NAS100, US30).  Reports, for the full
history and for the current calendar year:
  * every variant (markets that must agree, entry style) for the portfolio
  * per-market detail for the variant as specified (2+ agree, pullback entry)
under two cost scenarios: zero cost and estimated Exness Standard spreads.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backtester import confluence as cf  # noqa: E402
from backtester import data as D  # noqa: E402
from backtester import trend_rider as tr  # noqa: E402

VARIANTS = {
    "Strategy 1 (no confirmation)": cf.Params(min_agree=1),
    "2+ markets agree, pullback entry (as specified)": cf.Params(min_agree=2),
    "3+ markets agree, pullback entry": cf.Params(min_agree=3),
    "All 4 agree, pullback entry": cf.Params(min_agree=4),
    "2+ markets agree, enter when group lines up": cf.Params(min_agree=2, entry="onset"),
    "3+ markets agree, enter when group lines up": cf.Params(min_agree=3, entry="onset"),
}
SPEC = "2+ markets agree, pullback entry (as specified)"
COSTS = {"no costs": lambda s: 0.0, "Exness spreads": lambda s: D.EXNESS_STANDARD_SPREAD.get(s, 0.0)}


def stats(t: pd.DataFrame, risk: float) -> dict:
    if t.empty:
        return {"trades": 0}
    t = t.sort_values("exit_time")
    eq = np.cumprod(1 + risk * t.r.to_numpy())
    loss = -t.r[t.r < 0].sum()
    return {
        "trades": len(t),
        "hit_3R": (t.exit == "target").mean(),
        "breakeven": (t.exit == "breakeven").mean(),
        "stopped": (t.exit == "stop").mean(),
        "avg_r": t.r.mean(),
        "profit_factor": t.r[t.r > 0].sum() / loss if loss > 0 else np.nan,
        "total_r": t.r.sum(),
        "return": eq[-1] - 1,
        "max_dd": (eq / np.maximum.accumulate(eq) - 1).min(),
    }


def fmt(df: pd.DataFrame) -> str:
    d = df.copy()
    for c in ("hit_3R", "breakeven", "stopped", "return", "max_dd"):
        if c in d:
            d[c] = d[c].map(lambda v: f"{v:+.1%}" if c in ("return", "max_dd") else f"{v:.0%}")
    for c in ("avg_r", "profit_factor", "total_r"):
        if c in d:
            d[c] = d[c].map(lambda v: f"{v:+.3f}" if c == "avg_r" else f"{v:.2f}" if c == "profit_factor" else f"{v:+.0f}")
    return d.to_markdown(index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "data"))
    ap.add_argument("--risk", type=float, default=0.005)
    ap.add_argument("--year", type=int, default=pd.Timestamp.now().year)
    ap.add_argument("--out", default=str(ROOT / "results" / "confluence"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    uni = {}
    for p in sorted(Path(a.data).glob("*_M1.csv")):
        uni[D.normalise_symbol(p.stem.split("_")[0])] = D.load_csv(p).drop(columns="spread", errors="ignore")
    if len(uni) < 2:
        sys.exit("need M1 data for at least 2 markets in data/")
    start = min(d.index[0] for d in uni.values())
    end = max(d.index[-1] for d in uni.values())
    ytd = pd.Timestamp(f"{a.year}-01-01")
    print("Markets:", ", ".join(uni), f"| {start:%Y-%m-%d} -> {end:%Y-%m-%d}")

    periods = {f"Full history ({start:%b %Y} - {end:%b %Y})": start, f"{a.year} only": ytd}
    port_rows, mkt_rows, all_trades = [], [], []
    for vname, vp in VARIANTS.items():
        sigs = cf.signals(uni, vp)
        for cname, cost in COSTS.items():
            trades = []
            for sym, df in uni.items():
                t = tr.backtest(df, vp.base, cost(sym), risk=a.risk, sig=sigs[sym]).trades
                trades.append(t.assign(symbol=sym))
            T = pd.concat(trades)
            if vname == SPEC:
                all_trades.append(T.assign(costs=cname))
            for pname, p0 in periods.items():
                tt = T[T.entry_time >= p0]
                port_rows.append({"period": pname, "costs": cname, "variant": vname, **stats(tt, a.risk)})
                if vname == SPEC:
                    for sym in uni:
                        mkt_rows.append({"period": pname, "costs": cname, "market": sym,
                                         **stats(tt[tt.symbol == sym], a.risk)})
        print(f"done: {vname}")

    port = pd.DataFrame(port_rows)
    mkts = pd.DataFrame(mkt_rows)
    port.to_csv(out / "variants.csv", index=False)
    mkts.to_csv(out / "markets.csv", index=False)
    pd.concat(all_trades).to_csv(out / "trades_as_specified.csv", index=False)

    md = ["# Confluence Rider (strategy 2) - backtest", "",
          f"M1, {', '.join(uni)}. Risk {a.risk:.1%} per trade, 1:3 target, stop to entry +0.1R at 1R. "
          "A market is only traded when it AND enough other markets trend the same way.", ""]
    for pname in periods:
        for cname in COSTS:
            md += [f"## {pname} - {cname}", "",
                   "### All markets together, by variant", "",
                   fmt(port[(port.period == pname) & (port.costs == cname)].drop(columns=["period", "costs"])), "",
                   "### Per market, as specified (2+ agree, pullback entry)", "",
                   fmt(mkts[(mkts.period == pname) & (mkts.costs == cname)].drop(columns=["period", "costs"])), ""]
    (out / "REPORT.md").write_text("\n".join(md))
    print("\n".join(md))


if __name__ == "__main__":
    main()
