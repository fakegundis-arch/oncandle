"""Wide search over entry styles x filters x exits, proxy = sum log(1 + 0.1 R) on the search period,
then the exact account (numba copy of common.account) for the finalists on search and check periods.
usage: python search.py <inst> <seed>"""
import sys, time
from lab import *
from outcomes import styles, DLM, LS, SDA, BT, TPS, HOLDS

T_SEARCH0 = int(pd.Timestamp('2025-01-01', tz='UTC').timestamp())
T_H2 = int(pd.Timestamp('2026-01-01', tz='UTC').timestamp())
T_CHECK = int(pd.Timestamp('2026-05-01', tz='UTC').timestamp())
T_END = int(pd.Timestamp('2026-07-01', tz='UTC').timestamp())
ZT = [3, 4, 5, 6, 8, 10]
NEX = len(SDA) * len(BT) * len(TPS) * len(HOLDS)


def exit_desc(x):
    a, b, q, h = np.unravel_index(x, (len(SDA), len(BT), len(TPS), len(HOLDS)))
    return dict(sda=float(SDA[a]), be=BT[b][0], trail=BT[b][1], tp=float(TPS[q]), hold=int(HOLDS[h]))


def filter_masks(ev, idx, zabs, zoth, burst, d_other_sign=None):
    """list of (desc, mask over idx)"""
    fj = ev.fj.to_numpy()[idx]; wb = ev.wb.to_numpy()[idx]
    echo = (fj & ev.wb_prev120.to_numpy()[idx]) | (wb & ev.fj_prev120.to_numpy()[idx])
    bang = ev.bang.to_numpy()[idx]; mac = ev.macro.to_numpy()[idx]
    since = ev.usdh_since.to_numpy()[idx]; until = ev.usdh_until.to_numpy()[idx]
    near = (since <= 1800) | (until <= 300)
    chs = {'any': np.ones(len(idx), bool), 'FJ': fj, 'WB': wb, 'echo': echo}
    out = []
    for zt in ZT:
        mz = zabs >= zt
        for cn, cm in chs.items():
            for bn in (0, 1):
                mb = bang if bn else True
                if bn and cn == 'WB':
                    continue
                for mn in (0, 1):
                    mm = ~mac if mn else True
                    for cal in ('any', 'far', 'near'):
                        mc = True if cal == 'any' else (~near if cal == 'far' else near)
                        for bu in (0, 1):
                            mbu = burst >= 2 if bu else True
                            for co in (0, 1):
                                mco = zoth >= 2 if co else True
                                m = mz & cm & mb & mm & mc & mbu & mco
                                out.append(((zt, cn, bn, mn, cal, bu, co), m))
    return out


def run(inst, seed, topk=4000, verbose=True, randdir=0):
    t0 = time.time()
    other = 'nasdaq' if inst == 'gold' else 'gold'
    base = f'cache/out_{inst}_{seed}'
    R = np.load(base + '_R.npy', mmap_mode='r'); X = np.load(base + '_X.npy', mmap_mode='r')
    U = pd.read_pickle(base + '_U.pkl'); Fz = dict(np.load(base + '_F.npz'))
    Fo = dict(np.load(f'cache/out_{other}_{seed}_F.npz'))
    ev = pd.read_pickle(f'cache/ev_{seed}.pkl')
    ST = styles()
    style_arr = U['style'].to_numpy()
    results = []
    for si, (kind, dl, k, T) in enumerate(ST):
        rows = np.flatnonzero(style_arr == si)
        Us = U.iloc[rows]
        half = len(rows) // 2
        r_up, r_dn = rows[:half], rows[half:]          # d=+1 block then d=-1 block (same event order)
        e = Us.ev.to_numpy()[:half]
        z = Fz[f'z{dl}'][e]                              # E x nL
        zo = Fo[f'z{dl}'][e]
        burst = Fz['burst'][e, list(__import__('events').DL).index(dl)]
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
                trig = ets >= 0
                ins = trig & (ets >= T_SEARCH0) & (ets < T_CHECK)
                h1 = ins & (ets < T_H2); h2 = ins & (ets >= T_H2)
                G = np.log1p(0.1 * np.maximum(Rs, -9.9))
                fm = filter_masks(ev, e, np.abs(z[:, li]), np.abs(zo[:, li]), burst)
                M = np.stack([m for _, m in fm]).astype(np.float32)
                g1 = (M * h1) @ G; g2 = (M * h2) @ G
                n1 = (M * h1).sum(1); n2 = (M * h2).sum(1)
                tot = g1 + g2
                ok = ((n1 + n2) >= 20)[:, None] & (g1 > 0) & (g2 > 0)
                sc = np.where(ok, tot, -np.inf)
                # keep the best few exits per filter and the best filters
                flat = np.argpartition(-sc.ravel(), min(200, sc.size - 1))[:200]
                for fl in flat:
                    fi, xi = divmod(int(fl), NEX)
                    if not np.isfinite(sc[fi, xi]):
                        continue
                    results.append(dict(style=si, L=L, mode=mode, filt=fm[fi][0], fi=fi, exit=xi,
                                        proxy=float(tot[fi, xi]), g1=float(g1[fi, xi]), g2=float(g2[fi, xi]),
                                        n=int(n1[fi] + n2[fi])))
        if verbose:
            print(inst, seed, 'style', si, ST[si], 'done', f'{time.time()-t0:.0f}s', len(results), flush=True)
    res = pd.DataFrame(results).sort_values('proxy', ascending=False).reset_index(drop=True)
    res = res.head(topk)
    # exact account for finalists
    accs = []
    for _, rw in res.iterrows():
        tr = trades_for(U, R, X, Fz, Fo, ev, rw, randdir)
        accs.append(evaluate(tr))
    res = pd.concat([res, pd.DataFrame(accs)], axis=1)
    rd = f'r{randdir}' if randdir else ''
    res.to_pickle(f'cache/search_{inst}_{seed}{rd}.pkl')
    print(inst, seed, 'finished', f'{time.time()-t0:.0f}s', flush=True)
    return res


