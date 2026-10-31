"""Supply & demand v2: the pick (fixed on 2026 before 2025 is opened) and its one-time 2025 reveal.

Five explorer agents searched five S&D families on 2026 only (scripts/sd_v2_eval.py protocol); all five reported a
passing candidate and independent auditors re-implemented them. v2 = the confirmed candidate with the highest plateau
score: 'structure_trend' (7.93; others: premium_discount 6.82, rejection 5.99, zone_quality 5.89, mtf_refine 2.17).
    python scripts/sd_v2.py            -> 2026 scorecard of the pick
    python scripts/sd_v2.py --reveal   -> its 2025 and 15 Nov - 31 Dec 2024 results (once)
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import sd_v2_eval as E  # noqa: E402
import sd_v2_strategy as ST  # noqa: E402

PICK = ROOT / "results/sd/v2_pick.json"
SEALED = {"y25": ("2025-01-01", "2026-01-01"), "late24": ("2024-11-15", "2025-01-01")}


def period(trades, a, b, risk=E.RISK):
    t = trades[(trades.entry_time >= a) & (trades.entry_time < b)].sort_values("entry_time")
    r = t.r.to_numpy(float)
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    mon = t.assign(m=t.exit_time.dt.to_period("M"), g=np.log1p(risk * r)).groupby("m").agg(n=("r", "size"), R=("r", "sum"), g=("g", "sum"))
    return dict(n=len(r), R=float(r.sum()), pf=E._pf(r), win=float((r > 0).mean()) if len(r) else 0.0,
                usd=float(1000 * eq[-1]), dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()),
                months={str(k): dict(n=int(v.n), R=round(float(v.R), 1), ret=round(float(np.expm1(v.g)), 3)) for k, v in mon.iterrows()})


def run():
    t25, t40 = ST.make_trades(ST.BEST, 0.25), ST.make_trades(ST.BEST, 0.40)
    m25, m40 = E.evaluate(t25), E.evaluate(t40)
    print("PICK:", ST.BEST)
    print({k: v for k, v in m25.items() if k != "months"}); print("passes:", E.passes(m25, m40))
    return m25, m40


def reveal():
    pick = json.loads(PICK.read_text())
    assert pick["cfg"] == ST.BEST
    for cost in (0.25, 0.40):
        t = ST.make_trades(ST.BEST, cost)
        for k, (a, b) in SEALED.items():
            m = period(t, a, b)
            print(f"{k} at ${cost:.2f}: {m['n']} trades, {m['R']:+.1f}R, PF {m['pf']:.2f}, win {m['win']:.0%} | "
                  f"$1,000 at 10% -> ${m['usd']:,.0f}, max drawdown {m['dd']:.1%}")
            if cost == 0.25 and k == "y25":
                for mo, v in m["months"].items():
                    print(f"   {mo}: {v['n']} trades, {v['R']:+.1f}R, {v['ret']:+.0%}")


if __name__ == "__main__":
    reveal() if "--reveal" in sys.argv else run()
