"""v2 Nasdaq entry (entry = "pair_reaction"): direction rule, backtest, live loop on synthetic data only."""
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from newsbot.backtest import make_trades  # noqa: E402
from newsbot.bot import Bot  # noqa: E402
from newsbot.config import DEFAULTS  # noqa: E402
from newsbot.events import Release, make_figure, releases_from_frame  # noqa: E402
from newsbot.replay import Clock, ReplayActuals, ReplayBroker, ReplaySchedule  # noqa: E402
from newsbot.strategy import make_plan, pre_release_close, reaction_direction, reaction_from_prices  # noqa: E402

V2 = json.loads((HERE.parent / "LOCKED_NQ.json").read_text())["versions"]["nasdaq_v2"]
T_REL = pd.Timestamp("2027-01-27 00:30")          # a Wednesday


def bars(start, end, px, step=0.0, noise=0.0, seed=0):
    idx = pd.date_range(start, end, freq="1min")
    rng = np.random.default_rng(seed)
    p = px + np.cumsum(rng.normal(0, noise, len(idx))) if noise else np.full(len(idx), float(px))
    p = p + step * np.arange(len(idx))
    return pd.DataFrame({"open": p, "high": p + abs(step) + noise, "low": p - abs(step) - noise, "close": p}, index=idx)


def rel(ccy="AUD", t=T_REL):
    return Release(t.to_pydatetime(), ccy, [make_figure("CPI y/y", "3.4%", "3.1%", "3.2%", 1)])


def pair_with_jump(jump):
    """AUDUSD flat at 0.70000, +jump from the release minute on."""
    p = bars(T_REL - pd.Timedelta(hours=2), T_REL + pd.Timedelta(hours=8), 0.70)
    p.loc[T_REL:, ["open", "high", "low", "close"]] += jump
    return p


def test_reaction_direction_rule():
    r = rel()
    up, dn, flat = pair_with_jump(0.0010), pair_with_jump(-0.0010), pair_with_jump(0.0)
    assert reaction_direction(r, V2, up).direction == 1             # AUD stronger -> buy NAS100
    assert reaction_direction(r, V2, dn).direction == -1            # AUD weaker -> sell NAS100
    assert reaction_direction(r, V2, flat).direction == 0
    rx = reaction_direction(r, V2, up)
    assert rx.pre == 0.70 and abs(rx.post - 0.7010) < 1e-12 and rx.post_time == datetime(2027, 1, 27, 0, 32)
    # the pre-release close must be recent, the post-release bar must exist
    gap = up[(up.index < T_REL - pd.Timedelta(minutes=10)) | (up.index >= T_REL)]
    assert reaction_direction(r, V2, gap) is None
    hole = up[(up.index < T_REL) | (up.index > T_REL + pd.Timedelta(minutes=6))]
    assert reaction_direction(r, V2, hole) is None
    # JPY is not traded by v2 (its BoJ minute is not known in advance); a yen version would invert USDJPY
    assert reaction_direction(rel("JPY"), V2, up) is None
    yen = {**V2, "currencies": ["JPY"], "signal_pairs": {"JPY": ["USDJPY", -1]}, "map": {"nasdaq": {"JPY": -1}}}
    assert reaction_from_prices(rel("JPY"), yen, 150.0, 149.5, None).direction == -1  # yen stronger -> sell NAS100
    assert pre_release_close(r, V2, up) == 0.70


def test_make_plan_needs_reaction():
    r = rel()
    nq = bars(T_REL - pd.Timedelta(days=3), T_REL + pd.Timedelta(hours=8), 20000, noise=5.0, seed=3)
    assert make_plan(r, V2, nq) is None                               # no reaction -> no plan
    p = make_plan(r, V2, nq, reaction=reaction_direction(r, V2, pair_with_jump(0.001)))
    assert p.direction == 1 and p.entry_after == datetime(2027, 1, 27, 0, 32)
    assert p.exit_by == datetime(2027, 1, 27, 6, 32) and math.isinf(p.target_dist) and p.stop_dist > 0


def calendar():
    return pd.DataFrame([dict(time_utc=T_REL, currency="AUD", impact="high", name="CPI y/y", actual="3.4%",
                              forecast="3.1%", previous="3.2%", better_worse=1),
                         dict(time_utc=T_REL + pd.Timedelta(hours=3), currency="JPY", impact="high",
                              name="BOJ Policy Rate", actual="1.00%", forecast="0.75%", previous="0.75%",
                              better_worse=1)])


