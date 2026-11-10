"""XAUUSDm for Nov 10 2026 (not in the Exness tick archive yet), from the user's MT5 export of 1-minute bars (bid OHLC
+ spread in points, UTC; checked against the tick archive Oct 1 - Nov 9: 68 % of OHLC values equal to the tenth of
a cent, 82 % within 5 cents).

Each live gold fill without tick data is run forward from its real fill price with the bot's own management:
SL from the fill (live value from the log), break-even stages on wicks (staged_break_even_sl), the social trailing
stop (trailing_sl), no TP.  Minute bars hide the order of prices inside a minute, so every trade is run under every
order: the fill minute ignored / adverse move first / favourable move first, and each later minute adverse-first or
favourable-first.  If all orders give the same exit the result is certain; otherwise the range is shown.

usage: python3 -I scripts/goldbot_backtest/m1_gold.py <XAUUSDm M1 export.csv> <newsbot.log>
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live_log  # noqa: E402
import replay as R  # noqa: E402
from m1_nasdaq import load_m1  # noqa: E402

OUT = R.OUT / "live_log_check"


def walk(m, side, fill, sl, fill_min, stages, trail, fill_mode, later_mode):
    """One path through the minute bars -> (exit minute, exit price, why)."""
    buy = side == "BUY"
    best = fill
    sp = R.SPEC["XAUUSDm"]

    def sym(px_bid, spread):
        return R.SymbolInfo(name="XAUUSDm", bid=px_bid, ask=px_bid + spread, point=sp["point"], digits=sp["digits"],
                            volume_min=0.01, volume_max=200.0, volume_step=0.01, trade_contract_size=sp["contract"],
                            tick_value=1.0)

    be = trailed = False
    bars = m.loc[fill_min:]
    for k, (ts, b) in enumerate(bars.iterrows()):
        mode = fill_mode if k == 0 else later_mode
        if mode == "ignore":
            continue
        adverse = b.low if buy else b.high + b.sp            # what closes a BUY (bid) / a SELL (ask)
        favour = b.high if buy else b.low + b.sp

        def hit(cur_sl):
            return (adverse <= cur_sl) if buy else (adverse >= cur_sl)

        def manage(cur_sl):
            nonlocal best, be, trailed
            best = max(best, favour) if buy else min(best, favour)
            s = sym(b.close, b.sp)
            new = R.staged_break_even_sl(R.BUY if buy else R.SELL, fill, best, cur_sl, stages, s)
            if new is not None and R.sl_placeable_now(R.BUY if buy else R.SELL, new, s):
                cur_sl, be = new, True
            price = b.close if buy else b.close + b.sp
            new = R.trailing_sl(R.BUY if buy else R.SELL, fill, price, cur_sl, trail.start, trail.distance, trail.step, s)
            if new is not None:
                cur_sl, trailed = new, True
            return cur_sl

        if mode == "adverse":
            if hit(sl):
                return ts, sl, "trailing stop" if trailed else "break-even stop" if be else "stop loss"
            sl = manage(sl)
        else:                                                # favourable first: move the SL, then test it
            sl = manage(sl)
            if hit(sl):
                return ts, sl, "trailing stop" if trailed else "break-even stop" if be else "stop loss"
    return None, np.nan, "open at end of data"


def main():
    m = load_m1(sys.argv[1])
    cfg = R.load_config(str(R.BOT / "config.yaml"))
    stages = R.break_even_stages(cfg.strategy)
    trail = cfg.social_trailing_stop
    S = live_log.straddles(sys.argv[2])
    G = S[(S.symbol == "XAUUSDm") & (S.n_fills > 0) & (S.fill_utc >= "2026-11-10")]
    rows = []
    for s in G.itertuples():
        fill_min = (s.fill_utc - pd.Timedelta(seconds=3)).floor("min")    # the real fill is 0-5 s before the log line
        outs = set()
        for fm, lm in itertools.product(("ignore", "adverse", "favour"), ("adverse", "favour")):
            ts, px, why = walk(m, s.side, s.fill, s.sl, fill_min, stages, trail, fm, lm)
            usd = (px - s.fill) * (1 if s.side == "BUY" else -1) * s.lots * 100.0
            outs.add((ts, why, round(usd, 2)))
        outs = sorted(outs, key=lambda o: o[2])
        rows.append(dict(fill_utc=s.fill_utc, side=s.side, fill=s.fill, sl=s.sl, lots=s.lots,
                         certain=len({(o[1], o[2]) for o in outs}) == 1,
                         exit_minute=outs[0][0], result=outs[0][1], usd=outs[0][2],
                         other_orders=" | ".join(f"{o[1]} {o[2]:+.2f}" for o in outs[1:]), title=s.title))
    D = pd.DataFrame(rows)
    D.to_csv(OUT / "gold_live_trades_nov10_m1.csv", index=False)
    print(D.drop(columns="title").to_string(index=False))


if __name__ == "__main__":
    main()
