import numpy as np, pandas as pd
from outcomes import styles, SDA, BT, TPS, HOLDS
from search import trades_for, evaluate, filter_masks
rows = []
for f, lab in [('gold_0', 'REAL gold'), ('nasdaq_0', 'REAL nasdaq'), ('gold_1', 'shift1 gold'), ('gold_2', 'shift2 gold'), ('gold_3', 'shift3 gold'),
               ('nasdaq_1', 'shift1 nasdaq'), ('nasdaq_2', 'shift2 nasdaq'), ('nasdaq_3', 'shift3 nasdaq'),
               ('gold_0r1', 'randdir1 gold'), ('gold_0r2', 'randdir2 gold'), ('nasdaq_0r1', 'randdir1 nasdaq')]:
    r = pd.read_pickle(f'cache/search_{f}.pkl').sort_values('s_fin', ascending=False)
    t20 = r.head(20)
    rows.append(dict(search=lab, best_search_usd=round(r.s_fin.iloc[0]), its_check_usd=round(r.c_fin.iloc[0]),
                     top20_check_usd_max=round(t20.c_fin.max()), top20_check_usd_median=round(t20.c_fin.median()),
                     top100_check_frac_profitable=round((r.head(100).c_fin > 1000).mean(), 2)))
print(pd.DataFrame(rows).to_string())
# same frozen rule at fake post times
ST = styles()
def ex_index(sda, be, tr, tp, hold):
    return np.ravel_multi_index((list(SDA).index(sda), BT.index((be, tr)), list(TPS).index(tp), list(HOLDS).index(hold)), (len(SDA), len(BT), len(TPS), len(HOLDS)))
for seed in [0, 1, 2, 3]:
    base = f'cache/out_gold_{seed}'
    R = np.load(base + '_R.npy', mmap_mode='r'); X = np.load(base + '_X.npy', mmap_mode='r')
    U = pd.read_pickle(base + '_U.pkl'); Fz = dict(np.load(base + '_F.npz')); Fo = dict(np.load(f'cache/out_nasdaq_{seed}_F.npz'))
    ev = pd.read_pickle(f'cache/ev_{seed}.pkl')
    fm = filter_masks(ev, np.arange(5), np.zeros(5), np.zeros(5), np.zeros(5)); fi = [x for x, _ in fm].index((3, 'any', 0, 0, 'any', 1, 1))
    for st, ex in [(('P', 0, 0.5, 600), (4.5, -1.0, -1.0, np.inf, 14400)), (('M', 0, 0.0, 0), (4.5, -1.0, -1.0, np.inf, 14400))]:
        rw = dict(style=ST.index(st), L=30, mode=1, fi=fi, exit=ex_index(*ex))
        o = evaluate(trades_for(U, R, X, Fz, Fo, ev, rw))
        print('frozen rule', st[0], 'seed', seed, {k: round(v, 2) for k, v in o.items() if k[0] in 'sch'})
