"""Unit tests (synthetic data only):  cd <this folder> && python -m pytest -q tests"""
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from newsbot.backtest import make_trades, simulate  # noqa: E402
from newsbot.events import Release, classify, make_figure, parse_value, releases_from_frame  # noqa: E402
from newsbot.feeds import FileActuals, parse_ff_page, releases_from_json, wait_for_actual  # noqa: E402
from newsbot.signal import currency_bias, instrument_direction  # noqa: E402
from newsbot.strategy import Plan, make_plan, weekend_cap  # noqa: E402

TB = ["unemployment rate", "cpi y/y", "cpi q/q"]


def rel(ccy, *figs, t=datetime(2027, 1, 27, 0, 30)):
    return Release(t, ccy, [make_figure(*f) for f in figs])


def test_parse_value():
    assert parse_value("65.2K") == 65200 and parse_value("-18.6K") == -18600
    assert parse_value("<0.75%") == 0.75 and parse_value("-0.7%") == -0.7
    assert math.isnan(parse_value("")) and math.isnan(parse_value(None)) and parse_value("1.2B") == 1.2e9


def test_classify():
    assert classify("Unemployment Rate") == ("EMP", -1)
    assert classify("Employment Change q/q") == ("EMP", 1)
    assert classify("Trimmed Mean CPI m/m") == ("CPI", 1)
    assert classify("BOJ Policy Rate") == ("RATE", 1) and classify("Official Cash Rate") == ("RATE", 1)
    assert classify("RBA Rate Statement") is None and classify("BOJ Press Conference") is None
    assert classify("RBA Gov Bullock Speaks") is None


def test_bias_ff_and_tiebreak():
    r = rel("AUD", ("Unemployment Rate", "4.1%", "4.2%", "4.1%", 1), ("Employment Change", "17.8K", "20.0K", "65K", 2))
    assert currency_bias(r, {"vote": "ff"}).bias == 0                       # split report, no tie-break
    assert currency_bias(r, {"vote": "ff", "tiebreak": TB}).bias == 1       # the unemployment rate decides
    r = rel("AUD", ("CPI m/m", "0.0%", "0.1%", "0.4%", 2), ("CPI y/y", "3.7%", "3.8%", "3.8%", 2),
            ("Trimmed Mean CPI m/m", "0.2%", "0.3%", "0.3%", 2))
    assert currency_bias(r).bias == -1
    r = rel("AUD", ("Cash Rate", "4.35%", "4.35%", "4.10%", 0))
    assert currency_bias(r).bias == 0                                       # expected hike: no trade
    assert currency_bias(r, {"inline": "previous"}).bias == 1


def test_bias_calc_fallback_without_verdict():
    r = rel("NZD", ("Unemployment Rate", "5.5%", "5.3%", "5.3%", None))
    assert currency_bias(r, {"vote": "ff"}).bias == -1                      # no FF verdict -> computed, inverted


def test_direction_mapping():
    assert instrument_direction(1, "AUD", "pair", "AUDUSD") == 1
    assert instrument_direction(1, "JPY", "pair", "USDJPY") == -1           # stronger yen = USDJPY down
    assert instrument_direction(1, "AUD", "pair", "NZDUSD") == 0            # a pair trades only its own currency
    assert instrument_direction(-1, "AUD", "gold") == -1
    assert instrument_direction(1, "JPY", "nasdaq") == -1
    assert instrument_direction(0, "AUD", "gold") == 0


def test_weekend_cap():
    fri = datetime(2027, 1, 29, 18, 0)
    assert weekend_cap(fri, datetime(2027, 1, 30, 0, 0)) == datetime(2027, 1, 29, 20, 0)
    sun = datetime(2027, 1, 31, 22, 0)
    assert weekend_cap(sun, datetime(2027, 2, 1, 4, 0)) == datetime(2027, 2, 1, 4, 0)


def test_releases_from_json_sample():
    rows = json.loads((HERE / "sample_thisweek.json").read_text())
    rs = releases_from_json(rows)
    keys = [(r.currency, r.time, len(r.figures)) for r in rs]
    assert ("AUD", datetime(2027, 1, 27, 0, 30), 3) in keys                 # 3 high figures, the low one dropped
    assert ("JPY", datetime(2027, 1, 28, 3, 0), 1) in keys                  # press conference has no figure
    assert ("NZD", datetime(2027, 1, 27, 21, 45), 2) in keys
    assert not any(r.currency in ("USD", "GBP") for r in rs)


def test_parse_ff_page():
    html = 'x days: [{"events": [{"dateline": 1800000000, "currency": "AUD", "impactName": "high", "name": "CPI y/y",' \
           ' "actual": "3.2%", "forecast": "3.1%", "previous": "3.0%", "actualBetterWorse": 1}]}], y'
    rows = parse_ff_page(html)
    assert rows[0]["actual"] == "3.2%" and rows[0]["verdict"] == 1 and rows[0]["time"] == datetime(2027, 1, 15, 8, 0)


