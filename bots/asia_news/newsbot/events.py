"""Forex Factory events -> releases.

A *figure* is one calendar line (e.g. "CPI y/y" with actual / forecast / previous and FF's better/worse verdict).
A *release* is every high-impact figure of one currency published in the same minute (AUD CPI m/m + CPI y/y +
Trimmed Mean CPI m/m at 01:30 UTC are ONE release).  The same code is used for the historical calendar (backtest)
and the live feeds, so both see identical releases.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime

ASIAN_CCY = ("AUD", "NZD", "JPY", "CNY")
ASIA_START_H, ASIA_END_H = 21.75, 7.0          # 21:45 .. 07:00 UTC (protocol)


def parse_value(x) -> float:
    """'65.2K' -> 65200, '-0.7%' -> -0.7, '<0.75%' -> 0.75, '' / None / nan -> nan."""
    if x is None:
        return math.nan
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return math.nan
    v = float(m.group(0))
    tail = s[m.end():].strip().upper()
    v *= {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(tail[:1], 1.0)
    return v


# kind, polarity (+1: a higher number is good for the currency, -1: lower is good)
_NO_FIGURE = ("speaks", "speech", "statement", "conference", "report", "election", "minutes", "testifies",
              "meeting", "summary", "holiday")


def classify(name: str) -> tuple[str, int] | None:
    """Return (kind, polarity) of a figure, or None for events without a tradable number (speeches, statements)."""
    n = name.lower()
    if any(w in n for w in _NO_FIGURE):
        return None
    if "unemployment" in n or "jobless" in n or "claimant" in n:
        return "EMP", -1
    if "employment" in n or "payroll" in n or "jobs" in n:
        return "EMP", 1
    if "cpi" in n or "inflation" in n or "ppi" in n:
        return "CPI", 1
    if "gdp" in n:
        return "GDP", 1
    if "cash rate" in n or "policy rate" in n or "interest rate" in n or "loan prime" in n:
        return "RATE", 1
    if "trade balance" in n or "pmi" in n or "retail sales" in n or "production" in n or "spending" in n:
        return "ACT", 1
    return "OTHER", 1


@dataclass
class Figure:
    name: str
    actual: float
    forecast: float
    previous: float
    verdict: int | None = None        # FF: 1 better / 2 worse for the currency / 0 in line; None = unknown (JSON feed)
    kind: str = "OTHER"
    polarity: int = 1

    @property
    def has_actual(self) -> bool:
        return not math.isnan(self.actual)


@dataclass
class Release:
    time: datetime                    # UTC, minute precision, naive
    currency: str
    figures: list[Figure] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return self.figures[0].kind if self.figures else "NONE"

    def key(self) -> str:
        return f"{self.currency} {self.kind} {self.time:%Y-%m-%d %H:%M}"


def in_asia(t: datetime) -> bool:
    h = t.hour + t.minute / 60
    return h >= ASIA_START_H or h < ASIA_END_H


def is_target_event(currency: str, impact: str, t: datetime) -> bool:
    """The protocol's universe: Forex Factory HIGH impact, Asian currency, released 21:45-07:00 UTC."""
    return str(impact).lower() == "high" and currency in ASIAN_CCY and in_asia(t)


def make_figure(name, actual, forecast, previous, verdict=None) -> Figure | None:
    k = classify(str(name))
    if k is None:
        return None
    v = None if verdict is None or (isinstance(verdict, float) and math.isnan(verdict)) else int(verdict)
    return Figure(str(name), parse_value(actual), parse_value(forecast), parse_value(previous), v, k[0], k[1])


def releases_from_frame(cal) -> list[Release]:
    """Historical calendar (DataFrame with Forex Factory columns time_utc, currency, impact, name, actual, forecast,
    previous, better_worse) -> list of releases with an actual value, sorted by time."""
    out: dict[tuple, Release] = {}
    for r in cal.itertuples(index=False):
        t = r.time_utc.to_pydatetime().replace(tzinfo=None)
        if not is_target_event(r.currency, r.impact, t):
            continue
        f = make_figure(r.name, r.actual, r.forecast, r.previous, getattr(r, "better_worse", None))
        if f is None or not f.has_actual:
            continue
        out.setdefault((t, r.currency), Release(t, r.currency)).figures.append(f)
    return sorted(out.values(), key=lambda x: (x.time, x.currency))
