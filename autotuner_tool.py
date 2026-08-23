"""
AutoTuner Backup Tool — DME Innovation
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
PRESETS["MG1CP002"] = [("iflash0.bin", 4194304), ("iflash1.bin", 4194304),
                       ("dflash0.bin", 262144), ("dflash1.bin", 262144)]
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


def remember_layout(parts: list[dict], label: str = "", store: dict = None) -> dict:
    """Store one layout under its total size. Returns the updated store."""
    parts = [{"name": p["name"], "size": int(p["size"])} for p in parts if p.get("name")]
    if not parts:
        return store if store is not None else load_layouts()
    layouts = load_layouts() if store is None else store
    total = sum(p["size"] for p in parts)
    layouts[str(total)] = {"label": label, "parts": parts}
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
               ini_meta: dict = None) -> tuple[bool, str]:
    """
    Split a .bin file into named parts per parts_config and pack into an AutoTuner .zip.
    parts_config = [{'name': str, 'size': int}, ...]  — sizes must sum to bin file size.
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
            zf.writestr("how-to-use-backup.html", HOW_TO_USE_HTML)

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
    return {'parts': parts, 'extras': extras, 'meta': meta,
            'total': offset, 'count': len(parts)}


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────

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

_TkBase = tk.Tk if TK_AVAILABLE else object


class PartRow:
    """One row of the split table, laid out in the shared grid container."""

    COLOURS = ("#FFAA00", "#FF8A3D", "#63A9FF", "#3DDC84", "#C084FC", "#F472B6")

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

    def get(self) -> dict | None:
        name = self.name_var.get().strip()
        if not name:
            return None
        try:
            size = int(self.size_var.get().replace(',', '').replace(' ', '').replace('.', ''))
        except ValueError:
            return None
        return {'name': name, 'size': size}

    def destroy(self):
        for w in (self.index_lbl, self.swatch, self.name_entry, self.size_entry,
                  self.human_lbl, self.del_btn):
            w.destroy()


