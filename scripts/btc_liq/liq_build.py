"""Jan-Jun 2026 grid of liq_lab.py (4 families x signal knobs x 64 exits), the luck check on fake events (3 seeds) and
the pre-registered pick.  usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/btc_liq/liq_build.py"""
import itertools
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import liq_lab as Q  # noqa: E402

C = Q.C
MK = TK = None
EV: dict = {}
OUT: dict = {}
EXL = Q.exit_list()
NE = len(EXL)


def sig_configs():
    out = []
    for fam, g in Q.FAMILIES.items():
        for vals in itertools.product(*g.values()):
            out.append((fam, dict(zip(g, vals))))
    return out


def _outc(args):
    ts, d, stress = args
    n = len(ts)
    ent, ext, r = np.zeros((n, NE), np.int64), np.zeros((n, NE), np.int64), np.full((n, NE), np.nan)
    T = TK["t"]
    for i, (s, di) in enumerate(zip(ts.tolist(), d.tolist())):
        v = MK.vol[s - MK.t0] if 0 <= s - MK.t0 < MK.n else np.nan
        if not np.isfinite(v) or v <= 0:
            continue
        e = C.market_entry(TK, s, di, stress=stress)
        if e is None:
            continue
        j, fill = e
        for k, x in enumerate(EXL):
            kx, rr, sd = C.exit_trade(TK, j, fill, di, x["stop"] * v, tp_r=x["target"], max_hold_s=x["H"], stress=stress)
            ent[i, k], ext[i, k], r[i, k] = T[j], T[min(kx, len(T) - 1)], rr
    return ent, ext, r


def outcomes(pool, keys):
    """keys: array (n, 2) of unique (ts, dir) -> {stress: (ent, ext, r)}"""
    res = {}
    chunks = np.array_split(np.arange(len(keys)), 64)
    for stress in (False, True):
        parts = pool.map(_outc, [(keys[c, 0], keys[c, 1], stress) for c in chunks if len(c)])
        res[stress] = tuple(np.concatenate([p[i] for p in parts]) for i in range(3))
    return res


def simulate(rows, ts, ent, ext, r, k):
    out_r, out_e, busy = [], [], -1
    for row, s in zip(rows.tolist(), ts.tolist()):
        if s <= busy or not np.isfinite(r[row, k]):
            continue
        busy = ext[row, k]
        out_r.append(r[row, k])
        out_e.append(ent[row, k])
    return pd.DataFrame(dict(entry_ts=np.array(out_e, np.int64), r=np.array(out_r, float)))


def _grid(j):
    fam, sc = SIGS[j]
    ts, rows = EV[j]
    o, os_ = OUT[False], OUT[True]
    res = []
    for k, x in enumerate(EXL):
        t = simulate(rows, ts, *o, k)
        tsx = simulate(rows, ts, *os_, k)
        res.append(dict(fam=fam, **sc, **x, **Q.build_metrics(t, tsx)))
    return res


def run_grid(pool, events_by_sig):
    """events_by_sig: list of (ts, d) per signal config -> grid DataFrame"""
    global OUT
    allk = np.unique(np.concatenate([np.c_[ts, d] for ts, d in events_by_sig if len(ts)] or [np.zeros((0, 2), int)]),
                     axis=0)
    key_row = {(int(a), int(b)): i for i, (a, b) in enumerate(allk)}
    for j, (ts, d) in enumerate(events_by_sig):
        o = np.argsort(ts, kind="stable")
        EV[j] = (ts[o], np.array([key_row[(int(a), int(b))] for a, b in zip(ts[o], d[o])], dtype=np.int64))
    t0 = time.time()
    OUT = outcomes(pool, allk)
    print(f"  outcomes for {len(allk)} events x {NE} exits x 2: {time.time() - t0:.0f}s", flush=True)
    return allk


SIGS = sig_configs()


