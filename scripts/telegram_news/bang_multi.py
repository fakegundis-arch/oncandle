"""Gold direct order on FinancialJuice ❗ headlines with MULTIPLE open positions (Nov 7 2026, the user's request:
"open multiple positions whenever the emoji comes, don't stop").  Fixed before running; both periods reported.

  * Every trigger opens its own trade even while others are open (no one-position-at-a-time rule).
  * Trade: follow gold's mid move over the 30 s before the bot reads the post (MOM L=30, k=0; no move -> no trade),
    market order (+1 spread), stop $10, target 2R ($20); exit variants: "30min" (also closed 30 min after the fill) and
    "tpsl" (stop or target only); always closed before the daily break / weekend.  Stress: 5 s late, +2 spreads.
  * Trigger sets: "first_of_story" = bang_lab.triggers (first ❗ post of a story, outside calendar windows - as
    before); "every" = every ❗ post without $MACRO (repeats of a story and posts near calendar events included).
  * Money: each trade risks 10 % (and 2 % / 1 %) of the account BALANCE at its entry (closed P&L only); P&L is booked
    at its exit; trades are processed in time order.  Reported: trades, R, PF, final balance, the worst drop of the
    balance, the most trades open at once and the most of the balance at risk at once.
usage: python3 -I scripts/telegram_news/bang_multi.py"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bang_lab as B  # noqa: E402
import newsbot_lab as N  # noqa: E402

DIR = B.DIRS.index(dict(fam="MOM", L=30, k=0.0))
EXITS = {"30min": 1800, "tpsl": None}


def every_trigger(a, b):
    p = N.load_posts(a, b)
    p = p[(p.ch == "FJ") & p.text.str.contains("❗", regex=False) & ~p.text.str.contains("$MACRO", regex=False)].copy()
    p["in_cal"] = False
    p["topics"] = p.clean.map(N.topics_of)
    p["lex_gold"], p["lex_nasdaq"] = zip(*p.clean.map(N.lex_dir))
    return p.reset_index(drop=True)


def trades(f, H, stress=False):
    tk = N.ticks("gold")
    c = dict(dir=DIR, stop_abs=10, r=2, H=H, topics="ANY", cal="excl")
    rows = []
    for x in f.itertuples():
        if x.in_cal:
            continue
        res = B.direct(tk, x, c, stress)
        if res is not None:
            ft, xt, r, d = res
            rows.append(dict(entry=ft, exit=xt, r=r, dir=d))
    return pd.DataFrame(rows, columns=["entry", "exit", "r", "dir"])


def account(t, risk):
    """balance with overlapping trades: risk x balance at entry, P&L at exit."""
    ev = sorted([(e, 1, i) for i, e in enumerate(t.entry)] + [(x, 0, i) for i, x in enumerate(t.exit)])
    bal, peak, worst, stake, open_ = 1000.0, 1000.0, 0.0, {}, set()
    max_open, max_risk = 0, 0.0
    for tm, kind, i in ev:                      # exits (0) before entries (1) in the same second
        if kind == 1:
            stake[i] = risk * max(bal, 0.0)
            open_.add(i)
            max_open = max(max_open, len(open_))
            max_risk = max(max_risk, sum(stake[j] for j in open_) / max(bal, 1e-9))
        else:
            bal += stake[i] * t.r.iat[i]
            open_.discard(i)
            peak = max(peak, bal)
            worst = min(worst, bal / peak - 1)
    return bal, worst, max_open, max_risk


def summary(t, a, b):
    x = t[(t.entry >= pd.Timestamp(a).timestamp()) & (t.entry < pd.Timestamp(b).timestamp())].reset_index(drop=True)
    r = x.r.to_numpy()
    out = dict(n=len(r), R=float(r.sum()), pf=float(r[r > 0].sum() / -r[r < 0].sum()) if (r < 0).any() else 99.0,
               win=float((r > 0).mean()) if len(r) else 0.0)
    for risk in (0.10, 0.02, 0.01):
        bal, dd, mo, mr = account(x, risk)
        out[f"{int(risk * 100)}%"] = dict(balance=bal, worst_drop=dd, max_open=mo, max_at_risk=mr)
    m = pd.to_datetime(x.entry, unit="s").dt.strftime("%Y-%m")
    out["by_month"] = x.groupby(m).r.sum().round(1).to_dict()
    return out


def main():
    sets = {"first_of_story": B.triggers("2026-01-01", B.TEST[1]), "every": every_trigger("2026-01-01", B.TEST[1])}
    res = {}
    for sname, tr in sets.items():
        f = B.features(tr, "gold")
        for ename, H in EXITS.items():
            t, ts = trades(f, H), trades(f, H, stress=True)
            key = f"{sname}|{ename}"
            res[key] = {per: dict(summary(t, a, b), stress=summary(ts, a, b)) for per, (a, b) in
                        (("jan_jun", B.BUILD), ("jul_oct", B.TEST))}
            for per in ("jan_jun", "jul_oct"):
                s = res[key][per]
                m10 = s["10%"]
                print(f"{key:22s} {per}: trades {s['n']:4d} R {s['R']:+7.1f} PF {s['pf']:.2f} win {s['win']:.0%} | 10%: "
                      f"${max(m10['balance'], 0):,.0f} worst drop {m10['worst_drop']:.0%} most open {m10['max_open']} "
                      f"most at risk {m10['max_at_risk']:.0%} | 2%: ${s['2%']['balance']:,.0f} ({s['2%']['worst_drop']:.0%}) "
                      f"1%: ${s['1%']['balance']:,.0f} ({s['1%']['worst_drop']:.0%}) | stress R {s['stress']['R']:+.1f} "
                      f"PF {s['stress']['pf']:.2f}")
                print(f"{'':22s}   by month {s['by_month']}")
    (N.OUT / "bang_multi_results.json").write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
