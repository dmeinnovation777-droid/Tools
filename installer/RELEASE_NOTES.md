## Download & Installation

**`DME-Innovation-Tools-Setup-2.1.1.exe`** unten unter *Assets* herunterladen und starten.

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

## Korrekturen in 2.1.1

Am **AutoTuner Backup Tool**, gefunden an fünf echten Bench-Reads (Mercedes GLE
MG1CP002, zweimal BMW X5 MG1CS201, zweimal VW Caddy MD1CS004):

* **Das MG1CP002-Preset schnitt an der falschen Stelle.** Es stand auf vier
  Teilen (4 MB + 4 MB + 256 KB + 256 KB). Ein echter Mercedes-Read desselben
  Steuergeräts hat **zwei** Teile: 8 MB + 512 KB. Die Summe war zufällig
  dieselbe, und weil die Dateigröße das Preset auswählt, wäre daraus
  stillschweigend ein Archiv entstanden, das der AutoTuner so nie schreibt.
  Jetzt steht dort die gemessene Aufteilung.
* **Die `how-to-use-backup.html` wird nicht mehr überschrieben.** Der AutoTuner
  legt diese Seite in der Sprache des Bedieners ab — ein deutscher Read trägt
  die Meldung auf Deutsch. Das Werkzeug hat sie beim Zurückpacken durch eine
  englische Fassung ersetzt. Sie wird jetzt aus dem Ursprungsarchiv übernommen
  und zusammen mit der Aufteilung gemerkt, überlebt also auch einen Neustart.
* **Passt eine Dateigröße auf zwei Steuergeräte**, sagt das Werkzeug es jetzt.
  MED17.1.1 und MEVD17.2.x schneiden identisch, aber der Name landet in der
  `contents.ini` des Kunden — das war vorher ein stiller Rateschritt.

Ergebnis: alle fünf Backups gehen **ZIP → BIN → ZIP byteidentisch** durch —
jede Datei, gleiche Reihenfolge, gleiche Archivgröße.

## Neu in 2.1.0

**Das MHD Lock Tool kann jetzt auch nur den Ordner bauen.** Wer selbst in
`.mhd` umwandelt, drückt statt *Lock now* den Knopf **Prepare folder**
daneben — dauerhaft sichtbar, nichts aufzuklappen. Er legt das fertige
Arbeitsverzeichnis an, mit allem was hineingehört, und startet nichts. Der
Ordner bleibt liegen; den Rest machst Du von Hand.

Wenn das bei Dir die Regel ist, setz in den Einstellungen **„I convert to .mhd
myself — only prepare the folder"**. Dann wird der Ordner die Hauptaktion,
*Lock now* verschwindet, der Stapel heißt *Prepare folders* und baut einen
Ordner je Auftrag — und die App fragt nicht mehr nach dem Pfad zum Builder.
Eingetragen bleibt er trotzdem nützlich: er entscheidet, ob die `.exe` mit in
den Ordner kopiert wird. Der `.toolkey` wird weiter gebraucht, der gehört
hinein.

Gegengeprüft an einem echten Auftrag: der erzeugte Ordner ist mit einem von
Hand gebauten **byteidentisch**, alle sechs Dateien, keine Extras.

Dazu drei Kleinigkeiten, die beim Durchsehen jedes Bildschirms auffielen:

* Erklärungen unter den Kästchen in den Einstellungen wurden am Kartenrand
  abgeschnitten — sie brechen jetzt um.
* Im grünen Meldungsstreifen wurde „Show in folder" zu „in" gequetscht, sobald
  die Meldung ein langer Pfad ohne Leerzeichen war.
* Das Ordner-Symbol auf dem Knopf war ein dünner Umriss, der neben dem
  Vorhängeschloss verschwand — ersatzlos entfernt.

**An der Funktion des Lockens ändert sich nichts.** Kein Eingriff in das
Erkennen der Kundendatei, die XDF-Suche oder die Übernahme der VIN.

## Neu in 2.0.0

**Beide Werkzeuge sehen neu aus.** Heller Grund, weiße Karten mit weichen Ecken,
und genau eine Farbe im Bild: das DME-Amber. Es gehört der Aktion, die auf der
Seite gerade ansteht — *Lock now*, *Run batch*, *Open*. Alles andere ist Grau in
drei Stufen. Wo vorher farbige Kästchen um Aufmerksamkeit konkurrierten, führt
jetzt genau ein Knopf.

**An der Funktion ändert sich nichts.** Kein Eingriff in das Locken, in das
Erkennen der Kundendatei, in die XDF-Suche oder in die Übernahme der VIN. Die
2.0 ist eine Aussage über das Aussehen, nicht über das, was das Programm tut.
Deine Einstellungen bleiben stehen — sie liegen in `%APPDATA%\DME Innovation`
und überleben die Aktualisierung.

Dazu zwei Dinge, die man nicht sofort sieht:

* **Jede Schriftfarbe ist nachgerechnet.** Kein Text steht unter dem Kontrast,
  den man bei Werkstattlicht auf einem billigen Monitor noch sicher liest — auch
  nicht die kleinen Hinweiszeilen. Ein Test rechnet das bei jeder Änderung nach,
  damit es so bleibt.
* **Nichts wird mehr abgeschnitten.** Erklärungen brechen dort um, wo die Karte
  endet, statt mitten im Wort aufzuhören — bei jeder Fenstergröße und bei
  125 %, 150 % oder 200 % Windows-Skalierung.

## Korrekturen in 1.4.1

Nachträglich gefunden und behoben — alles Fälle, die bei über Jahre gewachsenen
Auftragsordnern auftreten:

* **Liegt neben der Kundendatei auch eine von Hand umbenannte `*_original.bin`,
  gewinnt jetzt immer die umbenannte.** Vorher entschied die alphabetische
  Sortierung, welche der beiden als Vergleichsbasis diente — bei einem
  kleingeschriebenen Namen wie `stock_….bin` also die falsche.
* **Eine übrig gebliebene Kundendatei eines anderen Fahrzeugs blockiert die
  Erkennung nicht mehr.** Vorher meldete der Ordner „2 mögliche Stock-ROMs" und
  verlangte eine Handauswahl, obwohl nur eine Datei zum Auto passte.
* **Nennt eine `<VIN>_vin.txt` im Ordner ein anderes Auto als die Kundendatei,
  wird das gemeldet** statt stillschweigend übergangen.
* **Keine Fehlwarnung mehr bei Tunes, die nach der Kundendatei benannt sind**
  (`…_mapswitch_STG2.bin`). Die Rückfrage „ist das wirklich der Tune?" kommt nur
  noch beim unveränderten Kundendatei-Namen.

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
