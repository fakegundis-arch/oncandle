"""Backtest of the 4newgolds gold bot's TELEGRAM path (branch claude/code-review-understanding-swltkb, config.yaml as
committed), replayed post by post on real Exness prices.

What is replayed, and from where:
  * Settings: loaded with the bot's OWN loader (newsbot.config.load_config) from its config.yaml; the Telegram profile is
    telegram_feed.profile_for(x_feed.defaults), exactly as bot._tg_profile().
  * Gates: copies of bot._emoji_flag, bot._post_tradable, bot._content_key / _seen_content_recently (600 s) and the
    order of bot._social_open_blocked (USD news blackout -> per-channel max_open -> global cap -> duplicate), using the
    bot's own keyword functions (newsbot.utils) and the blackout rule of calendar_feed.no_trade_windows.
  * Orders: plan_social_straddle -> _plan_pair: BUY STOP at ask + entry_offset, SELL STOP at bid - entry_offset, both at
    the profile lot; companion USTECm the same with its own numbers, only if no companion is open (its max_open).
  * Management, every 2 s like the bot's main loop (POLL_SECONDS): SL/TP attached from the real fill price
    (sltp_from_fill_dist, retried while MT5 would reject it), OCO, cancel after cancel_after_seconds, break-even stages
    on the best price since the fill (break_even_use_wicks; staged_break_even_sl + sl_placeable_now), the social
    trailing stop (trailing_sl).  Companion: its own SL / TP, no break-even, its own trailing.
  * Broker (simulated on Exness 1-second bid / ask bars, data/ticks_exness/<sym>/<YYYY-MM>.npz): pending stops trigger
    when ask / bid crosses them from the second after placement (fill at the worse of the order price and the
    second's first quote, plus `slip` spreads); SL / TP execute server-side at their price or at the first quote of a
    second that gaps through them; positions are held across nights and weekends (the bot never closes them); a post
    that lands while the market is shut (inside a >= 10-minute quote pause) places no orders.
  * AI post review (ai_post_check, gpt-4o-mini) cannot be called here.  It only cancels UNFILLED orders a few seconds
    after arming (close_if_filled: false) and never reviews ❗/🔴 posts.  Scenarios: "keep" (every review passes, also
    what happens when OpenAI is unreachable), "strict" (every reviewed post vetoed), "principal" (a rough stand-in:
    vetoed unless the headline starts with a principal speaking - Trump, Fed officials, Bessent / Treasury, the White
    House).
Not replayed: the Truth Social (Trump) feed, which also trades but is outside this test, and the calendar / Forex
Factory paths (calendar currencies "UASD" never match; forexfactory_news is disabled).

usage: python3 -I scripts/goldbot_backtest/replay.py <bot repo dir> [scenario ...]
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
BOT = (Path(sys.argv[1]) if len(sys.argv) > 1 and Path(sys.argv[1]).is_dir()
       else Path(os.environ.get("GOLDBOT_REPO", "/home/user/4newgolds"))).resolve()
sys.path.insert(0, str(BOT))
from newsbot.broker import BUY, SELL, SymbolInfo  # noqa: E402
from newsbot.config import load_config  # noqa: E402
from newsbot.strategy import (break_even_stages, round_price, sl_placeable_now, sltp_from_fill_dist,  # noqa: E402
                              staged_break_even_sl, trailing_sl)
from newsbot.utils import any_keyword, first_matching_group, matched_keywords  # noqa: E402

OUT = ROOT / "results" / "goldbot_backtest"
START, END = "2026-01-01", os.environ.get("GOLDBOT_END", "2026-11-01")   # END exclusive
TICK = 2                     # bot main-loop cadence (POLL_SECONDS)
GAP = 600                    # a >= 10-minute pause in quotes = market shut
CHANNEL = {"financialjuice": "FinancialJuice", "WalterBloomberg": "WalterBloomberg", "apewirenews": "apewirenews"}
SPEC = {"XAUUSDm": dict(point=0.001, digits=3, contract=100.0), "USTECm": dict(point=0.01, digits=2, contract=1.0)}
SCENARIOS = {
    "base": dict(lat=2, slip=1.0, exit_slip=0.0, ai="keep"),
    "ai_principal": dict(lat=2, slip=1.0, exit_slip=0.0, ai="principal"),
    "ai_strict": dict(lat=2, slip=1.0, exit_slip=0.0, ai="strict"),
    "optimistic": dict(lat=1, slip=0.0, exit_slip=0.0, ai="keep"),
    "stress": dict(lat=5, slip=2.0, exit_slip=1.0, ai="keep"),
    "ai_real": dict(lat=2, slip=1.0, exit_slip=0.0, ai="real"),
    # calibrated on the bot's own log (live_check.py, Oct 25 - Nov 10): armed a median 2 s after the post, priced from
    # the last quote BEFORE that second (qb), stops filled at their price (no extra spread)
    "live": dict(lat=2, slip=0.0, exit_slip=0.0, ai="keep", qb=True, fill="last"),
    "live_ai_real": dict(lat=2, slip=0.0, exit_slip=0.0, ai="real", qb=True, fill="last"),
    # the bot as configured today, whole period: real AI verdicts where they exist, the classifier's estimate elsewhere
    "main": dict(lat=2, slip=0.0, exit_slip=0.0, ai="est", qb=True, fill="last"),
    "main_lat1": dict(lat=1, slip=0.0, exit_slip=0.0, ai="est", qb=True, fill="last"),
    "main_lat3": dict(lat=3, slip=0.0, exit_slip=0.0, ai="est", qb=True, fill="last"),
    "main_lat4": dict(lat=4, slip=0.0, exit_slip=0.0, ai="est", qb=True, fill="last"),
    "main_perfect_fills": dict(lat=2, slip=0.0, exit_slip=0.0, ai="est", qb=True, fill="stop"),
}
_VERDICTS: dict = {}


def real_veto(ch: str, pid: int, det: int, estimate: bool = False):
    """Cancel the unfilled orders when the AI review said no; None = kept (also on an API error: the bot fails open).
    Verdicts, best first: the one the LIVE bot got (ai_verdicts_live_log.csv, with its real delay), my recorded run of
    the bot's own checker (ai_verdicts_last30.csv, Oct 11 - Nov 9, measured delay), and - only with estimate=True -
    the classifier's estimate for posts never reviewed (ai_verdicts_estimated.csv, ~80 % agreement, delay AI_DELAY)."""
    if not _VERDICTS:
        _VERDICTS[("", 0)] = None
        for name, kind in (("ai_verdicts_estimated.csv", "est"), ("ai_verdicts_last30.csv", "mine"),
                           ("ai_verdicts_live_log.csv", "live")):          # later files overwrite earlier ones
            f = OUT / name
            if not f.exists():
                continue
            for r in pd.read_csv(f).itertuples():
                err = str(getattr(r, "error", "")) if isinstance(getattr(r, "error", None), str) else ""
                lat = float(getattr(r, "latency_s", AI_DELAY)) if kind != "est" else float(AI_DELAY)
                _VERDICTS[(r.channel, int(r.post_id))] = (bool(r.ok), err, lat if lat == lat else float(AI_DELAY), kind)
    hit = _VERDICTS.get((ch, int(pid)))
    if hit is None or hit[0] or hit[1] or (hit[3] == "est" and not estimate):
        return None
    return det + max(1, int(np.ceil(hit[2])))


