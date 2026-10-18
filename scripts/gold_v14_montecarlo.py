"""Gold Asian breakout v14: what a year could look like. 10,000 simulated years, each built from 12 months drawn at random
(with replacement) from Feb 2023 - Sep 2026, every month replaying v14's real trades of that month in order, charged
Dukascopy's recorded spread. Single engine, one trade at a time, so compounding trade by trade is exact.
Writes results/gold/v14_montecarlo.csv."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
from backtester import gold as G  # noqa: E402
import gold_versions as V  # noqa: E402

N_SIM, MONTHS, SEED = 10_000, 12, 7


def main():
    m1, m15 = G.data(ROOT, "XAUUSD_LONG")
    t = V.trades("v14", m1, m15, cost_mode="data")
    t = t[(t.entry_time >= "2023-02-01") & (t.entry_time < "2026-10-01")]
    months = pd.period_range("2023-02", "2026-09", freq="M")
    by_m = [t[t.entry_time.dt.to_period("M") == m].r.to_numpy() for m in months]
    rng = np.random.default_rng(SEED)
    picks = rng.integers(0, len(months), size=(N_SIM, MONTHS))
    rows = []
    for risk in (0.04, 0.06, 0.08, 0.10):
        final, dd, losing_months = np.empty(N_SIM), np.empty(N_SIM), np.empty(N_SIM)
        for s in range(N_SIM):
            eq, peak, worst, lm = 1.0, 1.0, 0.0, 0
            for k in picks[s]:
                start = eq
                for r in by_m[k]:
                    eq *= 1 + risk * r
                    peak = max(peak, eq); worst = min(worst, eq / peak - 1)
                lm += eq < start
            final[s], dd[s], losing_months[s] = eq, worst, lm
        rows.append({"risk": risk, "p10": np.percentile(final, 10) * 1000, "median": np.median(final) * 1000,
                     "p90": np.percentile(final, 90) * 1000, "p_loss": (final < 1).mean(),
                     "p_dd30": (dd <= -0.30).mean(), "p_dd50": (dd <= -0.50).mean(),
                     "median_dd": np.median(dd), "median_losing_months": np.median(losing_months)})
    out = pd.DataFrame(rows)
    out.to_csv(ROOT / "results/gold/v14_montecarlo.csv", index=False)
    print(f"{len(t)} trades in {len(months)} months; trades per month median {np.median([len(x) for x in by_m]):.0f}, "
          f"months with no trade {sum(len(x) == 0 for x in by_m)}")
    pd.set_option("display.width", 200)
    print(out.round(3).to_string())


if __name__ == "__main__":
    main()