class AutoTunerTool(_TkBase):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} — {brand.VENDOR}")
        self.configure(bg=ui.BG)
        ui.init(self)
        self.minsize(ui.px(900), ui.px(680))
        brand.apply_window_icon(self)

        self._archive_info: dict | None = None
        self._part_rows: list[PartRow] = []
        self._last_output: str | None = None

        self._build()
        self._bind_shortcuts()

    # ── Shell ────────────────────────────────────────────────────────────────

    NAV = [
        {"key": "z2b", "label": "ZIP → BIN", "title": "ZIP → BIN",
         "subtitle": "Concentrate every memory part of an AutoTuner .zip/.bak backup "
                     "into one continuous .bin for your tuning software."},
        {"key": "b2z", "label": "BIN → ZIP", "title": "BIN → ZIP",
         "subtitle": "Split a modified .bin back into its memory parts and package them "
                     "as an AutoTuner-compatible .zip backup."},
    ]

    def _build(self):
        self.shell = ui.Shell(self, brand, APP_NAME, APP_VERSION, self.NAV,
                              self._show_page)
        self.shell.pack(fill=tk.BOTH, expand=True)
        self.tabs = self.shell          # the pages still say tabs.select(...)
        self.status = self.shell.status
        self._page_host = self.shell.host

        self.pages = {"z2b": self._build_zip_to_bin(), "b2z": self._build_bin_to_zip()}
        self.shell.select("z2b")

    def _show_page(self, key):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill=tk.BOTH, expand=True)

    def _bind_shortcuts(self):
        self.bind("<Control-o>", lambda _e: (self._browse_zip() if self._active() == "z2b"
                                             else self._browse_bin()))
        self.bind("<F5>", lambda _e: self._analyze_zip() if self._active() == "z2b" else None)
        self.bind("<Control-Return>", lambda _e: (self._run_zip_to_bin()
                                                  if self._active() == "z2b"
                                                  else self._run_bin_to_zip()))

    def _active(self) -> str:
        for key, page in self.pages.items():
            if page.winfo_ismapped():
                return key
        return "z2b"

    # ── Page 1: ZIP → BIN ────────────────────────────────────────────────────

    def _build_zip_to_bin(self):
        page = ui.Page(self._page_host)
        self._z2b_banner = page.banner

        src = page.card("Source backup")
        self._z2b_zip_var = tk.StringVar()
        self._z2b_path = ui.PathRow(src.body, "AutoTuner backup (.zip / .bak)",
                                    self._z2b_zip_var, self._browse_zip,
                                    hint="No file selected — Ctrl+O to browse")
        self._z2b_path.pack(fill=tk.X)
        self._z2b_zip_var.trace_add('write', lambda *_: self._on_zip_path_changed())

        self._z2b_preview_card = page.card("Archive contents", hint="—")
        self._z2b_log = ui.LogView(self._z2b_preview_card.body, height=13)
        self._z2b_log.pack(fill=tk.BOTH, expand=True)
        tools = tk.Frame(self._z2b_preview_card.body, bg=ui.CARD)
        tools.pack(fill=tk.X, pady=(10, 0))
        tk.Label(tools, text="Parts are listed in the exact order they are written "
                             "into the .bin file.",
                 bg=ui.CARD, fg=ui.TEXT_FAINT, font=ui.f("small")).pack(side=tk.LEFT)
        ui.button(tools, "Analyze  ⟳", self._analyze_zip, variant="secondary",
                  size="sm").pack(side=tk.RIGHT)
        self._z2b_log.set_text("Select a .zip or .bak backup to inspect its parts.", "dim")

        out = page.card("Output")
        self._z2b_out_var = tk.StringVar()
        self._z2b_out_path = ui.PathRow(out.body, "Combined binary (.bin)",
                                        self._z2b_out_var, self._browse_zip_output,
                                        browse_text="Save as…")
        self._z2b_out_path.pack(fill=tk.X)

        self._z2b_summary = tk.StringVar(value="Waiting for a backup file")
        self._action_bar(page, self._z2b_summary, "Concentrate to .bin  ⬇",
                         self._run_zip_to_bin)
        return page

    @staticmethod
    def _action_bar(page, summary_var, label, command):
        page.summary(summary_var)
        btn = ui.button(page.action_row, label, command, variant="primary", size="lg")
        btn.pack(side=tk.RIGHT)
        return btn

    def _on_zip_path_changed(self):
        path = self._z2b_zip_var.get().strip()
        if not path:
            self._z2b_path.set_hint("No file selected — Ctrl+O to browse")
        elif not os.path.exists(path):
            self._z2b_path.set_hint("File not found", "error")
        else:
            self._analyze_zip()

    def _browse_zip(self):
        path = filedialog.askopenfilename(
            title="Select AutoTuner backup",
            filetypes=[("AutoTuner backup", "*.zip *.bak"), ("All files", "*.*")])
        if path:
            self._z2b_zip_var.set(path)
            self._z2b_out_var.set(os.path.splitext(path)[0] + "_combined.bin")
            self._analyze_zip()

    def _browse_zip_output(self):
        path = filedialog.asksaveasfilename(
            title="Save combined .bin", defaultextension=".bin",
            filetypes=[("Binary file", "*.bin"), ("All files", "*.*")])
        if path:
            self._z2b_out_var.set(path)

    def _analyze_zip(self):
        zip_path = self._z2b_zip_var.get().strip()
        if not zip_path or not os.path.exists(zip_path):
            self._archive_info = None
            self._z2b_log.set_text("Select a .zip or .bak backup to inspect its parts.", "dim")
            self._z2b_preview_card.set_hint("—")
            self._z2b_path.set_hint("No file selected — Ctrl+O to browse")
            self._z2b_summary.set("Waiting for a backup file")
            return
        try:
            info = read_archive_info(zip_path)
        except zipfile.BadZipFile:
            self._archive_info = None
            self._z2b_log.set_text("Not a valid ZIP archive.", "error")
            self._z2b_preview_card.set_hint("invalid", "error")
            self._z2b_path.set_hint("Unreadable archive", "error")
            self.status.set("Invalid archive", "error")
            return
        except Exception as e:
            self._archive_info = None
            self._z2b_log.set_text(f"Error: {e}", "error")
            self.status.set("Error", "error")
            return

        self._archive_info = info
        self._z2b_log.clear()
        self._z2b_log.write(f"{'#':>2}  {'PART':<24}{'SIZE':>12}{'OFFSET':>14}", "dim")
        self._z2b_log.write("─" * 54, "dim")
        for i, part in enumerate(info['parts'], 1):
            self._z2b_log.write(
                f"{i:>2}  {part['name']:<24}{format_bytes(part['size']):>12}"
                f"{part['offset']:>14,}", "accent")
        for extra in info['extras']:
            self._z2b_log.write(
                f"    {extra['name']:<24}{format_bytes(extra['size']):>12}"
                f"{'metadata':>14}", "dim")
        self._z2b_log.write("─" * 54, "dim")
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

        self._z2b_preview_card.set_hint(
            f"{info['count']} part(s) · {format_bytes(info['total'])}", "ok")
        self._z2b_path.set_hint(
            f"{os.path.basename(zip_path)} · {info['count']} part(s) · "
            f"{format_bytes(info['total'])}", "ok")
        self._z2b_log.scroll_top()
        self._z2b_summary.set(f"{info['count']} part(s) · {info['total']:,} bytes ready "
                              f"to concentrate")
        self.status.set(f"Analyzed {os.path.basename(zip_path)}", "ok")

    def _run_zip_to_bin(self):
        zip_path = self._z2b_zip_var.get().strip()
        out_path = self._z2b_out_var.get().strip()
        if not zip_path:
            self._z2b_banner.show("error", "Select an AutoTuner .zip/.bak backup first.")
            return
        if not out_path:
            self._z2b_banner.show("error", "Choose where the combined .bin should be saved.")
            return

        self.status.set("Concentrating…", "busy")
        self._z2b_banner.show("busy", "Working…")
        self.update_idletasks()

        ok, msg, parts = zip_to_bin(zip_path, out_path)
        if ok:
            remember_layout(parts, os.path.basename(zip_path))
            self._z2b_banner.show("ok", f"{msg}\n{out_path}",
                                  action_text="Show in folder",
                                  action=lambda: ui.reveal_in_file_manager(out_path))
            self.status.set(f"Done · {os.path.basename(out_path)}", "ok")
            self._z2b_summary.set(f"{len(parts)} part(s) written · "
                                  f"{os.path.getsize(out_path):,} bytes")
        else:
            self._z2b_banner.show("error", msg)
            self.status.set("Failed", "error")

    # ── Page 2: BIN → ZIP ────────────────────────────────────────────────────

    def _build_bin_to_zip(self):
        page = ui.Page(self._page_host)
        self._b2z_banner = page.banner

        src = page.card("Source binary")
        self._b2z_bin_var = tk.StringVar()
        self._b2z_path = ui.PathRow(src.body, "Modified binary (.bin)", self._b2z_bin_var,
                                    self._browse_bin,
                                    hint="No file selected — Ctrl+O to browse")
        self._b2z_path.pack(fill=tk.X)
        self._b2z_bin_var.trace_add('write', lambda *_: self._on_bin_path_changed())

        split = page.card("Split configuration", hint="0 parts")
        self._split_card = split

        toolbar = tk.Frame(split.body, bg=ui.CARD)
        toolbar.pack(fill=tk.X, pady=(0, 12))
        ui.button(toolbar, "Load from ZIP template", self._load_parts_from_zip,
                  variant="secondary", size="sm").pack(side=tk.LEFT)
        for preset in PRESETS:
            ui.button(toolbar, preset, lambda p=preset: self._load_preset(p),
                      variant="secondary", size="sm").pack(side=tk.LEFT, padx=(8, 0))
        ui.button(toolbar, "+ Add part", self._add_part_row, variant="ghost",
                  size="sm", bg=ui.CARD).pack(side=tk.RIGHT)

        head = tk.Frame(split.body, bg=ui.CARD)
        head.pack(fill=tk.X)
        for col, (text, weight, anchor, width) in enumerate([
                ("#", 0, "e", 2), ("", 0, "w", 1), ("PART FILENAME", 3, "w", 0),
                ("SIZE (BYTES)", 2, "e", 0), ("", 0, "e", 9), ("", 0, "e", 3)]):
            lbl = tk.Label(head, text=text, bg=ui.CARD, fg=ui.TEXT_FAINT,
                           font=ui.f("micro"), anchor=anchor)
            lbl.grid(row=0, column=col, sticky="ew",
                     padx=(0, 6) if col == 0 else (10 if col in (3, 4) else 0, 0))
            if width:
                lbl.config(width=width)
            head.grid_columnconfigure(col, weight=weight)
        ui.hr(split.body, bg=ui.BORDER, pady=(4, 2))

        self._parts_table = tk.Frame(split.body, bg=ui.CARD)
        self._parts_table.pack(fill=tk.X)
        for col, weight in ((0, 0), (1, 0), (2, 3), (3, 2), (4, 0), (5, 0)):
            self._parts_table.grid_columnconfigure(col, weight=weight)
        self._parts_empty = tk.Label(
            self._parts_table,
            text="No parts configured — load a template, pick a preset, or add rows.",
            bg=ui.CARD, fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w", pady=14)

        self._split_canvas = tk.Canvas(split.body, bg=ui.CARD, height=10,
                                       highlightthickness=0, bd=0)
        self._split_canvas.pack(fill=tk.X, pady=(14, 8))
        self._split_canvas.bind("<Configure>", lambda _e: self._draw_split_bar())

        totals = tk.Frame(split.body, bg=ui.CARD)
        totals.pack(fill=tk.X)
        self._b2z_total_var = tk.StringVar(value="Parts 0 B  ·  File 0 B")
        tk.Label(totals, textvariable=self._b2z_total_var, bg=ui.CARD, fg=ui.TEXT_DIM,
                 font=ui.f("small")).pack(side=tk.LEFT)
        self._b2z_match = tk.Label(totals, text="", bg=ui.CARD, font=ui.f("small"))
        self._b2z_match.pack(side=tk.RIGHT)

        meta_card = page.card("Vehicle / ECU metadata",
                              hint="optional — written to contents.ini")
        grid = tk.Frame(meta_card.body, bg=ui.CARD)
        grid.pack(fill=tk.X)
        self._meta_vars = {}
        for i, (key, label, placeholder) in enumerate(META_FIELDS):
            var = tk.StringVar()
            self._meta_vars[key] = var
            cell = ui.LabeledEntry(grid, f"{label} ({placeholder})", var)
            cell.grid(row=i // 3, column=i % 3, sticky="ew",
                      padx=(0 if i % 3 == 0 else 12, 0), pady=(0, 10))
        for col in range(3):
            grid.grid_columnconfigure(col, weight=1, uniform="meta")

        out = page.card("Output")
        self._b2z_out_var = tk.StringVar()
        self._b2z_out_path = ui.PathRow(out.body, "AutoTuner backup (.zip)",
                                        self._b2z_out_var, self._browse_zip_out,
                                        browse_text="Save as…")
        self._b2z_out_path.pack(fill=tk.X)

        self._b2z_summary = tk.StringVar(value="Waiting for a .bin file")
        self._action_bar(page, self._b2z_summary, "Split & package to .zip  ⬆",
                         self._run_bin_to_zip)
        self._refresh_parts()
        return page

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
                self._parts_empty.config(
                    text="No parts configured — load a template, pick a preset, "
                         "or add rows.")
            self._parts_empty.grid(row=0, column=0, columnspan=6, sticky="ew")
        self._split_card.set_hint(f"{len(self._part_rows)} part(s)")
        self._update_totals()

    def _bin_size(self) -> int:
        path = self._b2z_bin_var.get().strip()
        return os.path.getsize(path) if path and os.path.exists(path) else 0

    def _update_totals(self):
        total = sum(row.size for row in self._part_rows)
        file_size = self._bin_size()
        self._b2z_total_var.set(
            f"Parts {total:,} B ({format_bytes(total)})  ·  "
            f"File {file_size:,} B ({format_bytes(file_size)})")
        if file_size == 0:
            self._b2z_match.config(text="")
        elif total == file_size:
            self._b2z_match.config(text="✓  sizes match", fg=ui.OK)
            self._b2z_summary.set(f"{len(self._part_rows)} part(s) · {total:,} bytes · ready")
        elif total > file_size:
            self._b2z_match.config(text=f"✕  overflow by {total - file_size:,} B", fg=ui.ERR)
            self._b2z_summary.set(f"Parts exceed the file by {total - file_size:,} bytes")
        else:
            self._b2z_match.config(text=f"✕  missing {file_size - total:,} B", fg=ui.ERR)
            self._b2z_summary.set(f"{file_size - total:,} bytes still unassigned")
        self._draw_split_bar()

    def _draw_split_bar(self):
        canvas = self._split_canvas
        canvas.delete("all")
        width = canvas.winfo_width()
        if width <= 1:
            return
        total = sum(row.size for row in self._part_rows)
        file_size = self._bin_size()
        scale_total = max(total, file_size, 1)
        canvas.create_rectangle(0, 0, width, 10, fill=ui.FIELD, outline="")
        x = 0.0
        for row in self._part_rows:
            if row.size <= 0:
                continue
            w = width * row.size / scale_total
            canvas.create_rectangle(x, 0, x + w, 10, fill=row.colour, outline="")
            x += w
        if file_size and total > file_size:
            over_x = width * file_size / scale_total
            canvas.create_rectangle(over_x, 0, width, 10, outline=ui.ERR, width=1)

    def _on_bin_path_changed(self):
        path = self._b2z_bin_var.get().strip()
        if not path:
            self._b2z_path.set_hint("No file selected — Ctrl+O to browse")
        elif not os.path.exists(path):
            self._b2z_path.set_hint("File not found", "error")
        else:
            size = os.path.getsize(path)
            self._b2z_path.set_hint(f"{os.path.basename(path)} · {size:,} bytes "
                                    f"({format_bytes(size)})", "ok")
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
            origin = f" from {label}" if label else ""
            self._b2z_banner.show("ok", f"Layout restored{origin} — {len(parts)} part(s), "
                                        f"sizes match.")
            self.status.set(f"Layout restored · {len(parts)} part(s)", "ok")
            return
        preset = preset_for_size(size)
        if preset:
            self._load_preset(preset)
            self._b2z_banner.show("info", f"File size matches the {preset} layout — "
                                          f"preset applied.")
            return
        self._empty_hint(size)

    def _empty_hint(self, size: int):
        self._parts_empty.config(
            text=f"{size:,} bytes match no preset — open the original AutoTuner backup "
                 f"with “Load from ZIP template”, then this layout is remembered.")

    def _browse_bin(self):
        path = filedialog.askopenfilename(
            title="Select .bin file",
            filetypes=[("Binary file", "*.bin"), ("All files", "*.*")])
        if not path:
            return
        self._b2z_bin_var.set(path)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self._b2z_out_var.set(os.path.join(os.path.dirname(path), f"{stamp}-backup.zip"))

    def _browse_zip_out(self):
        path = filedialog.asksaveasfilename(
            title="Save AutoTuner .zip backup", defaultextension=".zip",
            filetypes=[("AutoTuner backup", "*.zip"), ("All files", "*.*")])
        if path:
            self._b2z_out_var.set(path)

    def _load_parts_from_zip(self):
        path = filedialog.askopenfilename(
            title="Select an AutoTuner backup as template",
            filetypes=[("AutoTuner backup", "*.zip *.bak"), ("All files", "*.*")])
        if not path:
            return
        try:
            info = read_archive_info(path)
        except Exception as e:
            self._b2z_banner.show("error", f"Could not read the ZIP template: {e}")
            return
        remember_layout(info['parts'], os.path.basename(path))
        self._clear_part_rows()
        for part in info['parts']:
            self._add_part_row(name=part['name'], size=part['size'])
        for key, var in self._meta_vars.items():
            if info['meta'].get(key):
                var.set(info['meta'][key])
        self._refresh_parts()
        self._b2z_banner.show("ok", f"Loaded {info['count']} part(s) and metadata from "
                                    f"{os.path.basename(path)}")
        self.status.set(f"Template loaded · {os.path.basename(path)}", "ok")

    def _load_preset(self, name):
        self._clear_part_rows()
        for part_name, size in PRESETS[name]:
            self._add_part_row(name=part_name, size=size)
        for key, value in PRESET_META.get(name, {}).items():
            if key in self._meta_vars:
                self._meta_vars[key].set(value)
        self._refresh_parts()
        total = sum(s for _, s in PRESETS[name])
        self.status.set(f"{name} preset · {len(PRESETS[name])} parts · {total:,} bytes", "ok")

    def _run_bin_to_zip(self):
        bin_path = self._b2z_bin_var.get().strip()
        out_path = self._b2z_out_var.get().strip()

        if not bin_path:
            self._b2z_banner.show("error", "Select a source .bin file first.")
            return
        if not out_path:
            self._b2z_banner.show("error", "Choose where the .zip backup should be saved.")
            return
        if not self._part_rows:
            self._b2z_banner.show("error", "Add at least one part — use a preset or a ZIP template.")
            return

        parts_config = []
        for i, row in enumerate(self._part_rows, 1):
            part = row.get()
            if part is None:
                self._b2z_banner.show("error", f"Part {i} has a missing or invalid name/size.")
                return
            parts_config.append(part)

        meta = {
            'make': self._meta_vars['VehicleProducer'].get(),
            'model': self._meta_vars['VehicleBuild'].get(),
            'variant': self._meta_vars['VehicleModel'].get(),
            'year': self._meta_vars['VehicleModelYear'].get(),
            'ecu_model': self._meta_vars['EcuBuild'].get(),
            'ecu_maker': self._meta_vars['EcuProducer'].get(),
            'fuel': self._meta_vars['EngineType'].get(),
            'ps': self._meta_vars['OutputPS'].get(),
            'vin': self._meta_vars['VehicleVIN'].get(),
            'hardware': 'Autotuner',
        }

        self.status.set("Packaging…", "busy")
        self._b2z_banner.show("busy", "Working…")
        self.update_idletasks()

        ok, msg = bin_to_zip(bin_path, out_path, parts_config, meta)
        if ok:
            self._b2z_banner.show("ok", f"{msg}\n{out_path}",
                                  action_text="Show in folder",
                                  action=lambda: ui.reveal_in_file_manager(out_path))
            self.status.set(f"Done · {os.path.basename(out_path)}", "ok")
        else:
            self._b2z_banner.show("error", msg)
            self.status.set("Failed", "error")


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    if not TK_AVAILABLE:
        print(f"{APP_NAME} v{APP_VERSION} — {brand.VENDOR}", file=sys.stderr)
        print("tkinter is not available in this Python installation.", file=sys.stderr)
        print("Windows/macOS: reinstall Python and tick 'tcl/tk and IDLE'.", file=sys.stderr)
        print("Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
        return 1
    ui.enable_dpi_awareness()
    app = AutoTunerTool()
    app.geometry(f"{ui.px(980)}x{ui.px(780)}")
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
