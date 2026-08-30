# Codewhale Launcher

*Deutsche Übersetzung — maßgeblich ist die [englische README](README.md).*

GNOME-Shell-Extension: [Codewhale](https://github.com/)-Sessions direkt aus der
oberen Leiste starten und fortsetzen — ohne Terminal öffnen, `cd`,
`codewhale resume …` — plus Guthaben und Verbrauch im Blick.

## Funktionen

- **Panel-Anzeige**: Wal-Icon + aktuelles Guthaben des Providers
  (grün / gelb unter 5 $ / rot unter 1 $)
- **Neue Session…**: Verzeichnis-Dialog (neue Ordner lassen sich im Dialog anlegen),
  danach startet `codewhale` in einem neuen Terminal-Fenster im gewählten Verzeichnis
- **Letzte Sessions**: die 5 jüngsten Sessions mit Titel, Projekt und Alter —
  ein Klick führt `codewhale resume <id>` im richtigen Workspace aus
- **Vollständige Historie…**: öffnet ein GTK4/libadwaita-Fenster mit *allen*
  Sessions — durchsuchbar, Klick setzt fort. Der Papierkorb entfernt einen
  Eintrag im Heroic-Stil: standardmäßig wird die Session nur im Launcher
  ausgeblendet (der Codewhale-Store bleibt unangetastet, die Kosten zählen
  weiter); eine Checkbox mit ausdrücklicher Warnung löscht sie endgültig aus
  dem Store. Ausgeblendete Sessions lassen sich über den Kopfzeilen-Schalter
  wieder anzeigen und wiederherstellen.
- **Kosten heute / 7 Tage**: aggregiert aus dem lokalen Codewhale-Session-Store
- **Übersetzte Oberfläche**: Englisch plus 11 Sprachen (de, fr, es, it, pt, nl,
  da, sv, nb, hi, zh_CN) — die Sprache folgt automatisch der GNOME-System-Locale

## Voraussetzungen

| Was | Warum |
|---|---|
| GNOME Shell 47–50 | Extension-API |
| `codewhale` CLI im `PATH` | Sessions, Resume, API-Key-Weitergabe |
| Python ≥ 3.11 | Daten-Helper (`tomllib`) |
| `ptyxis` (Fedora-Standard-Terminal) | öffnet die Sessions |
| `zenity` | Verzeichnis-Dialog für neue Sessions |
| GTK4 + libadwaita + PyGObject | Historie-Fenster (auf Fedora Workstation vorinstalliert) |
| `msgfmt` (gettext) | kompiliert die Übersetzungen bei `install.sh` |

## Installation

```sh
git clone https://github.com/luff-biz/codewhale-launcher.git
cd codewhale-launcher
./install.sh
```

Bei der **Erstinstallation** unter Wayland: einmal ab- und wieder anmelden, dann

```sh
gnome-extensions enable codewhale-launcher@luff.biz
```

Spätere Updates: einfach erneut `./install.sh` — unter Wayland wirkt der neue Code
erst nach Ab-/Anmelden, unter X11 reicht `Alt+F2` → `r`.

## Provider-Unterstützung

Die Extension ist **nicht** auf DeepSeek festgenagelt. Der aktive Provider wird aus
der Codewhale-Konfiguration gelesen (`~/.codewhale/config.toml`, Schlüssel
`provider`) und im Menü-Kopf angezeigt.

- **Sessions, Resume, neue Sessions, Kostenanzeige** funktionieren mit **jedem**
  Provider — sie nutzen nur die Codewhale-CLI und den lokalen Session-Store.
- **Guthaben-Abfrage** braucht eine Balance-API des Providers. Hinterlegt ist bisher:

  | Provider | Guthaben | Quelle |
  |---|---|---|
  | `deepseek` | ✅ | `GET https://api.deepseek.com/user/balance` |
  | alle anderen | ➖ Panel zeigt stattdessen die Tageskosten | — |

  Weitere Provider lassen sich in `helper/panel-data.py` ergänzen
  (`BALANCE_PROVIDERS` + `parse_balance()`). Der API-Key kommt dabei immer über
  `codewhale auth print-api-key --provider <name>` — die Extension speichert oder
  zeigt nie einen Key.

## ⚠️ Bekannte Näherungen und Grenzen — bitte vor Nutzung lesen

1. **Kostenzuordnung ist eine Näherung.** Der Codewhale-Session-Store hält nur die
   *Gesamtkosten je Session*, keine Tagesscheiben. Eine Session zählt daher
   vollständig zu dem Tag, an dem sie **zuletzt aktualisiert** wurde. Beispiel: eine
   Session, die Montag 4 $ und Dienstag 1 $ verbraucht, erscheint am Dienstag mit
   5 $ unter „Today". Für Buchhaltung/Abrechnung sind die Zahlen des Providers
   maßgeblich, nicht diese Anzeige.
2. **„7 Tage" ist ein rollierendes Fenster** über `updated_at` der Sessions — mit
   derselben Zuordnungs-Näherung wie oben.
3. **Guthaben ≠ Limit.** Pay-as-you-go-Provider wie DeepSeek haben keine
   Nutzungslimits mit Reset-Fenstern (wie z. B. Claude-Abos); angezeigt wird das
   Konto-Guthaben in USD. Die Warnschwellen (5 $ / 1 $) sind Konstanten in
   `extension.js`.
4. **Aktualisierung** alle 10 Minuten, zusätzlich beim Menü-Öffnen (wenn Daten
   älter als 60 s) und per Refresh-Knopf — die Anzeige kann also bis zu 10 Minuten
   hinterherlaufen.
5. **Terminal fest auf Ptyxis** verdrahtet (`_newSession`/`_resumeSession` in
   `extension.js` anpassen für andere Terminals).
6. Gelöschte oder verschobene Projektverzeichnisse: Resume startet dann im
   Home-Verzeichnis statt im ursprünglichen Workspace.
7. **Ausblenden vs. Löschen.** Ausblenden merkt sich nur die Session-ID in
   `~/.config/codewhale-launcher/hidden.json` — der Codewhale-Store bleibt
   unangetastet, ausgeblendete Sessions zählen weiter in die Kostenanzeige.
   Endgültiges Löschen entfernt die Session-Datei (und einen gleichnamigen
   Checkpoint) aus `~/.codewhale/sessions/` — die Codewhale-CLI selbst hat
   keinen Lösch-Befehl.

## Architektur

| Datei | Aufgabe |
|---|---|
| `extension.js` | UI: Panel-Button, Menü, Prozess-Starts (GJS) |
| `helper/panel-data.py` | Datensammlung: Provider aus Config, Guthaben, Kosten, Session-Liste → ein JSON auf stdout |
| `helper/store.py` | geteilter Session-Store-Zugriff: Liste, Ausblenden/Wiederherstellen, Löschen |
| `app/history.py` | GTK4/libadwaita-Historie-Fenster (eigener Prozess) |
| `po/` | Übersetzungen (gettext; kompiliert von `install.sh`) |
| `stylesheet.css` | Optik |

Die Shell-Extension enthält keine Provider- oder Netzwerk-Logik; alles Datenseitige
steckt im Python-Helper und ist einzeln testbar:

```sh
python3 codewhale-launcher@luff.biz/helper/panel-data.py | python3 -m json.tool
```

## Mögliche Ausbaustufen

- Kostenverlauf / Diagramme im Historie-Fenster.
- Standard-Projektwurzel und Warnschwellen als Einstellungen (GSettings).
- Balance-APIs weiterer Provider, Terminal-Wahl.
- Muttersprachler-Review der maschinell erzeugten Übersetzungen.

## Lizenz

[GPL-3.0-or-later](LICENSE)
