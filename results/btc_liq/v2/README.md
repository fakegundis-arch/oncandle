# Bitcoin liquidation bot - version 2 (Nov 9 2026)

> **CORRECTION (Nov 9 2026) - these results are NOT valid.**  A Binance 5-minute metrics row with create_time `ct`
> describes the 5 minutes AFTER `ct` (its taker buy / sell ratio matches Binance taker volume in [ct, ct+300) with
> correlation 0.997 vs 0.107 for [ct-300, ct); its open-interest value is the snapshot at about ct+300).  Versions 1
> and 2 used each row from ct + 60 s, i.e. about 4 minutes before it could be known - look-ahead.  Rebuilt with the
> row used only from ct + 360 s (end of its window + 60 s), on Jan-Jun 2026: version 1 88 trades, -3.7R, PF 0.84,
> $1,000 -> $581; version 2 177 trades, -1.2R, PF 0.96, $1,000 -> $718.  The open-interest-drop edge was an artifact
> of the timestamp error.  Found by a version-3 research agent and verified by the lead.


Protocol `scripts/btc_liq/v2_lab.py`, search `v2_build.py` (committed before any version-2 result).  Built on
Jan 1 - Jun 30 2026 only; then ONE run on Jul 1 - Oct 31 2026 and ONE run on Jan 1 - Nov 30 2025.  Jul-Oct 2026 is no
longer fully clean (version 1's trades there had been looked at, and the "give trades more room" idea came from
them); 2025 had never been touched by any version and is the clean exam.  Same execution rules as version 1 (Binance
5-minute open interest known 60 s after its time, Exness BTCUSDm order 2 s later at ask / bid + 1 spread, stop before
target, stress 5 s late + 2 spreads in + 1 out), 10 % risk, position capped at 100 x the balance.  The fast numba
engine matched agents/common.py in 84,327 comparisons (0 mismatches).

## Search: 1,382,400 settings on Jan-Jun 2026
Trigger (open-interest fall 0.2-1 %, price move 0.2-0.8 %, over 5 or 10 min, "still moving", taker-flow confirmation,
thin book), entry (market, limit 0.5 / 1 vol back), stop 1.5-8 vol, target 0.5-3R / none, timer 2-60 min, management
(none, break-even, trailing 1R / 2R), 1 or up to 3 positions.  6,842 settings pass every rule (15,916 all but the
drawdown rule).  Luck check (all signals moved 1-14 days): 0 / 16 / 184 settings pass; best fake R +10 / +48 / +38
(real best +146).  The pick's own Jan-Jun R (+25.0) does NOT beat the best fake settings (+48.2, +38.5), so by the
declared rule its Jan-Jun result alone is not proof against luck (the grid as a whole is far stronger than the fakes).
Before the analysis, Jan-Jun price action after version-1 signals showed the push lasts ~1-5 minutes and fades by
30-60 minutes; longer holds did not win the search.

**Version 2** (pick: most passing neighbours, 82 %): Binance open interest falls >= 0.5 % in 5 minutes while BTC moves
>= 0.3 % and the net aggressive (taker) volume in those 5 minutes agrees with the move -> follow the move with a
market order (60 s + 2 s after the 5-minute mark); stop 8 x 1-min vol; target 1.5R; after +1R the stop trails 1R
behind the best price; out after 5 minutes; one trade at a time.

## Results, $1,000 at 10 % risk (version 1 on the same engine)
| Period | Version | Trades | R | PF | Win | $1,000 at 10 % | Max DD | 5 % | 2 % | Stress PF ($) | Success rule |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Jan-Jun 2026 (build) | V2 | 97 | +25.0 | 2.40 | - | $9,198 | -20 % | - | - | 1.74 | - |
| | V1 | 52 | +19.7 | 2.43 | - | $5,351 | -30 % | - | - | 1.47 | - |
| Jul-Oct 2026 (seen for V1) | **V2** | 28 | +8.8 | 2.67 | 71 % | $2,187 | -17 % | $1,515 | $1,188 | 1.82 ($1,534) | pass |
| | V1 | 15 | +12.8 | 4.26 | 67 % | $3,051 | -19 % | $1,815 | $1,282 | 2.32 ($1,666) | fail (15 trades) |
| Jan-Nov 2025 (clean exam) | **V2** | 188 | +17.9 | 1.49 | 55 % | $4,121 | -44 % | $2,227 | $1,409 | 1.14 ($1,235) | fail (DD) |
| | V1 | 112 | +12.0 | 1.31 | 49 % | $1,996 | -55 % | $1,599 | $1,244 | 0.93 ($449) | fail (DD) |

V2 per month, 2025 (trades / R): Jan 24 / -3.05, Feb 23 / +4.68, Mar 35 / +8.03, Apr 30 / +2.39, May 15 / +1.22,
Jun 11 / -1.64, Jul 5 / +0.20, Aug 6 / +0.05, Sep 4 / +1.93, Oct 27 / +2.01, Nov 8 / +2.09 (9 of 11 months up).
Jul-Oct 2026: Jul 6 / +1.28, Aug 8 / +3.39, Sep 7 / +3.07, Oct 7 / +1.08.  Largest position: about 1 BTC.

Reading: the open-interest-drop momentum effect shows up in all three periods for version 2 (PF 2.40 / 2.67 / 1.49),
and version 2 beats version 1 on the clean year (more trades, higher PF, smaller drawdown, still profitable with
worse fills, where version 1 is not).  It is not "extremely" more profitable: on the clean year at 10 % risk the
drawdown reached -44 %; at 5 % risk $1,000 -> $2,227 with -24 %.
