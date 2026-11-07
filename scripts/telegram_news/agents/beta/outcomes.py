"""Precompute per-unit trade outcomes for the wide search.
unit = (event, entry style); for each direction (+1/-1) and exit combo we store R (float16) and the exit offset (uint16 s).
usage: python outcomes.py <inst> <seed>   (seed 0 = real post times; seed>0 = posts moved to random other times)"""
import sys, time
from lab import *
from events import DL, LB, post_events, inst_features

DLM = [0, 3, 12, 30, 60, 120, 300]           # market delays (s after post + 2)
LS = [10, 30, 60, 120, 300]                    # lookbacks for the move
LSI = [list(LB).index(L) for L in LS]
PEND_DL = [0, 12]
PEND_K = [0.5, 1.0, 2.0]
STOP_T = [60, 300, 900]
LIM_T = [120, 600, 1800]
SDA = np.array([1.5, 2.0, 3.0, 4.5, 7.0])
BT = [(-1.0, -1.0), (1.0, -1.0), (-1.0, 1.5), (-1.0, 3.0), (1.0, 1.0), (2.0, 2.0)]
TPS = np.array([1.5, 3.0, 5.0, 10.0, np.inf])
HOLDS = np.array([600, 1800, 3600, 7200, 14400], np.int64)
ZMIN = 3.0


def styles():
    st = [('M', dl, 0.0, 0) for dl in DLM]
    for dl in PEND_DL:
        for k in PEND_K:
            st += [('S', dl, k, T) for T in STOP_T]
            st += [('P', dl, k, T) for T in LIM_T]
    return st


def shifted_events(seed):
    ev = post_events()
    if seed == 0:
        return ev
    rng = np.random.default_rng(seed)
    ev = ev.copy()
    ev['ts'] = ev.ts + rng.integers(-14 * 86400, 14 * 86400, len(ev))
    ev = ev.sort_values('ts').drop_duplicates('ts').reset_index(drop=True)
    ts = ev.ts.to_numpy()
    ev['prev_gap'] = np.r_[10**6, np.diff(ts)]
    ev['n60'] = np.searchsorted(ts, ts) - np.searchsorted(ts, ts - 60)
    ev['n600'] = np.searchsorted(ts, ts) - np.searchsorted(ts, ts - 600)
    cal = C.load_calendar(D)
    cal['ts'] = cal.time_utc.astype('datetime64[s]').astype('int64')
    for nm, msk in [('usdh', (cal.currency == 'USD') & (cal.impact == 'high')), ('anyh', cal.impact == 'high')]:
        ct = np.sort(cal.ts[msk].unique())
        i = np.searchsorted(ct, ts, side='right') - 1
        ev[f'{nm}_since'] = np.where(i >= 0, ts - ct[np.maximum(i, 0)], 10**7)
        ev[f'{nm}_until'] = np.where(i + 1 < len(ct), ct[np.minimum(i + 1, len(ct) - 1)] - ts, 10**7)
    ev['hour'] = (ts % 86400) // 3600
    ev['dow'] = pd.to_datetime(ts, unit='s').dayofweek
    ev['month'] = pd.to_datetime(ts, unit='s').strftime('%Y-%m')
    # echo flags: other channel within the previous 120 s (among the moved posts)
    for ch, col in [('fj', 'fj_prev120'), ('wb', 'wb_prev120')]:
        c = np.sort(ts[ev[ch].to_numpy()])
        ev[col] = (np.searchsorted(c, ts) - np.searchsorted(c, ts - 120)) > 0
    return ev


@nb.njit(cache=True, parallel=True)
def exits_batch(t, bf, bmin, bmax, bl, af, amin, amax, al, gaps, J, FILL, DIR, S60, sda, bes, trs, tps, holds, R, XO):
    U = len(J)
    nq = len(tps); nh = len(holds)
    for u in nb.prange(U):
        j = J[u]
        if j < 0:
            continue
        o_r = np.zeros((nq, nh)); o_x = np.zeros((nq, nh), np.int64)
        for a in range(len(sda)):
            for b in range(len(bes)):
                exit_multi(t, bf, bmin, bmax, bl, af, amin, amax, al, gaps, j, FILL[u], DIR[u], sda[a] * S60[u],
                           bes[b], trs[b], tps, holds, False, o_r, o_x)
                for q in range(nq):
                    for h in range(nh):
                        R[u, a, b, q, h] = o_r[q, h]
                        off = t[min(o_x[q, h], len(t) - 1)] - t[j]
                        XO[u, a, b, q, h] = min(off, 65535)


