"""features at decision second s (index into Lean arrays), direction d, using only data known before s."""
import numpy as np, pandas as pd, numba as nb


class Pre:
    def __init__(self, L):
        self.L = L
        r = L.raw
        self.CB = np.r_[0, np.cumsum(r['bq'], dtype=np.float64)]
        self.CS = np.r_[0, np.cumsum(r['sq'], dtype=np.float64)]
        self.CNB = np.r_[0, np.cumsum(r['nb'], dtype=np.float64)]
        self.CNS = np.r_[0, np.cumsum(r['ns'], dtype=np.float64)]
        # metrics arrays, known index
        m = L.metrics
        self.m_known = (m.known_ts.to_numpy() - L.t0)
        self.m_ts = m.ts.to_numpy() - L.t0
        oi = m.sum_open_interest.to_numpy()
        self.oi = oi
        self.lsr = m.count_long_short_ratio.to_numpy(); self.tlsr = m.sum_toptrader_long_short_ratio.to_numpy()
        self.tvr = m.sum_taker_long_short_vol_ratio.to_numpy()
        e = L.eth; self.e_known = e.known_ts.to_numpy() - L.t0; self.eoi = e.sum_open_interest.to_numpy(); self.e_ts = e.ts.to_numpy() - L.t0
        p = L.premium; self.p_known = p.known_ts.to_numpy() - L.t0; self.pc = p.close.to_numpy(); self.ph = p.high.to_numpy(); self.pl = p.low.to_numpy()
        dp = L.depth; self.d_known = dp.ts.to_numpy() - L.t0 + 5
        self.dbid = dp['d-1.0'].to_numpy(); self.dask = dp['d+1.0'].to_numpy()
        self.dbid2 = dp['d-2.0'].to_numpy(); self.dask2 = dp['d+2.0'].to_numpy()
        self.dbid5 = dp['d-5.0'].to_numpy(); self.dask5 = dp['d+5.0'].to_numpy()
        f = L.funding; self.f_known = f.ts.to_numpy() - L.t0; self.fr = f.last_funding_rate.to_numpy()


@nb.njit(cache=True)
def rmax(a, s, W):
    out = np.empty(len(s))
    for k in range(len(s)):
        lo = max(s[k] - W, 0)
        out[k] = a[lo:s[k]].max() if s[k] > lo else 0.0
    return out


@nb.njit(cache=True)
def rext(c, s, W, skip, d):
    """directional extreme of c over [s-W, s-skip): for d>0 the max, d<0 the min"""
    out = np.empty(len(s))
    for k in range(len(s)):
        lo = max(s[k] - W, 0); hi = max(s[k] - skip, lo + 1)
        seg = c[lo:hi]
        out[k] = seg.max() if d[k] > 0 else seg.min()
    return out