def test_wait_for_actual(tmp_path):
    t = datetime(2027, 1, 27, 0, 30)
    sched = rel("AUD", ("CPI y/y", "", "3.1%", "3.2%", None), ("CPI m/m", "", "0.3%", "-0.2%", None), t=t)
    f = tmp_path / "a.json"
    f.write_text(json.dumps([{"time": "2027-01-27 00:30", "currency": "AUD", "name": "CPI y/y", "actual": "3.3%",
                              "forecast": "3.1%", "previous": "3.2%", "verdict": 1}]))
    clock = iter([t, t, datetime(2027, 1, 27, 0, 45)])
    got = wait_for_actual(FileActuals(f), sched, 1, 60, require_all=True, now=lambda: next(clock), sleep=lambda s: None)
    assert got is None                                                      # CPI m/m never arrived -> skip
    clock = iter([t, t, datetime(2027, 1, 27, 0, 45)])
    got = wait_for_actual(FileActuals(f), sched, 1, 60, require_all=False, now=lambda: next(clock), sleep=lambda s: None)
    assert got is not None and currency_bias(got).bias == 1


def frame(start, opens, highs, lows, closes):
    idx = pd.date_range(start, periods=len(opens), freq="1min")
    return pd.DataFrame({"open": opens, "high": highs, "low": lows, "close": closes}, index=idx, dtype=float)


def plan(t, d, sd, tgt=math.inf, entry_min=1, hold=10):
    r = Release(t, "AUD", [])
    return Plan(r, d, sd, tgt, t + pd.Timedelta(minutes=entry_min), t + pd.Timedelta(minutes=entry_min + hold), "x")


def test_simulate_long_stop_and_costs():
    t = pd.Timestamp("2027-01-27 00:30")
    m = frame(t, [100, 100, 100, 99.5, 99], [100, 100.5, 100.2, 99.6, 99.1], [100, 99.8, 99.9, 98.0, 98.9],
              [100, 100, 100, 99.5, 99])
    s = simulate(m, plan(t, 1, 1.0), cost=0.1, news_mult=2.0, news_window=5)
    assert s[4] == 100.2                                                    # long buys at bid + 2 x 0.1 in the window
    assert s[3] == "stop" and s[2] == -1.0 and s[1] == t + pd.Timedelta(minutes=3)


def test_simulate_short_pays_spread_on_exit_and_entry_minute_no_target():
    t = pd.Timestamp("2027-01-27 00:30")
    m = frame(t, [100] * 6, [100, 100.0, 100, 100, 100, 100], [100, 98.0, 99.7, 99.7, 99.7, 99.7], [100] * 6)
    s = simulate(m, plan(t, -1, 1.0, tgt=1.0, entry_min=1, hold=3), cost=0.1, news_mult=1.0, news_window=0)
    # entry minute touches the target but may not take it; time exit at the open of minute 4 at the ask (bid + cost)
    assert s[3] == "time" and abs(s[2] - (100 - 100.1) / 1.0) < 1e-12


def test_simulate_gap_through_stop():
    t = pd.Timestamp("2027-01-27 00:30")
    m = frame(t, [100, 100, 97], [100, 100.1, 97.2], [100, 99.9, 96.5], [100, 100, 97])
    s = simulate(m, plan(t, 1, 1.0), cost=0.0, news_mult=1.0, news_window=0)
    assert s[3] == "stop-gap" and s[2] == -3.0


def test_make_trades_end_to_end_synthetic():
    t0 = pd.Timestamp("2027-01-25 00:00")
    idx = pd.date_range(t0, "2027-01-27 08:00", freq="1min")
    rng = np.random.default_rng(1)
    px = 0.70 + np.cumsum(rng.normal(0, 0.00005, len(idx)))
    m = pd.DataFrame({"open": px, "high": px + 0.0001, "low": px - 0.0001, "close": px}, index=idx)
    m.loc["2027-01-27 00:45":, ["open", "high", "low", "close"]] += 0.002   # drift after the release
    cal = pd.DataFrame([dict(time_utc=pd.Timestamp("2027-01-27 00:30"), currency="AUD", impact="high", name="CPI y/y",
                             actual="3.4%", forecast="3.1%", previous="3.2%", better_worse=1)])
    cfg = dict(instrument="pair", symbol="AUDUSD", currencies=["AUD"], entry_delay=15, stop_k=1.5, hold_min=360)
    tr = make_trades(cfg, cal, m, 0.00015)
    assert len(tr) == 1 and tr.dir.iloc[0] == 1 and tr.entry_time.iloc[0] == pd.Timestamp("2027-01-27 00:45")
    assert releases_from_frame(cal)[0].figures[0].verdict == 1
    p = make_plan(releases_from_frame(cal)[0], cfg, m)
    assert p.exit_by == datetime(2027, 1, 27, 6, 45)
