"""Trade plan shared by the backtest and the live bot: release -> (direction, stop distance, target distance,
time exit).  Prices are BID M1 bars (pandas DataFrame indexed by UTC minute with open/high/low/close).

Two entry modes (cfg["entry"]):
  "news"           (v1) direction from the Forex Factory verdicts of the release (newsbot.signal), entry at
                   release + entry_delay minutes.  Needs the actual.
  "pair_reaction"  (v2, Nasdaq) direction from the released currency's OWN pair reaction: the pair's bid from the close
                   of the minute before the release to the open of minute release + react_min; currency stronger ->
                   cfg map +1 (buy NAS100 for AUD / NZD).  Entry at release + entry_delay at market.  Needs prices of
                   the signal pair, NOT the actual (see reaction_direction)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from .events import Release
from .signal import DEFAULT_MAP, currency_bias, instrument_direction

DEFAULT_CFG = {
    "instrument": "gold",          # gold | nasdaq | pair
    "symbol": "XAUUSD",            # research symbol (the broker maps it to the MT5 name)
    "currencies": ["AUD", "NZD", "JPY", "CNY"],
    "kinds": ["CPI", "EMP", "GDP", "RATE", "ACT", "OTHER"],
    "signal": {"vote": "ff", "inline": "none"},
    "map": None,                   # None = signal.DEFAULT_MAP
    "entry_delay": 1,              # minutes after the release minute (1 = open of the next minute)
    "confirm": 0,                  # 1 = trade only if the release-minute move of the traded symbol agrees
    "stop_atr_tf": 60,             # ATR bar length in minutes
    "stop_atr_n": 24,              # number of ATR bars (before the release)
    "stop_k": 1.0,                 # stop = k x ATR
    "target_r": 2.0,               # target in R (0 = no target, time exit only)
    "hold_min": 120,               # time exit, minutes after entry
    "news_mult": 2.0,              # spread multiplier for fills within `news_window` minutes of the release
    "news_window": 5,
    # --- v2 "pair_reaction" entry (ignored by entry = "news")
    "entry": "news",               # "news" (v1, FF verdict) | "pair_reaction" (v2, direction from the pair's reaction)
    "signal_pairs": {"AUD": ["AUDUSD", 1], "NZD": ["NZDUSD", 1], "JPY": ["USDJPY", -1]},   # pair, +1 = ccy is base
    "react_min": 2,                # the pair's move is read from the pre-release close to the open of release + react_min
    "react_min_move": 0.0,         # minimum |pair move| (price units) to trade; 0 = any non-zero move
    "pre_gap_max": 5,              # the pair's pre-release close must be at most this many minutes before the release
}


@dataclass
class Plan:
    release: Release
    direction: int                 # +1 buy, -1 sell
    stop_dist: float               # price units
    target_dist: float             # price units (inf = none)
    entry_after: datetime          # earliest entry time (UTC)
    exit_by: datetime              # time exit (UTC) relative to the planned entry
    why: str


def full_cfg(cfg: dict) -> dict:
    out = {**DEFAULT_CFG, **cfg}
    out["signal"] = {**DEFAULT_CFG["signal"], **(cfg.get("signal") or {}), "kinds": out["kinds"]}
    return out


def atr(bars: pd.DataFrame, before: datetime, tf_min: int, n: int) -> float:
    """Mean true range of `n` bars of `tf_min` minutes built from M1 bars strictly before `before`."""
    w = bars.loc[before - timedelta(minutes=tf_min * (n + 1) * 3): before - timedelta(minutes=1)]
    if len(w) < 10:
        return math.nan
    agg = w.resample(f"{tf_min}min").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    agg = agg.iloc[-(n + 1):]
    pc = agg.close.shift(1)
    tr = pd.concat([agg.high - agg.low, (agg.high - pc).abs(), (agg.low - pc).abs()], axis=1).max(axis=1)
    tr = tr.iloc[1:]
    return float(tr.mean()) if len(tr) else math.nan


def weekend_cap(entry: datetime, exit_by: datetime) -> datetime:
    """No positions over the weekend: a trade is closed by Friday 20:00 UTC at the latest."""
    fri = (entry + timedelta(days=(4 - entry.weekday()) % 7)).replace(hour=20, minute=0, second=0, microsecond=0)
    if entry >= fri:
        fri += timedelta(days=7)
    return min(exit_by, fri)


def confirmed(direction: int, pre_close: float, entry_bid: float) -> bool:
    """Optional filter: the traded symbol already moved in the trade's direction during the release minute."""
    return (entry_bid - pre_close) * direction > 0


@dataclass
class Reaction:
    direction: int                 # +1 buy / -1 sell the traded symbol, 0 = no trade
    pair: str
    pre: float                     # pair bid: close of the last bar before the release
    post: float                    # pair bid: open of the first bar at / after release + react_min
    post_time: datetime
    why: str


