import numpy as np
import pandas as pd

from backtester import candle_run as cr


def bars(oc):
    o = np.array([x[0] for x in oc], float)
    c = np.array([x[1] for x in oc], float)
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + .1, "low": np.minimum(o, c) - .1, "close": c},
                        index=pd.date_range("2025", periods=len(oc), freq="min"))


def test_run_length_counts_and_resets():
    df = bars([(1, 2), (2, 3), (3, 4), (4, 3), (3, 2), (2, 2), (2, 3)])
    assert cr.run_length(df).tolist() == [1, 2, 3, -1, -2, 0, 1]


def test_signal_fires_once_when_run_reaches_n():
    rng = np.random.default_rng(0)
    noise = [(100 + x, 100 + x + rng.choice([-.5, .5])) for x in rng.normal(0, .3, 40)]
    run = [(100 + i, 101 + i) for i in range(6)]          # six big green candles
    df = bars(noise + run + noise)
    s = cr.signals(df, cr.Params(run_len=4, min_move_atr=1.0, max_stop_atr=50))
    fired = s.index[s.signal == 1]
    assert df.index[40 + 3] in fired                      # 4th green candle of the run
    assert df.index[40 + 4] not in fired and df.index[40 + 5] not in fired


def test_no_lookahead():
    rng = np.random.default_rng(1)
    c = 60000 + np.cumsum(rng.normal(0, 20, 3000))
    o = np.r_[c[0], c[:-1]] + rng.normal(0, 5, 3000)
    df = pd.DataFrame({"open": o, "high": np.maximum(o, c) + 10, "low": np.minimum(o, c) - 10, "close": c},
                      index=pd.date_range("2025", periods=3000, freq="min"))
    full = cr.signals(df, cr.Params())
    part = cr.signals(df.iloc[:2000], cr.Params())
    pd.testing.assert_frame_equal(full.iloc[:2000], part)
