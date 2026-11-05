"""The live loop.  Non-blocking: every `loop_seconds` it
  1. manages open positions (time exit / weekend cap; notices broker-side stop or target hits),
  2. refreshes the weekly schedule (cached, at most hourly) and picks the target releases,
  3. from each release time polls the actual source until every figure has an actual (or the timeout passes ->
     the release is skipped),
  4. runs the SAME signal / plan code as the backtest (newsbot.strategy.make_plan) and, at release + entry_delay,
     sends the order with its stop (and target) sized to risk `risk` x equity,
and persists its state so a restart neither repeats nor forgets a trade.

Versions with entry = "pair_reaction" (v2 Nasdaq) need no actual: at the release time the bot schedules the entry;
at release + react_min it reads the signal pair (AUDUSD / NZDUSD): pre-release close from its M1 bars, post = the
first quote at / after that minute; the direction rule is newsbot.strategy.reaction_from_prices (the backtest's), and
NAS100 is bought / sold at the first quote at / after release + entry_delay.  Pair or NAS100 not quoting within
`max_entry_lag_seconds` -> skipped (as in the backtest)."""
from __future__ import annotations

import csv
import json
import logging
import math
from datetime import datetime, timedelta
from pathlib import Path

from .broker import Position, utcnow
from .events import Release
from .signal import currency_bias
from .strategy import full_cfg, make_plan, pre_release_close, reaction_from_prices, signal_pair

log = logging.getLogger("newsbot.bot")


def expand_versions(locked: dict, wanted: list[str]) -> dict:
    out = {}
    for w in wanted:
        hits = {k: v for k, v in locked.items() if k == w or k.startswith(w + "_")}
        if not hits:
            raise KeyError(f"version {w!r} not in LOCKED.json ({list(locked)})")
        out.update(hits)
    return out