def neighbours(row, okd):
    fam = row["fam"]
    g = {**Q.FAMILIES[fam], **Q.EXITS}
    out = []
    for k, vals in g.items():
        i = vals.index(row[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append(okd.get(key({**row, k: vals[j]}), False))
    return np.mean(out) if out else 0.0


def canon(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "None"
    if isinstance(v, (int, float, np.integer, np.floating)):
        return f"{float(v):g}"
    return str(v)


def key(r):
    fam = r["fam"]
    return (fam,) + tuple(canon(r[k]) for k in list(Q.FAMILIES[fam]) + list(Q.EXITS))


def main():
    global MK, TK
    t0 = time.time()
    MK = Q.Market(Q.BUILD[1])
    TK = Q.load_exness(Q.BUILD[1])
    MK.liq_map()
    print(f"market loaded {time.time() - t0:.0f}s; Exness seconds {len(TK['t'])}, median spread "
          f"{np.median(TK['ask_first'] - TK['bid_first']):.2f}", flush=True)
    a = int(pd.Timestamp(Q.BUILD[0], tz="UTC").timestamp())
    real = []
    for fam, sc in SIGS:
        ts, d = MK.events(fam, sc)
        keep = ts >= a - 4 * 3600
        real.append((ts[keep], d[keep]))
    print("signal configs", len(SIGS), "events per config median", int(np.median([len(x[0]) for x in real])), flush=True)
    summary = {}
    for tag, evs in [("real", real)] + [(f"fake{s}", [Q.shift_events(ts, d, 1000 * s + j) for j, (ts, d) in
                                                       enumerate(real)]) for s in (1, 2, 3)]:
        f = Q.OUT / f"grid_{tag}.csv"
        if f.exists():                              # resume: this grid was finished before a restart
            df = pd.read_csv(f)
        else:
            with Pool(4) as pool:
                run_grid(pool, evs)
            with Pool(4) as pool:
                rows = sum(pool.map(_grid, range(len(SIGS)), chunksize=2), [])
            df = pd.DataFrame(rows)
            df.to_csv(f, index=False)
        nodd = df[df.ok_nodd]
        summary[tag] = dict(settings=len(df), passing=int(df.ok.sum()), passing_no_dd=int(len(nodd)),
                            best_R_no_dd=float(nodd.R.max()) if len(nodd) else None,
                            best_R_n40=float(df[df.n >= 40].R.max()), best_usd_n40=float(df[df.n >= 40].usd.max()))
        print(tag, summary[tag], f"{time.time() - t0:.0f}s", flush=True)
    df = pd.read_csv(Q.OUT / "grid_real.csv")
    df["target"] = df.target.astype(object).where(df.target.notna(), None)
    for c in ("target",):
        df[c] = [None if v is None else int(v) for v in df[c]]
    recs = df.to_dict("records")
    for r in recs:
        for k in r:
            if isinstance(r[k], float) and k in ("W", "k", "m", "D", "d", "q", "s", "x", "y") and not np.isnan(r[k]):
                r[k] = int(r[k]) if float(r[k]).is_integer() and k in ("W", "k", "m", "D") else r[k]
    okd = {key(r): bool(r["ok"]) for r in recs}
    okn = {key(r): bool(r["ok_nodd"]) for r in recs}
    df["nb_pass"] = [neighbours(r, okd) for r in recs]
    df["nb_pass_nodd"] = [neighbours(r, okn) for r in recs]
    df["desc"] = [Q.describe(r["fam"], r) for r in recs]
    df.to_csv(Q.OUT / "grid_real.csv", index=False)
    cols = ["desc", "n", "R", "pf", "win", "dd", "usd", "h1R", "h2R", "stress_pf", "nb_pass", "nb_pass_nodd"]
    txt = [json.dumps(summary, indent=1)]
    for fam in Q.FAMILIES:
        f = df[df.fam == fam]
        txt.append(f"\nfamily {fam}: {len(f)} settings, median PF {f.pf.median():.2f}, {int((f.R > 0).sum())} with R > 0, "
                   f"{int(f.ok.sum())} pass, {int(f.ok_nodd.sum())} pass without the drawdown rule")
        txt.append(f.sort_values("R", ascending=False).head(5)[cols].to_string(index=False))
    out = {}
    cand = df[df.ok].sort_values(["nb_pass", "dd", "R"], ascending=False)
    if len(cand):
        rule, pick = "all rules", cand.iloc[0]
    else:
        cand = df[df.ok_nodd].sort_values(["nb_pass_nodd", "dd", "R"], ascending=False)
        rule, pick = ("all rules except drawdown", cand.iloc[0]) if len(cand) else ("info-only: highest R", None)
        if pick is None:
            pick = df.sort_values("R", ascending=False).iloc[0]
    g = {**Q.FAMILIES[pick["fam"]], **Q.EXITS}
    pr = {"fam": pick["fam"]}
    for k, vals in g.items():                    # the grid's own value (keeps int / float / None as in the grid)
        pr[k] = next(v for v in vals if canon(v) == canon(pick[k]))
    fakes = [summary[f"fake{s}"]["best_R_no_dd"] for s in (1, 2, 3)]
    beats = all(f is None or pick["R"] > f for f in fakes)
    out = dict(rule=rule, pick=pr, desc=pick["desc"], build=dict(n=int(pick.n), R=float(pick.R), pf=float(pick.pf),
               dd=float(pick.dd), usd=float(pick.usd), stress_pf=float(pick.stress_pf)),
               luck=dict(best_fake_R_no_dd=fakes, pick_beats_every_fake=bool(beats)))
    txt.append(f"\nPICK ({rule}): {pick['desc']}\n  Jan-Jun: {int(pick.n)} trades, R {pick.R:+.1f}, PF {pick.pf:.2f}, "
               f"DD {pick.dd:.0%}, $1,000 -> ${pick.usd:,.0f}, stress PF {pick.stress_pf:.2f}\n  luck: best fake R "
               f"(rules except drawdown) {fakes}; beats every fake: {beats}")
    if len(cand):
        txt.append("\nTop 15 by the pick rule:\n" + cand.head(15)[cols].to_string(index=False))
    (Q.OUT / "build.txt").write_text("\n".join(txt) + "\n")
    (Q.OUT / "pick.json").write_text(json.dumps(out, indent=1, default=str))
    print("\n".join(txt))


if __name__ == "__main__":
    Q.OUT.mkdir(parents=True, exist_ok=True)
    main()
