# 4newgolds Telegram bot - version 2 (Nov 10 2026)

Protocol, engine and runner: `scripts/goldbot_backtest/v2_lab.py`, `v2_build.py` (committed before any version-2
result).  Built on Jan 1 - May 31 2026; one run on Jun 1 - Nov 9 2026.  Same machinery as the replay of the current bot
(`replay.py`); the fast engine reproduces the replay's Jan-May result to the cent (-$950.58).  Fixed lots as the bot:
gold 0.01 ($1 per $1), USTECm 0.5 ($0.50 per point).  No AI review in either version (no OpenAI key here).
Caveat stated before the search: the current bot's Jun-Nov results had already been looked at and some option ranges
(e.g. a trigger without "trump", turning the Nasdaq companion off) were chosen knowing its full-year breakdown.

## Search (Jan-May 2026): 27,648 settings
channels (all / FinancialJuice / WalterBloomberg / FJ + WB) x trigger (current keywords or ❗/🔴, the same without
"trump", principal-speaking headline or ❗/🔴, principal only, ❗/🔴 only, keywords only) x news blackout (on / off) x
gold straddle distance ($2 / 3 / 5 / 8) x order life (1 / 2 / 5 min) x stop ($3 / 6) x target (none / $15) x
management (current break-even + trailing / none) x time exit (none / 30 min) x Nasdaq companion (off / current / wide).

* Only 2 settings pass every rule (>= 60 positions, profit in Jan-Mar and in Apr-May, profit factor >= 1.3, still
  profitable with worse fills, drawdown smaller than the profit).  The current bot in the same grid: -$950.58.
* **Luck check failed:** with every post moved to a random time 1-14 days away, the same search finds 568 / 213 / 32
  passing settings and a best of +$665 / +$784 / +$299 - far more than the real posts (2 passing, best +$60).  On
  Jan-May, trading these channels' posts did no better than trading at random moments.

**Version 2 (the pick):** WalterBloomberg posts only; trigger = the current keywords without "trump" (Fed, Fed's,
Warsh, Federal Reserve, Bessent, Scott, Treasury, White House) or ❗/🔴; USD news blackout on; gold straddle $8 from the
price, live 2 minutes; stop $3; no target; current break-even / trailing; close any trade after 30 minutes; Nasdaq
companion off.  Jan-May: 81 positions, +$60.36, profit factor 1.46, worst drawdown -$24, with worse fills +$24 (profit
factor 1.13); only 8 % of neighbouring settings also pass.

## One run on Jun 1 - Nov 9 2026
| | Positions | P&L | Profit factor | Worst drawdown | Jun-Aug | Sep - Nov 9 | Worse fills |
|---|---|---|---|---|---|---|---|
| **Version 2** | 14 | **+$11.11** | 1.53 | -$15.34 | -$2.80 | +$13.91 | +$14.29 (PF 1.88) |
| Current bot | 816 | **-$358.32** | 0.93 | -$1,165.10 | -$622.17 | +$263.85 | -$1,554.43 (PF 0.74) |

Version 2 meets the declared test rule (P&L > 0, above the current bot's, profit factor >= 1.2), but with 14 trades in
five months and +$11, it mostly avoids losses by trading rarely - no Nasdaq companion and wider gold orders that seldom
fill - and it did not beat the luck check on Jan-May.  It is a safer configuration of the bot, not a proven edge.

**Correction (Nov 10 2026):** the Jun-Nov run above had no USD news blackout on Nov 1-9 (the calendar file ended Oct
31).  Rerun of the same pick with the November calendar added (`test_calendar_fixed.json`): version 2 13 positions,
+$14.11, profit factor 1.78, worst drawdown -$15.34 (worse fills +$17.53); current bot -$352.32.
