## Download & Installation

**`DME-Innovation-Tools-Setup-3.0.0.exe`** unten unter *Assets* herunterladen und starten.

Windows zeigt bei unsignierten Setups die Meldung „Der Computer wurde durch Windows
geschützt" — über **Weitere Informationen → Trotzdem ausführen** fortfahren.
Manche Virenscanner schlagen bei PyInstaller-Programmen an; das ist ein Fehlalarm.

**Neu in 3.0.0: aus drei Programmen wird eine App.** Ein Fenster, vier
Bereiche in der Leiste oben, und in jedem Bereich dieselbe senkrechte Kette von
Schritten. Es öffnet sich kein zweites Fenster mehr, für nichts.

Installiert wird:

| Startmenü-Eintrag | öffnet die App auf |
| --- | --- |
| **DME Innovation Tools** | Locken |
| **MHD Lock Tool** | Locken |
| **AutoTuner Backup Tool** | Backup |

Alle drei starten dieselbe Datei. Dazu auf Wunsch eine Desktop-Verknüpfung und
ein Uninstaller.
Standardmäßig wird nur für den aktuellen Benutzer installiert — ohne
Administratorrechte; „für alle Benutzer" ist im Assistenten wählbar.
Setup wahlweise auf Deutsch oder Englisch.

## Was 3.0.0 anders macht

**Eine App statt drei Programme.** Der Starter ist weg. Locken, Stapel, Backup
und Einstellungen sind Bereiche eines Fensters, oben in einer Leiste. Nichts
öffnet mehr ein zweites Fenster: das Protokoll steht in dem Schritt, der gerade
läuft, ein Fehler steht in dem Schritt, in dem er auftritt, und das Ergebnis
steht da, wo es entstanden ist.

**Ein Fluss statt Karten.** Jeder Bereich ist eine senkrechte Kette von
Schritten mit einem Ring davor. Erledigte Schritte bleiben grün stehen, der
laufende trägt als einziger das Amber, die kommenden stehen grau da. Man sieht
auf einen Blick, wo man ist und was noch fehlt.

**Deutsch und Englisch, umschaltbar.** Der Schalter steht ganz oben in den
Einstellungen und wird gemerkt. Deutsch ist voreingestellt. Fachwörter bleiben
stehen, wie Du sie sagst: Lock, Tune, Stock ROM, XDF, Tool key, VIN.

**Der Fluss hält an, wo es klemmt.** Eine fehlende VIN färbt nicht mehr die
Vorprüfung rot, sondern den VIN-Schritt. Ein falsches Stock ROM hält bei der
Vorprüfung an und sagt beide Program IDs.

**Nichts verrutscht mehr.** Der Fix aus 2.3.4 gilt weiter und wird jetzt in
beiden Sprachen gemessen: alle vier Bereiche fangen auf demselben Pixel an, und
ein Sprachwechsel bewegt keine Zeile.

Am Motor hat sich nichts geändert. Auflösung, Vorprüfung, Staging, der Aufruf
des Builders und das Zusammenführen der Backups sind Zeile für Zeile dieselben
wie in 2.3.4. Umgebaut wurde nur, was man sieht.

## Korrektur in 2.3.4

**Die Zeilen sind beim Seitenwechsel verrutscht.** Jeder Klick in der
Seitenleiste hat den Inhalt ein Stück nach oben oder unten gesetzt, und auf dem
Weg dorthin lief der ganze Aufbau noch einmal durch. Drei Ursachen, alle drei
behoben:

* **Der Kopfbereich hat nur für den Untertitel der gerade offenen Seite Platz
  gelassen.** Lock braucht drei Zeilen, Settings eine, also sprang alles
  darunter um 17 Pixel. Jetzt hält der Kopf immer die Höhe des längsten
  Untertitels frei, auch für die Fassungen, die eine Einstellung erst später
  einblendet.
