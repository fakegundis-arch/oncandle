"""Final numbers for the frozen candidates, through strategy.backtest (common.py fills / exits / account)."""
import json, sys
import numpy as np, pandas as pd
from lib import C, DATA, WORK
import strategy as ST

PERIODS = [("search 2025-01..2026-04", "2025-01-01", "2026-05-01"), ("check 2026-05..06", "2026-05-01", "2026-07-01"),
           ("Jan-Jun 2026", "2026-01-01", "2026-07-01")]


def run(names):
    out = {}
    for nm in names:
        prm = ST.CANDIDATES[nm]
        tr = ST.backtest(prm, DATA, "2025-01-01", "2026-07-01")
        trs = ST.backtest(prm, DATA, "2025-01-01", "2026-07-01", stress=True)
        tr.to_csv(f"{WORK}/trades_{nm}.csv", index=False); trs.to_csv(f"{WORK}/trades_{nm}_stress.csv", index=False)
        res = {}
        for lab, a, b in PERIODS:
            m = C.metrics(tr, a, b); ms = C.metrics(trs, a, b)
            res[lab] = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()}
            res[lab]["stress_pf"] = round(ms["pf"], 3); res[lab]["stress_R"] = round(ms["R"], 1); res[lab]["stress_final"] = round(ms["final"], 0)
        tr["m"] = pd.to_datetime(tr.entry_ts, unit="s").dt.strftime("%Y-%m")
        res["per_month_R"] = tr.groupby("m").r.sum().round(2).to_dict()
        res["per_month_n"] = tr.groupby("m").size().to_dict()
        out[nm] = res
        print(nm, json.dumps(res, indent=1, default=float), flush=True)
    json.dump(out, open(f"{WORK}/final_eval.json", "w"), indent=1, default=float)


if __name__ == "__main__":
    run(sys.argv[1:] or list(ST.CANDIDATES))
