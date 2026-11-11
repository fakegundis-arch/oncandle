"""An ESTIMATE of the bot's AI post review for the posts that have no real verdict.

Real verdicts exist for (a) every post the live bot reviewed (newsbot.log, Oct 25 - Nov 10) and (b) my one permitted
run of the bot's own AIPostChecker on Oct 11 - Nov 9 (ai_verdicts_last30.csv).  For the rest of the year the review
cannot be replayed without calling OpenAI, so a text classifier (word + character TF-IDF, logistic regression) is
trained on the real verdicts and applied to every other reviewable post.  10-fold cross-validated agreement with the
real verdicts is printed and saved - it is about 80 %, so results that rest on it are estimates, and are labelled so.
(The earlier "principal" regex stand-in agrees with the real verdicts on 54 % only and is no longer used.)

usage: python3 -I scripts/goldbot_backtest/ai_standin.py <bot repo> <newsbot.log>
writes results/goldbot_backtest/ai_verdicts_live_log.csv, ai_verdicts_estimated.csv, ai_standin_check.json
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

os.environ.setdefault("GOLDBOT_END", "2026-11-11")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import live_log  # noqa: E402
import replay as R  # noqa: E402

CLEAN = r"\|FJ$|\(@WalterBloomberg\)|@apewirenews"


def model():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline, make_union
    return make_pipeline(make_union(TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True),
                                    TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), min_df=3, sublinear_tf=True)),
                         LogisticRegression(C=8, max_iter=3000, class_weight="balanced"))


def main():
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    log = sys.argv[2]
    L, _, _ = live_log.parse(log)
    L = L[L.ai.isin(["keep", "close"])].copy()
    L["latency_s"] = (pd.to_datetime(L.ai_utc) - pd.to_datetime(L.armed_utc)).dt.total_seconds()
    live = pd.DataFrame(dict(channel=L.channel, post_id=L.post_id.astype(int), ok=(L.ai == "keep").to_numpy(),
                             latency_s=L.latency_s.to_numpy(), verdict=L.ai_text, text=L.text))
    live.to_csv(R.OUT / "ai_verdicts_live_log.csv", index=False)
    V = pd.read_csv(R.OUT / "ai_verdicts_last30.csv")
    V = V[~(V.error.notna() & (V.error.astype(str) != "nan") & (V.error.astype(str) != ""))]
    A = pd.concat([live[["channel", "post_id", "ok", "text"]],
                   pd.DataFrame(dict(channel=V.channel, post_id=V.post_id.astype(int), ok=V.ok.astype(bool).to_numpy(),
                                     text=V.text))], ignore_index=True).drop_duplicates(["channel", "post_id"])
    X, y = A.text.str.replace(CLEAN, "", regex=True), A.ok.to_numpy(bool)
    pr = cross_val_predict(model(), X, y, cv=StratifiedKFold(10, shuffle=True, random_state=0), method="predict_proba")[:, 1]
    p = pr >= 0.5
    both = live.merge(V[["channel", "post_id", "ok"]], on=["channel", "post_id"], suffixes=("_live", "_mine"))
    chk = dict(real_verdicts=int(len(A)), real_keep_rate=round(float(y.mean()), 3),
               cv_agreement=round(float((p == y).mean()), 3), predicted_keep_rate=round(float(p.mean()), 3),
               real_keeps_predicted_keep=round(float(p[y].mean()), 3), real_closes_predicted_close=round(float((~p[~y]).mean()), 3),
               old_principal_rule_agreement=round(float(np.mean([(R.PRINCIPAL.search(t) is not None) == k
                                                                for t, k in zip(A.text, y)])), 3),
               my_run_vs_live_same_posts=dict(n=int(len(both)), same=int((both.ok_live == both.ok_mine.astype(bool)).sum())),
               live_verdict_delay_s=dict(median=float(live.latency_s.median()), p90=float(live.latency_s.quantile(0.9))))
    (R.OUT / "ai_standin_check.json").write_text(json.dumps(chk, indent=1))
    print(json.dumps(chk, indent=1))
    # every other reviewable post of the year
    cfg = R.load_config(str(R.BOT / "config.yaml"))
    d = R.derive(cfg)
    posts = R.load_posts()
    have = set(zip(A.channel, A.post_id))
    rows = []
    for q in posts.itertuples():
        if (q.ch, int(q.id)) in have or R.emoji_flag(q.text, d.et, d.mode):
            continue
        ok, _ = R.post_tradable(q, d.prof, d.mode, 2, keyword_bypass=False)
        if ok:
            rows.append((q.ch, int(q.id), q.text))
    E = pd.DataFrame(rows, columns=["channel", "post_id", "text"])
    m = model().fit(X, y)
    E["p_keep"] = m.predict_proba(E.text.str.replace(CLEAN, "", regex=True))[:, 1].round(3)
    E["ok"] = E.p_keep >= 0.5
    E[["channel", "post_id", "ok", "p_keep", "text"]].to_csv(R.OUT / "ai_verdicts_estimated.csv", index=False)
    print(len(E), "posts estimated; keep rate", round(float(E.ok.mean()), 3))


if __name__ == "__main__":
    main()