def frames(jump=-0.0010):
    nq = bars(T_REL - pd.Timedelta(days=3), T_REL + pd.Timedelta(hours=10), 20000, step=-0.05, noise=2.0, seed=5)
    return {"NAS100": nq, "AUDUSD": pair_with_jump(jump)}


def test_make_trades_pair_reaction():
    f = frames(-0.0010)
    tr = make_trades(V2, calendar(), f["NAS100"], 1.5, detail=True, aux={"AUDUSD": f["AUDUSD"]})
    assert len(tr) == 1                                               # the JPY release is not traded
    t = tr.iloc[0]
    assert t.dir == -1 and t.entry_time == T_REL + pd.Timedelta(minutes=2) and t.reason == "time"
    assert t.exit_time == T_REL + pd.Timedelta(minutes=362)
    # short entered inside the news window: sells at the bid, pays 2 x 1.5 on the exit
    nq = f["NAS100"]
    assert t.entry == nq.open.loc[T_REL + pd.Timedelta(minutes=2)]
    assert abs(t.exit - (nq.open.loc[T_REL + pd.Timedelta(minutes=362)] + 3.0)) < 1e-9
    # "entry 2 min later" moves the entry, not the signal
    late = make_trades(V2, calendar(), nq, 1.5, entry_delay=4, aux={"AUDUSD": f["AUDUSD"]})
    assert late.entry_time.iloc[0] == T_REL + pd.Timedelta(minutes=4) and late.dir.iloc[0] == -1


def test_live_loop_matches_backtest():
    f = frames(+0.0010)
    cal = calendar()
    clock = Clock(T_REL.to_pydatetime() - timedelta(minutes=5))
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    cfg["general"].update(state_file="", journal_file="")
    broker = ReplayBroker(f, {"NAS100": 1.5, "AUDUSD": 0.00015}, clock, news_times=[r.time for r in releases_from_frame(cal)])
    bot = Bot(cfg, {"nasdaq_v2": V2}, ReplaySchedule(cal, clock), ReplayActuals(cal, clock, 1e9), broker, clock)
    t = clock.t
    while t <= T_REL.to_pydatetime() + timedelta(hours=7):
        clock.t = t
        bot.step()
        t += timedelta(seconds=30)
    assert len(bot.closed) == 1 and not bot.positions
    p = bot.closed[0]
    bt = make_trades(V2, cal, f["NAS100"], 1.5, aux={"AUDUSD": f["AUDUSD"]})
    assert p.direction == bt.dir.iloc[0] == 1                         # no actual was ever available: price-led
    assert pd.Timestamp(p.opened).floor("min") == bt.entry_time.iloc[0]
    assert abs(p.direction * (p.exit_price - p.entry) / abs(p.entry - p.sl) - bt.r.iloc[0]) < 1e-9
    assert any(k.startswith("nasdaq_v2|AUD") and v.startswith("entered") for k, v in bot.done.items())


def test_live_loop_flat_pair_no_trade_and_signal_only():
    f = frames(0.0)
    cal = calendar()
    clock = Clock(T_REL.to_pydatetime())
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    cfg["general"].update(state_file="", journal_file="")
    bot = Bot(cfg, {"nasdaq_v2": V2}, ReplaySchedule(cal, clock), ReplayActuals(cal, clock, 30),
              ReplayBroker(f, {"NAS100": 1.5, "AUDUSD": 0.00015}, clock), clock)
    for m in range(0, 6):
        clock.t = T_REL.to_pydatetime() + timedelta(minutes=m)
        bot.step()
    assert not bot.positions and any(v.startswith("no trade") for v in bot.done.values())

    class SignalOnly:
        signal_only = True

        def is_open(self, p):
            return False

    bot = Bot(cfg, {"nasdaq_v2": V2}, ReplaySchedule(cal, clock), ReplayActuals(cal, clock, 30), SignalOnly(), clock)
    clock.t = T_REL.to_pydatetime()
    bot.step()
    assert not bot.entries and any("signal-only" in v for v in bot.done.values())


def test_replay_broker_news_spread():
    f = frames()
    clock = Clock(T_REL.to_pydatetime() + timedelta(minutes=2))
    b = ReplayBroker(f, {"NAS100": 1.5, "AUDUSD": 0.00015}, clock, news_times=[T_REL])
    bid, ask, _ = b.tick("NAS100")
    assert abs(ask - bid - 3.0) < 1e-9                                # 2 x spread within 5 min of the release
    clock.t = T_REL.to_pydatetime() + timedelta(minutes=6)
    bid, ask, _ = b.tick("NAS100")
    assert abs(ask - bid - 1.5) < 1e-9
