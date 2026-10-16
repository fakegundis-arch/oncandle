import numpy as np
import pandas as pd

from backtester import trend_rider_v2 as v2


def market(n=6000, seed=4):
    rng = np.random.default_rng(seed)
    c = 2000 + np.cumsum(rng.normal(0.02, 0.4, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + rng.uniform(0, .3, n),
                         "low": np.minimum(o, c) - rng.uniform(0, .3, n), "close": c},
                        index=pd.date_range("2025-01-06", periods=n, freq="min"))


def test_no_lookahead_even_when_cut_mid_htf_bar():
    df = market()
    full = v2.signals(df, v2.Params())
    for cut in (4003, 4001, 4000):          # 3 and 1 minute into an M5 bar, and on the boundary
        part = v2.signals(df.iloc[:cut], v2.Params())
        pd.testing.assert_frame_equal(full.iloc[:cut], part)


def test_regime_uses_completed_htf_bar_only():
    df = market()
    reg = v2.htf_regime(df, v2.Params())
    # the regime may only change on the last minute of an M5 bar (when it completes)
    changes = reg.index[reg.diff().fillna(0) != 0]
    assert all(t.minute % 5 == 4 for t in changes)
