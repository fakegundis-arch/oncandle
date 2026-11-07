"""Per-token average post-move ("text direction") with month cross-fitting on the search period."""
from __future__ import annotations
import sys
from collections import defaultdict
import numpy as np, pandas as pd
from lib import WORK, tokens, first_line

S1 = pd.Timestamp("2026-05-01", tz="UTC").timestamp()


def post_tokens(clean: pd.Series, ch: pd.Series) -> list[list[str]]:
    out = []
    for t, c in zip(clean, ch):
        h = first_line(t)
        tl = tokens(h)
        s = set(tl) | {a + "_" + b for a, b in zip(tl, tl[1:])}
        if "❗" in h: s.add("__excl")
        if "🚨" in t: s.add("__siren")
        s.add("__" + c)
        out.append(sorted(s))
    return out


def fit(toks, y, idx, shrink=20.0, minn=8):
    sm, cn = defaultdict(float), defaultdict(int)
    for i in idx:
        if not np.isfinite(y[i]):
            continue
        for w in toks[i]:
            sm[w] += y[i]; cn[w] += 1
    return {w: sm[w] / (cn[w] + shrink) for w in sm if cn[w] >= minn}


def score(toks, table, idx):
    out = np.full(len(toks), np.nan)
    for i in idx:
        v = [table[w] for w in toks[i] if w in table]
        out[i] = np.sum(v) if v else 0.0
    return out


def target(base, H=300, o=2, clip=5.0):
    P, offs = base["P"], list(base["offs"])
    v = np.where(np.isfinite(base["vol60"]), base["vol60"], base["vol240"])
    y = (P[:, offs.index(o + H if o + H in offs else H)] - P[:, offs.index(o)]) / v
    return np.clip(y, -clip, clip)


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else ""
    p = pd.read_pickle(f"{WORK}/posts{tag}.pkl")
    toks = post_tokens(p.clean, p.ch)
    ts = p.ts.to_numpy()
    mon = (pd.to_datetime(ts, unit="s").year * 12 + pd.to_datetime(ts, unit="s").month).to_numpy()
    srch = ts < S1
    res = {}
    for inst in ["gold", "nasdaq"]:
        base = np.load(f"{WORK}/base{tag}_{inst}.npz")
        for H in [60, 300, 1800]:
            y = target(base, H)
            sc = np.full(len(ts), np.nan)
            for m in np.unique(mon[srch]):
                tr = np.flatnonzero(srch & (mon != m))
                te = np.flatnonzero(srch & (mon == m))
                tab = fit(toks, y, tr)
                sc[te] = score(toks, tab, te)[te]
            tab = fit(toks, y, np.flatnonzero(srch))
            te = np.flatnonzero(~srch)
            sc[te] = score(toks, tab, te)[te]
            res[f"{inst}_{H}"] = sc
            for nm, msk in [("search(CV)", srch), ("check", ~srch)]:
                ok = msk & np.isfinite(sc) & np.isfinite(y) & (sc != 0)
                c = np.corrcoef(sc[ok], y[ok])[0, 1]
                q = np.abs(sc[ok]) > np.quantile(np.abs(sc[ok]), 0.9)
                hit = np.mean(np.sign(sc[ok][q]) == np.sign(y[ok][q]))
                print(inst, H, nm, "corr", round(c, 4), "top10% hit", round(hit, 3), "mean signed y", round(np.mean(np.sign(sc[ok][q]) * y[ok][q]), 3))
    np.savez(f"{WORK}/tscore{tag}.npz", **res)
