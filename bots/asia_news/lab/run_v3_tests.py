"""Run the two unseen tests of Nasdaq v3 ONCE (research_v3.md, protocol 5): Jul 1 - Oct 15 2026 with
asia_news_lab.final_test(tag="nasdaq_v3") and Jan - Dec 2025 with asia_news_lab.exam_2025(tag="nasdaq_v3").
Both refuse a second run.  usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python bots/asia_news/lab/run_v3_tests.py"""
import json
import sys
from pathlib import Path

BOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BOT.parents[1] / "scripts"))
sys.path.insert(0, str(BOT))
import asia_news_lab as L  # noqa: E402
from newsbot.backtest import make_trades  # noqa: E402

locked = json.loads((BOT / "LOCKED_V3.json").read_text())
cfg = locked["versions"]["nasdaq_v3"]
S = {"nasdaq_v3": (make_trades, cfg, "NAS100")}


def show(title, m, m2, ok, rule, trades):
    print(f"{title}: n {m['n']}  R {m['R']:+.2f}  PF {m['pf']:.2f}  win {m['win']:.0%}  max DD {m['dd']:.1%}  "
          f"$1,000 -> {m['usd']:,.0f}  longest losing streak {m['max_losing_streak']}")
    print(f"   at 2 x cost: n {m2['n']}  R {m2['R']:+.2f}  PF {m2['pf']:.2f}  max DD {m2['dd']:.1%}  $1,000 -> {m2['usd']:,.0f}")
    print(f"   success ({rule}): {ok}")
    for t in trades:
        print("  ", t["entry_time"], t["exit_time"], f"dir {int(float(t['dir'])):+d}", f"R {float(t['r']):+.3f}",
              t["event"][:60])


r = L.final_test(S, tag="nasdaq_v3")["nasdaq_v3"]
show("Jul 1 - Oct 15 2026", r["test"], r["test_2x_cost"], r["success"], ">= 8 trades, R > 0, PF >= 1.3, DD > -35%",
     r["trades"])
e = L.exam_2025(S, tag="nasdaq_v3")["nasdaq_v3"]
show("Jan - Dec 2025", e["exam"], e["exam_2x_cost"], e["success"], "R > 0, PF >= 1.2", e["trades"])
print("v3 WORKS (passes both)" if r["success"] and e["success"] else "v3 does NOT pass both unseen tests")
