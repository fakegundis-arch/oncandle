"""MetaTrader 5 broker (official `MetaTrader5` Python package, Windows only) with a DRY-RUN mode.

* symbols are mapped from the research names (XAUUSD, NAS100, AUDUSD, NZDUSD, USDJPY) to the broker's names
  (Exness: XAUUSDm, USTECm, AUDUSDm, NZDUSDm, USDJPYm) through the config
* bar times from MT5 are server time; `server_utc_offset_hours` converts them to UTC (Exness servers run on UTC+0)
* position size: the loss at the stop for 1 lot comes from mt5.order_calc_profit (handles contract size, tick value
  and currency conversion); lots = risk_fraction x equity / loss_per_lot, rounded DOWN to the volume step; if that
  is below the minimum lot the trade is skipped (it would risk more than asked)
* dry_run=True: connects to MT5 for prices / bars / account size, but never calls order_send; orders, stop / target
  hits (checked on M1 bars) and time exits are logged and kept in a virtual position book
* pending stop orders (v3 breakout): place_stop / cancel_order / order_status / modify_sltp.  Live they are real MT5
  BUY_STOP / SELL_STOP orders (a buy stop triggers when the ask reaches its price, a sell stop when the bid does) with
  an expiration (GTC if the symbol refuses one - the bot cancels them itself); dry-run keeps them in a virtual order
  book and triggers them on M1 bars.
"""
from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

import pandas as pd

log = logging.getLogger("newsbot.broker")


