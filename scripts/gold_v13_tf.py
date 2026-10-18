"""Gold Asian breakout v13, attempt 3: a third engine = v10 rules on 30-minute or 1-hour bars, trading alongside v12
(Asia 12% + New York 4%), same rules every month. Chosen on 2026 only: >= 9/10 months up, drawdown >= -45%, above v12
($414,516), half the neighbours passing, then the highest 2026 total.
    python scripts/gold_v13_tf.py [--reveal]   -> results/gold/v13_tf.csv"""
import itertools
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
from gold_v12 import book, stream  # noqa: E402
from gold_v11_check import ASIA, NY  # noqa: E402

GRID = dict(tf=[30, 60], ses=["00-06", "00-08", "12-15", "12-16"], don=[10, 20], ema_mode=["bars", "hours"],
            rr=[3.0, 4.0], w=[0.03, 0.05])
V12_2026 = 414_516


def bars(m1, minutes):
    return m1.resample(f"{minutes}min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()


def main(reveal=False):
    m1, m15 = G.data(ROOT)
    base = pd.concat([stream(m1, m15, ASIA).assign(f=0.12), stream(m1, m15, NY).assign(f=0.04)])
    rows, cache = [], {}
    for v in itertools.product(*GRID.values()):
        kw = dict(zip(GRID, v))
        key = tuple(v[:-1])
        if key not in cache:
            s0, s1 = map(int, kw["ses"].split("-"))
            k = 15 / kw["tf"] if kw["ema_mode"] == "hours" else 1.0
            p = replace(ASIA, bar_min=kw["tf"], ses_start=s0, ses_end=s1, don=kw["don"], rr=kw["rr"],
                        ema=max(int(round(400 * k)), 20), slope=max(int(round(16 * k)), 2))
            cache[key] = stream(m1, bars(m1, kw["tf"]), p)
        t3 = cache[key]
        r = {**kw, "n26": int((t3.entry_time.dt.year == 2026).sum())}
        for k, (usd, dd, up, nm, worst) in book(pd.concat([base, t3.assign(f=kw["w"])])).items():
            r.update({f"{k}_usd": usd, f"{k}_dd": dd, f"{k}_up": up, f"{k}_worst": worst})
        rows.append(r)
    d = pd.DataFrame(rows)
    d["pass"] = (d.y26_up >= 9) & (d.y26_dd >= -0.45) & (d.y26_usd > V12_2026)
    look = d.set_index(list(GRID))["pass"].to_dict()
    share = []
    for _, r in d.iterrows():
        if not r["pass"]:
            share.append(0.0); continue
        hits = tot = 0
        for k, opts in GRID.items():
            p = opts.index(r[k])
            for q in (p - 1, p + 1):
                if 0 <= q < len(opts):
                    tot += 1; hits += bool(look.get(tuple(opts[q] if kk == k else r[kk] for kk in GRID), False))
        share.append(hits / tot)
    d["nb"] = share
    d.to_csv(ROOT / "results/gold/v13_tf.csv", index=False)
    c = d[d["pass"] & (d.nb >= 0.5)].sort_values("y26_usd", ascending=False)
    pd.set_option("display.width", 250)
    print(len(d), "setups |", int(d["pass"].sum()), "pass |", len(c), "with half the neighbours")
    print(c[list(GRID) + ["n26", "y26_usd", "y26_dd", "y26_up", "y26_worst", "nb"]].head(12).round(2).to_string())
    if reveal and len(c):
        p = c.iloc[0]
        print("\nPICK", {k: p[k] for k in GRID})
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${p[f'{k}_usd']:,.0f} DD {p[f'{k}_dd']:.0%} months up {p[f'{k}_up']} worst {p[f'{k}_worst']:+.0%}")
    return d


if __name__ == "__main__":
    main("--reveal" in sys.argv)
