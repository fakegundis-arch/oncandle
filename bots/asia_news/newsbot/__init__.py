"""newsbot - trade Forex Factory high-impact releases of the Asian session (AUD, NZD, JPY, CNY).

Modules
  events    figure parsing, event classification, grouping of same-minute figures into one release
  signal    actual / forecast / previous (+ FF better/worse verdict) -> currency bias -> direction per instrument
  strategy  the trade plan (direction, stop, target, time exit) shared by the backtest and the live bot; entry modes
            "news" (v1: FF verdict) and "pair_reaction" (v2 Nasdaq: direction from the AUDUSD / NZDUSD reaction)
  backtest  M1-exact simulation with the protocol's costs; make_trades() for asia_news_lab.final_test
  feeds     live calendar sources: FF weekly JSON (schedule, forecast, previous) + FF page (actual) via Playwright
  broker    MetaTrader 5 broker (Windows, `MetaTrader5` package) and a paper / dry-run broker
  config    configuration loading
"""
__version__ = "2.0.0"
