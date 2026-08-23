# Arbeitsstand — DME Innovation Tools

Stand: laufende Session. Dieses Dokument ist die Gedächtnisstütze: was fertig ist,
was noch offen ist und alle Erkenntnisse, die für die Weiterarbeit nötig sind.

---

## 1. Auftrag (in der Reihenfolge der Anfragen)

1. **AutoTuner Backup Tool** aus `github.com/CarbonCodeSystems/autotuner-backup-tool`
   „exakt mit allen Funktionen" nachbauen — **mit dem DME-Innovation-Logo**.
2. **MHD Lock Tool** — ein Tool, das das Locken von MHD+ Tune-Files
   **automatisch** macht (Grundlage: `MHD_Suite_Tuning_Guide.pdf` + die
   hochgeladene `TuningMapBuilder-v6.exe`).
3. **Design modern und übersichtlicher** — gilt für beide Tools.

Zielrepo/Branch: `dmeinnovation777-droid/tools`, Branch
`claude/autotuner-backup-tool-logo-9fxtnm`.

---

## 2. Was fertig ist

### Branding-Pipeline
* Logo-Master liegt als Vektor in `assets/logo-source/DME-Innovation.ai`
  (Illustrator-Datei mit PDF-Stream, 967.96 × 432.26 pt, schwarze Wortmarke
  „DME INNOVATION" auf transparent).
* `tools/generate_assets.py` rendert daraus alle Assets und schreibt die
  base64-Blobs direkt in `dme_brand.py`:
  * `assets/dme-icon.ico` — multi-size (16/24/32/48/64/128/256), amber Kachel
    (#FFAA00) mit schwarzem „DME"-Block; bei 16 px noch lesbar.
  * `assets/dme-icon.png`, `assets/dme-logo-black.png`, `assets/dme-logo-white.png`
  * Header-Wortmarke: weiß auf `#15171C`, 179×80 px (wird per `subsample(2,2)`
    auf 40 px Höhe dargestellt).
  * Aufruf: `python3 tools/generate_assets.py` (bzw. `--check` für CI).
  * Benötigt `pymupdf` + `pillow` (nur zum Regenerieren, nicht zur Laufzeit).

### Gemeinsames Design-System
* `dme_ui.py` (~600 Zeilen, reines tkinter, keine Fremdpakete):
  Palette (BG `#0E0F13`, SURFACE `#15171C`, CARD `#181B21`, BORDER `#272C35`,
  Akzent DME-Amber `#FFAA00`), Font-Auflösung mit Fallback-Kette,
  ttk-Styles (flache Scrollbars ohne Pfeile, dunkles Treeview),
  Widgets: `Header`, `TabBar` (Underline-Tabs), `Card`, `PathRow`,
  `LabeledEntry`, `Banner` (Inline-Statusmeldung statt Popup), `StatusBar`
  (Status-Dot), `VScroll`, `LogView` (Monospace + Farbtags + Auto-Hide-Bars),
  `Table` (Treeview), `button`/`icon_button`/`entry`, `ToolTip`,
  `reveal_in_file_manager`.
* `dme_brand.py` — Vendor-Name, eingebettete Logo-Blobs, `apply_window_icon()`,
  `header_logo()`.

### AutoTuner Backup Tool (`autotuner_tool.py`) — FERTIG
Funktional 1:1 zum Original, Design komplett neu:
* Kernlogik: `zip_to_bin`, `bin_to_zip`, `build_contents_ini`, `parse_ini`,
  `format_bytes`, `part_sort_key`, `read_archive_info`, `HOW_TO_USE_HTML`.
  `contents.ini`-Format und `how-to-use-backup.html` byte-identisch zum Original.
* GUI: Header mit Logo, Underline-Tabs „ZIP → BIN" / „BIN → ZIP",
  Cards, Sticky-Actionbar unten, Inline-Banner statt Popups,
  „Show in folder"-Action, Statusleiste, Shortcuts (Ctrl+O, F5, Ctrl+Enter).
* Neu ggü. Original (bewusst, in README dokumentieren):
  * Vorschau listet Teile in *derselben* Reihenfolge, in der sie ins .bin
    geschrieben werden (Original zeigte teils falsche Offsets).
  * Presets: MED17.1.1, MED17.5.x, MEVD17.2.x (Original: nur MED17.1.1);
    Auto-Preset, wenn die .bin-Größe zu einem Layout passt.
  * Proportionsbalken, der die Aufteilung des .bin visualisiert.
  * Reaktive Pfad-Hinweise, Scroll-Fixes, Linux-Mausrad.
* Tests: `tests/test_autotuner_core.py` — 13 Tests, alle grün
  (`python3 -m unittest discover -s tests`).
* GUI-Smoke-Test lief headless unter Xvfb inkl. Screenshots — beide Tabs OK.

---

## 3. Was noch offen ist

### MHD Lock Tool (`mhd_lock_tool.py`) — NOCH NICHT GESCHRIEBEN
Design steht komplett (siehe Abschnitt 4). Zu bauen:
1. Kernlogik (testbar, ohne GUI): VIN-Validierung, Binär-Diff,
   XDF-Parser + Coverage-Check, Staging, Runner, Output-Parser, Config.
2. GUI mit `dme_ui`: Tabs „Lock" (Einzeljob), „Batch", „Settings".
3. `tests/test_mhd_lock_core.py`.
4. GUI-Smoke-Test unter Xvfb.

### Danach noch offen (für beide Tools)
* `README.md` (deutsch) — Übersicht, Bedienung, Build, Änderungen ggü. Original.
* `build_exe.bat` — PyInstaller-Build für beide Tools (Icon aus `assets/dme-icon.ico`).
* `.github/workflows/build-windows-exe.yml` — Windows-Runner baut beide .exe
  (auf Linux ist kein Windows-Build möglich).
* Screenshots ins Repo (`docs/`), Commit + Push auf den Branch.

---

## 4. MHD Lock Tool — vollständiges Design (aus der Analyse)

### 4.1 Erkenntnisse aus `MHD_Suite_Tuning_Guide.pdf` (Rev 1.01, 16.06.2021)
* MHD+ Feature-Set für F-Serie (MEVD-DME): N13, N55 (PWG/EWG), S55.
  Features: Antilag, CAN-ECA, Motiv Re|Flex, On-the-fly Map Switching (1–4 Slots),
  FlexFuel (Main FF + FF#2, Interpolationsfaktoren 0.00–2.00), neue/Custom-Tables
  (Boost Ceiling Gear × RPM), MHD+ DTCs.
* **Seite 17 „Locking Tune Files with MHD+ Features"** ist der relevante Teil:
  * Es wird die **MHD Map Encryption Tool** benutzt (Stand des Guides: v6.7).
  * Vorher müssen die **XDFs** auf den aktuellen Stand gebracht werden
    (offizielle MHD-GitHub-XDFs mit allen MHD+ Tabellen).
  * Dann wird die Kundendatei „wie gewohnt" gelockt → Ergebnis: `*.mhd`.
* Leerer CAL-Bereich für neue Tabellen ist per Default `0xC3` — der Patch aus
  `[romtype]_PATCH.xdf` muss laufen, sonst Junk-Daten in den neuen Tabellen.

### 4.2 Erkenntnisse aus `TuningMapBuilder-v6.exe`
* PE32 .NET-Konsolenanwendung, intern **`XDF_Tools.exe`** (FileVersion 1.0.0.0,
  Build-Datum 29.11.2019), 425 472 Bytes.
* Arbeitet offensichtlich **auf einem Verzeichnis** (scannt per Glob), CLI-Hilfe
  gibt es nicht. Am Ende `Console`-Prompt **„Press a key…"** → beim Automatisieren
  stdin bedienen bzw. Exit-Code nicht als alleiniges Erfolgssignal nehmen.
* Gesuchte Dateien im Arbeitsverzeichnis (Globs aus den Strings):
  * `*.xdf` — genau eine
  * `*_original.bin` bzw. `*.org` — genau eine (Stock-ROM)
  * die getunte(n) `*.bin`
  * `*.toolkey` — genau eine (Lizenz-/Tuner-Schlüssel von MHD)
  * `*_vin.txt` — genau eine, Dateiname `YOURCLIENTVIN_vin.txt`, VIN = 17 Zeichen
  * optional: `Tables2Add.txt`, `MHD tool tables to ignore.txt`,
    `MHD map conv stock tables to include.txt`
* Ergebnis: `*.mhd`
* Meldungen (Marker fürs Parsen der Konsolenausgabe):
  * Erfolg: `Map correctly written : `
  * Info: `opened BIN: `, `Total bytes changed: `, `Restrict to VIN : `,
    `Found N tables`, `Removing common `
  * Fehler: `Error - one and only one xdf in the directory for programm `,
    `Error - one and only one _original.bin or .org for programm `,
    `Error - several xdfs detected for `, `Missing xdf for `,
    `Error - software version mismatch between original  and dest `,
    `Missing your .toolkey file`, `Error - several .toolkey detected.`,
    `Invalid key`, `Missing YOURCLIENTVIN_vin.txt file in the directory.`,
    `Error - several YOURCLIENTVIN_vin.txt in the directory.`,
    `Error - VIN length is incorrect N / 17`,
    `Modification not in xdf at 0x… length …`, `Table not in xdf, `,
    `N bytes not referenced in the XDFs`, `NO modifications found`,
    `Could not determine the DME model`, `Unsupported DME`,
    `Error - Failed to serialize.`, `******** CRC error `,
    `******** Map read error `, `Missing table at `
  * Warnungen: `WARNING: overlapping blocks:`, `MUST FIX axis ? `,
    `Skipped axis : `, `Missing tables:`
* Unterstützte DMEs laut Strings: MEVD1724/1725/1726/1728/1729/172G/172H/1784,
  MEVD172_P, MEVD1726P, MG1ppc sowie N54-ROMs (IJE0S, I8A0S, IKM0S, INA0S),
  9E60B, 98G0B, 9EI0B. Blocknamen: `BlockID_10_StartupBlock`,
  `BlockID_20_TPROT OTP`, `BlockID_30_CustomerBlock`, `BlockID_40_APP1`,
  `BlockID_50_APP2`, `BlockID_60_CAL`.
  Beispiel-ROM-IDs (14 Hex): `00005BA8134601`, `00005D55327806`, `00001A841D1401`, …
* **Wichtig:** Das Lock Tool reimplementiert nichts davon und umgeht nichts —
  es steuert die **offizielle, lizenzierte** MHD-Exe des Tuners. Die Exe selbst
  wird NICHT ins Repo committet (siehe `.gitignore`).

### 4.3 Geplanter Funktionsumfang
1. **Job-Formular**: Kunde, VIN, Stock-.bin, getunte .bin(s), XDF, `.toolkey`,
   Ausgabeordner.
2. **Preflight-Validierung** (läuft auch ohne die Vendor-Exe, plattformunabhängig):
   * genau eine `.toolkey`, vorhanden
   * VIN: 17 Zeichen, `[A-HJ-NPR-Z0-9]`, Großschreibung (kein I/O/Q)
   * Stock- und Tuned-.bin gleich groß; Anzahl geänderter Bytes;
     zusammenhängende Änderungs-Regionen (Start, Länge, Hex-Vorschau)
   * 0 geänderte Bytes → Abbruch vor dem Lauf (`NO modifications found`)
   * XDF: gültiges XML, Titel, ROM-Größe aus `<REGION size=…>`
   * **XDF-Coverage-Check** (der eigentliche Mehrwert): alle
     `EMBEDDEDDATA`-Adressen (Tabellen, Achsen, Konstanten, Patch-Entries)
     einsammeln, Spannweite über `mmedelementsizebits`/`rowcount`/`colcount`
     (+ Stride) berechnen, mit den geänderten Regionen abgleichen →
     meldet vorab genau das, woran der Vendor-Lauf sonst scheitert
     („Modification not in xdf at 0x…"), und benennt die betroffenen Tabellen.
     BASEOFFSET-Interpretation automatisch bestimmen (Kandidaten
     `addr`, `addr-base`, `addr+base`; die nehmen, bei der alle Ranges in die
     Datei passen). Ergebnis ist **beratend**, nicht blockierend.
   * ROM-/Software-ID-Heuristik: ASCII-Muster `[0-9A-F]{14}` und
     `swfl_/btld_/swfk_ + 8 Hex` in Stock vs. Tuned vergleichen →
     warnt vor „software version mismatch".
3. **Staging**: sauberes Temp-Verzeichnis mit exakt den erwarteten Dateinamen
   (`<stem>_original.bin`, `<name>.xdf`, `<tuned>.bin`, `<VIN>_vin.txt`,
   `<name>.toolkey`, optionale Extras). Verhindert die „one and only one"-Fehler.
   Getunte Datei umbenennen, falls sie auf `_original.bin`/`.org` endet.
4. **Run**: Vendor-Exe mit `cwd=staging` starten, stdout live streamen
   (Thread + Queue + `after()`), Zeilen klassifizieren und farbig ins `LogView`.
   Optional: Arbeitsverzeichnis als Argument übergeben, freie Zusatzargumente,
   Timeout, `\n` auf stdin wegen „Press a key…".
5. **Collect**: erzeugte `.mhd` einsammeln, nach Vorlage umbenennen
   (`{customer}_{vin}_{date}`), in den Ausgabeordner verschieben,
   Job-Log daneben schreiben.
6. **Batch-Tab**: Job-Queue (Treeview) mit Editor-Panel für die selektierte
   Zeile, „Add files…", CSV-Import (`customer,vin,tuned_bin[,stock_bin][,xdf]`),
   Report-Export, sequentieller Lauf mit Fortschritt.
7. **Settings-Tab**: Pfad zur Vendor-Exe, Zusatzargumente, Ausgabeordner,
   Namensvorlage, Staging behalten ja/nein, nach Erfolg Ordner öffnen, Timeout.
   Persistenz als JSON unter `%APPDATA%/DME Innovation/mhd_lock_tool.json`
   (macOS: `~/Library/Application Support/…`, Linux: `~/.config/…`).
8. **Dry-Run**: alles außer dem Vendor-Aufruf — funktioniert auch auf Linux/macOS.

---

## 5. Entwicklungsumgebung (Container)

* Arbeitsverzeichnis `/home/user/Tools`, Git-Repo, Branch
  `claude/autotuner-backup-tool-logo-9fxtnm`.
* `python3` = 3.11 (ohne tkinter). **`/usr/bin/python3.12` hat tkinter 8.6** —
  damit laufen die GUI-Smoke-Tests.
* Installiert: `pymupdf`, `pillow`, `numpy`, `py7zr` (pip),
  `python3-tk`, `xvfb`, `x11-apps` (apt).
* GUI-Smoke-Test:
  `xvfb-run -a -s "-screen 0 1000x800x24" /usr/bin/python3.12 <script>.py`
  Screenshot mit `xwd -root -silent -out shot.xwd`, Umwandlung mit dem
  xwd→PNG-Parser im Scratchpad (`xwd2png.py`).
* Scratchpad:
  `/tmp/claude-0/-home-user-Tools/e3ea80d2-2bc2-5088-97fe-97bcf4969d4a/scratchpad`
  (enthält: `upstream/` = geklontes Original-Repo, `tmb/TuningMapBuilder-v6.exe`,
  Smoke-Test-Skripte, Screenshots). **Achtung: Scratchpad und Uploads sind
  flüchtig — Wichtiges gehört ins Repo.**
* Uploads (flüchtig):
  `/root/.claude/uploads/e3ea80d2-2bc2-5088-97fe-97bcf4969d4a/`
  → `45bdb2ac-DMEai.ai` (Logo, bereits ins Repo kopiert),
    `9904903b-TuningMapBuilderv6.7z`, `b88a29d4-MHD_Suite_Tuning_Guide.pdf`.

## 6. Bewusste Entscheidungen

* **UI-Sprache Englisch** (wie das Original und die MHD/AutoTuner-Terminologie),
  Dokumentation auf Deutsch. Auf Wunsch leicht umstellbar.
* **Amber `#FFAA00` als Akzent** beibehalten (passt zur Icon-Kachel, typisch
  Tuning-Werkzeug); das Logo selbst bleibt schwarz/weiß wie im Original.
* Statt einer einzelnen Datei pro Tool jetzt **gemeinsame Module**
  (`dme_ui.py`, `dme_brand.py`) — beide Tools sehen dadurch identisch aus.
  PyInstaller bündelt die Importe automatisch.
* Weder die Vendor-Exe noch das MHD-PDF werden ins Repo committet
  (fremdes Copyright bzw. Lizenzdatei); `.toolkey`, `*_vin.txt` und `*.mhd`
  sind in `.gitignore` (Kundendaten).