* **Beim Wechsel wurde die alte Seite abgehängt und die neue neu eingehängt.**
  Eine frisch eingehängte Seite ist für einen Augenblick ein Pixel breit, also
  hat jeder umbrechende Text neu umgebrochen, bevor er sich gesetzt hat. Jetzt
  liegen alle Seiten von Anfang an in voller Größe übereinander, und ein
  Seitenwechsel ist ein Heben, keine Neuberechnung.
* **Die Bildlaufleiste hat sich eine eigene Spalte genommen.** Erschien sie,
  wurde der Inhalt schmaler, der Text brach neu um, die Höhe änderte sich, und
  die Leiste konnte dadurch wieder erscheinen. Sie schwebt jetzt am rechten
  Rand über dem Inhalt, in der Randfläche, die ohnehin frei ist.

Dazu räumt die App beim Schließen ihren Ereigniszähler auf, statt eine offene
Rückmeldung gegen ein bereits geschlossenes Fenster laufen zu lassen.

Ein neuer Test misst das nach: er merkt sich für jede Seite, auf welchem Pixel
der Inhalt beginnt, läuft alle Seiten hin und zurück durch und schlägt fehl,
sobald sich auch nur eine Zeile bewegt. Gegen die alte Fassung schlägt er fehl.

## Korrektur in 2.3.3

**Lock now hat den Builder gestartet, ihm aber nie gesagt, woran er arbeiten
soll.** Das Ergebnis war ein grün geprüfter Auftrag, der dann mit
`Nothing was locked` endete.

Der TuningMapBuilder nimmt die getunte Datei als Übergabewert entgegen. Genau
das passiert, wenn Du sie im Explorer auf die `.exe` ziehst, und genau so
arbeitest Du damit. Die App hat ihn ohne Übergabe gestartet. Er hatte also
nichts zu tun, gab nichts aus und lief direkt auf seine Schlusszeile.

Behoben, und dabei zwei weitere Dinge am selben Handgriff:

* **Die getunte Datei wird übergeben**, so wie beim Draufziehen.
* **Der Builder bekommt eine eigene Konsole**, deren Fenster verborgen bleibt,
  und seine Eingabe wird nicht mehr umgeleitet. Er endet auf einem Tastendruck,
  und den verweigert Windows einem Programm ohne Konsole mit einer Ausnahme.
  Die stand bei Dir im Protokoll.
* **Deutsche Windows-Meldungen werden jetzt richtig gelesen.** Vorher stand da
  `Schl?ssel` statt `Schlüssel`, und die Bewertung kannte nur die englischen
  Texte.

Der Rauchtest verhält sich jetzt wie das echte Werkzeug: er arbeitet nur, wenn
er die Datei übergeben bekommt, und er beendet sich nicht von selbst. Ohne die
Übergabe fällt er durch, mit ihr läuft er. Das war vorher nicht so, und deshalb
ist der Fehler bis zu Dir durchgekommen.

## Neu in 2.3.2

**Scheitert ein Lauf, steht das Protokoll jetzt offen da.** Vorher meldete die
App „Nothing was locked. See the log" und das Protokoll war zugeklappt.

Dazu ein Knopf **Save log** darin. Er schreibt die Ausgabe des MHD Tools in eine
Datei, zusammen mit den verwendeten Pfaden, der VIN und der Version. Ein
gescheiterter Lauf legt nämlich keine Protokolldatei neben eine Ausgabe, weil es
keine Ausgabe gibt. Bisher blieb nur ein Foto vom Bildschirm.

## Korrektur in 2.3.1

**In 2.2.0 und 2.3.0 ging der Starter auf, aber kein Werkzeug startete.** Ein
Klick auf AutoTuner Backup Tool oder MHD Lock Tool brachte nur ein Fenster mit
`No module named`. Bitte diese beiden Versionen nicht verwenden.

