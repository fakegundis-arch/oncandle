"""Fixed-distance straddle on FinancialJuice + Walter Bloomberg headlines (gold / Nasdaq).  PROTOCOL (fixed before any
result, Nov 7 2026).  The user's design: gold at 4,670 -> buy stop 4,675, sell stop 4,665; the same for Nasdaq.

  * When the bot reads a tradable headline (newsbot_lab rules, post time + 2 s) it places a BUY STOP at mid x (1 + p)
    and a SELL STOP at mid x (1 - p), one cancels the other; mid = the price at that moment.  The distance is a
    PERCENT of the price so the rule means the same at any price level: p in {0.05, 0.10, 0.15, 0.20, 0.30, 0.45} %
    = about $2.3 / $4.7 / $7.0 / $9.3 / $14 / $21 for gold at 4,670 (the user's $5 example is ~0.10 %) and about
    13 / 26 / 39 / 51 / 77 / 116 points for Nasdaq at 25,670.  Each level is at least half a spread outside bid / ask.
  * Fills, slippage, stress test, both-legs rule, flat-before-close, one-at-a-time and $1,000 / 10 % risk: exactly as
    straddle_lab.py (fill at the level or worse + one spread; stress: read 5 s late + two spreads; the worse leg when
    both trigger in one second; closed at the last price before a >= 10-minute pause in quotes).
  * Knobs: p (above), order life W in {60, 300, 900} s, stop in {opp = at the other order's level (2 x the distance),
    mid = back at the starting price (1 x the distance)} (at least 3 spreads), target r in {0, 1, 2} x stop,
    hold H in {300, 900, 1800} s, topics in {ALL, GEO+ENERGY, FED, TRADE+POLITICS+CHINA}  -> 1,296 per instrument.
  * BUILD on Jan 1 - Jun 30 2026 (the user's choice, Nov 7: "build on the first 6 months of 2026 and then backtest it
    on the remaining months of 2026 unseen").  Pass: >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, stress
    PF >= 1.15, max drawdown at 10 % better than -35 %.  Pick: most passing neighbours (one knob one step), then
    shallower drawdown, then higher R.
  * TEST once on Jul 1 - Oct 31 2026: success = >= 20 trades, R > 0, PF >= 1.3, drawdown better than -35 %.  If NO
    setting passes for an instrument, its highest-R build setting gets one information-only Jul-Oct run instead
    (declared here, before any result).  Jul-Oct was already the test period of the direction bots and of the
    volatility-scaled straddle; no fixed-distance straddle has been run on it.
  (Revision of Nov 7, before any result: the first draft built on Jan-Oct 2026 and tested on 2025.)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import newsbot_lab as N
import straddle_lab as S

BUILD = ("2026-01-01", "2026-07-01")
HALVES = {"jan-mar": ("2026-01-01", "2026-04-01"), "apr-jun": ("2026-04-01", "2026-07-01")}
TEST = ("2026-07-01", "2026-11-01")
GRID = dict(p=[0.05, 0.10, 0.15, 0.20, 0.30, 0.45], W=[60, 300, 900], stop=["opp", "mid"], r=[0, 1, 2],
            H=[300, 900, 1800], topics=["ALL", "GEO+ENERGY", "FED", "TRADE+POLITICS+CHINA"])
KNOBS = list(GRID)


def features(tp: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"t_post": [int(t.timestamp()) for t in tp.t], "topics": list(tp.topics)})


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
    off = cfg["p"] / 100.0 * mid
    up, dn = max(mid + off, ask + 0.5 * spread), min(mid - off, bid - 0.5 * spread)
    gaps = np.flatnonzero(np.diff(T[i: i + 4000]) >= S.GAP)
    end_gap = i + int(gaps[0]) if len(gaps) else len(T) - 1
    w_end = min(np.searchsorted(T, T[i] + cfg["W"]), end_gap + 1)
    a_max, b_min = tk["ask_max"][i + 1: w_end], tk["bid_min"][i + 1: w_end]
    hu, hd = a_max >= up, b_min <= dn
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


def passes_build(t: pd.DataFrame, ts: pd.DataFrame) -> tuple[bool, dict]:
    m = N.metrics(t, *BUILD)
    h1, h2 = N.metrics(t, *HALVES["jan-mar"]), N.metrics(t, *HALVES["apr-jun"])
    ms = N.metrics(ts, *BUILD)
    chk = {"n>=40": m["n"] >= 40, "pf>=1.3": m["pf"] >= 1.3, "jan-mar R>0": h1["R"] > 0, "apr-jun R>0": h2["R"] > 0,
           "stress pf>=1.15": ms["pf"] >= 1.15, "dd>-35%": m["dd"] > -0.35}
    return all(chk.values()), dict(m, h1R=h1["R"], h2R=h2["R"], stress_pf=ms["pf"], stress_R=ms["R"], **chk)


def final_test(picks: dict, tag: str = "straddle_fixed") -> dict:
    """ONE run on Jul-Oct 2026. Saves results/telegram_news/<tag>_test.json, refuses a second run."""
    fpath = N.OUT / f"{tag}_test.json"
    if fpath.exists():
        raise RuntimeError("final_test has already been run")
    tp = N.tradable(N.load_posts("2026-06-30", TEST[1]))
    feat = features(tp)
    res = {}
    for inst, cfg in picks.items():
        t, ts = run(feat, inst, cfg), run(feat, inst, cfg, stress=True)
        m, ms = N.metrics(t, *TEST), N.metrics(ts, *TEST)
        ok = m["n"] >= 20 and m["R"] > 0 and m["pf"] >= 1.3 and m["dd"] > -0.35
        res[inst] = dict(cfg=cfg, test=m, test_stress=ms, success=ok,
                         trades=t[(t.entry_time >= TEST[0]) & (t.entry_time < TEST[1])].astype(str).to_dict("records"))
    fpath.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), results=res),
                                indent=1, default=str))
    return res
