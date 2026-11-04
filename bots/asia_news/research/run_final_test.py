"""THE one call to asia_news_lab.final_test (Jul 1 - Oct 15 2026) with the settings frozen in LOCKED.json.
The toolkit refuses a second run.  Output: <folder>/final_test_output.json + a printed summary.
usage: cd /home/user/oncandle && PYTHONDONTWRITEBYTECODE=1 python <folder>/research/run_final_test.py"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

FOLDER = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FOLDER))
sys.path.insert(0, "/home/user/oncandle/scripts")
import asia_news_lab as L  # noqa: E402
from newsbot.backtest import make_trades  # noqa: E402

locked_path = FOLDER / "LOCKED.json"
locked = json.loads(locked_path.read_text())
V, entries = locked["versions"], locked["final_test_entries"]
strategies = {name: (make_trades, V[name], sym) for name, sym in entries.items()}
print("LOCKED.json sha256", hashlib.sha256(locked_path.read_bytes()).hexdigest())

res = L.final_test(strategies)                      # <- runs once; raises if it has run before

out = {"locked_sha256": hashlib.sha256(locked_path.read_bytes()).hexdigest(), "results": res}
(FOLDER / "final_test_output.json").write_text(json.dumps(out, indent=1, default=str))   # save first, then summarise


def combined(trs):
    t = pd.DataFrame(trs)
    if not len(t):
        return dict(n=0, R=0.0, pf=0.0, dd=0.0, usd=1000.0, win=0.0)
    t["entry_time"] = pd.to_datetime(t.entry_time)
    t = t.sort_values("entry_time")
    r = t.r.astype(float).to_numpy()
    eq = np.cumprod(1 + L.RISK * r)
    gl, gw = -r[r < 0].sum(), r[r > 0].sum()
    return dict(n=len(r), R=float(r.sum()), pf=float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0),
                win=float((r > 0).mean()), usd=float(1000 * eq[-1]),
                dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()))


pair_tr = [x for k in res if k.startswith("pair_") for x in res[k]["trades"]]
pc = combined(pair_tr)
pc["success"] = pc["n"] >= 8 and pc["R"] > 0 and pc["pf"] >= 1.3 and pc["dd"] > -0.35
out["pair_combined_test"] = pc
(FOLDER / "final_test_output.json").write_text(json.dumps(out, indent=1, default=str))

print(f"{'entry':9s} {'sym':7s} {'n':>3s} {'R':>7s} {'PF':>6s} {'win':>5s} {'maxDD':>7s} {'$1000->':>8s} | 2x cost n/R/PF | success")
for k, v in res.items():
    m, m2 = v["test"], v["test_2x_cost"]
    print(f"{k:9s} {v['symbol']:7s} {m['n']:3d} {m['R']:7.2f} {m['pf']:6.2f} {m['win']:5.2f} {m['dd']:7.1%} {m['usd']:8.0f} | "
          f"{m2['n']}/{m2['R']:.2f}/{m2['pf']:.2f} | {v['success']}")
print(f"{'PAIR all':9s} {'3 pairs':7s} {pc['n']:3d} {pc['R']:7.2f} {pc['pf']:6.2f} {pc['win']:5.2f} {pc['dd']:7.1%} "
      f"{pc['usd']:8.0f} | {'':14s} | {pc['success']}")
for k, v in res.items():
    print(f"\n-- {k} trades")
    for x in v["trades"]:
        print(f"  {x['entry_time']} -> {x['exit_time']} dir {x['dir']:>2s} R {float(x['r']):+.2f}  {x['event'][:110]}")
