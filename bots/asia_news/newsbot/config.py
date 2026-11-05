"""Configuration: config.toml (operational settings) + LOCKED.json (the strategy settings frozen before the final
test - the bot trades exactly those)."""
from __future__ import annotations

import json
from pathlib import Path

try:
    import tomllib                              # Python >= 3.11
except ModuleNotFoundError:                     # pragma: no cover
    tomllib = None

DEFAULTS = {
    "general": {"mode": "dry-run", "versions": ["nasdaq_v2"], "risk": 0.10, "locked_file": "LOCKED_NQ.json",
                "state_file": "state/newsbot_state.json", "log_file": "logs/newsbot.log",
                "journal_file": "logs/trades.csv", "loop_seconds": 5, "max_entry_lag_seconds": 120},
    "calendar": {"json_url": "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
                 "cache_file": "state/ff_thisweek.json", "refresh_minutes": 60, "actual_source": "ffpage",
                 "actual_file": "state/actuals.json", "poll_seconds": 10, "actual_timeout_seconds": 600,
                 "require_all_figures": True, "chromium_path": "", "user_agent": ""},
    "mt5": {"path": "", "login": "", "password": "", "server": "", "server_utc_offset_hours": 0,
            "magic": 260707, "deviation_points": 50},
    "symbols": {"XAUUSD": "XAUUSDm", "NAS100": "USTECm", "AUDUSD": "AUDUSDm", "NZDUSD": "NZDUSDm",
                "USDJPY": "USDJPYm"},
}


def load_config(path: str | Path | None) -> dict:
    cfg = {k: dict(v) for k, v in DEFAULTS.items()}
    if path:
        p = Path(path)
        if tomllib is None:
            raise RuntimeError("Python >= 3.11 is needed to read config.toml")
        user = tomllib.loads(p.read_text())
        for k, v in user.items():
            cfg.setdefault(k, {}).update(v)
        base = p.resolve().parent
        for sect, key in (("general", "locked_file"), ("general", "state_file"), ("general", "log_file"),
                          ("general", "journal_file"), ("calendar", "cache_file"), ("calendar", "actual_file")):
            q = Path(cfg[sect][key])
            cfg[sect][key] = str(q if q.is_absolute() else base / q)
    return cfg


def load_locked(path: str | Path) -> dict:
    """LOCKED.json -> {version name: strategy cfg}.  The pair version is stored as one cfg per pair
    (pair_aud / pair_nzd / pair_jpy), each trading only its own currency."""
    d = json.loads(Path(path).read_text())
    return d["versions"]
