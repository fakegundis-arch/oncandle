# Confluence Rider (strategy 2) - backtest

M1, BTCUSD, NAS100, US30, XAUUSD. Risk 0.5% per trade, 1:3 target, stop to entry +0.1R at 1R. A market is only traded when it AND enough other markets trend the same way.

## Full history (Oct 2024 - Oct 2026) - no costs

### All markets together, by variant

| variant                                         |   trades | hit_3R   | breakeven   | stopped   |   avg_r |   profit_factor |   total_r | return   | max_dd   |
|:------------------------------------------------|---------:|:---------|:------------|:----------|--------:|----------------:|----------:|:---------|:---------|
| Strategy 1 (no confirmation)                    |    11292 | 17%      | 32%         | 51%       |   0.015 |            1.03 |      +164 | +69.7%   | -44.2%   |
| 2+ markets agree, pullback entry (as specified) |     3634 | 16%      | 32%         | 51%       |  -0.001 |            1    |        -4 | -10.7%   | -55.0%   |
| 3+ markets agree, pullback entry                |      935 | 18%      | 31%         | 51%       |   0.056 |            1.11 |       +52 | +26.6%   | -19.1%   |
| All 4 agree, pullback entry                     |      125 | 23%      | 26%         | 50%       |   0.214 |            1.42 |       +27 | +13.8%   | -12.2%   |
| 2+ markets agree, enter when group lines up     |    15445 | 17%      | 34%         | 49%       |   0.042 |            1.08 |      +642 | +1532.3% | -38.3%   |
| 3+ markets agree, enter when group lines up     |     7113 | 16%      | 34%         | 50%       |   0.003 |            1.01 |       +20 | -7.1%    | -52.4%   |

### Per market, as specified (2+ agree, pullback entry)

| market   |   trades | hit_3R   | breakeven   | stopped   |   avg_r |   profit_factor |   total_r | return   | max_dd   |
|:---------|---------:|:---------|:------------|:----------|--------:|----------------:|----------:|:---------|:---------|
| BTCUSD   |      791 | 16%      | 33%         | 52%       |  -0.011 |            0.98 |        -9 | -6.1%    | -20.9%   |
| NAS100   |     1087 | 16%      | 32%         | 51%       |  -0.012 |            0.98 |       -13 | -8.9%    | -28.1%   |
| US30     |     1080 | 16%      | 31%         | 53%       |  -0.039 |            0.93 |       -42 | -21.0%   | -29.2%   |
| XAUUSD   |      676 | 18%      | 34%         | 48%       |   0.088 |            1.18 |       +59 | +32.1%   | -21.0%   |

## Full history (Oct 2024 - Oct 2026) - Exness spreads

### All markets together, by variant

| variant                                         |   trades | hit_3R   | breakeven   | stopped   |   avg_r |   profit_factor |   total_r | return   | max_dd   |
|:------------------------------------------------|---------:|:---------|:------------|:----------|--------:|----------------:|----------:|:---------|:---------|
| Strategy 1 (no confirmation)                    |    11568 | 14%      | 27%         | 59%       |  -0.17  |            0.72 |     -1963 | -100.0%  | -100.0%  |
| 2+ markets agree, pullback entry (as specified) |     3661 | 14%      | 28%         | 57%       |  -0.116 |            0.8  |      -426 | -89.1%   | -90.8%   |
| 3+ markets agree, pullback entry                |      940 | 15%      | 28%         | 57%       |  -0.071 |            0.87 |       -67 | -30.2%   | -40.5%   |
| All 4 agree, pullback entry                     |      126 | 20%      | 27%         | 53%       |   0.083 |            1.15 |       +10 | +5.0%    | -12.7%   |
| 2+ markets agree, enter when group lines up     |    15652 | 15%      | 30%         | 55%       |  -0.073 |            0.87 |     -1150 | -99.8%   | -99.8%   |
| 3+ markets agree, enter when group lines up     |     7144 | 14%      | 31%         | 55%       |  -0.086 |            0.84 |      -615 | -96.1%   | -96.3%   |

### Per market, as specified (2+ agree, pullback entry)

| market   |   trades | hit_3R   | breakeven   | stopped   |   avg_r |   profit_factor |   total_r | return   | max_dd   |
|:---------|---------:|:---------|:------------|:----------|--------:|----------------:|----------:|:---------|:---------|
| BTCUSD   |      798 | 13%      | 27%         | 60%       |  -0.181 |            0.7  |      -145 | -52.3%   | -53.9%   |
| NAS100   |     1093 | 15%      | 29%         | 56%       |  -0.097 |            0.83 |      -106 | -42.6%   | -45.0%   |
| US30     |     1090 | 13%      | 27%         | 60%       |  -0.169 |            0.72 |      -184 | -61.1%   | -61.8%   |
| XAUUSD   |      680 | 16%      | 31%         | 52%       |   0.012 |            1.02 |        +8 | +2.2%    | -29.3%   |

