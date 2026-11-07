"""Straddle news bot on FinancialJuice + Walter Bloomberg headlines (gold / Nasdaq).  PROTOCOL (fixed before any
straddle result, Nov 7 2026) and engine.  Reuses newsbot_lab.py for the posts, the tradable-post rules (with the
corrected calendar window), the Exness one-second ticks and the metrics.

THE STRADDLE
  * When the bot reads a tradable headline (post time + 2 s) it places a BUY STOP at ref + d x vol and a SELL STOP at
    ref - d x vol, one cancels the other.  ref = the mid price at that moment ("now") or 30 s before the post ("pre30";
    a level the market is already beyond is filled at once at market).  vol = median |1-minute mid change| over the 2
    hours before the post (newsbot_lab.vol60).  Each level is at least half a spread outside the current bid / ask.
  * A buy stop triggers when the ASK reaches its level, a sell stop when the BID does; the fill is the level, or the
    second's first price if it opened beyond the level, PLUS one spread of slippage (stop orders fill as market
    orders).  Both levels hit in the same second -> the WORSE of the two trades is booked.  Untriggered orders are
    cancelled after W seconds.
  * After the fill: stop = the straddle width (the opposite level's distance, "opp") or m x vol from the fill (at least
    3 x the spread), target = r x stop (r = 0: none), time exit H s after the fill.  Stop before target within a
    second, gaps fill at the second's first price, checks start the second after the fill.
  * FLAT BEFORE THE CLOSE: a position is closed at the last price before any pause in quotes of >= 10 minutes (the
    daily break, the weekend), and pending orders are cancelled there - the market's schedule is known in advance.
  * One straddle / position per instrument at a time (headlines while one is working are skipped).  $1,000, 10 %
    risk per trade, compounding.  Stress test: read 5 s after the post and two spreads of slippage on the fill.
  * Knobs (Jan-Jun only): d in {0.5, 1, 2, 3}, ref in {now, pre30}, W in {60, 300, 900}, stop in {opp, 2, 4},
    r in {0, 1, 2}, H in {300, 900, 1800}, topics in {ALL, GEO+ENERGY, FED, TRADE+POLITICS+CHINA}
    -> 2,592 settings per instrument.
RULES (as newsbot_lab.py): Jan-Jun pass = >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and Apr-Jun, stress PF >= 1.15,
max drawdown at 10 % better than -35 %.  Pick = most passing neighbours (one knob one step), then shallower drawdown,
then higher R; no passing setting -> that instrument is not traded.  Jul-Oct success = >= 20 trades, R > 0,
PF >= 1.3, drawdown better than -35 %.  final_test() runs Jul-Oct once (tag "straddle").
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import newsbot_lab as N

GRID = dict(d=[0.5, 1, 2, 3], ref=["now", "pre30"], W=[60, 300, 900], stop=["opp", 2, 4], r=[0, 1, 2],
            H=[300, 900, 1800], topics=["ALL", "GEO+ENERGY", "FED", "TRADE+POLITICS+CHINA"])
KNOBS = list(GRID)
GAP = 600                      # a pause in quotes this long = the market is closed (daily break / weekend)


def features(tp: pd.DataFrame, inst: str) -> pd.DataFrame:
    tk = N.ticks(inst)
    rows = []
    for p in tp.itertuples():
        t0 = int(p.t.timestamp())
        rows.append(dict(t_post=t0, vol=N.vol60(tk, t0), pre30=N.mid_at(tk, t0 - 30), topics=p.topics))
    return pd.DataFrame(rows)


def _exit(tk, j, fill, d, sd, r, H, end_gap):
    """Trade filled in second index j -> (exit index, r)."""
    T = tk["t"]
    sl = fill - d * sd
    tp = fill + d * r * sd if r > 0 else None
    k_end = min(np.searchsorted(T, T[j] + H), end_gap + 1, len(T))
    j0 = j + 1
    if j0 < k_end:
        if d > 0:
            first, lo, hi = tk["bid_first"][j0:k_end], tk["bid_min"][j0:k_end], tk["bid_max"][j0:k_end]
            g_sl, h_sl = first <= sl, lo <= sl
            g_tp = (first >= tp) if tp is not None else np.zeros(len(first), bool)
            h_tp = (hi >= tp) if tp is not None else np.zeros(len(first), bool)
        else:
            first, lo, hi = tk["ask_first"][j0:k_end], tk["ask_min"][j0:k_end], tk["ask_max"][j0:k_end]
            g_sl, h_sl = first >= sl, hi >= sl
            g_tp = (first <= tp) if tp is not None else np.zeros(len(first), bool)
            h_tp = (lo <= tp) if tp is not None else np.zeros(len(first), bool)
        hit = g_sl | h_sl | g_tp | h_tp
        if hit.any():
            k = int(np.argmax(hit))
            px = first[k] if (g_sl[k] or g_tp[k]) else (sl if h_sl[k] else tp)
            return j0 + k, d * (px - fill) / sd
    if end_gap < k_end or k_end >= len(T):            # flat before the close: last price before the pause
        k = min(end_gap, len(T) - 1)
        px = tk["bid_last"][k] if d > 0 else tk["ask_last"][k]
        return k, d * (px - fill) / sd
    px = tk["bid_first"][k_end] if d > 0 else tk["ask_first"][k_end]
    return k_end, d * (px - fill) / sd


def straddle(tk, f, cfg, stress=False):
    """-> (fill_time, exit_time, r, dir) or None."""
    T = tk["t"]
    lat = N.LAT_STRESS if stress else N.LAT
    slip_k = 2.0 if stress else 1.0
    tpl = f.t_post + lat
    i = np.searchsorted(T, tpl)
    if i >= len(T) or T[i] - tpl > 10 or not np.isfinite(f.vol) or f.vol <= 0:
        return None
    bid, ask = tk["bid_first"][i], tk["ask_first"][i]
    spread = ask - bid
    mid = 0.5 * (bid + ask)
    ref = mid if cfg["ref"] == "now" else f.pre30
    if not np.isfinite(ref):
        return None
    off = cfg["d"] * f.vol
    up, dn = ref + off, ref - off
    if cfg["ref"] == "now":
        up, dn = max(up, ask + 0.5 * spread), min(dn, bid - 0.5 * spread)
    # the first pause in quotes >= GAP after placement (market close)
    gaps = np.flatnonzero(np.diff(T[i: i + 4000]) >= GAP)
    end_gap = i + int(gaps[0]) if len(gaps) else len(T) - 1
    w_end = min(np.searchsorted(T, T[i] + cfg["W"]), end_gap + 1)
    # second i: levels the market is already beyond -> filled at market now
    hit_up = np.zeros(0, bool)
    if ask >= up or bid <= dn:
        j, legs = i, ([(1, ask)] if ask >= up else []) + ([(-1, bid)] if bid <= dn else [])
    else:
        a_max, b_min = tk["ask_max"][i + 1: w_end], tk["bid_min"][i + 1: w_end]
        hu, hd = a_max >= up, b_min <= dn
        hit = hu | hd
        if not hit.any():
            return None
        k = int(np.argmax(hit))
        j = i + 1 + k
        af, bf = tk["ask_first"][j], tk["bid_first"][j]
        legs = ([(1, max(up, af))] if hu[k] else []) + ([(-1, min(dn, bf))] if hd[k] else [])
    sp_j = tk["ask_first"][j] - tk["bid_first"][j]
    out = None
    for d, px in legs:
        fill = px + d * slip_k * sp_j
        sd = (up - dn) if cfg["stop"] == "opp" else cfg["stop"] * f.vol
        sd = max(sd, 3 * sp_j)
        kx, r = _exit(tk, j, fill, d, sd, cfg["r"], cfg["H"], end_gap)
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
            busy = max(busy, f.t_post + (N.LAT_STRESS if stress else N.LAT) + cfg["W"])   # orders were working
            continue
        ft, xt, r, d = res
        busy = xt
        rows.append(dict(entry_time=pd.Timestamp(ft, unit="s"), exit_time=pd.Timestamp(xt, unit="s"), dir=d, r=r))
    return pd.DataFrame(rows, columns=["entry_time", "exit_time", "dir", "r"])


def final_test(picks: dict, tag: str = "straddle") -> dict:
    """ONE run on Jul-Oct 2026. Saves results/telegram_news/<tag>_test.json, refuses a second run."""
    fpath = N.OUT / f"{tag}_test.json"
    if fpath.exists():
        raise RuntimeError("final_test has already been run")
    tp = N.tradable(N.load_posts("2026-06-30", N.TEST[1]))
    res = {}
    for inst, cfg in picks.items():
        feat = features(tp, inst)
        t, ts = run(feat, inst, cfg), run(feat, inst, cfg, stress=True)
        m, ms = N.metrics(t, *N.TEST), N.metrics(ts, *N.TEST)
        ok = m["n"] >= 20 and m["R"] > 0 and m["pf"] >= 1.3 and m["dd"] > -0.35
        res[inst] = dict(cfg=cfg, test=m, test_stress=ms, success=ok,
                         trades=t[(t.entry_time >= N.TEST[0]) & (t.entry_time < N.TEST[1])].astype(str).to_dict("records"))
    fpath.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), results=res),
                                indent=1, default=str))
    return res