def compute(P, s, d):
    L = P.L; s = np.asarray(s, np.int64); d = np.asarray(d, np.int64)
    c = L.c; vol = L.vol[s]; F = {}
    F['vol'] = vol
    F['vol_rel'] = vol / np.array([np.nanmean(L.vol[max(x - 86400, 0):x:600]) for x in s])
    p0 = c[s - 1]
    for W in (5, 10, 20, 30, 60, 120, 300, 900):
        F[f'r{W}'] = d * (p0 - c[s - 1 - W]) / vol
    hv = (P.CB[s] - P.CB[s - 3600] + P.CS[s] - P.CS[s - 3600]) / 3600
    hn = (P.CNB[s] - P.CNB[s - 3600] + P.CNS[s] - P.CNS[s - 3600]) / 3600
    for W in (10, 30, 60, 120, 300):
        b = P.CB[s] - P.CB[s - W]; sl = P.CS[s] - P.CS[s - W]
        nb_ = P.CNB[s] - P.CNB[s - W]; ns_ = P.CNS[s] - P.CNS[s - W]
        dv = np.where(d > 0, b, sl); ov = np.where(d > 0, sl, b)
        dn = np.where(d > 0, nb_, ns_)
        F[f'v{W}'] = (b + sl) / (W * hv)          # volume intensity
        F[f'imb{W}'] = (dv - ov) / np.maximum(b + sl, 1e-9)
        F[f'dv{W}'] = dv / (W * hv)
        F[f'cnt{W}'] = dn / (W * hn)
        F[f'asz{W}'] = (dv / np.maximum(dn, 1)) / (hv / np.maximum(hn, 1e-9))   # avg aggressive size vs hour avg
        F[f'eff{W}'] = F[f'r{W}'] / np.maximum(F[f'dv{W}'], 1e-3) if W in (10, 30, 60, 120, 300) else 0  # move per volume
    mbig = np.where(d > 0, 1, 0)
    for W in (10, 30, 60, 300):
        bb = rmax(L.raw['mb'].astype(np.float64), s, W); ss = rmax(L.raw['ms'].astype(np.float64), s, W)
        F[f'big{W}'] = np.where(d > 0, bb, ss)
        F[f'bigo{W}'] = np.where(d > 0, ss, bb)
    hb = rmax(np.maximum(L.raw['mb'], L.raw['ms']).astype(np.float64), s, 3600)
    F['big60_rel'] = F['big60'] / np.maximum(hb, 1e-9)
    F['big300_rel'] = F['big300'] / np.maximum(hb, 1e-9)
    # breakout of range: distance beyond previous extreme (excluding last 300 s)
    for W in (3600, 4 * 3600, 86400):
        ex = rext(c, s, W, 300, d)
        F[f'brk{W // 3600}h'] = d * (p0 - ex) / vol
    # metrics (OI etc.) last known before s
    k = np.searchsorted(P.m_known, s, 'right') - 1
    oi = P.oi
    def lag(kk, j):
        kk2 = kk - j
        return np.where(kk2 >= 0, oi[np.clip(kk2, 0, len(oi) - 1)], np.nan)
    F['oi_lastchg'] = oi[k] / lag(k, 1) - 1
    F['oi_prevchg'] = lag(k, 1) / lag(k, 2) - 1
    F['oi_1h'] = oi[k] / lag(k, 12) - 1
    F['oi_4h'] = oi[k] / lag(k, 48) - 1
    F['oi_24h'] = oi[k] / lag(k, 288) - 1
    F['oi_age'] = s - P.m_ts[k]                      # seconds since the last known bucket time
    F['lsr'] = P.lsr[k]; F['tlsr'] = P.tlsr[k]; F['tvr'] = P.tvr[k]
    F['lsr_1h'] = P.lsr[k] - P.lsr[np.maximum(k - 12, 0)]
    # count of OI drops >=0.3% in the last hour (known)
    doi = np.r_[np.nan, oi[1:] / oi[:-1] - 1]
    cs = np.r_[0, np.cumsum(np.nan_to_num(doi) <= -0.003)]
    F['nOIdrop1h'] = cs[k + 1] - cs[np.maximum(k + 1 - 12, 0)]
    ke = np.searchsorted(P.e_known, s, 'right') - 1
    F['eoi_lastchg'] = P.eoi[ke] / P.eoi[np.maximum(ke - 1, 0)] - 1
    # premium
    kp = np.searchsorted(P.p_known, s, 'right') - 1
    F['prem'] = P.pc[kp] * 1e4
    F['prem_d'] = d * (P.pc[kp] - P.pc[np.maximum(kp - 5, 0)]) * 1e4
    F['prem_d1'] = d * (P.pc[kp] - P.pc[np.maximum(kp - 1, 0)]) * 1e4
    F['prem_dir'] = d * P.pc[kp] * 1e4
    F['prem_rel'] = d * (P.pc[kp] - np.array([np.mean(P.pc[max(x - 60, 0):x + 1]) for x in kp])) * 1e4
    F['prem_age'] = s - P.p_known[kp]
    # depth
    kd = np.searchsorted(P.d_known, s, 'right') - 1
    hit = np.where(d > 0, P.dask[kd], P.dbid[kd]); opp = np.where(d > 0, P.dbid[kd], P.dask[kd])
    F['dep_hit'] = hit; F['dep_opp'] = opp
    F['dep_imb'] = (opp - hit) / (opp + hit)
    hit5 = np.where(d > 0, P.dask5[kd], P.dbid5[kd]); opp5 = np.where(d > 0, P.dbid5[kd], P.dask5[kd])
    F['dep5_imb'] = (opp5 - hit5) / (opp5 + hit5)
    # depth relative to its 24h median (sampled)
    ref = np.array([np.nanmedian((P.dbid[max(x - 2880, 0):x + 1:4] + P.dask[max(x - 2880, 0):x + 1:4])) for x in kd])
    F['dep_rel'] = (P.dbid[kd] + P.dask[kd]) / ref
    F['dep_hit_rel'] = hit / (0.5 * ref)
    F['dep_age'] = s - P.d_known[kd]
    # depth change over last ~5 min on the hit side
    kd5 = np.searchsorted(P.d_known, s - 300, 'right') - 1
    hit_p = np.where(d > 0, P.dask[kd5], P.dbid[kd5])
    F['dep_hit_chg'] = hit / hit_p - 1
    kf = np.searchsorted(P.f_known, s, 'right') - 1
    F['fund'] = d * P.fr[kf] * 1e4
    F['hour'] = ((s + L.t0) % 86400) // 3600
    F['bucket_pos'] = (s + L.t0) % 300
    return pd.DataFrame(F)
