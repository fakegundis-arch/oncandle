import numpy as np, pandas as pd, fast, btc_common as bc
from scipy.stats import spearmanr
SP = '/home/user/oncandle/scripts/btc_liq/agents3/flow/cache/'
F = pd.read_pickle(SP + 'ev.pkl').replace([np.inf, -np.inf], np.nan)
F['h1'] = F.ts < bc.ts_of('2026-04-01')
skip = {'fam', 'W', 'X', 's', 'd', 'ts', 'sk', 'h1'} | {c for c in F.columns if c[0] in 'fg' and c[1:].isdigit()}
cols = [c for c in F.columns if c not in skip]
# pooled over mid-size families, dedupe events within 900 s across families? use families separately and pool rho
sel = F[F.fam.isin([1, 2, 4, 5, 6, 8, 9, 11])]
rows = []
for c in cols:
    r = []
    for tgt in ('f3600', 'f14400', 'g3600'):
        for h in (True, False):
            q = sel[sel.h1 == h]; x = q[c]; y = q[tgt]; ok = x.notna() & y.notna()
            r.append(spearmanr(x[ok], y[ok])[0] if ok.sum() > 50 else np.nan)
    rows.append([c] + r)
R = pd.DataFrame(rows, columns=['f', 'f1h_H1', 'f1h_H2', 'f4h_H1', 'f4h_H2', 'g1h_H1', 'g1h_H2'])
R['minabs'] = np.where(np.sign(R.f1h_H1) == np.sign(R.f1h_H2), np.minimum(R.f1h_H1.abs(), R.f1h_H2.abs()), 0)
pd.set_option('display.width', 200)
print(R.sort_values('minabs', ascending=False).round(3).head(40).to_string())
