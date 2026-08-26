# Entwicklungsnotizen

Hintergrundwissen zu den beiden Tools: woher die Annahmen stammen, was
gegengeprüft wurde und wie die Entwicklungsumgebung aufgesetzt ist.
Bedienung und Aufbau stehen im [README](README.md).

---

## 1. Stand

| Teil | Status |
| --- | --- |
| Branding-Pipeline aus dem Vektor-Logo | fertig |
| Gemeinsames Design-System `dme_ui.py` | fertig, heller Look |
| AutoTuner Backup Tool | fertig, 36 Unit-Tests + GUI-Smoke-Test |
| MHD Lock Tool | fertig, 84 Unit-Tests + GUI-Smoke-Test mit Builder-Stub |
| Starter `dme_suite.py` | fertig, 17 Unit-Tests + GUI-Smoke-Test |
| Windows-Setup (Inno Setup) + CI-Build | fertig |
| README, Build-Skripte | fertig |

`python -m unittest discover -s tests` → 165 Tests, grün.

Produktname und Version stehen zentral in `dme_brand.py`
(`SUITE = "DME Innovation Tools"`, `VERSION = "2.2.0"`); beide Werkzeuge, das
Setup und der Dateiname der Setup-Datei ziehen daraus.

---

## 2. AutoTuner Backup Tool — Abweichungen vom Original

Nachbau von `github.com/CarbonCodeSystems/autotuner-backup-tool`. Ausgabeformat
(`contents.ini`, `how-to-use-backup.html`, Teilereihenfolge) ist unverändert.
Bewusst anders:

* Die Archivvorschau sortiert die Teile jetzt genauso wie der Schreibvorgang.
  Vorher konnten angezeigte Offsets von der erzeugten `.bin` abweichen, wenn die
  Teile im ZIP in anderer Reihenfolge lagen.
* Presets für MED17.1.1, MED17.5.x, MEVD17.2.x und MG1CP002 statt nur MED17.1.1;
  passt die Dateigröße zu einem Layout, wird es automatisch vorgeschlagen.
  MED17.1.1 und MEVD17.2.x teilen sich eine Gesamtgröße und schneiden identisch —
  der Hinweis nennt seitdem beide, weil der ECU-Name in die `contents.ini` des
  Kunden geht.
* **Die `how-to-use-backup.html` wird übernommen statt neu geschrieben.** Das
  Original tut Letzteres, mit einer fest verdrahteten englischen Fassung — der
  AutoTuner schreibt die Seite aber übersetzt (ein deutscher Read trägt die
  Offline-Meldung auf Deutsch und zwei zusätzliche `<meta>`-Zeilen). Sie wird
  jetzt mit der Aufteilung gemerkt und beim Zurückpacken durchgereicht.
* Proportionsbalken für die Aufteilung, reaktive Pfad-Hinweise, Inline-Banner
  statt modaler Popups, Tastenkürzel.
* Zwei Darstellungsfehler behoben: abgeschnittenes Eingabelabel und ein
  abgeschnittener „Browse"-Button im Scrollbereich (inneres Frame wurde nicht
  auf die Canvas-Breite gesetzt). Zusätzlich Mausrad-Unterstützung unter X11.

### 2.1 Gegenprobe an echten Backups

Fünf echte AutoTuner-Bench-Reads vom Kunden, alle mit demselben Gerät gelesen:

| Fahrzeug | ECU | Aufteilung | gesamt |
| --- | --- | --- | --- |
| Mercedes GLE 2018 | MG1CP002 | 8.388.608 + 524.288 | 8.912.896 |
| BMW X5 2019 (2×) | MG1CS201 | 8.388.608 + 868.352 | 9.256.960 |
| VW Caddy 2021 (2×) | MD1CS004 | 8.388.608 + 868.352 | 9.256.960 |

**Alle fünf gehen ZIP → BIN → ZIP byteidentisch durch** — jede Datei, gleiche
Reihenfolge, gleiche Archivgröße. Zwei Befunde kamen dabei heraus:

