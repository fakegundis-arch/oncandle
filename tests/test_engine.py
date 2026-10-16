import numpy as np
import pandas as pd
import pytest

from backtester.engine import backtest
from backtester.strategies import STRATEGIES


def bars(rows):
    idx = pd.date_range("2020-01-01", periods=len(rows), freq="h")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float)


def sig(n, le=(), se=(), lx=(), sx=()):
    out = {}
    for k, ix in dict(le=le, se=se, lx=lx, sx=sx).items():
        s = pd.Series(False, index=range(n))
        s.iloc[list(ix)] = True
        out[k] = s
    return out


def flat_atr(df, v=1.0):
    return pd.Series(v, df.index)


def test_entry_next_open_and_stop_fill():
    df = bars([(100, 101, 99, 100), (100, 101, 99, 100), (100, 100.5, 97.5, 98), (98, 99, 97, 98)])
    s = {k: v.set_axis(df.index) for k, v in sig(4, le=[0]).items()}
    res = backtest(df, s, flat_atr(df), cost=0.0, stop_mult=2.0)
    t = res.trades.iloc[0]
    assert t.entry_time == df.index[1] and t.exit_time == df.index[2]
    assert t.r == pytest.approx(-1.0)  # stopped at 98 = entry - 2*ATR


def test_gap_through_stop_fills_at_open():
    df = bars([(100, 100, 100, 100), (100, 100.5, 99.5, 100), (95, 96, 94, 95)])
    s = {k: v.set_axis(df.index) for k, v in sig(3, le=[0]).items()}
    res = backtest(df, s, flat_atr(df), cost=0.0, stop_mult=2.0)
    assert res.trades.r.iloc[0] == pytest.approx(-2.5)  # (95-100)/2


def test_reversal_and_costs():
    df = bars([(100, 100, 100, 100)] * 2 + [(101, 102, 100.5, 102), (102, 103, 101.5, 102), (104, 104, 103, 103)])
    s = {k: v.set_axis(df.index) for k, v in sig(5, le=[0], se=[3]).items()}
    res = backtest(df, s, flat_atr(df), cost=0.2, stop_mult=2.0)
    long, short = res.trades.iloc[0], res.trades.iloc[1]
    assert long.dir == 1 and long.r == pytest.approx((104 - 100 - 0.2) / 2)
    assert short.dir == -1 and short.exit_time == df.index[-1]


def test_risk_scales_equity():
    df = bars([(100, 101, 99, 100), (100, 101, 99, 100), (100, 100.5, 97.5, 98), (98, 99, 97, 98)])
    s = {k: v.set_axis(df.index) for k, v in sig(4, le=[0]).items()}
    res = backtest(df, s, flat_atr(df), cost=0.0, stop_mult=2.0, risk=0.01)
    assert res.equity.iloc[-1] == pytest.approx(0.99)


@pytest.mark.parametrize("name", list(STRATEGIES))
def test_no_lookahead(name):
    rng = np.random.default_rng(0)
    c = 1.1 + np.cumsum(rng.normal(0, 0.001, 1500))
    o = np.r_[c[0], c[:-1]]
    h = np.maximum(o, c) + rng.uniform(0, 0.0008, len(c))
    l = np.minimum(o, c) - rng.uniform(0, 0.0008, len(c))
    df = pd.DataFrame({"open": o, "high": h, "low": l, "close": c},
                      index=pd.date_range("2020", periods=len(c), freq="h"))
    fn, grid, _ = STRATEGIES[name]
    full = fn(df, **grid[0])
    part = fn(df.iloc[:1000], **grid[0])
    for k in full:
        pd.testing.assert_series_equal(full[k].iloc[:1000], part[k], check_names=False)
