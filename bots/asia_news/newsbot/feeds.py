"""Live calendar sources (pluggable).

Schedule source  - which releases are coming, with forecast / previous:
    FFWeeklyJSON   Forex Factory's public weekly export https://nfs.faireconomy.media/ff_calendar_thisweek.json
                   (fields: title, country (= currency), date (ISO with the New-York offset), impact, forecast,
                   previous).  It carries NO actual value.  FF rate-limits it hard: "the export file is only updated
                   once per hour" and more than a few requests per five minutes get HTTP 429 "Request Denied" - so it
                   is fetched at most once per `refresh_minutes` and cached on disk; on 429 / errors the cache is used.
Actual source    - the actual value right after the release:
    FFPageActuals  loads the Forex Factory calendar page of the release day in headless Chromium (Playwright) and
                   parses the `days: [...]` JSON embedded in it (the same parser as scripts/fetch_ff_calendar.py),
                   which carries actual, forecast, previous and FF's better/worse verdict (actualBetterWorse).
                   Latency: FF usually shows the actual 5-60 s after the release; one page load is 3-10 s; the bot
                   polls every `poll_seconds` until every figure of the release has an actual, or gives up after
                   `timeout_seconds` (then the release is skipped).  Forex Factory sits behind Cloudflare and may
                   challenge or block automated browsers at any time: check its terms of use, keep the polling slow,
                   and expect to replace this source (e.g. a paid economic-calendar API) - anything implementing
                   `fetch(release_time, currency)` can be plugged in.
    FileActuals    reads actuals typed into a local JSON file (manual entry / another feed writes it) - also used
                   for tests and dry runs.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from .events import Release, is_target_event, make_figure

log = logging.getLogger("newsbot.feeds")
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def utc_naive(t: datetime) -> datetime:
    if t.tzinfo is not None:
        t = t.astimezone(timezone.utc).replace(tzinfo=None)
    return t


class ScheduleSource(Protocol):
    def upcoming(self) -> list[Release]: ...


class ActualSource(Protocol):
    def fetch(self, release_time: datetime, currency: str) -> list[dict] | None:
        """Rows (name, actual, forecast, previous, verdict) for that currency and minute, or None if unavailable."""
        ...


# --------------------------------------------------------------------------------------------- schedule: weekly JSON
class FFWeeklyJSON:
    def __init__(self, url: str, cache_file: str | Path, refresh_minutes: int = 60, timeout: int = 20):
        self.url, self.cache, self.refresh = url, Path(cache_file), refresh_minutes
        self.timeout = timeout
        self._last_try = 0.0

    def _download(self) -> None:
        import requests
        fresh = self.cache.exists() and time.time() - self.cache.stat().st_mtime < self.refresh * 60
        if fresh or time.time() - self._last_try < self.refresh * 60:
            return                                   # at most one request per `refresh_minutes`, even after a restart
        self._last_try = time.time()
        try:
            r = requests.get(self.url, timeout=self.timeout)
            if r.status_code == 200 and r.text.lstrip().startswith("["):
                self.cache.parent.mkdir(parents=True, exist_ok=True)
                self.cache.write_text(r.text)
                log.info("weekly calendar downloaded (%d bytes)", len(r.text))
            else:
                log.warning("weekly calendar: HTTP %s (%s) - using cache %s", r.status_code,
                            "rate limited" if r.status_code == 429 else "unexpected body", self.cache)
        except Exception as e:                                    # network errors: keep the cache
            log.warning("weekly calendar download failed: %s - using cache", e)

    def rows(self) -> list[dict]:
        self._download()
        if not self.cache.exists():
            return []
        return json.loads(self.cache.read_text())

    def upcoming(self) -> list[Release]:
        return releases_from_json(self.rows())


def releases_from_json(rows: list[dict]) -> list[Release]:
    """FF weekly JSON rows -> target releases (high impact, Asian currency, 21:45-07:00 UTC), figures without
    actuals (actual = nan) but with forecast / previous."""
    out: dict[tuple, Release] = {}
    for e in rows:
        try:
            t = utc_naive(datetime.fromisoformat(str(e["date"])))
        except (KeyError, ValueError):
            continue
        ccy = str(e.get("country", "")).upper()
        if not is_target_event(ccy, str(e.get("impact", "")), t):
            continue
        f = make_figure(e.get("title", ""), e.get("actual"), e.get("forecast"), e.get("previous"), None)
        if f is None:
            continue
        out.setdefault((t, ccy), Release(t, ccy)).figures.append(f)
    return sorted(out.values(), key=lambda r: (r.time, r.currency))


# --------------------------------------------------------------------------------------------- actual: FF page
def parse_ff_page(html: str) -> list[dict]:
    """The calendar page embeds `days: [...]` JSON with every event (same parser as scripts/fetch_ff_calendar.py)."""
    rows, dec, pos = [], json.JSONDecoder(), 0
    while True:
        i = html.find("days: [", pos)
        if i < 0:
            break
        days, end = dec.raw_decode(html, i + len("days: "))
        pos = end
        for d in days:
            for e in d.get("events", []):
                rows.append({"time": datetime.fromtimestamp(int(e["dateline"]), tz=timezone.utc).replace(tzinfo=None),
                             "currency": e.get("currency"), "impact": e.get("impactName"), "name": e.get("name"),
                             "actual": e.get("actual"), "forecast": e.get("forecast"), "previous": e.get("previous"),
                             "verdict": e.get("actualBetterWorse")})
    return rows


class FFPageActuals:
    """Polls the FF calendar day page with a persistent headless Chromium (Playwright)."""

    def __init__(self, chromium_path: str = "", user_agent: str = "", page_wait_ms: int = 2500,
                 base_url: str = "https://www.forexfactory.com/calendar"):
        self.chromium_path, self.user_agent, self.wait = chromium_path, user_agent, page_wait_ms
        self.base = base_url
        self._pw = self._browser = self._page = None

    def _ensure(self):
        if self._page is not None:
            return
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        kw = {"args": ["--no-sandbox"]}
        if self.chromium_path:
            kw["executable_path"] = self.chromium_path
        self._browser = self._pw.chromium.launch(**kw)
        ctx_kw = {"locale": "en-US", "timezone_id": "UTC"}
        if self.user_agent:
            ctx_kw["user_agent"] = self.user_agent
        self._page = self._browser.new_context(**ctx_kw).new_page()

    def close(self):
        try:
            if self._browser:
                self._browser.close()
            if self._pw:
                self._pw.stop()
        finally:
            self._pw = self._browser = self._page = None

    def day_url(self, t: datetime) -> str:
        # FF shows days in the browser's time zone; the context is UTC, so the UTC date is the right page
        return f"{self.base}?day={MONTHS[t.month - 1]}{t.day}.{t.year}"

    def fetch(self, release_time: datetime, currency: str) -> list[dict] | None:
        try:
            self._ensure()
            r = self._page.goto(self.day_url(release_time), wait_until="domcontentloaded", timeout=30000)
            self._page.wait_for_timeout(self.wait)
            rows = parse_ff_page(self._page.content())
            if not rows:
                log.warning("FF page: no calendar data (HTTP %s) - blocked or layout changed?", r.status if r else None)
                return None
        except Exception as e:
            log.warning("FF page fetch failed: %s", e)
            self.close()
            return None
        return [x for x in rows if x["currency"] == currency and x["time"] == release_time]


# --------------------------------------------------------------------------------------------- actual: local file
class FileActuals:
    """JSON file: [{"time": "2026-07-29 01:30", "currency": "AUD", "name": "CPI y/y", "actual": "3.1%",
    "forecast": "3.0%", "previous": "2.9%", "verdict": 1}, ...]  (verdict optional)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self, release_time: datetime, currency: str) -> list[dict] | None:
        if not self.path.exists():
            return None
        out = []
        for x in json.loads(self.path.read_text()):
            t = datetime.fromisoformat(str(x["time"]))
            if utc_naive(t) == release_time and x["currency"] == currency:
                out.append(x)
        return out or None


