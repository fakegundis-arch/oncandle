"""The ONE signal module shared by the backtest and the live bot.

Step 1  figure vote   each figure of a release votes +1 (good for the currency), -1 (bad) or 0 (in line / unknown):
          vote="ff"    Forex Factory's own better/worse verdict (1 -> +1, 2 -> -1, 0 -> 0); if FF gave no verdict
                       (e.g. the JSON feed, which has none), fall back to the computed sign below
          vote="calc"  sign(actual - forecast) x polarity (unemployment: lower is better)
Step 2  currency bias  sum of votes; > 0 bullish (+1), < 0 bearish (-1), 0 (all in line or a tie) -> no trade.
          tiebreak=[...]: when the votes cancel out (a split report, e.g. unemployment rate better but employment
          change worse), the first figure whose name contains one of these strings and has a non-zero vote decides
          (default: the unemployment rate, then the headline CPI) - the market's headline numbers.
          inline="previous": if every figure is in line with the forecast, use actual vs previous instead
          (e.g. a rate hike that was expected). Default "none" = no trade.
Step 3  direction per instrument
          pair    AUD -> AUDUSD, NZD -> NZDUSD (currency is the base: bullish = buy);
                  JPY -> USDJPY (currency is the quote: bullish yen = sell USDJPY)
          gold    bullish currency x map["gold"][ccy]   (+1 = buy gold when the currency is bullish)
          nasdaq  bullish currency x map["nasdaq"][ccy]
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .events import Release

PAIR = {"AUD": ("AUDUSD", 1), "NZD": ("NZDUSD", 1), "JPY": ("USDJPY", -1)}   # (pair, +1 = currency is the base)

DEFAULT_SIGNAL = {
    "vote": "ff",            # "ff" or "calc"
    "inline": "none",        # "none" or "previous"
    "tiebreak": [],          # e.g. ["unemployment rate", "cpi y/y", "cpi q/q"]
    "kinds": ["CPI", "EMP", "GDP", "RATE", "ACT", "OTHER"],   # figure kinds that may vote
}
# economically motivated defaults (see research.md): commodity currencies and gold move together, a stronger yen goes
# with gold up (both havens / weaker USD) and with Nasdaq down (carry unwind); strong AUD / NZD data = risk-on.
DEFAULT_MAP = {"gold": {"AUD": 1, "NZD": 1, "JPY": 1, "CNY": 1},
               "nasdaq": {"AUD": 1, "NZD": 1, "JPY": -1, "CNY": 1}}


def _sign(x: float) -> int:
    if x is None or math.isnan(x) or x == 0:
        return 0
    return 1 if x > 0 else -1


def figure_vote(f, vote: str = "ff") -> int:
    if vote == "ff" and f.verdict in (0, 1, 2):
        return {1: 1, 2: -1, 0: 0}[f.verdict]
    if math.isnan(f.forecast):
        return 0
    return _sign(f.actual - f.forecast) * f.polarity


@dataclass
class Bias:
    bias: int            # +1 bullish currency, -1 bearish, 0 no trade
    score: int
    votes: list          # [(figure name, vote)]
    why: str


def currency_bias(rel: Release, scfg: dict | None = None) -> Bias:
    s = {**DEFAULT_SIGNAL, **(scfg or {})}
    figs = [f for f in rel.figures if f.kind in s["kinds"] and f.has_actual]
    votes = [(f.name, figure_vote(f, s["vote"])) for f in figs]
    score = sum(v for _, v in votes)
    why = "vs forecast"
    if score == 0 and any(v for _, v in votes) and s["tiebreak"]:
        for key in s["tiebreak"]:
            hit = [v for n, v in votes if key in n.lower() and v != 0]
            if hit:
                score, why = hit[0], f"split -> {key}"
                break
    if s["inline"] == "previous" and figs and all(v == 0 for _, v in votes):
        votes = [(f.name, _sign(f.actual - f.previous) * f.polarity) for f in figs if not math.isnan(f.previous)]
        score = sum(v for _, v in votes)
        why = "in line -> vs previous"
    return Bias(_sign(score), score, votes, why)


def instrument_direction(bias: int, currency: str, instrument: str, symbol: str | None = None,
                         mapping: dict | None = None) -> int:
    """+1 buy / -1 sell / 0 no trade for `instrument` in {"pair", "gold", "nasdaq"}."""
    if bias == 0:
        return 0
    if instrument == "pair":
        if currency not in PAIR or (symbol is not None and PAIR[currency][0] != symbol):
            return 0          # a pair only trades its own currency's releases
        return bias * PAIR[currency][1]
    mp = {**DEFAULT_MAP, **(mapping or {})}
    return bias * int(mp.get(instrument, {}).get(currency, 0))
