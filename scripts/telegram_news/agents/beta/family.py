"""Scan one filter family over all styles / lookbacks / exits: mean R per trade in search and check periods."""
import sys
from lab import *
from outcomes import styles, LS, SDA, BT, TPS, HOLDS
from search import filter_masks, NEX, T_SEARCH0, T_CHECK, T_END
from events import DL


def scan(inst, seed, filt, randdir=0, mode_list=(1, -1)):
    other = 'nasdaq' if inst == 'gold' else 'gold'
    base = f'cache/out_{inst}_{seed}'
    R = np.load(base + '_R.npy', mmap_mode='r')
    U = pd.read_pickle(base + '_U.pkl'); Fz = dict(np.load(base + '_F.npz'))
    Fo = dict(np.load(f'cache/out_{other}_{seed}_F.npz'))
    ev = pd.read_pickle(f'cache/ev_{seed}.pkl')
    out = []
    sa = U['style'].to_numpy()
    for si, (kind, dl, k, T) in enumerate(styles()):
        rows = np.flatnonzero(sa == si); half = len(rows) // 2
        e = U.ev.to_numpy()[rows[:half]]
        z = Fz[f'z{dl}'][e]; zo = Fo[f'z{dl}'][e]; burst = Fz['burst'][e, list(DL).index(dl)]
        Rup = np.asarray(R[rows[:half]]).reshape(half, NEX).astype(np.float32)
        Rdn = np.asarray(R[rows[half:]]).reshape(half, NEX).astype(np.float32)
        eu = U.entry_ts.to_numpy()[rows[:half]]; ed = U.entry_ts.to_numpy()[rows[half:]]
        for li, L in enumerate(LS):
            sgn = np.sign(z[:, li])
            if randdir:
                sgn = np.random.default_rng(randdir * 1000 + si * 10 + li).choice([-1.0, 1.0], len(sgn))
            fm = dict(filter_masks(ev, e, np.abs(z[:, li]), np.abs(zo[:, li]), burst))
            m = fm[filt]
            for mode in mode_list:
                d = sgn * mode
                Rs = np.where((d > 0)[:, None], Rup, Rdn); ets = np.where(d > 0, eu, ed)
                ins = m & (ets >= T_SEARCH0) & (ets < T_CHECK); chk = m & (ets >= T_CHECK) & (ets < T_END)
                rs = Rs[ins].mean(0) if ins.any() else np.zeros(NEX)
                rc = Rs[chk].mean(0) if chk.any() else np.zeros(NEX)
                out.append(dict(style=styles()[si], L=L, mode=mode, ns=int(ins.sum()), nc=int(chk.sum()),
                                s_mean=float(rs.mean()), c_mean=float(rc.mean()), s_pos=float((rs > 0).mean()),
                                c_pos=float((rc > 0).mean()), s_best=float(rs.max()), c_at_sbest=float(rc[rs.argmax()])))
    return pd.DataFrame(out)


if __name__ == '__main__':
    pd.set_option('display.width', 250)
    inst, seed = sys.argv[1], int(sys.argv[2]); rd = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    filt = eval(sys.argv[4]) if len(sys.argv) > 4 else (3, 'any', 0, 0, 'any', 1, 1)
    df = scan(inst, seed, filt, rd)
    print(inst, seed, rd, filt)
    for mode in (1, -1):
        q = df[df['mode'] == mode]
        print('mode', mode, 'avg over styles/L: s_mean %.3f c_mean %.3f  frac(style,L) s_mean>0 %.2f c_mean>0 %.2f, ns avg %.0f nc avg %.0f' % (
            q.s_mean.mean(), q.c_mean.mean(), (q.s_mean > 0).mean(), (q.c_mean > 0).mean(), q.ns.mean(), q.nc.mean()))
    if len(sys.argv) > 5:
        print(df[df['mode'] == 1].to_string())
