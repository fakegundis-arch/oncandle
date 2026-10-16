import numpy as np
import pandas as pd
import pytest

from backtester import sessions as S


def market(n=8 * 1440, seed=7):
    rng = np.random.default_rng(seed)
    c = 2000 + np.cumsum(rng.normal(0, 0.4, n))
    o = np.r_[c[0], c[:-1]]
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) + rng.uniform(0, .3, n),
                         "low": np.minimum(o, c) - rng.uniform(0, .3, n), "close": c},
                        index=pd.date_range("2025-03-24", periods=n, freq="min"))


CASES = [S.orb, S.asian_range_breakout, S.session_mean_fade, S.opening_drive]


@pytest.mark.parametrize("fn", CASES)
def test_no_lookahead(fn):
    df = market()
    cut = 5 * 1440 + 777                     # mid-session on day 6
    full, part = fn(df), fn(df.iloc[:cut])
    np.testing.assert_array_equal(full.sig[:cut], part.sig)
    np.testing.assert_allclose(full.sl[:cut], part.sl)
    np.testing.assert_allclose(full.tp[:cut], part.tp)


def test_entries_only_inside_session():
    df = market()
    s = S.orb(df, session="newyork", range_min=15)
    mod, _, s0, s1 = S.clock(df, "newyork")
    idx = np.nonzero(s.sig)[0]
    assert len(idx) > 0 and ((mod[idx] >= s0 + 15) & (mod[idx] < s1)).all()


def test_one_orb_trade_per_session():
    df = market()
    s = S.orb(df, session="london")
    _, day, _, _ = S.clock(df, "london")
    assert pd.Series(s.sig != 0).groupby(day).sum().max() <= 1


def test_each_local_day_is_its_own_session():
    df = market()
    _, day, _, _ = S.clock(df, "london")
    assert len(np.unique(day)) == 9          # 8 UTC days span 9 London days after the BST switch
