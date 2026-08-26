"""
DME Innovation Tools · the word list
====================================

Every line the app shows, in German and English, in one place. The app starts
in German; the switch sits at the top of Settings and is remembered.

    from dme_text import t
    ui.label(parent, text=t("lock.title"))
    status.set(t("status.locked", n=3))

Rules for this file, so it stays a word list and not a second program:

* One entry per visible line, with both languages side by side. A key without
  both is a bug, and tests/test_text_catalog.py fails on it.
* Placeholders are named, never positional, and identical in both languages.
* No dashes in the middle of a sentence. Your rule, and the test enforces it.
* Technical words stay technical in both languages: Lock, Tune, Stock ROM,
  XDF, Tool key, VIN, .mhd, .bin. A German workshop says "gelockt", not
  "verriegelt", and translating it would make the app harder to read, not
  easier.

© DME Innovation
"""

LANGUAGES = ("de", "en")
LANGUAGE_NAMES = {"de": "Deutsch", "en": "English"}
#: What the switch in the top bar says. Two letters, because it sits beside
#: the state and has to stay out of the way of it.
LANGUAGE_SHORT = {"de": "DE", "en": "EN"}
DEFAULT_LANGUAGE = "de"

_current = DEFAULT_LANGUAGE


def language() -> str:
    """The language in use right now."""
    return _current


def set_language(code: str) -> str:
    """Switch language. Unknown codes fall back to the default, never crash."""
    global _current
    _current = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _current


def t(key: str, **values) -> str:
    """The line for ``key`` in the current language.

    An unknown key returns the key itself instead of raising: a missing word
    must never take the window down in front of a customer. The test suite is
    where a missing key is supposed to hurt.
    """
    entry = CATALOG.get(key)
    if entry is None:
        return key
    text = entry.get(_current) or entry.get(DEFAULT_LANGUAGE) or key
    if values:
        try:
            return text.format(**values)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def _(de: str, en: str) -> dict:
    return {"de": de, "en": en}


