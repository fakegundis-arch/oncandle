"""4newgolds Telegram gold bot - VERSION 2 search.  PROTOCOL (fixed before any version-2 result, Nov 10 2026).

BUILD on Jan 1 - May 31 2026 only; ONE run of the pick on Jun 1 - Nov 9 2026 (Exness prices end Nov 9 23:59 for gold,
Nov 8 23:59 for USTECm).  Caveats stated in advance: the original bot's Jun-Nov results were already looked at, and the
option ranges below were chosen knowing its full-year breakdown (e.g. "trump" keyword and the Nasdaq companion lost),
so the test months are not fully fresh; version 2's own settings are still chosen on Jan-May alone.

Same machinery as replay.py (the bot's own gate order, 2-s management loop, SL / TP from the real fill, OCO, cancel
window, break-even stages on wicks, trailing stop, fills at the worse of order price and first quote + 1 spread,
positions held overnight, no orders while the market is shut, one gold straddle at a time, 10-minute duplicate filter,
companion only when gold arms and only one open), re-implemented in numba and checked against replay.py.  Fixed lots
as the original bot: gold 0.01 lot ($1 per $1), USTECm 0.5 lot ($0.50 per point).  No AI review (cannot be run here);
"principal speaking" is a rule-based trigger option instead.

Options (27,648 settings):
  channels   all three | FinancialJuice | WalterBloomberg | FinancialJuice + WalterBloomberg
  trigger    v1 (keywords or ❗/🔴, as the bot) | no_trump (same keywords without "trump") | principal (headline
             starts with Trump / a Fed official / Bessent-Treasury / White House speaking, or ❗/🔴) | principal_only
             | flag_only (❗/🔴) | kw_only (keywords, no fast track)
  blackout   on (as the bot: 30 / 60 min after high-impact USD releases) | off
  gold       entry offset $2 / 3 / 5 / 8; order life 60 / 120 / 300 s; stop $3 / 6; target none / $15;
             management v1 (break-even +4.5 -> +1, +15 -> +12, trailing from +24 at 4) | none;
             time exit none / 30 min (new in version 2)
  companion  off | v1 (USTECm +/-30, SL 40, TP 40, 0.5 lot) | wide (+/-50, SL 50, TP 100, 0.5 lot)
Selection on Jan-May: pass = >= 60 positions, P&L > 0 in Jan-Mar AND in Apr-May, profit factor >= 1.3, stress profit
factor >= 1.1 (acts 5 s after the post, 2 spreads on entry, 1 more on exit), worst drawdown smaller than the total
profit.  Pick = most passing neighbours (one option one step), then the highest Jan-May P&L.  Luck check: the same grid
on fake signal times (each candidate post moved 1-14 days inside Jan-May), 3 seeds; the pick counts as better than
luck only if its Jan-May P&L beats the best fake setting that meets the same rules.  If nothing passes, the
highest-P&L setting gets an information-only test.  Test: one run on Jun 1 - Nov 9 2026, compared with the original
bot (replay.py base) on the same months; success = P&L > 0, above the original's, profit factor >= 1.2.
"""
from __future__ import annotations

import itertools
import json
import re
import sys
from pathlib import Path

import numba as nb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay as R  # noqa: E402  (the bot's code is put on sys.path by replay.py)

BUILD = ("2026-01-01", "2026-06-01")
SPLIT = "2026-04-01"
TEST = ("2026-06-01", "2026-11-10")
CHANNELS = {"all": ("FinancialJuice", "WalterBloomberg", "apewirenews"), "FJ": ("FinancialJuice",),
            "WB": ("WalterBloomberg",), "FJ+WB": ("FinancialJuice", "WalterBloomberg")}
TRIGGERS = ["v1", "no_trump", "principal", "principal_only", "flag_only", "kw_only"]
BLACKOUT = ["on", "off"]
GOLD = dict(offset=[2.0, 3.0, 5.0, 8.0], life=[60, 120, 300], sl=[3.0, 6.0], tp=[0.0, 15.0], manage=["v1", "none"],
            timer=[0, 1800])
