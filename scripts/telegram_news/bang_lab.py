"""FinancialJuice ❗ headlines only: straddle vs direct market order, gold and Nasdaq.  PROTOCOL (fixed before any
result, Nov 7 2026), the user's design.

TRIGGERS
  * @financialjuice posts that carry the ❗ emoji and do NOT contain "$MACRO" (FJ's tag for scheduled data releases).
    The first ❗ post of a story only (no ❗ post sharing >= 3 distinctive words, >= 50 % of the smaller set, in the
    previous 20 minutes).  Knob cal: "excl" = skip posts from 2 min before to 15 min after a high / medium calendar
    event (60 min after the start of a speech / press conference); "incl" = keep them.  Knob topics: ANY (every
    trigger), GEO+ENERGY, FED, TRADE+POLITICS+CHINA (newsbot_lab topic lists).
ENTRY TYPES (the bot reads the post 2 s after it appears; stress test: 5 s, and 2 spreads of slippage instead of 1)
  * STRADDLE: buy stop `dist` above and sell stop `dist` below the mid (each >= half a spread outside bid / ask), live W
    seconds, one cancels the other; fill at the level or worse + 1 spread; the worse leg when both trigger in one
    second.  Stop = at the other order (opp, 2 x dist) / back at the start (mid, 1 x dist) / half (0.5 x dist).
  * DIRECT: one market order at once (long at the ask, short at the bid, + 1 spread), direction from newsbot_lab:
    MOM (sign of the mid move from L s before the post to the entry, |move| >= k x vol), FADE (the opposite), LEX
    (headline words), LEXMOM (words, only if MOM L=30 k=0 agrees).  Stop = a fixed distance (gold $, Nasdaq points).
  * Both: target r x stop (gold r = 0 means none); gold: time exit H s after the fill; Nasdaq: exit ONLY at stop or
    target.  Always flat at the last price before the daily break / weekend (>= 10-minute pause in quotes).  Stops at
    least 3 spreads.  One position per instrument at a time.  $1,000, 10 % risk per trade.
GRIDS (Jan-Jun 2026 only)
  * gold straddle: dist $ {3, 4, 5, 6, 8}, W {30, 60, 120}, stop {opp, mid}, r {0, 1, 2, 3}, H {300, 900, 1800},
    topics x 4, cal x 2  (2,880)
  * gold direct: 20 directions (MOM / FADE with L {10, 30, 60} x k {0, 0.5, 1}, LEX, LEXMOM), stop $ {5, 10},
    r {0, 1, 2, 3}, H {300, 900, 1800}, topics x 4, cal x 2  (3,840)
  * Nasdaq straddle: dist pts {20, 30, 40, 50, 60}, W {60, 120, 300}, stop {opp, mid, half}, r {1, 2, 3}, TP / SL only,
    topics x 4, cal x 2  (1,080)
  * Nasdaq direct: 20 directions, stop pts {40, 80}, r {1, 2, 3}, TP / SL only, topics x 4, cal x 2  (960)
USER'S FIXED SETTINGS (reported on both periods, not picked from these grids; topics ANY, cal excl):
  * gold straddle  : $5, orders live 60 s, stop at the other order, 2R, out after 30 min
  * gold direct    : MOM L=30 k=0, stop $10 (= the straddle's width), 2R, out after 30 min
  * Nasdaq straddle: 40 pts, orders live 120 s, stop at the other order, 3R, TP / SL only
  * Nasdaq direct  : MOM L=30 k=0, stop 80 pts, 3R, TP / SL only
RULES (per group): Jan-Jun pass = >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, stress PF >= 1.15, max
drawdown at 10 % better than -35 %.  Pick = most passing neighbours (one knob one step), then shallower drawdown, then
higher R; if none passes, the group's highest-R setting gets one information-only run.  TEST once on Jul 1 - Oct 31
2026: success = >= 20 trades, R > 0, PF >= 1.3, drawdown better than -35 %.  (Jul-Oct has been the test period of the
earlier news bots; no ❗-only setting has been run on it.)
"""
from __future__ import annotations

import itertools
import json
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import newsbot_lab as N
import straddle_lab as S
import straddle_tpsl_lab as L

BUILD = ("2026-01-01", "2026-07-01")
HALVES = {"jan-mar": ("2026-01-01", "2026-04-01"), "apr-jun": ("2026-04-01", "2026-07-01")}
TEST = ("2026-07-01", "2026-11-01")
TOPICS = {"ANY": None, "GEO+ENERGY": ["GEO", "ENERGY"], "FED": ["FED"], "TRADE+POLITICS+CHINA": ["TRADE", "POLITICS", "CHINA"]}
DIRS = [dict(fam=f, L=l, k=k) for f in ("MOM", "FADE") for l in (10, 30, 60) for k in (0.0, 0.5, 1.0)] + \
       [dict(fam="LEX", L=30, k=0.0), dict(fam="LEXMOM", L=30, k=0.0)]
