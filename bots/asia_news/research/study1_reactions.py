"""Step 1: how do gold, Nasdaq and the currency's pair move after each Asian high-impact release (Jan-Jun 2026)?
Moves are measured from the earliest tradable price (open of the minute after the release minute) and expressed in
multiples of the protocol's base spread COST[symbol]; pair moves are signed so that + = the released currency stronger."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
from common import L, SYMS, releases  # noqa: E402

pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500); pd.set_option("display.max_columns", 50)
H = [1, 5, 15, 30, 60, 120, 240]


def at_close(m, t):
    """close of the last bar that starts at or before t (asof)."""
    i = m.index.searchsorted(t, side="right") - 1
    return m.close.iloc[i], m.index[i]


def reaction(m, t0, cost):
    one = pd.Timedelta(minutes=1)
    out = {}
    if t0 not in m.index:
        out["gap0"] = 1
    pre, tp = at_close(m, t0 - one)
    e_i = m.index.searchsorted(t0 + one)
    te = m.index[e_i]
    entry = m.open.iloc[e_i]
    out["entry_delay"] = (te - (t0 + one)) / one
    out["r0"] = (entry - pre) / cost                   # pre-release close -> entry open (release-minute move)
    p30, _ = at_close(m, t0 - 30 * one)
    out["pre30"] = (pre - p30) / cost
    for h in H:
        px, _ = at_close(m, te + (h - 1) * one)
        out[f"m{h}"] = (px - entry) / cost
    w = m.loc[te: te + 239 * one]
    out["mfe240"] = (w.high.max() - entry) / cost
    out["mae240"] = (w.low.min() - entry) / cost
    # pre-release volatility: mean M1 range over previous 120 minutes, in cost units
    pv = m.loc[t0 - 120 * one: t0 - one]
    out["vol120"] = (pv.high - pv.low).mean() / cost
    return out


def main():
    rel = releases(L.calendar_train())
    px = {s: L.prices_train(s) for s in SYMS}
    rows = []
    for _, r in rel.iterrows():
        bw = [f["bw"] for f in r.figs]
        score = sum(1 if b == 1 else -1 if b == 2 else 0 for b in bw)
        base = dict(time=r.time, ccy=r.ccy, kind=r.kind, nfig=len(bw), bw="".join(str(b) for b in bw), ffscore=score,
                    figs="; ".join(f"{f['name'][:14]} {f['actual']:g}/{f['forecast']:g}/{f['previous']:g}" for f in r.figs))
        for s in SYMS:
            rr = reaction(px[s], r.time, L.COST[s])
            sign = 1
            if s in ("AUDUSD", "NZDUSD", "USDJPY"):
                pair, sign = L.PAIR[r.ccy]
                if s != pair:
                    continue
                s = "PAIR"
            for k, v in rr.items():
                base[f"{s}_{k}"] = v * sign if k not in ("entry_delay", "gap0", "vol120") else v
        rows.append(base)
    df = pd.DataFrame(rows)
    out = Path(__file__).parent / "reactions.csv"
    df.to_csv(out, index=False)
    for s in ["PAIR", "XAUUSD", "NAS100"]:
        cols = ["time", "ccy", "kind", "bw", "ffscore"] + [f"{s}_{k}" for k in
                ["entry_delay", "vol120", "pre30", "r0", "m1", "m5", "m15", "m30", "m60", "m120", "m240", "mfe240", "mae240"]]
        print(f"\n=== {s} (cost units; PAIR signed + = released currency stronger) ===")
        print(df[cols].round(1).to_string(index=False))
    print(df[["time", "ccy", "figs"]].to_string(index=False))


if __name__ == "__main__":
    main()
