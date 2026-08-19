#!/usr/bin/env python3
"""Datensammler für die Codewhale-Launcher-Extension.

Gibt genau ein JSON-Objekt auf stdout aus:

{
  "provider":          "deepseek",
  "balance_supported": true | false,
  "balance":           {"currency": "USD", "total": "1.93", "available": true} | null,
  "balance_error":     "…"            (nur wenn unterstützt, aber Abruf scheiterte),
  "cost_today_usd":    0.06,
  "cost_week_usd":     0.12,
  "sessions":          [{id, title, workspace, updated_epoch, cost_usd, model, messages}, …]
}

Der aktive Provider kommt aus ~/.codewhale/config.toml (Schlüssel `provider`).
Sessions und Kosten sind provider-unabhängig; eine Guthaben-Abfrage gibt es nur
für Provider mit Eintrag in BALANCE_PROVIDERS.

Kosten sind eine Näherung: eine Session zählt vollständig zu dem Tag, an dem sie
zuletzt aktualisiert wurde (der Session-Store hält nur Gesamtkosten je Session).
"""

import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.request
from datetime import datetime, timedelta, timezone

CONFIG_PATH = os.path.expanduser("~/.codewhale/config.toml")
SESSIONS_DIR = os.path.expanduser("~/.codewhale/sessions")
MAX_SESSIONS = 8

# Provider mit bekannter Guthaben-API. Neue Provider: URL ergänzen und
# parse_balance() um das jeweilige Antwortformat erweitern.
BALANCE_PROVIDERS = {
    "deepseek": "https://api.deepseek.com/user/balance",
}

UUID_JSON_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27}\.json$")
FRACTION_RE = re.compile(r"\.(\d{6})\d+")  # fromisoformat verträgt max. 6 Nachkommastellen


def parse_ts(value):
    if not value:
        return None
    value = FRACTION_RE.sub(r".\1", value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def collect_sessions():
    sessions = []
    try:
        names = os.listdir(SESSIONS_DIR)
    except OSError:
        return sessions
    for name in names:
        if not UUID_JSON_RE.match(name):
            continue
        try:
            with open(os.path.join(SESSIONS_DIR, name)) as f:
                meta = json.load(f).get("metadata") or {}
        except (OSError, ValueError):
            continue
        ts = parse_ts(meta.get("updated_at"))
        if ts is None:
            continue
        cost = meta.get("cost") or {}
        sessions.append({
            "id": meta.get("id") or name[:-5],
            "title": (meta.get("title") or "(ohne Titel)").strip(),
            "workspace": meta.get("workspace") or "",
            "updated_epoch": ts.timestamp(),
            "cost_usd": float(cost.get("session_cost_usd") or 0.0)
                        + float(cost.get("subagent_cost_usd") or 0.0),
            "model": meta.get("model") or "",
            "messages": meta.get("message_count") or 0,
        })
    sessions.sort(key=lambda s: s["updated_epoch"], reverse=True)
    return sessions


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
        return None, None  # Provider ohne bekannte Guthaben-API — kein Fehler
    try:
        proc = subprocess.run(
            ["codewhale", "auth", "print-api-key", "--provider", provider],
            capture_output=True, text=True, timeout=15, stdin=subprocess.DEVNULL,
        )
        key = proc.stdout.strip()
        if not key:
            return None, "kein API-Key (codewhale auth print-api-key)"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
        balance = parse_balance(provider, data)
        if balance is None:
            return None, "Antwortformat unbekannt"
        return balance, None
    except Exception as exc:  # Netz/Timeout/CLI — Panel soll trotzdem rendern
        return None, str(exc)


def main():
    provider = active_provider()
    sessions = collect_sessions()
    today, week = cost_windows(sessions)
    balance, err = fetch_balance(provider)
    result = {
        "provider": provider,
        "balance_supported": provider in BALANCE_PROVIDERS,
        "balance": balance,
        "cost_today_usd": round(today, 4),
        "cost_week_usd": round(week, 4),
        "sessions": sessions[:MAX_SESSIONS],
    }
    if err:
        result["balance_error"] = err
    json.dump(result, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
