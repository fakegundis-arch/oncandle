"""The acid test of the backtest: replay the days covered by the bot's own log AS THE BOT LIVED THEM, with the same
code path as the normal backtest (replay.replay), and score it post by post and trade by trade against the log.

What is taken from the log (and only this):
  * which posts the bot received and when (a post it never received - bot stopped, channel not watched yet - is not
    replayed); for a post it armed, the second it armed; for the rest, the second it received it;
  * its AI verdicts and the second they landed;
  * restarts (the bot's open-straddle stores and dedupe cache start empty after each);
  * the straddles of the other feeds: X straddles hold the global slot, X / Trump companions hold the USTECm slot,
    from arming until veto / window end / the position's exit.
The settings in force are a timeline of the repo's committed configs, corrected where the log shows the live file was
ahead of the commits (see PERIODS).  Everything else - gates, order of checks, stop prices from Exness quotes, fills,
SL / TP, break-even, exits - is computed by the replay and compared with what the log says happened.

usage: python3 -I scripts/goldbot_backtest/as_live.py <bot repo> <newsbot.log>
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("GOLDBOT_END", "2026-11-11")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live_log  # noqa: E402
import replay as R  # noqa: E402

OFF = pd.Timedelta(hours=3)
UTC = lambda s: int((pd.Timestamp(s) - pd.Timestamp("1970-01-01")) // pd.Timedelta(seconds=1))  # noqa: E731


def cfg_at(commit: str):
    y = subprocess.check_output(["git", "-C", str(R.BOT), "show", f"{commit}:config.yaml"])
    with tempfile.NamedTemporaryFile("wb", suffix=".yaml", delete=False) as f:
        f.write(y)
    c = R.load_config(f.name)
    os.unlink(f.name)
    return c


def periods() -> list:
    """(from UTC, settings).  Commits: 49bb4ca Sep 25, 49c9762 Nov 4, cb6d625 Nov 10.  Log evidence for the dates:
    gold SL 6 on Oct 28, 5 on Nov 2-3, 3 from Nov 5 15:04; USTECm stops 25 apart from the quote until Nov 4 18:01 and 30
    from Nov 5 15:03, SL / TP 30 then 40; lot 0.1 until Nov 9 13:08 and 0.5 from 16:04; last USTECm break-even move
    Nov 5 21:44 UTC, none after the 22:33 restart; @WalterBloomberg first watched at the Nov 4 13:14 restart."""
    p0 = cfg_at("49bb4ca")
    p1 = cfg_at("49c9762")
    p1.telegram_feed.channels = [c for c in p1.telegram_feed.channels if "walter" not in c.lower()]
    p2 = cfg_at("49c9762")
    p3 = cfg_at("cb6d625")
    c = p3.companion
    c.lot, c.break_even_enabled, c.break_even_trigger, c.break_even_offset = 0.1, True, 20.0, 5.0
    c.break_even_2_enabled, c.break_even_2_trigger, c.break_even_2_offset = True, 80.0, 60.0
    p4 = cfg_at("cb6d625")
    p4.companion.lot = 0.1
    p5 = cfg_at("cb6d625")
    return [(UTC("2026-01-01"), R.derive(p0)), (UTC("2026-11-01 15:14"), R.derive(p1)),
            (UTC("2026-11-04 13:14"), R.derive(p2)), (UTC("2026-11-04 18:45"), R.derive(p3)),
            (UTC("2026-11-05 22:33"), R.derive(p4)), (UTC("2026-11-09 14:40"), R.derive(p5))]


class LiveCtx:
    def __init__(self, log: str, exits: pd.DataFrame | None = None):
        self.P, _, _ = live_log.parse(log)
        self.S = live_log.straddles(log)
        self.periods = periods()
        self.starts = []
        for raw in open(log, encoding="utf-8", errors="replace"):
            if "NewsBot starting" in raw:
                self.starts.append(UTC(pd.Timestamp(raw[:19]) - OFF))
        self.post = {}
        for r in self.P.itertuples():
            armed = getattr(r, "armed_utc", None)
            det = UTC(armed) if armed is not None and pd.notna(armed) else UTC(r.recv_utc)
            ai = getattr(r, "ai", None)
            veto = UTC(r.ai_utc) if ai == "close" and pd.notna(r.ai_utc) else None
            self.post[(r.channel, int(r.post_id))] = (det, ai if isinstance(ai, str) else "", veto,
                                                      float(r.latency_s) if pd.notna(r.latency_s) else 0.0)
        # the other feeds' straddles: [arm, close) intervals
        ex = exits if exits is not None else pd.DataFrame(columns=["symbol", "fill_utc", "exit_utc"])
        self.x_gold, self.other_comp = [], []
        for s in self.S[self.S.feed != "TELEGRAM"].itertuples():
            a = UTC(s.arm_utc)
            if s.n_fills:
                m = ex[(ex.symbol == s.symbol) & ((ex.fill_utc - s.fill_utc).abs() <= pd.Timedelta(seconds=2))]
                done = m.exit_utc.iloc[0] if len(m) and pd.notna(m.exit_utc.iloc[0]) else None
                close = UTC(done) + 2 if done is not None else a + 600
            elif s.ai == "close" and pd.notna(s.ai_utc):
                close = UTC(s.ai_utc)
            elif pd.notna(s.no_fill_utc):
                close = UTC(s.no_fill_utc)
            else:
                close = a + 121
            if s.symbol == "USTECm":
                self.other_comp.append((a, close))
            elif s.feed == "X":
                self.x_gold.append((a, close))

    def det(self, ch, pid):
        hit = self.post.get((ch, int(pid)))
        return hit[0] if hit else None

    def age(self, ch, pid, whole_seconds):
        """The post's age when the bot judged it: never less than the delay the bot itself logged on receipt."""
        return max(float(whole_seconds), self.post[(ch, int(pid))][3])

    def settings(self, det):
        return [d for t, d in self.periods if t <= det][-1]

    def epoch(self, det):
        return int(np.searchsorted(self.starts, det, side="right"))

    def veto(self, ch, pid):
        det, ai, veto, _ = self.post[(ch, int(pid))]
        if ai:                                     # the verdict the live bot got
            return veto
        return R.real_veto(ch, pid, det)           # the bot never asked (it did not arm): my recorded verdict, if any

    def global_holders(self, det):
        return sum(a <= det < c for a, c in self.x_gold)

    def comp_busy(self, det):
        return any(a <= det < c for a, c in self.other_comp)


