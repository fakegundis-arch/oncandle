"""End-to-end check: the LIVE loop (newsbot.bot.Bot) replayed minute by minute over Jan-Jun 2026 must take the same
trades as the backtest (newsbot.backtest.make_trades).  usage: python check_replay.py [LOCKED.json]"""
import json
import logging
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import harness as H  # noqa: E402
from harness import L  # noqa: E402
from newsbot.bot import Bot  # noqa: E402
from newsbot.config import DEFAULTS  # noqa: E402
from newsbot.events import releases_from_frame  # noqa: E402
from newsbot.replay import Clock, ReplayActuals, ReplayBroker, ReplaySchedule  # noqa: E402

logging.basicConfig(level=logging.WARNING)


def replay(versions: dict) -> pd.DataFrame:
    cal = H.CAL
    rels = releases_from_frame(cal)
    syms = sorted({v["symbol"] for v in versions.values()})
    frames = {s: H.px(s) for s in syms}
    costs = {s: L.COST[s] for s in syms}
    clock = Clock(rels[0].time)
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    cfg["general"].update(state_file="", journal_file="", max_entry_lag_seconds=120)
    cfg["calendar"].update(poll_seconds=10, actual_timeout_seconds=600)
    bot = Bot(cfg, versions, ReplaySchedule(cal, clock), ReplayActuals(cal, clock, 30), ReplayBroker(frames, costs, clock),
              clock)
    span = max(int(v["entry_delay"]) + int(v["hold_min"]) for v in versions.values()) + 10
    steps = set()
    for r in rels:
        if not (pd.Timestamp(L.TRAIN[0]) <= pd.Timestamp(r.time) < pd.Timestamp(L.TRAIN[1])):
            continue
        t = r.time - timedelta(minutes=1)
        while t <= r.time + timedelta(minutes=span):
            steps.add(t)
            steps.add(t + timedelta(seconds=30))
            t += timedelta(minutes=1)
    for t in sorted(steps):
        clock.t = t
        bot.step()
    rows = []
    for p in bot.closed:
        risk = abs(p.entry - p.sl)
        rows.append(dict(version=p.version, entry_time=pd.Timestamp(p.opened).floor("min"),
                         exit_time=pd.Timestamp(p.extra.get("exit_time")), dir=p.direction,
                         r=p.direction * (p.exit_price - p.entry) / risk, reason=p.exit_reason))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    locked = json.loads(Path(sys.argv[1]).read_text())["versions"] if len(sys.argv) > 1 else None
    if locked is None:
        from robust import BASE, VERS
        locked = {"gold": {**BASE, **VERS["gold"]}, "nasdaq": {**BASE, **VERS["nasdaq"]}}
        locked.update({f"pair_{c.lower()}": c2 for c, c2 in zip(("AUD", "NZD", "JPY"),
                                                                 H.pair_cfgs({**BASE, "instrument": "pair"}).values())})
    rep = replay(locked)
    ok_all = True
    for name, v in locked.items():
        bt = H.trades(v).reset_index(drop=True)
        rp = rep[rep.version == name].sort_values("entry_time").reset_index(drop=True)
        same_n = len(bt) == len(rp)
        m = bt.merge(rp, on="entry_time", how="outer", suffixes=("_bt", "_live"), indicator=True)
        both = m[m._merge == "both"]
        dr = (both.r_bt - both.r_live).abs()
        ok = same_n and (m._merge == "both").all() and (both.dir_bt == both.dir_live).all() and (dr < 0.05).all()
        ok_all &= bool(ok)
        print(f"{name:9s} backtest n={len(bt):2d} R={bt.r.sum():6.2f} | live replay n={len(rp):2d} R={rp.r.sum():6.2f} | "
              f"max |dR| {dr.max() if len(dr) else 0:.3f} | {'MATCH' if ok else 'DIFFERENT'}")
        if not ok:
            print(m[["entry_time", "dir_bt", "dir_live", "r_bt", "r_live", "exit_time_bt", "exit_time_live", "_merge"]])
    print("ALL MATCH" if ok_all else "SOME DIFFERENCES")
