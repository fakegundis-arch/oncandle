"""Gold Asian breakout v17, second stage (Rule B, chosen on 2025 AND 2026): the v17 engines (scripts/gold_v17_search.py)
with a wider risk grid, after the 2026-only pick failed its 2025 test (-56% to -59%) and Rule B's first pick sat on the
edge of the old grid (v5 sleeve 3%, the most it allowed).

Risk grid: v5 sleeve 0-10% with full- or half-size sells (v5's own setting), Asia 0-8%, New York 0-6%, daily stop off /
-6% / -10% of the day's starting balance, daily loss limit off / 2. Rule B (unchanged, see gold_v17.select_both):
  1. drawdown no worse than -45% in 2025 and in 2026;
  2. at least 75% of months up in each (9/12 in 2025, 8/10 in 2026);
  3. at least half of the one-step neighbours with drawdown no worse than -50% in both years and rule 2;
  4. block-bootstrap worst-decile drawdown better than -50% for each year's trades;
  5. highest profit in the weaker of the two years. Q4 2024 is the only period not used.
    python scripts/gold_v17b.py search   -> results/gold/v17b_search.npz
    python scripts/gold_v17b.py          -> Rule B pick
"""
import itertools
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import gold_v17_search as SR  # noqa: E402
import gold_v17_sim as S  # noqa: E402
from gold_v17 import YEARS, neighbour_share  # noqa: E402

RISK = dict(w1=[0.0, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.10], s1=[1.0, 0.5],
            w2=[0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08], w3=[0.0, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06],
            dstop=[0.0, 0.06, 0.10], dl=[0, 2])
DIMS = {**SR.VAR, **RISK}
OUT = ROOT / "results/gold/v17b_search.npz"


def mixes():
    rows = list(itertools.product(*RISK.values()))
    W = np.array([[r[0], r[2], r[3]] for r in rows], float)
    SM = np.ones_like(W); SM[:, 0] = [r[1] for r in rows]
    return W, SM, np.zeros(len(rows)), np.array([r[4] for r in rows], float), np.array([r[5] for r in rows], np.int64)


_M: dict = {}


def _init():
    SR.init(); _M["mix"] = mixes()


def job(v):
    if not _M:
        _init()
    t = SR.trades_for(dict(zip(SR.VAR, v)))
    return {k: S.run(S.prepare(t, a, b), *_M["mix"]) for k, (a, b) in SR.PER.items()}


def search():
    jobs = list(itertools.product(*SR.VAR.values()))
    n_mix = len(mixes()[0])
    res = {f"{k}_{m}": np.empty((len(jobs), n_mix), np.float32) for k in SR.PER for m in ("usd", "dd", "up", "worst")}
    print(len(jobs), "engine sets x", n_mix, "risk mixes =", f"{len(jobs) * n_mix:,}", "combinations", flush=True)
    with ProcessPoolExecutor(4, initializer=_init) as ex:
        for i, out in enumerate(ex.map(job, jobs, chunksize=4)):
            for k, (fin, dd, up, worst) in out.items():
                res[f"{k}_usd"][i], res[f"{k}_dd"][i], res[f"{k}_up"][i], res[f"{k}_worst"][i] = fin * 1000, dd, up, worst
            if i % 100 == 0:
                print(i, "/", len(jobs), flush=True)
    shape = [len(x) for x in SR.VAR.values()] + [len(x) for x in RISK.values()]
    np.savez_compressed(OUT, shape=np.array(shape), **res)


def load():
    z = np.load(OUT)
    shape = tuple(z["shape"])
    return {k: z[k].reshape(shape) for k in z.files if k != "shape"}, shape


def describe(ix):
    return {k: v[i] for (k, v), i in zip(DIMS.items(), ix)}


def _boot_job(arg):
    e, mix_idx = arg
    if not _M:
        _init()
    kw = dict(zip(SR.VAR, [v[i] for v, i in zip(SR.VAR.values(), np.unravel_index(e, [len(v) for v in SR.VAR.values()]))]))
    t = SR.trades_for(kw)
    W, SM, CAP, DST, DL = (a[mix_idx] for a in _M["mix"])
    return e, mix_idx, {h: S.boot_p10(S.boot_samples(t, a, b), W, SM, CAP, DST, DL) for h, (a, b) in YEARS.items()}


def select(want=10):
    r, shape = load()
    ok2 = (r["y25_up"] >= 9) & (r["y26_up"] >= 8)
    p = (r["y25_dd"] >= -0.45) & (r["y26_dd"] >= -0.45) & ok2
    nb = neighbour_share((r["y25_dd"] >= -0.50) & (r["y26_dd"] >= -0.50) & ok2)
    c = (p & (nb >= 0.5)).ravel()
    print(f"{p.size:,} combinations | {int(p.sum()):,} pass rules 1-2 | {int(c.sum()):,} also rule 3", flush=True)
    score = np.minimum(r["y25_usd"], r["y26_usd"]).ravel()
    flat = np.flatnonzero(c)
    flat = flat[np.argsort(-score[flat], kind="stable")]
    n_mix = int(np.prod([len(v) for v in RISK.values()]))
    passed = np.zeros(p.size, bool)
    worst = {h: np.full(p.size, np.nan, np.float32) for h in YEARS}
    done, size = 0, 2000
    with ProcessPoolExecutor(4) as ex:
        while done < len(flat) and passed.sum() < want:
            part = flat[done:done + size]
            e_of = part // n_mix
            for e, mi, res in ex.map(_boot_job, [(int(e), part[e_of == e] % n_mix) for e in np.unique(e_of)]):
                j = e * n_mix + mi
                ok = np.ones(len(mi), bool)
                for h, v in res.items():
                    worst[h][j] = v; ok &= v > -0.50
                passed[j] = ok
            done += len(part)
            print(f"  checked the best {done:,} (weaker year down to ${score[part[-1]]:,.0f}): "
                  f"{int(passed.sum()):,} pass rule 4", flush=True)
            size *= 2
    np.savez_compressed(ROOT / "results/gold/v17b_boot.npz", passed=passed, **{f"boot_{h}": v for h, v in worst.items()})
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


if __name__ == "__main__":
    search() if "search" in sys.argv else select()
