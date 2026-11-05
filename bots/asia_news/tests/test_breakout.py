"""v3 Nasdaq entry (entry = "breakout"): range / levels, backtest fills, live loop with pending orders, MT5 orders.
Synthetic data only."""
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from newsbot.backtest import make_trades  # noqa: E402
from newsbot.bot import Bot  # noqa: E402
from newsbot.broker import MT5Broker  # noqa: E402
from newsbot.config import DEFAULTS  # noqa: E402
from newsbot.events import Release, make_figure, releases_from_frame  # noqa: E402
from newsbot.replay import Clock, ReplayActuals, ReplayBroker, ReplaySchedule  # noqa: E402
from newsbot.strategy import breakout_setup  # noqa: E402

V3 = json.loads((HERE.parent / "LOCKED_V3.json").read_text())["versions"]["nasdaq_v3"]
T_REL = pd.Timestamp("2027-01-27 00:30")          # a Wednesday
P0 = 20000.0
COST = 1.5


def nq(jump_at=None, o=0.0, h=0.0, l=0.0, after=None, both=False):
    """NAS100: +-5 bars (hourly ATR = 10 -> stop 5, buffer 0.5, target 15) up to the release + 2 min, then quiet +-2
    bars; optionally one breakout bar at `jump_at` (open / high / low offsets) and `after` = the level after it."""
    idx = pd.date_range(T_REL - pd.Timedelta(days=2), T_REL + pd.Timedelta(hours=8), freq="1min")
    df = pd.DataFrame({"open": P0, "high": P0 + 5, "low": P0 - 5, "close": P0}, index=idx)
    quiet = idx >= T_REL + pd.Timedelta(minutes=3)
    df.loc[quiet, "high"], df.loc[quiet, "low"] = P0 + 2, P0 - 2
    if jump_at is not None:
        t = T_REL + pd.Timedelta(minutes=jump_at)
        df.loc[t] = [P0 + o, P0 + h, P0 + l, P0 + (h + l) / 2]
        if after is not None:
            later = idx > t
            df.loc[later, ["open", "close"]] = P0 + after
            df.loc[later, "high"], df.loc[later, "low"] = P0 + after + 2, P0 + after - 2
    return df


def rel(ccy="AUD"):
    return Release(T_REL.to_pydatetime(), ccy, [make_figure("CPI y/y", "3.4%", "3.1%", "3.2%", 1)])


def calendar(ccy="AUD"):
    return pd.DataFrame([dict(time_utc=T_REL, currency=ccy, impact="high", name="CPI y/y", actual="3.4%",
                              forecast="3.1%", previous="3.2%", better_worse=1)])


def test_setup_levels_and_quote_rule():
    st, why = breakout_setup(rel(), V3, nq())
    assert why == "" and abs(st.atr - 10) < 1e-9
    assert st.hi == P0 + 5 and st.lo == P0 - 5                       # release .. release + 2 (+ pre-release close)
    assert abs(st.up - (P0 + 5.5)) < 1e-9 and abs(st.dn - (P0 - 5.5)) < 1e-9
    assert abs(st.stop_dist - 5) < 1e-9 and abs(st.target_dist - 15) < 1e-9
    assert st.place_at == datetime(2027, 1, 27, 0, 33) and st.expire_at == datetime(2027, 1, 27, 1, 33)
    b = nq().drop(T_REL)                                              # no quote at the release minute
    assert breakout_setup(rel(), V3, b)[0] is None
    assert breakout_setup(rel("JPY"), V3, nq())[0] is None            # JPY is not traded by v3


