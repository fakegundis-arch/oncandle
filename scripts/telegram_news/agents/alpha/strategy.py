"""alpha: Telegram headline bot (FinancialJuice + Walter Bloomberg) for gold / Nasdaq.

backtest(params, data_dir, start, end, stress=False) -> one row per trade signal whose entry is in [start, end).
Everything (posts, prices, fills, exits) goes through common.py; this file only decides WHICH posts to trade, in which
direction, and with which stop / target / timer.  Signals use only posts already published and price bars of seconds
before the decision second.  One position per instrument at a time (a signal is skipped while the previous trade on
that instrument is still open), so common.account's 30 % open-risk cap is never the binding limit.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))
import common as C  # noqa: E402
import feats as FE  # noqa: E402
from lib import clean, known_price, minute_vol, mid_last  # noqa: E402

# Frozen 2026-11-07.  All three are gold-only; stops are multiples of the 60-minute mean |1-minute change| ("vol")
# measured before the post.  See alpha's report (REPORT.md text was handed back to the lead; writing .md files was
# blocked for this agent): none of them beats the luck check or the May-Jun check, so none is a real edge.
CANDIDATES: dict = {
    # 1. search winner (highest search-period $ under the robustness filter): sell gold 30 s after a 🚨 Iran headline
    "iran_siren_short": {"legs": [{"inst": "gold", "filter": "siren&iran", "rule": {"kind": "sell"}, "delay": 30,
                                   "stop": 3.0, "tp": None, "hold": 3600}]},
    # 2. most month-consistent search result: fade the 10-s move into a burst of posts in the European morning
    "eu_burst_fade": {"legs": [{"inst": "gold", "filter": "burst&eu", "rule": {"kind": "fade", "a": -10, "th": 0.5},
                                "delay": 0, "stop": 6.0, "tp": None, "hold": 3600}]},
    # 3. best of the 'market had not moved yet' family: urgent headline, quiet minute before it, follow the 2->30 s reaction
    "urgent_first_follow": {"legs": [{"inst": "gold", "filter": "urg3",
                                      "rule": {"kind": "react", "o1": 2, "o2": 30, "th": 1.0, "quiet": 1.0, "mode": "mom"},
                                      "delay": 30, "stop": 6.0, "tp": 4.0, "hold": 3600}]},
}


# ------------------------------------------------------------------ signal pieces (same definitions as the search)
def atoms(F: pd.DataFrame) -> dict:
    a = {"all": np.ones(len(F), bool)}
    for c in ["wb", "excl", "brk", "siren", "star", "macro", "first", "sim_other", "num", "pct"]:
        a[c] = F[c].to_numpy()
    a["fj"] = ~F.wb.to_numpy(); a["nonmacro"] = ~F.macro.to_numpy(); a["caps"] = (F.caps >= 0.7).to_numpy()
    a["follow"] = ~F["first"].to_numpy(); a["burst"] = (F.nprev60 >= 2).to_numpy(); a["quiet"] = (F.nprev300 == 0).to_numpy()
    a["long"] = (F.len >= 100).to_numpy(); a["short"] = (F.len < 60).to_numpy()
    a["cal_near"] = (F.cal_since <= 900).to_numpy(); a["cal_far"] = ((F.cal_since > 3600) & (F.cal_until > 3600)).to_numpy()
    h = F.hour.to_numpy()
    a["asia"] = h <= 6; a["eu"] = (h >= 7) & (h <= 12); a["us"] = (h >= 13) & (h <= 20); a["late"] = h >= 21
    for c in F.columns:
        if c.startswith("kw_"):
            a[c[3:]] = F[c].to_numpy()
    a["urg3"] = a["siren"] | a["brk"] | a["excl"]          # 🚨 / ‼ / BREAKING / ⚠ / ❗ headlines
    return a


def filter_mask(F, expr: str) -> np.ndarray:
    a = atoms(F)
    m = np.ones(len(F), bool)
    for part in expr.split("&"):
        neg = part.startswith("!")
        x = a[part[1:] if neg else part]
        m &= ~x if neg else x
    return m


def direction(rule: dict, P: dict, vol: np.ndarray) -> np.ndarray:
    """P: known prices {offset: array} (offset relative to post time; 'o' = last bar before the decision second)."""
    kind = rule["kind"]
    n = len(vol)
    if kind == "buy":
        return np.ones(n, int)
    if kind == "sell":
        return -np.ones(n, int)
    if kind == "react":            # quiet minute before the post, then follow the reaction o1 -> o2 seconds after it
        quiet = np.abs((P[0] - P[-60]) / vol) < rule["quiet"]
        rx = (P[rule["o2"]] - P[rule["o1"]]) / vol
        rx = np.where(np.isfinite(rx), rx, 0.0)
        m = (np.abs(rx) >= rule["th"]) * np.sign(rx) * quiet
        return (m if rule.get("mode", "mom") == "mom" else -m).astype(int)
    pre = (P["o"] - P[rule["a"]]) / vol
    pre = np.where(np.isfinite(pre), pre, 0.0)
    m = (np.abs(pre) >= rule["th"]) * np.sign(pre)
    return (m if kind == "mom" else -m).astype(int)


# ------------------------------------------------------------------ backtest
def backtest(params: dict, data_dir: str, start, end, stress: bool = False) -> pd.DataFrame:
    t0 = int(pd.Timestamp(start, tz="UTC").timestamp()) if not isinstance(start, (int, np.integer)) else int(start)
    t1 = int(pd.Timestamp(end, tz="UTC").timestamp()) if not isinstance(end, (int, np.integer)) else int(end)
    posts = C.load_posts(data_dir)
    posts = posts[posts.ts < t1].reset_index(drop=True)          # look-back allowed, nothing after the end
    p = posts[["ts", "ch", "id"]].copy()
    p["clean"] = posts.text.map(clean)
    F = FE.build(p, C.load_calendar(data_dir))
    rows = []
    for leg in params["legs"]:
        inst = leg["inst"]
        tk = C.load_ticks(inst, data_dir)
        T = tk["t"]; px = mid_last(tk)
        ts = p.ts.to_numpy(np.int64)
        sel = (ts + C.LAT + leg["delay"] >= t0 - 4 * 3600) & filter_mask(F, leg["filter"])
        idx = np.flatnonzero(sel)
        tsi = ts[idx]
        v = minute_vol(T, px, tsi, 60)
        v = np.where(np.isfinite(v), v, minute_vol(T, px, tsi, 240))
        o = {0: 2, 10: 12, 30: 30}.get(leg["delay"], 2 + leg["delay"])
        P = {"o": known_price(T, px, tsi + o)}
        if leg["rule"]["kind"] in ("mom", "fade"):
            P[leg["rule"]["a"]] = known_price(T, px, tsi + leg["rule"]["a"])
        if leg["rule"]["kind"] == "react":
            for off in {0, -60, leg["rule"]["o1"], leg["rule"]["o2"]}:
                assert off < C.LAT + leg["delay"]                  # only seconds before the decision second
                P[off] = known_price(T, px, tsi + off)
        d = direction(leg["rule"], P, v)
        last_exit = -1
        for k, i in enumerate(idx):
            if d[k] == 0 or not np.isfinite(v[k]):
                continue
            m = C.market_entry(tk, int(ts[i]), int(d[k]), delay=leg["delay"], stress=stress)
            if m is None:
                continue
            j, fill = m
            ets = int(T[j])
            if ets < last_exit:
                continue                                         # previous trade on this instrument still open
            kx, r, sd = C.exit_trade(tk, j, fill, int(d[k]), float(leg["stop"] * v[k]), tp_r=leg.get("tp"),
                                     max_hold_s=leg.get("hold"), be_at_r=leg.get("be"), trail_r=leg.get("trail"),
                                     stress=stress)
            xts = int(T[kx])
            last_exit = xts
            if t0 <= ets < t1:
                rows.append((inst, int(ts[i]), ets, xts, int(d[k]), float(r), float(sd)))
    out = pd.DataFrame(rows, columns=["inst", "post_ts", "entry_ts", "exit_ts", "dir", "r", "sd"])
    return out.sort_values(["entry_ts", "inst"]).reset_index(drop=True)
