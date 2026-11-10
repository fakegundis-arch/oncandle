"""Version 2 of the 4newgolds Telegram bot: validation, Jan-May grid + luck check, pick, one Jun-Nov 9 test.
usage: cd <repo> && PYTHONDONTWRITEBYTECODE=1 python3 -I scripts/goldbot_backtest/v2_build.py <validate|grid|test>"""
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v2_lab as V  # noqa: E402

R = V.R
R.END = "2026-11-10"
OUT = R.OUT / "v2"
TS = lambda s: int(pd.Timestamp(s, tz="UTC").timestamp())
COMPS = [k for k in V.COMP if V.COMP[k] is not None]


def setup(a, b):
    cfg = R.load_config(str(R.BOT / "config.yaml"))
    posts = R.load_posts()
    ticks = {s: R.load_ticks(s) for s in (cfg.symbol, cfg.companion.symbol)}
    windows = R.blackout_windows(cfg.news_blackout)
    c = V.candidates(cfg, a, b, posts)
    return cfg, ticks, windows, c


def precompute(c, det, ticks, cfg, stress):
    g = V.outcomes(c, det, ticks[cfg.symbol], cfg.symbol, V.GLIST, stress)
    k = V.outcomes(c, det, ticks[cfg.companion.symbol], cfg.companion.symbol, [V.COMP[x] for x in COMPS], stress,
                   comp_mode=True)
    return g, k


def settings():
    for ch, tr, bo, gi, cp in itertools.product(V.CHANNELS, V.TRIGGERS, V.BLACKOUT, range(len(V.GLIST)), V.COMP):
        yield dict(channels=ch, trigger=tr, blackout=bo, **V.GLIST[gi], comp=cp), gi


def evaluate(c, det, flags, pre, pre_s, a, b):
    shut, nshut, blk = flags
    split, end = TS(V.SPLIT), TS(b)
    (gc, gp, gf), (kc, kp, kf) = pre
    (gcs, gps, gfs), (kcs, kps, kfs) = pre_s
    chm = {k: c.ch.isin(v).to_numpy() for k, v in V.CHANNELS.items()}
    trm = {t: V.trig_mask(c, t) for t in V.TRIGGERS}
    key = c.key_id.to_numpy().astype(np.int64)
    rows = []
    for s, gi in settings():
        use = chm[s["channels"]] & trm[s["trigger"]]
        ci = COMPS.index(s["comp"]) if s["comp"] != "off" else 0
        uc = s["comp"] != "off"
        bo = s["blackout"] == "on"
        r = V.run_setting(det, use, blk, shut, nshut, key, gc[:, gi], gp[:, gi], gf[:, gi], kc[:, ci], kp[:, ci],
                          kf[:, ci], uc, bo, split, end)
        rs = V.run_setting(det, use, blk, shut, nshut, key, gcs[:, gi], gps[:, gi], gfs[:, gi], kcs[:, ci], kps[:, ci],
                           kfs[:, ci], uc, bo, split, end)
        tot, g, n, a1, a2, npos, gw, gl, dd = r
        rows.append(dict(s, pnl=tot, gold=g, nasdaq=n, h1=a1, h2=a2, positions=npos, pf=gw / gl if gl > 0 else 99.0,
                         dd=dd, stress_pnl=rs[0], stress_pf=rs[6] / rs[7] if rs[7] > 0 else 99.0))
    df = pd.DataFrame(rows)
    df["ok"] = (df.positions >= 60) & (df.h1 > 0) & (df.h2 > 0) & (df.pf >= 1.3) & (df.stress_pf >= 1.1) & (-df.dd < df.pnl)
    return df


