import numpy as np
import pandas as pd

from backtester import news_open as NO


def cal(rows):
    return pd.DataFrame(rows, columns=["time_utc", "currency", "impact", "name", "better_worse"]).assign(
        time_utc=lambda d: pd.to_datetime(d.time_utc))


def test_score_window_prev_close_to_open_and_weights():
    c = cal([
        ("2025-03-06 20:59", "USD", "high", "too early (before prev 16:00 ET)", 1),   # 15:59 ET Mar 6
        ("2025-03-06 21:01", "USD", "medium", "after prev close", 2),               # -1
        ("2025-03-07 13:30", "USD", "high", "NFP", 1),                              # +2 (08:30 ET)
        ("2025-03-07 14:31", "USD", "high", "after the open", 2),                   # excluded
        ("2025-03-07 13:30", "EUR", "high", "not USD", 1),                          # excluded
        ("2025-03-07 13:30", "USD", "low", "low impact", 1),                        # excluded
        ("2025-03-07 13:31", "USD", "high", "in line", 0),                          # excluded
    ])
    s = NO.day_scores(c, [pd.Timestamp("2025-03-07").date()])
    assert s.loc["2025-03-07", "score"] == 1 and s.loc["2025-03-07", "n_events"] == 2


def test_no_news_day_has_zero_score():
    s = NO.day_scores(cal([("2025-03-10 13:30", "USD", "high", "x", 1)]), [pd.Timestamp("2025-03-07").date()])
    assert s.iloc[0].score == 0


def test_direction_map_covers_all_markets():
    assert set(NO.USD_BULL_DIRECTION.values()) == {-1, 1}
    assert NO.USD_BULL_DIRECTION["XAUUSD"] == -1 and NO.USD_BULL_DIRECTION["USDJPY"] == 1


def test_m1_candidates_follow_news_and_use_m1_atr():
    t = pd.date_range("2025-03-07 13:00", periods=180, freq="1min")
    px = np.r_[np.full(30, 100.0), 100 - 0.05 * np.arange(150)]        # falls after the 13:30 UTC open
    m1 = pd.DataFrame({"open": px, "high": px + 0.03, "low": px - 0.03, "close": px - 0.01}, index=t)
    sc = pd.DataFrame({"t0": [pd.Timestamp("2025-03-07 14:30")], "score": [2], "events": ["NFP (+)"]},
                      index=[pd.Timestamp("2025-03-07")])
    sc.loc[:, "t0"] = pd.Timestamp("2025-03-07 13:30")
    p = NO.ParamsM1(observe_min=3, entry="momentum", stop="atr", stop_atr=2.0)
    cd = NO.candidates_m1(m1, "XAUUSD", sc, p)                          # USD bullish -> gold short
    assert len(cd) == 1 and cd.iloc[0].dir == -1
    assert m1.index[int(cd.iloc[0].entry_i)] == pd.Timestamp("2025-03-07 13:33")
    assert NO.candidates_m1(m1, "USDJPY", sc, p).empty                 # USDJPY should rise: no trade