def test_buy_breakout_to_target():
    m = nq(jump_at=10, o=3, h=12, l=2, after=10)                     # 00:40, outside the 5-min news window
    m.loc[T_REL + pd.Timedelta(minutes=30), "high"] = P0 + 25        # 01:00 reaches the target
    t = make_trades(V3, calendar(), m, COST, detail=True)
    assert len(t) == 1
    r = t.iloc[0]
    assert r.dir == 1 and r.entry_time == T_REL + pd.Timedelta(minutes=10)
    assert abs(r.entry - (P0 + 5.5)) < 1e-9                           # the level (no slippage outside the window)
    assert r.reason == "target" and abs(r.r - 3.0) < 1e-9 and r.exit_time == T_REL + pd.Timedelta(minutes=30)


def test_fill_inside_news_window_pays_spread_and_slippage():
    m = nq(jump_at=3, o=1, h=12, l=0, after=8)                       # 00:33: spread 2 x 1.5, slippage 1.5
    t = make_trades(V3, calendar(), m, COST, detail=True).iloc[0]
    assert t.dir == 1 and abs(t.entry - (P0 + 5.5 + 1.5)) < 1e-9
    g = nq(jump_at=3, o=9, h=12, l=8, after=10)                      # opens beyond the level: fills at the open
    t = make_trades(V3, calendar(), g, COST, detail=True).iloc[0]
    assert abs(t.entry - (P0 + 9 + 3.0 + 1.5)) < 1e-9
    s = nq(jump_at=4, o=-5.3, h=-5.2, l=-12, after=-8)                    # sell stop: at the level minus slippage
    t = make_trades(V3, calendar(), s, COST, detail=True).iloc[0]
    assert t.dir == -1 and abs(t.entry - (P0 - 5.5 - 1.5)) < 1e-9
    # time exit 6 h after the fill; a short pays the trade's spread (2 x 1.5) on the exit
    assert t.reason == "time" and t.exit_time == T_REL + pd.Timedelta(minutes=4 + 360)
    assert abs(t.exit - (P0 - 8 + 3.0)) < 1e-9


def test_no_trigger_and_both_legs():
    assert len(make_trades(V3, calendar(), nq(), COST)) == 0          # quiet: the orders expire
    late = nq(jump_at=70, o=0, h=12, l=0, after=10)                   # after the 60-min window
    assert len(make_trades(V3, calendar(), late, COST)) == 0
    both = nq(jump_at=10, o=0, h=12, l=-12, after=0)                  # both levels in one bar: the worse is booked
    t = make_trades(V3, calendar(), both, COST, detail=True).iloc[0]
    assert t.r == -1.0 and t.reason == "stop"
    # "entry 2 minutes later": a market order 2 minutes after the trigger
    m = nq(jump_at=10, o=3, h=12, l=2, after=10)
    t = make_trades(V3, calendar(), m, COST, entry_delay=V3.get("entry_delay", 3) + 2, detail=True).iloc[0]
    assert t.entry_time == T_REL + pd.Timedelta(minutes=12) and abs(t.entry - (P0 + 10 + 1.5)) < 1e-9


def run_live(m, cal, minutes=430, state_file=""):
    clock = Clock(T_REL.to_pydatetime() - timedelta(minutes=2))
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    cfg["general"].update(state_file=state_file, journal_file="")
    broker = ReplayBroker({"NAS100": m}, {"NAS100": COST}, clock,
                          news_times=[r.time for r in releases_from_frame(cal)], stop_slip=1.0)
    bot = Bot(cfg, {"nasdaq_v3": V3}, ReplaySchedule(cal, clock), ReplayActuals(cal, clock, 1e9), broker, clock)
    t = clock.t
    while t <= T_REL.to_pydatetime() + timedelta(minutes=minutes):
        clock.t = t
        bot.step()
        t += timedelta(seconds=30)
    return bot, broker


