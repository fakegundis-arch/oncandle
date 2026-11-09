"""Search helpers: light Exness loader identical to btc_common.Market's, per-signal outcomes with btc_common.nb_trades,
fast account with btc_common.nb_account."""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import btc_common as bc  # noqa: E402

D = "/home/user/btc_lab_data"
HERE = os.path.dirname(os.path.abspath(__file__))


class Ex:
    def __init__(self, start="2025-12-01", end="2026-07-01"):
        t1 = bc.ts_of(end)
        ms = bc._months(start, end)
        parts = [dict(np.load(os.path.join(D, "exness", f"{m}.npz"))) for m in ms]
        tk = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
        del parts
        o = np.argsort(tk["t"], kind="stable")
        tk = {k: v[o] for k, v in tk.items()}
        keep = np.r_[True, np.diff(tk["t"]) > 0] & (tk["t"] < t1)
        self.tk = {k: np.ascontiguousarray(v[keep]) for k, v in tk.items()}
        self.gaps = np.flatnonzero(np.diff(self.tk["t"]) >= bc.GAP).astype(np.int64)

    def run(self, sig, dirs, stop_dist, tp_r=np.nan, hold=0, be_at=np.nan, trail=np.nan, stress=False, kind=0,
            offset=0.0, life=180):
        m = len(sig)
        f = lambda v, t: np.broadcast_to(np.asarray(v, t), (m,)).copy()
        tk = self.tk
        return bc.nb_trades(tk["t"], tk["bid_first"], tk["bid_last"], tk["bid_min"], tk["bid_max"], tk["ask_first"],
                            tk["ask_last"], tk["ask_min"], tk["ask_max"], self.gaps, np.asarray(sig, np.int64),
                            f(dirs, np.int64), f(kind, np.int64), f(offset, float), f(life, np.int64),
                            f(stop_dist, float), f(tp_r, float), f(hold, np.int64), f(be_at, float), f(trail, float),
                            stress)


def acct(ent, ext, rr, sds, pxs, start, end, maxpos=1):
    o = np.lexsort((np.arange(len(ent)), ent))
    n, wn, R, gw, gl, bal, dd, ml = bc.nb_account(ent[o], ext[o], rr[o], sds[o], pxs[o], maxpos, bc.RISK, bc.CAP,
                                                 bc.MAXOPEN, bc.ts_of(start), bc.ts_of(end))
    return dict(n=int(n), R=float(R), pf=float(gw / gl) if gl > 0 else 99.0, win=wn / max(n, 1), final=float(bal),
                dd=float(dd), max_lot=float(ml))
