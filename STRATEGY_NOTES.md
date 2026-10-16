# Strategy scorecard

The strategies that held up in testing are kept here for later comparison. Unless noted otherwise:
* data is Dukascopy, Oct 2024 to Oct 2026; times are UTC (Exness server = GMT+0)
* costs are Exness Standard spreads: BTC $20, gold $0.20, Nasdaq 1.2-1.5 pts, Dow 2 pts; no commission
* **2025 = discovery** and **2026 = unseen validation** (parameters were never tuned on 2026)
* "$1,000 in 2026" compounds from 1 Jan to about 15 Oct 2026
* R = one unit of risk (the stop distance); PF = profit factor (gross wins / gross losses)

## Shortlist (best first)

| # | Strategy | Market / TF | Win rate | PF 2025 | PF 2026 | $1,000 in 2026 (risk/trade, max drawdown) | Robustness | EA |
|---|---|---|---|---|---|---|---|---|
| 0 | **Gold Asian Breakout** (10% risk deep search) | Gold M15, Asian session | 53% | 1.96 | 1.38 | **$3,853 (10%, -74%)** | ★★★ family 100%/83% of variants profitable in 2025/2026; Q4 2024 +13% (with a -79% dip) | `GoldAsianBreakout.mq5` |
| 1 | **Trend Rider v2, Asian session only** | Nasdaq (USTEC) M1 | ~55% | 1.26 | 1.39 | **$3,862 (2%, -33%)** / $6,613 (3%, -46%) / $14,969 (5%, -66%) | ★★★ all 36 neighbouring settings profitable in both years; OK up to 3-pt spread; Q4 2024 only break-even | `TrendRiderV2.mq5` |
| 2 | **Gold H4 MACD + EMA100** (trend following) | Gold H4 | ~50% | strong (2025 boom year) | +0.24R avg | $2,881 (10%, -33%) / $5,883 (20%, -57%) | ★★☆ 8/8 MACD variants profitable in 2026; few trades (54/yr) | `OnCandleTrend.mq5` |
| 3 | **Run Fade** (mean reversion, high win rate) | BTC H1 | **93%** | 1.82 | 1.77 | $1,440 (10%, -19%) / $1,927 (20%, -36%) | ★★★ 3 periods incl. Q4 2024 (94%/93%/92% wins); OK to $60 spread; exits verified on M1 | `RunFade.mq5` |
| 4 | **Run Fade portfolio** | BTC H1 + Dow H4 + gold H1 | **91%** | 1.82 | 1.65 | $1,981 (10%, -27%) / $3,381 (20%, -50%) | ★★☆ gold leg weakest; trades can overlap at high risk | `RunFade.mq5` (3 charts) |
| 5 | **Trend Rider v2** (trend on M5, entry on M1) | Gold M1 | ~50% | +32% in 2025 | +4% in 2026 | small gain at 0.5% risk | ★★☆ thin edge (+0.03R); catches clean multi-hour trends | `TrendRiderV2.mq5` |
| 6 | **Confluence Rider** (2+ markets must agree), $10 gold stop | Gold M1 | ~50% | - | - | +12.5% over 2 yrs (0.5%), +19% in 2026 | ★☆☆ best stop size varied by year | `ConfluenceRider.mq5` |

## Details

### 0. Gold Asian Breakout (`results/deep/REPORT.md`)
* XAUUSD M15, entries only 00:00-06:00 UTC. Close breaks the prior 20-bar high (low) with price above (below) a rising (falling)
  EMA200 on M15 (~50 h). Stop 1.5x ATR(14), target 3R, stop to +0.1R at +1R. Built for 10% risk per trade.
* 2026 at 10% risk: $1,000 -> $3,853 (dipped to $1,438 in April). Exits verified on M1.
* Warning: the top single pick by 2025 in the same search went $1,000 -> $10 in 2026. Choose by robustness, not the best year.

