"""MT5Broker against a minimal fake `MetaTrader5` module (the real package only exists on Windows)."""
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from newsbot.broker import MT5Broker, Position  # noqa: E402


def fake_mt5(bid=0.70000, ask=0.70015, now=datetime(2027, 1, 27, 0, 45, tzinfo=timezone.utc)):
    m = types.ModuleType("MetaTrader5")
    m.TIMEFRAME_M1, m.ORDER_TYPE_BUY, m.ORDER_TYPE_SELL, m.POSITION_TYPE_SELL = 1, 0, 1, 1
    m.TRADE_ACTION_DEAL, m.ORDER_TIME_GTC, m.TRADE_RETCODE_DONE = 1, 0, 10009
    m.ORDER_FILLING_FOK, m.ORDER_FILLING_IOC, m.ORDER_FILLING_RETURN = 0, 1, 2
    m.sent, m.positions = [], {}
    ns = types.SimpleNamespace
    m.initialize = lambda **kw: True
    m.last_error = lambda: (0, "ok")
    m.symbol_select = lambda s, v: True
    m.account_info = lambda: ns(login=1, server="demo", equity=1000.0, currency="USD")
    m.symbol_info = lambda s: ns(volume_step=0.01, volume_min=0.01, volume_max=100.0, filling_mode=2, digits=5)
    m.symbol_info_tick = lambda s: ns(bid=bid, ask=ask, time=int(now.timestamp()))
    # AUDUSD: 1 lot = 100,000 AUD -> USD P&L = 100000 x price change
    m.order_calc_profit = lambda t, s, v, p0, p1: v * 100000 * ((p1 - p0) if t == 0 else (p0 - p1))
    t0 = int(now.timestamp()) - 60 * 100
    rates = np.zeros(100, dtype=[("time", "i8"), ("open", "f8"), ("high", "f8"), ("low", "f8"), ("close", "f8")])
    rates["time"] = t0 + 60 * np.arange(100)
    rates["open"] = rates["close"] = bid
    rates["high"], rates["low"] = bid + 0.0002, bid - 0.0002
    m.copy_rates_from_pos = lambda s, tf, i, n: rates[-n:]

    def order_send(req):
        m.sent.append(req)
        tk = 1000 + len(m.sent)
        if "position" not in req:
            m.positions[tk] = ns(ticket=tk, symbol=req["symbol"], volume=req["volume"],
                                 type=0 if req["type"] == 0 else 1)
        else:
            m.positions.pop(req["position"], None)
        return ns(retcode=10009, order=tk, price=req["price"], comment="done")
    m.order_send = order_send
    m.positions_get = lambda ticket=None: tuple(p for k, p in m.positions.items() if k == ticket)
    m.shutdown = lambda: None
    return m


def test_live_order_flow(monkeypatch):
    fm = fake_mt5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fm)
    b = MT5Broker({"server_utc_offset_hours": 0}, {"AUDUSD": "AUDUSDm"}, dry_run=False)
    b.connect()
    lots, loss1 = b.lots_for("AUDUSD", 1, 0.70015, 0.69865, 100.0)      # 15-pip stop, risk $100
    assert abs(loss1 - 150.0) < 1e-6 and lots == 0.66
    bars = b.bars_m1("AUDUSD", 50)
    assert len(bars) == 50 and bars.index[-1] == datetime(2027, 1, 27, 0, 44)
    pos = Position(0, "pair_aud", "AUDUSD", 1, lots, 0.70015, 0.69865, 0.0, "2027-01-27T00:45", "2027-01-27T06:45", "x")
    pos = b.open(pos)
    req = fm.sent[-1]
    assert pos.ticket and req["symbol"] == "AUDUSDm" and req["sl"] == 0.69865 and req["type_filling"] == 1
    assert b.is_open(pos)
    assert b.close(pos, "time") and not b.is_open(pos) and fm.sent[-1]["position"] == pos.ticket


def test_dry_run_never_sends(monkeypatch):
    fm = fake_mt5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fm)
    b = MT5Broker({}, {"AUDUSD": "AUDUSDm"}, dry_run=True)
    b.connect()
    pos = Position(0, "pair_aud", "AUDUSD", -1, 0.5, 0.70000, 0.70150, 0.0, "2027-01-27T00:45", "2027-01-27T06:45", "x")
    pos = b.open(pos)
    assert pos.ticket > 0 and fm.sent == []
    assert b.is_open(pos)                       # flat fake bars never reach the stop
    assert b.close(pos) and pos.closed and fm.sent == []
