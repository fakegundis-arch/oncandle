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
    "live": dict(lat=2, slip=0.0, exit_slip=0.0, ai="keep", qb=True),
    "live_ai_real": dict(lat=2, slip=0.0, exit_slip=0.0, ai="real", qb=True),
}
_VERDICTS: dict = {}


def real_veto(ch: str, pid: int, det: int):
    """The bot's own AI review (ai_verdicts_last30.csv, gpt-4o-mini): cancel the unfilled orders at det + the measured
    response time when the verdict is a clear no; no verdict / an error -> kept (the bot fails open)."""
    if not _VERDICTS:
        f = OUT / "ai_verdicts_last30.csv"
        if f.exists():
            v = pd.read_csv(f)
            for r in v.itertuples():
                _VERDICTS[(r.channel, int(r.post_id))] = (bool(r.ok), str(r.error) if isinstance(r.error, str) else "",
                                                          float(r.latency_s))
    hit = _VERDICTS.get((ch, int(pid)))
    if hit is None or hit[0] or hit[1]:
        return None
    return det + int(np.ceil(hit[2]))
AI_DELAY = 3                 # seconds from arming to the AI verdict (gpt-4o-mini round trip)


# ------------------------------------------------------------------ data
def load_posts() -> pd.DataFrame:
    rows = []
    for f in glob.glob(str(ROOT / "data/telegram/history/*.jsonl")):
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


def load_ticks(sym: str) -> dict:
    ms = pd.period_range(START, pd.Timestamp(END) - pd.Timedelta(seconds=1), freq="M")
    parts = [dict(np.load(ROOT / "data/ticks_exness" / sym / f"{m}.npz")) for m in ms.astype(str)]
    tk = {k: np.concatenate([p[k] for p in parts]) for k in parts[0]}
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
    return next_t - prev_t >= GAP and ts - prev_t > 60