@nb.njit(cache=True, parallel=True)
def pending_batch(t, bf, bmin, bmax, af, amin, amax, gaps, I0, PX, DIR, kind, expire):
    U = len(I0)
    J = np.full(U, -1, np.int64); F = np.zeros(U)
    for u in nb.prange(U):
        if I0[u] < 0:
            continue
        if DIR[u] > 0:
            x, dd, fl = pending_scan(t, bf, bmin, bmax, af, amin, amax, gaps, I0[u], PX[u], np.nan, kind, expire, False)
        else:
            x, dd, fl = pending_scan(t, bf, bmin, bmax, af, amin, amax, gaps, I0[u], np.nan, PX[u], kind, expire, False)
        if x >= 0:
            J[u] = x; F[u] = fl
    return J, F


def build(inst, seed):
    t0 = time.time()
    ev = shifted_events(seed)
    I = Inst(inst)
    f = inst_features(I, ev.ts.to_numpy())
    sig = np.maximum(f['sig'], 0.05 * f['spbase'])
    s60 = sig * np.sqrt(60)
    ok = (f['tspan'] < 1500) & (f['open_s'] > 1200) & (f['nclose_s'] > 3600)
    # per delay: z for each L and event mask
    zs = {}
    sel = {}
    for dl in sorted(set(DLM) | set(PEND_DL)):
        di = list(DL).index(dl)
        z = np.stack([(f['pnow'][:, di] - f['ref'][:, li]) / (sig * np.sqrt(LB[li] + 1 + C.LAT + dl)) for li in LSI], 1)
        zs[dl] = z
        sel[dl] = np.flatnonzero(ok & (f['iD'][:, di] >= 0) & (np.abs(z).max(1) >= ZMIN))
    ST = styles()
    rows = []   # unit table
    J_all, F_all, D_all, S_all = [], [], [], []
    for si, (kind, dl, k, T) in enumerate(ST):
        di = list(DL).index(dl)
        e = sel[dl]
        iD = f['iD'][e, di].astype(np.int64)
        kD = f['kD'][e, di].astype(np.int64)
        for d in (1, -1):
            if kind == 'M':
                sp = I.af[iD] - I.bf[iD]
                J = iD.copy(); F = (I.af[iD] + sp) if d > 0 else (I.bf[iD] - sp)
            else:
                mid = I.mid[kD]
                if kind == 'S':
                    px = mid + d * k * s60[e]
                    J, F = pending_batch(*pargs(I), iD, px, np.full(len(e), d, np.int64), 0, T)
                else:
                    px = mid - d * k * s60[e]
                    J, F = pending_batch(*pargs(I), iD, px, np.full(len(e), d, np.int64), 1, T)
            J_all.append(J); F_all.append(F); D_all.append(np.full(len(e), d, np.int64)); S_all.append(s60[e])
            rows.append(pd.DataFrame(dict(style=si, ev=e, d=d, j=J,
                                          entry_ts=np.where(J >= 0, I.t[np.maximum(J, 0)], -1))))
    U = pd.concat(rows, ignore_index=True)
    J = np.concatenate(J_all); F = np.concatenate(F_all); Dd = np.concatenate(D_all); S = np.concatenate(S_all)
    print(inst, seed, 'units', len(U), 'triggered', (J >= 0).sum(), f'{time.time()-t0:.0f}s', flush=True)
    shp = (len(U), len(SDA), len(BT), len(TPS), len(HOLDS))
    R = np.zeros(shp, np.float32); XO = np.zeros(shp, np.int32)
    bes = np.array([b for b, _ in BT]); trs = np.array([tr for _, tr in BT])
    exits_batch(*args(I), J, F, Dd, S, SDA, bes, trs, TPS, HOLDS, R, XO)
    print(inst, seed, 'exits done', f'{time.time()-t0:.0f}s', flush=True)
    U['sd60'] = S
    out = f'cache/out_{inst}_{seed}'
    np.save(out + '_R.npy', R.astype(np.float16))
    np.save(out + '_X.npy', np.minimum(XO, 65535).astype(np.uint16))
    U.to_pickle(out + '_U.pkl')
    zz = {f'z{dl}': zs[dl] for dl in zs}
    np.savez(out + '_F.npz', ok=ok, sig=sig, burst=f['burst'], spnow=f['spnow'], **zz)
    ev.to_pickle(f'cache/ev_{seed}.pkl')
    print(inst, seed, 'saved', f'{time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    build(sys.argv[1], int(sys.argv[2]))
