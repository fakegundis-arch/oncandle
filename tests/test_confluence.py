import numpy as np
import pandas as pd

from backtester import confluence as cf


def market(seed, drift, n=4000):
    rng = np.random.default_rng(seed)
    c = 1000 + np.cumsum(rng.normal(drift, 0.5, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + rng.uniform(0, .3, n),
                         "low": np.minimum(o, c) - rng.uniform(0, .3, n), "close": c},
                        index=pd.date_range("2025-01-01", periods=n, freq="min"))


def test_lone_trend_is_ignored():
    uni = {"A": market(1, 0.25), "B": market(2, 0.0), "C": market(3, 0.0)}
    alone = cf.signals(uni, cf.Params(min_agree=1))["A"]
    confirmed = cf.signals(uni, cf.Params(min_agree=2))["A"]
    assert (alone.signal == 1).sum() > 0
    # B and C are random walks: A may only trade when one of them happens to trend up too
    both = confirmed.signal == 1
    assert both.sum() < (alone.signal == 1).sum()
    assert (confirmed.loc[both, "n_up"] >= 2).all()


def test_more_agreement_means_fewer_trades():
    uni = {k: market(i, 0.15) for i, k in enumerate("ABCD")}
    counts = [sum((s.signal != 0).sum() for s in cf.signals(uni, cf.Params(min_agree=k)).values())
              for k in (1, 2, 3, 4)]
    assert counts == sorted(counts, reverse=True)


def test_no_lookahead():
    uni = {k: market(i, 0.1) for i, k in enumerate("AB")}
    full = cf.signals(uni, cf.Params(min_agree=2))
    part = cf.signals({k: v.iloc[:3000] for k, v in uni.items()}, cf.Params(min_agree=2))
    for k in uni:
        pd.testing.assert_frame_equal(full[k].iloc[:3000], part[k])
