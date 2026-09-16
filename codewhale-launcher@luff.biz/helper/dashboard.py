#!/usr/bin/env python3
"""Dashboard status generator for the Codewhale Launcher extension.

Produces a cached "current status" for the favorite session's workspace by
running a single non-interactive Codewhale prompt:

    codewhale exec --auto --resume <session-id> --output-format text "<prompt>"

The result is cached under the launcher cache directory. Staleness is decided
by a cheap workspace fingerprint (newest mtime of the workspace, or the git
HEAD when the workspace is a repository) together with a maximum age. The
extension calls this helper on demand (when the dashboard opens) and passes the
settings as arguments; this file knows nothing about the launcher's settings
store and nothing about any particular workspace layout.

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
SCAN_LIMIT = 200_000   # bound the fingerprint walk so huge workspaces stay cheap
EXEC_TIMEOUT = 300     # seconds; a status run reads the workspace and answers


def prompt_hash(prompt):
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:16]


def workspace_fingerprint(workspace):
    """A cheap, stable fingerprint of a workspace.

    For a git repository the HEAD commit is used (fast and precise). Otherwise
    the newest mtime plus the file count is used — good enough to catch the
    common cases (new, changed, or removed files); an in-place edit of an old
    file that leaves the newest mtime untouched is the known blind spot, and
    the max-age and the manual refresh cover it.
    """
    if os.path.isdir(os.path.join(workspace, ".git")):
        try:
            head = subprocess.run(
                ["git", "-C", workspace, "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=10,
            ).stdout.strip()
            if head:
                return f"git:{head}"
        except (OSError, subprocess.SubprocessError):
            pass

    newest = 0
    count = 0
    try:
        for root, _dirs, files in os.walk(workspace):
            for name in files:
                try:
                    st = os.lstat(os.path.join(root, name))
                    newest = max(newest, st.st_mtime_ns)
                    count += 1
                except OSError:
                    continue
                if count > SCAN_LIMIT:
                    return f"mtime:{newest}:{count}"
    except OSError:
        pass
    return f"mtime:{newest}:{count}"


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
    fingerprint = workspace_fingerprint(workspace)
    now = time.time()

    cache = load_cache()
    usable = (
        not args.force
        and cache is not None
        and cache.get("session_id") == args.session
        and cache.get("prompt_hash") == phash
        and cache.get("fingerprint") == fingerprint
        and now - cache.get("generated_at", 0) < args.max_age * 60
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
        "fingerprint": fingerprint,
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
