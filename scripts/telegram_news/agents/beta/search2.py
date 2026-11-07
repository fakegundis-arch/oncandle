"""Robust selection: score each (style, L, mode, filter) family by a neighbourhood-smoothed proxy over the exit grid,
so a single sharp exit peak cannot win.  usage: python search2.py <inst> <seed> [randdir]"""
import sys, time
from lab import *
from outcomes import styles, LS, SDA, BT, TPS, HOLDS
from search import filter_masks, trades_for, evaluate, NEX, T_SEARCH0, T_H2, T_CHECK
from events import DL

SH = (len(SDA), len(BT), len(TPS), len(HOLDS))


def smooth(P):
    """P: F x NEX -> mean over the 3x1x3x3 neighbourhood (edges: nearest), bt not smoothed"""
    Q = P.reshape((P.shape[0],) + SH)
    for ax in (1, 3, 4):
        pad = [(0, 0)] * Q.ndim; pad[ax] = (1, 1)
        Z = np.pad(Q, pad, mode='edge')
        n = Q.shape[ax]
        Q = (np.take(Z, range(0, n), axis=ax) + np.take(Z, range(1, n + 1), axis=ax) + np.take(Z, range(2, n + 2), axis=ax)) / 3
    return Q.reshape(P.shape[0], NEX)


def run(inst, seed, randdir=0, topk=300):
    t0 = time.time()
    other = 'nasdaq' if inst == 'gold' else 'gold'
    base = f'cache/out_{inst}_{seed}'
    R = np.load(base + '_R.npy', mmap_mode='r'); X = np.load(base + '_X.npy', mmap_mode='r')
    U = pd.read_pickle(base + '_U.pkl'); Fz = dict(np.load(base + '_F.npz'))
    Fo = dict(np.load(f'cache/out_{other}_{seed}_F.npz'))
    ev = pd.read_pickle(f'cache/ev_{seed}.pkl')
    ST = styles()
    style_arr = U['style'].to_numpy()
    res = []
    ncomb = 0
    for si, (kind, dl, k, T) in enumerate(ST):
        rows = np.flatnonzero(style_arr == si)
        half = len(rows) // 2
        r_up, r_dn = rows[:half], rows[half:]
        e = U.ev.to_numpy()[r_up]
        z = Fz[f'z{dl}'][e]; zo = Fo[f'z{dl}'][e]
        burst = Fz['burst'][e, list(DL).index(dl)]
        Rup = np.asarray(R[r_up]).reshape(half, NEX).astype(np.float32)
        Rdn = np.asarray(R[r_dn]).reshape(half, NEX).astype(np.float32)
        ets_up = U.entry_ts.to_numpy()[r_up]; ets_dn = U.entry_ts.to_numpy()[r_dn]
        for li, L in enumerate(LS):
            sgn = np.sign(z[:, li])
            if randdir:
                sgn = np.random.default_rng(randdir * 1000 + si * 10 + li).choice([-1.0, 1.0], len(sgn))
            for mode in (1, -1):
                d = sgn * mode
                Rs = np.where((d > 0)[:, None], Rup, Rdn)
                ets = np.where(d > 0, ets_up, ets_dn)
                ins = (ets >= T_SEARCH0) & (ets < T_CHECK)
                h1 = ins & (ets < T_H2); h2 = ins & (ets >= T_H2)
                G = np.log1p(0.1 * np.maximum(Rs, -9.9))
                fm = filter_masks(ev, e, np.abs(z[:, li]), np.abs(zo[:, li]), burst)
                M = np.stack([m for _, m in fm]).astype(np.float32)
                g1 = (M * h1) @ G; g2 = (M * h2) @ G
                n = (M * ins).sum(1)
                ncomb += g1.size
                s1, s2 = smooth(g1), smooth(g2)
                sc = np.where((n >= 30)[:, None] & (s1 > 0) & (s2 > 0), s1 + s2, -np.inf)
                bx = sc.argmax(1)
                bs = sc[np.arange(len(sc)), bx]
                for fi in np.flatnonzero(np.isfinite(bs)):
                    res.append(dict(style=si, L=L, mode=mode, filt=fm[fi][0], fi=fi, exit=int(bx[fi]), smooth=float(bs[fi]),
                                    proxy=float(g1[fi, bx[fi]] + g2[fi, bx[fi]]), n=int(n[fi]),
                                    fam_mean=float((g1[fi] + g2[fi]).mean())))
    res = pd.DataFrame(res).sort_values('smooth', ascending=False).reset_index(drop=True).head(topk)
    accs = [evaluate(trades_for(U, R, X, Fz, Fo, ev, rw, randdir)) for _, rw in res.iterrows()]
    res = pd.concat([res, pd.DataFrame(accs)], axis=1)
    rd = f'r{randdir}' if randdir else ''
    res.to_pickle(f'cache/robust_{inst}_{seed}{rd}.pkl')
    print(inst, seed, rd, 'combos', ncomb, 'finished', f'{time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 0)
