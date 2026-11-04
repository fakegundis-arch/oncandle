"""MetaTrader 5 broker (official `MetaTrader5` Python package, Windows only) with a DRY-RUN mode.

* symbols are mapped from the research names (XAUUSD, NAS100, AUDUSD, NZDUSD, USDJPY) to the broker's names
  (Exness: XAUUSDm, USTECm, AUDUSDm, NZDUSDm, USDJPYm) through the config
* bar times from MT5 are server time; `server_utc_offset_hours` converts them to UTC (Exness servers run on UTC+0)
* position size: the loss at the stop for 1 lot comes from mt5.order_calc_profit (handles contract size, tick value
  and currency conversion); lots = risk_fraction x equity / loss_per_lot, rounded DOWN to the volume step; if that
  is below the minimum lot the trade is skipped (it would risk more than asked)
* dry_run=True: connects to MT5 for prices / bars / account size, but never calls order_send; orders, stop / target
  hits (checked on M1 bars) and time exits are logged and kept in a virtual position book
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