# --------------------------------------------------------------------------------------------- polling helper
def wait_for_actual(src: ActualSource, rel: Release, poll_seconds: float, timeout_seconds: float,
                    require_all: bool = True, now=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
                    sleep=time.sleep) -> Release | None:
    """Poll `src` from the release time until every scheduled figure has an actual (or `timeout_seconds` pass).
    Returns the release rebuilt from the source rows (actual, forecast, previous, verdict) or None (skip).
    With require_all (default, = what the backtest sees) a release with a missing figure at the timeout is skipped."""
    deadline = rel.time + timedelta(seconds=timeout_seconds)
    want = {f.name for f in rel.figures}
    best = None
    while now() <= deadline:
        rows = src.fetch(rel.time, rel.currency)
        if rows:
            figs = []
            for x in rows:
                if not is_target_event(rel.currency, x.get("impact", "high") or "high", rel.time):
                    continue
                f = make_figure(x["name"], x.get("actual"), x.get("forecast"), x.get("previous"), x.get("verdict"))
                if f is not None and f.has_actual:
                    figs.append(f)
            if figs:
                best = Release(rel.time, rel.currency, figs)
                if want <= {f.name for f in figs}:
                    return best
        sleep(poll_seconds)
    if best is not None and require_all:
        log.warning("%s: only %s arrived before the timeout - skipped", rel.key(), [f.name for f in best.figures])
        return None
    return best
