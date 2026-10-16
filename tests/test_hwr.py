import numpy as np
import pandas as pd
import pytest

from backtester import hwr


def bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], dtype=float,
                        index=pd.date_range("2025", periods=len(rows), freq="5min"))


def setup(n, sig_at=0, d=1, sl=2.0, tp=1.0, xl=(), xs=(), max_bars=0):
    s = np.zeros(n, np.int64); s[sig_at] = d
    a = lambda ix: np.isin(np.arange(n), ix)
    return hwr.Setup(s, np.full(n, sl), np.full(n, tp), a(xl), a(xs), max_bars)


def test_small_target_win():
    df = bars([(100, 100, 100, 100), (100, 100.5, 99.5, 100.2), (100.2, 101.2, 100, 101)])
    t = hwr.run(df, setup(3), 0.0)
    assert t.r.iloc[0] == pytest.approx(0.5)          # +1 target on a 2-point stop


def test_stop_beats_target_same_bar():
    df = bars([(100, 100, 100, 100), (100, 101.5, 97.5, 100)])
    assert hwr.run(df, setup(2), 0.0).r.iloc[0] == pytest.approx(-1.0)


def test_condition_exit_next_open():
    df = bars([(100, 100, 100, 100), (100, 100.3, 99.8, 100.2), (100.4, 100.6, 100.3, 100.5)])
    t = hwr.run(df, setup(3, tp=0, xl=[1]), 0.0)
    assert t.exit_time.iloc[0] == df.index[2] and t.r.iloc[0] == pytest.approx(0.2)


def test_time_exit_and_spread_counts_against_win():
    df = bars([(100, 100, 100, 100)] + [(100, 100.1, 99.9, 100)] * 4)
    t = hwr.run(df, setup(5, tp=0, max_bars=2), 0.1)
    assert t.r.iloc[0] < 0                              # flat price, spread paid -> a loss
