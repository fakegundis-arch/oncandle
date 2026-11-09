import numpy as np, numba as nb, fast, slib, btc_common as bc
T = {k: bc.ts_of(v) for k, v in dict(a='2026-01-01', m='2026-04-01', s='2026-05-01', e='2026-07-01').items()}


@nb.njit(cache=True)
def run_all(E, X, R, S, P, Rs, masks, idx, T_a, T_m, T_s, T_e):
    """masks [F, n] bool; idx = events of the family (sorted) -> metrics [F, G, 3(maxpos), 12]"""
    F, n = masks.shape; G = R.shape[0]
    out = np.zeros((F, G, 3, 12))
    for f in range(F):
        mk = masks[f]
        if mk.sum() < 10:
            continue
        for g in range(G):
            for mp in range(3):
                n1, R1, gw1, gl1, b1, dd1, Ra1, Rb1 = slib.acct_mask(E[g], X[g], R[g], S[g], P[g], mk, mp + 1, T_a, T_m, T_e)
                n2, R2, gw2, gl2, b2, dd2, Ra2, Rb2 = slib.acct_mask(E[g], X[g], R[g], S[g], P[g], mk, mp + 1, T_a, T_s, T_s)
                n3, R3, gw3, gl3, b3, dd3, Ra3, Rb3 = slib.acct_mask(E[g], X[g], Rs[g], S[g], P[g], mk, mp + 1, T_a, T_m, T_e)
                o = out[f, g, mp]
                o[0] = n1; o[1] = R1; o[2] = gw1 / max(gl1, 1e-9); o[3] = b1; o[4] = dd1; o[5] = Ra1; o[6] = Rb1
                o[7] = gw3 / max(gl3, 1e-9); o[8] = n2; o[9] = R2; o[10] = b2; o[11] = dd2
    return out


