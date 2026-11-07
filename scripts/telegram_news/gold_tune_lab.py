"""Gold on FinancialJuice ❗ headlines: stop / target in DOLLARS with the lot sized to risk 10 % (the user's idea,
Nov 7 2026: smaller gold moves with a bigger lot, still 10 % risk).  PROTOCOL (fixed before any result) and engine.

  * Lot = 10 % of the balance / (stop $ x 100 oz).  A trade's result in R = profit / stop distance, so the dollar
    result at 10 % risk is 10 % of the balance x R whatever the stop size.
  * Triggers (knob trig): "story" = the first ❗ post of a story (no $MACRO), outside calendar windows (bang_lab.triggers);
    "every" = every ❗ post without $MACRO (bang_multi.every_trigger).  Topics knob: ANY, GEO+ENERGY.
  * Entries (knob entry): direct market orders - MOM L10 k0, MOM L30 k0, MOM L60 k0, MOM L30 k0.5, MOM L30 k1,
    FADE L30 k0, LEXMOM (bang_lab / newsbot_lab directions) - and straddles: buy stop / sell stop $3, $5 or $8 from the
    price, live 60 or 120 s, one cancels the other.  +1 spread on every fill; stress: read 5 s late, +2 spreads on the
    entry AND 1 more spread lost on the exit (small stops make exit slippage matter more); the worse leg when both
    straddle orders trigger in one second.
  * Stop $ in {3, 4, 5, 6, 8, 10, 12, 15}, target $ in {5, 7.5, 10, 12.5, 15, 20} (target R = target / stop), exit
    timer H in {300, 900, 1800 s, none = stop / target only}; always closed before the daily break / weekend; stop at
    least 3 spreads.  ONE position at a time (the multiple-position versions lost with every target).
  * 13 entries x 8 stops x 6 targets x 4 exits x 2 trigger sets x 2 topic sets = 9,984 settings.
  * BUILD Jan-Jun 2026.  Pass: >= 40 trades, PF >= 1.3, R > 0 in Jan-Mar and in Apr-Jun, stress PF >= 1.15, max
    drawdown at 10 % better than -35 %.  Pick: most passing neighbours (stop / target / exit one step), then shallower
    drawdown, then higher R; none passing -> the highest-R setting gets an information-only run.
  * TEST once on Jul 1 - Oct 31 2026.  Success: >= 20 trades, R > 0, PF >= 1.3, drawdown better than -35 %.  Caveat
    stated in advance: Jul-Oct has already been used for nearby ❗ settings (FJ uses ❗ only from Feb 2026, so no
    untouched earlier period exists).
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import bang_lab as B
import bang_multi as M
import newsbot_lab as N
import straddle_tpsl_lab as L

BUILD, TEST = B.BUILD, B.TEST
DIRECT = [dict(fam="MOM", L=10, k=0.0), dict(fam="MOM", L=30, k=0.0), dict(fam="MOM", L=60, k=0.0),
          dict(fam="MOM", L=30, k=0.5), dict(fam="MOM", L=30, k=1.0), dict(fam="FADE", L=30, k=0.0),
          dict(fam="LEXMOM", L=30, k=0.0)]
STRADDLE = [dict(dist=d, W=w) for d in (3, 5, 8) for w in (60, 120)]
ENTRIES = [("direct", d) for d in DIRECT] + [("straddle", s) for s in STRADDLE]
GRID = dict(entry=list(range(len(ENTRIES))), stop=[3, 4, 5, 6, 8, 10, 12, 15], target=[5, 7.5, 10, 12.5, 15, 20],
            H=[300, 900, 1800, None], trig=["story", "every"], topics=["ANY", "GEO+ENERGY"])
KNOBS = list(GRID)


def configs():
    return [dict(zip(GRID, c)) for c in itertools.product(*GRID.values())]


def trigger_sets(a, b):
    return {"story": B.triggers(a, b), "every": M.every_trigger(a, b)}


def _straddle(tk, f, e, c, stress):
    T = tk["t"]
    tpl = f.t_post + (N.LAT_STRESS if stress else N.LAT)
    slip_k = 2.0 if stress else 1.0
    i = np.searchsorted(T, tpl)
    if i >= len(T) or T[i] - tpl > 10:
        return None
    bid, ask = tk["bid_first"][i], tk["ask_first"][i]
    sp = ask - bid
    mid = 0.5 * (bid + ask)
    up, dn = max(mid + e["dist"], ask + 0.5 * sp), min(mid - e["dist"], bid - 0.5 * sp)
    end = L.next_close(tk, i)
    w_end = min(np.searchsorted(T, T[i] + e["W"]), end + 1)
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
        sd = max(c["stop"], 3 * (af - bf))
        kx, r = B._exit(tk, j, fill, d, sd, c["target"] / c["stop"], c["H"], end)
        if out is None or r < out[2]:
            out = (int(T[j]), int(T[kx]), float(r), d)
    return out


def run(feat: pd.DataFrame, c: dict, stress: bool = False) -> pd.DataFrame:
    tk = N.ticks("gold")
    kind, e = ENTRIES[c["entry"]]
    allowed = B.TOPICS[c["topics"]]
    rows, busy = [], -1
    for f in feat.itertuples():
        if f.t_post <= busy or f.in_cal:
            continue
        if allowed is not None and not (set(f.topics) & set(allowed)):
            continue
        if kind == "direct":
            dc = dict(dir=B.DIRS.index(e), stop_abs=c["stop"], r=c["target"] / c["stop"], H=c["H"])
            res = B.direct(tk, f, dc, stress)
        else:
            res = _straddle(tk, f, e, c, stress)
            if res is None:
                busy = max(busy, f.t_post + (N.LAT_STRESS if stress else N.LAT) + e["W"])
                continue
        if res is None:
            continue
        ft, xt, r, d = res
        busy = xt
        if stress:                                   # one extra spread lost on the exit
            j = min(np.searchsorted(tk["t"], ft), len(tk["t"]) - 1)
            sp = tk["ask_first"][j] - tk["bid_first"][j]
            r -= sp / max(c["stop"], 3 * sp)
        rows.append(dict(entry_time=pd.Timestamp(ft, unit="s"), exit_time=pd.Timestamp(xt, unit="s"), dir=d, r=r))
    return pd.DataFrame(rows, columns=["entry_time", "exit_time", "dir", "r"])


def describe(c) -> str:
    kind, e = ENTRIES[c["entry"]]
    if kind == "direct":
        ent = f"direct {e['fam']}" + (f" L{e['L']} k{e['k']}" if e["fam"] != "LEXMOM" else "")
    else:
        ent = f"straddle ${e['dist']} live {e['W']} s"
    ex = f"out after {c['H'] // 60} min" if c["H"] else "stop / target only"
    return (f"{ent}, stop ${c['stop']}, target ${c['target']} ({c['target'] / c['stop']:.2f}R), {ex}, "
            f"triggers {c['trig']}, topics {c['topics']}")


def final_test(entries: dict, tag: str = "gold_tune") -> dict:
    fpath = N.OUT / f"{tag}_test.json"
    if fpath.exists():
        raise RuntimeError("final_test has already been run")
    feats = {k: B.features(v, "gold") for k, v in trigger_sets("2026-06-30", TEST[1]).items()}
    res = {}
    for name, c in entries.items():
        f = feats[c["trig"]]
        t, ts = run(f, c), run(f, c, stress=True)
        m, ms = N.metrics(t, *TEST), N.metrics(ts, *TEST)
        ok = m["n"] >= 20 and m["R"] > 0 and m["pf"] >= 1.3 and m["dd"] > -0.35
        res[name] = dict(cfg=c, desc=describe(c), test=m, test_stress=ms, success=ok,
                         m2=N.metrics(t, *TEST, risk=0.02), m1=N.metrics(t, *TEST, risk=0.01),
                         trades=t[(t.entry_time >= TEST[0]) & (t.entry_time < TEST[1])].astype(str).to_dict("records"))
    fpath.write_text(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), results=res),
                                indent=1, default=str))
    return res
