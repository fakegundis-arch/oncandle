"""Check the replay against the bot's own live log, straddle by straddle.

Every straddle the live bot armed (Telegram, X and Trump feeds; gold and the USTECm companion) is taken from the log
(live_log.straddles) and run through the replay's order engine (replay.simulate) with what the bot actually had:
  * armed at the logged second (log clock UTC+3), priced from the last quote before that second (the USTECm stop
    prices in the log match this to the cent when the bot was not busy);
  * USTECm stop prices exactly as logged; gold stops at ask + offset / bid - offset with the offset in force;
  * the settings in force, read from the fills in the log (the live config ran ahead of the git commits):
      until Nov 1 14:41 UTC        gold offset 6, SL 6;   no companion
      Nov 1 15:14 - Nov 4 18:45    gold offset 6, SL 5;   USTECm offset 25, SL 30, TP 30, 0.1 lot
      Nov 4 18:45 - Nov 9 14:40    gold offset 5, SL 3;   USTECm offset 30, SL 40, TP 40, 0.1 lot
      from Nov 9 14:40             gold offset 5, SL 3;   USTECm offset 30, SL 40, TP 40, 0.5 lot
    gold break-even 4.5 -> +1 and 15 -> +12, trailing 24 / 4 (as config.yaml); USTECm break-even 20 -> +5 and
    80 -> +60 until the Nov 6 01:33 (local) restart, off after it (the log's last USTECm break-even move is 00:44 that
    night, and the Nov 6 17:37 trade lost the full 40 points, -$4.00, as the balance shows);
  * the AI verdict at the logged time (a CLOSE cancels the pending orders, as live);
  * no extra slippage: stops fill at their price or the first quote through it.
Then the simulated result is compared with the live one: filled or not, which side, when, at what price.

usage: python3 -I scripts/goldbot_backtest/live_check.py <newsbot.log> <out_dir>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live_log  # noqa: E402
import replay as R  # noqa: E402

UTC = lambda s: int(pd.Timestamp(s).value // 10**9)  # noqa: E731
PERIODS = [  # (from, gold offset, gold SL, USTECm offset, SL, TP, USTECm break-even on)
    (UTC("2026-01-01"), 6.0, 6.0, None, None, None, False),
    (UTC("2026-11-01 15:00"), 6.0, 5.0, 25.0, 30.0, 30.0, True),
    (UTC("2026-11-04 18:45"), 5.0, 3.0, 30.0, 40.0, 40.0, True),
    (UTC("2026-11-05 22:33"), 5.0, 3.0, 30.0, 40.0, 40.0, False),
]


def settings(ts):
    return [p for p in PERIODS if p[0] <= ts][-1]


def load(sym):
    zs = [np.load(R.ROOT / f"data/ticks_exness/{sym}/2026-{m}.npz") for m in ("10", "11")]
    return {k: np.concatenate([z[k] for z in zs]) for k in zs[0].files}


def main():
    log, out = sys.argv[1], Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    cfg = R.load_config(str(R.BOT / "config.yaml"))
    gstages = R.break_even_stages(cfg.strategy) if cfg.strategy.break_even_enabled else []
    gtrail = cfg.social_trailing_stop if cfg.social_trailing_stop.enabled else None
    comp = cfg.companion
    comp.break_even_enabled, comp.break_even_trigger, comp.break_even_offset = True, 20.0, 5.0
    comp.break_even_2_enabled, comp.break_even_2_trigger, comp.break_even_2_offset = True, 80.0, 60.0
    cstages = R.break_even_stages(comp)
    ctrail = comp.trailing if comp.trailing.enabled else None
    tk = {s: load(s) for s in ("XAUUSDm", "USTECm")}
    S = live_log.straddles(log)
    rows = []
    for s in S.itertuples():
        t = tk[s.symbol]
        arm = UTC(s.arm_utc)
        base = s._asdict()
        base.pop("Index")
        if s.no_orders:
            rows.append(dict(base, check="live placed no orders (" + s.no_orders + ")"))
            continue
        if arm > t["t"][-1] - 600:
            rows.append(dict(base, check="no price data yet"))
            continue
        if R.market_shut(t, arm):
            rows.append(dict(base, check="market shut in the data"))
            continue
        _, goff, gsl, coff, csl, ctp, cbe = settings(arm)
        j = int(np.searchsorted(t["t"], arm, side="left")) - 1          # last quote before the logged second
        sym = R.sym_info(s.symbol, t, j)
        if s.symbol == "USTECm":
            buy, sell, sl, tp, stages, trail = s.buy_stop, s.sell_stop, csl, ctp, cstages if cbe else [], ctrail
        else:
            buy, sell = R.round_price(sym.ask + goff, sym), R.round_price(sym.bid - goff, sym)
            sl, tp, stages, trail = gsl, 0.0, gstages, gtrail
        veto = UTC(s.ai_utc) if s.ai == "close" else None
        pos, close = R.simulate(s.symbol, t, arm, buy, sell, sl, tp, 120, stages, trail, veto, 0.0, 0.0)
        q = pos[0] if pos else None
        mult = R.SPEC[s.symbol]["contract"] * s.lots
        usd = sum((p.exit - p.fill) * (1 if p.side == R.BUY else -1) * mult for p in pos)
        live_fill = s.n_fills > 0
        sim_fill = q is not None
        if live_fill and sim_fill:
            same = "same side" if q.side == s.side else "OTHER side"
            check = f"both filled, {same}"
        elif live_fill:
            check = "live filled, replay did not"
        elif sim_fill:
            check = "replay filled, live did not"
        else:
            check = "neither filled"
        rows.append(dict(base, check=check, sim_buy_stop=buy, sim_sell_stop=sell, sim_side=q.side if q else "",
                         sim_fill_utc=pd.Timestamp(q.fill_ts, unit="s") if q else None, sim_fill=q.fill if q else None,
                         sim_exit_utc=pd.Timestamp(q.exit_ts, unit="s") if q else None, sim_exit=q.exit if q else None,
                         sim_exit_reason=q.why if q else "", sim_n_fills=len(pos), sim_usd=round(usd, 2)))
    D = pd.DataFrame(rows)
    D.to_csv(out / "live_vs_replay_straddles.csv", index=False)
    print(D.groupby(["symbol", "check"]).size().to_string())
    return D


if __name__ == "__main__":
    main()


def live_exits(log, tk=None, sl_model="stop"):
    """Each LIVE fill, run forward from its real fill price and second with the settings in force -> exit and $."""
    cfg = R.load_config(str(R.BOT / "config.yaml"))
    gstages = R.break_even_stages(cfg.strategy) if cfg.strategy.break_even_enabled else []
    gtrail = cfg.social_trailing_stop if cfg.social_trailing_stop.enabled else None
    comp = cfg.companion
    comp.break_even_enabled, comp.break_even_trigger, comp.break_even_offset = True, 20.0, 5.0
    comp.break_even_2_enabled, comp.break_even_2_trigger, comp.break_even_2_offset = True, 80.0, 60.0
    cstages = R.break_even_stages(comp)
    tk = tk or {s: load(s) for s in ("XAUUSDm", "USTECm")}
    S = live_log.straddles(log)
    rows = []
    for s in S[S.n_fills > 0].itertuples():
        t = tk[s.symbol]
        f = UTC(s.fill_utc)
        _, goff, gsl, coff, csl, ctp, cbe = settings(UTC(s.arm_utc))
        if s.symbol == "USTECm":
            sl_d, tp_d, stages, trail = csl, ctp, cstages if cbe else [], None
        else:
            sl_d, tp_d, stages, trail = gsl, 0.0, gstages, gtrail
        row = dict(feed=s.feed, symbol=s.symbol, title=s.title, lots=s.lots, side=s.side, fill_utc=s.fill_utc,
                   fill=s.fill, live_sl=s.sl, live_be_sl=s.be_sl)
        if f > t["t"][-1]:
            rows.append(dict(row, exit_reason="no price data yet"))
            continue
        # only the side that filled live, as a stop at the live fill price, from the live arm time (the "filled" log
        # line comes from the bot's 2-s loop, up to ~5 s after the real fill)
        a = UTC(s.arm_utc)
        buy, sell = (s.fill, -1e9) if s.side == "BUY" else (1e9, s.fill)
        pos, _ = R.simulate(s.symbol, t, a, buy, sell, sl_d, tp_d, 10**7, stages, trail, None, 0.0, 0.0,
                            sl_model=sl_model)
        p = pos[0]
        usd = (p.exit - p.fill) * (1 if p.side == R.BUY else -1) * R.SPEC[s.symbol]["contract"] * s.lots
        rows.append(dict(row, sim_fill_utc=pd.Timestamp(p.fill_ts, unit="s"), sim_fill=p.fill,
                         exit_utc=pd.Timestamp(p.exit_ts, unit="s"), exit=p.exit, exit_reason=p.why, usd=round(usd, 2)))
    return pd.DataFrame(rows)
