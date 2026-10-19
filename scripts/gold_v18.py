"""Gold Asian breakout v18: pick from results/gold/v18_search.npz using 2026 ONLY. 2025 and Q4 2024 sit in
results/gold/v18_sealed.npz, which this script opens only with --reveal, once, after the pick is fixed.

PROTOCOL (written and committed before the search ran; v17's 2026-only pick of the same engine family failed 2025 at
-59%, so the selection rule itself is chosen by an out-of-sample test inside 2026 instead of by judgement):

Candidate rules, each applied to one selection window S of 2026:
  filters (all rules): drawdown in S >= -35%; >= 70% of S's months up; at least half of the one-step neighbours with
    drawdown >= -40% and the same months rule.
  then a block bootstrap of S's trades (2-week blocks, 400 simulated one-year paths, seed 11) must have a worst-decile
    drawdown better than B, with every trade's R first reduced by `hc` (an edge haircut) where stated:
      R1: B -50%, no haircut, highest S profit          R4: B -50%, no haircut, highest plateau profit
      R2: B -40%, no haircut, highest S profit          R5: B -40%, no haircut, highest plateau profit
      R3: B -50%, haircut 0.1R, highest S profit        R6: B -50%, haircut 0.1R, highest plateau profit
    (plateau profit = median S profit over the candidate and its one-step neighbours)
Choosing the rule (inside 2026 only): fold A picks on Jan-May and is scored on Jun-Oct; fold B picks on Jun-Oct and
  is scored on Jan-May. A rule qualifies if its picks' drawdown in the scoring half is better than -40% in both folds;
  of those, the highest geometric mean of the two scoring-half growths wins (ties: lower rule number). If none
  qualifies, the rule with the best worse-fold drawdown wins.
v18 = the winning rule applied to all of 2026 (S = Jan-Oct 2026). Then --reveal prints its 2025 and Q4 2024 once.
Target (stated in advance, by the user): 2025 drawdown better than -50%.
    python scripts/gold_v18.py            -> rule test inside 2026 and the v18 pick (2026 figures only)
    python scripts/gold_v18.py --reveal   -> the pick's 2025 and Q4 2024 (sealed file)
"""
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "scripts"))
import gold_portfolio_sim as S  # noqa: E402
import gold_v18_search as SR  # noqa: E402

N_MONTHS = {"y26": 10, "h1": 5, "h2": 5}
BOOT = {"y26": ("2026-01-01", "2026-10-15"), "h1": ("2026-01-01", "2026-06-01"), "h2": ("2026-06-01", "2026-10-15")}
RULES = {"R1": (-0.50, 0.0, "max"), "R2": (-0.40, 0.0, "max"), "R3": (-0.50, 0.1, "max"),
         "R4": (-0.50, 0.0, "plateau"), "R5": (-0.40, 0.0, "plateau"), "R6": (-0.50, 0.1, "plateau")}
FOLDS = {"A": ("h1", "h2"), "B": ("h2", "h1")}
PICK = ROOT / "results/gold/v18_pick.json"


def load():
    z = np.load(SR.OUT)
    shape = tuple(z["shape"])
    return {k: z[k].reshape(shape) for k in z.files if k != "shape"}, shape


def shifted(p):
    """One-step neighbours of every cell along every axis: list of (array, valid mask)."""
    out = []
    for ax in range(p.ndim):
        for lo_src, lo_dst in ((slice(1, None), slice(None, -1)), (slice(None, -1), slice(1, None))):
            a = np.full(p.shape, np.nan, np.float32)
            src = [slice(None)] * p.ndim; dst = [slice(None)] * p.ndim
            src[ax] = lo_src; dst[ax] = lo_dst
            a[tuple(dst)] = p[tuple(src)]
            out.append(a)
    return out


def neighbour_share(p):
    nb = shifted(p.astype(np.float32))
    hits = np.nansum(nb, axis=0); tot = np.sum([~np.isnan(a) for a in nb], axis=0)
    return hits / np.maximum(tot, 1)


def plateau(usd):
    return np.nanmedian(np.stack([usd.astype(np.float32)] + shifted(usd)), axis=0)


def describe(ix):
    return {k: (v[i].item() if hasattr(v[i], "item") else v[i]) for (k, v), i in zip(SR.DIMS.items(), ix)}


_W: dict = {}


def _boot_job(arg):
    e, mix_idx, win, hc = arg
    if not _W:
        SR.init(); _W["mix"] = SR.mixes()
    t = SR.trades_for(SR.engine_set(e))
    if hc:
        t = t.assign(r=t.r - hc)
    W, SM, CAP, DST, DL = (a[mix_idx] for a in _W["mix"])
    a, b = BOOT[win]
    return e, mix_idx, S.boot_p10(S.boot_samples(t, a, b), W, SM, CAP, DST, DL)


