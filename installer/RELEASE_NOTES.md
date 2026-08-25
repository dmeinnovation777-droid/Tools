## Download & Installation

**`DME-Innovation-Tools-Setup-1.4.0.exe`** unten unter *Assets* herunterladen und starten.

Windows zeigt bei unsignierten Setups die Meldung „Der Computer wurde durch Windows
geschützt" — über **Weitere Informationen → Trotzdem ausführen** fortfahren.
Manche Virenscanner schlagen bei PyInstaller-Programmen an; das ist ein Fehlalarm.

Installiert werden:

| Programm | Zweck |
| --- | --- |
| **DME Innovation Tools** | Starter — zeigt beide Werkzeuge zur Auswahl |
| **AutoTuner Backup Tool** | AutoTuner-Backups (`.zip`/`.bak`) zu einer `.bin` zusammenführen und zurück verpacken |
| **MHD Lock Tool** | Locken von MHD+ Tune-Files automatisieren |

Dazu Startmenü-Einträge, auf Wunsch eine Desktop-Verknüpfung und ein Uninstaller.
Standardmäßig wird nur für den aktuellen Benutzer installiert — ohne
Administratorrechte; „für alle Benutzer" ist im Assistenten wählbar.
Setup wahlweise auf Deutsch oder Englisch.

## Neu in 1.4.0

Das **MHD Lock Tool** nimmt die Datei jetzt so an, wie der Kunde sie schickt.

* **Kein Umbenennen, kein VIN-Abtippen.** Die Datei aus der MHD-App
  (`<VIN>_<Programm-Nummer>_mapswitch.bin`) kommt unverändert in den
  Auftragsordner. Das Tool erkennt sie als Original, legt sie im
  Arbeitsverzeichnis als `<Programm-Nummer>_original.bin` ab und liest die VIN
  aus dem Dateinamen. Download-Kopien (`… (1).bin`, `… - Kopie.bin`) gelten
  genauso. Damit bleibt pro Auftrag nur noch: getunte Datei wählen, *Lock now*.
* **Die ganze XDF-Sammlung als Bibliothek.** Unter *Settings* lässt sich der
  komplette MHD-XDF-Ordner eintragen — Plattform, DME, Softwarestände,
  Unterordner bis sechs Ebenen tief. Die passende Datei wird über die
  ROM-Nummer gefunden, auch bei mehreren tausend XDFs ohne spürbare Wartezeit;
  liegen mehrere Revisionen zur selben Nummer vor, gewinnt die neueste.
* **Die VIN kann nicht mehr vom falschen Auto stammen.** Eine Programm-Nummer
  benennt einen Softwarestand, kein Fahrzeug — zwei Kunden auf demselben Stand
  teilen sie sich. Übernommen wird eine VIN deshalb nur aus einer Kundendatei,
  die zum Auftrag gehört: neben der getunten Datei und mit der Programm-Nummer
  dieses Steuergeräts. Bei zwei Kundendateien mit verschiedenen VINs im selben
  Ordner bleibt das Feld leer, statt zu raten.

## Hinweise

Das **MHD Lock Tool steuert deine eigene lizenzierte MHD-Exe** (TuningMapBuilder /
MHD Map Encryption) — trage ihren Pfad unter *Settings* ein. Sie ist absichtlich
nicht Teil dieses Downloads.

Für den ersten Test empfiehlt sich **„Prepare folder only"**: das legt nur das
Arbeitsverzeichnis an, ohne etwas auszuführen. Stimmt es mit einem von Hand
gebauten Ordner überein, macht „Lock now" denselben Schritt automatisch.

Alle Einzelheiten stehen in der [README](https://github.com/dmeinnovation777-droid/Tools#readme).
