## Download & Installation

**`DME-Innovation-Tools-Setup-3.2.2.exe`** unten unter *Assets* herunterladen und starten.

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

## Korrektur in 3.2.2: zwei Autos, eine Größe

Gefunden beim Vergleich von vier echten Bench Backups gegen das alte Werkzeug.

**Ein BMW X5 auf MG1CS201 und ein VW Caddy auf MD1CS004 sind beide 9.256.960
Bytes groß und werden gleich aufgeteilt.** Das Gedächtnis lag nach Größe ab,
also hat das Einlesen des Caddy den BMW überschrieben, und der BMW ging danach
als Volkswagen zum Kunden zurück: falsche Marke, falsches Modell, falsches
Steuergerät, falsche Leistung.

Das war schlimmer als das, was es ersetzen sollte. Leere Felder sind lästig,
das falsche Auto in einem fremden Archiv ist ein Fehler.

Gemerkt werden jetzt **alle** Fahrzeuge zu einer Größe. Beim Öffnen einer .bin
entscheidet der Dateiname, welches gemeint ist, denn die Dateien kommen vom
Lesegerät nach Auto und Steuergerät benannt. Sagt der Name nichts, wird nichts
geraten: die Aufteilung kommt, die Angaben zum Fahrzeug bleiben leer, und die
Seite sagt welche Fahrzeuge in Frage kommen.

Dasselbe gilt für die Hilfeseite: tragen alle gemerkten Fahrzeuge dieselbe,
wird sie benutzt, denn dann ist nichts zu entscheiden. Sind sie verschieden und
das Auto ist unklar, kommt die eingebaute.

## Vergleich mit dem alten Werkzeug

Vier echte Archive, beide Wege durchgespielt, Ergebnis gegen das Original:

| | altes Werkzeug | 3.2.2 |
| --- | --- | --- |
| iflash0.bin | gleich | gleich |
| dflash0.bin | gleich | gleich |
| contents.ini | **anders** | gleich |
| how-to-use-backup.html | **anders** | gleich |

Das alte Werkzeug verliert bei jedem der vier Autos `VehicleSeries` und
`OutputKW` und schreibt seine eigene englische Hilfeseite über die deutsche des
Lesegeräts. Die .bin, die beide aus einem Archiv machen, ist byteweise
dieselbe.

## Korrektur in 3.2.1: Backup, BIN nach ZIP

**Eine leere Zeile in der Aufteilung hat das Packen blockiert.** Gemeldet an
einem echten Mercedes GLE MG1CP002 Bench Backup. Die Seite zeigte den Schritt
als erledigt, zählte drei Teile und meldete „Größen stimmen überein", und beim
Druck auf Packen kam „Zeile 3 hat keinen gültigen Namen oder keine gültige
Größe". Drei Stellen sagten ja und der Knopf sagte nein.

Eine leere Zeile ist eine Zeile, die noch ausgefüllt werden will. Sie ist kein
Teil: sie wird nicht mitgezählt, nicht gepackt und steht nicht im Weg. Eine
halb ausgefüllte Zeile ist dagegen ein echter Fehler und wird sofort rot
angezeigt, an der Zeile selbst, statt erst beim Knopf.

**Die Fahrzeugangaben gingen auf dem Rückweg verloren.** Beim selben Auto: das
Archiv nannte einen W167 GLE 450 AMG, Benzin, 367 PS, 270 kW. Auseinander
genommen und wieder zusammengebaut nannte das Archiv für den Kunden gar kein
Auto mehr, und aus dem Benziner war still ein Diesel geworden.

In welchem Auto ein Speicherabzug gesessen hat, steht nirgends im Abzug. Es
kann also nur aus dem Archiv kommen, aus dem er stammt. Diese Angaben werden
jetzt zusammen mit der Aufteilung gemerkt und beim Packen wieder eingetragen,
alle vierzehn Felder, auch die fünf ohne Eingabefeld auf der Seite.

Damit kommt ein Archiv vollständig zurück: beide Abbilder, die contents.ini und
die Hilfeseite sind byteweise dieselben wie im Original.

## Neu in 3.2.0: das Design