1. **Das MG1CP002-Preset war falsch.** Es stand auf 4 MB + 4 MB + 256 KB +
   256 KB — dieselbe Summe wie die Wirklichkeit, aber an den falschen Stellen
   geschnitten. Der echte Mercedes-Read liefert zwei Teile, 8 MB + 512 KB. Weil
   die Gesamtgröße das Preset auswählt, wäre der Fehler unsichtbar geblieben.
   Ein Test hält das Preset jetzt an der gemessenen Aufteilung fest.
2. **Die `how-to-use-backup.html` ist übersetzt** (siehe oben).

Nebenbefund ohne Handlungsbedarf: MG1CS201 und MD1CS004 haben dieselbe
Gesamtgröße, also denselben Schlüssel im Layout-Gedächtnis. Ihre Aufteilung ist
identisch, die Kollision damit folgenlos. Das gemerkte Layout hat ohnehin
Vorrang vor jedem Preset (`_auto_layout`), auch das hält ein Test fest.

Zur Herkunft: `AutoTunerBackupTool.exe` (PyInstaller, Python 3.13) und der
zugehörige Quelltext lagen zum Vergleich vor. `zip_to_bin`, `bin_to_zip`,
Teilereihenfolge und `contents.ini`-Format stimmen mit dem Original überein;
der einzige Unterschied in `part_sort_key` ist unsere Absicherung gegen einen
leeren Dateinamen.

---

## 3. MHD Lock Tool — Grundlagen

### 3.1 MHD+ Tuning Guide (Rev 1.01, 16.06.2021)

Seite 17 „Locking Tune Files with MHD+ Features" ist der relevante Teil:
Gelockt wird mit dem **MHD Map Encryption Tool** (Stand des Guides: v6.7), und
die verwendeten **XDFs müssen alle aktuellen MHD+ Tabellen enthalten** — sonst
gibt es Probleme mit der `*.mhd` beim Kunden. Der Rest des Guides beschreibt die
MHD+ Features (Antilag, Map Switching 1–4 Slots, FlexFuel mit FF/FF#2 und
Interpolationsfaktoren 0.00–2.00, Boost Ceiling Gear × RPM, CAN-ECA).
Nebenbefund: der leere CAL-Bereich für neue Tabellen ist `0xC3`-gefüllt, der
Patch aus `[romtype]_PATCH.xdf` muss laufen.

### 3.2 `TuningMapBuilder-v6.exe`

PE32 .NET-Konsolenanwendung, intern `XDF_Tools.exe`, Build 29.11.2019.
Aus den Strings rekonstruiert — sie arbeitet auf einem Verzeichnis und sucht:

| Glob | Bedeutung |
| --- | --- |
| `*.xdf` | genau eine |
| `*_original.bin` / `*.org` | genau eine (Stock-ROM) |
| `*.bin` | die getunte(n) Datei(en) |
| `*.toolkey` | genau eine |
| `*_vin.txt` | genau eine, VIN = 17 Zeichen |
| optional | `Tables2Add.txt`, `MHD tool tables to ignore.txt`, `MHD map conv stock tables to include.txt` |

Ergebnis: `*.mhd`. Erfolgsmarker `Map correctly written : `.
Fehlermeldungen (vollständig im Klassifikator `classify_line`):
`Error - one and only one xdf in the directory for programm `,
`Error - one and only one _original.bin or .org for programm `,
`Error - several xdfs detected for `, `Missing xdf for `,
`Error - software version mismatch between original  and dest `,
`Missing your .toolkey file`, `Error - several .toolkey detected.`,
`Invalid key`, `Missing YOURCLIENTVIN_vin.txt file in the directory.`,
`Error - VIN length is incorrect N / 17`, `Modification not in xdf at 0x…`,
`Table not in xdf, `, `N bytes not referenced in the XDFs`,
`NO modifications found`, `Could not determine the DME model`,
`Unsupported DME`, `Error - Failed to serialize.`, `******** CRC error `,
`******** Map read error `.
Am Ende steht `Press a key...` — der Exit-Code ist deshalb wertlos, gewertet
wird die Konsolenausgabe plus tatsächlich erzeugte `.mhd`.

