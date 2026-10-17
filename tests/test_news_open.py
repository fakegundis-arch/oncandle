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
