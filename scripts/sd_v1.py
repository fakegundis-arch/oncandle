"""Supply & demand v1 (gold): pick from results/sd/v1_search.npz using 2026 ONLY. 2025 and 15 Nov - 31 Dec 2024 sit
in results/sd/v1_sealed.npz, opened only by --reveal, once, after the pick is committed.

PROTOCOL (written and committed before the search ran):
  1. 2026 (Jan 1 - Oct 15): at least 60 trades, profit factor >= 1.3, and a positive total R in Jan-May AND in Jun-Oct.
  2. At least 60% of the one-step neighbours have a 2026 profit factor >= 1.15 with >= 40 trades.
  3. Score = median, over the setting and its one-step neighbours, of 2026 total R / max(2026 R-drawdown, 3R).
     The highest score among settings passing 1 and 2 is the pick.
  "Works on 2026" = at least one setting passes 1 and 2. If none does, v1 does not work and 2025 stays sealed.
  4. Risk per trade: the largest of 0.5, 1, 1.5, 2, 3, 4, 5% of equity at which a block bootstrap of the pick's 2026
     trades (2-week blocks, 400 one-year paths, seed 11) keeps the worst-decile max drawdown better than -25%.
  5. --reveal prints 2025 and late 2024 once. Success on 2025 (stated in advance): total R > 0 and profit factor >= 1.1.
    python scripts/sd_v1.py            -> the pick (2026 only)
    python scripts/sd_v1.py --reveal   -> its 2025 and late-2024 results
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import sd_v1_search as SR  # noqa: E402

PICK = SR.OUT / "v1_pick.json"
RISKS = [0.005, 0.01, 0.015, 0.02, 0.03, 0.04, 0.05]


def load(path=SR.OUT / "v1_search.npz"):
    z = np.load(path)
    shape = tuple(z["shape"])
    return {k: z[k].reshape(shape) for k in z.files if k != "shape"}, shape


def shifted(p):
    out = []
    for ax in range(p.ndim):
        for src_sl, dst_sl in ((slice(1, None), slice(None, -1)), (slice(None, -1), slice(1, None))):
            a = np.full(p.shape, np.nan, np.float32)
            src = [slice(None)] * p.ndim; dst = [slice(None)] * p.ndim
            src[ax] = src_sl; dst[ax] = dst_sl
            a[tuple(dst)] = p[tuple(src)]
            out.append(a)
    return out


def describe(ix):
    return {k: v[i] for (k, v), i in zip(SR.DIMS.items(), ix)}


def book(t, a, b, f):
    """$1,000 compounding at risk f on trades entered in [a, b): final, max drawdown (closed trades), months."""
    x = t[(t.entry_time >= a) & (t.entry_time < b)].sort_values("exit_time")
    eq = peak = 1000.0; dd = 0.0; mon = {}
    for r, xt in zip(x.r, x.exit_time):
        eq *= 1 + f * r; peak = max(peak, eq); dd = min(dd, eq / peak - 1); mon[xt.to_period("M")] = eq
    return eq, dd, mon


def boot_p10(t, a, b, f, n_sim=400, block_days=14, horizon_days=365, seed=11):
    x = t[(t.entry_time >= a) & (t.entry_time < b)].sort_values("entry_time")
    t0 = pd.Timestamp(a)
    blk = ((x.entry_time - t0).dt.days // block_days).to_numpy()
    nb = (pd.Timestamp(b) - t0).days // block_days
    groups = [x.r.to_numpy()[blk == k] for k in range(nb)]
    rng = np.random.default_rng(seed)
    dds = []
    for _ in range(n_sim):
        seq = np.concatenate([groups[k] for k in rng.integers(0, nb, horizon_days // block_days)])
        eq = np.cumprod(1 + f * seq); pk = np.maximum.accumulate(np.maximum(eq, 1.0))
        dds.append(min(0.0, (eq / pk - 1).min()) if len(seq) else 0.0)
    return float(np.percentile(dds, 10))


def run():
    r, shape = load()
    c1 = (r["y26_n"] >= 60) & (r["y26_pf"] >= 1.3) & (r["h1_R"] > 0) & (r["h2_R"] > 0)
    ok_nb = ((r["y26_pf"] >= 1.15) & (r["y26_n"] >= 40)).astype(np.float32)
    nb = shifted(ok_nb)
    share = np.nansum(nb, axis=0) / np.maximum(np.sum([~np.isnan(a) for a in nb], axis=0), 1)
    cell = (r["y26_R"] / np.maximum(-r["y26_dd"], 3.0)).astype(np.float32)
    score = np.nanmedian(np.stack([cell] + shifted(cell)), axis=0)
    passing = c1 & (share >= 0.6)
    print(f"{int(np.prod(shape)):,} combinations | rule 1: {int(c1.sum()):,} | rules 1+2: {int(passing.sum()):,}")
    if not passing.any():
        print("No setting passes: supply & demand v1 does not work on 2026; 2025 stays sealed.")
        return None
    flat = np.flatnonzero(passing.ravel())
    flat = flat[np.argsort(-score.ravel()[flat], kind="stable")]
    for j in flat[:10]:
        ix = np.unravel_index(j, shape)
        print(f"  score {score[ix]:.2f} | 2026 {int(r['y26_n'][ix])} trades {r['y26_R'][ix]:+.1f}R PF {r['y26_pf'][ix]:.2f} "
              f"DD {r['y26_dd'][ix]:.1f}R | Jan-May {r['h1_R'][ix]:+.1f}R Jun-Oct {r['h2_R'][ix]:+.1f}R | nb {share[ix]:.2f} | "
              + ", ".join(f"{k}={v}" for k, v in describe(ix).items()))
    ix = np.unravel_index(flat[0], shape)
    cfg = describe(ix)
    t = SR.trades_for(cfg)
    a, b = SR.SEL["y26"]
    p10 = {f: boot_p10(t, a, "2026-10-15", f) for f in RISKS}
    ok = [f for f in RISKS if p10[f] > -0.25]
    risk = max(ok) if ok else RISKS[0]
    eq, dd, mon = book(t, a, b, risk)
    print("\nbootstrap worst-decile drawdown by risk:", ", ".join(f"{f:.1%}: {v:.0%}" for f, v in p10.items()))
    print(f"PICK: {cfg} | risk {risk:.1%}\n  2026: {int(r['y26_n'][ix])} trades, {r['y26_R'][ix]:+.1f}R, PF {r['y26_pf'][ix]:.2f}, "
          f"$1,000 -> ${eq:,.0f}, max drawdown {dd:.1%}")
    PICK.write_text(json.dumps(dict(setting={k: (v if isinstance(v, str) else float(v)) for k, v in cfg.items()},
                                    index=[int(i) for i in ix], risk=risk, boot_p10={str(k): v for k, v in p10.items()},
                                    y26=dict(n=int(r["y26_n"][ix]), R=float(r["y26_R"][ix]), pf=float(r["y26_pf"][ix]),
                                             dd_R=float(r["y26_dd"][ix]), usd=eq, dd=dd)), indent=1))
    return cfg


def reveal():
    pick = json.loads(PICK.read_text())
    cfg = {k: (int(v) if k in ("tf", "nbase", "age") else v) for k, v in pick["setting"].items()}
    z, shape = load(SR.OUT / "v1_sealed.npz")
    ix = tuple(pick["index"])
    t = SR.trades_for(cfg)
    print("PICK:", cfg, f"| risk {pick['risk']:.1%}")
    print(f"  2026 (chosen on): {pick['y26']['n']} trades, {pick['y26']['R']:+.1f}R, PF {pick['y26']['pf']:.2f}, "
          f"${pick['y26']['usd']:,.0f} ({pick['y26']['dd']:.1%})")
    for k, lbl in (("y25", "2025 (unseen)"), ("late24", "15 Nov - 31 Dec 2024 (unseen)")):
        a, b = SR.SEALED[k]
        eq, dd, mon = book(t, a, b, pick["risk"])
        print(f"  {lbl}: {int(z[f'{k}_n'][ix])} trades, {z[f'{k}_R'][ix]:+.1f}R, PF {z[f'{k}_pf'][ix]:.2f}, "
              f"R-drawdown {z[f'{k}_dd'][ix]:.1f}R | $1,000 -> ${eq:,.0f}, max drawdown {dd:.1%}")


if __name__ == "__main__":
    reveal() if "--reveal" in sys.argv else run()