def test_live_loop_matches_backtest():
    cal = calendar()
    for m in (nq(jump_at=10, o=3, h=12, l=2, after=10), nq(jump_at=3, o=1, h=12, l=0, after=8),
              nq(jump_at=4, o=-5.3, h=-5.2, l=-12, after=-8), nq(jump_at=3, o=9, h=12, l=8, after=10)):
        bot, broker = run_live(m, cal)
        bt = make_trades(V3, cal, m, COST)
        assert len(bot.closed) == 1 and not bot.positions and not bot.brk and not broker.orders
        p = bot.closed[0]
        assert p.direction == bt.dir.iloc[0] and pd.Timestamp(p.opened).floor("min") == bt.entry_time.iloc[0]
        assert abs(p.direction * (p.exit_price - p.entry) / abs(p.entry - p.sl) - bt.r.iloc[0]) < 1e-9
        assert any(v.startswith("entered") for v in bot.done.values())


def test_live_loop_expiry_cancels_orders():
    bot, broker = run_live(nq(), calendar(), minutes=70)
    assert not bot.closed and not bot.positions and not bot.brk and not broker.orders
    assert any(v.startswith("no breakout within 60 min") for v in bot.done.values())


def test_state_keeps_working_orders(tmp_path):
    sf = tmp_path / "state.json"
    m = nq()
    clock = Clock(T_REL.to_pydatetime())
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    cfg["general"].update(state_file=str(sf), journal_file="")
    cal = calendar()
    broker = ReplayBroker({"NAS100": m}, {"NAS100": COST}, clock, news_times=[T_REL])
    bot = Bot(cfg, {"nasdaq_v3": V3}, ReplaySchedule(cal, clock), ReplayActuals(cal, clock, 1e9), broker, clock)
    for k in range(0, 5):
        clock.t = T_REL.to_pydatetime() + timedelta(minutes=k)
        bot.step()
    assert len(broker.orders) == 2
    s = json.loads(sf.read_text())
    assert len(s["breakouts"]) == 1 and all(lg["ticket"] for lg in s["breakouts"][0]["legs"].values())
    bot2 = Bot(cfg, {"nasdaq_v3": V3}, ReplaySchedule(cal, clock), ReplayActuals(cal, clock, 1e9), broker, clock)
    assert len(bot2.brk) == 1                                          # a restart keeps watching the orders
    clock.t = T_REL.to_pydatetime() + timedelta(minutes=64)
    bot2.step()
    assert not bot2.brk and not broker.orders


def fake_mt5(expiration_ok=True):
    m = types.ModuleType("MetaTrader5")
    m.ORDER_TYPE_BUY, m.ORDER_TYPE_SELL, m.ORDER_TYPE_BUY_STOP, m.ORDER_TYPE_SELL_STOP = 0, 1, 4, 5
    m.TRADE_ACTION_DEAL, m.TRADE_ACTION_PENDING, m.TRADE_ACTION_SLTP, m.TRADE_ACTION_REMOVE = 1, 5, 6, 8
    m.ORDER_TIME_GTC, m.ORDER_TIME_SPECIFIED, m.TRADE_RETCODE_DONE, m.TRADE_RETCODE_INVALID_EXPIRATION = 0, 2, 10009, 10022
    m.ORDER_FILLING_FOK, m.ORDER_FILLING_IOC, m.ORDER_FILLING_RETURN = 0, 1, 2
    m.DEAL_ENTRY_IN, m.DEAL_ENTRY_OUT = 0, 1
    ns = types.SimpleNamespace
    m.sent, m.orders, m.positions = [], {}, []
    m.last_error = lambda: (0, "ok")
    m.symbol_info = lambda s: ns(digits=2, filling_mode=2)

    def order_send(req):
        m.sent.append(req)
        if req["action"] == m.TRADE_ACTION_PENDING:
            if req["type_time"] == m.ORDER_TIME_SPECIFIED and not expiration_ok:
                return ns(retcode=m.TRADE_RETCODE_INVALID_EXPIRATION, order=0, comment="invalid expiration")
            tk = 5000 + len(m.sent)
            m.orders[tk] = req
            return ns(retcode=10009, order=tk, comment="done")
        if req["action"] == m.TRADE_ACTION_REMOVE:
            m.orders.pop(req["order"], None)
        return ns(retcode=10009, order=0, comment="done")
    m.order_send = order_send
    m.orders_get = lambda ticket=None: tuple(v for k, v in m.orders.items() if k == ticket)
    m.positions_get = lambda symbol=None, ticket=None: tuple(m.positions)
    m.history_deals_get = lambda position=None: ()
    return m


