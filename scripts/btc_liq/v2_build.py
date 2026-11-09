"""Version 2 search on Jan-Jun 2026 (1,382,400 settings), luck check on fake events (3 seeds) and the pre-registered
pick.  usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/btc_liq/v2_build.py <validate|grid>"""
import itertools
import json
import sys
import time
from pathlib import Path

import numba as nb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_lab as V  # noqa: E402

C = V.C
SIGS = [dict(zip(V.SIG, v)) for v in itertools.product(*V.SIG.values())]
KNOBS = list(V.SIG) + ["entry"] + list(V.EXITS) + ["pos"]
GRID_VALS = {**V.SIG, "entry": V.ENTRY, **V.EXITS, "pos": V.POS}
TS = lambda s: int(pd.Timestamp(s, tz="UTC").timestamp())
A, SPLIT, B = TS("2026-01-01"), TS("2026-04-01"), TS("2026-07-01")
WORK = V.ROOT / "data" / "btc" / "v2"


@nb.njit(cache=True)
def nb_grid(rows, ent, ext, rr, sds, pxs, risk, cap, maxopen, split, a, b):
    nx = ent.shape[1]
    out = np.zeros((nx, 2, 9))
    for q in range(nx):
        e1, x1, r1, s1, p1 = ent[rows, q], ext[rows, q], rr[rows, q], sds[rows, q], pxs[rows, q]
        for pi in range(2):
            res = V.nb_account(e1, x1, r1, s1, p1, 1 if pi == 0 else 3, risk, cap, maxopen, split, a, b)
            for k in range(9):
                out[q, pi, k] = res[k]
    return out


def validate():
    D = V.Data("build")
    tk = D.tk
    rng = np.random.default_rng(0)
    sig, d = D.signals(0.2, 0.2, 1, "any", "any", "none")
    sig, d = sig[sig >= A], d[sig >= A]
    print("signals for the loosest trigger:", len(sig))
    bad = tot = 0
    for kind in (0, 1, 2):
        for stress in (False, True):
            ent, ext, rr, sds, pxs = V.outcomes(D, sig, d, kind, stress)
            for e in range(len(sig)):
                v = D.vol[sig[e] - D.t0]
                if kind == 0:
                    m = C.market_entry(tk, int(sig[e]), int(d[e]), stress=stress)
                else:
                    i0 = C.bar_at(tk, int(sig[e]) + (C.LAT_STRESS if stress else C.LAT))
                    m = None
                    if i0 is not None:
                        px = 0.5 * (tk["ask_first"][i0] + tk["bid_first"][i0]) - d[e] * (0.5 if kind == 1 else 1.0) * v
                        pe = C.pending_entry(tk, i0, [("limit", int(d[e]), px)], 180, stress=stress)
                        m = None if pe is None else (pe[0], pe[1][0][1])
                if m is None:
                    bad += int(not np.all(np.isnan(rr[e])))
                    tot += 1
                    continue
                j, fill = m
                for q in rng.choice(len(V.EXL), 40, replace=False):
                    x = V.EXL[q]
                    be, tr = V.MANAGE[x["manage"]]
                    kx, r, sd = C.exit_trade(tk, j, fill, int(d[e]), x["stop"] * v, tp_r=x["target"],
                                             max_hold_s=x["timer"], be_at_r=None if np.isnan(be) else be,
                                             trail_r=None if np.isnan(tr) else tr, stress=stress)
                    tot += 1
                    if not (abs(r - rr[e, q]) < 1e-9 and int(tk["t"][min(kx, len(tk['t']) - 1)]) == ext[e, q]
                            and int(tk["t"][j]) == ent[e, q] and abs(sd - sds[e, q]) < 1e-9):
                        bad += 1
                        if bad <= 5:
                            print("MISMATCH", kind, stress, sig[e], x, r, rr[e, q], kx, ext[e, q])
    print(f"engine check: {tot} comparisons, {bad} mismatches")
    # account check (no cap binding) against common.account
    ent, ext, rr, sds, pxs = V.outcomes(D, sig, d, 0, False)
    for q in rng.choice(len(V.EXL), 20, replace=False):
        for mp in (1, 3):
            res = V.summarize(V.nb_account(ent[:, q], ext[:, q], rr[:, q], sds[:, q], pxs[:, q], mp, 0.10, 1e12, 0.30,
                                           SPLIT, A, B))
            ok = ~np.isnan(rr[:, q]) & (ent[:, q] >= A) & (ent[:, q] < B)
            t = pd.DataFrame(dict(entry_ts=ent[ok, q], exit_ts=ext[ok, q], r=rr[ok, q]))
            if mp == 1:                     # one at a time: drop trades that start before the previous one ended
                keep, busy = [], -1
                for i, row in enumerate(t.itertuples()):
                    if row.entry_ts < busy:
                        continue
                    keep.append(i)
                    busy = row.exit_ts
                t = t.iloc[keep]
                acc = C.account(t, 0.10, max_open_risk=0.10 + 1e-9)
            else:
                acc = C.account(t.assign(_k=0), 0.10, max_open_risk=0.30)
            if abs(acc["final"] - res["usd"]) > 1e-6 * max(1, acc["final"]) or abs(acc["dd"] - res["dd"]) > 1e-9:
                print("ACCOUNT MISMATCH", q, mp, acc["final"], res["usd"], acc["dd"], res["dd"], acc["taken"], res["n"])
    print("account check done")


