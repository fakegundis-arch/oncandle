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
`max_entry_lag_seconds` -> skipped (as in the backtest).

Versions with entry = "breakout" (v3 Nasdaq) need no actual either: at the release time the bot schedules the version;
at release + brk_min it reads NAS100's M1 bars, computes the range with newsbot.strategy.breakout_setup (the
backtest's rule) and places a buy stop above / a sell stop below it, sized to risk `risk` x equity (a level the market
is already beyond is entered at market).  When one fills the other is cancelled and the position's stop / target are
re-anchored to the real fill; untriggered orders are cancelled after brk_window minutes.  If both fill before the bot
sees either (one minute whipsaw) both positions are closed at once.  Orders are kept in the state file, so a restart
picks them up."""
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
from .strategy import (breakout_exit_by, breakout_setup, full_cfg, make_plan, pre_release_close, reaction_from_prices,
                       signal_pair)

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
        self.brk_v = {n for n, v in self.versions.items() if v["entry"] == "breakout"}
        self.brk: list[dict] = []                  # breakout setups: scheduled, orders working (JSON-safe, persisted)
        self._load()

    # ---------------------------------------------------------------- persistence
    def _load(self):
        if self.state_file and self.state_file.exists():
            s = json.loads(self.state_file.read_text())
            self.done = s.get("done", {})
            self.positions = [Position(**p) for p in s.get("positions", [])]
            self.brk = s.get("breakouts", [])
            log.info("state restored: %d releases handled, %d open positions, %d breakout setups", len(self.done),
                     len(self.positions), len(self.brk))

    def _save(self):
        if not self.state_file:
            return
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps({"done": self.done, "positions": [p.to_dict() for p in self.positions],
                                               "breakouts": self.brk}, indent=1, default=str))

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
        self._breakouts(now)
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
        news = {n: v for n, v in self.versions.items() if n not in self.react and n not in self.brk_v}
        latest_delay = max([int(v["entry_delay"]) for v in news.values()] or [0])
        for rel in rels:
            if self.react:
                self._schedule_reactions(rel, now)
            if self.brk_v:
                self._schedule_breakouts(rel, now)
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
            if name in self.react or name in self.brk_v:
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

    # ---------------------------------------------------------------- v3 breakout
    def _schedule_breakouts(self, rel: Release, now: datetime):
        """entry = "breakout": from the release time, schedule the range read and the stop orders at release + brk_min."""
        for name in self.brk_v:
            v = self.versions[name]
            if rel.currency not in v["currencies"] or now < rel.time:
                continue
            rk = f"{name}|{rel.key()}"
            if rk in self.done or any(b["rk"] == rk for b in self.brk):
                continue
            place_at = rel.time + timedelta(minutes=int(v["brk_min"]))
            if now > place_at + self.lag:
                self.done[rk] = "missed (bot was not running)"
                continue
            if getattr(self.broker, "signal_only", False):
                self.done[rk] = "not traded: breakout needs MT5 prices (signal-only mode)"
                log.info("%s %s: %s", name, rel.key(), self.done[rk])
                continue
            sym = v["symbol"]
            if any(p.symbol == sym for p in self.positions) or \
                    any(self.versions[b["version"]]["symbol"] == sym for b in self.brk):
                self.done[rk] = f"skipped: {sym} already has a position or working orders (one at a time)"
                log.info("%s %s: %s", name, rel.key(), self.done[rk])
                continue
            self.brk.append({"version": name, "rk": rk, "key": rel.key(), "rel_time": rel.time.isoformat(),
                             "currency": rel.currency, "place_at": place_at.isoformat(), "legs": None})
            log.info("release time reached: %s - %s: range of the first %d min, stop orders at %s", rel.key(), name,
                     int(v["brk_min"]), f"{place_at:%H:%M}")

    def _breakouts(self, now: datetime):
        keep = []
        for b in self.brk:
            try:
                alive = self._brk_step(b, now)
            except Exception as ex:                                  # never leave orders behind on an error
                log.exception("%s %s: breakout step failed: %s", b["version"], b["key"], ex)
                end = datetime.fromisoformat(b.get("expire_at") or b["place_at"]) + self.lag
                alive = now <= end
                if not alive:
                    self._brk_cancel(b)
                    self.done[b["rk"]] = f"failed: {ex}"
            if alive:
                keep.append(b)
        self.brk = keep

    def _brk_cancel(self, b: dict, keep: str | None = None):
        for d, lg in (b.get("legs") or {}).items():
            if d != keep and lg.get("ticket"):
                self.broker.cancel_order(lg["ticket"])

    def _brk_step(self, b: dict, now: datetime) -> bool:
        """One breakout setup; True while it is still working (waiting to place, or orders waiting for a trigger)."""
        name = b["version"]
        v = self.versions[name]
        sym = v["symbol"]
        if b["legs"] is None:
            place_at = datetime.fromisoformat(b["place_at"])
            if now < place_at:
                return True
            if now > place_at + self.lag:
                self.done[b["rk"]] = "skipped: the stop orders could not be placed in time"
                return False
            rel = Release(datetime.fromisoformat(b["rel_time"]), b["currency"])
            bars = self.broker.bars_m1(sym, int(v["stop_atr_tf"]) * (int(v["stop_atr_n"]) + 2) * 3)
            st, why = breakout_setup(rel, v, bars)
            if st is None:
                self.done[b["rk"]] = "no trade: " + why
                log.info("%s %s: %s", name, b["key"], self.done[b["rk"]])
                return False
            risk_money = self.risk * self.broker.equity()
            b.update(expire_at=st.expire_at.isoformat(), sd=st.stop_dist, why=st.why, risk_money=risk_money,
                     tgt=st.target_dist if math.isfinite(st.target_dist) else None,
                     legs={"1": {"level": st.up, "ticket": None}, "-1": {"level": st.dn, "ticket": None}})
            for d_s, lg in b["legs"].items():
                d = int(d_s)
                lg["lots"], loss1 = self.broker.lots_for(sym, d, lg["level"], lg["level"] - d * st.stop_dist, risk_money)
                if lg["lots"] <= 0:
                    self.done[b["rk"]] = f"skipped: the minimum lot would risk {loss1:.2f} > {risk_money:.2f}"
                    log.warning("%s %s: %s", name, b["key"], self.done[b["rk"]])
                    return False
            log.info("%s: %s", name, st.why)
        legs = b["legs"]
        # 1. a fill?
        stat = {d: self.broker.order_status(lg["ticket"], sym) for d, lg in legs.items() if lg.get("ticket")}
        filled = sorted((s["time"], d) for d, s in stat.items() if s["state"] in ("filled", "closed"))
        if filled:
            self._brk_cancel(b, keep=filled[0][1])
            if len(filled) == 2 and filled[0][0] == filled[1][0]:
                for _, d in filled:                                  # whipsaw inside one minute: flat at once
                    p = self._brk_position(b, int(d), stat[d])
                    if p is not None:
                        self.broker.close(p, "OCO: both filled")
                        self._journal(p)
                self.done[b["rk"]] = "both stop orders filled in the same minute - both closed at once"
                log.warning("%s %s: %s", name, b["key"], self.done[b["rk"]])
                return False
            d = filled[0][1]
            p = self._brk_position(b, int(d), stat[d])
            if len(filled) == 2:                                     # the later fill of the other leg: close it now
                q = self._brk_position(b, int(filled[1][1]), stat[filled[1][1]])
                if q is not None:
                    self.broker.close(q, "OCO: second leg")
                    self._journal(q)
            if p is not None:
                self.positions.append(p)
            self.done[b["rk"]] = f"entered {'BUY' if int(d) > 0 else 'SELL'} at {stat[d]['price']:.2f} " \
                                 f"({stat[d]['time']:%H:%M}): {b['why']}"
            log.info("%s %s: %s", name, b["key"], self.done[b["rk"]])
            return False
        # 2. expired?
        expire_at = datetime.fromisoformat(b["expire_at"])
        if now >= expire_at:
            self._brk_cancel(b)
            self.done[b["rk"]] = f"no breakout within {int(v['brk_window'])} min - orders cancelled"
            log.info("%s %s: %s", name, b["key"], self.done[b["rk"]])
            return False
        # 3. legs without a working order: the market already beyond the level -> enter at market, else place the order
        tk = self.broker.tick(sym)
        for d_s, lg in legs.items():
            if lg.get("ticket"):
                continue
            d = int(d_s)
            if tk is not None and ((d > 0 and tk[1] >= lg["level"]) or (d < 0 and tk[0] <= lg["level"])):
                self._brk_cancel(b, keep=d_s)
                ok = self._brk_market(b, d, now, tk)
                self.done[b["rk"]] = ("entered at market (price already beyond the level): " if ok else
                                      "market entry failed (see log): ") + b["why"]
                log.info("%s %s: %s", name, b["key"], self.done[b["rk"]])
                return False
            sl = lg["level"] - d * b["sd"]
            tp = lg["level"] + d * b["tgt"] if b["tgt"] else 0.0
            lg["ticket"] = self.broker.place_stop(sym, d, lg["level"], sl, tp, lg["lots"], expire_at, f"newsbot {name}")
        return True

    def _brk_position(self, b: dict, d: int, s: dict) -> Position | None:
        """A filled stop order -> Position with the stop / target re-anchored to the real fill."""
        v = self.versions[b["version"]]
        fill, ft = float(s["price"]), s["time"]
        sl = fill - d * b["sd"]
        tp = fill + d * b["tgt"] if b["tgt"] else 0.0
        p = Position(int(s["position"]), b["version"], v["symbol"], d, b["legs"][str(d)]["lots"], fill, sl, tp,
                     ft.isoformat(), breakout_exit_by(v, ft).isoformat(), b["key"],
                     extra={"why": b["why"], "stop_dist": b["sd"], "risk_money": b["risk_money"],
                            "order": b["legs"][str(d)]["ticket"]})
        if "spread" in s:
            p.extra["spread"] = s["spread"]
        if s["state"] == "closed":                                   # filled and already stopped / targeted
            p.closed, p.exit_price, p.exit_reason = True, float(s["exit_price"]), "stop/target at broker"
            p.extra["exit_time"] = str(s["exit_time"])
            self._journal(p)
            return None
        self.broker.modify_sltp(p, sl, tp)
        return p

    def _brk_market(self, b: dict, d: int, now: datetime, tk) -> bool:
        v = self.versions[b["version"]]
        sym = v["symbol"]
        bid, ask, _ = tk
        entry = ask if d > 0 else bid
        sl = entry - d * b["sd"]
        tp = entry + d * b["tgt"] if b["tgt"] else 0.0
        p = Position(0, b["version"], sym, d, b["legs"][str(d)]["lots"], entry, sl, tp, now.isoformat(),
                     breakout_exit_by(v, now).isoformat(), b["key"],
                     extra={"why": b["why"], "stop_dist": b["sd"], "risk_money": b["risk_money"], "stop_entry": True})
        p = self.broker.open(p)
        if p is None:
            return False
        self.positions.append(p)
        return True
