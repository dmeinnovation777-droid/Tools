"""
AutoTuner Backup Tool · DME Innovation
======================================

Concentrates AutoTuner .zip/.bak ECU backups into a single .bin file and splits
modified .bin files back into an AutoTuner-compatible .zip backup.

Core logic uses the Python standard library only; the GUI is plain tkinter on
top of the shared DME widget kit (dme_ui.py / dme_brand.py).

© DME Innovation
"""

import datetime
import json
import os
import sys
import zipfile

import dme_brand as brand
from dme_text import t

try:
    import tkinter as tk
    from tkinter import filedialog

    import dme_ui as ui
    TK_AVAILABLE = True
except ImportError:  # headless box / python3-tk not installed
    tk = filedialog = ui = None
    TK_AVAILABLE = False

APP_NAME = "AutoTuner Backup Tool"
APP_VERSION = brand.VERSION
APP_TAGLINE = "ZIP ↔ BIN converter for AutoTuner ECU backups"


# ─────────────────────────────────────────────────────────────────────────────
# Core logic
# ─────────────────────────────────────────────────────────────────────────────

# Standard AutoTuner memory part order and names
PART_ORDER = ["iflash0.bin", "iflash1.bin", "dflash0.bin", "dflash1.bin"]
# Parts that can exist optionally
OPTIONAL_PARTS = ["eflash.bin"]

# Known ECU part layouts (name, size in bytes)
PRESETS = {
    "MED17.1.1": [("iflash0.bin", 2097152), ("iflash1.bin", 2097152),
                  ("dflash0.bin", 32768), ("dflash1.bin", 32768)],
    "MED17.5.x": [("iflash0.bin", 2097152), ("iflash1.bin", 2097152),
                  ("dflash0.bin", 65536), ("dflash1.bin", 65536)],
    "MEVD17.2.x": [("iflash0.bin", 2097152), ("iflash1.bin", 2097152),
                   ("dflash0.bin", 32768), ("dflash1.bin", 32768)],
}
# Measured, not guessed: a real Mercedes GLE 2018 bench read off an AutoTuner
# splits its 8,912,896 bytes as two parts, not four. The four-part guess that
# stood here added up to the same total and would have written an archive the
# device never produces.
PRESETS["MG1CP002"] = [("iflash0.bin", 8388608), ("dflash0.bin", 524288)]
PRESET_META = {
    "MED17.1.1": {"EcuBuild": "MED17.1.1", "EcuProducer": "Bosch", "EngineType": "PETROL"},
    "MED17.5.x": {"EcuBuild": "MED17.5", "EcuProducer": "Bosch", "EngineType": "PETROL"},
    "MEVD17.2.x": {"EcuBuild": "MEVD17.2", "EcuProducer": "Bosch", "EngineType": "PETROL"},
    "MG1CP002": {"EcuBuild": "MG1CP002", "EcuProducer": "Bosch", "EngineType": "DIESEL"},
}


# ─────────────────────────────────────────────────────────────────────────────
# Layout memory
#
# Every archive the tool opens teaches it one part layout. The layout is stored
# by total size, so a .bin this tool produced can always be split again - even
# for an ECU no preset covers.
# ─────────────────────────────────────────────────────────────────────────────
LAYOUT_LIMIT = 60


def layout_store_path() -> str:
    return os.path.join(brand.config_dir(), "autotuner_layouts.json")