def grid_for(D, events, tag):
    """events: (sig array, dir array) of unique events; cfg_rows: rows per signal config (sorted by time)."""
    sig, dirs, cfg_rows = events
    rows_out = []
    t0 = time.time()
    for kind, ename in enumerate(V.ENTRY):
        res = {}
        for stress in (False, True):
            res[stress] = V.outcomes(D, sig, dirs, kind, stress)
        for ci, sc in enumerate(SIGS):
            rows = cfg_rows[ci]
            g = nb_grid(rows, *res[False], V.RISK, V.CAP, V.MAXOPEN, SPLIT, A, B)
            gs = nb_grid(rows, *res[True], V.RISK, V.CAP, V.MAXOPEN, SPLIT, A, B)
            for q, x in enumerate(V.EXL):
                for pi, pos in enumerate(V.POS):
                    n, R, gw, gl, r1, r2, usd, dd, ml = g[q, pi]
                    sgw, sgl = gs[q, pi, 2], gs[q, pi, 3]
                    rows_out.append((ci, kind, q, pos, int(n), R, gw / gl if gl > 0 else (99.0 if gw > 0 else 0.0),
                                     r1, r2, usd, dd, ml, sgw / sgl if sgl > 0 else (99.0 if sgw > 0 else 0.0),
                                     gs[q, pi, 1]))
        print(f"  {tag}: entry {ename} done, {time.time() - t0:.0f}s", flush=True)
    df = pd.DataFrame(rows_out, columns=["sig", "entry", "exit", "pos", "n", "R", "pf", "h1R", "h2R", "usd", "dd",
                                         "max_lot", "stress_pf", "stress_R"])
    df["ok_nodd"] = (df.n >= 40) & (df.pf >= 1.3) & (df.h1R > 0) & (df.h2R > 0) & (df.stress_pf >= 1.15)
    df["ok"] = df.ok_nodd & (df.dd > -0.35)
    return df


def events_real(D):
    per = [D.signals(**sc) for sc in SIGS]
    allk = np.unique(np.concatenate([np.c_[s, d] for s, d in per]), axis=0)
    key = {(int(a), int(b)): i for i, (a, b) in enumerate(allk)}
    cfg_rows = [np.array([key[(int(a), int(b))] for a, b in zip(s, d)], np.int64) for s, d in per]
    return allk[:, 0].astype(np.int64), allk[:, 1].astype(np.int64), cfg_rows


def events_fake(real, seed):
    sig, dirs, cfg_rows = real
    rng = np.random.default_rng(seed)
    sh = rng.integers(DAYS := 86400, 14 * DAYS, len(sig)) * rng.choice([-1, 1], len(sig))
    fs = (sig - A + sh) % (B - A) + A
    rows = [r[np.argsort(fs[r], kind="stable")] for r in cfg_rows]
    return fs.astype(np.int64), dirs, rows


def cfg_of(row):
    c = dict(SIGS[int(row["sig"])])
    c["entry"] = V.ENTRY[int(row["entry"])]
    c.update(V.EXL[int(row["exit"])])
    c["pos"] = int(row["pos"])
    return c


