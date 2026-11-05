"""Entry-idea families for the Nasdaq v2 study, evaluated on the releases (pass rules) and on placebo times.

P (dict) keys used by all families:
  fam        'news' | 'mom' | 'fade' | 'brk' | 'strad' | 'pull' | 'always'
  stop_k     stop = stop_k x ATR(24 x H1)       (or stop='range' -> other side of the range + buffer)
  tp_r       target in R (0 = none)
  hold       time exit, minutes after the entry  (or exit_h = clock hour UTC, e.g. 7.0)
  trail, be, be_lock   trailing stop / break-even in R
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

import common as C
import sim as S
from sim import Cl, H, Lo, O, TI, run_trade

MAP = {"AUD": 1, "NZD": 1, "JPY": -1, "CNY": 1}
COST = C.COST


def _ct(P, i, ctx, mult=1.0):
    """spread for an entry in bar i (2x within 5 minutes of the release minute)."""
    nm = P.get("news_mult", 2.0)
    return COST * mult * (nm if TI[i] - ctx["tm"] <= P.get("news_window", 5) else 1.0)


def _exit_tm(P, i_entry, ctx):
    if P.get("exit_h") is not None:
        # next occurrence of the clock hour after the entry
        t = pd.Timestamp(np.datetime64(int(TI[i_entry]), "m"))
        x = t.normalize() + pd.Timedelta(hours=float(P["exit_h"]))
        if x <= t:
            x += pd.Timedelta(days=1)
        return S.tmin(x)
    return int(TI[i_entry]) + int(P.get("hold", 360))


def ib(ctx, minutes):
    """first bar at or after release + minutes"""
    return S.i_at(ctx["tm"] + int(minutes))


def _market(P, ctx, i, d, sd, mult, want=None):
    """market entry at the open of bar i; `want` = planned minute (skip if the market does not quote within 2 min)"""
    if i >= S.NB:
        return None
    if want is not None and TI[i] - want > 2:
        return None
    ct = _ct(P, i, ctx, mult)
    fill = O[i] + ct if d > 0 else O[i]
    return dict(i=i, fill=fill, d=d, sd=sd, ct=ct)


def _stop_entry(P, ctx, a, b, lvl_up, lvl_dn, sd_up, sd_dn, mult, late, slip_k=1.0):
    """OCO stop orders: buy stop at lvl_up / sell stop at lvl_dn, active in bars a..b-1. Returns entry list (1 entry,
    or the worse of two when both trigger in one bar: handled by returning both with flag)."""
    for j in range(a, min(b, S.NB)):
        ct = _ct(P, j, ctx, mult)
        slip = slip_k * COST * mult if TI[j] - ctx["tm"] <= P.get("news_window", 5) else 0.0
        up = lvl_up is not None and H[j] + ct >= lvl_up
        dn = lvl_dn is not None and Lo[j] <= lvl_dn
        if not (up or dn):
            continue
        out = []
        if late:
            k = S.i_at(int(TI[j]) + late)
            if k >= S.NB:
                return None
            if up:
                out.append(_market(P, ctx, k, 1, sd_up, mult))
            if dn:
                out.append(_market(P, ctx, k, -1, sd_dn, mult))
            return [x for x in out if x]
        if up:
            out.append(dict(i=j, fill=max(lvl_up, O[j] + ct) + slip, d=1, sd=sd_up, ct=ct))
        if dn:
            out.append(dict(i=j, fill=min(lvl_dn, O[j]) - slip, d=-1, sd=sd_dn, ct=ct))
        return out
    return None


def entries(P: dict, ctx: dict, info: dict | None, mult=1.0, late=0):
    """-> list of candidate entries (normally one; two = OCO both triggered in one bar -> take the worse)."""
    fam = P["fam"]
    i0, pre, a = ctx["i0"], ctx["pre"], ctx["atr"]
    if not a > 0:
        return None
    if fam not in ("news", "always") and not ctx["q0"]:
        return None                      # price-led entries need the market quoting at the release
    if P.get("ccys") and info is not None and info.get("ccy") is not None and info["ccy"] not in P["ccys"]:
        return None
    sd = P.get("stop_k", 1.0) * a
    if fam == "news":
        if info is None:
            return None
        d = info["nd"]
        if d == 0 or info.get("absscore", 9) < P.get("min_score", 1) or (P.get("agree") and not info.get("agree")):
            return None
        want = ctx["tm"] + P["delay"] + late
        i = S.i_at(want)
        if P.get("confirm"):             # Nasdaq's move from the pre-release close to the decision open must agree
            if not ctx["q0"]:
                return None
            mv = O[ib(ctx, P["delay"])] - pre
            if mv * d <= P.get("confirm_k", 0.0) * a:
                return None
        e = _market(P, ctx, i, d, sd, mult, want)
        return [e] if e else None
    if fam in ("mom", "fade"):
        N = P["N"]
        i = ib(ctx, N)
        if TI[i] - ctx["tm"] > N + 2:
            return None
        mv = O[i] - pre if P.get("ref", "pre") == "pre" else O[i] - O[i0]
        if abs(mv) < P.get("k", 0.0) * a or mv == 0:
            return None
        d = int(np.sign(mv)) * (1 if fam == "mom" else -1)
        if P.get("news_agree") and info is not None:
            if info["nd"] == 0 or info["nd"] != d * (1 if fam == "mom" else 1):
                return None
        e = _market(P, ctx, S.i_at(ctx["tm"] + N + late), d, sd, mult, ctx["tm"] + N + late)
        return [e] if e else None
    if fam == "brk":                     # breakout of the first N minutes' range (bars i0 .. i0+N-1)
        N, W = P["N"], P.get("W", 60)
        iN = ib(ctx, N)
        hi, lo = H[i0:iN].max(), Lo[i0:iN].min()
        if P.get("incl_pre", True):
            hi, lo = max(hi, pre), min(lo, pre)
        buf = P.get("buf", 0.0) * a
        if P.get("stop") == "range":
            rng = hi - lo + 2 * buf + COST
            sdu = sdd = max(rng, P.get("min_sd", 0.0) * a)
        else:
            sdu = sdd = sd
        return _stop_entry(P, ctx, iN, ib(ctx, N + W), hi + buf, lo - buf, sdu, sdd, mult, late)
    if fam == "strad":                   # straddle around the pre-release range (bars i0-K .. i0-1), active from i0
        K, W = P["K"], P.get("W", 30)
        iK = ib(ctx, -K)
        hi, lo = H[iK:i0].max(), Lo[iK:i0].min()
        buf = P.get("buf", 0.0) * a
        if P.get("stop") == "range":
            sdu = sdd = max(hi - lo + 2 * buf, P.get("min_sd", 0.0) * a)
        else:
            sdu = sdd = sd
        return _stop_entry(P, ctx, i0, ib(ctx, W), hi + buf, lo - buf, sdu, sdd, mult, late, P.get("slip_k", 1.0))
    if fam == "pull":                    # first move over N minutes, then a limit order at a retrace of it
        N, W, x = P["N"], P.get("W", 60), P.get("x", 0.5)
        i = ib(ctx, N)
        mv = O[i] - pre
        if abs(mv) < P.get("k", 0.0) * a or mv == 0:
            return None
        d = int(np.sign(mv))
        ext = H[i0:i].max() if d > 0 else Lo[i0:i].min()
        lvl = ext - d * x * abs(ext - pre)
        for j in range(i, min(ib(ctx, N + W), S.NB)):
            ct = _ct(P, j, ctx, mult)
            if (d > 0 and Lo[j] + ct <= lvl) or (d < 0 and H[j] >= lvl):
                if late:
                    e = _market(P, ctx, S.i_at(int(TI[j]) + late), d, sd, mult)
                    return [e] if e else None
                fill = min(lvl, O[j] + ct) if d > 0 else max(lvl, O[j])
                return [dict(i=j, fill=fill, d=d, sd=sd, ct=ct)]
        return None
    if fam == "pairdir":                 # direction from the released currency's own pair (cross-asset), entry at +N
        if info is None or info.get("ccy") not in P.get("ccys", ("AUD", "NZD", "JPY")):
            return None
        N = P["N"]
        mv = pair_move(info["ccy"], ctx["tm"], N)     # + = released currency stronger, in pair spreads
        if mv is None or abs(mv) < P.get("k", 0.0) or mv == 0:
            return None
        d = int(np.sign(mv)) * MAP[info["ccy"]]
        if P.get("nq_agree"):            # Nasdaq's own move must agree
            if (O[ib(ctx, N)] - pre) * d <= 0:
                return None
        want = ctx["tm"] + N + late
        e = _market(P, ctx, S.i_at(want), d, sd, mult, want)
        return [e] if e else None
    if fam == "always":                  # always long / short at release + delay (drift control)
        want = ctx["tm"] + P["delay"] + late
        e = _market(P, ctx, S.i_at(want), P["dir"], sd, mult, want)
        return [e] if e else None
    raise ValueError(fam)


def trade_one(P, ctx, info, mult=1.0, late=0):
    es = entries(P, ctx, info, mult, late)
    if not es:
        return None
    best = None
    for e in es:
        ex = _exit_tm(P, e["i"], ctx)
        res = run_trade(e["i"], e["fill"], e["d"], e["sd"], P.get("tp_r", 0.0), ex, e["ct"],
                        P.get("trail", 0.0), P.get("be", 0.0), P.get("be_lock", 0.0))
        if res is None:
            continue
        r, jx, why, px = res
        row = dict(t=ctx["t"], entry_time=pd.Timestamp(np.datetime64(int(TI[e["i"]]), "m")),
                   exit_time=pd.Timestamp(np.datetime64(int(TI[jx]), "m")), dir=e["d"], r=float(r), why=why)
        if best is None or row["r"] < best["r"]:
            best = row
    return best


_PAIR: dict = {}
PAIRS = {"AUD": ("AUDUSD", 1), "NZD": ("NZDUSD", 1), "JPY": ("USDJPY", -1)}


def pair_move(ccy, tm, N):
    """move of the currency's pair from the close before minute tm to the open of minute tm+N, signed so that + = the
    currency stronger, in units of the pair's protocol spread; None if the pair is not quoting."""
    sym, sg = PAIRS[ccy]
    if sym not in _PAIR:
        m = C.L.prices_train(sym)
        _PAIR[sym] = (m.index.values.astype("datetime64[m]").astype(np.int64), m.open.to_numpy(), m.close.to_numpy())
    ti, op, cl = _PAIR[sym]
    i0 = int(np.searchsorted(ti, tm))
    i = int(np.searchsorted(ti, tm + N))
    if i0 >= len(ti) or ti[i0] != tm or i >= len(ti) or ti[i] - (tm + N) > 2:
        return None
    return sg * (op[i] - cl[i0 - 1]) / C.L.COST[sym]