COMMON = dict(topics=list(TOPICS), cal=["excl", "incl"])
GRIDS = {
    ("gold", "straddle"): dict(dist=[3, 4, 5, 6, 8], W=[30, 60, 120], stop=["opp", "mid"], r=[0, 1, 2, 3],
                               H=[300, 900, 1800], **COMMON),
    ("gold", "direct"): dict(dir=list(range(len(DIRS))), stop_abs=[5, 10], r=[0, 1, 2, 3], H=[300, 900, 1800], **COMMON),
    ("nasdaq", "straddle"): dict(dist=[20, 30, 40, 50, 60], W=[60, 120, 300], stop=["opp", "mid", "half"], r=[1, 2, 3],
                                 H=[None], **COMMON),
    ("nasdaq", "direct"): dict(dir=list(range(len(DIRS))), stop_abs=[40, 80], r=[1, 2, 3], H=[None], **COMMON),
}
USER = {
    ("gold", "straddle"): dict(dist=5, W=60, stop="opp", r=2, H=1800, topics="ANY", cal="excl"),
    ("gold", "direct"): dict(dir=DIRS.index(dict(fam="MOM", L=30, k=0.0)), stop_abs=10, r=2, H=1800, topics="ANY", cal="excl"),
    ("nasdaq", "straddle"): dict(dist=40, W=120, stop="opp", r=3, H=None, topics="ANY", cal="excl"),
    ("nasdaq", "direct"): dict(dir=DIRS.index(dict(fam="MOM", L=30, k=0.0)), stop_abs=80, r=3, H=None, topics="ANY", cal="excl"),
}
STOP_X = {"opp": 2.0, "mid": 1.0, "half": 0.5}


def configs(group) -> list[dict]:
    g = GRIDS[group]
    return [dict(zip(g, c)) for c in itertools.product(*g.values())]


# ------------------------------------------------------------------------------------------------------- triggers
def triggers(a: str, b: str) -> pd.DataFrame:
    p = N.load_posts(a, b)
    p = p[(p.ch == "FJ") & p.text.str.contains("❗", regex=False) & ~p.text.str.contains("$MACRO", regex=False)]
    p = p.reset_index(drop=True)
    sched, after = N.scheduled_times()
    ts = p.t.values.astype("datetime64[s]").astype(np.int64)
    keep, recent, cal = [], [], []
    for i, q in enumerate(p.itertuples()):
        t = ts[i]
        recent = [(tt, tok) for tt, tok in recent if t - tt <= 1200]
        dup = any(len(q.tok & tok) >= 3 and len(q.tok & tok) / max(1, min(len(q.tok), len(tok))) >= 0.5 for _, tok in recent)
        recent.append((t, q.tok))
        if dup:
            continue
        j = np.searchsorted(sched, t)
        lo = max(0, j - 40)
        cal.append(any(-120 <= t - s <= w for s, w in zip(sched[lo: j + 3], after[lo: j + 3])))
        keep.append(i)
    out = p.iloc[keep].copy()
    out["in_cal"] = cal
    out["topics"] = out.clean.map(N.topics_of)
    out["lex_gold"], out["lex_nasdaq"] = zip(*out.clean.map(N.lex_dir)) if len(out) else ([], [])
    return out.reset_index(drop=True)


def features(tr: pd.DataFrame, inst: str) -> pd.DataFrame:
    tk = N.ticks(inst)
    rows = []
    for p in tr.itertuples():
        t0 = int(p.t.timestamp())
        me = N.mid_at(tk, t0 + N.LAT)
        rec = dict(t_post=t0, topics=p.topics, in_cal=p.in_cal, vol=N.vol60(tk, t0),
                   lex=p.lex_gold if inst == "gold" else p.lex_nasdaq)
        for l in (10, 30, 60):
            rec[f"mv{l}"] = me - N.mid_at(tk, t0 - l)
        rows.append(rec)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------------- engines
def _exit(tk, j, fill, d, sd, r, H, end):
    if H is None:
        return L.exit_tpsl(tk, j, fill, d, sd, r, end)
    return S._exit(tk, j, fill, d, sd, r, H, end)


def straddle(tk, f, c, stress):
    T = tk["t"]
    tpl = f.t_post + (N.LAT_STRESS if stress else N.LAT)
    slip_k = 2.0 if stress else 1.0
    i = np.searchsorted(T, tpl)
    if i >= len(T) or T[i] - tpl > 10:
        return None
    bid, ask = tk["bid_first"][i], tk["ask_first"][i]
    sp = ask - bid
    mid = 0.5 * (bid + ask)
    up, dn = max(mid + c["dist"], ask + 0.5 * sp), min(mid - c["dist"], bid - 0.5 * sp)
    end = L.next_close(tk, i)
    w_end = min(np.searchsorted(T, T[i] + c["W"]), end + 1)
    hu, hd = tk["ask_max"][i + 1: w_end] >= up, tk["bid_min"][i + 1: w_end] <= dn
    hit = hu | hd
    if not hit.any():
        return None
    k = int(np.argmax(hit))
    j = i + 1 + k
    af, bf = tk["ask_first"][j], tk["bid_first"][j]
    legs = ([(1, max(up, af))] if hu[k] else []) + ([(-1, min(dn, bf))] if hd[k] else [])
    out = None
    for d, px in legs:
        fill = px + d * slip_k * (af - bf)
        sd = max(STOP_X[c["stop"]] * c["dist"], 3 * (af - bf))
        kx, r = _exit(tk, j, fill, d, sd, c["r"], c["H"], end)
        if out is None or r < out[2]:
            out = (int(T[j]), int(T[kx]), float(r), d)
    return out


