#!/usr/bin/env python3
"""Data collector for the Codewhale Launcher GNOME extension.

Prints exactly one JSON object to stdout:

{
  "provider":          "deepseek",
  "balance_supported": true | false,
  "balance":           {"currency": "USD", "total": "1.93", "available": true} | null,
  "balance_error":     "…"            (only when supported but the lookup failed),
  "cost_today_usd":    0.06,
  "cost_week_usd":     0.12,
  "sessions":          [{id, title, workspace, updated_epoch, cost_usd, model, messages}, …]
}

The active provider comes from ~/.codewhale/config.toml (key `provider`).
Sessions and costs are provider-independent; a balance lookup only exists for
providers listed in BALANCE_PROVIDERS.

Sessions hidden via the companion app are excluded from the list, but their
costs still count — hiding is cosmetic. Costs are an approximation: a session
counts entirely towards the day it was last updated (the session store only
keeps totals per session).
"""

import json
import subprocess
import sys
import tomllib
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store

CONFIG_PATH = Path.home() / ".codewhale" / "config.toml"
MAX_SESSIONS = 5

# Providers with a known balance API. To add one: add the URL here and extend
# parse_balance() with the provider's response format.
BALANCE_PROVIDERS = {
    "deepseek": "https://api.deepseek.com/user/balance",
}


def cost_windows(sessions):
    now = datetime.now().astimezone()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    today = week = 0.0
    for s in sessions:
        ts = datetime.fromtimestamp(s["updated_epoch"]).astimezone()
        if ts >= week_start:
            week += s["cost_usd"]
            if ts >= midnight:
                today += s["cost_usd"]
    return today, week


def active_provider():
    try:
        with open(CONFIG_PATH, "rb") as f:
            provider = tomllib.load(f).get("provider")
        return provider if isinstance(provider, str) and provider else None
    except (OSError, tomllib.TOMLDecodeError):
        return None


def parse_balance(provider, data):
    if provider == "deepseek":
        infos = data.get("balance_infos") or []
        usd = next((b for b in infos if b.get("currency") == "USD"),
                   infos[0] if infos else None)
        if usd is None:
            return None
        return {
            "currency": usd.get("currency", "USD"),
            "total": usd.get("total_balance", "?"),
            "available": bool(data.get("is_available")),
        }
    return None


def fetch_balance(provider):
    url = BALANCE_PROVIDERS.get(provider)
    if url is None:
        return None, None  # provider without a known balance API — not an error
    try:
        proc = subprocess.run(
            ["codewhale", "auth", "print-api-key", "--provider", provider],
            capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL,
        )
        key = proc.stdout.strip()
        if not key:
            return None, "no API key (codewhale auth print-api-key)"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        balance = parse_balance(provider, data)
        if balance is None:
            return None, "unknown response format"
        return balance, None
    except Exception as exc:  # network/timeout/CLI — the panel must still render
        return None, str(exc)


def main():
    provider = active_provider()
    sessions = store.collect_sessions()
    today, week = cost_windows(sessions)  # hidden sessions still cost money
    visible = [s for s in sessions if not s["hidden"]]
    balance, err = fetch_balance(provider)
    result = {
        "provider": provider,
        "balance_supported": provider in BALANCE_PROVIDERS,
        "balance": balance,
        "cost_today_usd": round(today, 4),
        "cost_week_usd": round(week, 4),
        "sessions": visible[:MAX_SESSIONS],
    }
    if err:
        result["balance_error"] = err
    json.dump(result, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
