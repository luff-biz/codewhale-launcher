#!/usr/bin/env python3
"""Codewhale session history — GTK4/libadwaita companion window.

Runs as a separate process (GNOME Shell extensions cannot open GTK windows);
the extension merely spawns it. Lists every session in the Codewhale store,
lets you resume one, and removes entries Heroic-style: one dialog per session
with an opt-in checkbox for permanent deletion from the store.
"""

import gettext
import os
import subprocess
import sys
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk  # noqa: E402

EXT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(EXT_DIR, "helper"))
import store  # noqa: E402

UUID = "codewhale-launcher@luff.biz"
_ = gettext.translation(UUID, os.path.join(EXT_DIR, "locale"), fallback=True).gettext


def relative_age(epoch_secs):
    diff = max(0, time.time() - epoch_secs)
    if diff < 60:
        return _("just now")
    if diff < 3600:
        return _("%d min ago") % (diff // 60)
    if diff < 86400:
        return _("%d h ago") % (diff // 3600)
    return _("%d d ago") % (diff // 86400)


def short_workspace(path):
    if not path:
        return ""
    home = os.path.expanduser("~")
    display = f"~{path[len(home):]}" if path.startswith(home) else path
    parts = [p for p in display.split("/") if p]
    if len(parts) <= 2:
        return display
    return f"…/{parts[-1]}"


class HistoryWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, default_width=720, default_height=560,
                         title=_("Codewhale Sessions"))
        self._show_hidden = False

        self._search = Gtk.SearchEntry(placeholder_text=_("Search sessions…"))
        self._search.connect("search-changed", lambda *_a: self._list.invalidate_filter())

        hidden_toggle = Gtk.ToggleButton(icon_name="view-reveal-symbolic",
                                         tooltip_text=_("Show hidden sessions"))
        hidden_toggle.connect("toggled", self._on_toggle_hidden)

        header = Adw.HeaderBar()
        header.set_title_widget(Adw.Clamp(child=self._search, maximum_size=400))
        header.pack_end(hidden_toggle)

        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE,
                                 valign=Gtk.Align.START)
        self._list.add_css_class("boxed-list")
        self._list.set_filter_func(self._filter_row)
        self._list.set_placeholder(Gtk.Label(label=_("No sessions found"),
                                             margin_top=24, margin_bottom=24,
                                             css_classes=["dim-label"]))
        self._list.connect("row-activated", self._on_row_activated)

        clamp = Adw.Clamp(child=self._list, maximum_size=760,
                          margin_top=18, margin_bottom=18,
                          margin_start=12, margin_end=12)
        view = Adw.ToolbarView(content=Gtk.ScrolledWindow(child=clamp, vexpand=True))
        view.add_top_bar(header)
        self._toasts = Adw.ToastOverlay(child=view)
        self.set_content(self._toasts)

        self._reload()

    def _reload(self):
        self._list.remove_all()
        for session in store.collect_sessions():
            if session["hidden"] and not self._show_hidden:
                continue
            self._list.append(self._build_row(session))

    def _build_row(self, session):
        meta = [
            short_workspace(session["workspace"]),
            relative_age(session["updated_epoch"]),
            f"${session['cost_usd']:.2f}",
            session["model"],
        ]
        row = Adw.ActionRow(
            title=GLib.markup_escape_text(session["title"]),
            subtitle=GLib.markup_escape_text(" · ".join(m for m in meta if m)),
            activatable=True,
        )
        row.session = session
        if session["hidden"]:
            row.add_css_class("dim-label")
            restore = Gtk.Button(label=_("Restore"), valign=Gtk.Align.CENTER,
                                 css_classes=["flat"])
            restore.connect("clicked", self._on_restore, session)
            row.add_suffix(restore)
        trash = Gtk.Button(icon_name="user-trash-symbolic", valign=Gtk.Align.CENTER,
                           css_classes=["flat"])
        trash.connect("clicked", self._on_trash, session)
        row.add_suffix(trash)
        return row

    def _filter_row(self, row):
        needle = self._search.get_text().strip().lower()
        if not needle:
            return True
        session = row.session
        return needle in session["title"].lower() or needle in session["workspace"].lower()

    def _on_toggle_hidden(self, button):
        self._show_hidden = button.get_active()
        self._reload()

    def _on_row_activated(self, _list, row):
        session = row.session
        workspace = session["workspace"]
        if not workspace or not os.path.isdir(workspace):
            workspace = os.path.expanduser("~")
        subprocess.Popen(["ptyxis", "--new-window", "--working-directory", workspace,
                          "--", "codewhale", "resume", session["id"]])

    def _on_restore(self, _button, session):
        store.restore_session(session["id"])
        self._reload()

    def _on_trash(self, _button, session):
        dialog = Adw.AlertDialog(
            heading=_("Remove “%s”?") % session["title"],
            body=_("The session disappears from the launcher list but stays in the Codewhale store."),
        )
        check = Gtk.CheckButton(
            label=_("Also delete the session permanently from the Codewhale store"))
        note = Gtk.Label(
            label=_("This cannot be undone: the session can no longer be resumed and its costs vanish from the launcher statistics."),
            wrap=True, xalign=0, margin_start=30,
            css_classes=["dim-label", "caption"])
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(check)
        box.append(note)
        dialog.set_extra_child(box)
        dialog.add_response("cancel", _("Cancel"))
        dialog.add_response("remove", _("Remove"))
        dialog.set_response_appearance("remove", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", self._on_trash_response, session, check)
        dialog.present(self)

    def _on_trash_response(self, _dialog, response, session, check):
        if response != "remove":
            return
        if check.get_active():
            try:
                store.delete_session(session["id"])
            except OSError as exc:
                self._toasts.add_toast(Adw.Toast(title=_("Could not delete: %s") % exc))
        else:
            store.hide_session(session["id"])
        self._reload()


class HistoryApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="biz.luff.CodewhaleLauncherHistory")

    def do_activate(self):
        window = self.get_active_window() or HistoryWindow(self)
        window.present()


if __name__ == "__main__":
    sys.exit(HistoryApp().run(sys.argv))
