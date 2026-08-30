# Codewhale Launcher

*[Deutsche Version](README.de.md)*

GNOME Shell extension: start and resume [Codewhale](https://github.com/) sessions
straight from the top bar — no opening a terminal, `cd`-ing into the project,
`codewhale resume …` — plus your balance and usage costs at a glance.

## Features

- **Panel display**: whale icon + current provider balance
  (green / yellow below $5 / red below $1)
- **New session…**: directory dialog (new folders can be created right in the
  dialog), then `codewhale` starts in a new terminal window in the chosen directory
- **Recent sessions**: the 5 most recent sessions with title, project, and age —
  one click runs `codewhale resume <id>` in the right workspace
- **Full history…**: opens a GTK4/libadwaita companion window listing *every*
  session — searchable, click to resume. The trash button removes an entry
  Heroic-style: by default the session is only hidden from the launcher (the
  Codewhale store is untouched and its costs still count); an opt-in checkbox
  with an explicit warning deletes it permanently from the store. Hidden
  sessions can be shown again and restored via the header toggle.
- **Costs today / 7 days**: aggregated from the local Codewhale session store
- **Translated UI**: English plus 11 languages (de, fr, es, it, pt, nl, da, sv,
  nb, hi, zh_CN) — the language follows the GNOME system locale automatically

## Requirements

| What | Why |
|---|---|
| GNOME Shell 47–50 | extension API |
| `codewhale` CLI in `PATH` | sessions, resume, API key hand-off |
| Python ≥ 3.11 | data helper (`tomllib`) |
| `ptyxis` (Fedora's default terminal) | opens the sessions |
| `zenity` | directory dialog for new sessions |
| GTK4 + libadwaita + PyGObject | full-history window (preinstalled on Fedora Workstation) |
| `msgfmt` (gettext) | compiles the translations during `install.sh` |

## Installation

```sh
git clone https://github.com/luff-biz/codewhale-launcher.git
cd codewhale-launcher
./install.sh
```

On the **first install** under Wayland: log out and back in once, then

```sh
gnome-extensions enable codewhale-launcher@luff.biz
```

Later updates: just run `./install.sh` again — under Wayland the new code takes
effect after logging out and back in, under X11 `Alt+F2` → `r` is enough.

## Provider support

The extension is **not** hardwired to DeepSeek. The active provider is read from
the Codewhale configuration (`~/.codewhale/config.toml`, key `provider`) and shown
in the menu header.

- **Sessions, resume, new sessions, and the cost display** work with **any**
  provider — they only use the Codewhale CLI and the local session store.
- **Balance lookup** needs a balance API on the provider's side. Currently wired up:

  | Provider | Balance | Source |
  |---|---|---|
  | `deepseek` | ✅ | `GET https://api.deepseek.com/user/balance` |
  | all others | ➖ the panel shows today's costs instead | — |

  Additional providers can be added in `helper/panel-data.py`
  (`BALANCE_PROVIDERS` + `parse_balance()`). The API key is always obtained via
  `codewhale auth print-api-key --provider <name>` — the extension never stores
  or displays a key.

## ⚠️ Known approximations and limitations — please read before relying on it

1. **Cost attribution is an approximation.** The Codewhale session store only keeps
   *total costs per session*, not per-day slices. A session therefore counts
   entirely towards the day it was **last updated**. Example: a session that spends
   $4 on Monday and $1 on Tuesday shows up on Tuesday with $5 under "Today". For
   accounting/billing, the provider's numbers are authoritative, not this display.
2. **"7 days" is a rolling window** over the sessions' `updated_at` — with the same
   attribution approximation as above.
3. **Balance ≠ limit.** Pay-as-you-go providers like DeepSeek have no usage limits
   with reset windows (like e.g. Claude subscriptions); what's shown is the account
   balance in USD. The warning thresholds ($5 / $1) are constants in `extension.js`.
4. **Refresh** every 10 minutes, additionally on menu open (when data is older than
   60 s) and via the refresh button — so the display can lag by up to 10 minutes.
5. **Terminal hardwired to Ptyxis** (adapt `_newSession`/`_resumeSession` in
   `extension.js` for other terminals).
6. Deleted or moved project directories: resume then starts in the home directory
   instead of the original workspace.
7. **Hiding vs. deleting.** Hiding a session only records its id in
   `~/.config/codewhale-launcher/hidden.json` — the Codewhale store is untouched
   and hidden sessions still count towards the cost display. Permanent deletion
   removes the session file (and a same-id checkpoint file) from
   `~/.codewhale/sessions/` — the Codewhale CLI itself has no delete command.

## Architecture

| File | Job |
|---|---|
| `extension.js` | UI: panel button, menu, process launches (GJS) |
| `helper/panel-data.py` | data collection: provider from config, balance, costs, session list → one JSON on stdout |
| `helper/store.py` | shared session-store access: list, hide/restore, delete |
| `app/history.py` | GTK4/libadwaita full-history window (own process) |
| `po/` | translations (gettext; compiled by `install.sh`) |
| `stylesheet.css` | looks |

The shell extension contains no provider or network logic; everything data-related
lives in the Python helper and can be tested on its own:

```sh
./codewhale-launcher@luff.biz/helper/panel-data.py | python3 -m json.tool
```

## Possible next steps

- Cost history / charts in the companion app.
- Default project root and warning thresholds as settings (GSettings).
- Balance APIs for more providers, terminal choice.
- Native-speaker review of the machine-generated translations.

## License

[GPL-3.0-or-later](LICENSE)
