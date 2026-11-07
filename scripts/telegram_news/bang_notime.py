"""The user's two gold settings on FinancialJuice ❗ headlines WITHOUT the 30-minute time exit (Nov 7 2026).
Fixed before running; nothing is searched, so both periods are reported (Jan-Jun 2026 and Jul-Oct 2026).
  * gold direct  : follow gold's mid move over the 30 s before the bot reads the post (MOM L=30, k=0), market order,
                   stop $10, target 2R ($20)
  * gold straddle: buy stop / sell stop $5 from the price, live 60 s, one cancels the other, stop at the other order
                   ($10), target 2R ($20)
Exit ONLY at the stop or the target; a trade still open at the daily break / weekend is closed just before it.
Everything else as bang_lab.py (❗ without $MACRO, first of story, outside calendar windows, +1 spread on fills,
stress 5 s + 2 spreads, one position at a time).  usage: python3 -I scripts/telegram_news/bang_notime.py"""
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bang_lab as B  # noqa: E402
import newsbot_lab as N  # noqa: E402

SETTINGS = {
    "gold_direct_no_time_exit": ("direct", dict(dir=B.DIRS.index(dict(fam="MOM", L=30, k=0.0)), stop_abs=10, r=2, H=None,
                                                topics="ANY", cal="excl")),
    "gold_straddle_no_time_exit": ("straddle", dict(dist=5, W=60, stop="opp", r=2, H=None, topics="ANY", cal="excl")),
}


def main():
    tr = B.triggers("2026-01-01", B.TEST[1])
    f = B.features(tr, "gold")
    out = {}
    for name, (kind, c) in SETTINGS.items():
        t, ts = B.run(f, "gold", kind, c), B.run(f, "gold", kind, c, stress=True)
        rec = {"desc": B.describe(("gold", kind), c), "cfg": c}
        for per, (a, b) in (("jan_jun", B.BUILD), ("jul_oct", B.TEST)):
            x = t[(t.entry_time >= a) & (t.entry_time < b)]
            hold = (x.exit_time - x.entry_time).dt.total_seconds() / 60
            rec[per] = {"m10": N.metrics(t, a, b), "m2": N.metrics(t, a, b, 0.02), "m1": N.metrics(t, a, b, 0.01),
                        "stress": N.metrics(ts, a, b),
                        "targets": int((x.r > 1.99).sum()), "stops": int((x.r < -0.99).sum()),
                        "closed_at_break": int(((x.r >= -0.99) & (x.r <= 1.99)).sum()),
                        "median_hold_min": float(hold.median()) if len(x) else None,
                        "by_month": x.groupby(x.entry_time.dt.strftime("%Y-%m")).r.sum().round(2).to_dict(),
                        "trades": x.astype(str).to_dict("records")}
        out[name] = rec
    (N.OUT / "bang_notime_results.json").write_text(json.dumps(out, indent=1, default=str))
    for name, rec in out.items():
        print(f"\n{name}: {rec['desc']}")
        for per in ("jan_jun", "jul_oct"):
            d = rec[per]; m, s = d["m10"], d["stress"]
            print(f"  {per}: n {m['n']} R {m['R']:+.1f} PF {m['pf']:.2f} win {m['win']:.0%} | 10%: ${max(m['usd'], 0):,.0f} "
                  f"(DD {m['dd']:.0%}) 2%: ${d['m2']['usd']:,.0f} (DD {d['m2']['dd']:.0%}) 1%: ${d['m1']['usd']:,.0f} "
                  f"(DD {d['m1']['dd']:.0%}) | stress R {s['R']:+.1f} PF {s['pf']:.2f} | targets {d['targets']} stops "
                  f"{d['stops']} closed at the break {d['closed_at_break']} | median hold {d['median_hold_min']:.0f} min "
                  f"| streak {m['max_losing_streak']}")
            print(f"     by month: {d['by_month']}")


if __name__ == "__main__":
    main()
