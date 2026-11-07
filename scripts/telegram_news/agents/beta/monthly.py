import sys
from lab import *
from outcomes import styles, LS, SDA, BT, TPS, HOLDS
from search import filter_masks, NEX, trades_for, evaluate
from events import DL
pd.set_option('display.width', 250)
inst, seed = 'gold', 0
base = f'cache/out_{inst}_{seed}'
R = np.load(base + '_R.npy', mmap_mode='r'); X = np.load(base + '_X.npy', mmap_mode='r')
U = pd.read_pickle(base + '_U.pkl'); Fz = dict(np.load(base + '_F.npz')); Fo = dict(np.load(f'cache/out_nasdaq_{seed}_F.npz'))
ev = pd.read_pickle(f'cache/ev_{seed}.pkl')
ST = styles()
def ex_index(sda, be, tr, tp, hold):
    a = list(SDA).index(sda); b = BT.index((be, tr)); q = list(TPS).index(tp); h = list(HOLDS).index(hold)
    return np.ravel_multi_index((a, b, q, h), (len(SDA), len(BT), len(TPS), len(HOLDS)))
def fidx(filt):
    e = np.arange(5); fm = filter_masks(ev, e, np.zeros(5), np.zeros(5), np.zeros(5))
    return [f for f, _ in fm].index(filt)
cands = {
 'A_P12_L300': (('P', 12, 1.0, 600), 300, 1, (3, 'any', 0, 1, 'any', 1, 1), (1.5, -1.0, 3.0, np.inf, 3600)),
 'B_P0_L30': (('P', 0, 0.5, 600), 30, 1, (3, 'any', 0, 0, 'any', 1, 1), (4.5, -1.0, -1.0, np.inf, 14400)),
 'C_M30_L120': (('M', 30, 0.0, 0), 120, 1, (3, 'any', 0, 0, 'any', 1, 1), (4.5, -1.0, -1.0, np.inf, 14400)),
 'D_M12_L300': (('M', 12, 0.0, 0), 300, 1, (3, 'any', 0, 0, 'any', 1, 1), (3.0, -1.0, 3.0, np.inf, 7200)),
}
for nm, (st, L, mode, filt, ex) in cands.items():
    rw = dict(style=ST.index(st), L=L, mode=mode, fi=fidx(filt), exit=ex_index(*ex))
    tr = trades_for(U, R, X, Fz, Fo, ev, rw)
    tr['m'] = pd.to_datetime(tr.entry_ts, unit='s').dt.strftime('%y%m')
    g = tr.groupby('m').r.agg(['size', 'sum']).round(1)
    print(nm, evaluate(tr))
    print(' '.join(f'{m}:{int(n)}/{s:+.1f}' for m, (n, s) in g.iterrows()))
    print('long frac %.2f, long R %.1f short R %.1f' % ((tr.dir > 0).mean(), tr.r[tr.dir > 0].sum(), tr.r[tr.dir < 0].sum()))