COMP = {"off": None, "v1": dict(offset=30.0, sl=40.0, tp=40.0, lot=0.5), "wide": dict(offset=50.0, sl=50.0, tp=100.0, lot=0.5)}
V1 = dict(channels="all", trigger="v1", blackout="on", offset=5.0, life=120, sl=3.0, tp=0.0, manage="v1", timer=0, comp="v1")
GLIST = [dict(zip(GOLD, v)) for v in itertools.product(*GOLD.values())]
KNOBS = dict(channels=list(CHANNELS), trigger=TRIGGERS, blackout=BLACKOUT, **GOLD, comp=list(COMP))


# ------------------------------------------------------------------ numba lifecycle (same rules as replay.simulate)
@nb.njit(cache=True)
def _rp(x, point, digits):
    return np.round(np.round(x / point) * point, digits)


@nb.njit(cache=True)
def sim(T, bf, bl, bmin, bmax, af, al, amin, amax, point, digits, t_arm, buy_px, sell_px, sl_d, tp_d, cancel_after,
        be_tr, be_of, use_tr, tr_start, tr_dist, tr_step, hold, veto_ts, slip, exit_slip, mult):
    """one straddle -> (close ts, P&L $, filled legs)"""
    n = len(T)
    half = point / 2
    pb, ps = True, True
    side = np.zeros(2, np.int64)
    fts = np.zeros(2, np.int64)
    fill = np.zeros(2)
    sl = np.zeros(2)
    tp = np.zeros(2)
    att = np.zeros(2, np.bool_)
    best = np.zeros(2)
    ext = np.zeros(2, np.int64)
    exv = np.zeros(2)
    npos = 0
    trig = False
    i = np.searchsorted(T, t_arm, side="right")
    nxt = t_arm + 2
    closed = -1
    while i < n and closed < 0:
        b = T[i]
        while nxt <= b and closed < 0:
            j = i - 1
            if j >= 0:
                bid, ask = bl[j], al[j]
                live = 0
                for k in range(npos):
                    if ext[k] == 0:
                        live += 1
                        if not att[k]:
                            s_ = 0.0 if sl_d <= 0 else _rp(fill[k] - side[k] * sl_d, point, digits)
                            t_ = 0.0 if tp_d <= 0 else _rp(fill[k] + side[k] * tp_d, point, digits)
                            ok_s = s_ == 0.0 or (side[k] > 0 and s_ < bid - half) or (side[k] < 0 and s_ > ask + half)
                            ok_t = t_ == 0.0 or (side[k] > 0 and t_ > bid) or (side[k] < 0 and t_ < ask)
                            if ok_s and ok_t:
                                sl[k], tp[k], att[k] = s_, t_, True
                if live > 0 and not trig:
                    trig = True
                    pb, ps = False, False
                if (pb or ps) and nxt >= t_arm + cancel_after:
                    pb, ps = False, False
                if (pb or ps) and veto_ts >= 0 and nxt >= veto_ts:
                    pb, ps = False, False
                for k in range(npos):
                    if ext[k] != 0 or not att[k]:
                        continue
                    d = side[k]
                    if len(be_tr) > 0:
                        basis = max(best[k], bid) if d > 0 else min(best[k], ask)
                        profit = (basis - fill[k]) * d
                        st = -1
                        for q in range(len(be_tr)):
                            if profit + half >= be_tr[q]:
                                st = q
                        if st >= 0:
                            new = _rp(fill[k] + d * be_of[st], point, digits)
                            better = sl[k] == 0.0 or (d > 0 and new > sl[k]) or (d < 0 and new < sl[k])
                            placeable = (d > 0 and new < bid - half) or (d < 0 and new > ask + half)
                            if better and placeable:
                                sl[k] = new
                    if use_tr:
                        price = bid if d > 0 else ask
                        if (price - fill[k]) * d + half >= tr_start:
                            new = _rp(price - d * tr_dist, point, digits)
                            if sl[k] == 0.0 or (new - sl[k]) * d >= max(tr_step, point) - half:
                                sl[k] = new
                    if hold > 0 and nxt >= fts[k] + hold:
                        ext[k] = nxt
                        exv[k] = (bid - exit_slip * (ask - bid)) if d > 0 else (ask + exit_slip * (ask - bid))
                live = 0
                for k in range(npos):
                    if ext[k] == 0:
                        live += 1
                if not (pb or ps) and live == 0:
                    closed = nxt
            busy = pb or ps
            for k in range(npos):
                if ext[k] == 0 and not att[k]:
                    busy = True
            if busy:
                nxt += 2
            else:
                nxt = max(nxt + 2, b - (b - nxt) % 2)
        if closed >= 0:
            break
        sp = af[i] - bf[i]
        for k in range(npos):
            if ext[k] != 0 or not att[k]:
                continue
            d = side[k]
            if d > 0:
                first, lo, hi = bf[i], bmin[i], bmax[i]
                hs = sl[k] != 0.0 and (first <= sl[k] or lo <= sl[k])
                ht = tp[k] != 0.0 and (first >= tp[k] or hi >= tp[k])
                if hs:
                    exv[k] = (first if first <= sl[k] else sl[k]) - exit_slip * sp
                elif ht:
                    exv[k] = first if first >= tp[k] else tp[k]
            else:
                first, lo, hi = af[i], amin[i], amax[i]
                hs = sl[k] != 0.0 and (first >= sl[k] or hi >= sl[k])
                ht = tp[k] != 0.0 and (first <= tp[k] or lo <= tp[k])
                if hs:
                    exv[k] = (first if first >= sl[k] else sl[k]) + exit_slip * sp
                elif ht:
                    exv[k] = first if first <= tp[k] else tp[k]
            if hs or ht:
                ext[k] = b
        for k in range(npos):
            if ext[k] == 0 and b > fts[k]:
                best[k] = max(best[k], bmax[i]) if side[k] > 0 else min(best[k], amin[i])
        if pb and amax[i] >= buy_px:
            side[npos], fts[npos], fill[npos] = 1, b, max(buy_px, af[i]) + slip * sp
            best[npos] = fill[npos]
            npos += 1
            pb = False
        if ps and bmin[i] <= sell_px:
            side[npos], fts[npos], fill[npos] = -1, b, min(sell_px, bf[i]) - slip * sp
            best[npos] = fill[npos]
            npos += 1
            ps = False
        i += 1
    if closed < 0:
        j = n - 1
        for k in range(npos):
            if ext[k] == 0:
                ext[k] = T[j]
                exv[k] = bl[j] if side[k] > 0 else al[j]
        closed = T[j]
    pnl = 0.0
    for k in range(npos):
        pnl += (exv[k] - fill[k]) * side[k] * mult
    return closed, pnl, npos