def canon(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "None"
    if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
        return f"{float(v):g}"
    return str(v)


def neighbours(c, okset):
    out = []
    for k in KNOBS:
        vals = GRID_VALS[k]
        i = next(n for n, v in enumerate(vals) if canon(v) == canon(c[k]))
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append(tuple(canon({**c, k: vals[j]}[q]) for q in KNOBS) in okset)
    return float(np.mean(out))


def grid():
    WORK.mkdir(parents=True, exist_ok=True)
    V.OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    D = V.Data("build")
    real = events_real(D)
    print(f"data {time.time() - t0:.0f}s; unique signal events {len(real[0])}; median per config "
          f"{int(np.median([len(r) for r in real[2]]))}", flush=True)
    summary = {}
    for tag, ev in [("real", real)] + [(f"fake{s}", events_fake(real, s)) for s in (1, 2, 3)]:
        f = WORK / f"grid_{tag}.parquet"
        if f.exists():
            df = pd.read_parquet(f)
        else:
            df = grid_for(D, ev, tag)
            df.to_parquet(f)
        nodd = df[df.ok_nodd]
        summary[tag] = dict(settings=len(df), passing=int(df.ok.sum()), passing_no_dd=int(len(nodd)),
                            best_R_no_dd=float(nodd.R.max()) if len(nodd) else None,
                            best_R_n40=float(df[df.n >= 40].R.max()), best_usd_n40=float(df[df.n >= 40].usd.max()))
        print(tag, summary[tag], f"{time.time() - t0:.0f}s", flush=True)
    df = pd.read_parquet(WORK / "grid_real.parquet")
    rule = "all rules"
    cand = df[df.ok].copy()
    flag = "ok"
    if not len(cand):
        rule, flag, cand = "all rules except drawdown", "ok_nodd", df[df.ok_nodd].copy()
    okset = {tuple(canon(cfg_of(r)[q]) for q in KNOBS) for r in df[df[flag]].to_dict("records")}
    if len(cand):
        cand["cfg"] = [cfg_of(r) for r in cand.to_dict("records")]
        cand["nb_pass"] = [neighbours(c, okset) for c in cand.cfg]
        cand = cand.sort_values(["nb_pass", "usd", "dd"], ascending=False)
        pick = cand.iloc[0]
    else:
        rule = "info-only: highest R"
        pick = df.sort_values("R", ascending=False).iloc[0]
        pick["cfg"], pick["nb_pass"] = cfg_of(pick), 0.0
    fakes = [summary[f"fake{s}"]["best_R_no_dd"] for s in (1, 2, 3)]
    beats = all(f is None or pick["R"] > f for f in fakes)
    v1row = df[(df.sig == SIGS.index({k: V.V1[k] for k in V.SIG})) & (df.entry == V.ENTRY.index(V.V1["entry"]))
               & (df.exit == next(i for i, x in enumerate(V.EXL) if all(x[k] == V.V1[k] for k in V.EXITS)))
               & (df.pos == V.V1["pos"])].iloc[0]
    cols = ["n", "R", "pf", "h1R", "h2R", "usd", "dd", "max_lot", "stress_pf"]
    txt = [json.dumps(summary, indent=1),
           f"\nversion 1 inside this grid (Jan-Jun, 100x cap): " + ", ".join(f"{k} {v1row[k]:.2f}" for k in cols),
           f"\nPICK ({rule}): {V.describe(pick.cfg)}",
           "  Jan-Jun: " + ", ".join(f"{k} {pick[k]:.2f}" for k in cols) + f", passing neighbours {pick.nb_pass:.2f}",
           f"  luck: best fake R meeting every rule except drawdown {fakes}; pick beats every fake: {beats}"]
    if len(cand):
        top = cand.head(25)
        txt.append(f"\n{len(cand)} settings pass ({rule}); top 25 by the pick rule:")
        for r in top.to_dict("records"):
            txt.append(f"  nb {r['nb_pass']:.2f} | n {r['n']} R {r['R']:+.1f} PF {r['pf']:.2f} DD {r['dd']:.0%} "
                       f"${r['usd']:,.0f} stressPF {r['stress_pf']:.2f} | {V.describe(r['cfg'])}")
        cand.drop(columns="cfg").head(2000).to_csv(V.OUT / "top_settings.csv", index=False)
    (V.OUT / "build.txt").write_text("\n".join(txt) + "\n")
    (V.OUT / "pick.json").write_text(json.dumps(dict(rule=rule, pick=pick.cfg, desc=V.describe(pick.cfg),
                                                     build={k: float(pick[k]) for k in cols},
                                                     nb_pass=float(pick.nb_pass), luck=dict(best_fake_R=fakes,
                                                     beats_every_fake=bool(beats)), version1=V.V1), indent=1,
                                                default=str))
    print("\n".join(txt))


if __name__ == "__main__":
    {"validate": validate, "grid": grid}[sys.argv[1]]()