Ursache: seit 2.2.0 steckt alles in einer Programmdatei, und die beiden
Werkzeuge werden erst beim Klick geladen. Damit das Bauwerkzeug sie überhaupt
mit einpackt, braucht es je einen ausdrücklichen Vermerk. Den hatte ich in das
Bauskript für den eigenen Rechner geschrieben, aber nicht in das, mit dem die
ausgelieferte Datei tatsächlich gebaut wird. Der Test daneben prüfte die
falsche der beiden Dateien und stand auf grün.

Behoben, und zwar an drei Stellen:

* Der Vermerk steht jetzt in **beiden** Bauskripten, und der Test liest auch
  beide.
* Nach jedem Bau **startet die Auslieferung jedes Werkzeug einmal aus der
  fertigen Datei** und bricht ab, wenn eines nicht hochkommt. Ein gesetzter
  Schalter ist kein Beweis, ein laufendes Fenster schon.
* Nachgestellt und gegengeprüft: derselbe Bau ohne den Vermerk bricht mit
  genau Deiner Meldung ab, mit Vermerk laufen beide Werkzeuge an.

## Neu in 2.3.0

**Beide Werkzeuge sehen wieder anders aus, und diesmal ruhiger.** Die
Seitenleiste ist jetzt grau und trägt Symbole, die Arbeitsfläche liegt heller
darüber, die Karten sind weiß. Drei Grautöne, gestapelt wie bei einem Mac
Fenster. Die ausgewählte Seite ist eine weiße Fläche, keine kaum sichtbare
Tönung mehr.

**Die Einstellungen sind neu gebaut.** Statt gestapelter Felder stehen dort
jetzt gruppierte Zeilen unter einer leisen Überschrift, getrennt durch
Haarlinien. Und aus den Häkchen sind **echte Schalter** geworden, so wie am
Telefon: über den Raum hinweg erkennbar, ob etwas an oder aus ist. Das kleine
Windows Kästchen war aus einem anderen Jahrzehnt.

**Alle Texte kommen ohne Gedankenstriche aus.** Rund siebzig Meldungen und
Beschriftungen sind neu formuliert, mit Komma, Punkt oder Mittelpunkt statt des
langen Strichs. Ein Test hält das fest, damit es so bleibt. Echte Dateinamen
wie `how-to-use-backup.html` bleiben natürlich, wie sie heißen.

**An der Funktion ändert sich nichts.** Kein Eingriff in das Locken, in die
Erkennung der Kundendatei, in die XDF Suche oder in das Zusammenführen der
AutoTuner Backups. Deine Einstellungen bleiben stehen.

Eine Anmerkung zur Schrift: der Entwurf nutzt Instrument Sans, die auf einem
normalen Windows PC nicht installiert ist. Die App bleibt deshalb bei Segoe UI
Variable, der nächstliegenden Schrift, die auf jedem Rechner da ist. Getragen
wird der Look ohnehin von Aufbau und Flächen, nicht von der Schriftart.

## Neu in 2.2.0

**Das Setup ist rund ein Drittel so groß.** Bisher war jedes Werkzeug eine
eigene Programmdatei — und jede brachte ihre eigene Kopie von Python und der
Oberflächenbibliothek mit, dreimal dasselbe. Jetzt ist es **eine** Datei, die
alle drei Programme trägt.

Für Dich ändert sich an der Bedienung nichts: im Startmenü stehen weiter drei
Einträge, die beiden Werkzeuge starten dieselbe Datei mit einem Schalter. Sie
laufen weiterhin in getrennten Prozessen — stürzt eines ab, bleibt das andere
stehen. Deine Einstellungen bleiben unberührt.

Beim Aktualisieren räumt das Setup die beiden alten Programmdateien weg.
Solltest Du Dir früher eine eigene Verknüpfung direkt auf
`AutoTuner Backup Tool.exe` oder `MHD Lock Tool.exe` gelegt haben, zeigt die
danach ins Leere — nimm die Einträge aus dem Startmenü.

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
