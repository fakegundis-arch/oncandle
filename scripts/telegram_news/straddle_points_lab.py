"""Nasdaq +/-30-point straddle on FinancialJuice + Walter Bloomberg headlines.  PROTOCOL (fixed before any result,
Nov 7 2026).  The user's design: Nasdaq at 26,700 -> buy stop 26,730, sell stop 26,670.

  * When the bot reads a tradable headline (newsbot_lab rules, post time + 2 s) it places a BUY STOP 30 points above and
    a SELL STOP 30 points below the mid price (each at least half a spread outside bid / ask), one cancels the other.
  * Fills, slippage (+1 spread; stress: read 5 s late + 2 spreads), the worse leg when both trigger in one second,
    flat before the daily / weekend close, one at a time, $1,000 at 10 % risk: exactly as straddle_fixed_lab.py.
  * Searched on Jan-Jun 2026 only (the distance stays 30 points): order life W in {60, 300, 900} s; stop in
    {opp = at the other order (60 points from the fill), mid = back at the starting price (30 points)} (at least 3
    spreads); target r in {0, 1, 2} x stop; hold H in {300, 900, 1800} s; topics in {ALL, GEO+ENERGY, FED,
    TRADE+POLITICS+CHINA}  -> 216 settings.
  * Pass (Jan-Jun): >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, stress PF >= 1.15, max drawdown at 10 %
    better than -35 %.  Pick: most passing neighbours, then shallower drawdown, then higher R.
  * TEST once on Jul 1 - Oct 31 2026 (no +/-30-point Nasdaq straddle has been run on it): success = >= 20 trades,
    R > 0, PF >= 1.3, drawdown better than -35 %.  If no setting passes, the highest-R one gets one information-only
    Jul-Oct run (declared here).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import newsbot_lab as N
import straddle_fixed_lab as F
import straddle_lab as S

INST = "nasdaq"
BUILD, HALVES, TEST = F.BUILD, F.HALVES, F.TEST
GRID = dict(pts=[30], W=[60, 300, 900], stop=["opp", "mid"], r=[0, 1, 2], H=[300, 900, 1800],
            topics=["ALL", "GEO+ENERGY", "FED", "TRADE+POLITICS+CHINA"])
KNOBS = list(GRID)
features = F.features
passes_build = F.passes_build


def straddle(tk, f, cfg, stress=False):
    T = tk["t"]
    lat = N.LAT_STRESS if stress else N.LAT
    slip_k = 2.0 if stress else 1.0
    tpl = f.t_post + lat
    i = np.searchsorted(T, tpl)
    if i >= len(T) or T[i] - tpl > 10:
        return None
    bid, ask = tk["bid_first"][i], tk["ask_first"][i]
    spread = ask - bid
    mid = 0.5 * (bid + ask)
    up, dn = max(mid + cfg["pts"], ask + 0.5 * spread), min(mid - cfg["pts"], bid - 0.5 * spread)
    gaps = np.flatnonzero(np.diff(T[i: i + 4000]) >= S.GAP)
    end_gap = i + int(gaps[0]) if len(gaps) else len(T) - 1
    w_end = min(np.searchsorted(T, T[i] + cfg["W"]), end_gap + 1)
    hu, hd = tk["ask_max"][i + 1: w_end] >= up, tk["bid_min"][i + 1: w_end] <= dn
    hit = hu | hd
    if not hit.any():
        return None
    k = int(np.argmax(hit))
    j = i + 1 + k
    af, bf = tk["ask_first"][j], tk["bid_first"][j]
    legs = ([(1, max(up, af))] if hu[k] else []) + ([(-1, min(dn, bf))] if hd[k] else [])
    sp_j = af - bf
    out = None
    for d, px in legs:
        fill = px + d * slip_k * sp_j
        sd = max((up - dn) if cfg["stop"] == "opp" else 0.5 * (up - dn), 3 * sp_j)
        kx, r = S._exit(tk, j, fill, d, sd, cfg["r"], cfg["H"], end_gap)
        if out is None or r < out[2]:
            out = (int(T[j]), int(T[kx]), float(r), d)
    return out


def run(feat: pd.DataFrame, inst: str, cfg: dict, stress: bool = False) -> pd.DataFrame:
    tk = N.ticks(inst)
    allowed = set(N.TOPICS[cfg["topics"]])
    rows, busy = [], -1
    for f in feat.itertuples():
        if f.t_post <= busy or not (set(f.topics) & allowed):
            continue
        res = straddle(tk, f, cfg, stress)
        if res is None:
            busy = max(busy, f.t_post + (N.LAT_STRESS if stress else N.LAT) + cfg["W"])
            continue
        ft, xt, r, d = res
        busy = xt
        rows.append(dict(entry_time=pd.Timestamp(ft, unit="s"), exit_time=pd.Timestamp(xt, unit="s"), dir=d, r=r))
    return pd.DataFrame(rows, columns=["entry_time", "exit_time", "dir", "r"])


def final_test(cfg: dict, tag: str) -> dict:
    """ONE run on Jul-Oct 2026 for Nasdaq. Saves results/telegram_news/<tag>_test.json, refuses a second run."""
    fpath = N.OUT / f"{tag}_test.json"
    if fpath.exists():
        raise RuntimeError("final_test has already been run")
    feat = features(N.tradable(N.load_posts("2026-06-30", TEST[1])))
    t, ts = run(feat, INST, cfg), run(feat, INST, cfg, stress=True)
    m, ms = N.metrics(t, *TEST), N.metrics(ts, *TEST)
    ok = m["n"] >= 20 and m["R"] > 0 and m["pf"] >= 1.3 and m["dd"] > -0.35
    res = dict(cfg=cfg, test=m, test_stress=ms, success=ok,
               trades=t[(t.entry_time >= TEST[0]) & (t.entry_time < TEST[1])].astype(str).to_dict("records"))
    fpath.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), result=res),
                                indent=1, default=str))
    return res