Unterstützte DMEs laut Strings: MEVD1724/1725/1726/1728/1729/172G/172H/1784,
MEVD172_P, MEVD1726P, MG1ppc, N54 (IJE0S, I8A0S, IKM0S, INA0S), 9E60B, 98G0B,
9EI0B. Blocknamen: `BlockID_10_StartupBlock`, `BlockID_20_TPROT OTP`,
`BlockID_30_CustomerBlock`, `BlockID_40_APP1`, `BlockID_50_APP2`,
`BlockID_60_CAL`.

### 3.3 Gegenprobe an einem echten Arbeitsverzeichnis („M2 PX")

Ein vom Kunden bereitgestellter, von Hand gebauter Ordner hat drei Annahmen
korrigiert:

1. **Die `*_vin.txt` ist leer (0 Byte).** Die VIN steht ausschließlich im
   Dateinamen. Das Staging schreibt deshalb ebenfalls eine leere Datei.
2. **Die Builder-Exe liegt im Arbeitsverzeichnis.** Da in der Exe weder
   `GetCurrentDirectory` noch `BaseDirectory` als API-Referenz auftaucht, ist
   nicht sicher, gegen welches Verzeichnis relative Pfade aufgelöst werden.
   Das Tool kopiert den Builder deshalb standardmäßig ins Arbeitsverzeichnis und
   startet ihn dort — damit ist die Frage gegenstandslos.
3. **Nicht abgedeckte Änderungen sind kein Fehler.** Der reale, erfolgreiche
   Lauf hatte 11.625 geänderte Bytes in 219 Regionen, davon 1.886 Bytes in 62
   Regionen ohne passende XDF-Tabelle. Der Builder bringt eigene
   Tabellendefinitionen mit (`_ROMsDesc.cs`, `commonRomDef`, `public MHDTable`
   in den Strings). Der Coverage-Check meldet solche Stellen deshalb als
   Information mit Offsets, nicht als Warnung.

Der XDF-Parser wurde an der echten Definition geprüft: 1373 Tabellen,
2195 Adressbereiche, 0,14 s Parsezeit; die vollständige Vorprüfung inklusive
Diff zweier 8-MB-Images dauert rund 1,1 s.

Ebenfalls bestätigt: die Ausgabe heißt wie die getunte Datei
(`<name>.bin` → `<name>.mhd`), Dateinamen mit Leerzeichen inklusive. Deshalb ist
die Standard-Namensvorlage `{source}`, und das Staging behält Originalnamen bei.

### 3.4 XDF-Auswertung

