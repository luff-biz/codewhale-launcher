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

        const resetRow = new Adw.ButtonRow({
            title: _('Reset prompt to default'),
            start_icon_name: 'edit-undo-symbolic',
        });
        resetRow.connect('activated', () => {
            settings.reset('dashboard-prompt');
            buffer.set_text(settings.get_string('dashboard-prompt'), -1);
        });
        group.add(resetRow);

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

        const aiRow = new Adw.SwitchRow({
            title: _('AI dashboard'),
            subtitle: _('Costs tokens — the status is generated with codewhale (LLM).'),
        });
        settings.bind('dashboard-ai', aiRow, 'active', Gio.SettingsBindFlags.DEFAULT);
        group.add(aiRow);

        const detRow = new Adw.ActionRow({
            title: _('Deterministic mode'),
            subtitle: _('Without AI the status is built directly from the workspace — CLAUDE.md, git status and recently changed files — without tokens.'),
        });
        detRow.set_activatable(false);
        group.add(detRow);
    }
}