def norm(d) -> str:
    d = str(d)
    for k, v in (("ARMED", "ARMED"), ("blacklisted", "blacklisted"), ("stale", "stale"), ("NO orders", "market shut"),
                 ("market shut", "market shut"), ("too short", "too short"), ("media post", "too short"),
                 ("repost", "repost"), ("no keyword", "no keyword match")):
        if d.startswith(k):
            return v
    return d


def main():
    log = sys.argv[2]
    out = R.OUT / "as_live"
    out.mkdir(parents=True, exist_ok=True)
    import live_check as LC
    exits = LC.live_exits(log)
    live = LiveCtx(log, exits)
    cfg = R.load_config(str(R.BOT / "config.yaml"))
    posts = R.load_posts()
    ticks = {s: R.load_ticks(s) for s in (cfg.symbol, cfg.companion.symbol)}
    windows = R.blackout_windows(cfg.news_blackout)
    sc = dict(lat=0, slip=0.0, exit_slip=0.0, ai="live", qb=True, fill=os.environ.get("GOLDBOT_FILL", "last"))
    tr, dec = R.replay(cfg, posts, ticks, windows, sc, live=live)

    # ---- decisions
    P = live.P.rename(columns={"channel": "ch", "post_id": "id"})
    D = P.merge(dec.rename(columns={"channel": "ch", "post_id": "id", "decision": "replay"}), on=["ch", "id"], how="inner")
    D["live_n"], D["replay_n"] = D.decision.map(norm), D.replay.map(norm)
    D = D[D.replay_n != "no price data yet"]
    same = D.live_n == D.replay_n
    lines = [f"posts the live bot received that the replay could price: {len(D)}",
             f"same decision: {int(same.sum())} ({same.mean():.2%})", "",
             pd.crosstab(D.live_n, D.replay_n, rownames=["live"], colnames=["replay"]).to_string(), ""]
    D[~same][["recv_utc", "ch", "id", "decision", "replay", "text"]].to_csv(out / "decision_mismatches.csv", index=False)

    # ---- trades: one row per (post, symbol) the live bot or the replay armed
    S = live.S[live.S.feed == "TELEGRAM"].copy()
    armed = P[P.armed_utc.notna()][["ch", "id", "armed_utc", "text"]]
    S["k"] = S.arm_utc.dt.floor("s")
    gold = S[S.symbol == "XAUUSDm"].merge(armed.assign(k=armed.armed_utc.dt.floor("s")), on="k", how="left")
    gold = gold[[t.strip().startswith(str(ti).strip()[:30]) if isinstance(t, str) else False
                 for t, ti in zip(gold.text, gold.title)]]
    key = gold[["arm_utc", "title", "ch", "id"]]
    S = S.merge(key, on=["arm_utc", "title"], how="left")
    comp_key = S[S.symbol == "XAUUSDm"][["ch", "id", "title"]].drop_duplicates()
    Sc = S[S.symbol == "USTECm"].drop(columns=["ch", "id"]).merge(comp_key, on="title", how="left")
    Sc = Sc[Sc.id.notna()].drop_duplicates(["arm_utc", "title"])
    L = pd.concat([S[(S.symbol == "XAUUSDm") & S.id.notna()], Sc])
    L["id"] = L.id.astype(int)
    L = L[["ch", "id", "symbol", "arm_utc", "lots", "side", "fill", "fill_utc", "n_fills", "buy_stop", "sell_stop", "title"]]
    L = L.rename(columns={"side": "live_side", "fill": "live_fill", "fill_utc": "live_fill_utc", "lots": "live_lots",
                          "buy_stop": "live_buy_stop", "sell_stop": "live_sell_stop"})
    T = tr.rename(columns={"channel": "ch", "post_id": "id"})
    T = T[~T.exit_reason.astype(str).str.startswith(("not armed", "no Nasdaq"))]
    T1 = T.sort_values("fill_ts").groupby(["ch", "id", "symbol"]).agg(
        side=("side", "first"), fill=("fill", "first"), fill_ts=("fill_ts", "first"), n=("side", lambda x: (x != "").sum()),
        usd=("usd", "sum"), exit_reason=("exit_reason", "first"), buy_stop=("buy_stop", "first"),
        sell_stop=("sell_stop", "first")).reset_index()
    C = L.merge(T1, on=["ch", "id", "symbol"], how="outer", indicator=True)
    end = {s: pd.Timestamp(int(ticks[s]["t"][-1]), unit="s") for s in ticks}
    C = C[~((C._merge != "right_only") & (C.arm_utc > C.symbol.map(end) - pd.Timedelta(minutes=10)))]

    def verdict(r):
        if r._merge == "left_only":
            return "live armed, replay did not"
        if r._merge == "right_only":
            return "replay armed, live did not"
        lf, rf = bool(r.n_fills and r.n_fills > 0), bool(r.n and r.n > 0)
        if lf and rf:
            return "both filled, same side" if r.live_side == r.side else "both filled, OTHER side"
        if lf:
            return "live filled, replay did not"
        if rf:
            return "replay filled, live did not"
        return "neither filled"
    C["check"] = C.apply(verdict, axis=1)
    C.to_csv(out / "trades_live_vs_replay.csv", index=False)
    tr.to_csv(out / "replay_trades.csv", index=False)
    lines += ["straddles (Telegram feed) with price data:",
              C.groupby(["symbol", "check"]).size().to_string(), ""]
    both = C[C.check == "both filled, same side"]
    for sym, g in both.groupby("symbol"):
        dpx = (g.fill - g.live_fill).abs()
        lines.append(f"{sym}: {len(g)} fills on the same side; fill price identical to the cent in {(dpx < 0.011).sum()}, "
                     f"median difference {dpx.median():.2f}, largest {dpx.max():.2f}")
    # ---- money: live trades rebuilt from their real fills vs the replay's own trades
    ex = exits[(exits.feed == "TELEGRAM") & exits.usd.notna()]
    lines += ["", f"live Telegram trades with price data, rebuilt from their real fills: {len(ex)} trades, "
                  f"{ex.usd.sum():+.2f} USD (gold {ex[ex.symbol == 'XAUUSDm'].usd.sum():+.2f}, "
                  f"Nasdaq {ex[ex.symbol == 'USTECm'].usd.sum():+.2f})"]
    f = tr[tr.side != ""]
    lines.append(f"replay's own trades over the same days: {len(f)} trades, {f.usd.sum():+.2f} USD "
                 f"(gold {f[f.symbol == 'XAUUSDm'].usd.sum():+.2f}, Nasdaq {f[f.symbol == 'USTECm'].usd.sum():+.2f})")
    (out / "scoreboard.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
