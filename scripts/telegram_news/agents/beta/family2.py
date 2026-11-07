"""Marginal effect of each exit parameter within one filter family (gold, follow)."""
import sys
from lab import *
from outcomes import styles, LS, SDA, BT, TPS, HOLDS
from search import filter_masks, NEX, T_SEARCH0, T_CHECK, T_END
from events import DL
inst, seed, filt = sys.argv[1], int(sys.argv[2]), eval(sys.argv[3])
mode = int(sys.argv[4]) if len(sys.argv) > 4 else 1
other = 'nasdaq' if inst == 'gold' else 'gold'
base = f'cache/out_{inst}_{seed}'
R = np.load(base + '_R.npy', mmap_mode='r')
U = pd.read_pickle(base + '_U.pkl'); Fz = dict(np.load(base + '_F.npz'))
Fo = dict(np.load(f'cache/out_{other}_{seed}_F.npz'))
ev = pd.read_pickle(f'cache/ev_{seed}.pkl')
sa = U['style'].to_numpy()
SH = (len(SDA), len(BT), len(TPS), len(HOLDS))
acc_s = []; acc_c = []; keys = []
for si, (kind, dl, k, T) in enumerate(styles()):
    rows = np.flatnonzero(sa == si); half = len(rows) // 2
    e = U.ev.to_numpy()[rows[:half]]
    z = Fz[f'z{dl}'][e]; zo = Fo[f'z{dl}'][e]; burst = Fz['burst'][e, list(DL).index(dl)]
    Rup = np.asarray(R[rows[:half]]).reshape(half, NEX).astype(np.float32)
    Rdn = np.asarray(R[rows[half:]]).reshape(half, NEX).astype(np.float32)
    eu = U.entry_ts.to_numpy()[rows[:half]]; ed = U.entry_ts.to_numpy()[rows[half:]]
    for li, L in enumerate(LS):
        sgn = np.sign(z[:, li])
        m = dict(filter_masks(ev, e, np.abs(z[:, li]), np.abs(zo[:, li]), burst))[filt]
        d = sgn * mode
        Rs = np.where((d > 0)[:, None], Rup, Rdn); ets = np.where(d > 0, eu, ed)
        ins = m & (ets >= T_SEARCH0) & (ets < T_CHECK); chk = m & (ets >= T_CHECK) & (ets < T_END)
        acc_s.append(Rs[ins].mean(0).reshape(SH)); acc_c.append(Rs[chk].mean(0).reshape(SH)); keys.append((styles()[si], L))
S = np.nanmean(np.stack(acc_s), 0); Cc = np.nanmean(np.stack(acc_c), 0)
for ax, nm, vals in [(0, 'sda', SDA), (1, 'bt', BT), (2, 'tp', TPS), (3, 'hold', HOLDS)]:
    o = tuple(a for a in range(4) if a != ax)
    print(nm, ' '.join(f'{v}: {S.mean(o)[i]:+.3f}/{Cc.mean(o)[i]:+.3f}' for i, v in enumerate(vals)))
# by style kind and L
st = np.stack(acc_s).reshape(len(keys), -1).mean(1); ct = np.stack(acc_c).reshape(len(keys), -1).mean(1)
df = pd.DataFrame(dict(k=[k for k, _ in keys], L=[l for _, l in keys], s=st, c=ct))
df['kind'] = [k[0] for k in df.k]; df['dl'] = [k[1] for k in df.k]
print(df.groupby('kind')[['s', 'c']].mean().round(3).T.to_string())
print(df.groupby('L')[['s', 'c']].mean().round(3).T.to_string())
print(df.groupby('dl')[['s', 'c']].mean().round(3).T.to_string())
