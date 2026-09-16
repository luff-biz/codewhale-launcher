#!/usr/bin/env python3
"""Dashboard status generator for the Codewhale Launcher extension.

Produces a cached "current status" for a chosen session's workspace by
running a single non-interactive Codewhale prompt:

    codewhale exec --auto --resume <session-id> --output-format text "<prompt>"

The result is cached under the launcher cache directory, keyed by session and
prompt, and is reused until the maximum age elapses (or the caller passes
--force). The extension calls this helper on demand (when the dashboard opens)
and passes the settings as arguments; this file knows nothing about the
launcher's settings store and nothing about any particular workspace layout.

Prints exactly one JSON object to stdout, always. On success:

    {"status": "ok", "session_id": …, "workspace": …, "text": …, "generated_at": …, "stale": false, "fresh": true}

`stale` is true when the cached text was reused and its inputs have since
changed (reported so the UI can label it); `fresh` is true when the text was
just generated.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import store

CACHE_DIR = Path(os.environ.get("XDG_CACHE_HOME", "") or Path.home() / ".cache") / "codewhale-launcher"
CACHE_PATH = CACHE_DIR / "dashboard.json"
EXEC_TIMEOUT = 300     # seconds; a status run reads the workspace and answers


def prompt_hash(prompt):
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def save_cache(entry):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CACHE_PATH.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(entry, f, ensure_ascii=False)
    os.replace(tmp, CACHE_PATH)


def find_workspace(session_id):
    for session in store.collect_sessions():
        if session["id"] == session_id:
            return session["workspace"] or ""
    return None


def generate(session_id, prompt, workspace):
    """Run the non-interactive status prompt and return the plain text."""
    proc = subprocess.run(
        ["codewhale", "exec", "--auto", "--resume", session_id,
         "--output-format", "text", prompt],
        cwd=workspace or os.path.expanduser("~"),
        capture_output=True, text=True, timeout=EXEC_TIMEOUT,
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"codewhale exec exited {proc.returncode}")
    text = proc.stdout.strip()
    if not text:
        raise RuntimeError("codewhale exec returned no output")
    return text


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="")
    parser.add_argument("--prompt", default="")
    parser.add_argument("--max-age", type=int, default=360)
    parser.add_argument("--force", action="store_true",
                        help="regenerate even when the cache is fresh")
    args = parser.parse_args()

    if not args.session:
        json.dump({"status": "no-session"}, sys.stdout, ensure_ascii=False)
        return

    workspace = find_workspace(args.session)
    if workspace is None:
        json.dump({"status": "session-not-found", "session_id": args.session},
                  sys.stdout, ensure_ascii=False)
        return

    phash = prompt_hash(args.prompt)
    now = time.time()

    cache = load_cache()
    age = now - cache.get("generated_at", 0) if cache else None
    usable = (
        not args.force
        and cache is not None
        and cache.get("session_id") == args.session
        and cache.get("prompt_hash") == phash
        and age is not None
        and age < args.max_age * 60
    )

    if usable:
        json.dump({
            "status": "ok",
            "session_id": args.session,
            "workspace": workspace,
            "text": cache["text"],
            "generated_at": cache["generated_at"],
            "fresh": False,
            "stale": False,
        }, sys.stdout, ensure_ascii=False)
        return

    try:
        text = generate(args.session, args.prompt, workspace)
    except Exception as exc:  # CLI missing, timeout, non-zero exit, empty output
        # Serve the stale cache when generation fails, clearly flagged.
        if cache is not None:
            json.dump({
                "status": "stale",
                "session_id": args.session,
                "workspace": workspace,
                "text": cache.get("text", ""),
                "generated_at": cache.get("generated_at"),
                "fresh": False,
                "stale": True,
                "error": str(exc),
            }, sys.stdout, ensure_ascii=False)
            return
        json.dump({"status": "error", "session_id": args.session,
                   "workspace": workspace, "error": str(exc)},
                  sys.stdout, ensure_ascii=False)
        return

    entry = {
        "session_id": args.session,
        "prompt_hash": phash,
        "generated_at": now,
        "text": text,
    }
    save_cache(entry)
    json.dump({
        "status": "ok",
        "session_id": args.session,
        "workspace": workspace,
        "text": text,
        "generated_at": now,
        "fresh": True,
        "stale": False,
    }, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
