import St from 'gi://St';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';
import GObject from 'gi://GObject';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension, gettext as _} from 'resource:///org/gnome/shell/extensions/extension.js';

const REFRESH_SECONDS = 600;      // balance/costs every 10 min
const STALE_SECONDS = 60;         // refresh on menu open when data is older
const TITLE_MAX_CHARS = 44;

const BALANCE_WARN_USD = 5.0;     // yellow below
const BALANCE_CRIT_USD = 1.0;     // red below

function balanceColor(usd) {
    if (usd < BALANCE_CRIT_USD)
        return '#e74c3c';
    if (usd < BALANCE_WARN_USD)
        return '#f1c40f';
    return '#2ecc71';
}

function formatUsd(value) {
    return `$${value.toFixed(2)}`;
}

// Minimal printf-style substitution for translated strings (%s and %d only)
function fmt(template, ...args) {
    let i = 0;
    return template.replace(/%[sd]/g, () => String(args[i++]));
}

function relativeAge(epochSecs) {
    const diff = Math.max(0, Date.now() / 1000 - epochSecs);
    if (diff < 60)
        return _('just now');
    if (diff < 3600)
        return fmt(_('%d min ago'), Math.floor(diff / 60));
    if (diff < 86400)
        return fmt(_('%d h ago'), Math.floor(diff / 3600));
    return fmt(_('%d d ago'), Math.floor(diff / 86400));
}

function shortWorkspace(path) {
    if (!path)
        return '';
    const home = GLib.get_home_dir();
    const display = path.startsWith(home) ? `~${path.slice(home.length)}` : path;
    const parts = display.split('/').filter(p => p !== '');
    if (parts.length <= 2)
        return display;
    return `…/${parts[parts.length - 1]}`;
}