Der Entwurf, den Du hast machen lassen, ist eingebaut. Er ist es an der Stelle
genau: dieselbe Palette, dieselben Radien, dieselben Schatten, dieselben
Schriftgrößen.

tkinter kann von sich aus keine runde Ecke, keinen weichen Schatten und keine
glatte Kante. Es kann aber ein Bild anzeigen, und jeder Grund in dieser App ist
eine einzige bekannte Fläche. Also wird jede runde Form ausgerechnet, gegen
genau diesen Grund, und als Bild übergeben. Das PNG dafür ist von Hand
geschrieben. Es kommt nichts dazu, was auf Deinem Rechner installiert sein
müsste.

Was Du siehst:

* **Runde, saubere Formen.** Felder als Mulden mit Radius zehn, Knöpfe mit
  einem Schatten von einem Haar. Der Amber-Knopf trägt seine eigene Farbe im
  Schatten, weil ein grauer Schatten unter warmem Gelb wie Schmutz aussieht.
* **Die Schritt-Ringe.** Erledigt ist ein voller grüner Kreis mit einem
  gezeichneten Haken, laufend ein weißer mit dickem Amber-Rand und seiner
  Zahl, kommend ein weißer mit dünner grauer Linie.
* **Ein Symbol je Schritt.** Blatt, Schild, Raute, Schloss, Liste, Archiv. Man
  sieht, worum es in einem Schritt geht, bevor man den Titel liest.
* **Die wandernde Linie.** Der laufende Schritt zeigt eine Amber-Linie, die
  gleichmäßig von links nach rechts läuft. Sie erscheint erst, wenn Du die
  Aktion drückst, und verschwindet erst, wenn der Schritt ehrlich fertig oder
  ehrlich rot ist. Sie sagt nie, dass gearbeitet wird, wenn nicht gearbeitet
  wird.
* **Deutsch und Englisch sitzen oben in der Leiste**, auf jeder Seite, statt
  auf einer Zeile in den Einstellungen.

## Auch in 3.2.0: das Fenster bleibt während der Prüfung stehen

Die Vorprüfung lief seit 3.1.0 in einem eigenen Faden, und trotzdem stand das
Fenster mitten darin vier Zehntelsekunden still. Ein Faden allein genügt nicht:
wer nur rechnet, behält den Interpreter für sich.

Die Suche nach der Programmkennung lief als ein einziger Schritt über das ganze
8 MB Abbild. Findet sie nichts, läuft sie bis zum Ende durch, ohne dass
irgendetwas dazwischen kann. Sie läuft jetzt Stück für Stück, mit Überlappung,
damit eine Kennung an einer Schnittstelle nicht verloren geht, und sie findet
nachweislich genau dasselbe. Dazu wird der Interpreter öfter weitergereicht.

Gemessen an einem echten 8 MB Paar:

| | vorher | jetzt |
| --- | --- | --- |
| schlimmster Moment während der Prüfung | 408 ms | 18 ms |
| die Prüfung selbst | 736 ms | 775 ms |

Der Test hat das bisher nicht gesehen, weil er nur die ersten vier Zehntel nach
dem Auswählen hingeschaut hat und das Stillstehen eine Sekunde später kam. Er
schaut jetzt so lange hin, wie die Prüfung läuft.

## Korrektur in 3.1.1

**Beim Öffnen hat die App gewackelt.** Sie erschien, stand kurz da, und
rückte sich dann selbst zurecht. Zwei Ursachen, beide aus 3.1.0:

* Das Fenster wurde in seiner natürlichen Größe aufgebaut und **erst danach**
  auf 1120 × 800 gesetzt. Jeder umbrechende Text war also auf eine falsche
  Breite umgebrochen.
* Das Entprellen der Größenänderung, das in 3.1.0 das Ziehen am Fensterrand
  flüssig gemacht hat, galt auch für den **ersten** Aufbau. Der ist aber keine
  Ziehbewegung: die Folge war, dass das Fenster sichtbar dastand und fünfzig
  Millisekunden später überall neu umbrach.

