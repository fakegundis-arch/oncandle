"""Gold Asian breakout v17: pick from results/gold/v17_search.npz using 2026 ONLY (Exness spread $0.25).

Rule (fixed before any v17 result existed; rule 4 made stricter after the 2026 study found the second half harsher):
  1. 2026 drawdown no worse than -35%.
  2. At least 8 of 10 months of 2026 profitable.
  3. At least half of the one-step neighbours have a 2026 drawdown no worse than -40% and >= 8/10 months up.
  4. Block bootstrap (2-week blocks, one-year horizon, 400 simulated years): worst-decile drawdown better than -50% for
     the full 2026 trades AND for each half alone (Jan-May, Jun-Oct).
  5. Highest 2026 total.
Target checked once on 2025 afterwards: drawdown better than -50%.
    python scripts/gold_v17.py            -> 2026 view + bootstrap
    python scripts/gold_v17.py --reveal   -> the pick on 2025 and Q4 2024
    python scripts/gold_v17.py --both     -> Rule B (chosen on 2025 + 2026), see select_both
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import gold_v17_search as SR  # noqa: E402
import gold_v17_sim as S  # noqa: E402

DIMS = {**SR.VAR, **SR.RISK}
HALVES = {"full": ("2026-01-01", "2026-10-15"), "H1": ("2026-01-01", "2026-06-01"), "H2": ("2026-06-01", "2026-10-15")}
MAX_CHECK = 20_000


def load():
    z = np.load(ROOT / "results/gold/v17_search.npz")
    shape = tuple(z["shape"])
    return {k: z[k].reshape(shape) for k in z.files if k != "shape"}, shape


def neighbour_share(p):
    hits = np.zeros(p.shape, np.float32); tot = np.zeros(p.shape, np.float32)
    for ax in range(p.ndim):
        lo = [slice(None)] * p.ndim; hi = [slice(None)] * p.ndim
        lo[ax] = slice(1, None); hi[ax] = slice(None, -1)
        hits[tuple(lo)] += p[tuple(hi)]; tot[tuple(lo)] += 1
        hits[tuple(hi)] += p[tuple(lo)]; tot[tuple(hi)] += 1
    return hits / np.maximum(tot, 1)


def describe(ix):
    return {k: v[i] for (k, v), i in zip(DIMS.items(), ix)}


def boot(t, d):
    w = [d["w1"], d["w2"], d["w3"]]
    return {h: S.bootstrap_fast(t, w, [1, 1, 1], 0.0, d["dst_k"] * d["w2"], d["dl"], a, b) for h, (a, b) in HALVES.items()}


_B: dict = {}


def _boot_job(arg):
    """Strict bootstrap for one engine set: worst-decile drawdown of the candidate mixes on full 2026, H1 and H2
    (or on the periods passed as a third item)."""
    e, mix_idx, *per = arg
    per = per[0] if per else HALVES
    if not _B:
        SR.init(); _B["mix"] = SR.mixes()
    kw = dict(zip(SR.VAR, [v[i] for v, i in zip(SR.VAR.values(), np.unravel_index(e, [len(v) for v in SR.VAR.values()]))]))
    t = SR.trades_for(kw)
    W, SM, CAP, DST, DL = (a[mix_idx] for a in _B["mix"])
    return e, mix_idx, {h: S.boot_p10(S.boot_samples(t, a, b), W, SM, CAP, DST, DL) for h, (a, b) in per.items()}


def select(reveal=False):
    """Rules 1-4 for every candidate (bootstrap vectorised per engine set), then the highest 2026 total."""
    from concurrent.futures import ProcessPoolExecutor
    r, shape = load()
    p = (r["y26_dd"] >= -0.35) & (r["y26_up"] >= 8)
    nb = neighbour_share((r["y26_dd"] >= -0.40) & (r["y26_up"] >= 8))
    c = p & (nb >= 0.5)
    n_e = int(np.prod([len(v) for v in SR.VAR.values()]))
    c2 = c.reshape(n_e, -1)
    print(f"{p.size:,} combinations | {int(p.sum()):,} pass rules 1-2 | {int(c.sum()):,} also rule 3", flush=True)
    jobs = [(e, np.flatnonzero(c2[e])) for e in range(n_e) if c2[e].any()]
    passed = np.zeros(c2.shape, bool)
    worst = {h: np.full(c2.shape, np.nan, np.float32) for h in HALVES}
    with ProcessPoolExecutor(4) as ex:
        for k, (e, mi, res) in enumerate(ex.map(_boot_job, jobs, chunksize=2)):
            ok = np.ones(len(mi), bool)
            for h, v in res.items():
                worst[h][e, mi] = v; ok &= v > -0.50
            passed[e, mi] = ok
            if k % 50 == 0:
                print(f"  bootstrap {k}/{len(jobs)} engine sets, {int(passed.sum()):,} pass rule 4 so far", flush=True)
    passed = passed.reshape(shape)
    print(f"{int(passed.sum()):,} pass rule 4 (bootstrap worst decile better than -50% in full 2026, H1 and H2)")
    np.savez_compressed(ROOT / "results/gold/v17_boot.npz", passed=passed,
                        **{f"boot_{h}": v.reshape(shape) for h, v in worst.items()})
    if not passed.any():
        return r, None
    flat = np.flatnonzero(passed.ravel())
    order = flat[np.argsort(-r["y26_usd"].ravel()[flat], kind="stable")]
    for j in order[:10]:
        ix = np.unravel_index(j, shape)
        print(f"  2026 ${r['y26_usd'][ix]:,.0f} DD {r['y26_dd'][ix]:.0%} up {int(r['y26_up'][ix])}/10 nb {nb[ix]:.2f} boot "
              + "/".join(f"{worst[h].reshape(shape)[ix]:.0%}" for h in HALVES) + " | "
              + ", ".join(f"{k}={v}" for k, v in describe(ix).items()))
    ix = np.unravel_index(order[0], shape)
    print("\nPICK:", describe(ix))
    if reveal:
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${r[f'{k}_usd'][ix]:,.0f} DD {r[f'{k}_dd'][ix]:.0%} months up {int(r[f'{k}_up'][ix])} "
                  f"worst month {r[f'{k}_worst'][ix]:+.0%}")
    return r, ix


def select_top(reveal=False, want=10):
    """Same pick as select(), faster: bootstrap the rule 1-3 candidates in order of 2026 total (best first), in rounds,
    and stop once `want` have passed rule 4. Every candidate not checked earns less than all the passers found, so the
    top `want` passers, and so the pick, are exactly those of the full check."""
    from concurrent.futures import ProcessPoolExecutor
    r, shape = load()
    p = (r["y26_dd"] >= -0.35) & (r["y26_up"] >= 8)
    nb = neighbour_share((r["y26_dd"] >= -0.40) & (r["y26_up"] >= 8))
    c = (p & (nb >= 0.5)).ravel()
    print(f"{p.size:,} combinations | {int(p.sum()):,} pass rules 1-2 | {int(c.sum()):,} also rule 3", flush=True)
    usd = r["y26_usd"].ravel()
    flat = np.flatnonzero(c)
    flat = flat[np.argsort(-usd[flat], kind="stable")]
    n_mix = int(np.prod([len(v) for v in SR.RISK.values()]))
    checked = np.zeros(p.size, bool); passed = np.zeros(p.size, bool)
    worst = {h: np.full(p.size, np.nan, np.float32) for h in HALVES}
    done, size = 0, 5000
    with ProcessPoolExecutor(4) as ex:
        while done < len(flat) and passed.sum() < want:
            part = flat[done:done + size]
            e_of = part // n_mix
            jobs = [(int(e), part[e_of == e] % n_mix) for e in np.unique(e_of)]
            for e, mi, res in ex.map(_boot_job, jobs):
                j = e * n_mix + mi
                ok = np.ones(len(mi), bool)
                for h, v in res.items():
                    worst[h][j] = v; ok &= v > -0.50
                passed[j] = ok; checked[j] = True
            done += len(part)
            print(f"  checked the best {done:,} by 2026 total (down to ${usd[part[-1]]:,.0f}): "
                  f"{int(passed.sum()):,} pass rule 4", flush=True)
            size *= 2
    np.savez_compressed(ROOT / "results/gold/v17_boot.npz", shape=np.array(shape), checked=checked, passed=passed,
                        **{f"boot_{h}": v for h, v in worst.items()})
    if not passed.any():
        print("no candidate passes rule 4")
        return r, None
    hits = flat[passed[flat]]
    for j in hits[:want]:
        ix = np.unravel_index(j, shape)
        print(f"  2026 ${usd[j]:,.0f} DD {r['y26_dd'][ix]:.0%} up {int(r['y26_up'][ix])}/10 nb {nb[ix]:.2f} boot "
              + "/".join(f"{worst[h][j]:.0%}" for h in HALVES) + " | "
              + ", ".join(f"{k}={v}" for k, v in describe(ix).items()))
    ix = np.unravel_index(hits[0], shape)
    print("\nPICK:", describe(ix))
    if reveal:
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${r[f'{k}_usd'][ix]:,.0f} DD {r[f'{k}_dd'][ix]:.0%} months up {int(r[f'{k}_up'][ix])} "
                  f"worst month {r[f'{k}_worst'][ix]:+.0%}")
    return r, ix


YEARS = {"y25": ("2025-01-01", "2026-01-01"), "y26": ("2026-01-01", "2026-10-15")}


def select_both(want=10):
    """Rule B, chosen on 2025 AND 2026 (after the 2026-only pick failed its 2025 test; 2025 is no longer unseen):
      1. drawdown no worse than -45% in 2025 and in 2026;
      2. at least 75% of months up in each (9/12 in 2025, 8/10 in 2026);
      3. at least half of the one-step neighbours with drawdown no worse than -50% in both years and rule 2;
      4. block-bootstrap worst-decile drawdown better than -50% for each year's trades;
      5. highest profit in the weaker of the two years. Q4 2024 is the only period not used."""
    from concurrent.futures import ProcessPoolExecutor
    r, shape = load()
    ok2 = (r["y25_up"] >= 9) & (r["y26_up"] >= 8)
    p = (r["y25_dd"] >= -0.45) & (r["y26_dd"] >= -0.45) & ok2
    nb = neighbour_share((r["y25_dd"] >= -0.50) & (r["y26_dd"] >= -0.50) & ok2)
    c = (p & (nb >= 0.5)).ravel()
    print(f"{p.size:,} combinations | {int(p.sum()):,} pass rules 1-2 | {int(c.sum()):,} also rule 3", flush=True)
    score = np.minimum(r["y25_usd"], r["y26_usd"]).ravel()
    flat = np.flatnonzero(c)
    flat = flat[np.argsort(-score[flat], kind="stable")]
    n_mix = int(np.prod([len(v) for v in SR.RISK.values()]))
    passed = np.zeros(p.size, bool)
    worst = {h: np.full(p.size, np.nan, np.float32) for h in YEARS}
    done, size = 0, 2000
    with ProcessPoolExecutor(4) as ex:
        while done < len(flat) and passed.sum() < want:
            part = flat[done:done + size]
            e_of = part // n_mix
            jobs = [(int(e), part[e_of == e] % n_mix, YEARS) for e in np.unique(e_of)]
            for e, mi, res in ex.map(_boot_job, jobs):
                j = e * n_mix + mi
                ok = np.ones(len(mi), bool)
                for h, v in res.items():
                    worst[h][j] = v; ok &= v > -0.50
                passed[j] = ok
            done += len(part)
            print(f"  checked the best {done:,} (weaker year down to ${score[part[-1]]:,.0f}): "
                  f"{int(passed.sum()):,} pass rule 4", flush=True)
            size *= 2
    hits = flat[passed[flat]]
    for j in hits[:want]:
        ix = np.unravel_index(j, shape)
        print(f"  2025 ${r['y25_usd'][ix]:,.0f} ({r['y25_dd'][ix]:.0%}) 2026 ${r['y26_usd'][ix]:,.0f} ({r['y26_dd'][ix]:.0%})"
              f" nb {nb[ix]:.2f} boot " + "/".join(f"{worst[h][j]:.0%}" for h in YEARS) + " | "
              + ", ".join(f"{k}={v}" for k, v in describe(ix).items()))
    if not len(hits):
        print("no candidate passes rule 4")
        return r, None
    ix = np.unravel_index(hits[0], shape)
    print("\nPICK B:", describe(ix))
    for k in ("y26", "y25", "q4"):
        print(f"  {k}: ${r[f'{k}_usd'][ix]:,.0f} DD {r[f'{k}_dd'][ix]:.0%} months up {int(r[f'{k}_up'][ix])} "
              f"worst month {r[f'{k}_worst'][ix]:+.0%}")
    return r, ix


def main(reveal=False):
    r, shape = load()
    p = (r["y26_dd"] >= -0.35) & (r["y26_up"] >= 8)
    nb = neighbour_share((r["y26_dd"] >= -0.40) & (r["y26_up"] >= 8))
    c = p & (nb >= 0.5)
    print(f"{p.size:,} combinations | {int(p.sum()):,} pass rules 1-2 | {int(c.sum()):,} also rule 3")
    flat = np.flatnonzero(c.ravel())
    flat = flat[np.argsort(-r["y26_usd"].ravel()[flat], kind="stable")][:MAX_CHECK]
    SR.init()
    rows, pick = [], None
    for n_checked, j in enumerate(flat, 1):
        ix = np.unravel_index(j, shape); d = describe(ix)
        t = SR.trades_for(d)
        b = boot(t, d)
        row = dict(y26=float(r["y26_usd"][ix]), dd26=float(r["y26_dd"][ix]), nb=float(nb[ix]),
                   **{f"boot_{h}": v[0] for h, v in b.items()}, boot_med=b["full"][1], **d)
        rows.append(row)
        if all(v[0] > -0.50 for v in b.values()):
            pick = (ix, row)
            break
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 340); pd.set_option("display.max_columns", 40)
    print(f"checked {n_checked:,} candidates (best 2026 first) with the bootstrap; last 8:")
    print(df.tail(8).round(3).to_string())
    if pick is None:
        print("no candidate passes rule 4")
        return r, None
    ix, row = pick
    print("\nPICK:", {k: row[k] for k in DIMS})
    print(f"  2026 ${row['y26']:,.0f} DD {row['dd26']:.0%} | bootstrap worst decile full {row['boot_full']:.0%}, "
          f"H1 {row['boot_H1']:.0%}, H2 {row['boot_H2']:.0%}, median {row['boot_med']:.0%}")
    if reveal:
        for k in ("y26", "y25", "q4"):
            print(f"  {k}: ${r[f'{k}_usd'][ix]:,.0f} DD {r[f'{k}_dd'][ix]:.0%} months up {int(r[f'{k}_up'][ix])} "
                  f"worst month {r[f'{k}_worst'][ix]:+.0%}")
    return r, pick


if __name__ == "__main__":
    if "--both" in sys.argv:
        select_both()
    else:
        select_top("--reveal" in sys.argv)