# ------------------------------------------------------------------------------------------------ news + placebo sets
_D: dict = {}


def news_set():
    if "news" not in _D:
        rt = C.rel_table()
        info = {}
        for r in rt.itertuples():
            info[pd.Timestamp(r.time)] = dict(ccy=r.ccy, kind=r.kind, nd=int(r.bias * MAP[r.ccy]), score=r.score,
                                              absscore=abs(r.score), agree=r.agree)
        ctxs = S.contexts(rt.time, "news")
        _D["news"] = (ctxs, info)
    return _D["news"]


def placebo_set():
    if "plc" not in _D:
        # one placebo set per release: its clock time on every weekday without a release (so the placebo has the
        # same time-of-day mix as the releases; clock times shared by several releases are counted once per release)
        rt = C.rel_table()
        days = {pd.Timestamp(t).date() for t in rt.time}
        out = []
        for t, ccy in zip(rt.time, rt.ccy):
            for c in S.contexts(C.placebo_times([t], exclude_days=days), "placebo"):
                out.append({**c, "ccy": ccy})
        _D["plc"] = out
    return _D["plc"]


def run_news(P, mult=1.0, late=0, events=None):
    """Trades on the releases in time order, one position at a time. events = (ctxs, info) to use another calendar
    (pseudo calendars of the placebo test); info is keyed by ctx["t"]."""
    ctxs, info = news_set() if events is None else events
    rows, busy = [], None
    for c in ctxs:
        if busy is not None and c["t"] <= busy:
            continue
        tr = trade_one(P, c, info.get(c["t"]), mult, late)
        if tr is None:
            continue
        if busy is not None and tr["entry_time"] <= busy:
            continue
        tr.update(ccy=info[c["t"]]["ccy"], kind=info[c["t"]]["kind"])
        rows.append(tr)
        busy = tr["exit_time"]
    return pd.DataFrame(rows)