@dataclass
class Position:
    ticket: int
    version: str
    symbol: str                 # research name
    direction: int
    lots: float
    entry: float
    sl: float
    tp: float                   # 0 = none
    opened: str                 # UTC iso
    exit_by: str                # UTC iso
    release: str
    closed: bool = False
    exit_price: float = math.nan
    exit_reason: str = ""
    extra: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MT5Broker:
    def __init__(self, mt5cfg: dict, symbol_map: dict, dry_run: bool = True):
        self.cfg, self.map, self.dry = mt5cfg, symbol_map, dry_run
        self.off = timedelta(hours=float(mt5cfg.get("server_utc_offset_hours", 0)))
        self.mt5 = None
        self._paper_ticket = 900000
        self._paper_orders: dict[int, dict] = {}

    # ------------------------------------------------------------------ connection
    def connect(self) -> None:
        import MetaTrader5 as mt5                     # Windows-only package: pip install MetaTrader5
        kw = {k: self.cfg[k] for k in ("path", "login", "password", "server") if self.cfg.get(k)}
        if "login" in kw:
            kw["login"] = int(kw["login"])
        if not mt5.initialize(**kw):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        self.mt5 = mt5
        for s in self.map.values():
            if not mt5.symbol_select(s, True):
                log.warning("symbol %s not available: %s", s, mt5.last_error())
        a = mt5.account_info()
        log.info("MT5 connected: account %s %s, equity %.2f %s, %s", a.login, a.server, a.equity, a.currency,
                 "DRY-RUN (no orders are sent)" if self.dry else "LIVE TRADING")

    def shutdown(self) -> None:
        if self.mt5:
            self.mt5.shutdown()

    def name(self, sym: str) -> str:
        return self.map.get(sym, sym)

    # ------------------------------------------------------------------ data
    def equity(self) -> float:
        return float(self.mt5.account_info().equity)

    def bars_m1(self, sym: str, count: int = 3000) -> pd.DataFrame:
        r = self.mt5.copy_rates_from_pos(self.name(sym), self.mt5.TIMEFRAME_M1, 0, count)
        if r is None or len(r) == 0:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        df = pd.DataFrame(r)
        df.index = pd.to_datetime(df["time"], unit="s") - self.off
        return df[["open", "high", "low", "close"]].astype(float)

    def tick(self, sym: str):
        t = self.mt5.symbol_info_tick(self.name(sym))
        if t is None:
            return None
        return float(t.bid), float(t.ask), datetime.fromtimestamp(t.time, tz=timezone.utc).replace(tzinfo=None) - self.off

    def lots_for(self, sym: str, direction: int, entry: float, sl: float, risk_money: float) -> tuple[float, float]:
        mt5, s = self.mt5, self.name(sym)
        info = mt5.symbol_info(s)
        otype = mt5.ORDER_TYPE_BUY if direction > 0 else mt5.ORDER_TYPE_SELL
        loss1 = mt5.order_calc_profit(otype, s, 1.0, entry, sl)
        if loss1 is None or loss1 >= 0:
            raise RuntimeError(f"order_calc_profit failed for {s}: {mt5.last_error()}")
        loss1 = -loss1
        step = info.volume_step
        lots = math.floor(risk_money / loss1 / step + 1e-9) * step
        lots = min(lots, info.volume_max)
        if lots < info.volume_min:
            return 0.0, loss1
        return round(lots, 8), loss1

    def _filling(self, s: str):
        mt5 = self.mt5
        mode = mt5.symbol_info(s).filling_mode
        if mode & 1:
            return mt5.ORDER_FILLING_FOK
        if mode & 2:
            return mt5.ORDER_FILLING_IOC
        return mt5.ORDER_FILLING_RETURN

    # ------------------------------------------------------------------ orders
    def open(self, pos: Position) -> Position | None:
        """Market order with stop (and target if pos.tp). pos.entry / sl / tp are the intended levels; the real fill
        price replaces pos.entry and the stop / target are re-anchored to it so the risk distance is unchanged."""
        if self.dry:
            self._paper_ticket += 1
            pos.ticket = self._paper_ticket
            log.info("[DRY-RUN] OPEN %s %s %.2f lots @ %.5f sl %.5f tp %s (%s)", "BUY" if pos.direction > 0 else "SELL",
                     self.name(pos.symbol), pos.lots, pos.entry, pos.sl, pos.tp or "-", pos.release)
            return pos
        mt5, s = self.mt5, self.name(pos.symbol)
        tk = mt5.symbol_info_tick(s)
        price = tk.ask if pos.direction > 0 else tk.bid
        shift = price - pos.entry
        dg = mt5.symbol_info(s).digits
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": s, "volume": pos.lots,
               "type": mt5.ORDER_TYPE_BUY if pos.direction > 0 else mt5.ORDER_TYPE_SELL, "price": price,
               "sl": round(pos.sl + shift, dg), "tp": round(pos.tp + shift, dg) if pos.tp else 0.0,
               "deviation": int(self.cfg.get("deviation_points", 50)), "magic": int(self.cfg.get("magic", 260707)),
               "comment": f"newsbot {pos.version}"[:31], "type_time": mt5.ORDER_TIME_GTC,
               "type_filling": self._filling(s)}
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            log.error("order_send failed: %s %s", getattr(res, "retcode", None), getattr(res, "comment", mt5.last_error()))
            return None
        pos.ticket = int(res.order)
        fill = float(res.price) if res.price else price
        d = fill - pos.entry
        pos.entry, pos.sl, pos.tp = fill, pos.sl + d, (pos.tp + d) if pos.tp else 0.0
        log.info("OPEN %s %s %.2f lots @ %.5f sl %.5f tp %s ticket %s", "BUY" if pos.direction > 0 else "SELL", s,
                 pos.lots, fill, pos.sl, pos.tp or "-", pos.ticket)
        return pos

    def is_open(self, pos: Position) -> bool:
        """Live: the position still exists at the broker. Dry-run: check the virtual stop / target on M1 bars."""
        if not self.dry:
            return bool(self.mt5.positions_get(ticket=pos.ticket))
        b = self.bars_m1(pos.symbol, 600)
        b = b[b.index >= pd.Timestamp(pos.opened).floor("min")]
        spread = self._spread(pos.symbol)
        for t, r in b.iterrows():
            lo, hi = (r.low, r.high) if pos.direction > 0 else (r.low + spread, r.high + spread)
            if (pos.direction > 0 and lo <= pos.sl) or (pos.direction < 0 and hi >= pos.sl):
                self._paper_close(pos, pos.sl, "stop", t)
                return False
            if pos.tp and ((pos.direction > 0 and hi >= pos.tp) or (pos.direction < 0 and lo <= pos.tp)):
                self._paper_close(pos, pos.tp, "target", t)
                return False
        return True

    def _spread(self, sym):
        tk = self.tick(sym)
        return (tk[1] - tk[0]) if tk else 0.0

    def _paper_close(self, pos, price, why, t):
        pos.closed, pos.exit_price, pos.exit_reason = True, float(price), why
        r = pos.direction * (pos.exit_price - pos.entry) / abs(pos.entry - pos.sl) if pos.sl != pos.entry else 0.0
        log.info("[DRY-RUN] %s %s closed at %.5f (%s, %s) R = %+.2f", pos.version, self.name(pos.symbol), price, why, t, r)

    def close(self, pos: Position, why: str = "time") -> bool:
        if self.dry:
            tk = self.tick(pos.symbol)
            px = (tk[0] if pos.direction > 0 else tk[1]) if tk else pos.entry
            self._paper_close(pos, px, why, utcnow())
            return True
        mt5 = self.mt5
        ps = mt5.positions_get(ticket=pos.ticket)
        if not ps:
            return True
        p = ps[0]
        s = p.symbol
        tk = mt5.symbol_info_tick(s)
        buy = p.type == mt5.POSITION_TYPE_SELL
        req = {"action": mt5.TRADE_ACTION_DEAL, "symbol": s, "volume": p.volume, "position": p.ticket,
               "type": mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL, "price": tk.ask if buy else tk.bid,
               "deviation": int(self.cfg.get("deviation_points", 50)), "magic": int(self.cfg.get("magic", 260707)),
               "comment": f"newsbot {why}"[:31], "type_time": mt5.ORDER_TIME_GTC, "type_filling": self._filling(s)}
        res = mt5.order_send(req)
        ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
        if ok:
            pos.closed, pos.exit_price, pos.exit_reason = True, float(res.price), why
            log.info("CLOSE %s ticket %s at %.5f (%s)", s, p.ticket, res.price, why)
        else:
            log.error("close failed for ticket %s: %s", p.ticket, getattr(res, "comment", mt5.last_error()))
        return ok

    # ------------------------------------------------------------------ pending stop orders (v3 breakout)
    def place_stop(self, sym: str, direction: int, price: float, sl: float, tp: float, lots: float,
                   expires: datetime, comment: str) -> int | None:
        """Buy stop (direction +1) / sell stop (-1) at `price` with its stop / target (tp 0 = none), cancelled by the
        broker at `expires` (UTC) where the symbol allows it.  -> order ticket, or None if refused."""
        if self.dry:
            self._paper_ticket += 1
            self._paper_orders[self._paper_ticket] = dict(sym=sym, d=direction, price=price, sl=sl, tp=tp, lots=lots,
                                                          placed=utcnow().replace(second=0, microsecond=0),
                                                          expires=expires)
            log.info("[DRY-RUN] PLACE %s %s %.2f lots @ %.5f sl %.5f tp %s until %s (%s)",
                     "BUY STOP" if direction > 0 else "SELL STOP", self.name(sym), lots, price, sl, tp or "-",
                     f"{expires:%H:%M}", comment)
            return self._paper_ticket
        mt5, s = self.mt5, self.name(sym)
        dg = mt5.symbol_info(s).digits
        base = {"action": mt5.TRADE_ACTION_PENDING, "symbol": s, "volume": lots,
                "type": mt5.ORDER_TYPE_BUY_STOP if direction > 0 else mt5.ORDER_TYPE_SELL_STOP,
                "price": round(price, dg), "sl": round(sl, dg), "tp": round(tp, dg) if tp else 0.0,
                "deviation": int(self.cfg.get("deviation_points", 50)), "magic": int(self.cfg.get("magic", 260707)),
                "comment": comment[:31]}
        exp = int((expires + self.off).replace(tzinfo=timezone.utc).timestamp())       # server time, seconds
        tries = [{"type_time": mt5.ORDER_TIME_SPECIFIED, "expiration": exp, "type_filling": self._filling(s)},
                 {"type_time": mt5.ORDER_TIME_GTC, "type_filling": self._filling(s)},
                 {"type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_RETURN}]
        res = None
        for t in tries:                              # refused expiration / filling mode -> the next variant
            res = mt5.order_send({**base, **t})
            if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
                log.info("PLACE %s %s %.2f lots @ %.5f sl %.5f tp %s order %s", "BUY STOP" if direction > 0 else
                         "SELL STOP", s, lots, price, sl, tp or "-", res.order)
                return int(res.order)
            if res is None or res.retcode not in (getattr(mt5, "TRADE_RETCODE_INVALID_EXPIRATION", 10022),
                                                  getattr(mt5, "TRADE_RETCODE_INVALID_FILL", 10030)):
                break
        log.error("pending order refused: %s %s", getattr(res, "retcode", None), getattr(res, "comment", mt5.last_error()))
        return None

    def cancel_order(self, ticket: int) -> bool:
        if self.dry:
            if self._paper_orders.pop(ticket, None) is not None:
                log.info("[DRY-RUN] CANCEL order %s", ticket)
            return True
        mt5 = self.mt5
        if not mt5.orders_get(ticket=ticket):
            return True                                  # already filled / expired / cancelled
        res = mt5.order_send({"action": mt5.TRADE_ACTION_REMOVE, "order": ticket})
        ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
        if not ok:
            log.error("cancel failed for order %s: %s", ticket, getattr(res, "comment", mt5.last_error()))
        return ok

    def _srv(self, ts) -> datetime:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).replace(tzinfo=None) - self.off

    def order_status(self, ticket: int, sym: str) -> dict:
        """{"state": "pending"} | {"state": "filled", "position", "price", "time"} | {"state": "closed", "position",
        "price", "time", "exit_price", "exit_time"} (filled and already closed) | {"state": "gone"} (expired /
        cancelled without a fill)."""
        if self.dry:
            o = self._paper_orders.get(ticket)
            if o is None:
                return {"state": "gone"}
            b = self.bars_m1(sym, 600)
            b = b[(b.index >= pd.Timestamp(o["placed"])) & (b.index < pd.Timestamp(o["expires"]))]
            spread = self._spread(sym)
            for t, r in b.iterrows():
                if o["d"] > 0 and r.high + spread >= o["price"]:
                    px = max(o["price"], r.open + spread)
                elif o["d"] < 0 and r.low <= o["price"]:
                    px = min(o["price"], r.open)
                else:
                    continue
                del self._paper_orders[ticket]
                self._paper_ticket += 1
                log.info("[DRY-RUN] order %s filled at %.5f (%s)", ticket, px, t)
                return {"state": "filled", "position": self._paper_ticket, "price": float(px), "time": t.to_pydatetime()}
            return {"state": "pending"}
        mt5, s = self.mt5, self.name(sym)
        if mt5.orders_get(ticket=ticket):
            return {"state": "pending"}
        for p in mt5.positions_get(symbol=s) or ():
            if int(p.identifier) == int(ticket):       # a position's identifier is the ticket of the order that opened it
                return {"state": "filled", "position": int(p.ticket), "price": float(p.price_open), "time": self._srv(p.time)}
        deals = mt5.history_deals_get(position=ticket) or ()
        ins = [d for d in deals if d.entry == mt5.DEAL_ENTRY_IN]
        outs = [d for d in deals if d.entry == mt5.DEAL_ENTRY_OUT]
        if ins and outs:
            return {"state": "closed", "position": int(ticket), "price": float(ins[0].price), "time": self._srv(ins[0].time),
                    "exit_price": float(outs[-1].price), "exit_time": self._srv(outs[-1].time)}
        return {"state": "gone"}

    def modify_sltp(self, pos: Position, sl: float, tp: float) -> bool:
        """Re-anchor the stop / target of an open position (to its real fill)."""
        pos.sl, pos.tp = sl, tp
        if self.dry:
            return True
        mt5, s = self.mt5, self.name(pos.symbol)
        dg = mt5.symbol_info(s).digits
        res = mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "symbol": s, "position": pos.ticket,
                              "sl": round(sl, dg), "tp": round(tp, dg) if tp else 0.0})
        ok = res is not None and res.retcode == mt5.TRADE_RETCODE_DONE
        if not ok:
            log.error("stop / target change failed for %s: %s (the order's own stop / target stay)", pos.ticket,
                      getattr(res, "comment", mt5.last_error()))
        return ok
