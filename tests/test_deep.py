import numpy as np
import pandas as pd
import pytest

from backtester import deep


def run(rows, sig_at=0, d=1, sl=2.0, tp=0.0, trail=0.0, xout=(), be=0.0, cost=0.0):
    a = np.array(rows, float)
    n = len(a)
    s = np.zeros(n, np.int64); s[sig_at] = d
    x = np.isin(np.arange(n), xout)
    return deep.run_engine(a[:, 0], a[:, 1], a[:, 2], a[:, 3], s, np.full(n, sl), np.full(n, tp),
                           np.full(n, trail), x, 0, cost, be, 0.1 if be else 0.0)[3]


def test_trailing_stop_locks_profit():
    # entry 100; closes climb to 106 -> trail 2 puts stop at 104; next bar drops to 103 -> exit 104 = +2R
    r = run([(100, 100, 100, 100), (100, 101, 99.5, 101), (101, 106, 101, 106), (106, 106, 103, 103)], trail=2.0)
    assert r[0] == pytest.approx(2.0)


def test_session_close_exit_next_open():
    r = run([(100, 100, 100, 100), (100, 101, 99.5, 101), (101.5, 102, 101, 101.8)], xout=[1])
    assert r[0] == pytest.approx(0.75)


def test_target_and_stop_priority():
    assert run([(100, 100, 100, 100), (100, 104, 97, 100)], tp=4.0)[0] == pytest.approx(-1.0)
    assert run([(100, 100, 100, 100), (100, 104.5, 99, 104)], tp=4.0)[0] == pytest.approx(2.0)
