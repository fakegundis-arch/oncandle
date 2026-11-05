"""Replay a historical period through the LIVE loop (newsbot.bot.Bot) with a simulated clock, historical M1 bars as
the broker's prices and the historical calendar as schedule + actual sources.  Used to check that the live code
path takes exactly the trades of the backtest (research/check_replay.py)."""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import pandas as pd

from .broker import MT5Broker, Position
from .events import Figure, Release, releases_from_frame


class Clock:
    def __init__(self, t: datetime):
        self.t = t

    def __call__(self) -> datetime:
        return self.t


class ReplaySchedule:
    """Weekly-JSON stand-in: the releases of the next 7 days with forecast / previous but no actual."""

    def __init__(self, calendar: pd.DataFrame, clock: Clock):
        self.rels, self.clock = releases_from_frame(calendar), clock

    def upcoming(self) -> list[Release]:
        now = self.clock()
        out = []
        for r in self.rels:
            if now - timedelta(days=1) <= r.time <= now + timedelta(days=7):
                out.append(Release(r.time, r.currency, [Figure(f.name, math.nan, f.forecast, f.previous, None, f.kind,
                                                               f.polarity) for f in r.figures]))
        return out


class ReplayActuals:
    """FF-page stand-in: the actuals become visible `latency_s` seconds after the release."""

    def __init__(self, calendar: pd.DataFrame, clock: Clock, latency_s: float = 30):
        self.rels = {(r.time, r.currency): r for r in releases_from_frame(calendar)}
        self.clock, self.lat = clock, timedelta(seconds=latency_s)

    def fetch(self, t: datetime, ccy: str):
        r = self.rels.get((t, ccy))
        if r is None or self.clock() < t + self.lat:
            return None
        return [dict(name=f.name, actual=f.actual, forecast=f.forecast, previous=f.previous, verdict=f.verdict,
                     impact="high") for f in r.figures]


class ReplayBroker(MT5Broker):
    """Prices from historical bid M1 bars; ask = bid + cost (x news_mult from a release minute to news_window minutes
    after it, as the protocol).  A position keeps the spread it was opened with and a short pays it on its exit (as
    newsbot.backtest.simulate).  Fills and stop / target checks follow the backtest's rules (entry minute: stop only;
    stop before target; gaps fill at the open)."""

    def __init__(self, frames: dict, costs: dict, clock: Clock, equity: float = 1000.0, news_times=(),
                 news_mult: float = 2.0, news_window: int = 5):
        super().__init__({}, {}, dry_run=True)
        self.frames, self.costs, self.clock, self.eq = frames, costs, clock, equity
        self.news = sorted(pd.Timestamp(t) for t in news_times)
        self.news_mult, self.news_window = news_mult, news_window

    def spread(self, sym: str, t: pd.Timestamp) -> float:
        import bisect
        i = bisect.bisect_right(self.news, t) - 1                 # latest release at or before t
        if i >= 0 and t - self.news[i] <= pd.Timedelta(minutes=self.news_window):
            return self.costs[sym] * self.news_mult
        return self.costs[sym]

    def equity(self) -> float:
        return self.eq

    def bars_m1(self, sym: str, count: int = 3000) -> pd.DataFrame:
        m = self.frames[sym]
        i = m.index.searchsorted(pd.Timestamp(self.clock()).floor("min"))
        return m.iloc[max(0, i - count): i]

    def tick(self, sym: str):
        m = self.frames[sym]
        t = pd.Timestamp(self.clock()).floor("min")
        if t in m.index:
            bid = float(m.open.loc[t])
            return bid, bid + self.spread(sym, t), t.to_pydatetime()
        i = m.index.searchsorted(t) - 1
        return float(m.close.iloc[i]), float(m.close.iloc[i]) + self.spread(sym, m.index[i]), m.index[i].to_pydatetime()

    def lots_for(self, sym, direction, entry, sl, risk_money):
        return 1.0, abs(entry - sl)

    def open(self, pos: Position):
        self._paper_ticket += 1
        pos.ticket = self._paper_ticket
        bid, ask, _ = self.tick(pos.symbol)
        pos.extra["spread"] = ask - bid                       # the trade's spread (a short pays it on its exit)
        return pos

    def _pos_spread(self, pos: Position) -> float:
        return float(pos.extra.get("spread", self.costs[pos.symbol]))

    def is_open(self, pos: Position) -> bool:
        m = self.frames[pos.symbol]
        t0 = pd.Timestamp(pos.opened).floor("min")
        w = m[(m.index >= t0) & (m.index < pd.Timestamp(self.clock()).floor("min"))]
        c = self._pos_spread(pos) if pos.direction < 0 else 0.0
        d = pos.direction
        for t, r in w.iterrows():
            first = t == t0
            op, hi, lo = r.open + c, r.high + c, r.low + c
            if not first:
                if (d > 0 and op <= pos.sl) or (d < 0 and op >= pos.sl):
                    return self._done(pos, op, "stop-gap", t)
                if pos.tp and ((d > 0 and op >= pos.tp) or (d < 0 and op <= pos.tp)):
                    return self._done(pos, op, "target-gap", t)
            if (d > 0 and lo <= pos.sl) or (d < 0 and hi >= pos.sl):
                return self._done(pos, pos.sl, "stop", t)
            if not first and pos.tp and ((d > 0 and hi >= pos.tp) or (d < 0 and lo <= pos.tp)):
                return self._done(pos, pos.tp, "target", t)
        return True

    def _done(self, pos, px, why, t):
        pos.closed, pos.exit_price, pos.exit_reason = True, float(px), why
        pos.extra["exit_time"] = str(t)
        return False

    def close(self, pos: Position, why: str = "time") -> bool:
        bid, ask, t = self.tick(pos.symbol)
        pos.closed, pos.exit_price, pos.exit_reason = True, (bid if pos.direction > 0 else bid + self._pos_spread(pos)), why
        pos.extra["exit_time"] = str(t)
        return True