AI_DELAY = 3                 # seconds from arming to the AI verdict (gpt-4o-mini round trip)


# ------------------------------------------------------------------ data
def load_posts() -> pd.DataFrame:
    rows = []
    for f in sorted(glob.glob(str(ROOT / "data/telegram/history/*.jsonl"))):   # earliest download of a post wins
        b = os.path.basename(f)
        ch = next((v for k, v in CHANNEL.items() if b.startswith(k)), None)
        if ch is None:
            continue
        for line in open(f, encoding="utf-8"):
            p = json.loads(line)
            rows.append(dict(ch=ch, id=int(p["id"]), time=p["time"], text=p.get("text") or "",
                             fwd=p.get("fwd") is not None, reply=bool(p.get("reply", False)),
                             media=bool(p.get("media", False))))
    d = pd.DataFrame(rows).drop_duplicates(["ch", "id"])
    d["t"] = pd.to_datetime(d.time, utc=True)
    d["ts"] = d.t.astype("datetime64[s, UTC]").astype("int64")
    d["text"] = [" ".join(x.split()) for x in d.text]          # telegram_feed._to_post collapses whitespace
    d = d[(d.t >= pd.Timestamp(START, tz="UTC")) & (d.t < pd.Timestamp(END, tz="UTC"))]
    return d.sort_values(["ts", "ch", "id"]).reset_index(drop=True)