Gemessen an einem Testlauf haben sich sechs Dinge bewegt, nachdem das Fenster
schon zu sehen war, darunter die Inhaltsspalte **jedes** Bereichs, die um rund
200 Pixel breiter sprang.

Jetzt bekommt das Fenster seine Größe, bevor irgendetwas gebaut wird, es wird
unsichtbar fertig zusammengesetzt und erst dann gezeigt. Der erste Aufbau wird
nicht mehr entprellt. Was erscheint, ist ein fertiges Bild.

Ein neuer Test hält das fest: er nimmt in dem Augenblick, in dem das Fenster
erscheint, Größe und Lage von rund zwanzig Bezugspunkten auf, lässt eine halbe
Sekunde vergehen und vergleicht. Bewegt sich irgendetwas, schlägt er fehl.
Gegen 3.1.0 schlägt er fehl, mit genau den sechs Meldungen von oben.

## Was 3.1.0 anders macht

**Das Fenster hängt nicht mehr.** Die Vorprüfung lief bis 3.0.0 im
Fensterthread, 350 ms nach jedem Tastendruck im VIN Feld: 16 MB lesen, die
Unterschiede suchen, beide Images nach Program IDs durchsuchen, alles auf die
XDF legen. Auf einer echten 8 MB S58 Datei sind das rund **0,8 Sekunden**, und
eine VIN hat siebzehn Zeichen.

Jetzt ist die Prüfung geteilt. Was die Dateien entscheiden, läuft auf einem
Nebenläufer und wird behalten, solange die drei Dateien unangetastet bleiben.
Was Du tippst, wird sofort geprüft, ohne ein einziges Byte zu lesen. Gemessen,
an genau so einer 8 MB Datei:

| | 3.0.0 | 3.1.0 |
| --- | --- | --- |
| ein Tastendruck im VIN Feld | rund 800 ms Stillstand | **2,5 ms** |
| eine Datei auswählen | rund 800 ms Stillstand | **17 ms** |
| Kundenname tippen | löste die ganze Prüfung aus | löst nichts aus |

Dazu ist die Rechnerei selbst schneller geworden: die geänderten Bytes werden
nicht mehr einzeln in Python gezählt, sondern blockweise in C, **0,04 statt
0,28 Sekunden**. Ein Image wird einmal gelesen und einmal durchsucht, nicht bei
jeder Prüfung neu. Und im Stapel wird die Zuordnung je Datei ebenfalls
nebenläufig gemacht, statt das Fenster zwanzigmal anzuhalten.

**Es bewegt sich etwas.** Bis 3.0.0 sprang alles um: die Seite, der Schalter,
die Pille in der Leiste, der Ring an einem Schritt. Jetzt gleitet die Seite beim
Wechsel herein, die Pille wandert von Wort zu Wort, der Schalter schiebt seinen
Knopf hinüber, und ein Ring blendet seine Farbe über. Gemessen bei über 100
Bildern je Sekunde.

**Das Scrollen gleitet und läuft aus.** Das Rad sprang bisher zeilenweise. Jetzt
gibt eine Rastung dem Inhalt einen Schwung, der ausklingt, rund 130 Pixel in
einer halben Sekunde. Und es funktioniert überall auf der Seite: bisher hörte
das Rad auf zu wirken, sobald der Zeiger über einem Text stand, weil die
Bindung an einer Stelle hing, die der Zeiger dabei verlässt. Über dem
Protokollfenster und über der Tabelle scrollt jetzt das, worüber der Zeiger
steht, und sonst die Seite.

**Das Fenster vergrößern ruckelt nicht mehr.** Jeder Pixel einer Ziehbewegung
ließ jeden umbrechenden Text auf allen vier Seiten neu umbrechen. Das passiert
jetzt einmal, fünfzig Millisekunden nachdem Du losgelassen hast.

Am Motor hat sich wieder nichts geändert: Auflösung, Vorprüfung, Staging, der
Aufruf des Builders und das Zusammenführen der Backups liefern dasselbe wie in
3.0.0. Ein Test vergleicht die neue Zählung der geänderten Bytes gegen die alte
auf dreihundert Zufallspaaren, damit das so bleibt.

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