def load_layouts() -> dict:
    try:
        with open(layout_store_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        return stored if isinstance(stored, dict) else {}
    except (OSError, ValueError):
        return {}


def remember_layout(parts: list[dict], label: str = "", store: dict = None,
                    how_to: str = "", meta: dict = None) -> dict:
    """Store one layout under its total size. Returns the updated store.

    `how_to` is the archive's own how-to-use-backup.html and `meta` is what its
    contents.ini said about the car. Neither can be worked out again from a
    .bin: which car a dump came from is not written anywhere in the dump. So
    both are carried across with the layout, and a .bin split months later
    still goes back into an archive that names the right car in the right
    language."""
    parts = [{"name": p["name"], "size": int(p["size"])} for p in parts if p.get("name")]
    if not parts:
        return store if store is not None else load_layouts()
    layouts = load_layouts() if store is None else store
    total = sum(p["size"] for p in parts)
    entry = {"label": label, "parts": parts}
    known = layouts.get(str(total)) if isinstance(layouts.get(str(total)), dict) else {}
    # Never lose one that is already held: a later split without the archive
    # in hand passes neither, and would otherwise wipe both.
    entry["how_to"] = how_to or known.get("how_to", "")
    entry["meta"] = {k: v for k, v in (meta or {}).items() if v} or known.get("meta", {})
    layouts[str(total)] = entry
    if len(layouts) > LAYOUT_LIMIT:
        for key in list(layouts)[:len(layouts) - LAYOUT_LIMIT]:
            layouts.pop(key, None)
    try:
        os.makedirs(os.path.dirname(layout_store_path()), exist_ok=True)
        with open(layout_store_path(), "w", encoding="utf-8") as handle:
            json.dump(layouts, handle, indent=2)
    except OSError:
        pass
    return layouts


def layout_for_size(size: int, store: dict = None) -> tuple[list[dict], str] | None:
    """A remembered layout whose parts add up to exactly this file size."""
    layouts = load_layouts() if store is None else store
    entry = layouts.get(str(int(size)))
    if not entry or not entry.get("parts"):
        return None
    return entry["parts"], entry.get("label", "")


def remembered_how_to(size: int, store: dict = None) -> str:
    """The how-to-use page that came with the archive of this total size."""
    layouts = load_layouts() if store is None else store
    entry = layouts.get(str(int(size)))
    return (entry or {}).get("how_to", "")


def remembered_meta(size: int, store: dict = None) -> dict:
    """What the archive of this total size said about the car."""
    layouts = load_layouts() if store is None else store
    entry = layouts.get(str(int(size)))
    return dict((entry or {}).get("meta", {}))


def presets_for_size(size: int) -> list[str]:
    """Every preset with this total. More than one means the size alone cannot
    tell the ECUs apart - they cut identically, but the name differs, and the
    name is what lands in the customer's contents.ini."""
    return [name for name, parts in PRESETS.items()
            if sum(part_size for _, part_size in parts) == size]


def preset_for_size(size: int) -> str | None:
    for name, parts in PRESETS.items():
        if sum(part_size for _, part_size in parts) == size:
            return name
    return None


def part_sort_key(name: str):
    """Known AutoTuner parts first in standard order, then any extras."""
    nl = name.lower()
    for i, p in enumerate(PART_ORDER):
        if nl == p:
            return i
    return len(PART_ORDER) + (ord(nl[0]) if nl else 0)


def zip_to_bin(zip_path: str, output_path: str) -> tuple[bool, str, list[dict]]:
    """
    Extract all .bin parts from an AutoTuner .zip/.bak and concatenate them.
    Returns (success, message, parts_info)
    parts_info = [{'name': str, 'size': int, 'offset': int}, ...]
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            bin_files = [n for n in names if n.lower().endswith('.bin')]
            if not bin_files:
                return False, "No .bin files found in the archive.", []

            bin_files.sort(key=part_sort_key)

            parts_info = []
            offset = 0
            combined = bytearray()

            for name in bin_files:
                data = zf.read(name)
                parts_info.append({'name': name, 'size': len(data), 'offset': offset})
                combined.extend(data)
                offset += len(data)

            with open(output_path, 'wb') as f:
                f.write(combined)

            return True, (f"Combined {len(bin_files)} part(s) → "
                          f"{os.path.getsize(output_path):,} bytes"), parts_info

    except zipfile.BadZipFile:
        return False, "File is not a valid ZIP archive.", []
    except Exception as e:
        return False, f"Error: {e}", []


def build_contents_ini(meta: dict = None) -> str:
    """Render the AutoTuner contents.ini for the given metadata."""
    meta = meta or {}
    ini_lines = [
        "[Global]",
        "EcuX_version = 0.3",
        "AuthorTool = Autotuner",
        "",
        "[Description]",
        f"VehicleVIN = {meta.get('vin', '')}",
        f"VehicleType = {meta.get('type', 'Passenger car')}",
        f"VehicleProducer = {meta.get('make', '')}",
        f"VehicleSeries = {meta.get('series', '')}",
        f"VehicleBuild = {meta.get('model', '')}",
        f"VehicleModel = {meta.get('variant', '')}",
        f"VehicleModelYear = {meta.get('year', '')}",
        f"EcuUsage = {meta.get('usage', 'Engine')}",
        f"EcuProducer = {meta.get('ecu_maker', '')}",
        f"EcuBuild = {meta.get('ecu_model', '')}",
        f"EngineType = {meta.get('fuel', '')}",
        f"OutputPS = {meta.get('ps', '')}",
        f"OutputKW = {meta.get('kw', '')}",
        f"ReadingHardware = {meta.get('hardware', 'Autotuner')}",
    ]
    return "\r\n".join(ini_lines) + "\r\n"


HOW_TO_NAME = "how-to-use-backup.html"

# The fallback only. A real backup carries this page translated into the
# operator's language - a German read has the offline notice in German and two
# extra <meta> lines - so whenever the source archive is known its own copy is
# carried across instead. Verified against a VW Caddy MD1CS004 bench read.
HOW_TO_USE_HTML = (
    "<!DOCTYPE html>\r\n<html lang=\"en\">\r\n<head>\r\n"
    "<meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\">\r\n"
    "<title>Autotuner</title>\r\n</head>\r\n<body>\r\n<p id=\"message\"/>\r\n"
    "<script type=\"text/javascript\">\r\n"
    "if (navigator.onLine) {\r\n"
    "    window.location.href =\"http://help.autotuner-tool.com/en/articles/2984015-backup-file\";\r\n"
    "} else {\r\n"
    "    document.getElementById(\"message\").innerHTML ="
    "\"Your browser is currently not connected to the Internet.</br>"
    " Please, check that the Internet connection is working.\";\r\n"
    "}\r\n</script>\r\n</body>\r\n</html>"
)


def bin_to_zip(bin_path: str, output_path: str, parts_config: list[dict],
               ini_meta: dict = None, how_to_html: str = "") -> tuple[bool, str]:
    """
    Split a .bin file into named parts per parts_config and pack into an AutoTuner .zip.
    parts_config = [{'name': str, 'size': int}, ...], sizes must sum to bin file size.

    `how_to_html` is the source archive's own how-to-use-backup.html. Pass it and
    it is carried across unchanged; the built-in English page is only the
    fallback for a .bin that never came from an archive.
    """
    try:
        with open(bin_path, 'rb') as f:
            data = f.read()

        total = sum(p['size'] for p in parts_config)
        if total != len(data):
            return False, (
                f"Size mismatch: parts total {total:,} bytes, "
                f"but .bin is {len(data):,} bytes.\n"
                "Please adjust the part sizes so they sum to the .bin file size."
            )

        ini_content = build_contents_ini(ini_meta)

        offset = 0
        with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for part in parts_config:
                chunk = data[offset:offset + part['size']]
                zf.writestr(part['name'], chunk)
                offset += part['size']
            zf.writestr("contents.ini", ini_content)
            zf.writestr(HOW_TO_NAME, how_to_html or HOW_TO_USE_HTML)

        return True, (f"Created {len(parts_config)} part(s) → "
                      f"{os.path.getsize(output_path):,} bytes")

    except Exception as e:
        return False, f"Error: {e}"


def parse_ini(content: str) -> dict:
    """Parse a simple INI file into a dict."""
    result = {}
    for line in content.splitlines():
        line = line.strip()
        if '=' in line and not line.startswith('['):
            k, _, v = line.partition('=')
            result[k.strip()] = v.strip()
    return result


def format_bytes(n: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def read_archive_info(zip_path: str) -> dict:
    """Inspect an AutoTuner backup without extracting it."""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = zf.namelist()
        bin_names = sorted([n for n in names if n.lower().endswith('.bin')],
                           key=part_sort_key)
        parts, offset = [], 0
        for name in bin_names:
            size = zf.getinfo(name).file_size
            parts.append({'name': name, 'size': size, 'offset': offset})
            offset += size
        extras = [{'name': n, 'size': zf.getinfo(n).file_size}
                  for n in names if not n.lower().endswith('.bin')]
        meta = {}
        if 'contents.ini' in names:
            meta = parse_ini(zf.read('contents.ini').decode('utf-8', errors='replace'))
        # The AutoTuner writes this page in the operator's language. It cannot be
        # reconstructed, only carried across - so read it out while we are here.
        how_to = ""
        if HOW_TO_NAME in names:
            how_to = zf.read(HOW_TO_NAME).decode('utf-8', errors='replace')
    return {'parts': parts, 'extras': extras, 'meta': meta, 'how_to': how_to,
            'total': offset, 'count': len(parts)}


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

# What contents.ini calls each field, and what this code calls it. Nine of the
# fourteen have a box on the page; the other five have none and are simply
# carried across from the archive the .bin came out of. Without this the series
# and the kW of a customer's car would quietly go missing on the way back.
INI_KEYS = {
    "VehicleVIN": "vin",            "VehicleType": "type",
    "VehicleProducer": "make",      "VehicleSeries": "series",
    "VehicleBuild": "model",        "VehicleModel": "variant",
    "VehicleModelYear": "year",     "EcuUsage": "usage",
    "EcuProducer": "ecu_maker",     "EcuBuild": "ecu_model",
    "EngineType": "fuel",           "OutputPS": "ps",
    "OutputKW": "kw",               "ReadingHardware": "hardware",
}

META_FIELDS = [
    ("VehicleProducer", "Make", "e.g. Lamborghini"),
    ("VehicleBuild", "Model", "e.g. Huracan"),
    ("VehicleModel", "Variant", "e.g. 5.2 V10 FSI"),
    ("VehicleModelYear", "Year", "e.g. 2014"),
    ("EcuBuild", "ECU", "e.g. MED17.1.1"),
    ("EcuProducer", "ECU maker", "e.g. Bosch"),
    ("EngineType", "Fuel", "PETROL / DIESEL"),
    ("OutputPS", "Power (PS)", "e.g. 610"),
    ("VehicleVIN", "VIN", "17 characters"),
]

class PartRow:
    """One row of the split table, laid out in the shared grid container."""

    # Six categories on a light ground. Checked with the palette validator:
    # every adjacent pair separates for normal and colour-blind vision, and
    # each clears 3:1 against the card it sits on. The first is the brand
    # amber darkened, because amber itself carries only 1.9:1 on white.
    COLOURS = ("#A66A00", "#0071E3", "#1B7F49", "#C4271F", "#6D4AAF", "#AD4570")

    def __init__(self, table, name="", size=0, on_change=None, on_delete=None):
        self.table = table
        self.on_change = on_change
        bg = ui.CARD

        self.index_lbl = tk.Label(table, text="", bg=bg, fg=ui.TEXT_FAINT,
                                  font=ui.f("mono_sm"), width=2, anchor="e")
        self.swatch = tk.Frame(table, bg=self.COLOURS[0], width=3)
        self.name_var = tk.StringVar(value=name)
        self.name_entry = ui.entry(table, self.name_var)
        self.size_var = tk.StringVar(value=str(size) if size else "")
        self.size_entry = ui.entry(table, self.size_var, justify="right")
        self.human_lbl = tk.Label(table, text="", bg=bg, fg=ui.TEXT_DIM,
                                  font=ui.f("small"), width=9, anchor="e")
        self.del_btn = ui.icon_button(table, "✕", on_delete, bg=bg)

        self.size_var.trace_add('write', self._changed)
        self.name_var.trace_add('write', self._changed)

    def _changed(self, *_):
        self.human_lbl.config(text=format_bytes(self.size) if self.size else "")
        if self.on_change:
            self.on_change()

    @property
    def size(self) -> int:
        try:
            return int(self.size_var.get().replace(',', '').replace(' ', '').replace('.', ''))
        except ValueError:
            return 0

    @property
    def colour(self) -> str:
        return self.swatch['bg']

    def mount(self, row: int):
        self.index_lbl.grid(row=row, column=0, sticky="e", padx=(0, 6), pady=3)
        self.swatch.grid(row=row, column=1, sticky="ns", padx=(0, 8), pady=5)
        self.name_entry.grid(row=row, column=2, sticky="ew", ipady=5, pady=3)
        self.size_entry.grid(row=row, column=3, sticky="ew", ipady=5, padx=(10, 0), pady=3)
        self.human_lbl.grid(row=row, column=4, sticky="e", padx=(10, 0), pady=3)
        self.del_btn.grid(row=row, column=5, sticky="e", padx=(8, 0), pady=3)
        self.index_lbl.config(text=f"{row}")
        self.swatch.config(bg=self.COLOURS[(row - 1) % len(self.COLOURS)])
        self._changed()

    @property
    def is_blank(self) -> bool:
        """Nothing has been typed here yet, so this is not a part.

        Pressing "add a part" makes an empty line to fill in. Until it is
        filled in it is a promise, not a part: it may not be counted, it may
        not be packed, and above all it may not stop the archive from being
        written.
        """
        return not self.name_var.get().strip() and not self.size_var.get().strip()

    @property
    def is_broken(self) -> bool:
        """Half filled in: a name without a size, or a size without a name.

        This one is a real mistake and has to be said out loud straight away,
        not held back until the button is pressed.
        """
        return not self.is_blank and self.get() is None

    def get(self) -> dict | None:
        name = self.name_var.get().strip()
        if not name:
            return None
        try:
            size = int(self.size_var.get().replace(',', '').replace(' ', '').replace('.', ''))
        except ValueError:
            return None
        if size <= 0:
            return None
        return {'name': name, 'size': size}

    def mark(self, broken: bool):
        """Show on the line itself which one is the matter."""
        colour = ui.ERR if broken else ui.FIELD_BORDER
        for field in (self.name_entry, self.size_entry):
            if hasattr(field, "_edge"):
                field._edge(colour)

    def destroy(self):
        for w in (self.index_lbl, self.swatch, self.name_entry, self.size_entry,
                  self.human_lbl, self.del_btn):
            w.destroy()


class BackupUI:
    """The Backup area: one page, two directions, the same four steps in each.

    It used to be a window with two sidebar pages. The two directions are now a
    switch beside the page title, because they are the same job in reverse and
    nobody has to hunt for the way back.
    """

    def __init__(self, app):
        self.app = app
        self._archive_info: dict | None = None
        self._part_rows: list[PartRow] = []
        self._last_output: str | None = None
        self._direction = "z2b"

        self._z2b_zip_var = tk.StringVar()
        self._z2b_out_var = tk.StringVar()
        self._b2z_bin_var = tk.StringVar()
        self._b2z_out_var = tk.StringVar()
        self._z2b_summary = tk.StringVar()
        self._b2z_summary = tk.StringVar()
        self._b2z_total_var = tk.StringVar()
        self._meta_vars = {key: tk.StringVar() for key, _l, _p in META_FIELDS}
        self._traced = False

    # ── the page ────────────────────────────────────────────────────────────
    def build_page(self):
        page = ui.Page(self.app.host, width=900)
        self.page = page
        self.banner = page.banner
        self._z2b_banner = page.banner
        self._b2z_banner = page.banner

        self.switch = ui.Segmented(
            self.app.shell.title_slot,
            [("z2b", t("backup.seg.z2b")), ("b2z", t("backup.seg.b2z"))],
            command=self._set_direction, bg=ui.BG)
        self.switch.pack()

        self._z2b = tk.Frame(page.body, bg=ui.BG)
        self._b2z = tk.Frame(page.body, bg=ui.BG)
        self._build_zip_to_bin(self._z2b)
        self._build_bin_to_zip(self._b2z)

        self._summary = tk.StringVar()
        page.summary(self._summary)
        self.btn_run = ui.button(page.action_row, t("backup.z2b.btn"), self._run,
                                 variant="primary", size="lg", bg=ui.SURFACE)
        self.btn_run.pack(side=tk.RIGHT)
        self._show_direction()
        return page

    def after_mount(self):
        if not self._traced:
            self._z2b_zip_var.trace_add("write", lambda *_: self._on_zip_path_changed())
            self._b2z_bin_var.trace_add("write", lambda *_: self._on_bin_path_changed())
            self._traced = True
        self._refresh_parts()
        self._on_zip_path_changed()
        self.switch.select(self._direction, notify=False)
        self._show_direction()

    def on_shown(self):
        self.app.shell.set_subtitle("backup", t(f"backup.sub.{self._direction}"))

    def _set_direction(self, key):
        """Change direction, wherever the change came from.

        Clicking the switch already moves it, so this is for every other way
        in. Without it the switch could sit on one direction while the page
        below showed the other, which is exactly the sort of thing nobody
        notices until it matters.
        """
        self._direction = key
        if self.switch is not None and self.switch.active != key:
            self.switch.select(key, notify=False)
        self._show_direction()
        self.on_shown()

    def _show_direction(self):
        for frame in (self._z2b, self._b2z):
            frame.pack_forget()
        target = self._z2b if self._direction == "z2b" else self._b2z
        target.pack(fill=tk.X)
        self.btn_run.configure(text=t(f"backup.{self._direction}.btn"))
        self._summary.set(self._z2b_summary.get() if self._direction == "z2b"
                          else self._b2z_summary.get())

    def _run(self):
        if self._direction == "z2b":
            self._run_zip_to_bin()
        else:
            self._run_bin_to_zip()

    def _file_row(self, parent, variable, on_browse, hint="", browse=None):
        holder = tk.Frame(parent, bg=ui.BG)
        row = tk.Frame(holder, bg=ui.BG)
        row.pack(fill=tk.X)
        field = ui.entry(row, variable)
        field.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=ui.px(7))
        ui.button(row, browse or t("word.choose"), on_browse, variant="secondary",
                  size="md", bg=ui.BG).pack(side=tk.LEFT, padx=(ui.px(9), 0))
        label = tk.Label(holder, text=hint, bg=ui.BG, fg=ui.TEXT_FAINT,
                         font=ui.f("small"), anchor="w", justify="left")
        label.pack(fill=tk.X, pady=(ui.px(7), 0))
        ui.wrap_to_parent(label)
        holder.hint = label
        return holder

    # ── ZIP to BIN ──────────────────────────────────────────────────────────
    def _build_zip_to_bin(self, parent):
        flow = ui.Flow(parent)
        flow.pack(fill=tk.X)
        self._z2b_flow = flow

        step = flow.step(t("backup.z2b.step1"), state="now", symbol="archive")
        self._z2b_step1 = step
        self._z2b_path = self._file_row(step.body, self._z2b_zip_var, self._browse_zip,
                                        hint=t("backup.z2b.step1.hint"))
        self._z2b_path.pack(fill=tk.X)

        step = flow.step(t("backup.z2b.step2"), symbol="list")
        self._z2b_step2 = step
        self._z2b_log = ui.LogView(step.body, height=11)
        self._z2b_log.pack(fill=tk.BOTH, expand=True)
        self._z2b_log.set_text(t("backup.z2b.step2.idle"), "dim")

        step = flow.step(t("backup.z2b.step3"), symbol="file")
        self._z2b_step3 = step
        self._z2b_out_path = self._file_row(step.body, self._z2b_out_var,
                                            self._browse_zip_output,
                                            hint=t("backup.z2b.step3.hint"),
                                            browse=t("word.save"))
        self._z2b_out_path.pack(fill=tk.X)

        step = flow.step(t("backup.z2b.step4"), symbol="lock")
        self._z2b_step4 = step
        note = tk.Label(step.body, text=t("backup.z2b.foot"), bg=ui.BG,
                        fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w", justify="left")
        note.pack(fill=tk.X)
        ui.wrap_to_parent(note)

    def _on_zip_path_changed(self):
        path = self._z2b_zip_var.get().strip()
        if not path:
            self._z2b_path.hint.configure(text=t("backup.z2b.step1.hint"),
                                          fg=ui.TEXT_FAINT)
            self._z2b_step1.set_state("now")
        elif not os.path.exists(path):
            self._z2b_path.hint.configure(text=t("word.not_found"), fg=ui.ERR)
            self._z2b_step1.set_state("err")
        else:
            self._analyze_zip()

    def _browse_zip(self):
        path = filedialog.askopenfilename(
            title=t("dlg.zip"),
            filetypes=[("AutoTuner backup", "*.zip *.bak"), ("All files", "*.*")])
        if path:
            self._z2b_zip_var.set(path)
            self._z2b_out_var.set(os.path.splitext(path)[0] + "_combined.bin")
            self._analyze_zip()

    def _browse_zip_output(self):
        path = filedialog.asksaveasfilename(
            title=t("dlg.save_bin"), defaultextension=".bin",
            filetypes=[("Binary file", "*.bin"), ("All files", "*.*")])
        if path:
            self._z2b_out_var.set(path)

    def _z2b_state(self, ok):
        self._z2b_step1.set_state("done" if ok else "now")
        self._z2b_step2.set_state("done" if ok else "next")
        self._z2b_step3.set_state("done" if ok and self._z2b_out_var.get().strip()
                                  else ("now" if ok else "next"))
        self._z2b_step4.set_state("now" if ok and self._z2b_out_var.get().strip()
                                  else "next")

    def _analyze_zip(self):
        zip_path = self._z2b_zip_var.get().strip()
        if not zip_path or not os.path.exists(zip_path):
            self._archive_info = None
            self._z2b_log.set_text(t("backup.z2b.step2.idle"), "dim")
            self._z2b_summary.set(t("err.no_zip"))
            self._z2b_state(False)
            return
        try:
            info = read_archive_info(zip_path)
        except zipfile.BadZipFile:
            self._archive_info = None
            self._z2b_log.set_text("Not a valid ZIP archive.", "error")
            self._z2b_path.hint.configure(text="Not a valid ZIP archive.", fg=ui.ERR)
            self._z2b_step1.set_state("err")
            self.app.set_status(t("word.failed"), "error")
            return
        except Exception as exc:
            self._archive_info = None
            self._z2b_log.set_text(str(exc), "error")
            self._z2b_step1.set_state("err")
            self.app.set_status(t("word.failed"), "error")
            return

        self._archive_info = info
        self._z2b_log.clear()
        self._z2b_log.write(f"{'#':>2}  {'PART':<24}{'SIZE':>12}{'OFFSET':>14}", "dim")
        self._z2b_log.write("\u2500" * 54, "dim")
        for i, part in enumerate(info['parts'], 1):
            self._z2b_log.write(
                f"{i:>2}  {part['name']:<24}{format_bytes(part['size']):>12}"
                f"{part['offset']:>14,}", "accent")
        for extra in info['extras']:
            self._z2b_log.write(
                f"    {extra['name']:<24}{format_bytes(extra['size']):>12}"
                f"{'metadata':>14}", "dim")
        self._z2b_log.write("\u2500" * 54, "dim")
        self._z2b_log.write(f"    {'Total binary data':<24}"
                            f"{format_bytes(info['total']):>12}"
                            f"{info['total']:>14,}", "ok")
        meta = info['meta']
        if meta:
            vehicle = " ".join(x for x in (meta.get('VehicleProducer', ''),
                                           meta.get('VehicleBuild', ''),
                                           meta.get('VehicleModel', '')) if x)
            year = meta.get('VehicleModelYear', '')
            self._z2b_log.write("")
            self._z2b_log.write(f"    Vehicle : {vehicle} {f'({year})' if year else ''}".rstrip())
            self._z2b_log.write(f"    ECU     : {meta.get('EcuProducer', '')} "
                                f"{meta.get('EcuBuild', '')}".rstrip())
            if meta.get('VehicleVIN'):
                self._z2b_log.write(f"    VIN     : {meta['VehicleVIN']}")

        self._z2b_path.hint.configure(
            text=f"{os.path.basename(zip_path)} \u00b7 {format_bytes(info['total'])}",
            fg=ui.OK)
        self._z2b_step2.set_note(f"{info['count']} \u00b7 {format_bytes(info['total'])}")
        self._z2b_log.scroll_top()
        self._z2b_summary.set(f"{info['count']} \u00b7 {info['total']:,} {t('word.bytes')}")
        self._z2b_state(True)
        if self._direction == "z2b":
            self._summary.set(self._z2b_summary.get())
            self.app.set_status(t("word.ready"), "ok")

    def _run_zip_to_bin(self):
        zip_path = self._z2b_zip_var.get().strip()
        out_path = self._z2b_out_var.get().strip()
        if not zip_path:
            self.banner.show("error", t("err.no_zip"))
            return
        if not out_path:
            self.banner.show("error", t("backup.z2b.step3.hint"))
            return

        self.app.set_status(t("word.running"), "busy")
        self.banner.show("busy", t("word.running"))
        self._z2b_step4.set_state("now")
        self._z2b_step4.set_running(True)
        self.app.update_idletasks()

        ok, msg, parts = zip_to_bin(zip_path, out_path)
        info = self._archive_info or {}
        how_to = info.get("how_to", "")
        if ok:
            remember_layout(parts, os.path.basename(zip_path), how_to=how_to,
                            meta=info.get("meta", {}))
            self.banner.show("ok", msg, action_text=t("word.open_folder"),
                             action=lambda: ui.reveal_in_file_manager(out_path))
            self.app.set_status(t("word.done"), "ok")
            self._z2b_step4.set_running(False)
            self._z2b_step4.set_state("done")
            self._z2b_step4.set_note(os.path.basename(out_path))
            self._z2b_summary.set(f"{len(parts)} \u00b7 "
                                  f"{os.path.getsize(out_path):,} {t('word.bytes')}")
            self._summary.set(self._z2b_summary.get())
        else:
            self.banner.show("error", msg)
            self._z2b_step4.set_running(False)
            self._z2b_step4.set_state("err")
            self.app.set_status(t("word.failed"), "error")

    # ── BIN to ZIP ──────────────────────────────────────────────────────────
    def _build_bin_to_zip(self, parent):
        flow = ui.Flow(parent)
        flow.pack(fill=tk.X)
        self._b2z_flow = flow

        step = flow.step(t("backup.b2z.step1"), state="now", symbol="file")
        self._b2z_step1 = step
        self._b2z_path = self._file_row(step.body, self._b2z_bin_var, self._browse_bin,
                                        hint=t("backup.b2z.step1.hint"))
        self._b2z_path.pack(fill=tk.X)

        step = flow.step(t("backup.b2z.step2"), symbol="list")
        self._b2z_step2 = step
        toolbar = tk.Frame(step.body, bg=ui.BG)
        toolbar.pack(fill=tk.X, pady=(0, ui.px(10)))
        ui.button(toolbar, t("backup.parts.preset"), self._load_parts_from_zip,
                  variant="secondary", size="sm", bg=ui.BG).pack(side=tk.LEFT)
        for preset in PRESETS:
            ui.button(toolbar, preset, lambda p=preset: self._load_preset(p),
                      variant="secondary", size="sm",
                      bg=ui.BG).pack(side=tk.LEFT, padx=(ui.px(7), 0))
        ui.button(toolbar, t("backup.parts.add"), self._add_part_row, variant="ghost",
                  size="sm", bg=ui.BG).pack(side=tk.RIGHT)

        head = tk.Frame(step.body, bg=ui.BG)
        head.pack(fill=tk.X)
        for col, (label, weight, anchor, width) in enumerate([
                ("#", 0, "e", 2), ("", 0, "w", 1),
                (t("backup.parts.name").upper(), 3, "w", 0),
                (t("backup.parts.size").upper(), 2, "e", 0),
                ("", 0, "e", 9), ("", 0, "e", 3)]):
            lbl = tk.Label(head, text=label, bg=ui.BG, fg=ui.TEXT_FAINT,
                           font=ui.f("micro"), anchor=anchor)
            lbl.grid(row=0, column=col, sticky="ew",
                     padx=(0, 6) if col == 0 else (10 if col in (3, 4) else 0, 0))
            if width:
                lbl.config(width=width)
            head.grid_columnconfigure(col, weight=weight)
        ui.hr(step.body, bg=ui.BORDER_SOFT, pady=(ui.px(4), ui.px(2)))

        self._parts_table = tk.Frame(step.body, bg=ui.BG)
        self._parts_table.pack(fill=tk.X)
        for col, weight in ((0, 0), (1, 0), (2, 3), (3, 2), (4, 0), (5, 0)):
            self._parts_table.grid_columnconfigure(col, weight=weight)
        self._parts_empty = tk.Label(self._parts_table, text="", bg=ui.BG,
                                     fg=ui.TEXT_FAINT, font=ui.f("small"),
                                     anchor="w", pady=ui.px(14), justify="left")

        self._split_canvas = tk.Canvas(step.body, bg=ui.BG, height=ui.px(10),
                                       highlightthickness=0, bd=0)
        self._split_canvas.pack(fill=tk.X, pady=(ui.px(14), ui.px(8)))
        self._split_canvas.bind("<Configure>", lambda _e: self._draw_split_bar())

        totals = tk.Frame(step.body, bg=ui.BG)
        totals.pack(fill=tk.X)
        tk.Label(totals, textvariable=self._b2z_total_var, bg=ui.BG, fg=ui.TEXT_DIM,
                 font=ui.f("small")).pack(side=tk.LEFT)
        self._b2z_match = tk.Label(totals, text="", bg=ui.BG, font=ui.f("small"))
        self._b2z_match.pack(side=tk.RIGHT)

        step = flow.step(t("backup.b2z.step3"), symbol="archive")
        self._b2z_step3 = step
        self._b2z_out_path = self._file_row(step.body, self._b2z_out_var,
                                            self._browse_zip_out,
                                            hint=t("backup.b2z.foot"),
                                            browse=t("word.save"))
        self._b2z_out_path.pack(fill=tk.X)

        step = flow.step(t("backup.b2z.step4"), symbol="lock")
        self._b2z_step4 = step
        meta = ui.Collapsible(step.body, t("backup.meta"), bg=ui.BG)
        meta.pack(fill=tk.X)
        grid = tk.Frame(meta.body, bg=ui.BG)
        grid.pack(fill=tk.X, pady=(ui.px(8), 0))
        for i, (key, label, placeholder) in enumerate(META_FIELDS):
            cell = ui.LabeledEntry(grid, f"{label} ({placeholder})",
                                   self._meta_vars[key], bg=ui.BG)
            cell.grid(row=i // 3, column=i % 3, sticky="ew",
                      padx=(0 if i % 3 == 0 else ui.px(12), 0), pady=(0, ui.px(10)))
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1, uniform="meta")
        hint = tk.Label(step.body, text=t("backup.meta.hint"), bg=ui.BG,
                        fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w", justify="left")
        hint.pack(fill=tk.X, pady=(ui.px(8), 0))
        ui.wrap_to_parent(hint)

    # ── Split table plumbing ────────────────────────────────────────────────
    def _add_part_row(self, name="", size=0):
        row = PartRow(self._parts_table, name=name, size=size,
                      on_change=self._update_totals)
        row.del_btn.config(command=lambda r=row: self._delete_part_row(r))
        self._part_rows.append(row)
        self._refresh_parts()

    def _delete_part_row(self, row):
        if row in self._part_rows:
            self._part_rows.remove(row)
            row.destroy()
            self._refresh_parts()

    def _clear_part_rows(self):
        for row in self._part_rows:
            row.destroy()
        self._part_rows.clear()

    def _refresh_parts(self):
        self._parts_empty.grid_forget()
        for i, row in enumerate(self._part_rows, 1):
            row.mount(i)
        if not self._part_rows:
            size = self._bin_size()
            if size and not layout_for_size(size) and not preset_for_size(size):
                self._empty_hint(size)
            else:
                self._parts_empty.config(text=t("backup.parts.empty"))
            self._parts_empty.grid(row=0, column=0, columnspan=6, sticky="ew")
        real = [row for row in self._part_rows if not row.is_blank]
        self._b2z_step2.set_note(str(len(real)) if real else "")
        self._update_totals()

    def _bin_size(self) -> int:
        path = self._b2z_bin_var.get().strip()
        return os.path.getsize(path) if path and os.path.exists(path) else 0

    def _update_totals(self):
        """What the screen says has to be what pressing the button will do.

        An empty line is left out of all of it: out of the count, out of the
        sum, and out of the archive. A half filled one is named here, at the
        moment it becomes half filled, instead of stopping the run later.
        """
        real = [row for row in self._part_rows if not row.is_blank]
        broken = next((i for i, row in enumerate(self._part_rows, 1)
                       if row.is_broken), None)
        for row in self._part_rows:
            row.mark(row.is_broken)

        total = sum(row.size for row in real)
        file_size = self._bin_size()
        self._b2z_total_var.set(
            f"{t('backup.parts.sum')} {total:,} B ({format_bytes(total)})  \u00b7  "
            f"{format_bytes(file_size)}")
        ready = False
        if broken is not None:
            message = t("backup.parts.bad_row", n=broken)
            self._b2z_match.config(text="\u2715  " + message, fg=ui.ERR)
            self._b2z_summary.set(message)
        elif file_size == 0:
            self._b2z_match.config(text="")
        elif not real:
            self._b2z_match.config(text="")
            self._b2z_summary.set(t("backup.parts.empty"))
        elif total == file_size:
            self._b2z_match.config(text="\u2713  " + t("backup.parts.match"), fg=ui.OK)
            self._b2z_summary.set(f"{len(real)} \u00b7 {total:,} "
                                  f"{t('word.bytes')}")
            ready = True
        else:
            delta = f"{abs(total - file_size):,}"
            self._b2z_match.config(text="\u2715  " + t("backup.parts.mismatch",
                                                      delta=delta), fg=ui.ERR)
            self._b2z_summary.set(t("backup.parts.mismatch", delta=delta))
        self._b2z_step1.set_state("done" if file_size else "now")
        self._b2z_step2.set_state("done" if ready else
                                  ("err" if file_size and real else "next"))
        self._b2z_step3.set_state("done" if ready and self._b2z_out_var.get().strip()
                                  else ("now" if ready else "next"))
        self._b2z_step4.set_state("now" if ready and self._b2z_out_var.get().strip()
                                  else "next")
        if self._direction == "b2z":
            self._summary.set(self._b2z_summary.get())
        self._draw_split_bar()

    def _draw_split_bar(self):
        canvas = self._split_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        if width <= 1:
            return
        height = ui.px(10)
        total = sum(row.size for row in self._part_rows)
        file_size = self._bin_size()
        scale_total = max(total, file_size, 1)
        canvas.create_rectangle(0, 0, width, height, fill=ui.FIELD, outline="")
        x = 0.0
        for row in self._part_rows:
            if row.size <= 0:
                continue
            w = width * row.size / scale_total
            canvas.create_rectangle(x, 0, x + w, height, fill=row.colour, outline="")
            x += w
        if file_size and total > file_size:
            over_x = width * file_size / scale_total
            canvas.create_rectangle(over_x, 0, width, height, outline=ui.ERR, width=1)

    def _on_bin_path_changed(self):
        path = self._b2z_bin_var.get().strip()
        if not path:
            self._b2z_path.hint.configure(text=t("backup.b2z.step1.hint"),
                                          fg=ui.TEXT_FAINT)
        elif not os.path.exists(path):
            self._b2z_path.hint.configure(text=t("word.not_found"), fg=ui.ERR)
        else:
            size = os.path.getsize(path)
            self._b2z_path.hint.configure(
                text=f"{os.path.basename(path)} \u00b7 {size:,} {t('word.bytes')} "
                     f"({format_bytes(size)})", fg=ui.OK)
            self._auto_layout(size)
        self._update_totals()

    def _auto_layout(self, size: int):
        """Fill the split table by itself: remembered layout first, preset second."""
        if self._part_rows:
            return
        remembered = layout_for_size(size)
        if remembered:
            parts, label = remembered
            for part in parts:
                self._add_part_row(name=part["name"], size=part["size"])
            self._refresh_parts()
            # The car comes back with the layout. Which car a dump came from
            # is written nowhere in the dump, so if it is not carried across
            # here it is gone, and the archive would go back to the customer
            # naming no car at all.
            car = self._restore_meta(remembered_meta(size))
            if car:
                self.banner.show("ok", t("backup.parts.restored_car",
                                         n=len(parts), car=car,
                                         source=label or t("word.manual")))
            else:
                self.banner.show("ok", t("backup.parts.restored", n=len(parts),
                                         source=label or t("word.manual")))
            self.app.set_status(t("word.ready"), "ok")
            return
        candidates = presets_for_size(size)
        if candidates:
            self._load_preset(candidates[0])
            if len(candidates) > 1:
                # Same split either way, but the ECU name goes into the
                # customer's contents.ini, so do not let it be a silent guess.
                self.banner.show("warn", t("backup.parts.ambiguous",
                                           all=" / ".join(candidates),
                                           picked=candidates[0]))
            else:
                self.banner.show("info", t("backup.parts.preset_applied",
                                           name=candidates[0]))
            return
        self._empty_hint(size)

    def _restore_meta(self, meta: dict) -> str:
        """Put remembered vehicle data into the fields, without overwriting typing.

        Gives back the car in a few words, so the page can say out loud which
        one came back. Silently restoring it would be the same kind of quiet
        as silently losing it.
        """
        for key, value in (meta or {}).items():
            var = self._meta_vars.get(key)
            if var is not None and value and not var.get().strip():
                var.set(value)
        named = [(meta or {}).get(key, "").strip() for key in
                 ("VehicleProducer", "VehicleBuild", "VehicleModelYear")]
        return " ".join(word for word in named if word)

    def _empty_hint(self, size: int):
        self._parts_empty.config(text=t("backup.parts.unknown", size=f"{size:,}"))

    def _browse_bin(self):
        path = filedialog.askopenfilename(
            title=t("dlg.bin"),
            filetypes=[("Binary file", "*.bin"), ("All files", "*.*")])
        if not path:
            return
        self._b2z_bin_var.set(path)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self._b2z_out_var.set(os.path.join(os.path.dirname(path), f"{stamp}-backup.zip"))

    def _browse_zip_out(self):
        path = filedialog.asksaveasfilename(
            title=t("dlg.save_zip"), defaultextension=".zip",
            filetypes=[("AutoTuner backup", "*.zip"), ("All files", "*.*")])
        if path:
            self._b2z_out_var.set(path)

    def _load_parts_from_zip(self):
        path = filedialog.askopenfilename(
            title=t("dlg.zip"),
            filetypes=[("AutoTuner backup", "*.zip *.bak"), ("All files", "*.*")])
        if not path:
            return
        try:
            info = read_archive_info(path)
        except Exception as exc:
            self.banner.show("error", str(exc))
            return
        remember_layout(info['parts'], os.path.basename(path),
                        how_to=info.get('how_to', ''))
        self._clear_part_rows()
        for part in info['parts']:
            self._add_part_row(name=part['name'], size=part['size'])
        for key, var in self._meta_vars.items():
            if info['meta'].get(key):
                var.set(info['meta'][key])
        self._refresh_parts()
        self.banner.show("ok", t("backup.parts.restored", n=info['count'],
                                 source=os.path.basename(path)))
        self.app.set_status(t("word.ready"), "ok")

    def _load_preset(self, name):
        self._clear_part_rows()
        for part_name, size in PRESETS[name]:
            self._add_part_row(name=part_name, size=size)
        for key, value in PRESET_META.get(name, {}).items():
            if key in self._meta_vars:
                self._meta_vars[key].set(value)
        self._refresh_parts()
        self.app.set_status(t("backup.parts.preset_applied", name=name), "ok")

    def _run_bin_to_zip(self):
        bin_path = self._b2z_bin_var.get().strip()
        out_path = self._b2z_out_var.get().strip()

        if not bin_path:
            self.banner.show("error", t("err.no_bin"))
            return
        if not out_path:
            self.banner.show("error", t("backup.b2z.step3"))
            return
        # An empty line is not a part, so it is neither packed nor complained
        # about. A half filled one is already marked on screen; the same words
        # are repeated here for whoever pressed the button without looking.
        parts_config = []
        for i, row in enumerate(self._part_rows, 1):
            if row.is_blank:
                continue
            part = row.get()
            if part is None:
                self.banner.show("error", t("backup.parts.bad_row", n=i))
                return
            parts_config.append(part)
        if not parts_config:
            self.banner.show("error", t("err.no_parts"))
            return

        # Everything the original archive said about the car, then whatever is
        # in the boxes on top of it. The five fields with no box - series,
        # type, usage, kW, hardware - survive this way instead of coming back
        # empty in the customer's archive.
        remembered = remembered_meta(os.path.getsize(bin_path))
        meta = {INI_KEYS[key]: value for key, value in remembered.items()
                if key in INI_KEYS and value}
        for key, var in self._meta_vars.items():
            typed = var.get().strip()
            if typed:
                meta[INI_KEYS[key]] = typed
        meta.setdefault('hardware', 'Autotuner')

        self.app.set_status(t("word.running"), "busy")
        self.banner.show("busy", t("word.running"))
        self._b2z_step4.set_state("now")
        self._b2z_step4.set_running(True)
        self.app.update_idletasks()

        # The how-to page belongs to the archive this .bin came out of, so it is
        # looked up by the size that identifies that archive.
        ok, msg = bin_to_zip(
            bin_path, out_path, parts_config, meta,
            how_to_html=remembered_how_to(sum(p['size'] for p in parts_config)))
        if ok:
            self.banner.show("ok", msg, action_text=t("word.open_folder"),
                             action=lambda: ui.reveal_in_file_manager(out_path))
            self.app.set_status(t("word.done"), "ok")
            self._b2z_step4.set_running(False)
            self._b2z_step4.set_state("done")
            self._b2z_step4.set_note(os.path.basename(out_path))
        else:
            self.banner.show("error", msg)
            self._b2z_step4.set_running(False)
            self._b2z_step4.set_state("err")
            self.app.set_status(t("word.failed"), "error")


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    """The Backup area of the one app. Kept so the Start menu entry still works."""
    import dme_app
    return dme_app.main("backup")


if __name__ == "__main__":
    sys.exit(main())
