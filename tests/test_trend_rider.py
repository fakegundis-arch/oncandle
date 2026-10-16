import numpy as np
import pandas as pd
import pytest

from backtester import trend_rider as tr


def run(rows, sig_at=0, direction=1, dist=1.0, cost=0.0, **kw):
    idx = pd.date_range("2024-01-01", periods=len(rows), freq="min")
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx, dtype=float)
    sig = pd.DataFrame({"signal": 0, "dist": 0.0}, index=idx)
    sig.iloc[sig_at] = [direction, dist]
    p = tr.Params(**kw)
    return tr.backtest(df, p, cost, risk=0.01, sig=sig).trades


def test_target_hit_is_3R():
    t = run([(100, 100, 100, 100), (100, 100.5, 99.5, 100.4), (100.4, 103.2, 100.3, 103)])
    assert t.exit.iloc[0] == "target" and t.r.iloc[0] == pytest.approx(3.0)


def test_stop_is_minus_1R():
    t = run([(100, 100, 100, 100), (100, 100.2, 98.9, 99)])
    assert t.exit.iloc[0] == "stop" and t.r.iloc[0] == pytest.approx(-1.0)


def test_break_even_after_1R():
    # bar 1 reaches +1R (101), bar 2 falls back through entry -> exits at entry + 0.1R
    t = run([(100, 100, 100, 100), (100, 101.2, 99.8, 101), (101, 101, 99, 99.2)])
    assert t.exit.iloc[0] == "breakeven" and t.r.iloc[0] == pytest.approx(0.1)


def test_no_break_even_when_disabled():
    t = run([(100, 100, 100, 100), (100, 101.2, 99.8, 101), (101, 101, 98.5, 98.6)], be_trigger=0)
    assert t.exit.iloc[0] == "stop" and t.r.iloc[0] == pytest.approx(-1.0)


def test_same_bar_stop_and_target_assumes_stop():
    t = run([(100, 100, 100, 100), (100, 103.5, 98.5, 101)])
    assert t.exit.iloc[0] == "stop"


def test_short_with_cost():
    # short sells bid 100; exits at ask = bid + 0.2; stop at 101 (ask), tp at 97 (ask)
    t = run([(100, 100, 100, 100), (100, 100.1, 99, 99.5), (99.5, 99.6, 96.7, 96.9)], direction=-1, cost=0.2)
    assert t.exit.iloc[0] == "target" and t.r.iloc[0] == pytest.approx(3.0)


def test_signals_no_lookahead():
    rng = np.random.default_rng(1)
    c = 2000 + np.cumsum(rng.normal(0, 0.5, 3000))
    o = np.r_[c[0], c[:-1]]
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c) + rng.uniform(0, .4, len(c)),
                       "low": np.minimum(o, c) - rng.uniform(0, .4, len(c)), "close": c},
                      index=pd.date_range("2024", periods=len(c), freq="min"))
    full = tr.signals(df, tr.Params())
    part = tr.signals(df.iloc[:2000], tr.Params())
    pd.testing.assert_frame_equal(full.iloc[:2000], part)