### 1. Nasdaq: Trend Rider v2, Asian session (`results/sessions/REPORT.md`)
* **Rules:** trend from completed M5 bars (EMA20 > EMA50 and rising, ADX > 20, efficiency ratio > 0.3,
  held through pullbacks until an M5 close through EMA50). Entry is an M1 pullback to EMA20 that resumes, with
  M1 EMA20 > 50 > 200. **New trades only 00:00-06:00 UTC** (Tokyo 09:00-15:00); trades may run past 06:00.
* **Exits:** stop = max(15-bar swing, 40 pts); target 3R; at +1R the stop moves to entry + 0.1R.
* **Results:** 437 trades in 2026 (54.5% wins, PF 1.39); 393 in 2025 (55.7%, PF 1.26).
* **Month-end balances at ~3% risk:** Jan $1,873, Mar $1,194 (the drawdown), Jul $5,424, Sep $8,678, Oct $8,373.
* **EA settings:** USTEC M1; MinStopPrice 40, RR 3, BETrigger 1, SessionStart 0, SessionEnd 6.

### 2. Gold H4 MACD + EMA100 (`results/growth/REPORT.md`)
* **Rules:** MACD(12,26,9) signal-line cross in the direction of EMA100; exit on the opposite cross; stop 3x ATR(14); no trail.
* **2026:** 54 trades, 50% wins, +0.24R average; biggest win +4.8R; longest losing streak 5.
* **$1,000 in 2026:** 2% -> $1,279; 5% -> $1,787; 10% -> $2,881; 20% -> $5,883; 35% -> $10,621 (-81% DD).
* **EA settings:** XAUUSD H4; Strategy = MACD + EMA Filter, MacdTrend 100, StopATR 3, TrailATR 0.

### 3. BTC H1 Run Fade (`results/high_winrate/REPORT.md`)
* **Rules:** after 4 same-colour H1 candles that moved >= 2.5x ATR together, trade against the run.
  TP 0.5x ATR, SL 4x ATR, time exit 30 bars.
* **Results:** Q4 2024 94.3% wins (PF 2.32); 2025 93.4% (1.82); 2026 92.4% (1.77). Median hold 54 min.
* **Caveat:** each win is small (+0.125R) and each loss large (-0.92R). With $1,000 the 0.01 minimum lot
  already risks about $18, so use a fixed 0.01-0.02 lot (2026: +$68 / +$135).
* **Other tested presets:** US30 H4 (4 candles, 1.5 ATR, TP 0.3, SL 3, 10 bars); XAUUSD H1 (4, 3.0, 0.5, 4, 10).

## Tested and rejected (for reference)
* **NY-open straddle (Nasdaq and Dow, 09:29:50 OCO stops):** Nasdaq loses in every robust test (tick PF ~0.8). Dow is about
  break-even and fragile; the best-by-2025 config gave $1,000 -> $434 in 2026 at 10% risk. Also tested on S&P 500, gold,
  silver, oil, BTC, EURUSD, GBPUSD, USDJPY and USDCAD: none beat the Dow and none is profitable in both years.
  See `results/straddle/REPORT.md`.
* **Trend Rider v1 on M1, all 4 markets:** -0.2R/trade after spread; the M1 ADX/chop filter switched off at every pullback.
* **Candle Run (strategy 3, BTC M1, follow the run):** negative even with zero cost; on BTC M1, runs revert rather than continue.
* **Confluence Rider over the full 2 years:** -89% (only 2026 was good).
* **Session families:** ORB, session-mean fade and opening drive were mostly unprofitable in one of the two years.
* **20x in 2026:** no variant reached it, even with hindsight (best 13.7x, with a 40% drawdown).
* **12 classic trend strategies on EURUSD 2017** (first study): sample too short to rank.

## How to compare later
Re-run any study on new data (`scripts/fetch_dukascopy_m1.py`, then the matching `scripts/run_*.py` /
`search_*.py`), or export your Exness bars and drop them in `data/`. For a like-for-like comparison, use the
same period, the same risk per trade, and judge PF, max drawdown and the number of trades, not win rate alone.