def trades_for(U, R, X, Fz, Fo, ev, rw, randdir=0):
    """trades (all periods) of one rule from the precomputed outcomes"""
    from events import DL
    ST = styles()
    kind, dl, k, T = ST[int(rw['style'])]
    rows = np.flatnonzero(U['style'].to_numpy() == int(rw['style']))
    half = len(rows) // 2
    e = U.ev.to_numpy()[rows[:half]]
    li = LS.index(int(rw['L']))
    z = Fz[f'z{dl}'][e, li]; zo = Fo[f'z{dl}'][e, li]
    burst = Fz['burst'][e, list(DL).index(dl)]
    fm = filter_masks(ev, e, np.abs(z), np.abs(zo), burst)
    m = fm[int(rw['fi'])][1]
    sg = np.sign(z)
    if randdir:
        sg = np.random.default_rng(randdir * 1000 + int(rw['style']) * 10 + li).choice([-1.0, 1.0], len(sg))
    d = sg * int(rw['mode'])
    r_idx = np.where(d > 0, rows[:half], rows[half:])[m]
    ets = U.entry_ts.to_numpy()[r_idx]
    keep = ets >= 0
    r_idx = r_idx[keep]
    xi = int(rw['exit'])
    rr = np.asarray(R[r_idx]).reshape(len(r_idx), NEX)[:, xi].astype(float)
    xo = np.asarray(X[r_idx]).reshape(len(r_idx), NEX)[:, xi].astype(np.int64)
    tr = pd.DataFrame(dict(ev=U.ev.to_numpy()[r_idx], entry_ts=ets[keep], exit_ts=ets[keep] + xo, r=rr,
                           dir=U.d.to_numpy()[r_idx]))
    return tr.sort_values(['entry_ts', 'exit_ts']).reset_index(drop=True)


def evaluate(tr):
    out = {}
    for nm, a, b in [('s', T_SEARCH0, T_CHECK), ('c', T_CHECK, T_END), ('h', int(pd.Timestamp('2026-01-01', tz='UTC').timestamp()), T_END)]:
        t = tr[(tr.entry_ts >= a) & (tr.entry_ts < b)]
        r = t.r.to_numpy()
        fin, dd, tk, sk = account_nb(t.entry_ts.to_numpy(np.int64), t.exit_ts.to_numpy(np.int64), r, 0.10, 1000.0, 0.30)
        gl = -r[r < 0].sum()
        out.update({f'{nm}_n': len(r), f'{nm}_R': float(r.sum()), f'{nm}_pf': float(r[r > 0].sum() / gl) if gl > 0 else 99.0,
                    f'{nm}_fin': fin, f'{nm}_dd': dd})
    return out


if __name__ == '__main__':
    run(sys.argv[1], int(sys.argv[2]), randdir=int(sys.argv[3]) if len(sys.argv) > 3 else 0)