## 2026 only - no costs

### All markets together, by variant

| variant                                         |   trades | hit_3R   | breakeven   | stopped   |   avg_r |   profit_factor |   total_r | return   | max_dd   |
|:------------------------------------------------|---------:|:---------|:------------|:----------|--------:|----------------:|----------:|:---------|:---------|
| Strategy 1 (no confirmation)                    |     4147 | 17%      | 32%         | 51%       |   0.03  |            1.06 |      +125 | +67.1%   | -40.5%   |
| 2+ markets agree, pullback entry (as specified) |     1301 | 18%      | 34%         | 48%       |   0.101 |            1.21 |      +131 | +85.5%   | -13.5%   |
| 3+ markets agree, pullback entry                |      379 | 20%      | 33%         | 47%       |   0.17  |            1.36 |       +64 | +36.4%   | -14.1%   |
| All 4 agree, pullback entry                     |       69 | 32%      | 28%         | 41%       |   0.578 |            2.43 |       +40 | +21.7%   | -3.8%    |
| 2+ markets agree, enter when group lines up     |     5980 | 17%      | 35%         | 48%       |   0.049 |            1.1  |      +293 | +269.2%  | -29.1%   |
| 3+ markets agree, enter when group lines up     |     3027 | 15%      | 34%         | 51%       |  -0.014 |            0.97 |       -43 | -25.0%   | -52.4%   |

### Per market, as specified (2+ agree, pullback entry)

| market   |   trades | hit_3R   | breakeven   | stopped   |   avg_r |   profit_factor |   total_r | return   | max_dd   |
|:---------|---------:|:---------|:------------|:----------|--------:|----------------:|----------:|:---------|:---------|
| BTCUSD   |      222 | 17%      | 36%         | 47%       |   0.081 |            1.17 |       +18 | +8.8%    | -9.1%    |
| NAS100   |      401 | 18%      | 35%         | 47%       |   0.074 |            1.15 |       +30 | +14.8%   | -9.6%    |
| US30     |      369 | 18%      | 30%         | 53%       |   0.024 |            1.04 |        +9 | +3.4%    | -10.8%   |
| XAUUSD   |      309 | 20%      | 37%         | 43%       |   0.241 |            1.56 |       +75 | +43.7%   | -5.6%    |

## 2026 only - Exness spreads

### All markets together, by variant

| variant                                         |   trades | hit_3R   | breakeven   | stopped   |   avg_r |   profit_factor |   total_r | return   | max_dd   |
|:------------------------------------------------|---------:|:---------|:------------|:----------|--------:|----------------:|----------:|:---------|:---------|
| Strategy 1 (no confirmation)                    |     4279 | 14%      | 27%         | 59%       |  -0.155 |            0.74 |      -664 | -96.7%   | -96.9%   |
| 2+ markets agree, pullback entry (as specified) |     1309 | 17%      | 31%         | 52%       |   0.02  |            1.04 |       +26 | +9.9%    | -15.9%   |
| 3+ markets agree, pullback entry                |      380 | 17%      | 32%         | 50%       |   0.065 |            1.13 |       +25 | +11.8%   | -17.0%   |
| All 4 agree, pullback entry                     |       69 | 28%      | 29%         | 43%       |   0.419 |            1.96 |       +29 | +15.3%   | -4.8%    |
| 2+ markets agree, enter when group lines up     |     6034 | 15%      | 32%         | 53%       |  -0.035 |            0.93 |      -212 | -70.4%   | -78.1%   |
| 3+ markets agree, enter when group lines up     |     3036 | 15%      | 31%         | 54%       |  -0.076 |            0.86 |      -230 | -70.5%   | -75.1%   |

### Per market, as specified (2+ agree, pullback entry)

| market   |   trades | hit_3R   | breakeven   | stopped   |   avg_r |   profit_factor |   total_r | return   | max_dd   |
|:---------|---------:|:---------|:------------|:----------|--------:|----------------:|----------:|:---------|:---------|
| BTCUSD   |      222 | 14%      | 31%         | 55%       |  -0.083 |            0.85 |       -19 | -9.3%    | -12.2%   |
| NAS100   |      404 | 17%      | 32%         | 51%       |  -0.005 |            0.99 |        -2 | -1.9%    | -8.9%    |
| US30     |      372 | 17%      | 27%         | 56%       |  -0.022 |            0.96 |        -8 | -5.1%    | -11.1%   |
| XAUUSD   |      311 | 19%      | 36%         | 45%       |   0.175 |            1.39 |       +55 | +30.1%   | -6.1%    |
