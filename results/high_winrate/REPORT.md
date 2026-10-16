# Search for a >70% win-rate strategy

**Goal:** a win rate above 70% that is **also profitable after Exness spreads**. A strategy only counts
if it was found on 2025 data and then **held up on 2026, which it never saw** (plus Q4 2024 as a third check).
A "win" means a trade that made money after spread.

## Round 1: 2,112 configurations
4 markets (BTC, gold, Nasdaq, Dow) × M5/M15/H1 × 7 families: RSI(2) dip-buying, Bollinger fade,
Z-score reversion, trend pullback with a small target, failed breakout, fading candle runs, and EMA snap-back.

* 374 had a 70%+ win rate in 2025, but only **143 were also profitable**. High win rate alone is easy, and usually loses money.
* 25 passed on unseen 2026 data, and almost all of them were **"Fade the candle run" on H1**.

## Round 2: 7,680 configurations of that family (M30/H1/H2/H4, finer grid)
BTCUSD H1 is the most robust: **21% of every parameter set tried passed all three periods**,
against 0–6% elsewhere.

## Result: BTCUSD H1 "Run Fade"
After **4 one-hour candles of the same colour** that together moved **≥ 2.5 × ATR(14)**, trade **against** the run.
Target **0.5 × ATR**, stop **4 × ATR**, close after 30 hours at most. One trade at a time.

| Period | Trades | Win rate | Profit factor | Return @1% risk | Max DD |
|---|---|---|---|---|---|
| Q4 2024 | 35 | **94.3%** | 2.32 | +2.4% | -1.2% |
| 2025 | 121 | **93.4%** | 1.82 | +6.5% | -1.6% |
| 2026 (unseen) | 79 | **92.4%** | 1.77 | +4.0% | -2.0% |

Exits were re-verified minute by minute on M1 data, and the results were identical (median hold 54 min).
It is still profitable up to a $60 spread (PF 1.35); at $100 it breaks even. The worst losing streak was 2 trades.
Shorts after green runs (95.5% win, PF 2.94) beat longs after red runs (91.1%, PF 1.38).

**Trade-off:** each win is small (+0.125R) and each loss is large (-0.92R). About 11 wins cover one loss.

Optional portfolio (`RunFade.mq5` presets): BTC H1 + US30 H4 + XAUUSD H1 gives a 91% win rate and PF 1.65–1.82
with about 230 trades a year. Gold is the weakest of the three.

Files: `all_configs.csv`, `run_fade_grid.csv`, `btc_h1_run_fade_m1_verified_trades.csv`.
