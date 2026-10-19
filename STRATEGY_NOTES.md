# Strategy scorecard

The strategies that held up in testing are kept here for later comparison. Unless noted otherwise:
* data is Dukascopy, Oct 2024 to Oct 2026; times are UTC (Exness server = GMT+0)
* costs are Exness Standard spreads: BTC $20, gold $0.20, Nasdaq 1.2-1.5 pts, Dow 2 pts; no commission
* **2025 = discovery** and **2026 = unseen validation** (parameters were never tuned on 2026)
* "$1,000 in 2026" compounds from 1 Jan to about 15 Oct 2026
* R = one unit of risk (the stop distance); PF = profit factor (gross wins / gross losses)

## Shortlist (best first)

> **Exness spread, measured (Oct 2026, user's MT5 export of XAUUSDm):** $0.24-0.26 at every hour, so the gold
> results at $0.20-0.25 apply to this account (Dukascopy's $0.65-0.78 does not). On Exness's own bars the bots take
> mostly the same trades, with ~15-35% lower results (Jul-Oct 2026). `results/gold/REPORT.md`, "Exness's real gold spread".

> **Exam on unseen gold (Feb 2023 - Sep 2024), Oct 2026:** every gold breakout version up to v13 loses 80-100% of the account
> there (even at $0.20 cost); Dukascopy's recorded gold spread is ~3x the $0.20 assumed. Details:
> `results/gold/REPORT.md`, section "Costs and the 2023 - 2024 check".


| # | Strategy | Market / TF | Win rate | PF 2025 | PF 2026 | $1,000 in 2026 (risk/trade, max drawdown) | Robustness | EA |
|---|---|---|---|---|---|---|---|---|
| 0++ | **v3 portfolio**: gold Asian breakout v3 (7%) + Truth tariff Dow (4%) + BTC Run Fade (5%) + gold H4 MACD (4%) | gold/Dow/BTC | ~60% | - | - | **$38,694, max DD -33%** (v2: $28,138, -82%) | ★★☆ weights at the grid edge; Dow leg needs a live Truth Social feed | `GoldAsianBreakoutV3.mq5` + `RunFade.mq5` + `OnCandleTrend.mq5` |
| 0+v5 | **Gold Asian Breakout v5** (chosen on 2026; Donchian 10, max 2/day, weekly stop, 12% / 6%) | Gold M15 | 58% | 1.86 (test) | 1.94 (chosen) | 2026 $126,210 (-57%, in-sample); **2025 $425,687 (-58%) and Q4 2024 $2,550 (-56%) out-of-sample** | ★★☆ neighbours profitable but median 2026 $23.9k, DD -73% — **fails 2023-2024 exam** | `GoldAsianBreakoutV5.mq5` |
| 0+v9 | **Gold Asian Breakout v9** (engines v5 3% + B 6% + C 3% together, every month; combination chosen on 2026) | Gold M15 | 58-61% | - | - | 2026 $603,341 (-53%), 10/10 months up (in-sample); **2025 $104,212 (-66%), 10/12 up**; Q4 2024 $1,552 (-42%) | ★★☆ all 234 passing combinations profitable in 2025; 2025 not fully clean for engine C — **fails 2023-2024 exam** | `GoldAsianBreakoutV9.mq5` |
| 0+v10 | **Gold Asian Breakout v10** (v5 + daily trend, regime filter, equity-curve filter; 8%; chosen on 2026) | Gold M15 | 60-62% | - | - | 2026 $72,607 (-33%), 10/10 months up (in-sample); **2025 $38,178 (-42%), 9/12 up, worst month -8%**; Q4 2024 $1,607 (-29%) | ★★☆ same engine profitable in 2025 under all 24 overlay/risk variants; far less profit than v5 — **fails 2023-2024 exam** | `GoldAsianBreakoutV10.mq5` |
| 0+v11 | **Gold Asian Breakout v11** (v10 10% + same rules on New York 12-15, Donchian 15, 5%; chosen on 2026) | Gold M15 | 58-59% | - | - | 2026 $244,454 (-35%), 9/10 up (in-sample); **2025 $97,956 (-53%), 10/12 up**; Q4 2024 $1,440 (-57%) | ★★☆ New York best second session in both years; its edge is small (+0.13R/trade in 2025) — **fails 2023-2024 exam** | `GoldAsianBreakoutV11.mq5` |
| SD1 | **Supply & Demand v1** (15-min base + leg-out zones, first-touch limit at the zone middle, 4R, break-even, with the daily trend; chosen on 2026 only) | Gold M15 / M1 fills | 37% | 0.99 (test) | 2.05 (chosen) | 2026 $2,006 (-14%, 2%); **2025 $950 (-24%), -0.6R (unseen)** | ☆☆☆ fails 2025; grid median PF 0.81-0.87 - no edge after costs | `SupplyDemandV1.mq5` |
| 0+v18 | **Gold Asian Breakout v18** (chosen on 2026 only by a rule tested inside 2026; v5 1%, v13-Asia 7%, New York 5%, 3-loss daily limit) | Gold M15 | - | - | - | 2026 $922,583 (-30%), 9/10 up (chosen on); **2025 $17,860 (-56%), 8/12 up, worst month -45% (unseen)**; Q4 2024 $1,158 (-36%) | ★☆☆ fails its 2025 target (-50%); the filters fit 2026 | `GoldAsianBreakoutV18.mq5` |
| 0+v13 | **Gold Asian Breakout v13** (v11 engines, Asia 14% + New York 4%) | Gold M15 | 58-59% | - | - | 2026 $678,871 (-45%), 9/10 up (in-sample); **2025 $221,532 (-64%), 9/12 up**; Q4 2024 $1,684 (-62%) | ★★☆ higher risk on v11's rules; exits, throttle and 1-hour engine attempts rejected — **fails 2023-2024 exam** | `GoldAsianBreakoutV13.mq5` |
| 0+v4 | **Gold Asian Breakout v4** (v3 + longs 12% / shorts 6%) | Gold M15 | 58% | 2.52 | 2.18 | **$38,290 (-63%)**; Q4 2024 $12,046 (-22%), 2025 $181,427 (-47%) | ★★☆ neighbours all profitable, median 2026 $11k | `GoldAsianBreakoutV4.mq5` |
| 0+v3 | Gold Asian Breakout v3 alone (v2 + D1 trend, vol cap, equity-curve filter, weekly stop) | Gold M15 | 58% | 2.52 | 2.18 | $30,750 (10%, -64%) / $15,649 (7%, -50%) | ★★★ 144 neighbours profitable in all periods (median 2026 $9,929) | `GoldAsianBreakoutV3.mq5` |
| 0+ | **Gold Asian Breakout v2** (Donchian 20, slope 4 h, 4R, BE +0.3R; `results/gold/REPORT.md`) | Gold M15 (M1-exact), Asian session | 56% | 2.04 | 1.67 | **$28,138 (10%, -82%)** / $20,221 (8%, -74%) | ★★★ all 2,304 neighbours profitable in 2025 and 2026; Q4 2024 PF 1.54 | `GoldAsianBreakout.mq5` v2 |
| 0 | **Gold Asian Breakout - combined** (Donchian10/100h + prev-day break; deep search on 11 markets) | Gold M15, Asian session | 53% | 1.74 | 1.46 | **$15,953 (10%, -78%)** | ★★★ only robust family out of 11 markets; 95-100% of combined variants profitable in 2026; Q4 2024 dipped -87% | `GoldAsianBreakout.mq5` |
| 0b | Gold Asian Breakout - single signal (Donchian20/50h) | Gold M15, Asian session | 53% | 1.96 | 1.38 | $3,853 (10%, -74%) | ★★★ | `GoldAsianBreakout.mq5` with UsePrevDay=false, Donchian 20, EMA 200 |
| 7 | **News bias -> NY open v2** (FF verdicts on USD medium+high news; wait 60 min, pullback, 1:3, >=2 markets confirm) | 11 markets M1 | ~48% | 1.38 | 1.47 | $1,706 (10%, -57%) | ★★☆ news beats both controls inside the cluster; fragile to the observe time | not built yet |
| 7b | News bias -> NY open v2, **one market is enough** (no 2-market rule) | 11 markets M1 | ~47% | 1.27 | 1.31 | $1,281 (10%, -61%) | ★★☆ the extra single-market days lost in both years | not built yet |
| 8 | **Truth Social tariff posts -> Dow** (tone: threat = sell, deal/pause = buy; 2-min reaction, 60-min hold) | US30 M1 | 54-56% | 1.66 | 2.58 | $2,648 (10%, -15%) / $5,456 (20%, -30%) | ★★☆ beats random-post and other-topic controls; not seen on Nasdaq/S&P | not built yet |
| 1 | **Trend Rider v2, Asian session only** | Nasdaq (USTEC) M1 | ~55% | 1.26 | 1.39 | **$3,862 (2%, -33%)** / $6,613 (3%, -46%) / $14,969 (5%, -66%) | ★★★ all 36 neighbouring settings profitable in both years; OK up to 3-pt spread; Q4 2024 only break-even | `TrendRiderV2.mq5` |
| 2++ | **Gold MACD v3** (v2 + break-even 1.5R->+0.3R + pause after 5 losses until a paper win) | Gold H2 (M1-exact) | 49% | 2.16 | 2.26 | **$17,179 (10%, -33%)**, longest losing streak 6 (v2: 12) | ★★★ neighbours all cap the streak at 6 | `GoldMacdV3.mq5` |
| 2+ | **Gold MACD v2** (H2, stop 2 ATR, 3R target; `results/macd/REPORT.md`) | Gold H2 (M1-exact) | 47% | 1.97 | 2.22 | **$15,968 (10%, -33%)** / $4,811 (5%, -18%) | ★★★ all 1,152 neighbours profitable in 2025-26 (median 2026 $7,709) | `GoldMacdV2.mq5` |
| 2 | **Gold H4 MACD + EMA100** (trend following) | Gold H4 | ~50% | strong (2025 boom year) | +0.24R avg | $2,881 (10%, -33%) / $5,883 (20%, -57%) | ★★☆ 8/8 MACD variants profitable in 2026; few trades (54/yr) | `OnCandleTrend.mq5` |
| 3+ | **BTC Run Fade v2** (stop 3 ATR, hold 48 h, fade only with the EMA50 trend; `results/btc/REPORT.md`) | BTC H1 (M1-exact) | 93% | 1.75 | 2.33 | $1,878 (10%, -19%) / $3,253 (20%, -36%) | ★★★ all 243 neighbours profitable in all 3 periods | `RunFadeV2.mq5` |
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
* **News bias -> trade the NY open** (Forex Factory better/worse verdicts on USD medium+high news, observe the open, join
  markets moving with the news; 11 markets, 1,728 settings): only 1% of settings profitable in both years; it does no
  better than ignoring the news. See `results/news_open/REPORT.md`.
* **Gold Asian breakout v3 method on Nasdaq / Dow / S&P** (8 sessions x 6,912 settings x 2 overlays per market, 55k runs):
  17.6% / 4.4% / 4.2% of settings profitable in all three periods (gold: 91%); 2025 picks fail in 2026.
  See `results/index_breakout/REPORT.md`.
* **Gap tests** (range-pair mean reversion with news filter, cointegration-gated pairs, GBPJPY/USDJPY H1-D1 trend, London ORB;
  6 new FX pairs, ~18,500 settings): 0.3-5% profitable in both years. EURCHF Asian fade has a real gross edge but needs a
  raw-spread account (0.5x Standard: $1,000 -> $1,749 in 2026, 20 trades). See `results/gaps/REPORT.md`.
* **Truth Social post bot, other variants** (straddle / follow / fade at the post, all topics, 11 markets; 508k settings): 1-4%
  profitable in both years; best 2026 with hindsight $51,959. See `results/truth/REPORT.md`.
* **Trump / Fed-chair speech straddle** (114 Trump speeches, 45 Powell/Warsh events, OCO stops at the start, 2,400 settings x
  11 markets): 1.4% profitable in both years, Trump-only 0%; median PF < 1 even with optimistic fills. See `results/speech/REPORT.md`.
* **Non-trend families, 100x target** (pairs mean reversion, RSI(2) snap-back, gap fade, hour seasonality; ~5,800 settings):
  nothing reaches 4x in 2026 even with hindsight; the gap fade only works at an unrealistic Sunday-open spread. Small
  edge: RSI(2) on gold H4 (76% wins, PF 1.5 in 2026, ~33 trades/yr). See `results/alt/REPORT.md`.
* **News lab, 100x target** (continuation / fade / verdict / retest / surprise-size families on every USD, EUR, GBP, JPY,
  CAD release, 2.4M settings): ~4% profitable in both years (luck level); 2025 picks fail in 2026; not one setting reaches
  $100,000 in 2026 even with hindsight (best $52,983, which lost 99% in 2025). See `results/news_lab/REPORT.md`.
* **News bias -> NY open, all on M1** (observe 1-15 M1 candles, M1 entries, M1 ATR stops, 1:3, 2 markets; 4,320 settings):
  0.7% profitable in both years, worse than the against-news control. Keep v2 (60-min wait, opening-range stop).
* **High-impact news trading** (Forex Factory calendar, 316 USD releases, tick-level, gold/Nasdaq/Dow/EURUSD): an OCO straddle
  at 1:3 and a buy+sell 5 s before at 1:4 are both unprofitable; no setting is profitable in both 2025 and 2026. Spreads jump
  about 4-7x at the release and the worst fills slip a lot. See `results/news/REPORT.md`.
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
