"""Trade plan shared by the backtest and the live bot: release -> (direction, stop distance, target distance,
time exit).  Prices are BID M1 bars (pandas DataFrame indexed by UTC minute with open/high/low/close)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from .events import Release
from .signal import currency_bias, instrument_direction

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


def make_plan(rel: Release, cfg: dict, bars: pd.DataFrame | None, entry_delay: int | None = None,
              atr_value: float | None = None) -> Plan | None:
    """`bars`: M1 bid bars of the traded symbol up to the release (only used for the ATR when `atr_value` is None)."""
    c = full_cfg(cfg)
    if rel.currency not in c["currencies"]:
        return None
    b = currency_bias(rel, c["signal"])
    d = instrument_direction(b.bias, rel.currency, c["instrument"], c["symbol"], c["map"])
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
    why = f"{rel.key()} score {b.score:+d} ({b.why}: " + ", ".join(f"{n} {v:+d}" for n, v in b.votes) + ")"
    return Plan(rel, d, stop, tgt, ent, ex, why)
