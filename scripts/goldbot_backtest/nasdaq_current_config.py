"""The live bot's Nasdaq trades of Nov 1 - 10 2026, redone with TODAY's companion settings (config.yaml: entry offset
30, SL 40, TP 40, 0.5 lot, 120-s window, one USTECm straddle at a time, break-even off, trailing from +150).

Every straddle the live bot armed (any feed - Telegram, X, Trump - since the companion rides on each) is an arming
moment, taken from the log with its AI verdict.  At each one a USTECm straddle is armed if none is open, at:
  * the bot's own quote when the live companion was armed then (logged stops minus / plus the offset in force), else
  * the last tick before the arming second (Exness ticks, to Nov 8), else the previous minute's close (MT5 export).
Ticks: replay.simulate, exact.  Nov 9 - 10 (no ticks): the 1-minute logic of m1_nasdaq.py, flagged.  From the Nov 5
22:33 UTC restart the live companion already ran these settings except the lot (0.1, then 0.5 from Nov 9 14:40), so
from then on an arming moment with no live companion stays unarmed, as live.

usage: python3 -I scripts/goldbot_backtest/nasdaq_current_config.py <newsbot.log> <USTECm M1 export.csv>
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live_check as LC  # noqa: E402
import live_log  # noqa: E402
import m1_nasdaq as M1  # noqa: E402
import replay as R  # noqa: E402

START = pd.Timestamp("2026-11-01 15:00")       # the companion went live with the Nov 1 restart
SAME = pd.Timestamp("2026-11-05 22:33")        # from this restart the live companion ran today's settings but the lot


def main():
    log, m1_path = sys.argv[1], sys.argv[2]
    comp = R.load_config(str(R.BOT / "config.yaml")).companion
    off, sl, tp, lot, win = comp.entry_offset, comp.stop_loss, comp.take_profit, comp.lot, comp.cancel_after_seconds
    stages = R.break_even_stages(comp) if comp.break_even_enabled else []
    trail = comp.trailing if comp.trailing.enabled else None
    tk = LC.load("USTECm")
    tick_end = pd.Timestamp(int(tk["t"][-1]), unit="s")
    m = M1.load_m1(m1_path)
    S = live_log.straddles(log)
    G = S[(S.symbol == "XAUUSDm") & (S.arm_utc >= START)].sort_values("arm_utc")
    C = S[S.symbol == "USTECm"]
    E = pd.read_csv(R.OUT / "live_log_check" / "live_trade_exits.csv", parse_dates=["fill_utc"])
    E = E[E.symbol == "USTECm"]
    M = pd.read_csv(R.OUT / "live_log_check" / "nasdaq_live_trades_nov9_10_m1.csv", parse_dates=["fill_utc"])
    live_res = pd.concat([E[E.usd.notna()][["fill_utc", "side", "fill", "lots", "usd"]],
                          M[["fill_utc", "side", "fill", "lots", "usd"]]])
    open_until = pd.Timestamp("2000-01-01")
    rows = []
    for g in G.itertuples():
        arm = g.arm_utc
        lc = C[(C.arm_utc - arm).abs() <= pd.Timedelta(seconds=3)]
        lc = lc.iloc[0] if len(lc) else None
        base = dict(arm_utc=arm, feed=g.feed, title=g.title, ai=g.ai)
        if lc is not None and lc.n_fills:
            x = live_res[(live_res.fill_utc - lc.fill_utc).abs() <= pd.Timedelta(seconds=5)]
            base.update(live=f"{lc.side} {lc.fill:.2f}, {lc.lots} lot" + (f": {x.usd.iloc[0]:+.2f}" if len(x) and
                                                                            pd.notna(x.usd.iloc[0]) else ""))
        elif lc is not None:
            base.update(live="armed, no fill")
        else:
            base.update(live="not armed")
        if arm < open_until:
            rows.append(dict(base, result="skipped: previous Nasdaq trade still open"))
            continue
        if arm >= SAME and lc is None:
            # same settings live (only the lot differs, which changes no price or time): the live bot's choice stands
            rows.append(dict(base, result="not armed, as live (a Nasdaq trade was still open)"))
            continue
        veto = (lc.ai_utc if lc is not None and lc.ai == "close" else g.ai_utc if g.ai == "close" else None)
        veto = pd.Timestamp(veto) if veto is not None and pd.notna(veto) else None
        a = LC.UTC(arm)
        if lc is not None:                           # the bot's own quote: undo the offset in force then
            _, _, _, coff, *_ = LC.settings(a)
            ask, bid, src = lc.buy_stop - coff, lc.sell_stop + coff, "bot's quote"
        elif arm <= tick_end:
            if R.market_shut(tk, a):
                rows.append(dict(base, result="Nasdaq closed"))
                continue
            j = int(np.searchsorted(tk["t"], a, side="left")) - 1
            ask, bid, src = float(tk["ask_last"][j]), float(tk["bid_last"][j]), "Exness ticks"
        else:
            prev = m.loc[:arm.floor("min") - pd.Timedelta(minutes=1)]
            if not len(prev) or arm.floor("min") - prev.index[-1] > pd.Timedelta(minutes=3):
                rows.append(dict(base, result="Nasdaq closed"))
                continue
            p = prev.iloc[-1]
            ask, bid, src = p.close + p.sp, p.close, "MT5 1-minute bars"
        buy, sell = round(ask + off, 2), round(bid - off, 2)
        base.update(buy_stop=buy, sell_stop=sell, quote=src)
        if arm <= tick_end - pd.Timedelta(minutes=10):
            pos, close = R.simulate("USTECm", tk, a, buy, sell, sl, tp, win, stages, trail,
                                    LC.UTC(veto) if veto is not None else None, 0.0, 0.0)
            open_until = pd.Timestamp(close, unit="s")
            if not pos:
                rows.append(dict(base, result="no fill" + (" (AI veto)" if veto is not None else "")))
                continue
            q = pos[0]
            usd = (q.exit - q.fill) * (1 if q.side == R.BUY else -1) * lot
            rows.append(dict(base, side=q.side, fill=round(q.fill, 2), fill_utc=pd.Timestamp(q.fill_ts, unit="s"),
                             exit=round(q.exit, 2), exit_utc=pd.Timestamp(q.exit_ts, unit="s"), result=q.why,
                             usd=round(usd, 2), prices="Exness ticks"))
            continue
        end = min(arm + pd.Timedelta(seconds=win), veto) if veto is not None else arm + pd.Timedelta(seconds=win)
        fts, side, sure = M1.fill_side(m, arm, end, buy, sell)
        if not sure and lc is not None and buy == round(lc.buy_stop, 2):
            side = lc.side if lc.n_fills else ""     # same orders as live: the log settles what the bars cannot
            fts = (lc.fill_utc - pd.Timedelta(seconds=3)).floor("min") if lc.n_fills else None
            sure = True
        if side in ("", "both"):
            open_until = end
            rows.append(dict(base, result="no fill" if side == "" else "both stops in one minute (unclear)"))
            continue
        fill = buy if side == "BUY" else sell
        s_, t_ = (fill - sl, fill + tp) if side == "BUY" else (fill + sl, fill - tp)
        ets, why, sure_x = M1.exit_from(m, side, fts, s_, t_)
        open_until = (ets + pd.Timedelta(minutes=1)) if ets is not None else pd.Timestamp("2100-01-01")
        usd = {"take profit": tp, "stop loss": -sl}.get(why, np.nan) * lot
        rows.append(dict(base, side=side, fill=fill, fill_utc=fts, exit_utc=ets, result=why, usd=usd,
                         prices="MT5 1-minute bars" + ("" if sure and sure_x else " (unclear)")))
    D = pd.DataFrame(rows)
    D.to_csv(R.OUT / "live_log_check" / "nasdaq_live_current_config.csv", index=False)
    T = D[D.side.notna()] if "side" in D else D.iloc[:0]
    pd.set_option("display.width", 260)
    pd.set_option("display.max_colwidth", 52)
    print(T[["arm_utc", "feed", "title", "side", "fill", "exit_utc", "result", "usd", "prices", "live"]].to_string(index=False))
    print(f"\n{len(T)} trades, {int((T.usd > 0).sum())} won, {int((T.usd < 0).sum())} lost, total {T.usd.sum():+.2f} USD "
          f"(Telegram only {T[T.feed == 'TELEGRAM'].usd.sum():+.2f})")
    print("arming moments:", D.result.where(D.side.isna() if "side" in D else True, "traded").value_counts().to_dict())


if __name__ == "__main__":
    main()
