"""(Already run on 2026-11-05; final_test refuses a second run. Kept as the record.)
Run asia_news_lab.final_test ONCE for the locked Nasdaq v2 version (tag "nasdaq_v2").
usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python <folder>/lab/run_final_test.py
Writes <folder>/final_test_nasdaq_v2.json (copy of the result) and prints the summary."""
import json
import sys
from pathlib import Path

NQ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(NQ.parents[1] / "scripts"))
sys.path.insert(0, str(NQ))
import asia_news_lab as L  # noqa: E402
from newsbot.backtest import make_trades  # noqa: E402

locked = json.loads((NQ / "LOCKED_NQ.json").read_text())
assert locked["locked_at_utc"] != "PENDING", "lock LOCKED_NQ.json first"
bot_copy = locked
assert bot_copy["versions"] == locked["versions"], "bot/LOCKED_NQ.json differs from LOCKED_NQ.json"
cfg = locked["versions"]["nasdaq_v2"]

res = L.final_test({"nasdaq_v2": (make_trades, cfg, "NAS100")}, tag="nasdaq_v2")
(NQ / "final_test_nasdaq_v2.json").write_text(json.dumps(res, indent=1, default=str))
r = res["nasdaq_v2"]
m, m2 = r["test"], r["test_2x_cost"]
print(f"nasdaq_v2 Jul 1 - Oct 15 2026: n {m['n']}  R {m['R']:+.2f}  PF {m['pf']:.2f}  win {m['win']:.0%}  "
      f"DD {m['dd']:.1%}  $1000 -> {m['usd']:.0f}  max losing streak {m['max_losing_streak']}")
print(f"   at 2 x cost: n {m2['n']}  R {m2['R']:+.2f}  PF {m2['pf']:.2f}  DD {m2['dd']:.1%}")
print(f"   success (>= 8 trades, R > 0, PF >= 1.3, DD better than -35%): {r['success']}")
for t in r["trades"]:
    print("  ", t["entry_time"], t["exit_time"], f"dir {int(t['dir']):+d}", f"R {float(t['r']):+.3f}", t["event"][:90])