def test_mt5_pending_orders():
    fm = fake_mt5()
    b = MT5Broker({"server_utc_offset_hours": 0, "magic": 7}, {"NAS100": "USTECm"}, dry_run=False)
    b.mt5 = fm
    exp = datetime(2027, 1, 27, 1, 33)
    tk = b.place_stop("NAS100", 1, 20005.504, 20000.504, 20020.504, 0.4, exp, "newsbot nasdaq_v3")
    req = fm.sent[-1]
    assert tk and req["action"] == fm.TRADE_ACTION_PENDING and req["type"] == fm.ORDER_TYPE_BUY_STOP
    assert req["symbol"] == "USTECm" and req["price"] == 20005.5 and req["sl"] == 20000.5 and req["volume"] == 0.4
    assert req["type_time"] == fm.ORDER_TIME_SPECIFIED
    assert req["expiration"] == int(exp.replace(tzinfo=timezone.utc).timestamp())
    assert b.order_status(tk, "NAS100") == {"state": "pending"}
    fm.orders.pop(tk)                                                  # the broker filled it -> a position
    fm.positions.append(types.SimpleNamespace(identifier=tk, ticket=tk, price_open=20006.0,
                                              time=int(datetime(2027, 1, 27, 0, 41, tzinfo=timezone.utc).timestamp())))
    st = b.order_status(tk, "NAS100")
    assert st["state"] == "filled" and st["price"] == 20006.0 and st["time"] == datetime(2027, 1, 27, 0, 41)
    tk2 = b.place_stop("NAS100", -1, 19994.5, 19999.5, 0.0, 0.4, exp, "x")
    assert fm.sent[-1]["type"] == fm.ORDER_TYPE_SELL_STOP and fm.sent[-1]["tp"] == 0.0
    assert b.cancel_order(tk2) and fm.sent[-1]["action"] == fm.TRADE_ACTION_REMOVE and not fm.orders
    assert b.order_status(tk2, "NAS100") == {"state": "gone"}
    # a symbol that refuses an expiration: falls back to GTC (the bot cancels it itself)
    fm2 = fake_mt5(expiration_ok=False)
    b.mt5 = fm2
    assert b.place_stop("NAS100", 1, 20005.5, 20000.5, 0.0, 0.4, exp, "x")
    assert fm2.sent[-1]["type_time"] == fm2.ORDER_TIME_GTC and "expiration" not in fm2.sent[-1]


def test_dry_run_pending_orders_never_send():
    fm = fake_mt5()
    b = MT5Broker({}, {"NAS100": "USTECm"}, dry_run=True)
    b.mt5 = fm
    m = nq(jump_at=10, o=3, h=12, l=2, after=10)
    b.bars_m1 = lambda sym, n=600: m[m.index <= T_REL + pd.Timedelta(minutes=12)]
    b.tick = lambda sym: (P0 + 10, P0 + 11.5, datetime(2027, 1, 27, 0, 42))
    tk = b.place_stop("NAS100", 1, P0 + 5.5, P0 + 0.5, P0 + 20.5, 1.0, datetime(2027, 1, 27, 1, 33), "x")
    b._paper_orders[tk]["placed"] = datetime(2027, 1, 27, 0, 33)
    st = b.order_status(tk, "NAS100")
    assert st["state"] == "filled" and st["time"] == datetime(2027, 1, 27, 0, 40) and fm.sent == []
    assert np.isclose(st["price"], P0 + 5.5)
