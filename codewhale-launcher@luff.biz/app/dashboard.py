#!/usr/bin/env python3
"""Codewhale dashboard — GTK4/libadwaita companion window.

Shows a cached "current status" for a chosen session's workspace, generated
with the Codewhale CLI. Runs as a separate process (GNOME Shell extensions
cannot open GTK windows); the extension merely spawns it. The status text comes
from helper/dashboard.py, which handles caching and staleness; this window only
displays the result. The prompt and cache age are configured in the extension
preferences.
"""

import argparse
import gettext
import json
import os
import re
import subprocess
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

EXT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UUID = "codewhale-launcher@luff.biz"
SCHEMA_ID = "org.gnome.shell.extensions.codewhale-launcher"

# Make the extension's compiled schema visible to Gio.Settings in this process.
os.environ["GSETTINGS_SCHEMA_DIR"] = os.path.join(EXT_DIR, "schemas")

_ = gettext.translation(UUID, os.path.join(EXT_DIR, "locale"), fallback=True).gettext

sys.path.insert(0, os.path.join(EXT_DIR, "helper"))
import store  # noqa: E402


def relative_age(epoch_secs):
    diff = max(0, time.time() - epoch_secs)
    if diff < 60:
        return _("just now")
    if diff < 3600:
        return _("%d min ago") % (diff // 60)
    if diff < 86400:
        return _("%d h ago") % (diff // 3600)
    return _("%d d ago") % (diff // 86400)


_INLINE_BOLD = re.compile(r"\*\*(.+?)\*\*")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BLOCK_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_BLOCK_BULLET = re.compile(r"^\s{0,3}[-*+]\s+(.*)$")
_BLOCK_NUM = re.compile(r"^\s{0,3}(\d+)[.)]\s+(.*)$")


def _inline_pango(s):
    s = _INLINE_BOLD.sub(r"<b>\1</b>", s)
    s = _INLINE_CODE.sub(r"<tt>\1</tt>", s)
    return s


def markdown_to_pango(text):
    """Render common markdown as Pango markup so the status stays readable."""
    text = GLib.markup_escape_text(text)
    out = []
    for line in text.split("\n"):
        m = _BLOCK_HEADING.match(line)
        if m:
            out.append(f"<b>{_inline_pango(m.group(1))}</b>")
            continue
        m = _BLOCK_BULLET.match(line)
        if m:
            out.append(f"  •  {_inline_pango(m.group(1))}")
            continue
        m = _BLOCK_NUM.match(line)
        if m:
            out.append(f"{m.group(1)}.  {_inline_pango(m.group(2))}")
            continue
        out.append(_inline_pango(line))
    return "\n".join(out)


class DashboardWindow(Adw.ApplicationWindow):
    def __init__(self, app, session_id):
        super().__init__(application=app, default_width=680, default_height=520,
                         title=_("Dashboard"))
        self._session_id = session_id
        self._settings = Gio.Settings.new(SCHEMA_ID)
        self.set_icon_name("codewhale-launcher")

        self._updated = Gtk.Label(label="", css_classes=["dim-label", "caption"],
                                  valign=Gtk.Align.CENTER)
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic",
                                 tooltip_text=_("Refresh"), css_classes=["flat"])
        refresh_btn.connect("clicked", self._on_refresh)

        resume_btn = Gtk.Button(label=_("Resume session"),
                                icon_name="utilities-terminal-symbolic",
                                css_classes=["suggested-action"])
        resume_btn.connect("clicked", self._resume_session)

        header = Adw.HeaderBar()
        header.pack_start(resume_btn)
        header.pack_end(self._updated)
        header.pack_end(refresh_btn)

        self._text = Gtk.Label(wrap=True, selectable=True,
                               xalign=0, valign=Gtk.Align.START,
                               use_markup=True, css_classes=["body"])
        clamp = Adw.Clamp(child=self._text, maximum_size=760,
                          margin_top=24, margin_bottom=24,
                          margin_start=18, margin_end=18)
        scroller = Gtk.ScrolledWindow(child=clamp, vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)
        view = Adw.ToolbarView(content=scroller)
        view.add_top_bar(header)
        self.set_content(view)

        self._generate(force=False)

    def _set_text(self, text):
        self._text.set_markup(GLib.markup_escape_text(text))

    def _generate(self, force):
        if not self._settings.get_boolean("dashboard-ai"):
            self._show_deterministic()
            return

        self._set_text(_("Generating…"))
        self._updated.set_text("")

        prompt = self._settings.get_string("dashboard-prompt")
        max_age = self._settings.get_int("dashboard-max-age")
        argv = [
            "/usr/bin/python3", os.path.join(EXT_DIR, "helper", "dashboard.py"),
            "--session", self._session_id,
            "--prompt", prompt,
            "--max-age", str(max_age),
        ]
        if force:
            argv.append("--force")

        threading.Thread(target=self._run, args=(argv,), daemon=True).start()

    def _run(self, argv):
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=320)
            data = json.loads(proc.stdout)
        except Exception as exc:  # noqa: BLE001
            GLib.idle_add(self._show_error, str(exc))
            return
        GLib.idle_add(self._show_result, data)

    def _show_result(self, data):
        status = data.get("status")
        if status == "no-session":
            self._set_text(_("No session selected"))
            self._updated.set_text("")
        elif status == "session-not-found":
            self._set_text(_("The session no longer exists"))
            self._updated.set_text("")
        elif status == "error":
            self._set_text(_("Dashboard failed: %s") % data.get("error", "unknown"))
            self._updated.set_text("")
        else:
            text = data.get("text") or ""
            if text:
                self._text.set_markup(markdown_to_pango(text))
            else:
                self._set_text(_("(empty)"))
            if data.get("stale"):
                self._updated.set_text(_("stale"))
            elif data.get("fresh"):
                self._updated.set_text(_("just now"))
            else:
                self._updated.set_text(_("Updated: %s") % relative_age(data.get("generated_at")))
        return GLib.SOURCE_REMOVE

    def _show_error(self, message):
        self._set_text(_("Dashboard failed: %s") % message)
        self._updated.set_text("")
        return GLib.SOURCE_REMOVE

    def _on_refresh(self, _button):
        self._generate(force=True)

    def _session_workspace(self):
        for session in store.collect_sessions():
            if session.get("id") == self._session_id:
                return session.get("workspace") or os.path.expanduser("~")
        return os.path.expanduser("~")

    def _resume_session(self, _button=None):
        workspace = self._session_workspace()
        if not os.path.isdir(workspace):
            workspace = os.path.expanduser("~")
        subprocess.Popen([
            "ptyxis", "--standalone", "--working-directory", workspace,
            "--", "codewhale", "resume", self._session_id,
        ], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)

    def _recent_files(self, workspace, limit=5):
        recent = []
        count = 0
        try:
            for root, dirs, files in os.walk(workspace):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for name in files:
                    if name.startswith('.'):
                        continue
                    path = os.path.join(root, name)
                    try:
                        st = os.lstat(path)
                    except OSError:
                        continue
                    recent.append((st.st_mtime, os.path.relpath(path, workspace)))
                    count += 1
                    if count > 20000:
                        break
                if count > 20000:
                    break
        except OSError:
            pass
        recent.sort(reverse=True)
        return [name for _, name in recent[:limit]]

    def _deterministic_summary(self):
        workspace = self._session_workspace()
        lines = [f"**{_('Status')}:** {_('deterministic — no tokens')}"]
        lines.append("")
        lines.append(f"**{_('Workspace')}:** {workspace}")
        claude = os.path.join(workspace, "CLAUDE.md")
        lines.append(
            f"- **{_('CLAUDE.md')}:** "
            f"{_('present') if os.path.isfile(claude) else _('missing')}")
        if os.path.isdir(os.path.join(workspace, ".git")):
            try:
                branch = subprocess.run(
                    ["git", "-C", workspace, "branch", "--show-current"],
                    capture_output=True, text=True, timeout=10).stdout.strip()
                out = subprocess.run(
                    ["git", "-C", workspace, "status", "--porcelain"],
                    capture_output=True, text=True, timeout=10).stdout
                n = sum(1 for line in out.splitlines() if line.strip())
                lines.append(
                    f"- **{_('Git')}:** {_('branch')} {branch or '—'}, "
                    f"{n} {_('uncommitted')}")
            except (OSError, subprocess.SubprocessError):
                pass
        recent = self._recent_files(workspace)
        if recent:
            lines.append("")
            lines.append(f"**{_('Recently changed')}:**")
            for name in recent:
                lines.append(f"- {name}")
        return "\n".join(lines)

    def _show_deterministic(self):
        self._text.set_markup(markdown_to_pango(self._deterministic_summary()))
        self._updated.set_text(_("deterministic"))


class DashboardApp(Adw.Application):
    def __init__(self, session_id):
        super().__init__(application_id="biz.luff.CodewhaleLauncherDashboard")
        self._session_id = session_id

    def do_activate(self):
        window = self.get_active_window() or DashboardWindow(self, self._session_id)
        window.present()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Codewhale dashboard window")
    parser.add_argument("--session", default="", help="Session id to summarize")
    args = parser.parse_args()
    sys.exit(DashboardApp(args.session).run(sys.argv[:1]))
