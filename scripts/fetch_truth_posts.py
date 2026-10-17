#!/usr/bin/env python3
"""Download @realDonaldTrump Truth Social posts with exact timestamps.

    python scripts/fetch_truth_posts.py              # -> data/truth/posts.csv

* Feb 2022 - Oct 2025: the public archive at stilesdata.com (trump-truth-social-archive, JSON).
* After that: www.trumpstruth.org pages (100 posts each, walked backwards with its date cursor).
Columns: time_utc, content (HTML stripped), source.
"""
from __future__ import annotations

import base64
import html
import json
import re
import time
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "truth"
ARCHIVE = "https://stilesdata.com/trump-truth-social-archive/truth_archive.json"
SITE = "https://www.trumpstruth.org/"
UA = {"User-Agent": "Mozilla/5.0 (research backtest; contact: none)"}


def strip(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def archive() -> pd.DataFrame:
    f = OUT / "t.json"
    if not f.exists():
        f.write_bytes(requests.get(ARCHIVE, headers=UA, timeout=300).content)
    d = pd.DataFrame(json.loads(f.read_text()))
    return pd.DataFrame({"time_utc": pd.to_datetime(d.created_at, utc=True).dt.tz_localize(None),
                         "content": d.content.map(strip), "source": "stiles"})


TIME = re.compile(r'<time datetime="([^"]+)"')
BODY = re.compile(r'<div class="status__content"[^>]*>(.*?)</div>', re.S)


def parse(page: str):
    out = []
    for block in page.split('class="status" data-status-url=')[1:]:
        t = TIME.search(block)
        if not t:
            continue
        b = BODY.search(block)
        out.append((pd.Timestamp(t.group(1)).tz_convert("UTC").tz_localize(None), strip(b.group(1)) if b else ""))
    return out


def _page(s, cur):
    c = base64.b64encode(json.dumps({"status_created_at": cur.strftime("%Y-%m-%d %H:%M:%S"),
                                      "_pointsToNextItems": True}).encode()).decode()
    for attempt in range(5):
        try:
            r = s.get(SITE, params={"sort": "desc", "per_page": 100, "cursor": c}, headers=UA, timeout=60)
            if r.status_code == 200:
                return parse(r.text)
        except requests.RequestException:
            pass
        time.sleep(5 * (attempt + 1))
    return []


def site(stop: pd.Timestamp) -> pd.DataFrame:
    """Walk day by day (the site's cursor order can skip weeks); within a day, page back until the day is covered."""
    rows = []
    s = requests.Session()
    day = pd.Timestamp.now("UTC").tz_localize(None).normalize()
    while day >= stop.normalize():
        cur = day + pd.Timedelta("1D")
        while True:
            page = [(t, b) for t, b in _page(s, cur) if day <= t < cur]
            rows += page
            if len(page) < 100:
                break
            cur = min(t for t, _ in page)
            time.sleep(0.5)
        print(day.date(), len(rows), flush=True)
        day -= pd.Timedelta("1D")
        time.sleep(0.5)
    return pd.DataFrame(rows, columns=["time_utc", "content"]).assign(source="trumpstruth")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    a = archive()
    b = site(a.time_utc.max() - pd.Timedelta("2D"))
    b["time_utc"] = pd.to_datetime(b.time_utc, format="mixed")
    df = pd.concat([a, b[b.time_utc > a.time_utc.max()]]).drop_duplicates(["time_utc", "content"]).sort_values("time_utc")
    df.to_csv(OUT / "posts.csv", index=False)
    print(len(df), "posts", df.time_utc.min(), "->", df.time_utc.max())


if __name__ == "__main__":
    main()
