import numpy as np, fast, events, btc_common as bc
L = fast.Lean()
tk = L.tk
mid = np.full(L.n, np.nan); i = tk['t'] - L.t0; ok = (i >= 0) & (i < L.n)
mid[i[ok]] = 0.5 * (tk['bid_last'][ok] + tk['ask_last'][ok]); fast._ffill_bfill(mid)
spr = np.full(L.n, np.nan); spr[i[ok]] = (tk['ask_last'] - tk['bid_last'])[ok]; fast._ffill_bfill(spr)
np.save('/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/mid.npy', mid.astype(np.float32) - 0)
lo = bc.ts_of('2026-01-01') - L.t0; hi = L.n - 3700
H = (5, 10, 30, 60, 120, 300, 600, 1800)
for W, X in ((5, 4), (5, 6), (10, 4), (10, 6), (30, 4), (30, 6), (30, 8), (60, 6), (60, 8), (60, 12), (120, 8), (120, 12), (300, 8), (300, 12)):
    s, d = events.bursts(L.c, L.vol, W, X, 300, lo, hi)
    v = L.vol[s]; e0 = mid[s + 2]
    sp = spr[s + 2] / v
    fw = [np.mean(d * (mid[s + 2 + h] - e0) / v) for h in H]
    fb = [np.mean(d * (L.c[s + 1 + h] - L.c[s + 1]) / v) for h in H]
    half = len(s) // 2
    fw1 = [np.mean(d[:half] * (mid[s[:half] + 2 + h] - e0[:half]) / v[:half]) for h in H]
    print(f'W{W:3d} X{X:2d} n{len(s):5d} spr/vol {np.median(sp):.2f} exness', ' '.join(f'{h}:{x:+.2f}' for h, x in zip(H, fw)), '| 1st half', ' '.join(f'{x:+.2f}' for x in fw1), '| binance', ' '.join(f'{x:+.2f}' for x in fb))