def validate():
    a, b = V.BUILD
    cfg, ticks, windows, c = setup(a, b)
    det, shut, nshut, blk = V.market_flags(c, ticks[cfg.symbol], ticks[cfg.companion.symbol], windows, 2)
    gi = next(i for i, g in enumerate(V.GLIST) if all(g[k] == V.V1[k] for k in V.GOLD))
    g = V.outcomes(c, det, ticks[cfg.symbol], cfg.symbol, [V.GLIST[gi]], False)
    k = V.outcomes(c, det, ticks[cfg.companion.symbol], cfg.companion.symbol, [V.COMP["v1"]], False, comp_mode=True)
    use = V.trig_mask(c, "v1")
    r = V.run_setting(det, use, blk, shut, nshut, c.key_id.to_numpy().astype(np.int64), g[0][:, 0], g[1][:, 0],
                      g[2][:, 0], k[0][:, 0], k[1][:, 0], k[2][:, 0], True, True, TS(V.SPLIT), TS(b))
    t = pd.read_csv(R.OUT / "trades_base.csv")
    t = t[t.post_ts < TS(b)]
    ref_g, ref_n = t[t.symbol.str.startswith("XAU")].usd.sum(), t[t.symbol.str.startswith("USTEC")].usd.sum()
    print(f"candidates Jan-May: {len(c)}; version-1 setting in the new engine: total {r[0]:.2f} (gold {r[1]:.2f}, "
          f"nasdaq {r[2]:.2f}), positions {r[5]}")
    print(f"replay.py base, posts Jan-May: total {ref_g + ref_n:.2f} (gold {ref_g:.2f}, nasdaq {ref_n:.2f}), positions "
          f"{int(t.side.notna().sum())}")


