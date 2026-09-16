import Adw from 'gi://Adw';
import Gio from 'gi://Gio';
import Gtk from 'gi://Gtk';

import {ExtensionPreferences, gettext as _} from 'resource:///org/gnome/Shell/Extensions/js/extensions/prefs.js';

export default class CodewhaleLauncherPreferences extends ExtensionPreferences {
    fillPreferencesWindow(window) {
        window.set_default_size(720, 480);
        const settings = this.getSettings();

        const page = new Adw.PreferencesPage();
        window.add(page);

        const group = new Adw.PreferencesGroup({
            title: _('Dashboard'),
            description: _('A compact “current status” of a session’s workspace, generated with codewhale and cached to save tokens. Open it from the dashboard button next to each session.'),
        });
        page.add(group);

        const promptRow = new Adw.ActionRow({
            title: _('Status prompt'),
            subtitle: _('Sent to `codewhale exec`. Kept generic — the workspace’s own instructions define what “status” means.'),
        });
        group.add(promptRow);

        const textView = new Gtk.TextView({
            hexpand: true,
            wrap_mode: Gtk.WrapMode.WORD_CHAR,
            top_margin: 6,
            bottom_margin: 6,
            left_margin: 6,
            right_margin: 6,
            monospace: true,
        });
        const buffer = textView.get_buffer();
        buffer.set_text(settings.get_string('dashboard-prompt'), -1);
        buffer.connect('changed', () => {
            settings.set_string(
                'dashboard-prompt',
                buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), false));
        });
        const promptScroll = new Gtk.ScrolledWindow({
            child: textView,
            min_content_height: 120,
            max_content_height: 240,
            vexpand: true,
        });
        group.add(promptScroll);

        const maxAgeRow = new Adw.SpinRow({
            title: _('Maximum cache age'),
            subtitle: _('Minutes before the status is regenerated even if the workspace has not changed.'),
            digits: 0,
            adjustment: new Gtk.Adjustment({
                lower: 5,
                upper: 10080,
                step_increment: 5,
                page_increment: 60,
            }),
        });
        settings.bind('dashboard-max-age', maxAgeRow, 'value',
            Gio.SettingsBindFlags.DEFAULT);
        group.add(maxAgeRow);
    }
}