# ------------------------------------------------------------------ candidates
PRINCIPAL = R.PRINCIPAL


def candidates(cfg, a, b, posts):
    """posts in [a, b) that pass the bot's fixed checks (forward, reply, length, blacklists) and at least one trigger."""
    mode = cfg.keyword_match
    prof = cfg.telegram_feed.profile_for(cfg.x_feed.defaults)
    et = cfg.x_feed.emoji_trigger
    kw_nt = [k for k in prof.keywords if k.lower() != "trump"]
    p = posts[(posts.t >= pd.Timestamp(a, tz="UTC")) & (posts.t < pd.Timestamp(b, tz="UTC"))]
    rows = []
    for q in p.itertuples():
        flag = R.emoji_flag(q.text, et, mode)
        ok, why = R.post_tradable(q, prof, mode, 2, keyword_bypass=True)       # everything but the trigger
        if not ok:
            continue
        kw = R.any_keyword(prof.keywords, q.text, mode)
        rows.append(dict(ts=int(q.ts), ch=q.ch, pid=int(q.id), text=q.text, flag=bool(flag), kw=kw,
                         kw_nt=R.any_keyword(kw_nt, q.text, mode), prin=PRINCIPAL.search(q.text) is not None,
                         key=R.content_key(q.text)))
    c = pd.DataFrame(rows)
    c = c[c.flag | c.kw | c.kw_nt | c.prin].reset_index(drop=True)
    c["key_id"] = pd.factorize(c.key)[0]
    return c


def trig_mask(c, trig):
    return {"v1": c.flag | c.kw, "no_trump": c.flag | c.kw_nt, "principal": c.flag | c.prin, "principal_only": c.prin,
            "flag_only": c.flag, "kw_only": c.kw}[trig].to_numpy()


