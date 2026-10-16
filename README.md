# OnCandle - trend-following bots for MT5, with an honest backtester

Twelve trend-following strategies, a fast Python backtester that ranks them by
**walk-forward out-of-sample** performance, and a single MT5 Expert Advisor
that trades any of them with the same rules.

| # | Strategy | Entry | Exit |
|---|----------|-------|------|
| 1 | EMA Crossover | fast EMA crosses slow EMA | opposite cross (reverse) |
| 2 | Donchian Breakout | close breaks N-bar high/low | M-bar opposite channel |
| 3 | Supertrend | Supertrend flips | opposite flip |
| 4 | MACD + EMA Filter | MACD/signal cross in direction of long EMA | opposite MACD cross |
| 5 | ADX/DMI | +DI/-DI cross while ADX > threshold | opposite DI cross |
| 6 | Keltner Breakout | close beyond EMA ± k·ATR | close back through EMA |
| 7 | Bollinger Breakout | close beyond band | close back through mid |
| 8 | Triple EMA | fast > mid > slow alignment starts | fast crosses mid |
| 9 | Ichimoku | close above/below cloud with Tenkan/Kijun agreement | close through Kijun |
| 10 | TS Momentum | N-bar rate of change crosses zero | opposite cross (reverse) |
| 11 | PSAR + EMA | Parabolic SAR flips in direction of long EMA | SAR flips back |
| 12 | KAMA Trend | close crosses rising/falling Kaufman AMA | opposite cross (reverse) |

Every strategy shares the same risk layer:
* hard stop at `stop_mult × ATR(14)` on every trade
* position size chosen so that hitting the stop loses a fixed % of equity
* optional chandelier trailing stop (`trail_mult × ATR` from the best close)
* signals are read on the bar close and executed at the next bar's open, so there is no look-ahead (this is tested)
* realistic per-pair costs (spread + commission) in `backtester/data.py`

## Quick start

```bash
pip install -r requirements.txt

# 1. Get data, using one of these:
python scripts/fetch_dukascopy.py --start 2005          # 12 pairs + gold, H1, free (needs datafeed.dukascopy.com)
#   ...or export bars from MT5 (View > Symbols > Bars > Export) into data/EURUSD_H1.csv etc.
#   ...or, offline: python scripts/fetch_sample_data.py   (EURUSD 2017 only, a demo set)

# 2. Backtest everything and rank
python scripts/run_research.py --out results/my_run
python scripts/make_report.py results/my_run          # -> results/my_run/REPORT.md + chart

python -m pytest                                       # engine + no-look-ahead tests
```

## How the ranking works

1. Every strategy × parameter set × pair × timeframe (H1, H4, D1) is backtested
   at 0.5% risk per trade, with costs.
2. **Anchored walk-forward**: the history is cut into 6 chunks. For each of the
   last 5, the parameter set with the best Sharpe on *all earlier data* (across
   all pairs together) is selected and then traded on that unseen chunk. Joining
   those 5 unseen periods gives the out-of-sample equity curve. This
   approximates what you would really have earned by choosing parameters
   with only the past available.
3. **Score** = 50% OOS Sharpe + 25% OOS CAGR/MaxDD + 25% robustness (share of
   all parameter sets that are profitable). Each metric is converted to a
   percentile rank before weighting. Results with fewer than 30 OOS trades are
   ranked last.

## Using the EA in MT5

1. Copy `mt5/Experts/OnCandleTrend.mq5` to `MQL5/Experts/` in your terminal's data folder, then compile it in MetaEditor (F7).
2. Attach the EA to a chart, choose the **Strategy** and timeframe, and use the parameters from `REPORT.md`.
3. Verify the result in the Strategy Tester using *Every tick based on real ticks* before you trade a live account.

## Trend Rider (M1, BTC / gold / Nasdaq / Dow)

This is a custom strategy, in `backtester/trend_rider.py` and `mt5/Experts/TrendRider.mq5`.

* **No trades in consolidation.** A market only counts as trending when EMA50 is on the
  right side of EMA200, price is beyond EMA50 and EMA50 is sloping, **ADX(14) > 25**
  and the **Choppiness Index(14) < 50**.
* **Joining the trend:** the previous bar pulls back to EMA20, and the current bar closes back
  through EMA20 and beyond the previous bar's high (or low, for shorts). Entry is at the next open.
* **Stop:** beyond the 10-bar swing low/high, never tighter than 1×ATR. The setup is skipped if
  the stop would be wider than 4×ATR. **Target: 1:3.**
* **Breakeven:** once price reaches **1R** in profit, the stop moves to entry + 0.1R, which makes it a free trade.
* One EA on one chart watches every market in `InpSymbols` and holds one position per market.

```bash
# Export M1 bars from MT5 for each market into data/ (e.g. data/XAUUSD_M1.csv, data/USTEC_M1.csv)
python scripts/run_trend_rider.py            # -> results/trend_rider/REPORT.md + equity.png
```

The report shows the rules as specified and a hold-out period. It also includes one-change variants
(no breakeven, breakeven at 1.5R, 1:2, no consolidation filter, stricter filter, US session only)
so you can see whether each rule actually helps.

## Confluence Rider (strategy 2, M1, multi-market confirmation)

This strategy lives in `backtester/confluence.py` and `mt5/Experts/ConfluenceRider.mq5`. Every minute, each
market (BTC, gold, Nasdaq, Dow) is classified as trending up, trending down, or consolidating, using
Trend Rider's definition. A market is only traded when it is trending **and at least
`MinAgree` markets (2 by default, counting itself) trend the same way**. One market trending
alone is ignored. Entry is either the EMA20 pullback (the default) or the minute the group lines up.
The stop, the 1:3 target and breakeven at 1R are the same as Trend Rider.

```bash
python scripts/run_confluence.py      # -> results/confluence/REPORT.md
```

## Candle Run (strategy 3, BTC M1)

This strategy lives in `backtester/candle_run.py` and `mt5/Experts/BtcCandleRun.mq5`. When 4 one-minute candles in a row
close the same colour and together move at least 1.5×ATR, it joins the move at the next open.
The stop goes beyond the start of the run, the target is 1:3, and the stop moves to breakeven at 1R.

```bash
python scripts/run_candle_run.py      # -> results/candle_run/REPORT.md
```

## Limitations (please read)

* Swaps/rollover are not modelled. Over multi-week D1 holds they can matter.
* The sample dataset (`results/sample_eurusd_2017`) is **one pair over 14
  months during a strong EURUSD uptrend**. It demonstrates the pipeline and
  is far too short to choose a strategy with. Run the full Dukascopy
  dataset before drawing conclusions.
* Past performance does not guarantee future results. This is research software, not financial advice.