function truncate(text, max) {
    return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

const CodewhaleIndicator = GObject.registerClass(
class CodewhaleIndicator extends PanelMenu.Button {
    _init(extension) {
        super._init(0.5, 'Codewhale Launcher');

        this._extension = extension;
        this._lastUpdate = null;
        this._refreshing = false;

        const box = new St.BoxLayout({style_class: 'cw-panel-box'});
        box.add_child(new St.Icon({
            gicon: Gio.icon_new_for_string(
                `${extension.path}/icons/codewhale-symbolic.svg`),
            style_class: 'system-status-icon',
        }));
        this._panelLabel = new St.Label({
            text: '$–.––',
            y_align: Clutter.ActorAlign.CENTER,
            style_class: 'cw-panel-label',
        });
        box.add_child(this._panelLabel);
        this.add_child(box);

        this._buildMenu();
        this._refresh();

        this._refreshTimer = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT, REFRESH_SECONDS, () => {
                this._refresh();
                return GLib.SOURCE_CONTINUE;
            });
    }

    _buildMenu() {
        const headerItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        const headerBox = new St.BoxLayout({style_class: 'cw-header', x_expand: true});
        this._headerTitle = new St.Label({
            text: 'Codewhale',
            style_class: 'cw-header-title',
            x_expand: true,
            y_align: Clutter.ActorAlign.CENTER,
        });
        headerBox.add_child(this._headerTitle);
        this._updatedLabel = new St.Label({
            text: '',
            style_class: 'cw-header-updated',
            y_align: Clutter.ActorAlign.CENTER,
        });
        headerBox.add_child(this._updatedLabel);
        const refreshBtn = new St.Button({
            style_class: 'cw-refresh-btn',
            child: new St.Icon({icon_name: 'view-refresh-symbolic', icon_size: 14}),
        });
        refreshBtn.connect('clicked', () => this._refresh());
        headerBox.add_child(refreshBtn);
        headerItem.add_child(headerBox);
        this.menu.addMenuItem(headerItem);

        const statusItem = new PopupMenu.PopupBaseMenuItem({reactive: false, can_focus: false});
        const statusBox = new St.BoxLayout({vertical: true, style_class: 'cw-status-box', x_expand: true});
        this._balanceLabel = new St.Label({text: fmt(_('Balance: %s'), '–'), style_class: 'cw-balance'});
        statusBox.add_child(this._balanceLabel);
        this._costLabel = new St.Label({text: fmt(_('Today: %s · 7 days: %s'), '–', '–'), style_class: 'cw-costs'});
        statusBox.add_child(this._costLabel);
        statusItem.add_child(statusBox);
        this.menu.addMenuItem(statusItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        const newItem = new PopupMenu.PopupMenuItem(_('New session…'));
        newItem.insert_child_at_index(new St.Icon({
            icon_name: 'folder-new-symbolic',
            icon_size: 16,
            style_class: 'cw-item-icon',
        }), 0);
        newItem.connect('activate', () => this._newSession());
        this.menu.addMenuItem(newItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem(_('Recent sessions')));
        this._sessionsSection = new PopupMenu.PopupMenuSection();
        this.menu.addMenuItem(this._sessionsSection);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const historyItem = new PopupMenu.PopupMenuItem(_('Full history…'));
        historyItem.insert_child_at_index(new St.Icon({
            icon_name: 'document-open-recent-symbolic',
            icon_size: 16,
            style_class: 'cw-item-icon',
        }), 0);
        historyItem.connect('activate', () => {
            this.menu.close();
            this._spawn(['/usr/bin/python3', `${this._extension.path}/app/history.py`]);
        });
        this.menu.addMenuItem(historyItem);

        this.menu.connect('open-state-changed', (menu, open) => {
            if (!open)
                return;
            this._updateHeaderAge();
            const stale = !this._lastUpdate ||
                (Date.now() - this._lastUpdate.getTime()) / 1000 > STALE_SECONDS;
            if (stale)
                this._refresh();
        });
    }

    _newSession() {
        this.menu.close();
        const title = GLib.shell_quote(_('Codewhale: choose a project directory'));
        const script =
            `dir=$(zenity --file-selection --directory --title=${title}) || exit 0; ` +
            'exec ptyxis --new-window --working-directory "$dir" -- codewhale';
        this._spawn(['/bin/bash', '-lc', script]);
    }

    _resumeSession(session) {
        this.menu.close();
        let dir = session.workspace;
        if (!dir || !GLib.file_test(dir, GLib.FileTest.IS_DIR))
            dir = GLib.get_home_dir();
        this._spawn([
            'ptyxis', '--new-window', '--working-directory', dir,
            '--', 'codewhale', 'resume', session.id,
        ]);
    }

    _spawn(argv) {
        try {
            Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
        } catch (e) {
            logError(e, 'codewhale-launcher: failed to launch process');
            Main.notifyError('Codewhale Launcher', fmt(_('Launch failed: %s'), e.message));
        }
    }

    _refresh() {
        if (this._refreshing)
            return;
        this._refreshing = true;

        let proc;
        try {
            proc = Gio.Subprocess.new(
                ['/usr/bin/python3', `${this._extension.path}/helper/panel-data.py`],
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE);
        } catch (e) {
            logError(e, 'codewhale-launcher: failed to start data helper');
            this._refreshing = false;
            return;
        }

        proc.communicate_utf8_async(null, null, (source, res) => {
            this._refreshing = false;
            try {
                const [, stdout, stderr] = source.communicate_utf8_finish(res);
                const data = JSON.parse(stdout ?? '');
                this._lastUpdate = new Date();
                this._render(data);
            } catch (e) {
                logError(e, 'codewhale-launcher: unreadable helper output');
            }
        });
    }

    _render(data) {
        const provider = data.provider ?? 'unknown';
        this._headerTitle.set_text(`Codewhale · ${provider}`);

        if (data.balance) {
            const usd = parseFloat(data.balance.total);
            const text = Number.isNaN(usd) ? `$${data.balance.total}` : formatUsd(usd);
            this._panelLabel.set_text(text);
            this._balanceLabel.set_text(fmt(_('Balance: %s'), text));
            if (!Number.isNaN(usd)) {
                const color = balanceColor(usd);
                this._panelLabel.set_style(`color: ${color};`);
                this._balanceLabel.set_style(`color: ${color};`);
            }
        } else if (data.balance_supported === false) {
            // Provider without a balance API: show today's cost in the panel instead
            this._panelLabel.set_text(formatUsd(data.cost_today_usd));
            this._panelLabel.set_style('');
            this._balanceLabel.set_text(fmt(_('No balance lookup for “%s”'), provider));
            this._balanceLabel.set_style('');
        } else {
            this._panelLabel.set_text('$?');
            this._panelLabel.set_style('');
            this._balanceLabel.set_text(
                fmt(_('Balance unavailable (%s)'), data.balance_error ?? 'unknown'));
            this._balanceLabel.set_style('');
        }

        this._costLabel.set_text(fmt(_('Today: %s · 7 days: %s'),
            formatUsd(data.cost_today_usd), formatUsd(data.cost_week_usd)));

        this._sessionsSection.removeAll();
        const sessions = data.sessions ?? [];
        if (sessions.length === 0) {
            this._sessionsSection.addMenuItem(new PopupMenu.PopupMenuItem(
                _('No saved sessions'), {reactive: false}));
        }
        for (const session of sessions) {
            const item = new PopupMenu.PopupMenuItem(
                truncate(session.title, TITLE_MAX_CHARS));
            item.add_child(new St.Label({
                text: `${shortWorkspace(session.workspace)} · ${relativeAge(session.updated_epoch)}`,
                style_class: 'cw-session-meta',
                y_align: Clutter.ActorAlign.CENTER,
                x_expand: true,
                x_align: Clutter.ActorAlign.END,
            }));
            item.connect('activate', () => this._resumeSession(session));
            this._sessionsSection.addMenuItem(item);
        }

        this._updateHeaderAge();
    }

    _updateHeaderAge() {
        if (!this._lastUpdate) {
            this._updatedLabel.set_text('');
            return;
        }
        const secs = Math.max(0, Math.round((Date.now() - this._lastUpdate.getTime()) / 1000));
        this._updatedLabel.set_text(secs < 60
            ? fmt(_('%d s ago'), secs)
            : fmt(_('%d min ago'), Math.floor(secs / 60)));
    }

    destroy() {
        if (this._refreshTimer) {
            GLib.source_remove(this._refreshTimer);
            this._refreshTimer = null;
        }
        super.destroy();
    }
});

export default class CodewhaleLauncherExtension extends Extension {
    enable() {
        this._indicator = new CodewhaleIndicator(this);
        Main.panel.addToStatusArea(this.uuid, this._indicator);
    }

    disable() {
        this._indicator?.destroy();
        this._indicator = null;
    }
}