def market_flags(c, gold, nas, windows, lat):
    det = c.ts.to_numpy() + lat
    shut = np.array([R.market_shut(gold, int(x)) for x in det])
    nshut = np.array([R.market_shut(nas, int(x)) or x > nas["t"][-1] for x in det])
    ws = np.array([w[0] for w in windows]); we = np.array([w[1] for w in windows])
    k = np.searchsorted(ws, det, side="right")
    blk = np.array([bool(np.any((ws[max(0, kk - 40):kk] <= x) & (we[max(0, kk - 40):kk] > x))) for x, kk in zip(det, k)])
    return det, shut, nshut, blk


def outcomes(c, det, tk, sym, prof_list, stress, comp_mode=False):
    """per candidate x per setting -> close ts, P&L"""
    s = R.SPEC[sym]
    T = tk["t"]
    lat_extra = 3 if stress else 0
    slip, exit_slip = (2.0, 1.0) if stress else (1.0, 0.0)
    m = len(c)
    close = np.zeros((m, len(prof_list)), np.int64)
    pnl = np.zeros((m, len(prof_list)))
    fills = np.zeros((m, len(prof_list)), np.int64)
    for e in range(m):
        t_arm = int(det[e]) + lat_extra
        j = int(np.searchsorted(T, t_arm, side="right")) - 1
        if j < 0 or t_arm > T[-1]:
            continue
        bid, ask = tk["bid_last"][j], tk["ask_last"][j]
        for g, pr in enumerate(prof_list):
            bp = np.round(np.round((ask + pr["offset"]) / s["point"]) * s["point"], s["digits"])
            spx = np.round(np.round((bid - pr["offset"]) / s["point"]) * s["point"], s["digits"])
            if comp_mode:
                be_tr, be_of, use_tr, tr = np.zeros(0), np.zeros(0), False, (0.0, 0.0, 0.0)
                hold, life, mult = 0, 120, pr["lot"] * s["contract"]
            else:
                v1 = pr["manage"] == "v1"
                be_tr = np.array([4.5, 15.0]) if v1 else np.zeros(0)
                be_of = np.array([1.0, 12.0]) if v1 else np.zeros(0)
                use_tr, tr = v1, (24.0, 4.0, 0.5)
                hold, life, mult = pr["timer"], pr["life"], 0.01 * s["contract"]
            cl, pl, nf = sim(T, tk["bid_first"], tk["bid_last"], tk["bid_min"], tk["bid_max"], tk["ask_first"],
                             tk["ask_last"], tk["ask_min"], tk["ask_max"], s["point"], s["digits"], t_arm, bp, spx,
                             pr["sl"], pr["tp"], life, be_tr, be_of, use_tr, tr[0], tr[1], tr[2], hold, -1, slip,
                             exit_slip, mult)
            close[e, g], pnl[e, g], fills[e, g] = cl, pl, nf
    return close, pnl, fills


# ------------------------------------------------------------------ the bot's one-at-a-time selection, per setting
@nb.njit(cache=True)
def run_setting(det, use, blk, shut, nshut, key_id, gclose, gpnl, gfill, cclose, cpnl, cfill, use_comp, blackout_on,
                split_ts, end_ts):
    """-> P&L total, gold, nasdaq, P&L before / after split, positions, gross win, gross loss, max drawdown"""
    gold_until, comp_until = -1, -1
    claimed = np.full(key_id.max() + 1 if len(key_id) else 1, -10**12, np.int64)
    tot = gp = cp = a1 = a2 = gw = gl = 0.0
    npos = 0
    eq = peak = dd = 0.0
    for e in range(len(det)):
        x = det[e]
        if not use[e] or x >= end_ts:
            continue
        if blackout_on and blk[e]:
            continue
        if x < gold_until:
            continue
        if x - claimed[key_id[e]] <= 600:
            continue
        claimed[key_id[e]] = x
        if shut[e]:
            continue
        gold_until = gclose[e]
        p = gpnl[e]
        npos += gfill[e]
        if use_comp and x >= comp_until and not nshut[e]:
            comp_until = cclose[e]
            p += cpnl[e]
            npos += cfill[e]
            cp += cpnl[e]
        gp += gpnl[e]
        if p != 0.0:
            tot += p
            if x < split_ts:
                a1 += p
            else:
                a2 += p
            if p > 0:
                gw += p
            else:
                gl -= p
            eq += p
            peak = max(peak, eq)
            dd = min(dd, eq - peak)
    return tot, gp, cp, a1, a2, npos, gw, gl, dd
