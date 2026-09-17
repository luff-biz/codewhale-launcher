#!/usr/bin/env python3
"""Codewhale Launcher — About dialog."""

import gettext
import os
import sys

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

EXT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UUID = "codewhale-launcher@luff.biz"

os.environ["GSETTINGS_SCHEMA_DIR"] = os.path.join(EXT_DIR, "schemas")

_ = gettext.translation(UUID, os.path.join(EXT_DIR, "locale"), fallback=True).gettext


class AboutApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="biz.luff.CodewhaleLauncherAbout")

    def do_activate(self):
        win = Adw.Window(application=self, title=_("About Codewhale Launcher"),
                         default_width=420, default_height=560)
        win.connect("close-request", lambda *_: self.quit())

        about = Adw.AboutDialog(
            application_name="Codewhale Launcher",
            application_icon="codewhale-launcher",
            developer_name="Steffen Luff",
            comments=_(
                "Start and resume Codewhale sessions straight from the top "
                "bar — one-click new sessions, recent sessions, balance and "
                "costs, and a per-session dashboard. No terminal required."
            ),
            issue_url="https://github.com/luff-biz/codewhale-launcher/issues",
            copyright="© 2026 Steffen Luff",
            license_type=Gtk.License.GPL_3_0,
        )
        about.add_link(_("Source Code"), "https://github.com/luff-biz/codewhale-launcher")
        about.add_link(_("Buy Me a Coffee"), "https://ko-fi.com/steffenluff")
        about.add_link(_("More Apps"), "https://github.com/steffenluff")
        about.connect("closed", lambda *_: win.close())
        about.present(win)
        win.present()


if __name__ == "__main__":
    sys.exit(AboutApp().run(sys.argv[:1]))
