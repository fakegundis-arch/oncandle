import numpy as np, pandas as pd, fast, btc_common as bc
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
F = pd.read_pickle('cache_bucket_feats.pkl')
F = F.replace([np.inf, -np.inf], np.nan)
y = (F.doi <= -0.005).astype(int)
L0 = bc.ts_of('2025-12-01')
# need time; reconstruct: hour isn't enough. store index order is chronological
n = len(F); half = n // 2
X = F.drop(columns=['doi', 'atT', 'atT60', 'fwd300', 'mv', 'bucket_pos', 'oi_age', 'oi_lastchg', 'oi_prevchg'])
cols = X.columns
for tr, te in ((slice(0, half), slice(half, n)), (slice(half, n), slice(0, half))):
    m = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05, min_samples_leaf=30)
    m.fit(X.iloc[tr], y.iloc[tr]); p = m.predict_proba(X.iloc[te])[:, 1]
    yt = y.iloc[te].to_numpy(); rt = F.atT.iloc[te].fillna(0).to_numpy(); r60 = F.atT60.iloc[te].fillna(0).to_numpy()
    print('AUC', roc_auc_score(yt, p), 'base', yt.mean())
    o = np.argsort(-p)
    for q in (20, 50, 100, 200):
        i = o[:q]; print(f' top{q}: oidrop rate {yt[i].mean():.2f}  R atT {rt[i].sum():+.1f} mean {rt[i].mean():+.3f}')
