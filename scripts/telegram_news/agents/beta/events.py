"""Event table: one row per post-second, features known at decision time for each instrument / delay."""
from lab import *

DL = np.array([0, 1, 2, 3, 5, 8, 12, 20, 30, 45, 60, 90, 120, 180, 300])
LB = np.array([0, 1, 3, 5, 10, 20, 30, 60, 120, 300])
BASEW = 900


def post_events(data_dir=D):
    p = C.load_posts(data_dir).copy()
    p['bang'] = p.text.str.contains('❗')
    p['macro'] = p.text.str.contains('$MACRO', regex=False)
    p['fj'] = p.ch.eq('FJ'); p['wb'] = p.ch.eq('WB')
    p['caps'] = p.text.str.replace(r'\(@WalterBloomberg\)|\|FJ', '', regex=True).str.count(r'[A-Z]') / p.text.str.len().clip(lower=1)
    p['star'] = p.text.str.startswith('*') | p.text.str.contains('🚨|BREAKING|🔥')
    g = p.groupby('ts')
    ev = pd.DataFrame(dict(fj=g.fj.any(), wb=g.wb.any(), bang=g.bang.any(), macro=g.macro.any(), npost=g.size(),
                           star=g.star.any(), text=g.text.first())).reset_index()
    ts = ev.ts.to_numpy()
    ev['prev_gap'] = np.r_[10**6, np.diff(ts)]
    # posts in the previous 60 / 600 s (already published)
    allts = p.ts.to_numpy()
    ev['n60'] = np.searchsorted(allts, ts) - np.searchsorted(allts, ts - 60)
    ev['n600'] = np.searchsorted(allts, ts) - np.searchsorted(allts, ts - 600)
    # other channel posted within the previous 120 s (FJ<->WB echo)
    for ch, col in [('FJ', 'fj_prev120'), ('WB', 'wb_prev120')]:
        c = np.sort(p.ts[p.ch == ch].to_numpy())
        ev[col] = (np.searchsorted(c, ts) - np.searchsorted(c, ts - 120)) > 0
    cal = C.load_calendar(data_dir)
    cal['ts'] = cal.time_utc.astype('datetime64[s]').astype('int64')
    for nm, msk in [('usdh', (cal.currency == 'USD') & (cal.impact == 'high')),
                    ('anyh', cal.impact == 'high')]:
        ct = np.sort(cal.ts[msk].unique())
        i = np.searchsorted(ct, ts, side='right') - 1
        prev = np.where(i >= 0, ts - ct[np.maximum(i, 0)], 10**7)
        nxt = np.where(i + 1 < len(ct), ct[np.minimum(i + 1, len(ct) - 1)] - ts, 10**7)
        ev[f'{nm}_since'] = prev; ev[f'{nm}_until'] = nxt
    ev['hour'] = (ts % 86400) // 3600
    ev['dow'] = pd.to_datetime(ts, unit='s').dayofweek
    ev['month'] = pd.to_datetime(ts, unit='s').strftime('%Y-%m')
    return ev


def inst_features(I, ts):
    """per event (len E) and per delay (len DL): dict of arrays shape (E, nDL) / (E, nDL, nLB)"""
    E = len(ts)
    out = {}
    kP = I.idx_before(ts - 60)                      # baseline ends 60 s before the post
    kP = np.maximum(kP, BASEW)
    nb_ = BASEW
    sig = np.sqrt((I.cs2[kP] - I.cs2[kP - nb_]) / nb_)
    sig4 = np.sqrt((I.cs2[kP] - I.cs2[np.maximum(kP - 3600, 0)]) / 3600)
    nbase = (I.csn[kP] - I.csn[kP - nb_]) / nb_
    spbase = (I.css[kP] - I.css[kP - nb_]) / nb_
    # seconds covered by baseline bars (quiet market / pauses inflate)
    tspan = I.t[kP] - I.t[kP - nb_]
    out['sig'] = sig; out['sig4'] = sig4; out['nbase'] = nbase; out['spbase'] = spbase; out['tspan'] = tspan
    kpost = I.idx_before(ts)                        # last bar before the post second
    refs = np.stack([I.mid[I.idx_before(ts - L)] for L in LB], 1)     # E x nLB
    out['ref'] = refs
    iD = np.stack([I.bar_at(ts + C.LAT + dl) for dl in DL], 1)       # fill bar (market)
    kD = np.stack([I.idx_before(ts + C.LAT + dl) for dl in DL], 1)   # last known bar
    out['iD'] = iD; out['kD'] = kD
    out['pnow'] = I.mid[kD]
    out['burst'] = (I.csn[kD] - I.csn[kpost][:, None]) / np.maximum(kD - kpost[:, None], 1) / np.maximum(nbase, 1e-9)[:, None]
    out['spnow'] = (I.al[kD] - I.bl[kD]) / np.maximum(spbase, 1e-9)[:, None]
    out['spfill'] = np.where(iD >= 0, I.af[np.maximum(iD, 0)] - I.bf[np.maximum(iD, 0)], np.nan)
    # path since post: max / min mid from post second to D-1
    hi = np.zeros((E, len(DL))); lo = np.zeros((E, len(DL)))
    _hilo(I.mid, kpost, kD, hi, lo)
    out['hi'] = hi; out['lo'] = lo
    # in-session check: no pause within the last 900 bars and the next close is > 1 h away
    out['nclose_s'] = I.t[I.next_close(np.maximum(kD[:, 0], 0))] - ts
    out['open_s'] = ts - I.t[_last_gap_end(I, kpost)]
    return out


@nb.njit(cache=True)
def _hilo(mid, kpost, kD, hi, lo):
    E, K = kD.shape
    for e in range(E):
        a = kpost[e] + 1
        h = mid[kpost[e]]; l = h
        x = a
        for q in range(K):
            while x <= kD[e, q]:
                if mid[x] > h: h = mid[x]
                if mid[x] < l: l = mid[x]
                x += 1
            hi[e, q] = h; lo[e, q] = l


def _last_gap_end(I, k):
    g = I.gaps
    i = np.searchsorted(g, k) - 1        # last gap index < k  (gap at g means pause after bar g)
    return np.where(i >= 0, g[np.maximum(i, 0)] + 1, 0)


if __name__ == '__main__':
    ev = post_events()
    ev.to_pickle('cache/events.pkl')
    print(len(ev), ev.groupby('month').size().to_dict())
    ts = ev.ts.to_numpy()
    for inst in ['gold', 'nasdaq']:
        I = Inst(inst)
        f = inst_features(I, ts)
        np.savez(f'cache/feat_{inst}.npz', **f)
        print(inst, {k: v.shape for k, v in f.items()})
        del I; C._TK.clear()