class Bot:
    def __init__(self, cfg: dict, versions: dict, schedule, actuals, broker, clock=utcnow):
        self.cfg, self.schedule, self.actuals, self.broker, self.clock = cfg, schedule, actuals, broker, clock
        self.versions = {k: full_cfg(v) for k, v in versions.items()}
        g, c = cfg["general"], cfg["calendar"]
        self.risk, self.lag = float(g["risk"]), timedelta(seconds=float(g["max_entry_lag_seconds"]))
        self.poll, self.timeout = float(c["poll_seconds"]), float(c["actual_timeout_seconds"])
        self.require_all = bool(c.get("require_all_figures", True))
        self.state_file = Path(g["state_file"]) if g.get("state_file") else None
        self.journal = Path(g["journal_file"]) if g.get("journal_file") else None
        self.done: dict[str, str] = {}             # release key -> outcome
        self.pending: dict[str, dict] = {}         # release key -> {"rel": Release, "last": datetime}
        self.entries: list[dict] = []              # scheduled entries {version, rel, at}
        self.positions: list[Position] = []
        self.closed: list[Position] = []
        self.react = {n for n, v in self.versions.items() if v["entry"] == "pair_reaction"}
        for n in self.react:
            v = self.versions[n]
            if int(v["react_min"]) > int(v["entry_delay"]):
                raise ValueError(f"{n}: react_min must not be later than entry_delay")
        self._load()

    # ---------------------------------------------------------------- persistence
    def _load(self):
        if self.state_file and self.state_file.exists():
            s = json.loads(self.state_file.read_text())
            self.done = s.get("done", {})
            self.positions = [Position(**p) for p in s.get("positions", [])]
            log.info("state restored: %d releases handled, %d open positions", len(self.done), len(self.positions))

    def _save(self):
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"done": self.done, "positions": [p.to_dict() for p in self.positions]},
                                              indent=1, default=str))

    def _journal(self, p: Position):
        self.closed.append(p)
        if not self.journal:
            return
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        new = not self.journal.exists()
        with self.journal.open("a", newline="") as fh:
            w = csv.writer(fh)
            if new:
                w.writerow(["version", "symbol", "release", "dir", "lots", "opened", "entry", "sl", "tp", "exit_reason",
                            "exit_price", "R"])
            risk = abs(p.entry - p.sl)
            r = p.direction * (p.exit_price - p.entry) / risk if risk and not math.isnan(p.exit_price) else ""
            w.writerow([p.version, p.symbol, p.release, p.direction, p.lots, p.opened, p.entry, p.sl, p.tp,
                        p.exit_reason, p.exit_price, r])

    # ---------------------------------------------------------------- one iteration
    def step(self) -> None:
        now = self.clock()
        self._manage(now)
        self._watch_releases(now)
        self._enter(now)
        self._save()

    def _manage(self, now: datetime):
        keep = []
        for p in self.positions:
            if not self.broker.is_open(p):                       # stop / target first (as the backtest)
                if not p.closed:
                    p.closed, p.exit_reason = True, "stop/target at broker"
                    log.info("%s %s closed by the broker (stop or target)", p.version, p.symbol)
            elif now >= datetime.fromisoformat(p.exit_by):
                self.broker.close(p, "time")
            if p.closed:
                self._journal(p)
            else:
                keep.append(p)
        self.positions = keep

    def _schedule_reactions(self, rel: Release, now: datetime):
        """entry = "pair_reaction": no actual needed - schedule the price check / entry of each such version."""
        for name in self.react:
            v = self.versions[name]
            if rel.currency not in v["currencies"] or now < rel.time:
                continue
            rk = f"{name}|{rel.key()}"
            if rk in self.done or any(e.get("rk") == rk for e in self.entries):
                continue
            at = rel.time + timedelta(minutes=int(v["entry_delay"]))
            if now > at + self.lag:
                self.done[rk] = "missed (bot was not running)"
                continue
            if getattr(self.broker, "signal_only", False):
                self.done[rk] = "not traded: pair_reaction needs MT5 prices (signal-only mode)"
                log.info("%s %s: %s", name, rel.key(), self.done[rk])
                continue
            pair = signal_pair(rel.currency, v)
            self.entries.append({"version": name, "rel": rel, "at": at, "rk": rk, "rx": None,
                                 "react_at": rel.time + timedelta(minutes=int(v["react_min"]))})
            log.info("release time reached: %s - %s: reading %s at %s, entry at %s", rel.key(), name,
                     pair[0] if pair else "?", f"{rel.time + timedelta(minutes=int(v['react_min'])):%H:%M}", f"{at:%H:%M}")

    def _watch_releases(self, now: datetime):
        try:
            rels = self.schedule.upcoming()
        except Exception as e:                                   # keep trading what is already scheduled
            log.warning("schedule source failed: %s", e)
            rels = []
        news = {n: v for n, v in self.versions.items() if n not in self.react}
        latest_delay = max([int(v["entry_delay"]) for v in news.values()] or [0])
        for rel in rels:
            if self.react:
                self._schedule_reactions(rel, now)
            if not news:
                continue
            k = rel.key()
            if k in self.done or k in self.pending or now < rel.time:
                continue
            if now > rel.time + timedelta(minutes=latest_delay) + self.lag:
                self.done[k] = "missed (bot was not running)"
                continue
            if not any(rel.currency in v["currencies"] for v in news.values()):
                self.done[k] = "no version trades this currency"
                continue
            self.pending[k] = {"rel": rel, "last": None}
            log.info("release time reached: %s - polling for the actual", k)
        for k, pend in list(self.pending.items()):
            rel = pend["rel"]
            if pend["last"] is not None and (now - pend["last"]).total_seconds() < self.poll:
                continue
            pend["last"] = now
            got = self._read_actual(rel)
            if got is not None:
                del self.pending[k]
                self._decide(got, now, k)
            elif now > rel.time + timedelta(seconds=self.timeout):
                del self.pending[k]
                self.done[k] = "skipped: no actual before the timeout"
                log.warning("%s: no actual within %.0f s - skipped", k, self.timeout)

    def _read_actual(self, rel: Release) -> Release | None:
        from .events import is_target_event, make_figure
        try:
            rows = self.actuals.fetch(rel.time, rel.currency)
        except Exception as e:
            log.warning("actual source failed: %s", e)
            return None
        if not rows:
            return None
        figs = []
        for x in rows:
            if not is_target_event(rel.currency, x.get("impact") or "high", rel.time):
                continue
            f = make_figure(x["name"], x.get("actual"), x.get("forecast"), x.get("previous"), x.get("verdict"))
            if f is not None and f.has_actual:
                figs.append(f)
        if not figs:
            return None
        want = {f.name for f in rel.figures}
        if self.require_all and not want <= {f.name for f in figs}:
            return None                                           # keep polling until every figure is out
        return Release(rel.time, rel.currency, figs)

    def _decide(self, rel: Release, now: datetime, k: str):
        out = []
        b = currency_bias(rel, next(iter(self.versions.values()))["signal"])
        for name, v in self.versions.items():
            if name in self.react:
                continue
            plan = make_plan(rel, v, None, atr_value=1.0)         # direction only; the stop is sized at entry
            if plan is None:
                out.append(f"{name}: no trade")
                continue
            if not getattr(self.broker, "signal_only", False):
                self.entries.append({"version": name, "rel": rel, "at": plan.entry_after})
            out.append(f"{name}: {'BUY' if plan.direction > 0 else 'SELL'} {v['symbol']} at {plan.entry_after:%H:%M}")
        figs = ", ".join(f"{f.name} {f.actual:g} vs {f.forecast:g} (FF {f.verdict})" for f in rel.figures)
        self.done[k] = "; ".join(out)
        log.info("%s: %s | bias %+d (%s) -> %s", k, figs, b.bias, b.why, "; ".join(out))

    def _enter(self, now: datetime):
        """An entry fills on the first tick at or after its planned time; if the symbol does not quote within
        `max_entry_lag_seconds` (market closed, e.g. gold's daily break) the trade is skipped - as in the backtest."""
        rest = []
        for e in self.entries:
            react = "rk" in e
            if react and e["rx"] is None and now >= e["react_at"]:
                if not self._read_reaction(e, now):
                    continue                                       # decided: no trade / pair not quoting
            if now < e["at"] or (react and e["rx"] is None):
                rest.append(e)
                continue
            if now > e["at"] + self.lag:
                log.warning("%s %s: %s did not quote within the entry window - skipped", e["version"], e["rel"].key(),
                            self.versions[e["version"]]["symbol"])
                if react:
                    self.done[e["rk"]] = "skipped: no quote within the entry window"
                continue
            tk = self.broker.tick(self.versions[e["version"]]["symbol"])
            if tk is None or tk[2] < e["at"]:
                rest.append(e)                                    # no fresh quote yet: keep waiting
                continue
            try:
                ok = self._open(e["version"], e["rel"], now, tk, e.get("rx"))
                if react:
                    self.done[e["rk"]] = ("entered: " if ok else "not entered (see log): ") + e["rx"].why
            except Exception as ex:
                log.exception("%s: entry failed: %s", e["version"], ex)
                if react:
                    self.done[e["rk"]] = f"entry failed: {ex}"
        self.entries = rest

    def _read_reaction(self, e: dict, now: datetime) -> bool:
        """pair_reaction: read the signal pair once a fresh quote at / after react_at exists.  Returns True if the entry
        stays scheduled (waiting for a quote, or a direction was found), False if it is finished (no trade / skipped)."""
        name, rel = e["version"], e["rel"]
        v = self.versions[name]
        pair = signal_pair(rel.currency, v)[0]
        if now > e["react_at"] + self.lag:
            self.done[e["rk"]] = f"skipped: {pair} did not quote within the window"
            log.warning("%s %s: %s", name, rel.key(), self.done[e["rk"]])
            return False
        tk = self.broker.tick(pair)
        if tk is None or tk[2] < e["react_at"]:
            return True                                            # wait for the first quote at / after react_at
        pre = pre_release_close(rel, v, self.broker.bars_m1(pair, 240))
        rx = reaction_from_prices(rel, v, pre, tk[0], tk[2])
        if rx is None or rx.direction == 0:
            self.done[e["rk"]] = "no trade: " + (rx.why if rx else f"{pair} had no quote before the release")
            log.info("%s %s: %s", name, rel.key(), self.done[e["rk"]])
            return False
        e["rx"] = rx
        log.info("%s: %s -> %s %s at %s", name, rx.why, "BUY" if rx.direction > 0 else "SELL", v["symbol"],
                 f"{e['at']:%H:%M}")
        return True

    def _open(self, name: str, rel: Release, now: datetime, tk, reaction=None):
        v = self.versions[name]
        sym = v["symbol"]
        if any(p.symbol == sym for p in self.positions):
            log.info("%s: %s already has an open position - one position per instrument, skipped", name, sym)
            return False
        bars = self.broker.bars_m1(sym, int(v["stop_atr_tf"]) * (int(v["stop_atr_n"]) + 2) * 3)
        plan = make_plan(rel, v, bars, reaction=reaction)
        if plan is None:
            log.warning("%s: no plan (ATR unavailable?)", name)
            return False
        bid, ask, _ = tk
        entry = ask if plan.direction > 0 else bid
        sl = entry - plan.direction * plan.stop_dist
        tp = entry + plan.direction * plan.target_dist if math.isfinite(plan.target_dist) else 0.0
        risk_money = self.risk * self.broker.equity()
        lots, loss1 = self.broker.lots_for(sym, plan.direction, entry, sl, risk_money)
        if lots <= 0:
            log.warning("%s: minimum lot would risk %.2f > %.2f - skipped", name, loss1, risk_money)
            return False
        pos = Position(0, name, sym, plan.direction, lots, entry, sl, tp, now.isoformat(), plan.exit_by.isoformat(),
                       rel.key(), extra={"why": plan.why, "stop_dist": plan.stop_dist, "risk_money": risk_money})
        pos = self.broker.open(pos)
        if pos is not None:
            self.positions.append(pos)
            log.info("%s: %s", name, plan.why)
            return True
        return False
