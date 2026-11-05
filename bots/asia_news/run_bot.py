#!/usr/bin/env python3
"""Asian-session news bot - main loop.

    python run_bot.py                         # dry-run loop (the default; needs MetaTrader 5 for prices)
    python run_bot.py --signal-only           # no MT5 at all: schedule + actual + signal are logged, nothing else
    python run_bot.py --schedule              # print this week's target releases and what each outcome would do
    python run_bot.py --test-actual "2026-07-29 01:30" AUD   # read one actual now and print the signal
    python run_bot.py --live                  # REAL orders - only if config.toml also says mode = "live"

Strategy settings come from LOCKED.json (frozen before the out-of-sample test); operational settings from
config.toml.  See README.md.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from newsbot.bot import Bot, expand_versions  # noqa: E402
from newsbot.config import load_config, load_locked  # noqa: E402
from newsbot.feeds import FFPageActuals, FFWeeklyJSON, FileActuals  # noqa: E402
from newsbot.signal import currency_bias, instrument_direction  # noqa: E402


class SignalOnlyBroker:
    """No MetaTrader 5: decisions are logged, nothing is priced or traded."""
    signal_only = True

    def is_open(self, pos):
        return False

    def close(self, pos, why="time"):
        return True


def setup_logging(path: str):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler(path, encoding="utf-8")])
    logging.Formatter.converter = time.gmtime          # log in UTC, like the calendar


def sources(cfg):
    c = cfg["calendar"]
    sched = FFWeeklyJSON(c["json_url"], c["cache_file"], int(c["refresh_minutes"]))
    if c["actual_source"] == "file":
        act = FileActuals(c["actual_file"])
    else:
        act = FFPageActuals(c.get("chromium_path", ""), c.get("user_agent", ""))
    return sched, act


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(HERE / "config.toml"))
    ap.add_argument("--live", action="store_true", help="send real orders (config mode must also be 'live')")
    ap.add_argument("--signal-only", action="store_true", help="run without MetaTrader 5 (log signals only)")
    ap.add_argument("--once", action="store_true", help="run one iteration and exit")
    ap.add_argument("--schedule", action="store_true", help="print the target releases of this week and exit")
    ap.add_argument("--test-actual", nargs=2, metavar=("UTC_TIME", "CCY"), help="read one actual and print the signal")
    a = ap.parse_args()

    cfg = load_config(a.config)
    setup_logging(cfg["general"]["log_file"])
    log = logging.getLogger("newsbot")
    versions = expand_versions(load_locked(cfg["general"]["locked_file"]), cfg["general"]["versions"])
    sched, act = sources(cfg)

    if a.schedule:
        from datetime import timedelta

        from newsbot.strategy import full_cfg, signal_pair
        for rel in sched.upcoming():
            figs = ", ".join(f"{f.name} (f {f.forecast:g}, p {f.previous:g})" for f in rel.figures)
            plans = []
            news = {n: v for n, v in versions.items() if full_cfg(v)["entry"] not in ("pair_reaction", "breakout")}
            for bias in (+1, -1):
                d = {n: instrument_direction(bias, rel.currency, v["instrument"], v["symbol"], v.get("map"))
                     for n, v in news.items() if rel.currency in v["currencies"]}
                if any(d.values()):
                    plans.append(("better: " if bias > 0 else "worse: ") +
                                 ", ".join(f"{n} {'BUY' if x > 0 else 'SELL'} {versions[n]['symbol']}"
                                           for n, x in d.items() if x))
            for n, v in versions.items():
                c = full_cfg(v)
                if c["entry"] != "pair_reaction" or rel.currency not in c["currencies"]:
                    continue
                pair, base = signal_pair(rel.currency, c)
                up = base * int((c["map"] or {}).get(c["instrument"], {}).get(rel.currency, 0))
                plans.append(f"{n}: {pair} at {rel.time + timedelta(minutes=int(c['react_min'])):%H:%M} vs the "
                             f"pre-release close: up -> {'BUY' if up > 0 else 'SELL'} {c['symbol']}, down -> "
                             f"{'SELL' if up > 0 else 'BUY'} (entry {rel.time + timedelta(minutes=int(c['entry_delay'])):%H:%M})")
            for n, v in versions.items():
                c = full_cfg(v)
                if c["entry"] != "breakout" or rel.currency not in c["currencies"]:
                    continue
                t3 = rel.time + timedelta(minutes=int(c["brk_min"]))
                plans.append(f"{n}: {c['symbol']} range {rel.time:%H:%M}-{t3 - timedelta(minutes=1):%H:%M}, buy stop above / "
                             f"sell stop below at {t3:%H:%M}, valid until {t3 + timedelta(minutes=int(c['brk_window'])):%H:%M}")
            print(f"{rel.time:%a %Y-%m-%d %H:%M} UTC {rel.currency} {figs}\n    " + (" | ".join(plans) or "not traded"))
        return

    if a.test_actual:
        t = datetime.fromisoformat(a.test_actual[0])
        rows = act.fetch(t, a.test_actual[1].upper())
        print(rows)
        if rows:
            from newsbot.events import Release, make_figure
            figs = [f for f in (make_figure(x["name"], x.get("actual"), x.get("forecast"), x.get("previous"),
                                            x.get("verdict")) for x in rows if (x.get("impact") or "high") == "high") if f]
            rel = Release(t, a.test_actual[1].upper(), figs)
            print(currency_bias(rel, next(iter(versions.values()))["signal"]))
        if hasattr(act, "close"):
            act.close()
        return

    live = a.live and cfg["general"]["mode"] == "live"
    if a.live and not live:
        log.error("--live given but config.toml says mode = %r: refusing to trade live", cfg["general"]["mode"])
        return
    if a.signal_only:
        broker = SignalOnlyBroker()
    else:
        from newsbot.broker import MT5Broker
        broker = MT5Broker(cfg["mt5"], cfg["symbols"], dry_run=not live)
        broker.connect()
    bot = Bot(cfg, versions, sched, act, broker)
    log.info("newsbot started: versions %s, mode %s", ", ".join(versions),
             "LIVE" if live else ("signal-only" if a.signal_only else "dry-run"))
    try:
        while True:
            bot.step()
            if a.once:
                break
            time.sleep(float(cfg["general"]["loop_seconds"]))
    except KeyboardInterrupt:
        log.info("stopped by user (open positions keep their broker-side stop; restart to manage the time exit)")
    finally:
        if hasattr(act, "close"):
            act.close()
        if hasattr(broker, "shutdown"):
            broker.shutdown()


if __name__ == "__main__":
    main()
