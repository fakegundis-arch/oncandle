"""2-minute straddle with take-profit / stop-loss exits, gold and Nasdaq, on FinancialJuice + Walter Bloomberg headlines.
PROTOCOL (fixed before any result, Nov 7 2026), the user's design.

  * When the bot reads a tradable headline (newsbot_lab rules, post time + 2 s) it places a BUY STOP `dist` above and
    a SELL STOP `dist` below the mid price (each at least half a spread outside bid / ask), one cancels the other,
    LIVE FOR 2 MINUTES (cancelled after 120 s if neither triggers).
  * Exit ONLY by the stop loss or the take profit (target = r x stop distance) - no time exit.  One safety rule: a
    position still open when the market pauses for the daily break or the weekend (a >= 10-minute pause in quotes) is
    closed at the last price before the pause (holding through the close gave the 49-hour, -17.7R trade earlier).
  * Fills, slippage (+1 spread; stress: read 5 s late + 2 spreads), the worse leg when both trigger in one second,
    one position at a time, $1,000 at 10 % risk: as straddle_fixed_lab.py.
  * Knobs (Jan-Jun 2026 only):  dist  gold $ {2, 3, 4, 5, 6, 8, 10, 12, 15, 20};  Nasdaq points {10, 15, 20, 25, 30,
    40, 50, 60, 80, 100};  stop in {opp = at the other order (2 x dist), mid = back at the start (1 x dist),
    half = 0.5 x dist} (at least 3 spreads);  r in {1, 2, 3};  topics in {ALL, GEO+ENERGY, FED, TRADE+POLITICS+CHINA};
    channel in {both, FJ, WB}  -> 1,080 settings per instrument.
  * Pass (Jan-Jun): >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, stress PF >= 1.15, max drawdown at 10 %
    better than -35 %.  Pick: most passing neighbours (one knob one step), then shallower drawdown, then higher R.
  * TEST once on Jul 1 - Oct 31 2026: success = >= 20 trades, R > 0, PF >= 1.3, drawdown better than -35 %.  If no
    setting passes for an instrument, its highest-R setting gets one information-only Jul-Oct run (declared here).
    Jul-Oct was the test period of the earlier straddles (60-s / 5-15-min orders, time exits); no 2-minute TP / SL
    straddle has been run on it.
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
W = 120
DIST = {"gold": [2, 3, 4, 5, 6, 8, 10, 12, 15, 20], "nasdaq": [10, 15, 20, 25, 30, 40, 50, 60, 80, 100]}
GRID_REST = dict(stop=["opp", "mid", "half"], r=[1, 2, 3], topics=["ALL", "GEO+ENERGY", "FED", "TRADE+POLITICS+CHINA"],
                 channel=["both", "FJ", "WB"])
KNOBS = ["dist"] + list(GRID_REST)
STOP_X = {"opp": 2.0, "mid": 1.0, "half": 0.5}
_GAPS: dict = {}


def grid(inst: str) -> dict:
    return {"dist": DIST[inst], **GRID_REST}


def features(tp: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"t_post": [int(t.timestamp()) for t in tp.t], "topics": list(tp.topics), "ch": list(tp.ch)})


def next_close(tk: dict, i: int) -> int:
    """index of the last tick before the next >= 10-minute pause in quotes at / after index i."""
    key = id(tk)
    if key not in _GAPS:
        _GAPS[key] = np.flatnonzero(np.diff(tk["t"]) >= S.GAP)
    g = _GAPS[key]
    k = np.searchsorted(g, i)
    return int(g[k]) if k < len(g) else len(tk["t"]) - 1


def exit_tpsl(tk, j, fill, d, sd, r, end):
    """TP / SL from the second after the fill j, until the last tick before the close `end` -> (index, r)."""
    sl, tp = fill - d * sd, fill + d * r * sd
    a = j + 1
    step = 1800
    while a <= end:
        b = min(end + 1, a + step)
        if d > 0:
            first, lo, hi = tk["bid_first"][a:b], tk["bid_min"][a:b], tk["bid_max"][a:b]
            g_sl, h_sl, g_tp, h_tp = first <= sl, lo <= sl, first >= tp, hi >= tp
        else:
            first, lo, hi = tk["ask_first"][a:b], tk["ask_min"][a:b], tk["ask_max"][a:b]
            g_sl, h_sl, g_tp, h_tp = first >= sl, hi >= sl, first <= tp, lo <= tp
        hit = g_sl | h_sl | g_tp | h_tp
        if hit.any():
            k = int(np.argmax(hit))
            px = first[k] if (g_sl[k] or g_tp[k]) else (sl if h_sl[k] else tp)
            return a + k, d * (px - fill) / sd
        a, step = b, step * 4
    k = min(end, len(tk["t"]) - 1)                      # flat before the close
    px = tk["bid_last"][k] if d > 0 else tk["ask_last"][k]
    return k, d * (px - fill) / sd


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
    up, dn = max(mid + cfg["dist"], ask + 0.5 * spread), min(mid - cfg["dist"], bid - 0.5 * spread)
    end = next_close(tk, i)
    w_end = min(np.searchsorted(T, T[i] + W), end + 1)
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
        sd = max(STOP_X[cfg["stop"]] * cfg["dist"], 3 * sp_j)
        kx, r = exit_tpsl(tk, j, fill, d, sd, cfg["r"], end)
        if out is None or r < out[2]:
            out = (int(T[j]), int(T[kx]), float(r), d)
    return out


def run(feat: pd.DataFrame, inst: str, cfg: dict, stress: bool = False) -> pd.DataFrame:
    tk = N.ticks(inst)
    allowed = set(N.TOPICS[cfg["topics"]])
    rows, busy = [], -1
    for f in feat.itertuples():
        if f.t_post <= busy or not (set(f.topics) & allowed) or (cfg["channel"] != "both" and f.ch != cfg["channel"]):
            continue
        res = straddle(tk, f, cfg, stress)
        if res is None:
            busy = max(busy, f.t_post + (N.LAT_STRESS if stress else N.LAT) + W)
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


def final_test(picks: dict, tag: str) -> dict:
    """ONE run on Jul-Oct 2026: picks = {inst: cfg}. Saves results/telegram_news/<tag>_test.json, refuses a rerun."""
    fpath = N.OUT / f"{tag}_test.json"
    if fpath.exists():
        raise RuntimeError("final_test has already been run")
    feat = features(N.tradable(N.load_posts("2026-06-30", TEST[1])))
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