def run_placebo(P, mult=1.0):
    rows = []
    rng = np.random.default_rng(7)
    for c in placebo_set():
        info = None
        if P["fam"] == "news":           # placebo for a news-sign rule: random direction, no filters
            info = dict(nd=int(rng.choice([-1, 1])), absscore=9, agree=1)
        elif P["fam"] == "pairdir" or P.get("ccys"):
            info = dict(ccy=c["ccy"])
        tr = trade_one(P, c, info, mult)
        if tr is not None:
            rows.append(tr)
    return pd.DataFrame(rows)


def metrics(t: pd.DataFrame, risk=0.10) -> dict:
    if len(t) == 0:
        return dict(n=0, R=0.0, pf=0.0, dd=0.0, q1=0.0, q2=0.0, win=0.0)
    t = t.sort_values("entry_time")
    r = t.r.to_numpy(float)
    eq = np.cumprod(1 + risk * r)
    gl, gw = -r[r < 0].sum(), r[r > 0].sum()
    pf = float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)
    q1 = float(t[t.entry_time < "2026-04-01"].r.sum())
    return dict(n=len(r), R=float(r.sum()), pf=pf, dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()),
                q1=q1, q2=float(r.sum() - q1), win=float((r > 0).mean()))


def evaluate(P, placebo=True, boot=2000, events=None):
    t1 = run_news(P, events=events)
    m = metrics(t1)
    m2 = metrics(run_news(P, mult=2.0, events=events))
    m3 = metrics(run_news(P, late=2, events=events))
    ok = (m["n"] >= 15 and m["pf"] >= 1.3 and m["q1"] > 0 and m["q2"] > 0 and m2["pf"] >= 1.15 and m3["pf"] >= 1.15
          and m["dd"] > -0.35)
    out = dict(n=m["n"], R=round(m["R"], 2), pf=round(m["pf"], 2), dd=round(m["dd"], 3), q1=round(m["q1"], 2),
               q2=round(m["q2"], 2), pf2x=round(m2["pf"], 2), pfL=round(m3["pf"], 2), win=round(m["win"], 2), ok=ok)
    if len(t1) > 2:
        r = np.sort(t1.r.to_numpy())[::-1]
        for k in (1, 2):
            rr = r[k:]
            gl = -rr[rr < 0].sum()
            out[f"pf-top{k}"] = round(rr[rr > 0].sum() / gl, 2) if gl > 0 else 99.0
    if placebo:
        pt = run_placebo(P)
        if len(pt):
            pm = metrics(pt)
            out.update(pl_n=len(pt), pl_avgR=round(pt.r.mean(), 3), pl_pf=round(pm["pf"], 2))
            if len(t1):
                rng = np.random.default_rng(1)
                pr = pt.r.to_numpy()
                bs = rng.choice(pr, (boot, len(t1))).mean(1)
                out["avgR"] = round(t1.r.mean(), 3)
                out["p_plc"] = round(float((bs >= t1.r.mean()).mean()), 3)
    return out, t1
