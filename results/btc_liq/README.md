# Bitcoin liquidation bot (Nov 7 2026)

Signals from Binance USD-M BTCUSDT public data (every trade -> 1-second taker buy / sell volume; 5-minute open
interest; ~30-second order-book depth), trades on Exness BTCUSDm 1-second bid / ask (the user's broker).  Free
liquidation records do not exist for 2026 (Binance's liquidation snapshots stop in 2024, coin-margined only), so
liquidations are inferred: forced liquidations hit the market as aggressive orders and shrink open interest.
Protocol and engine: `scripts/btc_liq/liq_lab.py` (committed before any result); grid `liq_build.py`; data
`binance_data.py` + `scripts/telegram_news/exness_ticks.py`.  BUILD Jan 1 - Jun 30 2026; the loaders refuse Jul-Oct
except inside the one `final_test()`.

Rules: act 2 s after the signal is known (a 5-minute open-interest value is assumed known 60 s after its time); Exness
ask / bid + 1 spread; stop fixed at entry (>= 3 spreads); stop before target; flat before >= 10-min quote pauses;
stress = 5 s late, 2 spreads in, 1 more out; one position at a time; 10 % risk per trade.  Exness BTC spread: median
$18 in Jan-Jun (about 0.6 x the typical 1-minute move of ~$30).

## Search (Jan-Jun 2026): 20,736 settings
| Family | Idea | Settings | Median PF | Pass |
|---|---|---|---|---|
| A cascade | burst of one-sided aggressive volume + sharp move -> ride it | 3,456 | 0.45 | 0 |
| B flush fade | same burst, wait for no new low / high, then fade | 10,368 | 0.44 | 0 |
| C liquidation map | estimated liquidation clusters from open-interest build-up -> trade toward the bigger one | 4,608 | 0.42 | 0 |
| D open-interest drop | 5-min open-interest fall >= x % with a price move >= y % -> follow / fade | 2,304 | 0.84 | 7 |

After a detected cascade the price moves only ~0.1 x the 1-minute vol in the next minutes, less than the ~1.2-vol
round-trip cost, so A-C lose almost everywhere.  Luck check (all events moved 1-14 days, 3 seeds): 0 settings pass in
every seed (best fake R +21 / +51 / +33); real: 7 pass, 83 pass all but the drawdown rule.

**Pick** (pre-registered rule): D, open interest falls >= 0.7 % in 5 min while BTC moves >= 0.3 % -> follow the move
(60 s after the 5-minute mark, +2 s), stop 5 x 1-min vol, target 2R, out after 5 min.  Jan-Jun: 51 trades, +19.5R,
PF 2.41, win 61 %, DD -30 %, $1,000 -> $5,262, stress PF 1.47.
Information-only (declared before the test): highest Jan-Jun balance among settings meeting every rule except
drawdown: open interest >= 0.3 %, move >= 0.3 %, follow, stop 2 vol, target 4R, out after 5 min.  Jan-Jun 216 trades,
+97.9R, PF 1.85, $1,000 -> $571k, DD -64 %, stress PF 1.25.

## Jul 1 - Oct 31 2026 (unseen, one run)
Binance published open interest = 0 in 8 five-minute rows on 2026-10-15 (13:40-14:40); the first run read them as
-100 % drops and took 3 trades from them (`btc_liq_test.json`).  The loader now treats 0 as missing (none before
July, so the build is unchanged) and the same settings were rerun with only that fix (`btc_liq_test_clean_oi.json`):

| | Trades | R | PF | Win | $1,000 at 10 % | DD | 5 % | 2 % | 1 % | Stress PF |
|---|---|---|---|---|---|---|---|---|---|---|
| Pick, as first run | 18 | +14.5 | 4.48 | 61 % | $3,569 | -19 % | $1,971 | $1,326 | $1,154 | 2.48 |
| **Pick, zero-OI fixed** | **15** | **+12.8** | **4.26** | 67 % | **$3,051** | **-19 %** | $1,815 | $1,282 | $1,134 | 2.32 |
| Info-only, as first run | 66 | +46.2 | 2.40 | 45 % | $28,014 | -47 % | $7,099 | $2,374 | $1,563 | 1.45 |
| Info-only, zero-OI fixed | 63 | +43.6 | 2.38 | 46 % | $23,061 | -54 % | $6,341 | $2,260 | $1,524 | 1.41 |

Pick per month (fixed): Jul 4 / -0.55R, Aug 6 / +7.48R, Sep 2 / +4.0R, Oct 3 / +1.84R.  By the pre-registered success
rule (>= 20 trades, R > 0, PF >= 1.3, DD better than -35 %) it fails only on the trade count (15-18 < 20).

Position size matters: at 10 % risk with a tight stop the lot grows with the balance.  Account with the position
capped at N x the balance (notional):

| | no cap | 100x | 20x | 10x |
|---|---|---|---|---|
| Pick Jan-Jun | $5,262 (max 2.0 BTC) | $5,262 | $3,371 | $2,183 |
| Pick Jul-Oct | $3,051 (max 2.3 BTC) | $3,051 | $1,848 | $1,355 |
| Info-only Jan-Jun | $571,461 (max 1,226 BTC) | $346,301 | $10,929 | $3,791 |
| Info-only Jul-Oct | $23,061 (max 54 BTC) | $14,907 | $2,102 | $1,479 |

The info-only version's large numbers need positions no retail account can fill; the pick's never exceeded ~2 BTC.
Caveats: few trades (about one a week); Exness's BTC spread was lower in Oct (median $6.40 vs $18 in Jan-Jun), which
helps the test months a little; swaps on positions held over the rollover are not modelled (holds are 5 minutes).
