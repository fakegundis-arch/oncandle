import numpy as np, pandas as pd, fast, btc_common as bc
L = fast.Lean(start='2026-01-01', end='2026-03-01')
tk = L.tk
# exness mid per second (last quote known by end of second), ffill
mid = np.full(L.n, np.nan)
i = tk['t'] - L.t0; ok = (i >= 0) & (i < L.n)
mid[i[ok]] = 0.5 * (tk['bid_last'][ok] + tk['ask_last'][ok])
fast._ffill_bfill(mid)
c = L.c
rb = np.diff(c); re = np.diff(mid)
for lag in range(-3, 8):
    if lag >= 0: a, b = rb[:len(rb) - lag], re[lag:]
    else: a, b = rb[-lag:], re[:len(re) + lag]
    print('lag', lag, round(np.corrcoef(a, b)[0, 1], 3))
print('spread median', np.median(tk['ask_last'] - tk['bid_last']))
print('exness quotes/s', ok.sum() / L.n)
# big binance moves over 5s: subsequent exness moves
vol = L.vol
for W, k in ((5, 2), (5, 3), (10, 3), (10, 4), (30, 5)):
    s = np.arange(W + 1, L.n - 120)
    mvb = (c[s - 1] - c[s - 1 - W]) / vol[s]
    idx = s[np.abs(mvb) >= k]
    # dedupe: 60 s refractory
    keep = [idx[0]]
    for x in idx[1:]:
        if x - keep[-1] >= 60: keep.append(x)
    idx = np.array(keep); d = np.sign(c[idx - 1] - c[idx - 1 - W])
    gap_e = d * (mid[idx - 1] - mid[idx - 1 - W]) / vol[idx]   # exness move in same window
    gap_b = d * (c[idx - 1] - c[idx - 1 - W]) / vol[idx]
    fut = {h: d * (mid[idx + h] - mid[idx + 1]) / vol[idx] for h in (5, 10, 30, 60, 120)}
    futb = {h: d * (c[idx + h] - c[idx + 1]) / vol[idx] for h in (5, 10, 30, 60, 120)}
    print(f'W{W} k{k} n{len(idx)} binance move {gap_b.mean():.2f} exness move {gap_e.mean():.2f} | exness fwd from s+1:',
          ' '.join(f'{h}:{v.mean():+.2f}' for h, v in fut.items()), '| binance fwd', ' '.join(f'{h}:{v.mean():+.2f}' for h, v in futb.items()))