Gelesen werden die `EMBEDDEDDATA`-Knoten aller `XDFTABLE`/`XDFCONSTANT`/
`XDFFLAG`/`XDFPATCH`/`XDFFUNCTION`-Elemente. Achsen ohne Adresse
(`<EMBEDDEDDATA />`, „autogen") werden übersprungen. Die Spannweite ergibt sich
aus `mmedelementsizebits`, `mmedrowcount`, `mmedcolcount` sowie
`mmedmajorstridebits`/`mmedminorstridebits`:

```
col_step = minor or element
row_step = major or cols * col_step
span     = (rows-1)*row_step + (cols-1)*col_step + element
```

`BASEOFFSET` wird nicht geraten: alle Interpretationen werden durchgerechnet und
die genommen, bei der sämtliche Bereiche in die ROM-Größe passen.

### 3.5 Kunden-Read aus der MHD-App

An einem echten Auftrag (S58, „Mathias S58 Multimap") gegengeprüft:

1. **Kunden schicken den Backup-Read als `<VIN>_<Programm-ID>_mapswitch.bin`**
   (z. B. `WBS42AY040FR10018_00005C64148205_mapswitch.bin`, 8 MB). Der
   Handgriff bisher: Datei zu `<Programm-ID>_original.bin` umbenennen. Die
   Datei aus dem erfolgreichen Arbeitsordner ist **byteidentisch** mit dem
   Kunden-Read — es ist wirklich nur ein Umbenennen.
2. **Die Programm-ID steht gepackt in beiden Images** (Read und Tune), das
   vorhandene ROM-ID-Matching greift also unverändert; die XDF heißt
   `<Programm-ID>.xdf`. `detect_rom_ids` findet auf diesen MG1-Images zusätzlich
   den ASCII-Füller `22222222222222` — unschädlich, er steht in beiden Images
   und wird nur für die Mismatch-Warnung verglichen.
3. **MHDs eigene Anleitung** (`MHD_Map_Encryption.docx`) empfiehlt als Basis das
   Original-Bin von MHDs GitHub; der reale, erfolgreiche Workflow verwendet den
   Kunden-Read als Original. Das Tool bildet den realen Workflow ab.

Umsetzung: `parse_customer_read` liest VIN und Programm-ID aus dem Namen
(Toleranz für Download-Kopien wie `… (1).bin`, die über `_is_stock_name` auch
als Original gelten), das Staging benennt den Read in `<ID>_original.bin` um.
Die Vorprüfung warnt, wenn die VIN vom Kunden-Dateinamen abweicht oder der Read
versehentlich als Tune gewählt wurde. End-to-End an den Echtdaten geprüft: das
gestagte Verzeichnis ist deckungsgleich mit dem handgebauten Ordner.

**Welche Datei das Original wird.** Ordner aus dem alten Handbetrieb enthalten
beides: den unveränderten Kunden-Read *und* die von Hand umbenannte Kopie. Beide
tragen dieselbe ROM-Nummer, die Auswahl hing also an der alphabetischen
Sortierung — bei einem kleingeschriebenen Präfix (`stock_…_original.bin`) hätte
der rohe Read gewonnen und wäre stillschweigend zur Diff-Basis geworden. Eine
bewusst auf `*_original.bin` benannte Datei hat deshalb Vorrang vor einem Read;
die Sortierung ist stabil, der eigene Ordner kommt weiterhin vor der Bibliothek.
Umgekehrt blockiert ein Read mit fremder Programm-ID nicht mehr die
Rückfallregel „die einzige Stock-ROM im Ordner" — er wird dort ignoriert, statt
den Ordner als mehrdeutig zu melden.

**Woher die VIN kommen darf.** Eine Programm-ID benennt einen Softwarestand,
kein Auto — zwei Kunden auf demselben Stand teilen sie sich. Eine automatisch
gesetzte VIN wird deshalb nur akzeptiert, wenn der Read **neben der getunten
Datei liegt** *und* seine Programm-ID zu diesem ROM gehört. Ein archivierter
Read aus dem Bibliotheksordner taugt damit weiterhin als Original, liefert aber
nie die VIN; liegen zwei Reads mit verschiedenen VINs im Auftragsordner, bleibt
das Feld leer und die Notiz sagt, dass hier nichts zu raten ist. Ebenso setzt
eine neue getunte Datei die VIN in der Oberfläche zurück, und Batch-Jobs erben
keine VIN vom vorherigen Auftrag. Alles andere könnte eine `.mhd` auf das
falsche Auto locken, ohne dass es jemand merkt. Nennt eine `<VIN>_vin.txt` im
Ordner ein anderes Auto als der Read, gewinnt weiterhin der Read — aber die
Abweichung wird gemeldet, statt sie stillschweigend zu übergehen.

**Die Warnung „ist das wirklich der Tune?"** greift nur noch beim exakten
Read-Namen. Tuner benennen die ausgelieferte Datei häufig nach der Quelle
(`…_mapswitch_STG2.bin`); dort löste die Warnung bei jedem Durchlauf grundlos
aus und hätte die Leute daran gewöhnt, sie auch im ernsten Fall zu überlesen.

### 3.6 Die XDF-Bibliothek als Ganzes

Der komplette MHD-XDF-Ordner (Plattform / DME / Softwarestand / Revision) wird
unter *Settings* als Bibliothek eingetragen; `LIBRARY_DEPTH = 6` deckt diese
Schachtelung ab. Entscheidend ist die Reihenfolge: **erst die ROM-Nummer, dann
die XDF.** Ist die Nummer aus dem Kunden-Read bekannt, wird die XDF rein über
den Dateinamen gefunden — kein weiterer Durchlauf durch das 8-MB-Image. Vorher
kostete jede Kandidatendatei einen eigenen Scan: gemessen 10,4 ms pro Datei,
also rund 21 s bei 2000 XDFs, und das im GUI-Thread. Jetzt sind es 0,07 s bei
2161 XDFs, die richtige Datei vier Ebenen tief.

Bleibt die ROM-Nummer unbekannt (kein Original im Auftragsordner), greift der
inhaltliche Abgleich weiter, aber gedeckelt durch `CONTENT_SCAN_BUDGET = 250`
(~2,7 s) mit einer Notiz statt einer hängenden Oberfläche. Gibt es mehrere XDFs
zu derselben ROM-Nummer, gewinnt die neueste (`_newest`) und die Notiz nennt
die gewählte Datei.

### 3.7 Ordner-Modus

Nicht jeder will, dass die App den Builder startet. `prepare_folder()` legt
deshalb dasselbe Arbeitsverzeichnis an wie ein Lock-Lauf, nur an einer
dauerhaften Stelle (Ausgabeordner, sonst neben der getunten Datei) und ohne
etwas auszuführen. Gegen den handgebauten Ordner aus „Mathias S58 Multimap"
gegengeprüft: alle sechs Dateien **byteidentisch** (SHA-256), keine Extras.

`prepare_only` in der Konfiguration macht daraus den Regelbetrieb — der
Ordner-Knopf wird zur Hauptaktion, *Lock now* wird nicht ausgegraut sondern
abgehängt (ein toter Knopf lädt zur Suche nach dem ein, was ihn belebt, und
hier gäbe es nichts), und `missing_setup()` verlangt den Builder-Pfad nicht
mehr. Der `.toolkey` bleibt in beiden Modi Pflicht, weil er in den Ordner
gehört.

Die Prüfung „was fehlt noch?" liegt bewusst in `missing_setup()` statt in der
GUI-Methode: so lässt sie sich ohne Anzeige testen — dieselbe Trennung wie bei
`prepare_folder()`.

---

## 4. Auslieferung

Eine Installationsdatei für den PC:
`dist\DME-Innovation-Tools-Setup-<version>.exe`, gebaut aus
`installer/dme-innovation-tools.iss` (Inno Setup 6).

* Installiert Starter plus beide Werkzeuge, Startmenü-Gruppe, optionale
  Desktop-Verknüpfung, Uninstaller; Deutsch und Englisch.
* `PrivilegesRequired=lowest` mit `PrivilegesRequiredOverridesAllowed=dialog`:
  standardmäßig Installation je Benutzer ohne UAC-Abfrage, „für alle Benutzer"
  ist im Assistenten wählbar.
* Die `AppId` ist ein fester, aus der Projektidentität abgeleiteter GUID —
  Updates ersetzen die vorhandene Installation, statt sie zu duplizieren.
* Die Einstellungsdatei unter `%APPDATA%\DME Innovation` bleibt bei einer
  Deinstallation erhalten (Builder-Pfad).
* Das `.iss` ist bewusst reines ASCII — Inno Setup verlangt sonst eine BOM.
* Der Starter findet die Werkzeuge relativ zu sich selbst: im Build neben der
  `.exe`, aus den Quellen neben dem Skript (`resolve_tool`). Unter Windows wird
  aus den Quellen `pythonw.exe` bevorzugt, damit kein Konsolenfenster aufblitzt.
* Ein Test hält Starter, `build_exe.bat` und `.iss` synchron: ein umbenanntes
  Werkzeug fällt sofort auf, statt erst beim Setup.

---

## 5. Entwicklungsumgebung

* `python3` = 3.11 **ohne** tkinter. **`/usr/bin/python3.12` hat tkinter 8.6** —
  damit laufen die GUI-Tests.
* Für die Asset-Erzeugung: `pip install pymupdf pillow`.
  Für die GUI-Tests: `apt install python3-tk xvfb x11-apps`.
* Screenshot headless:

  ```bash
  xvfb-run -a -s "-screen 0 1040x820x24" /usr/bin/python3.12 tests/smoke_gui_mhd_lock.py
  python3 tools/xwd2png.py /tmp/shot_mhd_lock.xwd docs/screenshot-mhd-lock-lock.png
  ```

* Nicht im Repo (flüchtig bzw. fremdes Eigentum): `TuningMapBuilder-v6.exe`,
  `MHD_Suite_Tuning_Guide.pdf`, das M2-PX-Beispielverzeichnis.
  Das Logo liegt dagegen dauerhaft unter `assets/logo-source/`.

---

## 6. Bewusste Entscheidungen

* **Oberfläche auf Englisch**, Dokumentation auf Deutsch — die Terminologie
  (iflash/dflash, toolkey, XDF, map slot) ist ohnehin englisch. Umstellbar.
* **Heller Grund, weiße Karten, eine Akzentfarbe.** Der dunkle Look bis
  einschließlich 1.4.1 steht in der Git-Historie; eine Umschaltmöglichkeit
  wäre ein eigenes Vorhaben, weil alle Widgets die Farben beim Import lesen.
  Beide Werkzeuge teilen sich `dme_ui.py`, also wechselt der AutoTuner mit.
* **Amber `#FFAA00` als einziger Akzent**; das Logo bleibt schwarz/weiß.
  Auf hellem Grund füllt das Amber nur (Pille, Trennstreifen, Cursor) — als
  Schriftfarbe trägt es 1,9:1. Dafür gibt es `ACCENT_INK` `#9A6300`, denselben
  Ton bei 5,1:1. `tests/test_palette.py` rechnet jede Kombination nach und
  fällt, sobald wieder jemand `fg=ACCENT` schreibt.
* **Gemeinsame Module statt Einzeldateien**: `dme_ui.py` und `dme_brand.py`
  sorgen dafür, dass beide Tools identisch aussehen. PyInstaller bündelt sie
  automatisch mit.
* **Ein Programm, drei Betriebsarten** (seit 2.2.0). Drei `--onefile`-Builds
  hießen dreimal Python plus tkinter im Setup — 36 MB, davon zwei Drittel
  Kopie. Jetzt baut `build_exe.bat` nur `dme_suite.py`, mit
  `--hidden-import` für die beiden Werkzeugmodule (nichts importiert sie auf
  Modulebene, PyInstaller fände sie sonst nicht). `resolve_tool` gibt im
  gefrorenen Zustand `[sys.executable, "--tool", key]` zurück, `main()`
  reicht an `<modul>.main()` weiter. Getrennte Prozesse bleiben: ein Absturz
  im einen Werkzeug lässt das andere stehen.
  Der Installer legt weiterhin drei Startmenü-Einträge an, die beiden
  Werkzeuge mit `Parameters:`. `[InstallDelete]` räumt die beiden alten
  `.exe` weg — Inno entfernt nur, was es selbst ausliefert.
* **Jeder Lock-Job bekommt ein eigenes Arbeitsverzeichnis.** Im Handbetrieb
  liegen oft mehrere Tunes in einem Ordner; getrennte Läufe machen Fehler
  eindeutig einem Kunden zuordenbar und schließen die „one and only one"-Fehler
  des Builders aus.
* **Erfolg wird an der Konsolenausgabe gemessen**, nicht am Exit-Code.
