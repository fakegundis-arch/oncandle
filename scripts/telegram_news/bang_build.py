"""Jan-Jun 2026 grids of the FinancialJuice ❗ bot (bang_lab.py): four groups (gold / Nasdaq x straddle / direct),
the user's fixed settings, and the pre-registered pick (or info-only best) per group.
usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/telegram_news/bang_build.py"""
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bang_lab as B  # noqa: E402
import newsbot_lab as N  # noqa: E402

_F: dict = {}


def key(c, g):
    return tuple(str(c[k]) for k in g)


def neighbours(c, g, kind):
    out = []
    for k, vals in g.items():
        if len(vals) < 2:
            continue
        if k == "dir":                                     # move L / k within the same family
            d = B.DIRS[c["dir"]]
            if d["fam"] not in ("MOM", "FADE"):
                continue
            for kk, opts in (("L", [10, 30, 60]), ("k", [0.0, 0.5, 1.0])):
                i = opts.index(d[kk])
                for j in (i - 1, i + 1):
                    if 0 <= j < len(opts):
                        out.append({**c, "dir": B.DIRS.index({**d, kk: opts[j]})})
            continue
        i = vals.index(c[k])
        out += [{**c, k: vals[j]} for j in (i - 1, i + 1) if 0 <= j < len(vals)]
    return out


def work(args):
    group, c = args
    inst, kind = group
    t, ts = B.run(_F[inst], inst, kind, c), B.run(_F[inst], inst, kind, c, stress=True)
    ok, m = B.passes_build(t, ts)
    return dict(c, ok=ok, **{k: v for k, v in m.items() if not k.endswith(("40", "1.3", "R>0", "1.15", "35%"))})


def clean(v):
    return v.item() if hasattr(v, "item") else (None if isinstance(v, float) and np.isnan(v) else v)


def main():
    tr = B.triggers(*B.BUILD)
    assert (tr.t < pd.Timestamp(B.BUILD[1], tz="UTC")).all()
    for inst in N.SYMS:
        _F[inst] = B.features(tr, inst)
    txt = [f"FJ ❗ triggers without $MACRO, Jan-Jun (first of story): {len(tr)}; inside calendar windows: {int(tr.in_cal.sum())}"]
    out = {"user": {}, "picks": {}}
    for group, c in B.USER.items():
        inst, kind = group
        t, ts = B.run(_F[inst], inst, kind, c), B.run(_F[inst], inst, kind, c, stress=True)
        ok, m = B.passes_build(t, ts)
        out["user"][f"{inst}_{kind}"] = c
        txt.append(f"USER {inst} {kind}: {B.describe(group, c)} | Jan-Jun n {m['n']} R {m['R']:+.1f} PF {m['pf']:.2f} "
                   f"win {m['win']:.0%} DD {m['dd']:.0%} $ {m['usd']:,.0f} | Jan-Mar {m['h1R']:+.1f} Apr-Jun {m['h2R']:+.1f} "
                   f"| stress PF {m['stress_pf']:.2f} | passes {ok}")
    for group in B.GRIDS:
        inst, kind = group
        g = B.GRIDS[group]
        cs = B.configs(group)
        with Pool(4) as pool:
            rows = pool.map(work, [(group, c) for c in cs], chunksize=16)
        df = pd.DataFrame(rows)
        okd = {key(r, g): bool(r["ok"]) for r in rows}
        df["nb_pass"] = [np.mean([okd.get(key(n, g), False) for n in neighbours(r, g, kind)]) for r in rows]
        df["desc"] = [B.describe(group, {k: r[k] for k in g}) for r in rows]
        df.to_csv(N.OUT / f"bang_grid_{inst}_{kind}.csv", index=False)
        txt.append(f"\n== {inst} {kind}: {len(df)} settings, {int(df.ok.sum())} pass; median PF {df.pf.median():.2f}; "
                   f"{int((df.R > 0).sum())} made money; median trades {df.n.median():.0f}")
        cols = ["desc", "n", "R", "pf", "win", "dd", "h1R", "h2R", "stress_pf", "nb_pass"]
        txt.append(df.sort_values("R", ascending=False).head(8)[cols].to_string(index=False))
        cand = df[df.ok].sort_values(["nb_pass", "dd", "R"], ascending=[False, False, False])
        if len(cand):
            c = {k: clean(cand.iloc[0][k]) for k in g}
            out["picks"][f"{inst}_{kind}"] = {"pick": c}
            txt.append("  passing (pick rule order):\n" + cand.head(6)[cols].to_string(index=False) +
                       f"\n  PICK: {B.describe(group, c)}")
        else:
            b = df.sort_values("R", ascending=False).iloc[0]
            c = {k: clean(b[k]) for k in g}
            out["picks"][f"{inst}_{kind}"] = {"info_only": c}
            txt.append(f"  NO SETTING PASSES - info-only Jul-Oct run of the highest-R: {B.describe(group, c)}")
    (N.OUT / "bang_build.txt").write_text("\n".join(txt) + "\n")
    (N.OUT / "bang_pick.json").write_text(json.dumps(out, indent=1, default=str))
    print("\n".join(txt))


if __name__ == "__main__":
    main()
