"""Agent lab: agents build a gold strategy on Jan-Jun 2026 and check it themselves on Jul-Oct 2026 (fixed before any run).

PROTOCOL
  * Gold M1 bid bars (data/XAUUSD_M1.csv); longs fill at bid + cost, shorts at bid; cost $0.25 (Exness measured), stress
    $0.40. One position at a time. $1,000 start, 10% of equity risked per trade, compounding (the user's choice).
  * BUILD on Jan-Jun 2026 with train_data() (bars 2025-10-01 .. 2026-06-30; data before 2026 is warm-up only).
  * CHECK on Jul 1 - Oct 15 2026 with check_unseen(): it runs the strategy on test_data(), logs the attempt to
    results/agent_lab/checks.jsonl and returns the Jul-Oct scorecard. Each agent may check at most MAX_CHECKS strategies,
    and only strategies that already pass the Jan-Jun rules (passes_train). A failed strategy is dropped, not tuned on
    Jul-Oct. Because agents look at Jul-Oct and retry, Jul-Oct is a validation period, not a clean test.
  * FINAL EXAM: 2025 (Jan-Dec) is never given to the agents. A strategy that passes Jul-Oct is run once on 2025 afterwards.
  * Jan-Jun rules: >= 40 trades; profit factor >= 1.3; Jan-Mar and Apr-Jun each with R > 0 and profit factor >= 1.1;
    profit factor >= 1.15 without its best trade and at $0.40; max drawdown at 10% risk better than -35%.
  * Jul-Oct "works": >= 20 trades; R > 0; profit factor >= 1.3 (>= 1.15 at $0.40); max drawdown at 10% better than -35%.
  * 2025 exam success (stated in advance): R > 0, profit factor >= 1.2, max drawdown at 10% better than -40%.
A strategy is make_trades(cfg, cost, m1) -> DataFrame(entry_time, exit_time, dir, r), built only from the M1 frame given.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TRAIN = ("2026-01-01", "2026-07-01")
TRAIN_Q = {"jan-mar": ("2026-01-01", "2026-04-01"), "apr-jun": ("2026-04-01", "2026-07-01")}
TEST = ("2026-07-01", "2026-10-16")
WARMUP = "2025-10-01"
RISK = 0.10
MAX_CHECKS = 8
LOG = ROOT / "results/agent_lab/checks.jsonl"
_CACHE: dict = {}


def _m1() -> pd.DataFrame:
    if "m1" not in _CACHE:
        from backtester import gold as G
        m1 = G.data(ROOT)[0]
        _CACHE["m1"] = m1[m1.index >= WARMUP]
    return _CACHE["m1"]


def train_data() -> pd.DataFrame:
    """M1 bid bars 2025-10-01 .. 2026-06-30 23:59 - the only data used to build."""
    return _m1()[_m1().index < TRAIN[1]].copy()


def test_data() -> pd.DataFrame:
    """M1 bid bars 2025-10-01 .. 2026-10-15 (for check_unseen only; never 2025 results)."""
    return _m1().copy()


def _pf(r):
    gl = -r[r < 0].sum(); gw = r[r > 0].sum()
    return float(gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)


def metrics(trades: pd.DataFrame, a: str, b: str, risk: float = RISK) -> dict:
    t = trades[(trades.entry_time >= a) & (trades.entry_time < b)].sort_values("entry_time")
    if len(t) > 1 and (t.entry_time.to_numpy()[1:] <= t.exit_time.to_numpy()[:-1]).any():
        raise ValueError("overlapping trades: one position at a time")
    r = t.r.to_numpy(float)
    eq = np.cumprod(1 + risk * r) if len(r) else np.array([1.0])
    rest = np.delete(r, r.argmax()) if len(r) else r
    streak = cur = 0
    for x in r:
        cur = cur + 1 if x < 0 else 0; streak = max(streak, cur)
    mon = t.assign(m=t.exit_time.dt.to_period("M"), g=np.log1p(risk * r)).groupby("m").g.sum()
    return dict(n=len(r), R=float(r.sum()), pf=_pf(r), win=float((r > 0).mean()) if len(r) else 0.0,
                pf_wo_best=_pf(rest), log_growth=float(np.log(eq[-1])), usd=float(1000 * eq[-1]),
                dd=float((eq / np.maximum.accumulate(np.maximum(eq, 1.0)) - 1).min()), max_losing_streak=streak,
                months={str(k): round(float(np.expm1(v)), 4) for k, v in mon.items()})


def evaluate_train(trades: pd.DataFrame) -> dict:
    """Jan-Jun 2026 scorecard (refuses trades after June)."""
    if len(trades) and (trades.entry_time >= TRAIN[1]).any():
        raise ValueError("build only on Jan-Jun 2026")
    out = metrics(trades, *TRAIN)
    for k, (a, b) in TRAIN_Q.items():
        m = metrics(trades, a, b)
        out.update({f"{k}_n": m["n"], f"{k}_R": m["R"], f"{k}_pf": m["pf"]})
    return out


def passes_train(m25: dict, m40: dict) -> dict:
    chk = {"trades>=40": m25["n"] >= 40, "pf>=1.3": m25["pf"] >= 1.3,
           "jan-mar R>0 pf>=1.1": m25["jan-mar_R"] > 0 and m25["jan-mar_pf"] >= 1.1,
           "apr-jun R>0 pf>=1.1": m25["apr-jun_R"] > 0 and m25["apr-jun_pf"] >= 1.1,
           "pf without best>=1.15": m25["pf_wo_best"] >= 1.15, "pf at $0.40>=1.15": m40["pf"] >= 1.15,
           "drawdown at 10% better than -35%": m25["dd"] > -0.35}
    chk["all"] = all(chk.values())
    return chk


def passes_test(m25: dict, m40: dict) -> dict:
    chk = {"trades>=20": m25["n"] >= 20, "R>0": m25["R"] > 0, "pf>=1.3": m25["pf"] >= 1.3,
           "pf at $0.40>=1.15": m40["pf"] >= 1.15, "drawdown at 10% better than -35%": m25["dd"] > -0.35}
    chk["all"] = all(chk.values())
    return chk


def checks_used(agent: str) -> int:
    if not LOG.exists():
        return 0
    return sum(1 for line in LOG.read_text().splitlines() if line and json.loads(line).get("agent") == agent)


def check_unseen(make_trades, cfg: dict, agent: str, label: str, rules: str) -> dict:
    """Run a strategy that passes the Jan-Jun rules once on Jul-Oct 2026, log the attempt, return the result."""
    used = checks_used(agent)
    if used >= MAX_CHECKS:
        raise RuntimeError(f"{agent} has used all {MAX_CHECKS} checks")
    tr = train_data()
    tr25, tr40 = evaluate_train(make_trades(cfg, 0.25, tr)), evaluate_train(make_trades(cfg, 0.40, tr))
    if not passes_train(tr25, tr40)["all"]:
        raise ValueError("only strategies that pass the Jan-Jun rules may be checked")
    full = test_data()
    t25, t40 = make_trades(cfg, 0.25, full), make_trades(cfg, 0.40, full)
    if len(t25) and (t25.entry_time < "2026-01-01").any():
        t25 = t25[t25.entry_time >= "2026-01-01"]; t40 = t40[t40.entry_time >= "2026-01-01"]
    te25, te40 = metrics(t25, *TEST), metrics(t40, *TEST)
    verdict = passes_test(te25, te40)
    rec = dict(time=datetime.now(timezone.utc).isoformat(timespec="seconds"), agent=agent, check=used + 1, label=label,
               rules=rules, cfg=cfg, train=tr25, test=te25, test_040=te40, works=verdict["all"], checks=verdict)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    return rec