class Selector:
    def __init__(self, r, shape, pool):
        self.r, self.shape, self.pool = r, shape, pool
        self.n_mix = int(np.prod([len(v) for v in SR.RISK.values()]))
        self.boot = {}          # (window, haircut) -> worst-decile drawdown per cell (NaN = not computed)
        self.cand, self.score = {}, {}

    def candidates(self, win):
        if win not in self.cand:
            r = self.r
            ok = (r[f"{win}_up"] >= np.ceil(0.7 * N_MONTHS[win]))
            c = (r[f"{win}_dd"] >= -0.35) & ok & (neighbour_share((r[f"{win}_dd"] >= -0.40) & ok) >= 0.5)
            self.cand[win] = np.flatnonzero(c.ravel())
            self.score[(win, "max")] = r[f"{win}_usd"].ravel()
            self.score[(win, "plateau")] = plateau(r[f"{win}_usd"]).ravel()
        return self.cand[win]

    def pick(self, win, B, hc, obj, want=1):
        """Highest-scoring candidates of window `win` whose bootstrap worst decile beats B, checked best-first."""
        flat = self.candidates(win)
        sc = self.score[(win, obj)]
        flat = flat[np.argsort(-sc[flat], kind="stable")]
        p10 = self.boot.setdefault((win, hc), np.full(int(np.prod(self.shape)), np.nan, np.float32))
        hits, done, size = [], 0, 1000
        while done < len(flat) and len(hits) < want:
            part = flat[done:done + size]
            todo = part[np.isnan(p10[part])]
            if len(todo):
                e_of = todo // self.n_mix
                jobs = [(int(e), todo[e_of == e] % self.n_mix, win, hc) for e in np.unique(e_of)]
                for e, mi, v in self.pool.map(_boot_job, jobs):
                    p10[e * self.n_mix + mi] = v
            hits += [int(j) for j in part if p10[j] > B][:want - len(hits)]
            done += len(part); size *= 2
        return hits, done


def run():
    r, shape = load()
    print(f"{int(np.prod(shape)):,} combinations (2026 only; 2025 and Q4 2024 sealed)", flush=True)
    rows = []
    with ProcessPoolExecutor(4) as pool:
        sel = Selector(r, shape, pool)
        for w in ("h1", "h2", "y26"):
            print(f"  {w}: {len(sel.candidates(w)):,} pass the filters", flush=True)
        for name, (B, hc, obj) in RULES.items():
            row = dict(rule=name)
            for f, (s_win, t_win) in FOLDS.items():
                hits, n = sel.pick(s_win, B, hc, obj)
                if not hits:
                    row[f] = None; continue
                ix = np.unravel_index(hits[0], shape)
                row[f] = dict(sel_usd=float(r[f"{s_win}_usd"][ix]), sel_dd=float(r[f"{s_win}_dd"][ix]),
                              test_usd=float(r[f"{t_win}_usd"][ix]), test_dd=float(r[f"{t_win}_dd"][ix]), setting=describe(ix))
            rows.append(row)
            print(f"  {name}: " + " | ".join(
                f"fold {f}: " + ("no pick" if row[f] is None else
                                 f"chosen ${row[f]['sel_usd']:,.0f} ({row[f]['sel_dd']:.0%}) -> scored ${row[f]['test_usd']:,.0f} "
                                 f"({row[f]['test_dd']:.0%})") for f in FOLDS), flush=True)
        ok = [x for x in rows if all(x[f] is not None and x[f]["test_dd"] > -0.40 for f in FOLDS)]
        if ok:
            best = max(ok, key=lambda x: (np.sqrt(x["A"]["test_usd"] / 1000 * x["B"]["test_usd"] / 1000), -int(x["rule"][1:])))
            why = "qualifies in both folds with the highest geometric-mean growth in the scoring halves"
        else:
            live = [x for x in rows if all(x[f] is not None for f in FOLDS)]
            best = max(live, key=lambda x: (min(x["A"]["test_dd"], x["B"]["test_dd"]), -int(x["rule"][1:])))
            why = "no rule qualifies; best worse-fold drawdown"
        B, hc, obj = RULES[best["rule"]]
        print(f"\nRULE CHOSEN INSIDE 2026: {best['rule']} ({why})", flush=True)
        hits, n = sel.pick("y26", B, hc, obj, want=5)
    for j in hits:
        ix = np.unravel_index(j, shape)
        print(f"  2026 ${r['y26_usd'][ix]:,.0f} ({r['y26_dd'][ix]:.0%}, {int(r['y26_up'][ix])}/10 up) | Jan-May "
              f"${r['h1_usd'][ix]:,.0f} ({r['h1_dd'][ix]:.0%}) | Jun-Oct ${r['h2_usd'][ix]:,.0f} ({r['h2_dd'][ix]:.0%}) | "
              + ", ".join(f"{k}={v}" for k, v in describe(ix).items()))
    ix = np.unravel_index(hits[0], shape)
    pick = dict(rule=best["rule"], index=[int(i) for i in ix], setting=describe(ix), y26_usd=float(r["y26_usd"][ix]),
                y26_dd=float(r["y26_dd"][ix]), folds=rows)
    PICK.write_text(json.dumps(pick, indent=1))
    print("\nV18 PICK:", pick["setting"])
    return pick


def reveal():
    pick = json.loads(PICK.read_text())
    z = np.load(SR.OUT_SEALED)
    shape = tuple(z["shape"]); ix = tuple(pick["index"])
    print("V18 PICK:", pick["setting"])
    print(f"  2026 (chosen on): ${pick['y26_usd']:,.0f} DD {pick['y26_dd']:.1%}")
    for k, lbl in (("y25", "2025 (unseen)"), ("q4", "Q4 2024 (unseen)")):
        g = {m: z[f"{k}_{m}"].reshape(shape)[ix] for m in ("usd", "dd", "up", "worst")}
        print(f"  {lbl}: ${g['usd']:,.0f} DD {g['dd']:.1%} months up {int(g['up'])} worst month {g['worst']:+.1%}")


if __name__ == "__main__":
    reveal() if "--reveal" in sys.argv else run()