CATALOG: dict[str, dict] = {
    # ── window and navigation ────────────────────────────────────────────────
    "app.title": _("DME Innovation Tools", "DME Innovation Tools"),
    "nav.lock": _("Locken", "Lock"),
    "nav.batch": _("Stapel", "Batch"),
    "nav.backup": _("Backup", "Backup"),
    "nav.settings": _("Einstellungen", "Settings"),

    # ── shared words ─────────────────────────────────────────────────────────
    "word.choose": _("Wählen", "Choose"),
    "word.change": _("Ändern", "Change"),
    "word.browse": _("Durchsuchen", "Browse"),
    "word.cancel": _("Abbrechen", "Cancel"),
    "word.stop": _("Anhalten", "Stop"),
    "word.clear": _("Leeren", "Clear"),
    "word.remove": _("Entfernen", "Remove"),
    "word.save": _("Sichern", "Save"),
    "word.open_folder": _("Ordner zeigen", "Show folder"),
    "word.save_log": _("Protokoll sichern", "Save log"),
    "word.reset": _("Zurücksetzen", "Reset"),
    "word.ready": _("Bereit", "Ready"),
    "word.running": _("Läuft", "Running"),
    "word.done": _("Fertig", "Done"),
    "word.stopped": _("Angehalten", "Stopped"),
    "word.waiting": _("Wartet", "Waiting"),
    "word.failed": _("Fehler", "Failed"),
    "word.queued": _("Wartet", "Queued"),
    "word.prepared": _("Ordner", "Folder"),
    "word.locked": _("Gelockt", "Locked"),
    "word.of": _("von", "of"),
    "word.bytes": _("Bytes", "bytes"),
    "word.not_found": _("nicht gefunden", "not found"),
    "word.found": _("gefunden", "found"),
    "word.set": _("hinterlegt", "set"),
    "word.missing": _("fehlt", "missing"),
    "word.manual": _("von Hand", "manual"),
    "word.language": _("Sprache", "Language"),
    "word.language_hint": _(
        "Die Ansicht wird dabei neu aufgebaut. Dateien, VIN und Einstellungen "
        "bleiben stehen, das Protokollfenster fängt von vorn an.",
        "The view is rebuilt when you switch. Files, VIN and settings stay, the "
        "log window starts over."),

    # ── page: lock ───────────────────────────────────────────────────────────
    "lock.title": _("Tune locken", "Lock a tune"),
    "lock.sub": _(
        "Ein Schritt nach dem anderen. Was erledigt ist, bleibt stehen.",
        "One step after the other. What is done stays where it is."),
    "lock.sub_prepare": _(
        "Ein Schritt nach dem anderen. Am Ende steht der fertige Arbeitsordner, "
        "die .mhd machst Du selbst.",
        "One step after the other. At the end you get the finished working "
        "folder; the .mhd is yours to make."),

    "lock.step1": _("Getunte Datei", "Tuned file"),
    "lock.step1.drop": _("Datei hierher ziehen", "Drop the file here"),
    "lock.step1.hint": _(
        "Die getunte .bin, so wie der Kunde sie geschickt hat.",
        "The tuned .bin, exactly as the customer sent it."),
    "lock.step1.field": _("Getunte ROM des Kunden (.bin)", "Customer's tuned ROM (.bin)"),
    "lock.step1.size": _("{size} · {when}", "{size} · {when}"),
    "lock.step1.empty": _("Noch keine Datei gewählt", "No file picked yet"),

    "lock.step2": _("Vorprüfung", "Pre-flight"),
    "lock.step2.idle": _(
        "Stock ROM, XDF und Tool key sucht das Werkzeug selbst.",
        "Stock ROM, XDF and tool key are found automatically."),
    "lock.step2.stock": _("Stock ROM", "Stock ROM"),
    "lock.step2.xdf": _("XDF", "XDF"),
    "lock.step2.toolkey": _("Tool key", "Tool key"),
    "lock.step2.builder": _("Builder", "Builder"),
    "lock.step2.manual": _("Von Hand ändern", "Change manually"),
    "lock.step2.note": _(
        "{bytes} geänderte Bytes in {tables} Tabellen",
        "{bytes} changed bytes in {tables} tables"),
    "lock.step2.checking": _("Wird geprüft …", "Checking …"),

    "lock.step3": _("VIN prüfen", "Check the VIN"),
    "lock.step3.hint": _(
        "Aus dem Mapswitch Read des Kunden gelesen. Stimmt sie nicht, hier ändern.",
        "Read from the customer's mapswitch file. Change it here if it is wrong."),
    "lock.step3.field": _("VIN (17 Zeichen)", "VIN (17 characters)"),
    "lock.step3.customer": _(
        "Name des Kunden, wird für den Dateinamen benutzt",
        "Customer name, used for the file name"),
    "lock.step3.idle": _(
        "Kommt aus dem Read des Kunden.",
        "Comes from the customer's read."),

    "lock.step4": _("Locken", "Lock"),
    "lock.step4.done": _("Gelockt", "Locked"),
    "lock.step4.hint": _(
        "Schreibt die .mhd in den Zielordner. Das Auto nimmt sie nur mit genau "
        "dieser VIN an.",
        "Writes the .mhd into the output folder. The car accepts it only with "
        "exactly this VIN."),
    "lock.step4.hint_prepare": _(
        "Legt den fertigen Arbeitsordner an und startet nichts. Der Builder "
        "liegt darin, Du ziehst die getunte Datei darauf.",
        "Builds the finished working folder and starts nothing. The builder is "
        "in there; you drop the tuned file onto it."),
    "lock.step4.result": _("Ergebnis", "Result"),
    "lock.step4.folder": _("Ordner", "Folder"),
    "lock.step4.bound": _("Gebunden an", "Bound to"),
    "lock.step4.size": _("Größe", "Size"),

    "lock.btn.lock": _("Jetzt locken", "Lock now"),
    "lock.btn.prepare": _("Nur Ordner", "Folder only"),
    "lock.btn.prepare_main": _("Ordner bauen", "Build the folder"),
    "lock.btn.next": _("Nächster Auftrag", "Next job"),
    "lock.foot.prepare": _(
        "Nur Ordner legt alles bereit, ohne den Builder zu starten.",
        "Folder only lays everything out without starting the builder."),
    "lock.foot.blocked": _(
        "Der Fluss hält an, wo es klemmt. Nichts dahinter läuft weiter.",
        "The flow stops where it is stuck. Nothing behind it runs on."),

    # ── page: batch ──────────────────────────────────────────────────────────
    "batch.title": _("Stapel", "Batch"),
    "batch.sub": _(
        "Derselbe Fluss, nur für einen ganzen Ordner auf einmal.",
        "The same flow, for a whole folder at once."),
    "batch.sub_prepare": _(
        "Derselbe Fluss für einen ganzen Ordner, und am Ende stehen nur die "
        "Arbeitsordner da.",
        "The same flow for a whole folder, and at the end only the working "
        "folders are there."),
    "batch.step1": _("Dateien", "Files"),
    "batch.step1.empty": _(
        "Noch keine Dateien in der Warteschlange.",
        "No files in the queue yet."),
    "batch.step1.count": _("{n} Dateien", "{n} files"),
    "batch.add_files": _("Dateien hinzufügen", "Add files"),
    "batch.add_folder": _("Ordner hinzufügen", "Add folder"),
    "batch.import_csv": _("CSV einlesen", "Import CSV"),
    "batch.export": _("Bericht sichern", "Save report"),
    "batch.remove": _("Ausgewählte entfernen", "Remove selected"),
    "batch.clear": _("Liste leeren", "Clear the list"),
    "batch.vin_to_all": _("VIN für alle", "VIN to all"),
    "batch.apply": _("Übernehmen", "Apply"),
    "batch.col.file": _("Datei", "File"),
    "batch.col.vin": _("VIN", "VIN"),
    "batch.col.customer": _("Kunde", "Customer"),
    "batch.col.status": _("Status", "Status"),
    "batch.col.result": _("Ergebnis", "Result"),
    "batch.step2": _("Vorprüfung je Datei", "Pre-flight per file"),
    "batch.step2.idle": _(
        "Stock ROM und XDF werden für jede Datei einzeln gesucht.",
        "Stock ROM and XDF are resolved for every file on its own."),
    "batch.step3": _("Stapel abarbeiten", "Run the batch"),
    "batch.step3.hint": _(
        "Jeder Auftrag läuft in seinem eigenen sauberen Ordner. Eine kaputte "
        "Datei hält die anderen nicht auf.",
        "Every job runs in its own clean folder. One broken file does not hold "
        "the others up."),
    "batch.step3.progress": _("{done} von {total} erledigt", "{done} of {total} done"),
    "batch.btn.run": _("Alle locken", "Lock them all"),
    "batch.btn.prepare": _("Ordner für alle", "Folders for all"),
    "batch.selected": _("Ausgewählte Zeile", "Selected row"),

    # ── page: backup ─────────────────────────────────────────────────────────
    "backup.title": _("Backup", "Backup"),
    "backup.sub.z2b": _(
        "Aus einem AutoTuner Backup wird eine durchgehende .bin für Deine "
        "Tuning Software.",
        "Turn an AutoTuner backup into one continuous .bin for your tuning "
        "software."),
    "backup.sub.b2z": _(
        "Aus der geänderten .bin wird wieder ein Archiv, das der AutoTuner "
        "annimmt.",
        "Turn the modified .bin back into an archive the AutoTuner accepts."),
    "backup.seg.z2b": _("ZIP nach BIN", "ZIP to BIN"),
    "backup.seg.b2z": _("BIN nach ZIP", "BIN to ZIP"),

    "backup.z2b.step1": _("Backup wählen", "Pick the backup"),
    "backup.z2b.step1.hint": _(
        "Ein AutoTuner .zip oder .bak, so wie das Werkzeug es ausgibt.",
        "An AutoTuner .zip or .bak, exactly as the tool writes it."),
    "backup.z2b.step2": _("Teile gefunden", "Parts found"),
    "backup.z2b.step2.idle": _(
        "Die Reihenfolge und die Adressen kommen aus dem Backup selbst.",
        "Order and addresses come out of the backup itself."),
    "backup.z2b.step3": _("Ziel", "Target"),
    "backup.z2b.step3.hint": _(
        "Eine durchgehende .bin für Deine Tuning Software.",
        "One continuous .bin for your tuning software."),
    "backup.z2b.step4": _("Zusammenführen", "Combine"),
    "backup.z2b.btn": _("Zusammenführen", "Combine"),
    "backup.z2b.foot": _(
        "Die Reihenfolge und die Adressen kommen aus dem Backup selbst, nicht "
        "aus einer Vermutung.",
        "Order and addresses come out of the backup itself, not out of a guess."),

    "backup.b2z.step1": _("Geänderte .bin", "Modified .bin"),
    "backup.b2z.step1.hint": _(
        "Die Datei, die aus Deiner Tuning Software kommt.",
        "The file that comes out of your tuning software."),
    "backup.b2z.step2": _("Aufteilung", "Split"),
    "backup.b2z.step2.idle": _(
        "So wird die .bin wieder in ihre Teile zerlegt.",
        "This is how the .bin is cut back into its parts."),
    "backup.b2z.step3": _("Zielarchiv", "Target archive"),
    "backup.b2z.step4": _("Packen", "Package"),
    "backup.b2z.btn": _("Packen", "Package"),
    "backup.b2z.foot": _(
        "Das Ergebnis ist byteweise so aufgebaut wie das Original.",
        "The result is built byte for byte like the original."),
    "backup.parts.add": _("Teil hinzufügen", "Add part"),
    "backup.parts.preset": _("Vorlage", "Preset"),
    "backup.parts.name": _("Name", "Name"),
    "backup.parts.size": _("Größe", "Size"),
    "backup.parts.sum": _("Summe", "Total"),
    "backup.parts.match": _("Größen stimmen überein", "Sizes match"),
    "backup.parts.mismatch": _(
        "{delta} Bytes Unterschied zur Datei",
        "{delta} bytes off from the file"),
    "backup.parts.empty": _(
        "Noch keine Aufteilung. Lade eine Vorlage, nimm eine Voreinstellung oder "
        "lege Zeilen an.",
        "No split set up yet. Load a template, pick a preset, or add rows."),
    "backup.parts.restored": _(
        "{n} Teile aus {source} übernommen.",
        "{n} parts taken from {source}."),
    "backup.parts.several_cars": _(
        "{n} Teile übernommen. Für diese Größe sind mehrere Fahrzeuge gemerkt: "
        "{cars}. Welches es ist, steht nicht in der .bin, also trage die "
        "Angaben zum Fahrzeug von Hand ein.",
        "{n} parts taken. More than one vehicle is remembered for this size: "
        "{cars}. Which one this is is not written in the .bin, so fill the "
        "vehicle details in by hand."),
    "backup.parts.restored_car": _(
        "{n} Teile aus {source} übernommen. Fahrzeug: {car}.",
        "{n} parts taken from {source}. Vehicle: {car}."),
    "backup.parts.ambiguous": _(
        "Diese Größe passt zu {all}. Die Aufteilung ist dieselbe, eingetragen ist "
        "{picked}. Prüfe das Feld für das Steuergerät.",
        "This size fits {all}. The split is the same either way, {picked} was "
        "filled in. Check the ECU field."),
    "backup.parts.preset_applied": _(
        "Voreinstellung {name} eingetragen.",
        "Preset {name} applied."),
    "backup.parts.unknown": _(
        "{size} Bytes passen zu keiner Voreinstellung. Öffne das Original mit "
        "Vorlage, danach ist die Aufteilung gemerkt.",
        "{size} bytes match no preset. Open the original with Template, and the "
        "split is remembered from then on."),
    "backup.parts.bad_row": _(
        "Zeile {n} hat keinen gültigen Namen oder keine gültige Größe.",
        "Row {n} has no valid name or size."),
    "backup.meta": _("Angaben zum Fahrzeug", "Vehicle details"),
    "backup.meta.hint": _(
        "Landet in der contents.ini im Archiv. Alles freiwillig.",
        "Goes into contents.ini inside the archive. All optional."),

    # ── page: settings ───────────────────────────────────────────────────────
    "settings.title": _("Einstellungen", "Settings"),
    "settings.sub": _(
        "Einmal einrichten. Danach fragt das Werkzeug nicht mehr.",
        "Set this up once. After that the tool stops asking."),
    "settings.group.general": _("Allgemein", "General"),
    "settings.group.tools": _("Werkzeuge", "Tools"),
    "settings.group.flow": _("Ablauf", "How it runs"),
    "settings.group.target": _("Ziel", "Where it lands"),
    "settings.builder": _("MHD Map Builder", "MHD map builder"),
    "settings.builder.hint": _(
        "Dein eigenes lizenziertes Programm. Einmal zeigen, danach für jeden "
        "Auftrag benutzt.",
        "Your own licensed program. Point at it once, used for every job after "
        "that."),
    "settings.toolkey": _("Tool key (.toolkey)", "Tool key (.toolkey)"),
    "settings.toolkey.hint": _(
        "Bleibt auf diesem Rechner. Wird nur in den Arbeitsordner kopiert.",
        "Stays on this machine. Only copied into the working folder."),
    "settings.library": _("Ordner mit Stock ROMs", "Stock ROM folder"),
    "settings.library.hint": _(
        "Hier wird das passende Original gesucht, wenn es nicht neben der "
        "getunten Datei liegt.",
        "Searched for the matching original when it is not next to the tuned "
        "file."),
    "settings.args": _("Zusätzliche Übergabewerte", "Extra command line arguments"),
    "settings.args.hint": _("Normalerweise leer.", "Usually empty."),
    "settings.timeout": _("Zeitablauf je Auftrag, Sekunden", "Timeout per job, seconds"),
    "settings.copy_builder": _(
        "Builder in den Arbeitsordner kopieren",
        "Copy the builder into the working folder"),
    "settings.copy_builder.hint": _(
        "Bildet den Ordner nach, den Du von Hand baust, damit der Builder immer "
        "die richtigen Dateien sieht.",
        "Mirrors the folder you build by hand, so the builder always sees the "
        "right files."),
    "settings.pass_workdir": _(
        "Arbeitsordner als Übergabewert mitgeben",
        "Pass the working folder as an argument"),
    "settings.pass_workdir.hint": _(
        "Nur nötig, wenn Deine Fassung des Werkzeugs einen Pfad erwartet.",
        "Only needed if your build of the tool expects a path."),
    "settings.prepare_only": _(
        "Ich wandle selbst um, nur den Ordner bauen",
        "I convert to .mhd myself, only prepare the folder"),
    "settings.prepare_only.hint": _(
        "Der Ordner wird die Hauptaktion und der Builder nie gestartet. Sein "
        "Pfad bleibt nützlich: er legt die .exe mit in den Ordner.",
        "The folder becomes the main action and the builder is never started. "
        "Its path stays useful: it puts the .exe into the folder."),
    "settings.keep_staging": _("Arbeitsordner behalten", "Keep the working folder"),
    "settings.keep_staging.hint": _(
        "Sonst wird er nach einem erfolgreichen Auftrag aufgeräumt.",
        "Otherwise it is cleaned up after a successful job."),
    "settings.open_after": _("Ordner nach dem Auftrag öffnen", "Open the folder afterwards"),
    "settings.output": _("Fertige Dateien", "Finished files"),
    "settings.output.hint": _(
        "Leer heißt: neben die getunte Datei.",
        "Empty means: next to the tuned file."),
    "settings.name_template": _("Name der fertigen Datei", "Name of the finished file"),
    "settings.name_template.hint": _(
        "Platzhalter: {tokens}",
        "Placeholders: {tokens}"),
    "settings.saved": _("Wird automatisch gesichert", "Saved automatically"),
    "settings.save_failed": _("Die Einstellungen lassen sich nicht schreiben",
                              "The settings file cannot be written"),
    "settings.save_now": _("Jetzt sichern", "Save now"),
    "settings.reset": _("Auf Werkseinstellung", "Back to defaults"),
    "settings.all_set": _("Alles gesetzt", "All set"),
    "settings.missing": _("{n} fehlt noch", "{n} still missing"),
    "settings.missing_plural": _("{n} fehlen noch", "{n} still missing"),

    # ── setup hint on the lock page ──────────────────────────────────────────
    "setup.title": _("Einmal einrichten", "One time setup"),
    "setup.body": _(
        "Es fehlt noch: {what}. Unter Einstellungen setzen. Danach braucht ein "
        "Auftrag nichts weiter als die getunte Datei und die VIN.",
        "Still missing: {what}. Set it under Settings. After that a job needs "
        "nothing but the tuned file and the VIN."),
    "setup.open": _("Einstellungen öffnen", "Open settings"),
    "setup.what.builder": _("der Pfad zum MHD Map Builder", "the path to your MHD map builder"),
    "setup.what.toolkey": _("Dein .toolkey", "your .toolkey"),

    # ── status line and banners ──────────────────────────────────────────────
    "status.idle": _("Bereit", "Ready"),
    "status.waiting_file": _("Wartet auf eine getunte Datei", "Waiting for a tuned file"),
    "status.resolving": _("Sucht Stock ROM, XDF und Tool key …",
                          "Looking for stock ROM, XDF and tool key …"),
    "status.checking": _("Prüft die Datei …", "Checking the file …"),
    "status.ready": _("Bereit zum Locken", "Ready to lock"),
    "status.ready_prepare": _("Bereit, den Ordner zu bauen", "Ready to build the folder"),
    "status.locking": _("Lockt …", "Locking …"),
    "status.preparing": _("Baut den Ordner …", "Building the folder …"),
    "status.locked_one": _("Gelockt", "Locked"),
    "status.stopped": _("Angehalten", "Stopped"),
    "status.blocked": _("Angehalten, die Vorprüfung hat etwas gefunden",
                        "Stopped, the pre-flight found something"),

    "banner.locked": _(
        "Die Karte ist geschrieben und auf {vin} gelockt.",
        "The map is written and locked to {vin}."),
    "banner.prepared": _(
        "Der Arbeitsordner steht. Zieh die getunte Datei auf den Builder darin.",
        "The working folder is ready. Drop the tuned file onto the builder in it."),
    "banner.batch_done": _(
        "{ok} gelockt, {failed} fehlgeschlagen, {total} insgesamt.",
        "{ok} locked, {failed} failed, {total} in total."),
    "banner.batch_prepared": _(
        "{ok} Ordner gebaut, {failed} fehlgeschlagen, {total} insgesamt.",
        "{ok} folders built, {failed} failed, {total} in total."),
    "banner.nothing": _(
        "Es wurde nichts gelockt. Das Protokoll steht im letzten Schritt.",
        "Nothing was locked. The log is in the last step."),
    "banner.log_saved": _("Protokoll gesichert als {name}.", "Log saved as {name}."),

    # ── the VIN, checked in one place and said in two languages ─────────────
    "vin.required": _(
        "Die VIN fehlt. Der Builder braucht eine <VIN>_vin.txt.",
        "VIN is required. The builder needs a <VIN>_vin.txt file."),
    "vin.length": _(
        "Die VIN hat {n} Zeichen, es müssen 17 sein.",
        "VIN length is {n}, must be 17 characters."),
    "vin.chars": _(
        "Die VIN enthält unerlaubte Zeichen. I, O und Q sind nicht zugelassen.",
        "VIN contains invalid characters. I, O and Q are not allowed."),
    "vin.ok": _("Die VIN sieht gut aus.", "VIN looks valid."),

    # ── errors that reach the surface ────────────────────────────────────────
    "err.no_tuned": _("Wähle zuerst die getunte Datei.", "Pick the tuned file first."),
    "err.vin_length": _(
        "Eine VIN hat 17 Zeichen, diese hat {n}.",
        "A VIN has 17 characters, this one has {n}."),
    "err.no_jobs": _("Die Warteschlange ist leer.", "The queue is empty."),
    "err.busy": _("Es läuft noch ein Auftrag.", "A job is still running."),
    "err.no_zip": _("Wähle zuerst ein Backup.", "Pick a backup first."),
    "err.no_bin": _("Wähle zuerst eine .bin.", "Pick a .bin first."),
    "err.no_parts": _("Es ist kein Teil angelegt.", "No part is set up."),

    # ── file dialogs ─────────────────────────────────────────────────────────
    "dlg.tuned": _("Getunte ROM wählen", "Pick the tuned ROM"),
    "dlg.stock": _("Stock ROM wählen", "Pick the stock ROM"),
    "dlg.xdf": _("XDF Definition wählen", "Pick the XDF definition"),
    "dlg.toolkey": _("Tool key wählen", "Pick the tool key"),
    "dlg.builder": _("MHD Map Builder wählen", "Pick the MHD map builder"),
    "dlg.output": _("Zielordner wählen", "Pick the output folder"),
    "dlg.library": _("Ordner mit Stock ROMs wählen", "Pick the stock ROM folder"),
    "dlg.zip": _("AutoTuner Backup wählen", "Pick the AutoTuner backup"),
    "dlg.bin": _("Datei wählen", "Pick the file"),
    "dlg.save_bin": _("Als .bin sichern", "Save as .bin"),
    "dlg.save_zip": _("Als .zip sichern", "Save as .zip"),
    "dlg.save_log": _("Protokoll sichern", "Save the log"),
    "dlg.csv": _("CSV wählen", "Pick the CSV"),
    "dlg.report": _("Bericht sichern", "Save the report"),
    "dlg.batch_files": _("Getunte Dateien wählen", "Pick the tuned files"),
    "dlg.batch_folder": _("Ordner wählen", "Pick the folder"),

    # ── the log window ───────────────────────────────────────────────────────
    "log.title": _("Protokoll", "Log"),
    "log.empty": _("Noch nichts gelaufen.", "Nothing has run yet."),
    "log.folder": _("Arbeitsordner", "Working folder"),
}
