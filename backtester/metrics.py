from __future__ import annotations

import numpy as np
import pandas as pd


def daily_returns(equity: pd.Series) -> pd.Series:
    d = equity.resample("1D").last().dropna()
    d = d[d.index.dayofweek < 5]
    return d.pct_change().fillna(0.0)


def summarize(rets: pd.Series, r_multiples: np.ndarray) -> dict:
    """rets: daily returns of the strategy; r_multiples: per-trade R."""
    if len(rets) < 2:
        return {}
    eq = (1 + rets).cumprod()
    years = max((rets.index[-1] - rets.index[0]).days / 365.25, 1e-9)
    total = eq.iloc[-1] - 1
    cagr = eq.iloc[-1] ** (1 / years) - 1 if eq.iloc[-1] > 0 else -1.0
    dd = (eq / eq.cummax() - 1).min()
    sd = rets.std()
    sharpe = rets.mean() / sd * np.sqrt(260) if sd > 0 else 0.0
    r = np.asarray(r_multiples)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {
        "total_return": total,
        "cagr": cagr,
        "max_dd": dd,
        "mar": cagr / abs(dd) if dd < 0 else np.nan,
        "sharpe": sharpe,
        "trades": int(len(r)),
        "trades_per_year": len(r) / years,
        "win_rate": float((r > 0).mean()) if len(r) else np.nan,
        "profit_factor": wins / losses if losses > 0 else np.nan,
        "avg_r": float(r.mean()) if len(r) else np.nan,
        "years": years,
    }
