#!/usr/bin/env python3
"""Scrape the Forex Factory economic calendar (month pages) with headless
Chromium and save every event with its exact UTC timestamp.

    pip install playwright      # uses the pre-installed Chromium in /opt/pw-browsers
    python scripts/fetch_ff_calendar.py --start 2024-10 --end 2026-10

Output: data/calendar/ff_calendar.csv
columns: time_utc, currency, impact, name, actual, forecast, previous, time_label,
         id, ebase_id, better_worse (FF: 1 better / 2 worse for the currency), revision
Forex Factory embeds each event's Unix timestamp ("dateline"), so no
time-zone guessing is needed.  Events marked "All Day"/"Tentative" are kept
but flagged by time_label.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


def parse(html: str) -> list[dict]:
    rows = []
    dec = json.JSONDecoder()
    pos = 0
    while True:
        i = html.find("days: [", pos)
        if i < 0:
            break
        days, end = dec.raw_decode(html, i + len("days: "))
        pos = end
        for d in days:
            for e in d.get("events", []):
                rows.append({
                    "time_utc": pd.Timestamp(e["dateline"], unit="s"),
                    "currency": e.get("currency"),
                    "impact": e.get("impactName"),
                    "name": e.get("name"),
                    "actual": e.get("actual"),
                    "forecast": e.get("forecast"),
                    "previous": e.get("previous"),
                    "time_label": e.get("timeLabel"),
                    "id": e.get("id"),
                    "ebase_id": e.get("ebaseId"),
                    # Forex Factory's own verdict: 1 = actual better than forecast for
                    # the currency (green), 2 = worse (red), 0 = in line / n.a.
                    "better_worse": e.get("actualBetterWorse"),
                    "revision": e.get("revision"),
                })
    return rows


async def scrape(months):
    from playwright.async_api import async_playwright
    out = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        ctx = await b.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/140.0 Safari/537.36", locale="en-US", timezone_id="UTC")
        pg = await ctx.new_page()
        for m in months:
            for attempt in range(4):
                r = await pg.goto(f"https://www.forexfactory.com/calendar?month={m}",
                                  wait_until="domcontentloaded", timeout=90000)
                await pg.wait_for_timeout(4000 + 3000 * attempt)
                rows = parse(await pg.content())
                if rows:
                    break
            print(m, r.status if r else None, len(rows), "events", flush=True)
            out += rows
            await pg.wait_for_timeout(2500)
        await b.close()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2024-10")
    ap.add_argument("--end", default="2026-10")
    ap.add_argument("--out", default="ff_calendar.csv")
    a = ap.parse_args()
    months = [f"{MONTHS[p.month - 1]}.{p.year}" for p in pd.period_range(a.start, a.end, freq="M")]
    rows = asyncio.run(scrape(months))
    df = pd.DataFrame(rows).drop_duplicates("id").sort_values("time_utc")
    out = ROOT / "data" / "calendar"
    out.mkdir(parents=True, exist_ok=True)
    df.to_csv(out / a.out, index=False)
    hi = df[df.impact.str.lower() == "high"]
    print(f"{len(df)} events, {len(hi)} high impact, {len(hi[hi.currency == 'USD'])} high-impact USD -> {out / a.out}")


if __name__ == "__main__":
    main()
