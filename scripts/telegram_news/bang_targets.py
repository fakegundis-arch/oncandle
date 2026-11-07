"""Gold direct order on FinancialJuice ❗ headlines with 1R / 2R / 3R targets (Nov 7 2026, the user's request).
Fixed before running; both periods reported.  Trade: follow gold's 30-s move (MOM L=30 k=0), market order (+1 spread),
stop $10, target r x $10 for r in {1, 2, 3}; exits "30min" (also closed 30 min after the fill) or "tpsl" (stop / target
only); always closed before the daily break / weekend.
  * "every, multiple": every ❗ post without $MACRO opens its own trade, several can be open (bang_multi.py accounting:
    10 % of the balance at each entry, P&L at exit).
  * "first of story, one at a time": bang_lab triggers (first ❗ post of a story, outside calendar windows), one position
    at a time (bang_lab.run).
usage: python3 -I scripts/telegram_news/bang_targets.py"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bang_lab as B  # noqa: E402
import bang_multi as M  # noqa: E402
import newsbot_lab as N  # noqa: E402


def multi_trades(f, H, r, stress=False):
    tk = N.ticks("gold")
    c = dict(dir=M.DIR, stop_abs=10, r=r, H=H, topics="ANY", cal="excl")
    rows = []
    for x in f.itertuples():
        res = B.direct(tk, x, c, stress)
        if res is not None:
            ft, xt, rr, d = res
            rows.append(dict(entry=ft, exit=xt, r=rr, dir=d))
    return pd.DataFrame(rows, columns=["entry", "exit", "r", "dir"])


def main():
    f_every = B.features(M.every_trigger("2026-01-01", B.TEST[1]), "gold")
    f_first = B.features(B.triggers("2026-01-01", B.TEST[1]), "gold")
    res = {}
    for ename, H in M.EXITS.items():
        for r in (1, 2, 3):
            t, ts = multi_trades(f_every, H, r), multi_trades(f_every, H, r, stress=True)
            res[f"every_multiple|{ename}|{r}R"] = {per: dict(M.summary(t, a, b), stress=M.summary(ts, a, b))
                                                    for per, (a, b) in (("jan_jun", B.BUILD), ("jul_oct", B.TEST))}
            c = dict(dir=M.DIR, stop_abs=10, r=r, H=H, topics="ANY", cal="excl")
            t1, ts1 = B.run(f_first, "gold", "direct", c), B.run(f_first, "gold", "direct", c, stress=True)
            out = {}
            for per, (a, b) in (("jan_jun", B.BUILD), ("jul_oct", B.TEST)):
                m = N.metrics(t1, a, b)
                out[per] = dict(n=m["n"], R=m["R"], pf=m["pf"], win=m["win"], usd10=m["usd"], dd10=m["dd"],
                                usd2=N.metrics(t1, a, b, 0.02)["usd"], usd1=N.metrics(t1, a, b, 0.01)["usd"],
                                dd1=N.metrics(t1, a, b, 0.01)["dd"], streak=m["max_losing_streak"],
                                stress_R=N.metrics(ts1, a, b)["R"], stress_pf=N.metrics(ts1, a, b)["pf"])
            res[f"first_one_at_a_time|{ename}|{r}R"] = out
    (N.OUT / "bang_targets_results.json").write_text(json.dumps(res, indent=1, default=str))
    for k, v in res.items():
        for per in ("jan_jun", "jul_oct"):
            s = v[per]
            if k.startswith("every"):
                m10 = s["10%"]
                print(f"{k:34s} {per}: n {s['n']:4d} R {s['R']:+7.1f} PF {s['pf']:.2f} win {s['win']:.0%} | 10% ${max(m10['balance'], 0):,.0f} "
                      f"(drop {m10['worst_drop']:.0%}, most open {m10['max_open']}, most at risk {m10['max_at_risk']:.0%}) | "
                      f"2% ${s['2%']['balance']:,.0f} 1% ${s['1%']['balance']:,.0f} ({s['1%']['worst_drop']:.0%}) | stress R "
                      f"{s['stress']['R']:+.1f} PF {s['stress']['pf']:.2f}")
            else:
                print(f"{k:34s} {per}: n {s['n']:4d} R {s['R']:+7.1f} PF {s['pf']:.2f} win {s['win']:.0%} | 10% ${max(s['usd10'], 0):,.0f} "
                      f"(DD {s['dd10']:.0%}, streak {s['streak']}) | 2% ${s['usd2']:,.0f} 1% ${s['usd1']:,.0f} ({s['dd1']:.0%}) | "
                      f"stress R {s['stress_R']:+.1f} PF {s['stress_pf']:.2f}")


if __name__ == "__main__":
    main()