def neighbours(row, okset):
    out = []
    for k, vals in V.KNOBS.items():
        i = vals.index(row[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                out.append(tuple(str({**row, k: vals[j]}[q]) for q in V.KNOBS) in okset)
    return float(np.mean(out))


def grid():
    OUT.mkdir(parents=True, exist_ok=True)
    a, b = V.BUILD
    t0 = time.time()
    cfg, ticks, windows, c = setup(a, b)
    gold, nas = ticks[cfg.symbol], ticks[cfg.companion.symbol]
    summary = {}
    for tag in ["real", "fake1", "fake2", "fake3"]:
        cc = c.copy()
        if tag != "real":
            rng = np.random.default_rng(int(tag[-1]))
            lo, hi = TS(a), TS(b)
            sh = rng.integers(86400, 14 * 86400, len(cc)) * rng.choice([-1, 1], len(cc))
            cc["ts"] = (cc.ts - lo + sh) % (hi - lo) + lo
            cc = cc.sort_values("ts").reset_index(drop=True)
        det, shut, nshut, blk = V.market_flags(cc, gold, nas, windows, 2)
        pre = precompute(cc, det, ticks, cfg, False)
        pre_s = precompute(cc, det, ticks, cfg, True)
        df = evaluate(cc, det, (shut, nshut, blk), pre, pre_s, a, b)
        df.to_csv(OUT / f"grid_{tag}.csv", index=False)
        summary[tag] = dict(settings=len(df), passing=int(df.ok.sum()), best_pnl_passing=float(df[df.ok].pnl.max()) if df.ok.any() else None,
                            best_pnl_any=float(df.pnl.max()))
        print(tag, summary[tag], f"{time.time() - t0:.0f}s", flush=True)
    df = pd.read_csv(OUT / "grid_real.csv")
    for k in ("offset", "sl", "tp"):
        df[k] = df[k].astype(float)
    recs = df.to_dict("records")
    okset = {tuple(str(r[q]) for q in V.KNOBS) for r in recs if r["ok"]}
    cand = df[df.ok].copy()
    rule = "all rules"
    if not len(cand):
        rule, cand = "info-only: highest P&L", df.sort_values("pnl", ascending=False).head(1).copy()
        cand["nb"] = 0.0
    else:
        cand["nb"] = [neighbours(r, okset) for r in cand.to_dict("records")]
        cand = cand.sort_values(["nb", "pnl"], ascending=False)
    pick = cand.iloc[0]
    fakes = [summary[f"fake{s}"]["best_pnl_passing"] for s in (1, 2, 3)]
    beats = all(f is None or pick.pnl > f for f in fakes)
    v1 = df[np.logical_and.reduce([df[k].astype(str) == str(v) for k, v in V.V1.items()])].iloc[0]
    cols = list(V.KNOBS) + ["pnl", "gold", "nasdaq", "h1", "h2", "positions", "pf", "dd", "stress_pnl", "stress_pf"]
    txt = [json.dumps(summary, indent=1),
           "version 1 in this grid (Jan-May): " + ", ".join(f"{k} {v1[k]:.2f}" for k in cols[10:]),
           f"PICK ({rule}): " + ", ".join(f"{k}={pick[k]}" for k in V.KNOBS),
           "  Jan-May: " + ", ".join(f"{k} {pick[k]:.2f}" for k in cols[10:]) + f", passing neighbours {pick.nb:.2f}",
           f"  luck: best fake P&L meeting the rules {fakes}; pick beats every fake: {beats}",
           f"\n{int(df.ok.sum())} passing; top 20 by the pick rule:\n" + cand.head(20)[cols + ["nb"]].round(2).to_string(index=False)]
    (OUT / "build.txt").write_text("\n".join(txt) + "\n")
    pk = {k: (pick[k].item() if hasattr(pick[k], "item") else pick[k]) for k in V.KNOBS}
    (OUT / "pick.json").write_text(json.dumps(dict(rule=rule, pick=pk, build={k: float(pick[k]) for k in cols[10:]},
                                                   luck=dict(best_fake=fakes, beats=bool(beats))), indent=1))
    print("\n".join(txt))


def test():
    f = OUT / "test.json"
    if f.exists():
        raise SystemExit("already run once")
    pick = json.loads((OUT / "pick.json").read_text())["pick"]
    a, b = V.TEST
    cfg, ticks, windows, c = setup(a, b)
    det, shut, nshut, blk = V.market_flags(c, ticks[cfg.symbol], ticks[cfg.companion.symbol], windows, 2)
    res = {}
    for name, s in (("version2", pick), ("version1", V.V1)):
        gi = next(i for i, g in enumerate(V.GLIST) if all(float(g[k]) == float(s[k]) if k in ("offset", "sl", "tp") else g[k] == s[k] for k in V.GOLD))
        out = {}
        for stress in (False, True):
            g = V.outcomes(c, det, ticks[cfg.symbol], cfg.symbol, [V.GLIST[gi]], stress)
            comp = s["comp"]
            k = V.outcomes(c, det, ticks[cfg.companion.symbol], cfg.companion.symbol, [V.COMP[comp or "v1"] or V.COMP["v1"]], stress, comp_mode=True)
            use = c.ch.isin(V.CHANNELS[s["channels"]]).to_numpy() & V.trig_mask(c, s["trigger"])
            r = V.run_setting(det, use, blk, shut, nshut, c.key_id.to_numpy().astype(np.int64), g[0][:, 0], g[1][:, 0], g[2][:, 0],
                              k[0][:, 0], k[1][:, 0], k[2][:, 0], comp != "off", s["blackout"] == "on", TS("2026-09-01"), TS(b))
            out["stress" if stress else "normal"] = dict(pnl=r[0], gold=r[1], nasdaq=r[2], jun_aug=r[3], sep_nov=r[4], positions=int(r[5]),
                                                          pf=r[6] / r[7] if r[7] > 0 else 99.0, max_drawdown=r[8])
        res[name] = dict(setting=s, **out)
        n = out["normal"]
        print(f"{name}: Jun 1 - Nov 9: P&L {n['pnl']:+.2f} (gold {n['gold']:+.2f}, nasdaq {n['nasdaq']:+.2f}), positions {n['positions']}, "
              f"PF {n['pf']:.2f}, worst drawdown {n['max_drawdown']:.2f} | Jun-Aug {n['jun_aug']:+.2f}, Sep-Nov {n['sep_nov']:+.2f} | "
              f"stress P&L {out['stress']['pnl']:+.2f} PF {out['stress']['pf']:.2f}")
    f.write_text(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    {"validate": validate, "grid": grid, "test": test}[sys.argv[1]]()
