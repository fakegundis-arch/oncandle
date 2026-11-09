"""Version-3 candidate from researcher "oi" (positioning signal), honest metrics timing.

Rule (OI_BIGMOVE): a Binance 5-minute metrics row with create_time ct describes [ct, ct+300) and is known at ct + 360
(btc_common known_ts).  At that moment, if
  * Binance BTCUSDT open interest fell >= 0.4 % over the 30 minutes ending with that row (row ct vs row ct - 30 min), and
  * the Binance price moved >= 0.8 % during that row's 5 minutes [ct, ct+300) (last trade before ct+300 vs before ct),
then follow the move: market order at ct + 360 (+ btc_common latency), stop 4 x vol, target 1.5 R, once the trade is
+1 R ahead the stop moves to break-even and then trails 0.5 R behind the best price, out after 10 minutes at the latest;
one position at a time.  vol = btc_common.Market.vol at the decision second.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import btc_common as bc  # noqa: E402

CANDIDATES = {
    "OI_BIGMOVE": dict(maxpos=1, oi_rows=6, oi_drop=-0.004, move=0.008, stop_k=4.0, tp_r=1.5, hold=600, be_at=1.0,
                       trail=0.5),
}


def signals(mk: bc.Market, p: dict):
    """-> decision seconds, directions (no look-ahead: metrics row used from its known_ts, Binance seconds < s)."""
    m = mk.metrics
    ct = m.ts.to_numpy(np.int64)
    known = m.known_ts.to_numpy(np.int64)
    oi = pd.Series(m.sum_open_interest.to_numpy(float), index=ct)
    oi_back = oi.reindex(ct - 300 * p["oi_rows"]).to_numpy()
    d_oi = oi.to_numpy() / oi_back - 1                                   # OI change over the last oi_rows rows
    a = ct - mk.t0                                                        # window start (second index)
    b = a + 300                                                           # window end
    ok = (a >= 1) & (known - mk.t0 < mk.n) & np.isfinite(d_oi)
    a, b, s, d_oi = a[ok], b[ok], known[ok], d_oi[ok]
    mv = mk.c[b - 1] / mk.c[a - 1] - 1                                    # last trade before ct+300 vs before ct
    vol = mk.vol[s - mk.t0]
    sel = (d_oi <= p["oi_drop"]) & (np.abs(mv) >= p["move"]) & np.isfinite(vol) & (vol > 0)
    return s[sel], np.sign(mv[sel]).astype(np.int64), vol[sel]


def backtest(params: dict, data_dir: str, start: str, end: str, stress: bool = False) -> pd.DataFrame:
    look = (pd.Timestamp(start) - pd.Timedelta(days=32)).strftime("%Y-%m-%d")
    mk = bc.Market(data_dir, look, end)
    s, d, vol = signals(mk, params)
    a, b = bc.ts_of(start), bc.ts_of(end)
    keep = (s >= a - 3600) & (s < b)
    s, d, vol = s[keep], d[keep], vol[keep]
    t = bc.trades(mk, s, d, kind=0, stop_dist=params["stop_k"] * vol, tp_r=params["tp_r"], hold=params["hold"],
                  be_at=params["be_at"], trail=params["trail"], stress=stress)
    t = t[(t.entry_ts >= a) & (t.entry_ts < b)].reset_index(drop=True)
    return t[["sig_ts", "dir", "entry_ts", "exit_ts", "r", "sd", "entry_px"]]


if __name__ == "__main__":
    data = sys.argv[1] if len(sys.argv) > 1 else "/home/user/btc_lab_data"
    st, en = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("2026-01-01", "2026-07-01")
    for name, p in CANDIDATES.items():
        for stress in (False, True):
            t = backtest(p, data, st, en, stress)
            print(name, "stress" if stress else "", bc.account(t, st, en, maxpos=p["maxpos"]))