def signal_pair(rel_ccy: str, cfg: dict) -> tuple[str, int] | None:
    sp = full_cfg(cfg)["signal_pairs"].get(rel_ccy)
    return (sp[0], int(sp[1])) if sp else None


def pre_release_close(rel: Release, cfg: dict, pair_bars: pd.DataFrame) -> float | None:
    """Close of the signal pair's last M1 bar before the release minute (None if older than pre_gap_max minutes)."""
    c = full_cfg(cfg)
    if pair_bars is None or len(pair_bars) == 0:
        return None
    t0 = pd.Timestamp(rel.time)
    i = pair_bars.index.searchsorted(t0) - 1
    if i < 0 or t0 - pair_bars.index[i] > timedelta(minutes=int(c["pre_gap_max"])):
        return None
    return float(pair_bars.close.iat[i])


def reaction_from_prices(rel: Release, cfg: dict, pre: float, post: float, post_time: datetime) -> Reaction | None:
    """THE direction rule of entry = "pair_reaction" (shared by the backtest and the live bot): the released currency's
    pair moved from `pre` (bid, close before the release) to `post` (bid, first price at / after release + react_min);
    currency stronger -> map[instrument][currency] (+1 = buy NAS100 for AUD / NZD); no move -> direction 0."""
    c = full_cfg(cfg)
    sp = signal_pair(rel.currency, c)
    if sp is None or rel.currency not in c["currencies"] or pre is None or post is None:
        return None
    sym, base = sp
    mv = post - pre
    mp = {**DEFAULT_MAP, **(c["map"] or {})}.get(c["instrument"], {})
    d = 0
    if abs(mv) > float(c["react_min_move"]) and mv != 0:
        d = (1 if mv > 0 else -1) * base * int(mp.get(rel.currency, 0))
    why = (f"{rel.key()} {sym} {pre:.5f} -> {post:.5f} ({mv:+.5f}) at +{int(c['react_min'])} min: "
           f"{rel.currency} {'stronger' if mv * base > 0 else 'weaker' if mv != 0 else 'unchanged'}")
    return Reaction(d, sym, pre, post, post_time, why)


def reaction_direction(rel: Release, cfg: dict, pair_bars: pd.DataFrame, max_gap_min: int = 2) -> Reaction | None:
    """Backtest form: pre = close of the pair's last bar before the release (pre_gap_max), post = OPEN of its first bar
    at / after release + react_min (None if that bar is more than `max_gap_min` minutes late)."""
    c = full_cfg(cfg)
    pre = pre_release_close(rel, c, pair_bars)
    if pre is None:
        return None
    t1 = pd.Timestamp(rel.time) + timedelta(minutes=int(c["react_min"]))
    j = pair_bars.index.searchsorted(t1)
    if j >= len(pair_bars) or pair_bars.index[j] - t1 > timedelta(minutes=max_gap_min):
        return None
    return reaction_from_prices(rel, c, pre, float(pair_bars.open.iat[j]), pair_bars.index[j].to_pydatetime())


def make_plan(rel: Release, cfg: dict, bars: pd.DataFrame | None, entry_delay: int | None = None,
              atr_value: float | None = None, reaction: Reaction | None = None) -> Plan | None:
    """`bars`: M1 bid bars of the traded symbol up to the release (only used for the ATR when `atr_value` is None).
    entry = "pair_reaction": the direction comes from `reaction` (reaction_direction); no reaction -> no plan."""
    c = full_cfg(cfg)
    if rel.currency not in c["currencies"]:
        return None
    if c["entry"] == "pair_reaction":
        if reaction is None or reaction.direction == 0:
            return None
        d = reaction.direction
        head = reaction.why
    else:
        b = currency_bias(rel, c["signal"])
        d = instrument_direction(b.bias, rel.currency, c["instrument"], c["symbol"], c["map"])
        head = None
    if d == 0:
        return None
    a = atr(bars, rel.time, int(c["stop_atr_tf"]), int(c["stop_atr_n"])) if atr_value is None else atr_value
    if not a > 0:
        return None
    stop = float(c["stop_k"]) * a
    tgt = float(c["target_r"]) * stop if c["target_r"] and c["target_r"] > 0 else math.inf
    delay = int(c["entry_delay"] if entry_delay is None else entry_delay)
    ent = rel.time + timedelta(minutes=delay)
    ex = weekend_cap(ent, ent + timedelta(minutes=int(c["hold_min"])))
    if head is not None:
        why = head
    else:
        why = f"{rel.key()} score {b.score:+d} ({b.why}: " + ", ".join(f"{n} {v:+d}" for n, v in b.votes) + ")"
    return Plan(rel, d, stop, tgt, ent, ex, why)