def direct(tk, f, c, stress):
    dcfg = DIRS[c["dir"]]
    d = N.direction(f, dcfg) if np.isfinite(f.vol) and f.vol > 0 else 0
    if d == 0:
        return None
    T = tk["t"]
    te = f.t_post + (N.LAT_STRESS if stress else N.LAT)
    slip_k = 2.0 if stress else 1.0
    i = np.searchsorted(T, te)
    if i >= len(T) or T[i] - te > 10:
        return None
    af, bf = tk["ask_first"][i], tk["bid_first"][i]
    fill = (af if d > 0 else bf) + d * slip_k * (af - bf)
    sd = max(c["stop_abs"], 3 * (af - bf))
    end = L.next_close(tk, i)
    kx, r = _exit(tk, i, fill, d, sd, c["r"], c["H"], end)
    return int(T[i]), int(T[kx]), float(r), d


def run(feat: pd.DataFrame, inst: str, kind: str, c: dict, stress: bool = False) -> pd.DataFrame:
    tk = N.ticks(inst)
    allowed = TOPICS[c["topics"]]
    fn = straddle if kind == "straddle" else direct
    rows, busy = [], -1
    for f in feat.itertuples():
        if f.t_post <= busy or (c["cal"] == "excl" and f.in_cal):
            continue
        if allowed is not None and not (set(f.topics) & set(allowed)):
            continue
        res = fn(tk, f, c, stress)
        if res is None:
            if kind == "straddle":
                busy = max(busy, f.t_post + (N.LAT_STRESS if stress else N.LAT) + c["W"])
            continue
        ft, xt, r, d = res
        busy = xt
        rows.append(dict(entry_time=pd.Timestamp(ft, unit="s"), exit_time=pd.Timestamp(xt, unit="s"), dir=d, r=r))
    return pd.DataFrame(rows, columns=["entry_time", "exit_time", "dir", "r"])


def passes_build(t, ts):
    m = N.metrics(t, *BUILD)
    h1, h2 = N.metrics(t, *HALVES["jan-mar"]), N.metrics(t, *HALVES["apr-jun"])
    ms = N.metrics(ts, *BUILD)
    chk = {"n>=40": m["n"] >= 40, "pf>=1.3": m["pf"] >= 1.3, "jan-mar R>0": h1["R"] > 0, "apr-jun R>0": h2["R"] > 0,
           "stress pf>=1.15": ms["pf"] >= 1.15, "dd>-35%": m["dd"] > -0.35}
    return all(chk.values()), dict(m, h1R=h1["R"], h2R=h2["R"], stress_pf=ms["pf"], stress_R=ms["R"], **chk)


def describe(group, c) -> str:
    inst, kind = group
    unit = "$" if inst == "gold" else "pts "
    tail = f"{c['r']}R target" if c["r"] else "no target"
    tail += f", out after {c['H'] // 60} min" if c["H"] else ", TP / SL only"
    tail += f", topics {c['topics']}, calendar {c['cal']}"
    if kind == "straddle":
        return f"straddle {unit}{c['dist']} each side, orders {c['W']} s, stop {c['stop']}, {tail}"
    dd = DIRS[c["dir"]]
    dname = dd["fam"] + (f" L{dd['L']} k{dd['k']}" if dd["fam"] in ("MOM", "FADE") else "")
    return f"direct {dname}, stop {unit}{c['stop_abs']}, {tail}"


def final_test(entries: dict, tag: str = "bang") -> dict:
    """ONE run on Jul-Oct 2026: entries = {name: (inst, kind, cfg)}. Saves results/telegram_news/<tag>_test.json."""
    fpath = N.OUT / f"{tag}_test.json"
    if fpath.exists():
        raise RuntimeError("final_test has already been run")
    tr = triggers("2026-06-30", TEST[1])
    feats = {inst: features(tr, inst) for inst in N.SYMS}
    res = {}
    for name, (inst, kind, c) in entries.items():
        t, ts = run(feats[inst], inst, kind, c), run(feats[inst], inst, kind, c, stress=True)
        m, ms = N.metrics(t, *TEST), N.metrics(ts, *TEST)
        ok = m["n"] >= 20 and m["R"] > 0 and m["pf"] >= 1.3 and m["dd"] > -0.35
        res[name] = dict(inst=inst, kind=kind, cfg=c, desc=describe((inst, kind), c), test=m, test_stress=ms, success=ok,
                         trades=t[(t.entry_time >= TEST[0]) & (t.entry_time < TEST[1])].astype(str).to_dict("records"))
    fpath.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), results=res),
                                indent=1, default=str))
    return res
