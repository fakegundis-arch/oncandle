"""Step 1: how does NAS100 move around the 32 Asian high-impact releases of Jan-Jun 2026, compared with the same clock
time on days without a release?  Moves in units of ATR(24 x H1) before the time (the stop unit) and in points.

usage: python study_reactions.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import common as C  # noqa: E402

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500); pd.set_option("display.max_columns", 60)
HZ = [1, 2, 3, 5, 10, 15, 30, 60, 120, 240, 360]


def measure(t: pd.Timestamp) -> dict | None:
    """Moves around time t (a release minute or a placebo minute)."""
    m = C.px()
    idx = m.index
    i0 = idx.searchsorted(t)                     # release-minute bar (or first bar after if closed)
    if i0 >= len(idx) or idx[i0] != t:
        return None                              # market not quoting at the release minute
    pre = m.close.iat[i0 - 1]
    if (t - idx[i0 - 1]) > pd.Timedelta(minutes=5):
        return None
    a = C.atr_h1(t)
    o, h, l, c = m.open.to_numpy(), m.high.to_numpy(), m.low.to_numpy(), m.close.to_numpy()
    e = i0 + 1                                   # earliest entry bar (open)
    out = dict(t=t, atr=a, pre=pre)
    out["r0"] = (o[e] - pre) / a                 # release-minute move (not capturable)
    out["rng0"] = (h[i0] - l[i0]) / a            # release-minute range
    # pre-release context
    for k in (15, 60, 240):
        j = idx.searchsorted(t - pd.Timedelta(minutes=k))
        out[f"pre{k}"] = (pre - o[j]) / a
    # range of the 30 minutes before
    w = slice(idx.searchsorted(t - pd.Timedelta(minutes=30)), i0)
    out["prerng30"] = (h[w].max() - l[w].min()) / a
    for hz in HZ:
        j = idx.searchsorted(t + pd.Timedelta(minutes=hz)) - 1      # close of the bar ending at t + hz
        out[f"c{hz}"] = (c[j] - pre) / a          # from the pre-release close
        out[f"e{hz}"] = (c[j] - o[e]) / a if hz > 1 else 0.0   # from the earliest entry
    # first-N-minute ranges (from the release minute, inclusive)
    for n in (1, 3, 5, 15, 30, 60):
        j = idx.searchsorted(t + pd.Timedelta(minutes=n))
        out[f"rng{n}"] = (h[i0:j].max() - l[i0:j].min()) / a
    return out


def main():
    rt = C.rel_table()
    rows = []
    for r in rt.itertuples():
        x = measure(r.time)
        if x is None:
            print("not quoting:", r.time, r.ccy, r.kind)
            continue
        x.update(ccy=r.ccy, kind=r.kind, bias=r.bias, score=r.score, agree=r.agree)
        rows.append(x)
    N = pd.DataFrame(rows)
    # placebo: same clock times on other weekdays without any release that day
    rel_days = {pd.Timestamp(t).date() for t in rt.time}
    P = []
    for r in rt.itertuples():
        for pt in C.placebo_times([r.time], exclude_days=rel_days):
            x = measure(pt)
            if x is not None:
                x["of"] = r.time
                P.append(x)
    P = pd.DataFrame(P)
    out = Path(__file__).parent / "out"
    out.mkdir(exist_ok=True)
    N.to_csv(out / "news_reactions.csv", index=False)
    P.to_csv(out / "placebo_reactions.csv", index=False)
    print(f"news events quoting: {len(N)}; placebo samples: {len(P)}")

    # 1. volatility: |move| at news vs placebo (percentile of each event within its own clock-time placebo set)
    cols = ["rng0", "r0", "c1", "c3", "c5", "c15", "c30", "c60", "c120", "c240", "rng5", "rng15", "rng60"]
    pct = []
    for r in N.itertuples():
        p = P[P["of"] == r.t]
        d = {"t": r.t, "ccy": r.ccy, "kind": r.kind}
        for k in cols:
            d[k] = (np.abs(p[k]) < abs(getattr(r, k))).mean()
        pct.append(d)
    pct = pd.DataFrame(pct)
    print("\n=== |move| percentile of each release within its same-clock-time placebo days (0.5 = ordinary) ===")
    print(pct.round(2).to_string(index=False))
    print("\nmean percentile:", pct[cols].mean().round(2).to_dict())
    print("by kind:\n", pct.groupby("kind")[cols].mean().round(2))
    print("by ccy:\n", pct.groupby("ccy")[cols].mean().round(2))
    print("\nmedian |move| in ATR, news vs placebo:")
    print(pd.DataFrame({"news": N[cols].abs().median(), "placebo": P[cols].abs().median(),
                        "news_mean": N[cols].abs().mean(), "placebo_mean": P[cols].abs().mean()}).round(3).T)

    # 2. direction: signed by the news (nasdaq map AUD/NZD +1, JPY -1)
    mp = {"AUD": 1, "NZD": 1, "JPY": -1, "CNY": 1}
    N["nd"] = N.bias * N.ccy.map(mp)
    S = N[N.nd != 0]
    ecols = ["r0", "c1", "c5", "c15", "c30", "c60", "c120", "c240", "c360"]
    fcols = ["e5", "e15", "e30", "e60", "e120", "e240", "e360"]
    print(f"\n=== signed by the news direction (n={len(S)}) - moves from the pre-release close (c) and from the earliest entry (e), ATR ===")
    sg = S[ecols + fcols].mul(S.nd, axis=0)
    print(pd.DataFrame({"mean": sg.mean(), "median": sg.median(), "pos%": (sg > 0).mean(), "t": sg.mean() / sg.std() * np.sqrt(len(sg))}).round(2).T)
    for c_ in ("AUD", "NZD"):
        q = S[S.ccy == c_]
        g = q[ecols + fcols].mul(q.nd, axis=0)
        print(f"  {c_} n={len(q)} mean:", g.mean().round(2).to_dict())
    big = S[S.score.abs() >= 2]
    g = big[ecols + fcols].mul(big.nd, axis=0)
    print(f"  |score|>=2 n={len(big)} mean:", g.mean().round(2).to_dict())
    ag = S[S.agree == 1]
    g = ag[ecols + fcols].mul(ag.nd, axis=0)
    print(f"  all figures agree n={len(ag)} mean:", g.mean().round(2).to_dict())

    # 3. direction: signed by Nasdaq's own release-minute move (continuation vs reversal)
    print("\n=== signed by the sign of the release-minute move r0 (momentum > 0, reversal < 0), ATR ===")
    for lab, D, base in (("news", N, "r0"), ("placebo", P, "r0")):
        s = np.sign(D[base])
        g = D[fcols].mul(s, axis=0)
        print(f"{lab:8s} n={len(D)}", {k: f"{g[k].mean():+.3f} ({(g[k] > 0).mean():.0%})" for k in fcols})
    # signed by the first 5 / 15 minute move (from pre-release close)
    for base, fw in (("c5", ["e15", "e30", "e60", "e120", "e240"]), ("c15", ["e30", "e60", "e120", "e240", "e360"])):
        for lab, D in (("news", N), ("placebo", P)):
            s = np.sign(D[base])
            # continuation measured from the end of the base window
            k0 = "e" + base[1:]
            g = D[fw].sub(D[k0], axis=0).mul(s, axis=0)
            print(f"signed by {base:4s} {lab:8s}", {k: f"{g[k].mean():+.3f} ({(g[k] > 0).mean():.0%})" for k in fw})

    # 4. per-event table
    show = ["t", "ccy", "kind", "score", "nd", "atr", "pre60", "r0", "rng0", "c5", "c15", "c60", "c240", "c360", "rng15"]
    print("\n=== per release (ATR units) ===")
    print(N[show].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
