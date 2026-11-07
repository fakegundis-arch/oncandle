import sys, itertools
from lab import *
from outcomes import styles, LS, SDA, BT, TPS, HOLDS
from search import filter_masks, NEX, trades_for, evaluate
exec(open('monthly.py').read().split("cands = {")[0].split("pd.set_option")[1].split('\n', 1)[1]) if False else None
from monthly import U, R, X, Fz, Fo, ev, ST, ex_index, fidx
base = (('P', 0, 0.5, 600), 30, 1, (3, 'any', 0, 0, 'any', 1, 1), (4.5, -1.0, -1.0, np.inf, 14400))
rows = []
def run(st, L, mode, filt, ex, tag):
    rw = dict(style=ST.index(st), L=L, mode=mode, fi=fidx(filt), exit=ex_index(*ex))
    tr = trades_for(U, R, X, Fz, Fo, ev, rw)
    o = evaluate(tr); o.update(tag=tag, st=st, L=L, filt=filt, ex=ex); rows.append(o)
st, L, mode, filt, ex = base
for k in [0.5, 1.0, 2.0]:
    for T in [120, 600, 1800]:
        for dl in [0, 12]:
            run(('P', dl, k, T), L, mode, filt, ex, 'style')
for kk in [0.5, 1.0, 2.0]:
    for T in [60, 300, 900]:
        run(('S', 0, kk, T), L, mode, filt, ex, 'stopstyle')
for dl in [0, 3, 12, 30, 60]:
    run(('M', dl, 0.0, 0), L, mode, filt, ex, 'mkt')
for LL in LS:
    run(st, LL, mode, filt, ex, 'L')
for f in [(z, c, b, m, cal, bu, co) for z in [3, 4, 5] for c in ['any', 'FJ', 'WB'] for b in [0] for m in [0, 1] for cal in ['any', 'far'] for bu in [0, 1] for co in [0, 1]]:
    run(st, L, mode, f, ex, 'filt')
for sda in SDA:
    for tp in TPS:
        for hold in HOLDS:
            run(st, L, mode, filt, (sda, -1.0, -1.0, tp, hold), 'exit')
for bt in BT:
    run(st, L, mode, filt, (4.5, bt[0], bt[1], np.inf, 14400), 'bt')
df = pd.DataFrame(rows)
pd.set_option('display.width', 250); pd.set_option('display.max_rows', 500)
cols = ['tag', 'st', 'L', 'filt', 'ex', 's_n', 's_R', 's_pf', 's_fin', 'c_n', 'c_R', 'c_pf', 'c_fin', 'h_fin', 'h_dd']
df.to_pickle('cache/neigh_B.pkl')
for tg in df.tag.unique():
    q = df[df.tag == tg]
    print(tg, 'n=%d  frac s_R>0 %.2f  frac c_R>0 %.2f  med s_fin %.0f med c_fin %.0f med h_fin %.0f' % (len(q), (q.s_R > 0).mean(), (q.c_R > 0).mean(), q.s_fin.median(), q.c_fin.median(), q.h_fin.median()))
print(df[df.tag.isin(['style', 'stopstyle', 'mkt', 'L', 'bt'])][cols].round(2).to_string())
print(df[df.tag == 'filt'][cols].round(2).to_string())
