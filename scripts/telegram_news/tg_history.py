"""Download the full post history of public Telegram channels from their web preview (t.me/s/<channel>), newest to
oldest, back to a start date.  One JSON line per post: id, time (UTC, to the second), text, links, views.
Resumable: an existing file is extended back from its oldest post.

usage: python3 -I scripts/telegram_news/tg_history.py <since YYYY-MM-DD> <outdir> <channel> [...]"""
import html
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"}
MSG = re.compile(r'data-post="([^"/]+)/(\d+)"(.*?)(?=data-post="|\Z)', re.S)


def get(url: str) -> str:
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception:                                        # noqa: BLE001
            time.sleep(4 * (i + 1))
    return ""


def parse(page: str) -> list[dict]:
    out = []
    for _, mid, body in MSG.findall(page):
        t = re.search(r'<time datetime="([^"]+)"', body)
        if not t:
            continue
        tx = re.search(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', body, re.S)
        raw = tx.group(1) if tx else ""
        links = re.findall(r'href="(https?://[^"]+)"', raw)
        text = html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<br\s*/?>", "\n", raw))).strip()
        fwd = re.search(r'tgme_widget_message_forwarded_from_name[^>]*>(?:<[^>]+>)*([^<]+)', body)
        views = re.search(r'tgme_widget_message_views">([^<]+)<', body)
        out.append({"id": int(mid), "time": t.group(1), "text": text, "links": links,
                    "fwd": html.unescape(fwd.group(1)).strip() if fwd else None,
                    "views": views.group(1) if views else None})
    return out


def scrape(ch: str, since: datetime, outdir: Path, pause: float = 0.5):
    f = outdir / f"{ch}.jsonl"
    seen, oldest = set(), None
    if f.exists():
        for line in f.read_text().splitlines():
            p = json.loads(line)
            seen.add(p["id"])
            oldest = p["id"] if oldest is None else min(oldest, p["id"])
    n_new = 0
    with f.open("a") as fh:
        # newest posts first (only on a fresh file), then back from the oldest one we have
        before = oldest
        for _ in range(100000):
            ps = parse(get(f"https://t.me/s/{ch}" + (f"?before={before}" if before else "")))
            time.sleep(pause)
            if not ps:
                break
            for p in ps:
                if p["id"] not in seen:
                    seen.add(p["id"])
                    fh.write(json.dumps(p, ensure_ascii=False) + "\n")
                    n_new += 1
            low = min(ps, key=lambda p: p["id"])
            if datetime.fromisoformat(low["time"]) < since or low["id"] <= 1:
                break
            before = low["id"]
    print(f"{ch}: +{n_new} posts ({len(seen)} total)", flush=True)


if __name__ == "__main__":
    since = datetime.fromisoformat(sys.argv[1]).replace(tzinfo=timezone.utc)
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for c in sys.argv[3:]:
        scrape(c, since, out)
