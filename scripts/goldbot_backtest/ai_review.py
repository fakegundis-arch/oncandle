"""Run the bot's OWN post review (newsbot.ai_post_check.AIPostChecker: its prompt, model gpt-4o-mini, temperature 0,
JSON reply, principal + rating >= 60 gates) on every post of the last 30 days that would reach the review: no ❗/🔴
flag and passing the keyword gate (Oct 11 - Nov 9 2026).  The API key is read from OPENAI_API_KEY and never written
anywhere.  Output: results/goldbot_backtest/ai_verdicts_last30.csv (verdict + the measured response time).
usage: OPENAI_API_KEY=... python3 -I scripts/goldbot_backtest/ai_review.py"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import replay as R  # noqa: E402
from newsbot.ai_post_check import AIPostChecker  # noqa: E402

R.END = "2026-11-10"
WINDOW = "2026-10-11"


def main():
    cfg = R.load_config(str(R.BOT / "config.yaml"))
    chk = AIPostChecker(cfg.ai_post_check)
    assert chk.available, "no key"
    prof = cfg.telegram_feed.profile_for(cfg.x_feed.defaults)
    posts = R.load_posts()
    w = posts[posts.t >= pd.Timestamp(WINDOW, tz="UTC")]
    todo = []
    for p in w.itertuples():
        if R.emoji_flag(p.text, cfg.x_feed.emoji_trigger, cfg.keyword_match):
            continue
        ok, _ = R.post_tradable(p, prof, cfg.keyword_match, 2, keyword_bypass=False)
        if ok:
            todo.append(p)
    print("posts to review:", len(todo), flush=True)

    def one(p):
        t0 = time.time()
        v = chk.review(p.text, p.ch, "Telegram")                 # bot: review(text, author, post.source)
        return dict(channel=p.ch, post_id=int(p.id), post_ts=int(p.ts), ok=v.ok, is_principal=v.is_principal,
                    rating=v.rating, failed_gate=v.failed_gate, error=v.error, reason=getattr(v, "reason", ""),
                    latency_s=round(time.time() - t0, 2), text=p.text[:200])

    rows = []
    with ThreadPoolExecutor(cfg.ai_post_check.max_workers) as ex:
        for k, r in enumerate(ex.map(one, todo), 1):
            rows.append(r)
            if k % 100 == 0:
                print(k, "done", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(R.OUT / "ai_verdicts_last30.csv", index=False)
    print("reviewed", len(df), "| keep", int(df.ok.sum()), "| veto speaker", int((df.failed_gate == "speaker").sum()),
          "| veto rating", int((df.failed_gate == "rating").sum()), "| errors", int((df.error.fillna("") != "").sum()),
          "| median latency", df.latency_s.median(), "s")


if __name__ == "__main__":
    main()
