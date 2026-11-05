"""M1-exact backtest with the protocol's costs, using the same signal / plan code as the live bot.

Fills (bars are BID):
  * long  buys at the ask = bid + cost, exits at the bid; short sells at the bid, exits at the ask = bid + cost;
    a short's stop / target is hit when bid + cost reaches it
  * cost = `cost` (the protocol's base spread), x `news_mult` for a trade ENTERED within `news_window` minutes of the
    release; the trade pays that spread once, at the entry for a long, at the exit (stop / target / time) for a
    short - so a short entered at a release cannot escape the wide spread by exiting after the window
  * entry at the OPEN of the first bar at release + entry_delay minutes; skipped if the market is not quoting then
  * stop before target inside a minute; the entry minute can only stop out; a gap through a level fills at the open
  * time exit at the open of the first bar at / after the exit time; weekends closed by Friday 20:00 UTC
  * one position per instrument at a time (a release arriving while a trade is open is skipped)
make_trades(cfg, calendar, m1, cost) is the strategy entry point used by asia_news_lab.final_test.

entry = "pair_reaction" (v2 Nasdaq) also needs the M1 bid bars of the signal pair (AUDUSD / NZDUSD): pass them as
aux={"AUDUSD": df, ...}, or leave aux=None and the bars come from `AUX_PRICES(symbol, start, end)` - by default the
research toolkit scripts/asia_news_lab.py (prices_train() when the traded bars end inside the build period, so a
build run never loads later data; the toolkit's own M1 loader cut to the traded bars' time span otherwise, i.e. in
final_test).  The direction is read from the pair at release + react_min; the entry is at release + entry_delay
(the "entry 2 minutes later" stress test moves the entry, not the signal).
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from .events import releases_from_frame
from .strategy import (atr, breakout_exit_by, breakout_setup, confirmed, full_cfg, make_plan, reaction_direction,
                       signal_pair)

_ATR: dict = {}                            # (frame fingerprint, release, tf, n) -> ATR  (speed only)
MAX_ENTRY_GAP = timedelta(minutes=2)       # market not quoting within 2 min of the planned entry -> skip
REPO_DEFAULT = str(__import__("pathlib").Path(__file__).resolve().parents[3])   # repo root


def lab_prices(symbol: str, start, end) -> pd.DataFrame:
    """M1 bid bars of `symbol` from the research toolkit (scripts/asia_news_lab.py), cut to [start, end]."""
    import os
    import sys
    if "asia_news_lab" in sys.modules:
        L = sys.modules["asia_news_lab"]
    else:
        sys.path.insert(0, os.path.join(os.environ.get("NEWSBOT_REPO", REPO_DEFAULT), "scripts"))
        import asia_news_lab as L
    if pd.Timestamp(start) >= pd.Timestamp(L.PRICE_FROM) and pd.Timestamp(end) < pd.Timestamp(L.TRAIN[1]):
        m = L.prices_train(symbol)                 # build period: never touches later data
    else:
        m = L._m1(symbol)                          # final_test / exam_2025: the toolkit's loader, cut to the span
    return m[(m.index >= pd.Timestamp(start)) & (m.index <= pd.Timestamp(end))]


AUX_PRICES = lab_prices                    # replaceable price source for signal pairs (tests use synthetic bars)
_AUX: dict = {}


def simulate(m1: pd.DataFrame, plan, cost: float, news_mult: float, news_window: int):
    """Return (entry_time, exit_time, r, reason, entry_price, exit_price) or None if no entry."""
    idx = m1.index
    i = idx.searchsorted(pd.Timestamp(plan.entry_after))
    if i >= len(idx) or idx[i] - pd.Timestamp(plan.entry_after) > MAX_ENTRY_GAP:
        return None
    rel_t = pd.Timestamp(plan.release.time)
    win_end = rel_t + timedelta(minutes=news_window)
    o, h, l = m1.open.to_numpy(), m1.high.to_numpy(), m1.low.to_numpy()
    d, sd = plan.direction, plan.stop_dist
    t_e = idx[i]
    ct = cost * news_mult if t_e <= win_end else cost        # the trade's spread
    fill = o[i] + ct if d > 0 else o[i]                      # long buys at the ask, short sells at the bid
    return run_from(m1, i, fill, d, sd, plan.target_dist, pd.Timestamp(plan.exit_by), ct)


def run_from(m1: pd.DataFrame, i: int, fill: float, d: int, sd: float, target_dist: float, ex_t, ct: float):
    """The trade after its fill in bar i at `fill` (a long's fill already includes the spread; a short pays `ct` on its
    exit): stop / target from the fill, stop before target, the fill bar can only stop out, gaps at the open, time
    exit at the open of the first bar at / after ex_t.  -> (entry_time, exit_time, r, reason, fill, exit_price)."""
    idx = m1.index
    o, h, l = m1.open.to_numpy(), m1.high.to_numpy(), m1.low.to_numpy()
    t_e = idx[i]
    sl = fill - d * sd
    tp = fill + d * target_dist if np.isfinite(target_dist) else None
    j = i
    while j < len(idx):
        t = idx[j]
        c = ct if d < 0 else 0.0                             # shorts exit at the ask
        if t >= ex_t and j > i:
            px = o[j] + c
            return t_e, t, d * (px - fill) / sd, "time", fill, px
        op, hi, lo = o[j] + c, h[j] + c, l[j] + c
        if j > i:                                            # gaps at the open
            if (d > 0 and op <= sl) or (d < 0 and op >= sl):
                return t_e, t, d * (op - fill) / sd, "stop-gap", fill, op
            if tp is not None and ((d > 0 and op >= tp) or (d < 0 and op <= tp)):
                return t_e, t, d * (op - fill) / sd, "target-gap", fill, op
        if (d > 0 and lo <= sl) or (d < 0 and hi >= sl):
            return t_e, t, -1.0, "stop", fill, sl
        if j > i and tp is not None and ((d > 0 and hi >= tp) or (d < 0 and lo <= tp)):
            return t_e, t, d * (tp - fill) / sd, "target", fill, tp
        j += 1
    px = m1.close.iloc[-1] + (ct if d < 0 else 0.0)
    return t_e, idx[-1], d * (px - fill) / sd, "end-of-data", fill, px


def simulate_breakout(m1: pd.DataFrame, s, cfg: dict, cost: float, late: int = 0):
    """entry = "breakout": OCO stop orders of the BreakoutSetup `s`, active in the bars from s.place_at to before
    s.expire_at.  A buy stop triggers when the ask (bid + spread) high reaches s.up and fills at max(s.up, ask open),
    a sell stop when the bid low reaches s.dn and fills at min(s.dn, bid open); within news_window minutes of the
    release the spread is news_mult x cost and a fill pays brk_slip x cost of slippage.  Both triggered in one bar ->
    the WORSE trade is booked.  late > 0 (stress test): a market order `late` minutes after the trigger instead.
    -> (entry_time, exit_time, r, reason, fill, exit_price, direction) or None (no trigger)."""
    c = cfg
    idx = m1.index
    o, h, l = m1.open.to_numpy(), m1.high.to_numpy(), m1.low.to_numpy()
    rel_t = pd.Timestamp(s.release.time)
    win = timedelta(minutes=int(c["news_window"]))
    a, b = idx.searchsorted(pd.Timestamp(s.place_at)), idx.searchsorted(pd.Timestamp(s.expire_at))

    def spread(k):
        return cost * float(c["news_mult"]) if idx[k] - rel_t <= win else cost

    for j in range(a, min(b, len(idx))):
        ct = spread(j)
        up, dn = h[j] + ct >= s.up, l[j] <= s.dn
        if not (up or dn):
            continue
        legs = []
        if late:
            k = idx.searchsorted(idx[j] + timedelta(minutes=int(late)))
            if k >= len(idx):
                return None
            ck = spread(k)
            legs = [(k, o[k] + ck, 1, ck)] * int(up) + [(k, o[k], -1, ck)] * int(dn)
        else:
            slip = float(c["brk_slip"]) * cost if idx[j] - rel_t <= win else 0.0
            if up:
                legs.append((j, max(s.up, o[j] + ct) + slip, 1, ct))
            if dn:
                legs.append((j, min(s.dn, o[j]) - slip, -1, ct))
        out = None
        for i, fill, d, ci in legs:
            ex_t = pd.Timestamp(breakout_exit_by(c, idx[i].to_pydatetime()))
            r = run_from(m1, i, fill, d, s.stop_dist, s.target_dist, ex_t, ci)
            if out is None or r[2] < out[2]:
                out = (*r, d)
        return out
    return None


def _breakout_trades(c: dict, rels, m1: pd.DataFrame, cost: float, late: int, detail: bool, fp) -> list[dict]:
    lo, hi = m1.index[0], m1.index[-1]
    rows, busy_until = [], None
    for rel in rels:
        t = pd.Timestamp(rel.time)
        if not (lo <= t <= hi) or rel.currency not in c["currencies"]:
            continue
        if busy_until is not None and t <= busy_until:          # one position at a time
            continue
        key = (fp, rel.time, int(c["stop_atr_tf"]), int(c["stop_atr_n"]))
        if key not in _ATR:
            _ATR[key] = atr(m1, rel.time, int(c["stop_atr_tf"]), int(c["stop_atr_n"]))
        st, _ = breakout_setup(rel, c, m1, atr_value=_ATR[key])
        if st is None:
            continue
        res = simulate_breakout(m1, st, c, cost, late)
        if res is None:
            continue
        te, tx, r, why, fill, px, d = res
        if busy_until is not None and te <= busy_until:
            continue
        busy_until = tx
        row = dict(entry_time=te, exit_time=tx, dir=d, r=float(r), event=st.why)
        if detail:
            row.update(reason=why, entry=fill, exit=px, stop_dist=st.stop_dist, ccy=rel.currency, kind=rel.kind,
                       release=t, up=st.up, dn=st.dn)
        rows.append(row)
    return rows


_REL: dict = {}


def _releases(calendar):
    k = (id(calendar), len(calendar))
    if k not in _REL:
        _REL.clear()
        _REL[k] = releases_from_frame(calendar)
    return _REL[k]


def _aux_bars(sym: str, lo, hi, aux: dict | None) -> pd.DataFrame:
    if aux is not None and sym in aux:
        return aux[sym]
    k = (sym, pd.Timestamp(lo), pd.Timestamp(hi), id(AUX_PRICES))
    if k not in _AUX:
        if len(_AUX) > 8:
            _AUX.clear()
        _AUX[k] = AUX_PRICES(sym, lo, hi)
    return _AUX[k]


def make_trades(cfg: dict, calendar: pd.DataFrame, m1: pd.DataFrame, cost: float,
                entry_delay: int | None = None, detail: bool = False, aux: dict | None = None) -> pd.DataFrame:
    """Strategy for ONE instrument: cfg["symbol"] / cfg["instrument"] decide which releases it trades."""
    c = full_cfg(cfg)
    rels = _releases(calendar)
    lo, hi = m1.index[0], m1.index[-1]
    fp = (len(m1), lo, hi, float(m1.close.iloc[0]), float(m1.close.iloc[-1]), float(m1.high.max()))
    rows, busy_until = [], None
    if c["entry"] == "breakout":
        late = 0 if entry_delay is None else int(entry_delay) - int(c["entry_delay"])
        rows = _breakout_trades(c, rels, m1, cost, late, detail, fp)
    react = c["entry"] == "pair_reaction"
    for rel in (rels if c["entry"] != "breakout" else []):
        if not (lo <= pd.Timestamp(rel.time) <= hi):
            continue
        if rel.currency not in c["currencies"]:
            continue
        rx = None
        if react:
            sp = signal_pair(rel.currency, c)
            if sp is None:
                continue
            rx = reaction_direction(rel, c, _aux_bars(sp[0], lo, hi, aux), int(MAX_ENTRY_GAP.total_seconds() // 60))
            if rx is None or rx.direction == 0:
                continue
        key = (fp, rel.time, int(c["stop_atr_tf"]), int(c["stop_atr_n"]))
        if key not in _ATR:
            _ATR[key] = atr(m1, rel.time, int(c["stop_atr_tf"]), int(c["stop_atr_n"]))
        plan = make_plan(rel, c, None, entry_delay, atr_value=_ATR[key], reaction=rx)
        if plan is None:
            continue
        if busy_until is not None and pd.Timestamp(plan.entry_after) <= busy_until:
            continue
        if c["confirm"]:
            p0 = m1.index.searchsorted(pd.Timestamp(rel.time)) - 1          # last bar before the release minute
            k = m1.index.searchsorted(pd.Timestamp(plan.entry_after))
            if p0 < 0 or k >= len(m1) or not confirmed(plan.direction, m1.close.iloc[p0], m1.open.iloc[k]):
                continue
        res = simulate(m1, plan, cost, c["news_mult"], c["news_window"])
        if res is None:
            continue
        te, tx, r, why, fill, px = res
        busy_until = tx
        row = dict(entry_time=te, exit_time=tx, dir=plan.direction, r=float(r), event=plan.why)
        if detail:
            row.update(reason=why, entry=fill, exit=px, stop_dist=plan.stop_dist, ccy=rel.currency, kind=rel.kind,
                       release=pd.Timestamp(rel.time))
            if rx is not None:
                row.update(pair=rx.pair, pair_pre=rx.pre, pair_post=rx.post)
        rows.append(row)
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame({"entry_time": pd.Series(dtype="datetime64[ns]"), "exit_time": pd.Series(dtype="datetime64[ns]"),
                         "dir": pd.Series(dtype=int), "r": pd.Series(dtype=float), "event": pd.Series(dtype=str)})