def simulate(name, tk, t_arm, buy_px, sell_px, sl_d, tp_d, cancel_after, stages, trail, veto_ts, slip, exit_slip):
    """One straddle from arming to the last exit -> (positions, close_ts).  Bars are processed second by second;
    the bot's management runs at t_arm, t_arm + 2, ... on the latest quote before that moment."""
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
                ok_sl = (sl == 0.0) or sl_placeable_now(p.side, sl, sym)
                ok_tp = (tp == 0.0) or (tp > sym.bid if p.side == BUY else tp < sym.ask)
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
                if new_sl is not None and sl_placeable_now(p.side, new_sl, sym):
                    p.sl = new_sl
                    p.be_stage += 1
            if trail is not None:                              # social trailing stop
                price = sym.bid if p.side == BUY else sym.ask
                new_sl = trailing_sl(p.side, p.fill, price, p.sl, trail.start, trail.distance, trail.step, sym)
                if new_sl is not None:
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
                elif hit_tp:
                    p.exit = first if first >= p.tp else p.tp
            else:
                first, lo, hi = tk["ask_first"][i], tk["ask_min"][i], tk["ask_max"][i]
                hit_sl = p.sl and (first >= p.sl or hi >= p.sl)
                hit_tp = p.tp and (first <= p.tp or lo <= p.tp)
                if hit_sl:
                    p.exit = (first if first >= p.sl else p.sl) + exit_slip * sp
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
            pos.append(Pos(BUY, b, fill, "BUY", best=fill))
            del pend["BUY"]
        if "SELL" in pend and tk["bid_min"][i] <= pend["SELL"]:
            fill = min(pend["SELL"], bf) - slip * sp
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
def replay(cfg, posts, ticks, windows, sc) -> tuple[pd.DataFrame, pd.DataFrame]:
    mode = cfg.keyword_match
    prof = cfg.telegram_feed.profile_for(cfg.x_feed.defaults)
    et, nb, comp = cfg.x_feed.emoji_trigger, cfg.news_blackout, cfg.companion
    stages = break_even_stages(cfg.strategy) if cfg.strategy.break_even_enabled else []
    trail = cfg.social_trailing_stop if (cfg.social_trailing_stop.enabled and "telegram" in cfg.social_trailing_stop.feeds) else None
    ctrail = comp.trailing if comp.trailing.enabled else None
    cstages = break_even_stages(comp) if comp.break_even_enabled else []
    gmo = cfg.global_max_open
    cap = gmo.max_open if (gmo.enabled and "telegram" in gmo.feeds) else 10**9
    per_channel = prof.max_open
    gold, nas = ticks[cfg.symbol], ticks[comp.symbol]
    wstart = np.array([w[0] for w in windows])
    open_gold: list = []          # (close_ts, channel)
    open_comp_until = -1
    recent: dict = {}
    decisions, trades = [], []
    gold_end, nas_end = int(gold["t"][-1]), int(nas["t"][-1])
    for p in posts.itertuples():
        det = int(p.ts) + sc["lat"]
        if det > gold_end:
            decisions.append((p.ts, p.ch, "no price data yet"))
            continue
        flag = emoji_flag(p.text, et, mode)
        ok, why = post_tradable(p, prof, mode, sc["lat"], keyword_bypass=bool(flag))
        if not ok:
            decisions.append((p.ts, p.ch, why))
            continue
        # _social_open_blocked, in the bot's order
        k = np.searchsorted(wstart, det, side="right")
        if any(w[0] <= det < w[1] for w in windows[max(0, k - 40):k]) and "telegram" in nb.feeds and nb.enabled:
            decisions.append((p.ts, p.ch, "USD news blackout"))
            continue
        open_gold = [g for g in open_gold if g[0] > det]
        if len([g for g in open_gold if g[1] == p.ch]) >= per_channel:
            decisions.append((p.ts, p.ch, "channel max_open"))
            continue
        if len(open_gold) >= cap:
            decisions.append((p.ts, p.ch, "global cap"))
            continue
        key = content_key(p.text)
        recent = {kk: v for kk, v in recent.items() if det - v <= 600}
        if key and key in recent:
            decisions.append((p.ts, p.ch, "duplicate content"))
            continue
        if key:
            recent[key] = det
        if market_shut(gold, det):
            decisions.append((p.ts, p.ch, "market shut (orders rejected)"))
            continue
        j = int(np.searchsorted(gold["t"], det, side="left" if sc.get("qb") else "right")) - 1
        sym = sym_info(cfg.symbol, gold, j)
        buy = round_price(sym.ask + prof.entry_offset, sym)
        sell = round_price(sym.bid - prof.entry_offset, sym)
        if sc["ai"] == "real":
            veto = None if flag else real_veto(p.ch, p.id, det)
        else:
            veto = det + AI_DELAY if (not flag and ai_vetoes(p.text, sc["ai"])) else None
        pos, close = simulate(cfg.symbol, gold, det, buy, sell, prof.stop_loss, prof.take_profit,
                              prof.cancel_after_seconds, stages, trail, veto, sc["slip"], sc["exit_slip"])
        open_gold.append((close, p.ch))
        decisions.append((p.ts, p.ch, "ARMED" + (f" ({flag} fast track)" if flag else "")))
        base = dict(post_ts=int(p.ts), channel=p.ch, post_id=int(p.id), flag=flag or "", text=p.text[:200],
                    armed_ts=det, ai_veto=veto is not None)
        lot = prof.lot
        for q in pos:
            trades.append(dict(base, symbol=cfg.symbol, side=q.side, fill_ts=q.fill_ts, fill=q.fill, exit_ts=q.exit_ts,
                               exit=q.exit, exit_reason=q.why, lot=lot,
                               usd=(q.exit - q.fill) * (1 if q.side == BUY else -1) * lot * SPEC[cfg.symbol]["contract"]))
        if not pos:
            trades.append(dict(base, symbol=cfg.symbol, side="", fill_ts=0, fill=np.nan, exit_ts=close, exit=np.nan,
                               exit_reason="no fill" + (" (AI veto)" if veto is not None and close < det + prof.cancel_after_seconds else ""),
                               lot=lot, usd=0.0))
        # companion (USTECm): only when gold armed, and only if no companion is open
        if comp.enabled and "telegram" in comp.feeds and det > nas_end:
            trades.append(dict(base, symbol=comp.symbol, side="", fill_ts=0, fill=np.nan, exit_ts=0, exit=np.nan,
                               exit_reason="no Nasdaq price data yet", lot=comp.lot, usd=0.0))
        elif comp.enabled and "telegram" in comp.feeds and det >= open_comp_until and not market_shut(nas, det):
            jn = int(np.searchsorted(nas["t"], det, side="left" if sc.get("qb") else "right")) - 1
            nsym = sym_info(comp.symbol, nas, jn)
            nb_, ns_ = round_price(nsym.ask + comp.entry_offset, nsym), round_price(nsym.bid - comp.entry_offset, nsym)
            cpos, cclose = simulate(comp.symbol, nas, det, nb_, ns_, comp.stop_loss, comp.take_profit,
                                    comp.cancel_after_seconds, cstages, ctrail, veto, sc["slip"], sc["exit_slip"])
            open_comp_until = cclose
            for q in cpos:
                trades.append(dict(base, symbol=comp.symbol, side=q.side, fill_ts=q.fill_ts, fill=q.fill,
                                   exit_ts=q.exit_ts, exit=q.exit, exit_reason=q.why, lot=comp.lot,
                                   usd=(q.exit - q.fill) * (1 if q.side == BUY else -1) * comp.lot
                                   * SPEC[comp.symbol]["contract"]))
    dec = pd.DataFrame(decisions, columns=["post_ts", "channel", "decision"])
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
        tag = name if END == "2026-11-01" else f"{name}_to_{END}"
        tr.to_csv(OUT / f"trades_{tag}.csv", index=False)
        dec.to_csv(OUT / f"decisions_{tag}.csv", index=False)
        res[name] = dict(settings=SCENARIOS[name], summary=summary(tr),
                         decisions=dec.decision.str.replace(r" \(.*", "", regex=True).value_counts().to_dict())
        print(name, json.dumps(res[name]["summary"]), flush=True)
    (OUT / ("summary.json" if END == "2026-11-01" else f"summary_to_{END}.json")).write_text(
        json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    main()
