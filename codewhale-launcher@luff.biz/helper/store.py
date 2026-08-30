"""Shared access to the Codewhale session store and the launcher's own state.

Used by helper/panel-data.py (extension data) and app/history.py (companion
window). Hiding a session only records its id in the launcher's config dir and
never touches the Codewhale store; deleting removes the session file (and a
same-id checkpoint file, if present) permanently.
"""

import json
import os
import re
from datetime import datetime

SESSIONS_DIR = os.path.expanduser("~/.codewhale/sessions")
CHECKPOINTS_DIR = os.path.join(SESSIONS_DIR, "checkpoints")
HIDDEN_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
    "codewhale-launcher", "hidden.json")

UUID_JSON_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f-]{27}\.json$")
FRACTION_RE = re.compile(r"\.(\d{6})\d+")  # fromisoformat allows at most 6 fractional digits


def parse_ts(value):
    if not value:
        return None
    value = FRACTION_RE.sub(r".\1", value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def load_hidden():
    try:
        with open(HIDDEN_PATH) as f:
            return set(json.load(f))
    except (OSError, ValueError):
        return set()


def save_hidden(ids):
    os.makedirs(os.path.dirname(HIDDEN_PATH), exist_ok=True)
    tmp = HIDDEN_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(sorted(ids), f)
    os.replace(tmp, HIDDEN_PATH)


def hide_session(session_id):
    save_hidden(load_hidden() | {session_id})


def restore_session(session_id):
    save_hidden(load_hidden() - {session_id})


def delete_session(session_id):
    """Permanently remove a session (and its same-id checkpoint) from the store."""
    name = f"{session_id}.json"
    if not UUID_JSON_RE.match(name):
        raise ValueError(f"not a session id: {session_id!r}")
    os.remove(os.path.join(SESSIONS_DIR, name))
    checkpoint = os.path.join(CHECKPOINTS_DIR, name)
    if os.path.exists(checkpoint):
        os.remove(checkpoint)
    restore_session(session_id)  # drop a stale hidden entry, if any


def collect_sessions():
    """All sessions, newest first, each flagged with `hidden`."""
    hidden = load_hidden()
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
        session_id = meta.get("id") or name[:-5]
        sessions.append({
            "id": session_id,
            "title": (meta.get("title") or "(untitled)").strip(),
            "workspace": meta.get("workspace") or "",
            "updated_epoch": ts.timestamp(),
            "cost_usd": float(cost.get("session_cost_usd") or 0.0)
                        + float(cost.get("subagent_cost_usd") or 0.0),
            "model": meta.get("model") or "",
            "messages": meta.get("message_count") or 0,
            "hidden": session_id in hidden,
        })
    sessions.sort(key=lambda s: s["updated_epoch"], reverse=True)
    return sessions
