"""run strategy.py's signal + btc_common.trades/account for a params dict on Jan-Jun with the light loader
(same arrays as btc_common.Market, checked), normal and stress; per-month R; Jan-Apr / May-Jun / Jan-Jun stats.
usage: python verify.py '<json params>'"""
import json
import sys

import numpy as np
import pandas as pd

import lab
import strategy
from lab import bc


class Adapter(lab.Lab):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.vol = self.vol_at(self.t0 + np.arange(self.n))
        self.CB = np.r_[0.0, np.cumsum(self.bq, dtype=np.float64)]
        self.CS = np.r_[0.0, np.cumsum(self.sq, dtype=np.float64)]


def run(mk, p, stress=False):
    dec, d, vol, move = strategy.signals(mk, p)
    sd = p["stop"] * (vol if p.get("stype", "v") == "v" else move)
    t = bc.trades(mk, dec, d, kind=p.get("kind", 0), offset=p.get("off", 0.0) * vol, life=p.get("life", 180),
                  stop_dist=sd, tp_r=p.get("tp", np.nan), hold=p.get("hold", 0), be_at=p.get("be", np.nan),
                  trail=p.get("tr", np.nan), stress=stress)
    return t.sort_values(["entry_ts", "sig_ts"]).reset_index(drop=True)


def report(mk, p, name=""):
    out = {}
    t = run(mk, p)
    ts_ = run(mk, p, stress=True)
    for lab_, a, b in (("Jan-Apr", "2026-01-01", "2026-05-01"), ("May-Jun", "2026-05-01", "2026-07-01"),
                       ("Jan-Jun", "2026-01-01", "2026-07-01"), ("Jan-Mar", "2026-01-01", "2026-04-01"),
                       ("Apr-Jun", "2026-04-01", "2026-07-01")):
        x = t[(t.entry_ts >= bc.ts_of(a)) & (t.entry_ts < bc.ts_of(b))]
        y = ts_[(ts_.entry_ts >= bc.ts_of(a)) & (ts_.entry_ts < bc.ts_of(b))]
        s = bc.account(x, a, b, maxpos=p["maxpos"])
        ss = bc.account(y, a, b, maxpos=p["maxpos"])
        s["stress_pf"] = ss["pf"]
        s["stress_R"] = ss["R"]
        s["stress_final"] = ss["final"]
        out[lab_] = s
    res = pd.DataFrame(out).T
    # per-month R of the trades actually taken in the Jan-Jun account (replica of nb_account with taken flags)
    from engine import acct_full
    x = t[(t.entry_ts >= bc.ts_of("2026-01-01")) & (t.entry_ts < bc.ts_of("2026-07-01"))].reset_index(drop=True)
    taken, bal, dd = acct_full(x.entry_ts.to_numpy(np.int64), x.exit_ts.to_numpy(np.int64), x.r.to_numpy(float),
                               x.sd.to_numpy(float), x.entry_px.to_numpy(float), np.ones(len(x), np.bool_),
                               p["maxpos"], bc.ts_of("2026-01-01"), bc.ts_of("2026-07-01"))
    assert abs(bal - out["Jan-Jun"]["final"]) < 1e-6 * max(1, bal), (bal, out["Jan-Jun"]["final"])
    mo = pd.to_datetime(x.entry_ts, unit="s").dt.month
    pm = x.r[taken].groupby(mo[taken]).agg(["sum", "count"]).round(2).to_dict("index")
    return res, pm, t


if __name__ == "__main__":
    p = json.loads(sys.argv[1])
    for k in ("tp", "be", "tr"):
        if p.get(k) is None:
            p[k] = np.nan
    mk = Adapter(start="2025-12-01", end="2026-07-01")
    res, pm, t = report(mk, p)
    pd.set_option("display.width", 250)
    print(res.round(3).to_string())
    print("per-month R / trades (Jan-Jun account):", pm)