M1_FILLED: dict = {}          # symbol -> set of UTC day starts (unix s) priced from the MT5 1-minute export


def m1_fill(sym: str, tk: dict) -> list:
    """Bars for whole weekdays the Exness tick archive lacks (its monthly files miss some days: USTECm Mar 30-31,
    Sep 30, Oct 19, Oct 29-30 2026), from the user's MT5 1-minute export (data/mt5_exports/<sym>_M1_*.csv, bid OHLC +
    spread in points, UTC) when it covers them.  One bar per minute, stamped at the minute's last second; ask = bid +
    the bar's spread.  Coarser than ticks (the arming quote is the previous minute's close, and a minute's range is
    taken as one step), so trades on these days are marked price_source = "MT5 1-minute bars"."""
    files = sorted(glob.glob(str(ROOT / "data/mt5_exports" / f"{sym}_M1_*.csv")))
    if not files:
        return []
    have = set(np.unique(tk["t"] // 86400 * 86400).tolist())
    lo, hi = int(tk["t"][0]), int(tk["t"][-1])
    out, days = [], set()
    for f in files:
        m = pd.read_csv(f, sep="\t")
        m.columns = [c.strip("<>").lower() for c in m.columns]
        t0 = (pd.to_datetime(m.date + " " + m.time, format="%Y.%m.%d %H:%M:%S") - pd.Timestamp("1970-01-01")) \
            // pd.Timedelta(seconds=1)
        day = t0 // 86400 * 86400
        wk = pd.to_datetime(day, unit="s").dt.dayofweek < 5
        miss = (~day.isin(have)) & wk & (t0 > lo) & (t0 < hi)
        if not miss.any():
            continue
        m, t0 = m[miss], t0[miss]
        sp = m.spread.to_numpy(float) * SPEC[sym]["point"]
        b = {"bid_first": m.open, "bid_last": m.close, "bid_min": m.low, "bid_max": m.high}
        part = {"t": (t0 + 59).to_numpy(np.int64), "n": m.tickvol.to_numpy(np.int32)}
        for k, v in b.items():
            part[k] = v.to_numpy(float)
            part[k.replace("bid", "ask")] = v.to_numpy(float) + sp
        out.append(part)
        days |= set(day[miss].unique().tolist())
    M1_FILLED[sym] = days
    return out


def load_ticks(sym: str) -> dict:
    ms = pd.period_range(START, pd.Timestamp(END) - pd.Timedelta(seconds=1), freq="M")
    parts = [dict(np.load(ROOT / "data/ticks_exness" / sym / f"{m}.npz")) for m in ms.astype(str)]
    tk = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
    for p in m1_fill(sym, tk):
        tk = {k: np.concatenate([tk[k], p[k].astype(tk[k].dtype)]) for k in tk}
    o = np.argsort(tk["t"], kind="stable")
    tk = {k: v[o] for k, v in tk.items()}
    keep = np.r_[True, np.diff(tk["t"]) > 0]
    return {k: v[keep] for k, v in tk.items()}


def blackout_windows(nb) -> list:
    """calendar_feed.no_trade_windows for the USD high-impact events of data/calendar/ff_calendar.csv."""
    c = pd.read_csv(ROOT / "data/calendar/ff_calendar.csv", parse_dates=["time_utc"])
    c = c[c.currency.str.upper().isin([x.upper() for x in nb.currencies])
          & c.impact.str.capitalize().isin(nb.impacts)]
    out = []
    for e in c.itertuples():
        when = int(pd.Timestamp(e.time_utc, tz="UTC").timestamp())
        if nb.ignore_all_day and pd.Timestamp(e.time_utc).minute % 5 != 0:      # Event.untimed
            continue
        has_data = bool(str(e.forecast if isinstance(e.forecast, str) else "").strip()
                        or str(e.previous if isinstance(e.previous, str) else "").strip())
        length = (nb.minutes_with_data if has_data else nb.minutes_without_data) * 60
        out.append((when - nb.minutes_before * 60, when + length, f"{e.currency} {e.name}"))
    return sorted(out)


# ------------------------------------------------------------------ the bot's gates (copied from bot.py)
def emoji_flag(text: str, et, mode: str):
    """bot._emoji_flag"""
    if not et.enabled or not text:
        return None
    flat = text.replace("️", "")
    hit = next((e for e in et.emojis if e.replace("️", "") and e.replace("️", "") in flat), None)
    if hit is None:
        return None
    if matched_keywords(et.blacklist, text, mode):
        return None
    return hit


def post_tradable(post, prof, mode: str, age: float, keyword_bypass: bool):
    """bot._post_tradable"""
    text = (post.text or "").strip()
    if age > prof.max_age_seconds:
        return False, "stale"
    if prof.skip_retruths and post.fwd:
        return False, "repost/forward"
    if getattr(prof, "skip_replies", False) and post.reply:
        return False, "reply"
    if len(text) < prof.min_length:
        return False, "too short"
    for w in matched_keywords(prof.blacklist, text, mode):
        return False, f"blacklisted ('{w}')"
    if first_matching_group(getattr(prof, "blacklist_all", []), text, mode):
        return False, "blacklisted phrase"
    if keyword_bypass:
        return True, "emoji flag"
    if prof.use_keywords and prof.keywords and not any_keyword(prof.keywords, text, mode):
        return False, "no keyword match"
    return True, "ok"


def content_key(text: str) -> str:
    """bot._content_key"""
    low = "".join(ch for ch in (text or "").lower() if ch.isalnum() or ch.isspace())
    return " ".join(low.split())[:80]


PRINCIPAL = re.compile(
    r"^\W*(?:breaking:?\s*)?(?:(?:us\s+)?(?:president\s+)?trump|powell|warsh|bessent|treasury(?:'s)?(?:\s+sec(?:retary)?)?"
    r"|fed(?:'s)?(?:\s+chair)?(?:\s+[a-z]+)?|fomc|white\s+house|leavitt|hassett|waller|bowman|jefferson|cook|barr|miran"
    r"|goolsbee|kashkari|logan|hammack|musalem|schmid|daly|bostic|barkin|harker|collins|williams|vance)"
    r"(?:\s+(?:says?|said|on|tells?)\b|\s*:)", re.I)


def ai_vetoes(text: str, mode: str) -> bool:
    if mode == "keep":
        return False
    if mode == "strict":
        return True
    return PRINCIPAL.search(text) is None                     # "principal": rough stand-in for gate 1


# ------------------------------------------------------------------ broker + bot management simulation
@dataclass
class Pos:
    side: str
    fill_ts: int
    fill: float
    leg: str
    sl: float = 0.0
    tp: float = 0.0
    attached: bool = False
    best: float = 0.0
    be_stage: int = 0
    trailed: bool = False
    exit_ts: int = 0
    exit: float = 0.0
    why: str = ""


def sym_info(name, tk, j) -> SymbolInfo:
    s = SPEC[name]
    return SymbolInfo(name=name, bid=float(tk["bid_last"][j]), ask=float(tk["ask_last"][j]), point=s["point"],
                      digits=s["digits"], volume_min=0.01, volume_max=200.0, volume_step=0.01,
                      trade_contract_size=s["contract"], tick_value=1.0)


def market_shut(tk, ts) -> bool:
    i = np.searchsorted(tk["t"], ts, side="right")            # first bar after ts
    prev_t = tk["t"][i - 1] if i > 0 else -10**12
    next_t = tk["t"][i] if i < len(tk["t"]) else 10**12
    return next_t - prev_t >= GAP and ts > prev_t     # nothing quotes for 10+ minutes from here: the session is shut


MIN_DIST = {"XAUUSDm": 0.0, "USTECm": 15.0}


def simulate(name, tk, t_arm, buy_px, sell_px, sl_d, tp_d, cancel_after, stages, trail, veto_ts, slip, exit_slip,
             min_dist=None, fill_model="stop", sl_model="stop"):
    """One straddle from arming to the last exit -> (positions, close_ts).  Bars are processed second by second;
    the bot's management runs at t_arm, t_arm + 2, ... on the latest quote before that moment.

    min_dist: the broker's real minimum distance between the price and an SL / TP being set or moved.  The bot reads
    stops_level 0 from MT5 and so tries anything on the right side of the price, but the live log shows Exness
    rejecting USTECm stops closer than about 15 points ("bad stops" 270 times while <15 away, accepted from 15.4);
    gold was accepted from under 1.5 away, so none is assumed there.  A rejected SL is retried every loop, as live."""
    if min_dist is None:
        min_dist = MIN_DIST.get(name, 0.0)
    # fill_model / sl_model "last": a stop that triggers inside a second is filled at the worse of its price and that
    # second's last quote (a market order sent into a fast move).  Against the live fills this beats "at the stop
    # price": the Nov 10 09:01 gold SELL (stop ~4096.0, live fill 4093.23, model 4093.77), USTECm Nov 5 16:36 (live
    # 9.47 beyond, model 8.23), Nov 9 19:39 (4.24 / 2.99); mean abs error 1.07 vs 1.34 points (USTECm), 0.40 vs 0.52 $.

    def far_enough(side, level, sym, is_tp=False):
        if not level:
            return True
        if (side == BUY) != is_tp:                 # BUY's SL / SELL's TP sit below the price
            return level <= sym.bid - min_dist
        return level >= sym.ask + min_dist
    m1days = M1_FILLED.get(name, ())           # days priced from 1-minute bars: a bar's last quote is a minute away
    T = tk["t"]
    pend = {"BUY": buy_px, "SELL": sell_px}
    pos: list[Pos] = []
    triggered = False
    i = int(np.searchsorted(T, t_arm, side="right"))          # orders live from the next second
    next_tick = t_arm + TICK
    closed_ts = None
    n = len(T)

    def manage(now, j):
        nonlocal triggered, pend, closed_ts
        if j < 0:
            return
        sym = sym_info(name, tk, j)
        live = [p for p in pos if not p.exit_ts]
        for p in live:                                         # sl_tp_after_fill
            if not p.attached:
                sl, tp = sltp_from_fill_dist(p.side, p.fill, sl_d, tp_d, sym)
                ok_sl = (sl == 0.0) or (sl_placeable_now(p.side, sl, sym) and far_enough(p.side, sl, sym))
                ok_tp = (tp == 0.0) or ((tp > sym.bid if p.side == BUY else tp < sym.ask)
                                        and far_enough(p.side, tp, sym, is_tp=True))
                if ok_sl and ok_tp:
                    p.sl, p.tp, p.attached = sl, tp, True
        if live and not triggered:                            # OCO
            triggered = True
            pend = {}
        if pend and now >= t_arm + cancel_after:              # cancel window
            pend = {}
        if pend and veto_ts is not None and now >= veto_ts:   # AI review veto: pending only
            pend = {}
        for p in live:
            if not p.attached:
                continue
            if stages:                                         # break-even, wicks
                basis = max(p.best, sym.bid) if p.side == BUY else min(p.best, sym.ask)
                new_sl = staged_break_even_sl(p.side, p.fill, basis, p.sl, stages, sym)
                if new_sl is not None and sl_placeable_now(p.side, new_sl, sym) and far_enough(p.side, new_sl, sym):
                    p.sl = new_sl
                    p.be_stage += 1
            if trail is not None:                              # social trailing stop
                price = sym.bid if p.side == BUY else sym.ask
                new_sl = trailing_sl(p.side, p.fill, price, p.sl, trail.start, trail.distance, trail.step, sym)
                if new_sl is not None and far_enough(p.side, new_sl, sym):
                    p.sl, p.trailed = new_sl, True
        if not pend and not [p for p in pos if not p.exit_ts]:
            closed_ts = now

    while i < n and closed_ts is None:
        b = int(T[i])
        while next_tick <= b and closed_ts is None:            # bot ticks before this second
            manage(next_tick, i - 1)
            busy = bool(pend) or any(not p.exit_ts for p in pos if not p.attached)
            next_tick = next_tick + TICK if busy else max(next_tick + TICK, b - (b - next_tick) % TICK)
        if closed_ts is not None:
            break
        af, bf = tk["ask_first"][i], tk["bid_first"][i]
        sp = af - bf
        for p in pos:                                          # server-side SL / TP of attached positions
            if p.exit_ts or not p.attached:
                continue
            if p.side == BUY:
                first, lo, hi = tk["bid_first"][i], tk["bid_min"][i], tk["bid_max"][i]
                hit_sl = p.sl and (first <= p.sl or lo <= p.sl)
                hit_tp = p.tp and (first >= p.tp or hi >= p.tp)
                if hit_sl:
                    p.exit = (first if first <= p.sl else p.sl) - exit_slip * sp
                    if sl_model == "last":
                        p.exit = min(p.exit, tk["bid_last"][i])
                elif hit_tp:
                    p.exit = first if first >= p.tp else p.tp
            else:
                first, lo, hi = tk["ask_first"][i], tk["ask_min"][i], tk["ask_max"][i]
                hit_sl = p.sl and (first >= p.sl or hi >= p.sl)
                hit_tp = p.tp and (first <= p.tp or lo <= p.tp)
                if hit_sl:
                    p.exit = (first if first >= p.sl else p.sl) + exit_slip * sp
                    if sl_model == "last":
                        p.exit = max(p.exit, tk["ask_last"][i])
                elif hit_tp:
                    p.exit = first if first <= p.tp else p.tp
            if hit_sl or hit_tp:
                p.exit_ts = b
                if hit_tp:
                    p.why = "take profit"
                elif p.trailed:
                    p.why = "trailing stop"
                elif p.be_stage:
                    p.why = f"break-even stop"
                else:
                    p.why = "stop loss"
        for p in pos:                                          # best price since the fill (wicks)
            if not p.exit_ts and b > p.fill_ts:
                p.best = max(p.best, tk["bid_max"][i]) if p.side == BUY else min(p.best, tk["ask_min"][i])
        if "BUY" in pend and tk["ask_max"][i] >= pend["BUY"]:  # pending stop triggers
            fill = max(pend["BUY"], af) + slip * sp
            if fill_model == "last" and b // 86400 * 86400 not in m1days:
                fill = max(fill, tk["ask_last"][i])
            pos.append(Pos(BUY, b, fill, "BUY", best=fill))
            del pend["BUY"]
        if "SELL" in pend and tk["bid_min"][i] <= pend["SELL"]:
            fill = min(pend["SELL"], bf) - slip * sp
            if fill_model == "last" and b // 86400 * 86400 not in m1days:
                fill = min(fill, tk["bid_last"][i])
            pos.append(Pos(SELL, b, fill, "SELL", best=fill))
            del pend["SELL"]
        i += 1
    if closed_ts is None:                                      # data ended with something open
        j = n - 1
        for p in pos:
            if not p.exit_ts:
                p.exit_ts, p.why = int(T[j]), "open at end of data"
                p.exit = tk["bid_last"][j] if p.side == BUY else tk["ask_last"][j]
        closed_ts = int(T[j])
    return pos, closed_ts


# ------------------------------------------------------------------ replay
def derive(cfg) -> SimpleNamespace:
    """Everything the Telegram path reads from one config."""
    prof = cfg.telegram_feed.profile_for(cfg.x_feed.defaults)
    comp, gmo, ts = cfg.companion, cfg.global_max_open, cfg.social_trailing_stop
    return SimpleNamespace(
        cfg=cfg, mode=cfg.keyword_match, prof=prof, et=cfg.x_feed.emoji_trigger, nb=cfg.news_blackout, comp=comp,
        stages=break_even_stages(cfg.strategy) if cfg.strategy.break_even_enabled else [],
        trail=ts if (ts.enabled and ts.distance > 0 and "telegram" in ts.feeds) else None,
        cstages=break_even_stages(comp) if comp.break_even_enabled else [],
        ctrail=comp.trailing if (comp.trailing.enabled and comp.trailing.distance > 0) else None,
        cap=gmo.max_open if (gmo.enabled and "telegram" in gmo.feeds) else 10**9,
        channels={c.lstrip("@").lower() for c in cfg.telegram_feed.channels})


def replay(cfg, posts, ticks, windows, sc, live=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Post by post.  `live` (as_live.LiveCtx) switches to the as-live check: the settings in force at each moment,
    the bot's real arming second and AI verdicts, restarts that wipe its memory, and the X / Trump straddles that
    held the shared slots - everything else is the same code path as the normal backtest."""
    today = derive(cfg)
    gold, nas = ticks[cfg.symbol], ticks[cfg.companion.symbol]
    gold_end, nas_end = int(gold["t"][-1]), int(nas["t"][-1])
    wstart = np.array([w[0] for w in windows])
    side = "left" if sc.get("qb") else "right"
    open_gold: list = []          # (close_ts, channel) of Telegram gold straddles still open
    open_comp_until = -1
    recent: dict = {}
    epoch = None
    decisions, trades = [], []

    def note(p, text):
        decisions.append((int(p.ts), p.ch, int(p.id), text))

    for p in posts.itertuples():
        if live is not None:
            det = live.det(p.ch, p.id)
            if det is None:                       # the live bot never received it (offline, or not watching yet)
                continue
            d = live.settings(det)
            if live.epoch(det) != epoch:          # a restart: the bot's stores and dedupe cache start empty
                epoch, open_gold, open_comp_until, recent = live.epoch(det), [], -1, {}
        else:
            det, d = int(p.ts) + sc["lat"], today
        if p.ch.lower() not in d.channels:
            continue
        prof, comp = d.prof, d.comp
        if det > gold_end:
            note(p, "no price data yet")
            continue
        flag = emoji_flag(p.text, d.et, d.mode)
        age = live.age(p.ch, p.id, det - int(p.ts)) if live is not None else det - int(p.ts)
        ok, why = post_tradable(p, prof, d.mode, age, keyword_bypass=bool(flag))
        if not ok:
            note(p, why)
            continue
        # _social_open_blocked, in the bot's order
        k = np.searchsorted(wstart, det, side="right")
        if d.nb.enabled and "telegram" in d.nb.feeds and any(w[0] <= det < w[1] for w in windows[max(0, k - 40):k]):
            note(p, "USD news blackout")
            continue
        open_gold = [g for g in open_gold if g[0] > det]
        if len([g for g in open_gold if g[1] == p.ch]) >= prof.max_open:
            note(p, "channel max_open")
            continue
        if len(open_gold) + (live.global_holders(det) if live is not None else 0) >= d.cap:
            note(p, "global cap")
            continue
        key = content_key(p.text)
        recent = {kk: v for kk, v in recent.items() if det - v <= 600}
        if key and key in recent:
            note(p, "duplicate content")
            continue
        if key:
            recent[key] = det
        if market_shut(gold, det):
            note(p, "market shut (orders rejected)")
            continue
        j = int(np.searchsorted(gold["t"], det, side=side)) - 1
        sym = sym_info(cfg.symbol, gold, j)
        buy = round_price(sym.ask + prof.entry_offset, sym)
        sell = round_price(sym.bid - prof.entry_offset, sym)
        if live is not None:
            veto = None if flag else live.veto(p.ch, p.id)
        elif sc["ai"] in ("real", "est"):
            veto = None if flag else real_veto(p.ch, p.id, det, estimate=sc["ai"] == "est")
        else:
            veto = det + AI_DELAY if (not flag and ai_vetoes(p.text, sc["ai"])) else None
        pos, close = simulate(cfg.symbol, gold, det, buy, sell, prof.stop_loss, prof.take_profit,
                              prof.cancel_after_seconds, d.stages, d.trail, veto, sc["slip"], sc["exit_slip"],
                              fill_model=sc.get("fill", "stop"), sl_model=sc.get("sl", "stop"))
        open_gold.append((close, p.ch))
        note(p, "ARMED" + (f" ({flag} fast track)" if flag else ""))
        base = dict(post_ts=int(p.ts), channel=p.ch, post_id=int(p.id), flag=flag or "", text=p.text[:200],
                    armed_ts=det, ai_veto=veto is not None)

        def rows(symbol, lot, ps, cl, buy_px, sell_px):
            c = SPEC[symbol]["contract"]
            for q in ps:
                trades.append(dict(base, symbol=symbol, side=q.side, fill_ts=q.fill_ts, fill=q.fill, exit_ts=q.exit_ts,
                                   exit=q.exit, exit_reason=q.why, lot=lot, buy_stop=buy_px, sell_stop=sell_px,
                                   usd=(q.exit - q.fill) * (1 if q.side == BUY else -1) * lot * c))
            if not ps:
                vetoed = veto is not None and cl < det + 119
                trades.append(dict(base, symbol=symbol, side="", fill_ts=0, fill=np.nan, exit_ts=cl, exit=np.nan,
                                   exit_reason="no fill" + (" (AI veto)" if vetoed else ""), lot=lot,
                                   buy_stop=buy_px, sell_stop=sell_px, usd=0.0))

        rows(cfg.symbol, prof.lot, pos, close, buy, sell)
        # companion (USTECm): only when gold armed, and only if no companion is open (its max_open)
        if not (comp.enabled and "telegram" in comp.feeds):
            continue
        skip = None
        if det > nas_end:
            skip = "no Nasdaq price data yet"
        elif det < open_comp_until or (live is not None and live.comp_busy(det)):
            skip = "not armed: a Nasdaq straddle was still open"
        elif market_shut(nas, det):
            skip = "not armed: Nasdaq closed"
        if skip:
            trades.append(dict(base, symbol=comp.symbol, side="", fill_ts=0, fill=np.nan, exit_ts=0, exit=np.nan,
                               exit_reason=skip, lot=comp.lot, usd=0.0))
            continue
        jn = int(np.searchsorted(nas["t"], det, side=side)) - 1
        nsym = sym_info(comp.symbol, nas, jn)
        nb_, ns_ = round_price(nsym.ask + comp.entry_offset, nsym), round_price(nsym.bid - comp.entry_offset, nsym)
        cpos, cclose = simulate(comp.symbol, nas, det, nb_, ns_, comp.stop_loss, comp.take_profit,
                                comp.cancel_after_seconds, d.cstages, d.ctrail, veto, sc["slip"], sc["exit_slip"],
                                fill_model=sc.get("fill", "stop"), sl_model=sc.get("sl", "stop"))
        open_comp_until = cclose
        rows(comp.symbol, comp.lot, cpos, cclose, nb_, ns_)
    dec = pd.DataFrame(decisions, columns=["post_ts", "channel", "post_id", "decision"])
    return pd.DataFrame(trades), dec


def summary(tr: pd.DataFrame) -> dict:
    f = tr[tr.side != ""]
    out = {}
    for sym, g in [("gold", f[f.symbol.str.startswith("XAU")]), ("nasdaq", f[f.symbol.str.startswith("USTEC")]), ("all", f)]:
        g = g.sort_values("exit_ts")
        eq = g.usd.cumsum().to_numpy()
        dd = float((eq - np.maximum.accumulate(np.r_[0.0, eq])[1:]).min()) if len(eq) else 0.0
        w, l = g.usd[g.usd > 0].sum(), -g.usd[g.usd < 0].sum()
        out[sym] = dict(positions=len(g), usd=round(float(g.usd.sum()), 2), win_rate=round(float((g.usd > 0).mean()), 3) if len(g) else 0,
                        pf=round(float(w / l), 2) if l > 0 else None, max_drawdown_usd=round(dd, 2),
                        median_hold_min=round(float(((g.exit_ts - g.fill_ts) / 60).median()), 1) if len(g) else 0)
    out["straddles_armed"] = int(tr[tr.symbol.str.startswith("XAU")].drop_duplicates(["channel", "post_id"]).shape[0])
    return out


def main():
    cfg = load_config(str(BOT / "config.yaml"))
    posts = load_posts()
    ticks = {s: load_ticks(s) for s in (cfg.symbol, cfg.companion.symbol)}
    windows = blackout_windows(cfg.news_blackout)
    OUT.mkdir(parents=True, exist_ok=True)
    names = sys.argv[2:] or list(SCENARIOS)
    res = {}
    for name in names:
        tr, dec = replay(cfg, posts, ticks, windows, SCENARIOS[name])
        if len(tr):
            day = tr.armed_ts // 86400 * 86400
            tr["price_source"] = np.where([d in M1_FILLED.get(s, ()) for d, s in zip(day, tr.symbol)],
                                          "MT5 1-minute bars", "Exness ticks")
        tag = name if END == "2026-11-01" else f"{name}_to_{END}"
        tr.to_csv(OUT / f"trades_{tag}.csv", index=False)
        dec.to_csv(OUT / f"decisions_{tag}.csv", index=False)
        res[name] = dict(settings=SCENARIOS[name], summary=summary(tr),
                         decisions=dec.decision.str.replace(r" \(.*", "", regex=True).value_counts().to_dict())
        print(name, json.dumps(res[name]["summary"]), flush=True)
    f = OUT / ("summary.json" if END == "2026-11-01" else f"summary_to_{END}.json")
    old = json.loads(f.read_text()) if f.exists() else {}           # keep the scenarios not rerun this time
    old.update(res)
    f.write_text(json.dumps(old, indent=1, default=str))


if __name__ == "__main__":
    main()
