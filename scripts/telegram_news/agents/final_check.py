"""ONE run of an agent's frozen candidates on the hidden months Jul 1 - Oct 31 2026 (full data folder), normal and
stress, plus Jan 1 - Oct 31 2026 for the whole-year account.  Refuses a second run.
usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/telegram_news/agents/final_check.py <agent>"""
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import common as C  # noqa: E402

agent = sys.argv[1]
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
out = os.path.join(ROOT, "results", "telegram_news", f"agent_{agent}_test.json")
if os.path.exists(out):
    raise SystemExit("final check already run for " + agent)
spec = importlib.util.spec_from_file_location(f"{agent}_strategy", os.path.join(HERE, agent, "strategy.py"))
S = importlib.util.module_from_spec(spec)
sys.path.insert(0, os.path.join(HERE, agent))
spec.loader.exec_module(S)
D = os.path.join(ROOT, "data")
TEST, YEAR = ("2026-07-01", "2026-11-01"), ("2026-01-01", "2026-11-01")
res = {}
for name, p in S.CANDIDATES.items():
    t = S.backtest(p, D, *YEAR)
    ts = S.backtest(p, D, *TEST, stress=True)
    tt = t[t.entry_ts >= pd.Timestamp(TEST[0], tz="UTC").timestamp()]
    month = pd.to_datetime(tt.entry_ts, unit="s").dt.strftime("%Y-%m")
    res[name] = dict(params=p,
                     test={f"{int(rk * 100)}%": C.metrics(t, *TEST, risk=rk) for rk in (0.10, 0.05, 0.02, 0.01)},
                     test_stress=C.metrics(ts, *TEST), year_10=C.metrics(t, *YEAR),
                     month_R=tt.groupby(month).r.agg(["size", "sum"]).round(2).to_dict("index"),
                     trades=tt.to_dict("records"))
json.dump(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), agent=agent, results=res),
          open(out, "w"), indent=1, default=float)
for name, r in res.items():
    m, ms, y = r["test"]["10%"], r["test_stress"], r["year_10"]
    print(f"{name}: Jul-Oct {m['n']} trades, R {m['R']:+.1f}, PF {m['pf']:.2f}, win {m['win']:.0%}, $1,000 -> "
          f"${m['final']:,.0f} (DD {m['dd']:.0%}, max lot {m['max_lot']:.2f}) | 5%: ${r['test']['5%']['final']:,.0f} "
          f"DD {r['test']['5%']['dd']:.0%} | 2%: ${r['test']['2%']['final']:,.0f} DD {r['test']['2%']['dd']:.0%} | "
          f"stress R {ms['R']:+.1f} PF {ms['pf']:.2f} | Jan-Oct at 10%: ${y['final']:,.0f} (DD {y['dd']:.0%})")
    print("   per month (trades, R):", {k: (int(v["size"]), v["sum"]) for k, v in r["month_R"].items()})
