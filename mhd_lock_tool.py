"""
MHD Lock Tool · DME Innovation
==============================

Automates the tune locking workflow described in the MHD+ Tuning Guide
("Locking Tune Files with MHD+ Features"): it stages a clean working directory
for the official MHD Map Encryption tool (TuningMapBuilder / XDF_Tools),
validates every input before the run, drives the tool, reads its console
output and files the resulting *.mhd away per customer.

The locking itself is done by the tuner's own licensed copy of the MHD tool,
nothing here reimplements, patches or bypasses any part of it. The tool path is
configured in the Settings tab; the executable is never bundled.

© DME Innovation
"""

import csv
import datetime
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import dme_brand as brand

try:
    import tkinter as tk
    from tkinter import filedialog

    import dme_ui as ui
    TK_AVAILABLE = True
except ImportError:  # headless box / python3-tk not installed
    tk = filedialog = ui = None
    TK_AVAILABLE = False

APP_NAME = "MHD Lock Tool"
APP_VERSION = brand.VERSION
APP_TAGLINE = "Automated MHD+ tune locking for the MHD Map Encryption tool"

# Both pages say something different once the builder is left out of it.
LOCK_SUBTITLE = ("Pick the customer's tuned file. Stock ROM, XDF and tool key are "
                 "found automatically, and the VIN comes from the customer's mapswitch "
                 "read. Check the VIN, then press Lock.")
PREPARE_SUBTITLE = ("Pick the customer's tuned file. Stock ROM, XDF and tool key are "
                    "found automatically, and the VIN comes from the customer's mapswitch "
                    "read. You get the finished working folder; the .mhd is yours to make.")
BATCH_SUBTITLE = ("Lock a whole queue in one go. Stock ROM and XDF are resolved per "
                  "file, and every job runs in its own clean folder.")
BATCH_PREPARE_SUBTITLE = ("Build a working folder for every file in the queue. Stock ROM "
                          "and XDF are resolved per file, and nothing is started.")


# ─────────────────────────────────────────────────────────────────────────────
# What the MHD map builder expects in its working directory
# ─────────────────────────────────────────────────────────────────────────────
STOCK_SUFFIX = "_original.bin"
VIN_SUFFIX = "_vin.txt"
TOOLKEY_EXT = ".toolkey"
XDF_EXT = ".xdf"
OUTPUT_EXT = ".mhd"

# Optional side-car files the builder reads if they are present
OPTIONAL_SIDECARS = (
    "Tables2Add.txt",
    "MHD tool tables to ignore.txt",
    "MHD map conv stock tables to include.txt",
)

# Console output of the builder, classified so the log stays readable
SUCCESS_MARKERS = ("Map correctly written",)
ERROR_MARKERS = (
    "Error -", "Error:", "Error name too short",
    "******** CRC error", "******** Map read error",
    "Missing your .toolkey file", "Missing YOURCLIENTVIN", "Missing xdf for",
    "Missing table at", "Missing table ", "Invalid key",
    "Modification not in xdf", "Table not in xdf",
    "NO modifications found", "Could not determine the DME model",
    "Unsupported DME", "Prozess not supported", "Failed to serialize",
    "Unhandled area", "Unhandled exception",
)
# The builder ends on Console.ReadKey(). With stdin redirected .NET raises
# InvalidOperationException *after* the map has already been written, noise
# not a failure.
BENIGN_MARKERS = (
    "Cannot read keys",
    "Press a key",
    "System.Console.ReadKey",
)
WARN_MARKERS = (
    "WARNING", "bytes not referenced in the XDFs", "MUST FIX axis",
    "Skipped axis", "Missing tables:", "Duplicate:", "Doublon ",
)
INFO_MARKERS = (
    "opened BIN:", "Total bytes changed:", "Restrict to VIN :", "Found ",
    "Removing common", "Renaming ", "Total time ", "copy ",
)

VIN_RE = re.compile(r"^[A-HJ-NPR-Z0-9]{17}$")
ROM_ID_RE = re.compile(rb"(?<![0-9A-Za-z])[0-9A-F]{14}(?![0-9A-Za-z])")
SGBM_RE = re.compile(rb"(?:swfl|btld|swfk)[_-][0-9a-fA-F]{8}")
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]+')
# BMW program id as it appears in file names: 14 hex digits, e.g. 00005C6414C808
FILE_ID_RE = re.compile(r"(?<![0-9A-Za-z])([0-9A-Fa-f]{14})(?![0-9A-Za-z])")
STOCK_PATTERNS = ("_original.bin", "_orig.bin", "_stock.bin", ".org", "_mapswitch.bin")
# A whole MHD XDF library is handed over as one folder: platform / DME / software
# version / … Six levels cover that comfortably.
LIBRARY_DEPTH = 6
# Confirming a program id means scanning the 8 MB image, so a library with
# thousands of XDFs must never be checked file by file. Once the ROM number is
# known, XDFs are matched by name and no scan happens at all; this budget only
# caps the fallback where nothing is known yet.
CONTENT_SCAN_BUDGET = 250
# The MHD app names a customer's backup read <VIN>_<program id>_mapswitch.bin,
# the file the customer sends already carries VIN and program id. The trailer
# tolerates download copies ("…_mapswitch (1).bin", "…_mapswitch - Kopie.bin").
CUSTOMER_READ_RE = re.compile(
    r"^([A-HJ-NPR-Z0-9]{17})_([0-9A-F]{14})_mapswitch(?:[\s_\-(.].*)?$",
    re.IGNORECASE)


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────
def human_size(n: int) -> str:
    value = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024:
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def safe_name(text: str, fallback: str = "unnamed", keep_spaces: bool = False) -> str:
    """Strip characters Windows rejects. Spaces are kept for staged file names so
    the .mhd ends up with the same name a hand-built folder would produce."""
    cleaned = _UNSAFE_NAME.sub("", (text or "").strip()).strip(" .")
    if not keep_spaces:
        cleaned = re.sub(r"\s+", "_", cleaned)
    return cleaned or fallback


def _num(value, default: int = 0) -> int:
    """Parse XDF numbers, which come as 0x-hex, plain decimal or empty."""
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text, 16) if text.lower().startswith("0x") else int(text, 10)
    except ValueError:
        try:
            return int(text, 16)
        except ValueError:
            return default


def normalise_vin(vin: str) -> str:
    return re.sub(r"[\s\-]", "", (vin or "")).upper()


def validate_vin(vin: str) -> tuple[bool, str, str]:
    """Return (ok, normalised, message). The builder demands exactly 17 chars."""
    value = normalise_vin(vin)
    if not value:
        return False, value, "VIN is required. The builder needs a <VIN>_vin.txt file."
    if len(value) != 17:
        return False, value, f"VIN length is {len(value)}, must be 17 characters."
    if not VIN_RE.match(value):
        return False, value, "VIN contains invalid characters (I, O and Q are not allowed)."
    return True, value, "VIN looks valid."


def read_bytes(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read()


# ─────────────────────────────────────────────────────────────────────────────
# Binary comparison
# ─────────────────────────────────────────────────────────────────────────────
def diff_regions(stock: bytes, tuned: bytes, merge_gap: int = 16,
                 block: int = 4096) -> list[tuple[int, int]]:
    """Continuous (offset, length) runs where the two images differ."""
    shared = min(len(stock), len(tuned))
    raw: list[list[int]] = []
    start = None
    for base in range(0, shared, block):
        chunk_a = stock[base:base + block]
        chunk_b = tuned[base:base + block]
        if chunk_a == chunk_b:
            if start is not None:
                raw.append([start, base])
                start = None
            continue
        for i, (byte_a, byte_b) in enumerate(zip(chunk_a, chunk_b)):
            if byte_a != byte_b:
                if start is None:
                    start = base + i
            elif start is not None:
                raw.append([start, base + i])
                start = None
    if start is not None:
        raw.append([start, shared])
    if len(tuned) > shared:
        raw.append([shared, len(tuned)])

    merged: list[list[int]] = []
    for begin, end in raw:
        if merged and begin - merged[-1][1] <= merge_gap:
            merged[-1][1] = end
        else:
            merged.append([begin, end])
    return [(begin, end - begin) for begin, end in merged]


def changed_byte_count(stock: bytes, tuned: bytes) -> int:
    shared = min(len(stock), len(tuned))
    count = sum(1 for a, b in zip(stock[:shared], tuned[:shared]) if a != b)
    return count + abs(len(tuned) - len(stock))


def detect_rom_ids(data: bytes, limit: int = 12) -> list[str]:
    """Heuristic: the 14-digit program id and SGBM tokens BMW ROMs carry."""
    found: list[str] = []
    for match in ROM_ID_RE.findall(data):
        text = match.decode("ascii")
        if text != "0" * 14 and text not in found:
            found.append(text)
        if len(found) >= limit:
            break
    for match in SGBM_RE.findall(data):
        text = match.decode("ascii").lower()
        if text not in found:
            found.append(text)
        if len(found) >= limit * 2:
            break
    return found


def ids_in_name(path: str) -> list[str]:
    """Program ids embedded in a file name, upper case."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return [match.group(1).upper() for match in FILE_ID_RE.finditer(stem)]


def parse_customer_read(path: str) -> tuple[str, str]:
    """
    (VIN, program id) from a customer's MHD backup read, ("", "") otherwise.

    Customers send the read exactly as the MHD app saves it:
    <VIN>_<program id>_mapswitch.bin. That name is the metadata, the VIN does
    not have to be typed and the file does not have to be renamed by hand.
    """
    stem = os.path.splitext(os.path.basename(path))[0]
    match = CUSTOMER_READ_RE.match(stem)
    if not match:
        return "", ""
    return match.group(1).upper(), match.group(2).upper()


def id_in_image(data: bytes, identifier: str) -> bool:
    """
    True when the program id is present in the ROM.

    BMW stores it as seven packed bytes (00005C6414C808 -> 00 00 5C 64 14 C8 08),
    not as text, so a plain string search finds nothing.
    """
    try:
        packed = bytes.fromhex(identifier)
    except ValueError:
        return False
    if len(packed) != 7:
        return False
    return packed in data or identifier.encode() in data or identifier.lower().encode() in data


# ─────────────────────────────────────────────────────────────────────────────
# Companion lookup - the app finds stock ROM, XDF and key by itself
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Resolution:
    """What the app worked out on its own from a single tuned file."""
    tuned: str = ""
    stock: str = ""
    xdf: str = ""
    toolkey: str = ""
    vin: str = ""
    rom_id: str = ""
    sources: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def source(self, key: str) -> str:
        return self.sources.get(key, "")

    @property
    def complete(self) -> bool:
        return bool(self.stock and self.xdf and self.toolkey)


def _scan_dirs(tuned_path: str, library_dir: str = "", max_depth: int = LIBRARY_DEPTH) -> list[str]:
    """The tuned file's own folder first, then the library, breadth limited."""
    folders: list[str] = []
    own = os.path.dirname(os.path.abspath(tuned_path))
    if os.path.isdir(own):
        folders.append(own)
    if library_dir and os.path.isdir(library_dir):
        root = os.path.abspath(library_dir)
        base_depth = root.rstrip(os.sep).count(os.sep)
        for current, subdirs, _files in os.walk(root):
            if current.rstrip(os.sep).count(os.sep) - base_depth >= max_depth:
                subdirs[:] = []
            subdirs[:] = [d for d in subdirs if not d.startswith(".")]
            if current not in folders:
                folders.append(current)
    return folders


def _files_in(folders, predicate) -> list[str]:
    found = []
    for folder in folders:
        try:
            entries = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in entries:
            path = os.path.join(folder, name)
            if os.path.isfile(path) and predicate(name):
                found.append(path)
    return found


def _is_customer_read(name: str) -> bool:
    return name.lower().endswith(".bin") and parse_customer_read(name)[1] != ""


def _is_stock_name(name: str) -> bool:
    lower = name.lower()
    if any(lower.endswith(pattern) for pattern in STOCK_PATTERNS):
        return True
    # download copies of a read ("… (1).bin", "… - Kopie.bin") are originals too
    return _is_customer_read(name)


def _is_bare_customer_read(path: str) -> bool:
    """Exactly <VIN>_<id>_mapswitch.bin - not a tune named after one."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return bool(parse_customer_read(path)[1]) and stem.lower().endswith("_mapswitch")


def _newest(paths: list[str]) -> str:
    """Several files for the same ROM: the most recent one is the current XDF."""
    try:
        return max(paths, key=os.path.getmtime)
    except OSError:
        return paths[0]


class _IdLookup:
    """
    'Is this program id really in the image?' asked once per id, not per file.

    Each answer costs a scan of an 8 MB image, and a full MHD XDF library holds
    thousands of candidates. Caching keeps a re-check cheap; the budget keeps the
    window responsive when nothing matches at all.
    """

    def __init__(self, data: bytes, budget: int = CONTENT_SCAN_BUDGET):
        self.data = data
        self.budget = budget
        self.exhausted = False
        self._known: dict[str, bool] = {}

    def has(self, identifier: str) -> bool:
        cached = self._known.get(identifier)
        if cached is not None:
            return cached
        if self.budget <= 0:
            self.exhausted = True
            return False
        self.budget -= 1
        answer = id_in_image(self.data, identifier)
        self._known[identifier] = answer
        return answer

    def first_match(self, paths) -> tuple[str, str]:
        """(path, id) of the first candidate whose name id occurs in the image."""
        for path in paths:
            for identifier in ids_in_name(path):
                if self.has(identifier):
                    return path, identifier
        return "", ""


def _read_of_another_car(path: str, lookup: "_IdLookup") -> bool:
    """A customer read whose program id is absent from this image is not this job's."""
    read_id = parse_customer_read(path)[1]
    return bool(read_id) and not lookup.has(read_id)


def resolve_inputs(tuned_path: str, library_dir: str = "", toolkey: str = "",
                   max_depth: int = LIBRARY_DEPTH) -> Resolution:
    """
    Work out stock ROM, XDF, tool key and VIN from the tuned file alone.

    Candidates are not guessed: a companion whose file name carries a program id
    is only accepted when that id is really present inside the tuned image. Only
    if nothing matches by id does the lookup fall back to "the single obvious
    file in the same folder".
    """
    result = Resolution(tuned=tuned_path)
    if not tuned_path or not os.path.isfile(tuned_path):
        result.notes.append("Select a tuned .bin first.")
        return result

    data = read_bytes(tuned_path)
    own_folder = os.path.dirname(os.path.abspath(tuned_path))
    folders = _scan_dirs(tuned_path, library_dir, max_depth)

    lookup = _IdLookup(data)

    # ── stock ROM ───────────────────────────────────────────────────────────
    stock_candidates = [p for p in _files_in(folders, _is_stock_name)
                        if os.path.abspath(p) != os.path.abspath(tuned_path)]
    # A file somebody deliberately named *_original.bin outranks a raw customer
    # read. Both can match the same ROM, but the curated one was picked as the
    # diff base on purpose - and folders from the old workflow hold both. The
    # sort is stable, so the own folder still comes before the library.
    stock_candidates.sort(key=lambda p: _is_customer_read(os.path.basename(p)))
    stock, rom_id = lookup.first_match(stock_candidates)
    if stock:
        result.sources["stock"] = "matched by ROM id"
    else:
        same_size = [p for p in stock_candidates
                     if os.path.dirname(p) == own_folder
                     and os.path.getsize(p) == len(data)
                     and not _read_of_another_car(p, lookup)]
        if len(same_size) == 1:
            stock = same_size[0]
            result.sources["stock"] = "only stock ROM in the folder"
        elif len(same_size) > 1:
            result.notes.append(f"{len(same_size)} possible stock ROMs in the folder - "
                                f"pick one under Details.")
    if stock:
        result.stock = stock
        if not rom_id:
            ids = ids_in_name(stock)
            rom_id = ids[0] if ids else ""

    # ── XDF ─────────────────────────────────────────────────────────────────
    # With the ROM number already established the whole MHD XDF library is
    # matched by name, no further pass over the image, however big the library.
    xdf_candidates = _files_in(folders, lambda n: n.lower().endswith(XDF_EXT))
    xdf = ""
    if rom_id:
        named = [p for p in xdf_candidates if rom_id in ids_in_name(p)]
        if named:
            xdf = _newest(named)
            result.sources["xdf"] = "matched by ROM id"
            if len(named) > 1:
                result.notes.append(f"{len(named)} XDFs for ROM {rom_id} in the library - "
                                    f"using the newest ({os.path.basename(xdf)}).")
    if not xdf:
        xdf, xdf_id = lookup.first_match(xdf_candidates)
        if xdf:
            result.sources["xdf"] = "matched by ROM id"
            rom_id = rom_id or xdf_id
    if not xdf:
        local = [p for p in xdf_candidates if os.path.dirname(p) == own_folder]
        if len(local) == 1:
            xdf = local[0]
            result.sources["xdf"] = "only XDF in the folder"
        elif len(local) > 1:
            result.notes.append(f"{len(local)} XDFs in the folder - pick one under Details.")
    result.xdf = xdf or ""
    result.rom_id = rom_id

    if lookup.exhausted and not (result.stock and result.xdf):
        result.notes.append(f"Stopped checking after {CONTENT_SCAN_BUDGET} files - the "
                            f"library is large and the ROM number is still unknown. Point "
                            f"the library at the XDF folder itself, or pick the files "
                            f"under Details.")

    # ── tool key ────────────────────────────────────────────────────────────
    if toolkey and os.path.isfile(toolkey):
        result.toolkey = toolkey
        result.sources["toolkey"] = "from settings"
    else:
        keys = _files_in(folders, lambda n: n.lower().endswith(TOOLKEY_EXT))
        if len(keys) == 1:
            result.toolkey = keys[0]
            result.sources["toolkey"] = "found next to the files"
        elif len(keys) > 1:
            local = [p for p in keys if os.path.dirname(p) == own_folder]
            if len(local) == 1:
                result.toolkey = local[0]
                result.sources["toolkey"] = "found next to the files"

    # ── VIN ─────────────────────────────────────────────────────────────────
    # A VIN is only ever taken from a read that belongs to THIS job: it has to
    # sit next to the tuned file and carry this ROM's program id. A program id
    # names a software version, not a car, and an archived read from another
    # customer on the same version would otherwise lock the .mhd to their car.
    vins = set()
    for path in _files_in([own_folder], _is_customer_read):
        read_vin, read_id = parse_customer_read(path)
        if read_vin and (read_id == rom_id or lookup.has(read_id)):
            vins.add(read_vin)
    if len(vins) == 1:
        result.vin = vins.pop()
        result.sources["vin"] = "from the customer's read"
    elif len(vins) > 1:
        result.notes.append(f"{len(vins)} customer reads with different VINs in the "
                            f"folder - type the right VIN, it cannot be guessed.")
    # A <VIN>_vin.txt is normally left over from an earlier run of the same job.
    # If it names a different car, somebody put it there on purpose - say so
    # instead of quietly preferring one of the two.
    for path in _files_in([own_folder], lambda n: n.lower().endswith(VIN_SUFFIX)):
        candidate = os.path.basename(path)[: -len(VIN_SUFFIX)]
        ok, vin, _ = validate_vin(candidate)
        if not ok:
            continue
        if not result.vin:
            result.vin = vin
            result.sources["vin"] = "from the folder"
        elif vin != result.vin:
            result.notes.append(f"{os.path.basename(path)} in the folder names a different "
                                f"car than the customer's read ({result.vin}) - check which "
                                f"VIN is right.")
        break

    return result


# ─────────────────────────────────────────────────────────────────────────────
# XDF definition
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class XdfRange:
    start: int
    end: int          # exclusive
    title: str


class XdfDefinition:
    """
    Minimal TunerPro XDF reader, enough to know which byte ranges the
    definition actually describes.

    The MHD builder refuses a file whose modifications are not covered by the
    XDF ("Modification not in xdf at 0x…"), so knowing the covered ranges up
    front turns a failed run into an instant, precise warning.
    """

    CONTAINERS = ("XDFTABLE", "XDFCONSTANT", "XDFFLAG", "XDFPATCH", "XDFFUNCTION")

    def __init__(self, path, title, rom_size, ranges, base_offset, subtract):
        self.path = path
        self.title = title
        self.rom_size = rom_size
        self.raw_ranges: list[XdfRange] = ranges
        self.base_offset = base_offset
        self.subtract = subtract
        self._resolved: dict[int, list[XdfRange]] = {}

    # ── parsing ─────────────────────────────────────────────────────────────
    @classmethod
    def load(cls, path: str) -> "XdfDefinition":
        root = ET.parse(path).getroot()
        header = root.find("XDFHEADER")
        title = os.path.basename(path)
        rom_size = 0
        base_offset = 0
        subtract = False
        if header is not None:
            title = (header.findtext("deftitle") or header.findtext("title")
                     or title).strip() or title
            base = header.find("BASEOFFSET")
            if base is not None:
                base_offset = _num(base.get("offset"), 0)
                subtract = str(base.get("subtract", "0")).strip() not in ("0", "", "false")
            region = header.find("REGION")
            if region is not None:
                rom_size = _num(region.get("size"), 0)

        ranges: list[XdfRange] = []
        for node in root:
            tag = node.tag.upper()
            if tag not in cls.CONTAINERS:
                continue
            name = (node.findtext("title") or node.get("name") or tag).strip()
            for embedded in node.iter("EMBEDDEDDATA"):
                span = cls._span(embedded)
                if span <= 0:
                    continue
                address = _num(embedded.get("mmedaddress"), -1)
                if address < 0:
                    continue
                ranges.append(XdfRange(address, address + span, name))
            for patch in node.iter("XDFPATCHENTRY"):
                address = _num(patch.get("address"), -1)
                if address < 0:
                    continue
                size = _num(patch.get("datasize"), 0)
                if not size:
                    data = (patch.get("patchdata") or patch.get("basedata") or "")
                    size = max(1, len(re.sub(r"[^0-9a-fA-F]", "", data)) // 2)
                ranges.append(XdfRange(address, address + size, name))
        return cls(path, title, rom_size, ranges, base_offset, subtract)

    @staticmethod
    def _span(embedded) -> int:
        element = max(1, _num(embedded.get("mmedelementsizebits"), 8) // 8)
        rows = max(1, _num(embedded.get("mmedrowcount"), 1))
        cols = max(1, _num(embedded.get("mmedcolcount"), 1))
        major = abs(_num(embedded.get("mmedmajorstridebits"), 0)) // 8
        minor = abs(_num(embedded.get("mmedminorstridebits"), 0)) // 8
        col_step = minor or element
        row_step = major or cols * col_step
        return (rows - 1) * row_step + (cols - 1) * col_step + element

    # ── address resolution ──────────────────────────────────────────────────
    def resolve(self, file_size: int) -> list[XdfRange]:
        """
        Map XDF addresses onto file offsets.

        BASEOFFSET semantics differ between definition authors, so instead of
        guessing we try every interpretation and keep the one whose ranges fit
        inside the ROM.
        """
        if file_size in self._resolved:
            return self._resolved[file_size]
        if not self.raw_ranges:
            self._resolved[file_size] = []
            return []

        preferred = -self.base_offset if not self.subtract else self.base_offset
        candidates = [preferred, 0, -preferred]
        best: list[XdfRange] = []
        for shift in candidates:
            shifted = [XdfRange(r.start + shift, r.end + shift, r.title)
                       for r in self.raw_ranges]
            if all(0 <= r.start and r.end <= file_size for r in shifted):
                best = shifted
                break
        if not best:
            best = [XdfRange(r.start, r.end, r.title) for r in self.raw_ranges]
        self._resolved[file_size] = sorted(best, key=lambda r: r.start)
        return self._resolved[file_size]

    def coverage(self, file_size: int) -> list[tuple[int, int]]:
        merged: list[list[int]] = []
        for entry in self.resolve(file_size):
            if merged and entry.start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], entry.end)
            else:
                merged.append([entry.start, entry.end])
        return [(start, end) for start, end in merged]

    def tables_at(self, start: int, length: int, file_size: int) -> list[str]:
        end = start + length
        names: list[str] = []
        for entry in self.resolve(file_size):
            if entry.start < end and start < entry.end and entry.title not in names:
                names.append(entry.title)
        return names

    def uncovered(self, regions, file_size: int) -> list[tuple[int, int]]:
        """Parts of the modified regions the XDF does not describe."""
        coverage = self.coverage(file_size)
        gaps: list[tuple[int, int]] = []
        for start, length in regions:
            cursor = start
            end = start + length
            for cov_start, cov_end in coverage:
                if cov_end <= cursor:
                    continue
                if cov_start >= end:
                    break
                if cov_start > cursor:
                    gaps.append((cursor, min(cov_start, end) - cursor))
                cursor = max(cursor, cov_end)
                if cursor >= end:
                    break
            if cursor < end:
                gaps.append((cursor, end - cursor))
        return [g for g in gaps if g[1] > 0]

    @property
    def table_count(self) -> int:
        return len({r.title for r in self.raw_ranges})


# ─────────────────────────────────────────────────────────────────────────────
# Jobs and pre-flight validation
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Issue:
    level: str        # "error" | "warn" | "info"
    text: str

    def __str__(self):
        return f"[{self.level}] {self.text}"


@dataclass
class LockJob:
    customer: str = ""
    vin: str = ""
    stock_bin: str = ""
    tuned_bin: str = ""
    xdf: str = ""
    toolkey: str = ""
    output_dir: str = ""
    extras: list[str] = field(default_factory=list)

    @property
    def label(self) -> str:
        return self.customer or os.path.splitext(os.path.basename(self.tuned_bin))[0] or "job"


@dataclass
class Preflight:
    issues: list[Issue] = field(default_factory=list)
    changed_bytes: int = 0
    regions: list[tuple[int, int]] = field(default_factory=list)
    touched_tables: list[str] = field(default_factory=list)
    uncovered: list[tuple[int, int]] = field(default_factory=list)
    stock_ids: list[str] = field(default_factory=list)
    tuned_ids: list[str] = field(default_factory=list)
    xdf_title: str = ""
    xdf_tables: int = 0
    file_size: int = 0
    vin: str = ""

    @property
    def ok(self) -> bool:
        return not any(issue.level == "error" for issue in self.issues)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warn"]

    def add(self, level, text):
        self.issues.append(Issue(level, text))


def _require_file(report: Preflight, path: str, label: str, extension=None) -> bool:
    if not path:
        report.add("error", f"{label} is missing.")
        return False
    if not os.path.isfile(path):
        report.add("error", f"{label} not found: {path}")
        return False
    if extension and not path.lower().endswith(extension):
        report.add("warn", f"{label} does not end in {extension}: {os.path.basename(path)}")
    return True


def preflight(job: LockJob, definition: XdfDefinition = None) -> Preflight:
    """Check everything the builder would choke on, before spending a run."""
    report = Preflight()

    ok_vin, vin, message = validate_vin(job.vin)
    report.vin = vin
    report.add("error" if not ok_vin else "info", message)

    has_stock = _require_file(report, job.stock_bin, "Stock (original) .bin", ".bin")
    has_tuned = _require_file(report, job.tuned_bin, "Tuned .bin", ".bin")
    has_xdf = _require_file(report, job.xdf, "XDF definition", XDF_EXT)
    _require_file(report, job.toolkey, "MHD .toolkey", TOOLKEY_EXT)

    if job.output_dir and not os.path.isdir(job.output_dir):
        report.add("error", f"Output folder does not exist: {job.output_dir}")

    if has_stock and has_tuned and os.path.abspath(job.stock_bin) == os.path.abspath(job.tuned_bin):
        report.add("error", "Stock and tuned .bin are the same file.")
        has_tuned = False

    # Only the untouched read name is suspicious. Tuners routinely name the tune
    # after it ("…_mapswitch_STG2.bin"), and warning on those trains people to
    # ignore the warning in the one case that matters.
    if has_tuned and _is_bare_customer_read(job.tuned_bin):
        report.add("warn", "The tuned .bin is named exactly like the customer's backup "
                           "read. Is this really the tune?")
    # Only a read filed with this job says anything about this car; one pulled
    # from the library belongs to whoever sent it.
    if has_stock and has_tuned and ok_vin and \
            os.path.dirname(os.path.abspath(job.stock_bin)) == \
            os.path.dirname(os.path.abspath(job.tuned_bin)):
        read_vin, _ = parse_customer_read(job.stock_bin)
        if read_vin and read_vin != vin:
            report.add("warn", f"VIN differs from the customer's read ({read_vin}). "
                               f"the .mhd will only flash on {vin}.")
        elif read_vin:
            report.add("info", "VIN matches the customer's read.")

    stock = tuned = b""
    if has_stock:
        stock = read_bytes(job.stock_bin)
    if has_tuned:
        tuned = read_bytes(job.tuned_bin)
        report.file_size = len(tuned)

    if stock and tuned:
        if len(stock) != len(tuned):
            report.add("error", f"Size mismatch: stock is {len(stock):,} bytes, "
                                f"tuned is {len(tuned):,} bytes.")
        else:
            report.regions = diff_regions(stock, tuned)
            report.changed_bytes = changed_byte_count(stock, tuned)
            if report.changed_bytes == 0:
                report.add("error", "Stock and tuned .bin are identical, "
                                    "the builder would report 'NO modifications found'.")
            else:
                report.add("info", f"{report.changed_bytes:,} byte(s) changed in "
                                   f"{len(report.regions)} region(s).")

        report.stock_ids = detect_rom_ids(stock)
        report.tuned_ids = detect_rom_ids(tuned)
        shared_ids = set(report.stock_ids) & set(report.tuned_ids)
        if report.stock_ids and report.tuned_ids and not shared_ids:
            report.add("warn", "No common software id found in stock and tuned image. The "
                               "the builder may report a software version mismatch.")

    if has_xdf and definition is None:
        try:
            definition = XdfDefinition.load(job.xdf)
        except ET.ParseError as exc:
            report.add("error", f"XDF is not valid XML: {exc}")
            definition = None
        except Exception as exc:
            report.add("error", f"XDF could not be read: {exc}")
            definition = None

    if definition is not None:
        report.xdf_title = definition.title
        report.xdf_tables = definition.table_count
        report.add("info", f"XDF '{definition.title}' · {definition.table_count} table(s).")
        if definition.rom_size and report.file_size and definition.rom_size != report.file_size:
            report.add("warn", f"XDF describes a {human_size(definition.rom_size)} ROM, "
                               f"the .bin is {human_size(report.file_size)}.")
        if report.regions:
            for start, length in report.regions:
                for name in definition.tables_at(start, length, report.file_size):
                    if name not in report.touched_tables:
                        report.touched_tables.append(name)
            report.uncovered = definition.uncovered(report.regions, report.file_size)
            if report.uncovered:
                total = sum(length for _, length in report.uncovered)
                report.add("info",
                           f"{total:,} changed byte(s) in {len(report.uncovered)} region(s) "
                           f"are outside this XDF. The builder also carries its own table "
                           f"definitions, so this is not necessarily a problem, but if it "
                           f"reports 'Modification not in xdf', these are the offsets.")
            else:
                report.add("info", f"All modifications are covered by the XDF "
                                   f"({len(report.touched_tables)} table(s) touched).")
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Staging, a clean directory the builder cannot misread
# ─────────────────────────────────────────────────────────────────────────────
def stock_staged_name(path: str) -> str:
    _vin, read_id = parse_customer_read(path)
    if read_id:
        # the manual rename, automated: the customer's read becomes <id>_original.bin
        return f"{read_id}{STOCK_SUFFIX}"
    stem = os.path.splitext(os.path.basename(path))[0]
    for suffix in ("_original", "_orig", "_stock", "_stk", "_mapswitch"):
        if stem.lower().endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    return f"{safe_name(stem, 'rom', keep_spaces=True)}{STOCK_SUFFIX}"


def tuned_staged_name(path: str, stock_name: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    for suffix in ("_original", "_orig", "_stock"):
        if stem.lower().endswith(suffix):
            stem = stem[:-len(suffix)] + "_tuned"
            break
    name = f"{safe_name(stem, 'tuned', keep_spaces=True)}.bin"
    if name.lower() == stock_name.lower():
        name = f"{safe_name(stem, 'tuned', keep_spaces=True)}_tuned.bin"
    return name


def stage_job(job: LockJob, workdir: str, builder_exe: str = "") -> dict:
    """
    Copy the inputs into `workdir` under the exact names the builder expects.

    This is what removes the classic failures: several .xdf files in the folder,
    a stray *_original.bin, a missing <VIN>_vin.txt or two .toolkey files.
    """
    os.makedirs(workdir, exist_ok=True)
    vin = normalise_vin(job.vin)

    stock_name = stock_staged_name(job.stock_bin)
    tuned_name = tuned_staged_name(job.tuned_bin, stock_name)
    xdf_name = os.path.basename(job.xdf)
    toolkey_name = os.path.basename(job.toolkey)

    shutil.copy2(job.stock_bin, os.path.join(workdir, stock_name))
    shutil.copy2(job.tuned_bin, os.path.join(workdir, tuned_name))
    shutil.copy2(job.xdf, os.path.join(workdir, xdf_name))
    shutil.copy2(job.toolkey, os.path.join(workdir, toolkey_name))

    # The builder takes the VIN from the file name; the file itself stays empty,
    # exactly as in a hand-built working directory.
    vin_name = f"{vin}{VIN_SUFFIX}"
    open(os.path.join(workdir, vin_name), "wb").close()

    staged_extras = []
    for extra in job.extras:
        if extra and os.path.isfile(extra):
            shutil.copy2(extra, os.path.join(workdir, os.path.basename(extra)))
            staged_extras.append(os.path.basename(extra))

    staged_builder = ""
    if builder_exe and os.path.isfile(builder_exe):
        staged_builder = os.path.join(workdir, os.path.basename(builder_exe))
        shutil.copy2(builder_exe, staged_builder)

    return {"workdir": workdir, "stock": stock_name, "tuned": tuned_name,
            "xdf": xdf_name, "toolkey": toolkey_name, "vin_file": vin_name,
            "extras": staged_extras, "builder": staged_builder}


def staged_builder_exe(config: dict) -> str:
    """The builder to copy into a working folder, or "" when none should go in."""
    if not config.get("builder_in_workdir", True):
        return ""
    return config.get("builder_exe", "")


def prepare_folder(job: LockJob, config: dict) -> dict:
    """Build the working folder and leave it there. Nothing is started.

    For the tuner who converts to .mhd by hand: the folder ends up next to the
    tuned file (or in the configured output folder) instead of in a temporary
    directory that the lock run deletes again.
    """
    target = job.output_dir or os.path.dirname(job.tuned_bin)
    workdir = unique_path(os.path.join(target, f"{safe_name(job.label, 'job')}_work"))
    return stage_job(job, workdir, staged_builder_exe(config))


# ─────────────────────────────────────────────────────────────────────────────
# Running the builder
# ─────────────────────────────────────────────────────────────────────────────
def classify_line(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    if any(marker in text for marker in SUCCESS_MARKERS):
        return "ok"
    if any(marker in text for marker in BENIGN_MARKERS):
        return "dim"
    if any(marker in text for marker in ERROR_MARKERS):
        return "error"
    if any(marker in text for marker in WARN_MARKERS):
        return "warn"
    if any(marker in text for marker in INFO_MARKERS):
        return "info"
    return "dim"


@dataclass
class RunResult:
    returncode: int = -1
    lines: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    written: list[str] = field(default_factory=list)
    changed_bytes: int | None = None
    vin_restriction: str = ""
    timed_out: bool = False
    launch_error: str = ""

    @property
    def ok(self) -> bool:
        return bool(self.written) and not self.errors and not self.launch_error


def parse_builder_output(lines) -> RunResult:
    """
    Turn the builder's console chatter into a verdict.

    The exit code is unreliable, the tool ends on a `Press a key…` prompt and
    can fault there after a perfectly good run, so success is decided by the
    'Map correctly written' marker instead.
    """
    result = RunResult(lines=list(lines))
    for raw in result.lines:
        line = raw.strip()
        kind = classify_line(line)
        if kind == "ok":
            _, _, written = line.partition(":")
            result.written.append(written.strip() or line)
        elif kind == "error":
            result.errors.append(line)
        elif kind == "warn":
            result.warnings.append(line)
        if line.startswith("Total bytes changed:"):
            digits = re.sub(r"[^0-9]", "", line)
            result.changed_bytes = int(digits) if digits else None
        elif line.startswith("Restrict to VIN"):
            result.vin_restriction = line.split(":", 1)[-1].strip()
    return result


def run_builder(exe: str, workdir: str, extra_args=None, pass_workdir=False,
                on_line=None, timeout: int = 600, stop_event=None) -> RunResult:
    """Run the MHD builder in `workdir` and stream its output line by line."""
    if not exe or not os.path.isfile(exe):
        result = RunResult()
        result.launch_error = ("MHD map builder not configured. Set the path to "
                               "TuningMapBuilder / MHD Map Encryption in Settings.")
        return result

    command = [exe]
    if pass_workdir:
        command.append(workdir)
    if extra_args:
        command.extend(extra_args if isinstance(extra_args, (list, tuple))
                       else extra_args.split())

    kwargs = {}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    lines: list[str] = []
    state = {"timed_out": False}
    try:
        process = subprocess.Popen(
            command, cwd=workdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1, **kwargs)
    except OSError as exc:
        result = RunResult()
        result.launch_error = f"Could not start the builder: {exc}"
        return result

    def _on_timeout():
        state["timed_out"] = True
        process.kill()

    timer = threading.Timer(timeout, _on_timeout)
    timer.daemon = True
    timer.start()
    try:
        try:  # the builder ends on "Press a key…", feed it one
            process.stdin.write("\r\n")
            process.stdin.flush()
        except OSError:
            pass
        for raw in process.stdout:
            line = raw.rstrip("\r\n")
            lines.append(line)
            if on_line:
                on_line(line, classify_line(line))
            if stop_event is not None and stop_event.is_set():
                process.kill()
                break
        process.wait()
    finally:
        timer.cancel()
        try:
            process.stdin.close()
        except Exception:
            pass

    result = parse_builder_output(lines)
    result.returncode = process.returncode
    result.timed_out = state["timed_out"]
    if result.timed_out:
        result.errors.append(f"Timeout after {timeout} s - the builder was stopped. "
                             f"Raise the timeout in Settings if the job needs longer.")
    elif stop_event is not None and stop_event.is_set():
        result.errors.append("Stopped on request.")
    return result


def collect_outputs(workdir: str, known: set = None) -> list[str]:
    """New *.mhd files the run produced, newest first."""
    known = known or set()
    found = []
    for root, _dirs, files in os.walk(workdir):
        for name in files:
            if name.lower().endswith(OUTPUT_EXT):
                path = os.path.join(root, name)
                if path not in known:
                    found.append(path)
    found.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return found


def snapshot_outputs(workdir: str) -> set:
    return set(collect_outputs(workdir))


def format_output_name(template: str, job: LockJob, index: int = 0,
                       source: str = "") -> str:
    now = datetime.datetime.now()
    tokens = {
        "customer": safe_name(job.customer, "customer"),
        "vin": normalise_vin(job.vin) or "novin",
        "date": now.strftime("%Y%m%d"),
        "time": now.strftime("%H%M%S"),
        "datetime": now.strftime("%Y%m%d-%H%M%S"),
        "tuned": safe_name(os.path.splitext(os.path.basename(job.tuned_bin))[0],
                           "tune", keep_spaces=True),
        "stock": safe_name(os.path.splitext(os.path.basename(job.stock_bin))[0],
                           "stock", keep_spaces=True),
        "source": (safe_name(os.path.splitext(os.path.basename(source))[0], "map",
                             keep_spaces=True) if source else ""),
        "n": str(index + 1),
    }
    try:
        name = template.format(**tokens)
    except (KeyError, IndexError, ValueError):
        name = f"{tokens['customer']}_{tokens['vin']}_{tokens['date']}"
    name = safe_name(name, "locked", keep_spaces=True)
    return name if name.lower().endswith(OUTPUT_EXT) else name + OUTPUT_EXT


def unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    counter = 2
    while os.path.exists(f"{stem}_{counter}{ext}"):
        counter += 1
    return f"{stem}_{counter}{ext}"


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "builder_exe": "",
    "builder_args": "",
    "pass_workdir_arg": False,
    "builder_in_workdir": True,
    "prepare_only": False,
    "output_dir": "",
    "name_template": "{source}",
    "keep_staging": False,
    "open_after_success": True,
    "timeout": 600,
    "toolkey": "",
    "library_dir": "",
    "last_customer": "",
}


def missing_setup(config: dict, toolkey_override: str = "") -> list[str]:
    """What still has to be set once before jobs stop needing anything.

    In folder mode the builder is never started, so its path is no longer a
    condition - it only decides whether the .exe is copied into the folder.
    The .toolkey stays required either way: it belongs in the folder.
    """
    problems = []
    if not config.get("prepare_only", False):
        exe = config.get("builder_exe", "")
        if not exe or not os.path.isfile(exe):
            problems.append("the path to your MHD map builder (TuningMapBuilder / "
                            "MHD Map Encryption)")
    key = config.get("toolkey", "")
    if (not key or not os.path.isfile(key)) and not toolkey_override.strip():
        problems.append("your .toolkey")
    return problems


def config_path() -> str:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "DME Innovation", "mhd_lock_tool.json")


def load_config() -> dict:
    config = dict(DEFAULT_CONFIG)
    try:
        with open(config_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
        if isinstance(stored, dict):
            config.update({k: v for k, v in stored.items() if k in DEFAULT_CONFIG})
    except (OSError, ValueError):
        pass
    return config


def save_config(config: dict) -> bool:
    path = config_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({k: config.get(k, v) for k, v in DEFAULT_CONFIG.items()},
                      handle, indent=2)
        return True
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Batch CSV
# ─────────────────────────────────────────────────────────────────────────────
CSV_FIELDS = ("customer", "vin", "tuned_bin", "stock_bin", "xdf")


def read_batch_csv(path: str, defaults: LockJob) -> tuple[list[LockJob], list[str]]:
    """Read customer,vin,tuned_bin[,stock_bin][,xdf], header optional."""
    jobs: list[LockJob] = []
    problems: list[str] = []
    base = os.path.dirname(os.path.abspath(path))

    def resolve(value):
        value = (value or "").strip().strip('"')
        if not value:
            return ""
        return value if os.path.isabs(value) else os.path.normpath(os.path.join(base, value))

    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(handle, dialect))

    if not rows:
        return jobs, ["CSV file is empty."]

    header = [cell.strip().lower().replace(" ", "_") for cell in rows[0]]
    if set(header) & set(CSV_FIELDS):
        columns = header
        data_rows = rows[1:]
    else:
        columns = list(CSV_FIELDS[:len(rows[0])])
        data_rows = rows

    for number, row in enumerate(data_rows, start=2):
        if not any(cell.strip() for cell in row):
            continue
        values = dict(zip(columns, row))
        job = LockJob(
            customer=(values.get("customer") or "").strip(),
            vin=normalise_vin(values.get("vin")),
            tuned_bin=resolve(values.get("tuned_bin")),
            stock_bin=resolve(values.get("stock_bin")) or defaults.stock_bin,
            xdf=resolve(values.get("xdf")) or defaults.xdf,
            toolkey=defaults.toolkey,
            output_dir=defaults.output_dir,
        )
        if not job.tuned_bin:
            problems.append(f"Row {number}: no tuned .bin given, skipped.")
            continue
        jobs.append(job)
    return jobs, problems


def write_report_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["customer", "vin", "tuned_bin", "status", "output", "detail"])
        for row in rows:
            writer.writerow([row.get("customer", ""), row.get("vin", ""),
                             row.get("tuned_bin", ""), row.get("status", ""),
                             row.get("output", ""), row.get("detail", "")])


# ─────────────────────────────────────────────────────────────────────────────
# GUI
# ─────────────────────────────────────────────────────────────────────────────
NAME_TOKENS = "{customer} {vin} {date} {time} {datetime} {tuned} {stock} {source} {n}"

_TkBase = tk.Tk if TK_AVAILABLE else object


class MhdLockTool(_TkBase):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} · {brand.VENDOR}")
        self.configure(bg=ui.BG)
        ui.init(self)
        self.minsize(ui.px(960), ui.px(700))
        brand.apply_window_icon(self)

        self.config_data = load_config()
        self.batch_jobs: list[LockJob] = []
        self._events: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()
        self._preflight_after = None
        self._manual: set[str] = set()
        self._job_folder = ""       # which customer folder the VIN belongs to
        self._vin_auto = False      # VIN was resolved, not typed - may be corrected
        self._setting_vin = False
        self._xdf_cache: tuple[str, float, XdfDefinition] | None = None

        self._build()
        self._restore_settings()
        self.after(120, self._drain_events)

    # ── Shell ────────────────────────────────────────────────────────────────

    NAV = [
        {"key": "lock", "label": "Lock", "title": "Lock a tune", "icon": "lock",
         "subtitle": LOCK_SUBTITLE},
        {"key": "batch", "label": "Batch", "title": "Batch", "icon": "batch",
         "subtitle": BATCH_SUBTITLE},
        {"key": "settings", "label": "Settings", "title": "Settings", "icon": "settings",
         "subtitle": "Point the tool at your own licensed MHD map builder and your key. "
                     "Set once, used for every job."},
    ]

    def _build(self):
        self.shell = ui.Shell(self, brand, APP_NAME, APP_VERSION, self.NAV,
                              self._show_page)
        self.shell.pack(fill=tk.BOTH, expand=True)
        self.tabs = self.shell
        self.status = self.shell.status
        self._host = self.shell.host
        self.pages = {"lock": self._build_lock_page(),
                      "batch": self._build_batch_page(),
                      "settings": self._build_settings_page()}
        self.shell.select("lock")

    def _show_page(self, key):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill=tk.BOTH, expand=True)

    # ── Lock page ────────────────────────────────────────────────────────────

    def _build_lock_page(self):
        page = ui.Page(self._host)
        self.lock_page = page

        # Shown only while something global is still missing.
        self.setup_card = ui.Card(page.body, title="One-time setup")
        self.setup_msg = tk.Label(self.setup_card.body, text="", bg=ui.CARD, fg=ui.TEXT_DIM,
                                  font=ui.f("small"), anchor="w", justify="left",
                                  wraplength=ui.px(800))
        self.setup_msg.pack(fill=tk.X)
        ui.wrap_to_parent(self.setup_msg)
        ui.button(self.setup_card.body, "Open settings", lambda: self.tabs.select("settings"),
                  variant="secondary", size="sm").pack(anchor="e", pady=(10, 0))

        # ── 1 · the only file you have to pick ──────────────────────────────
        step1 = page.card("Tuned file")
        self._step1 = step1
        self.var_tuned = tk.StringVar()
        self.row_tuned = ui.PathRow(step1.body, "Customer's tuned ROM (.bin)",
                                    self.var_tuned, self._pick_tuned,
                                    browse_text="Choose…",
                                    hint="Everything else is derived from this file")
        self.row_tuned.pack(fill=tk.X)

        ui.hr(step1.body, bg=ui.BORDER, pady=(14, 10))
        self.res_rows = {}
        for key, label in (("stock", "Stock ROM"), ("xdf", "XDF"), ("toolkey", "Tool key")):
            row = ui.ResolvedRow(step1.body, label)
            row.pack(fill=tk.X, pady=1)
            self.res_rows[key] = row

        self.manual = ui.Collapsible(step1.body, "Change manually", bg=ui.CARD)
        self.manual.pack(fill=tk.X, pady=(10, 0))
        self.var_stock = tk.StringVar()
        self.var_xdf = tk.StringVar()
        self.var_toolkey = tk.StringVar()
        for var, label, types, key in (
                (self.var_stock, "Stock / original ROM (.bin)",
                 [("ROM image", "*.bin *.org"), ("All files", "*.*")], "stock"),
                (self.var_xdf, "XDF definition (.xdf)",
                 [("TunerPro XDF", "*.xdf"), ("All files", "*.*")], "xdf"),
                (self.var_toolkey, "MHD tool key (.toolkey)",
                 [("MHD tool key", "*.toolkey"), ("All files", "*.*")], "toolkey")):
            ui.PathRow(self.manual.body, label, var,
                       lambda v=var, l=label, t=types, k=key: self._pick_override(v, l, t, k)
                       ).pack(fill=tk.X, pady=(8, 0))

        # ── 2 · the only thing you have to type ─────────────────────────────
        step2 = page.card("Customer")
        grid = tk.Frame(step2.body, bg=ui.CARD)
        grid.pack(fill=tk.X)
        self.var_vin = tk.StringVar()
        ui.LabeledEntry(grid, "VIN (17 characters)", self.var_vin).grid(
            row=0, column=0, sticky="ew", padx=(0, 14))
        self.var_customer = tk.StringVar()
        ui.LabeledEntry(grid, "Name (optional, used for the file name)",
                        self.var_customer, mono=False).grid(row=0, column=1, sticky="ew")
        grid.grid_columnconfigure(0, weight=1, uniform="c")
        grid.grid_columnconfigure(1, weight=1, uniform="c")
        self.lbl_vin = tk.Label(step2.body, text="", bg=ui.CARD, fg=ui.TEXT_FAINT,
                                font=ui.f("small"), anchor="w")
        self.lbl_vin.pack(fill=tk.X, pady=(8, 0))

        # ── everything else is out of the way ───────────────────────────────
        self.details = ui.Collapsible(page.body, "Details and builder log", bg=ui.BG)
        self.details.pack(fill=tk.X, pady=(0, 14))
        detail_card = ui.Card(self.details.body, title=None)
        detail_card.pack(fill=tk.BOTH, expand=True)
        self.log = ui.LogView(detail_card.body, height=14)
        self.log.pack(fill=tk.BOTH, expand=True)
        tools = tk.Frame(detail_card.body, bg=ui.CARD)
        tools.pack(fill=tk.X, pady=(10, 0))
        ui.button(tools, "Clear", self.log.clear, variant="ghost", size="sm",
                  bg=ui.CARD).pack(side=tk.RIGHT)
        ui.button(tools, "Re-check  ⟳", lambda: self._resolve_and_check(force=True),
                  variant="ghost", size="sm", bg=ui.CARD).pack(side=tk.RIGHT, padx=(0, 8))
        self.log.set_text("Pick a tuned file. The checks start on their own.", "dim")

        self.var_summary = tk.StringVar(value="Waiting for a tuned file")
        page.summary(self.var_summary)
        # Two ways out of this page, both always visible. Which one is the
        # primary pill depends on the folder mode - see _apply_prepare_mode.
        self.btn_lock = ui.button(page.action_row, "Lock now  🔒", self._on_lock,
                                  variant="primary", size="lg")
        self.btn_lock.pack(side=tk.RIGHT)
        # No icon: the folder emoji is an outline glyph that all but disappears
        # next to the solid padlock, and how Windows draws it is not ours to know.
        self.btn_stage = ui.button(page.action_row, "Prepare folder",
                                   self._on_stage_only, variant="secondary", size="lg")
        self.btn_stage.pack(side=tk.RIGHT, padx=(0, 10))

        self.var_tuned.trace_add("write", lambda *_: self._on_tuned_changed())
        self.var_vin.trace_add("write", lambda *_: self._on_vin_typed())
        self.var_customer.trace_add("write", lambda *_: self._schedule_preflight())
        return page

    def _on_vin_typed(self):
        """A VIN is upper case and has no spaces - the file name must match exactly."""
        raw = self.var_vin.get()
        clean = normalise_vin(raw)
        if clean != raw:
            self.var_vin.set(clean)   # re-enters once, then raw == clean
            return
        if not self._setting_vin:
            self._vin_auto = False    # typed by hand: the app stops correcting it
        self._schedule_preflight()

    # ── automatic resolution ─────────────────────────────────────────────────

    def _pick_tuned(self):
        path = filedialog.askopenfilename(
            title="Select the tuned ROM",
            filetypes=[("ROM image", "*.bin"), ("All files", "*.*")],
            initialdir=os.path.dirname(self.var_tuned.get()) or None)
        if path:
            self.var_tuned.set(path)

    def _pick_override(self, variable, title, filetypes, key):
        path = filedialog.askopenfilename(title=title, filetypes=filetypes,
                                          initialdir=os.path.dirname(variable.get()) or None)
        if path:
            self._manual.add(key)
            variable.set(path)
            if key == "stock" and not self.var_vin.get().strip():
                vin, _ = parse_customer_read(path)
                if vin:
                    self.var_vin.set(vin)   # the customer's read carries the VIN
            self._schedule_preflight()

    def _on_tuned_changed(self):
        self._manual.clear()          # a new car starts from scratch
        # Another folder is another customer: a VIN must never survive that move.
        # Within one folder it stays, so a second tune version costs no retyping.
        folder = os.path.dirname(os.path.abspath(self.var_tuned.get().strip()))
        if folder != self._job_folder:
            self._job_folder = folder
            self._set_vin("")
            self._vin_auto = False
        self._schedule_preflight()

    def _set_vin(self, value: str):
        """Fill the VIN field without it counting as typed."""
        self._setting_vin = True
        try:
            self.var_vin.set(value)
        finally:
            self._setting_vin = False

    def _resolve_and_check(self, force=False):
        """Derive every companion file from the tuned ROM, then run the checks."""
        self._cancel_preflight()
        if self._running:
            return
        self._update_setup_hint()

        tuned = self.var_tuned.get().strip()
        if not tuned or not os.path.isfile(tuned):
            for row in self.res_rows.values():
                row.set("", "", ok=False)
            self.row_tuned.set_hint("Everything else is derived from this file")
            self.var_summary.set("Waiting for a tuned file")
            if force:
                self.log.set_text("Pick a tuned file first.", "warn")
            return

        size = os.path.getsize(tuned)
        self.row_tuned.set_hint(f"{os.path.basename(tuned)} · {human_size(size)}", "ok")

        try:
            found = resolve_inputs(tuned, self.config_data.get("library_dir", ""),
                                   self.config_data.get("toolkey", ""))
        except OSError as exc:
            self.log.set_text(f"Could not read the file: {exc}", "error")
            return

        for key in ("stock", "xdf", "toolkey"):
            if key not in self._manual:
                getattr(self, f"var_{key}").set(getattr(found, key))
        # A resolved VIN fills an empty field and corrects an earlier resolved one;
        # a VIN typed by hand is left alone (pre-flight warns if it disagrees).
        if found.vin and (self._vin_auto or not self.var_vin.get().strip()):
            if found.vin != self.var_vin.get():
                self._set_vin(found.vin)
            self._vin_auto = True
        if found.rom_id:
            self._step1.set_hint(f"ROM {found.rom_id}", "ok")

        for key, label in (("stock", "Stock ROM"), ("xdf", "XDF"), ("toolkey", "Tool key")):
            path = getattr(self, f"var_{key}").get().strip()
            source = "chosen manually" if key in self._manual else found.source(key)
            self.res_rows[key].set(os.path.basename(path) if path else "", source,
                                   ok=bool(path) and os.path.isfile(path))

        missing = [k for k in ("stock", "xdf", "toolkey")
                   if not getattr(self, f"var_{k}").get().strip()]
        if missing:
            self.manual.set_title(f"Change manually · {len(missing)} file(s) not found")
        else:
            self.manual.set_title("Change manually")
        for note in found.notes:
            self.log.write(f" ! {note}", "warn")

        self._run_preflight()

    def _update_setup_hint(self):
        """The setup card only exists while something global is still missing."""
        problems = missing_setup(self.config_data, self.var_toolkey.get())
        if problems:
            self.setup_msg.config(text="Still missing: " + " and ".join(problems) +
                                       ". Set it once under Settings. After that every "
                                       "job needs nothing but the tuned file and the VIN.")
            if not self.setup_card.winfo_ismapped():
                self.setup_card.pack(fill=tk.X, pady=(0, 14), before=self._step1)
        elif self.setup_card.winfo_ismapped():
            self.setup_card.pack_forget()

    # ── Pre-flight ───────────────────────────────────────────────────────────

    def _cancel_preflight(self):
        if self._preflight_after:
            self.after_cancel(self._preflight_after)
            self._preflight_after = None

    def _schedule_preflight(self):
        self._save_settings()
        self._cancel_preflight()
        if self._running:
            return
        self._preflight_after = self.after(350, self._resolve_and_check)

    def _run_preflight(self):
        job = self._current_job()
        ok_vin, vin, vin_msg = validate_vin(job.vin)
        self.lbl_vin.config(text=("✓  " if ok_vin else "✕  ") + vin_msg,
                            fg=ui.OK if ok_vin else (ui.TEXT_FAINT if not job.vin else ui.ERR))
        if not (job.stock_bin and job.tuned_bin and os.path.isfile(job.stock_bin)
                and os.path.isfile(job.tuned_bin)):
            self.var_summary.set("Stock ROM not found. Pick it under Details")
            return None
        report = preflight(job, self._definition(job.xdf))
        self._render_preflight(report, job)
        return report

    def _render_preflight(self, report: Preflight, job: LockJob):
        self.log.clear()
        self.log.write("PRE-FLIGHT CHECKS", "dim")
        self.log.write("─" * 62, "dim")
        for issue in report.issues:
            tag = {"error": "error", "warn": "warn"}.get(issue.level, "info")
            mark = {"error": "✕", "warn": "!", "info": "·"}[issue.level]
            self.log.write(f" {mark} {issue.text}", tag)
        if report.regions:
            definition = self._definition(job.xdf)
            self.log.write("")
            self.log.write(f"MODIFIED REGIONS ({len(report.regions)})", "dim")
            self.log.write("─" * 62, "dim")
            for start, length in report.regions[:25]:
                names = definition.tables_at(start, length, report.file_size) if definition else []
                label = ", ".join(names[:2]) if names else "not in this XDF"
                self.log.write(f"  0x{start:07X}  {length:>6,} B   {label[:64]}",
                               "accent" if names else "warn")
            if len(report.regions) > 25:
                self.log.write(f"  … and {len(report.regions) - 25} more region(s)", "dim")
        if report.touched_tables:
            self.log.write("")
            self.log.write(f"TABLES TOUCHED ({len(report.touched_tables)})", "dim")
            self.log.write("─" * 62, "dim")
            for name in report.touched_tables[:20]:
                self.log.write(f"  · {name[:70]}")
            if len(report.touched_tables) > 20:
                self.log.write(f"  … and {len(report.touched_tables) - 20} more", "dim")
        self.log.scroll_top()

        if report.ok:
            self.details.set_title("Details and builder log")
            self.var_summary.set(f"{report.changed_bytes:,} byte(s) changed · "
                                 f"{len(report.touched_tables)} table(s) · ready")
            self.status.set("Ready to prepare"
                            if self.config_data.get("prepare_only", False)
                            else "Ready to lock", "ok")
        else:
            self.details.set_title(f"Details and builder log · {len(report.errors)} problem(s)")
            self.var_summary.set(report.errors[0].text if report.errors else "Checks failed")
            self.status.set("Check failed", "error")
        return report

    # ── Batch page ───────────────────────────────────────────────────────────

    def _build_batch_page(self):
        page = ui.Page(self._host)
        self.batch_page = page

        queue_card = page.card("Job queue", hint="0 jobs")
        self.batch_card = queue_card
        bar = tk.Frame(queue_card.body, bg=ui.CARD)
        bar.pack(fill=tk.X, pady=(0, 12))
        ui.button(bar, "Add tuned files…", self._batch_add_files,
                  variant="secondary", size="sm").pack(side=tk.LEFT)
        ui.button(bar, "Import CSV…", self._batch_import_csv,
                  variant="secondary", size="sm").pack(side=tk.LEFT, padx=(8, 0))
        ui.button(bar, "Export report…", self._batch_export,
                  variant="secondary", size="sm").pack(side=tk.LEFT, padx=(8, 0))
        ui.button(bar, "Clear", self._batch_clear, variant="ghost", size="sm",
                  bg=ui.CARD).pack(side=tk.RIGHT)
        ui.button(bar, "Remove selected", self._batch_remove, variant="ghost", size="sm",
                  bg=ui.CARD).pack(side=tk.RIGHT, padx=(0, 8))

        self.batch_table = ui.Table(queue_card.body, columns=[
            {"key": "customer", "title": "Customer", "width": 170},
            {"key": "vin", "title": "VIN", "width": 160},
            {"key": "tuned", "title": "Tuned file", "width": 260},
            {"key": "status", "title": "Status", "width": 110},
            {"key": "output", "title": "Result", "width": 220},
        ], height=9)
        self.batch_table.pack(fill=tk.BOTH, expand=True)
        self.batch_table.tree.bind("<<TreeviewSelect>>", lambda _e: self._batch_load_selected())

        edit = page.card("Selected job")
        grid = tk.Frame(edit.body, bg=ui.CARD)
        grid.pack(fill=tk.X)
        self.var_b_customer = tk.StringVar()
        self.var_b_vin = tk.StringVar()
        ui.LabeledEntry(grid, "Customer", self.var_b_customer, mono=False).grid(
            row=0, column=0, sticky="ew", padx=(0, 14))
        ui.LabeledEntry(grid, "VIN", self.var_b_vin).grid(row=0, column=1, sticky="ew")
        grid.grid_columnconfigure(0, weight=1, uniform="b")
        grid.grid_columnconfigure(1, weight=1, uniform="b")
        apply_row = tk.Frame(edit.body, bg=ui.CARD)
        apply_row.pack(fill=tk.X, pady=(10, 0))
        self.lbl_batch_file = tk.Label(apply_row, text="No job selected", bg=ui.CARD,
                                       fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w")
        self.lbl_batch_file.pack(side=tk.LEFT)
        ui.button(apply_row, "Apply to selected", self._batch_apply_edit,
                  variant="secondary", size="sm").pack(side=tk.RIGHT)
        ui.button(apply_row, "VIN to all", self._batch_vin_to_all, variant="ghost",
                  size="sm", bg=ui.CARD).pack(side=tk.RIGHT, padx=(0, 8))

        log_card = page.card("Batch log")
        self.batch_log = ui.LogView(log_card.body, height=10)
        self.batch_log.pack(fill=tk.BOTH, expand=True)
        self.batch_log.set_text("Add tuned files or import a CSV to build the queue.", "dim")

        self.var_batch_summary = tk.StringVar(value="Queue is empty")
        page.summary(self.var_batch_summary)
        self.btn_batch_run = ui.button(page.action_row, "Run batch  ▶", self._on_batch_run,
                                       variant="primary", size="lg")
        self.btn_batch_run.pack(side=tk.RIGHT)
        self.btn_batch_stop = ui.button(page.action_row, "Stop", self._on_stop,
                                        variant="secondary", size="lg")
        self.btn_batch_stop.pack(side=tk.RIGHT, padx=(0, 10))
        self.btn_batch_stop.config(state="disabled")
        return page

    # ── Settings page ────────────────────────────────────────────────────────

    def _build_settings_page(self):
        page = ui.Page(self._host)

        def group(label):
            block = ui.GroupedList(page.body, label)
            block.pack(fill=tk.X, pady=(0, 18))
            return block

        builder = group("MHD MAP BUILDER")
        self.var_exe = tk.StringVar()
        ui.PathRow(builder.row(), "Path to the builder executable", self.var_exe,
                   lambda: self._pick_file(self.var_exe, "Select the MHD map builder",
                                           [("Programs", "*.exe"), ("All files", "*.*")]),
                   ).pack(fill=tk.X)
        opts = builder.row()
        self.var_args = tk.StringVar()
        ui.LabeledEntry(opts, "Extra command line arguments, usually empty",
                        self.var_args).grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.var_timeout = tk.StringVar()
        ui.LabeledEntry(opts, "Timeout per job, seconds", self.var_timeout,
                        width=10).grid(row=0, column=1, sticky="ew")
        opts.grid_columnconfigure(0, weight=3)
        opts.grid_columnconfigure(1, weight=1)
        self.var_copy_builder = tk.BooleanVar()
        self.var_pass_workdir = tk.BooleanVar()
        self.var_prepare_only = tk.BooleanVar()
        builder.switch_row("Copy the builder into the working folder",
                           self.var_copy_builder,
                           "Mirrors a folder you built by hand, so the builder always sees "
                           "the right files, and it is the copy that runs when this app "
                           "runs it.", command=self._save_settings)
        builder.switch_row("Pass the working folder as a command line argument",
                           self.var_pass_workdir,
                           "Only needed if your build of the tool expects a path argument.",
                           command=self._save_settings)
        builder.switch_row("I convert to .mhd myself, only prepare the folder",
                           self.var_prepare_only,
                           "Preparing the folder becomes the main action and the builder is "
                           "never started. Its path stays useful: it puts the .exe into the "
                           "folder so you can run it there.", command=self._save_settings)

        yours = group("YOUR FILES, SET ONCE AND USED FOR EVERY JOB")
        self.var_cfg_toolkey = tk.StringVar()
        ui.PathRow(yours.row(), "MHD tool key (.toolkey)", self.var_cfg_toolkey,
                   lambda: self._pick_file(self.var_cfg_toolkey, "Select your .toolkey",
                                           [("MHD tool key", "*.toolkey"),
                                            ("All files", "*.*")]),
                   hint="Stays on this machine. Only copied into the temporary "
                        "working folder.").pack(fill=tk.X)
        self.var_library = tk.StringVar()
        ui.PathRow(yours.row(), "Folder with your XDFs and stock ROMs, optional",
                   self.var_library,
                   lambda: self._pick_dir(self.var_library, "Select the folder"),
                   browse_text="Choose",
                   hint="Only needed when stock ROM and XDF are not stored next to the "
                        "tuned file. Subfolders are searched, matched by ROM id."
                   ).pack(fill=tk.X)

        output = group("OUTPUT")
        self.var_cfg_outdir = tk.StringVar()
        ui.PathRow(output.row(), "Default output folder", self.var_cfg_outdir,
                   lambda: self._pick_dir(self.var_cfg_outdir, "Select the default output folder"),
                   browse_text="Choose").pack(fill=tk.X)
        holder = output.row()
        self.var_template = tk.StringVar()
        ui.LabeledEntry(holder, "File name template", self.var_template).pack(fill=tk.X)
        tokens = tk.Label(holder, text=f"Tokens: {NAME_TOKENS}   ·   "
                                       "{source} keeps the name the builder produced",
                          bg=ui.CARD, fg=ui.TEXT_FAINT, font=ui.f("small"),
                          anchor="w", justify="left")
        tokens.pack(fill=tk.X, pady=(6, 0))
        ui.wrap_to_parent(tokens)
        self.var_open_after = tk.BooleanVar()
        output.switch_row("Open the output folder after a successful lock",
                          self.var_open_after, command=self._save_settings)

        advanced = group("ADVANCED")
        self.var_keep_staging = tk.BooleanVar()
        advanced.switch_row("Keep the temporary working folder after the run",
                            self.var_keep_staging,
                            "Useful when you want to inspect exactly what the builder saw.",
                            command=self._save_settings)
        actions = advanced.row()
        ui.button(actions, "Open settings file location",
                  lambda: ui.reveal_in_file_manager(config_path()),
                  variant="ghost", size="sm", bg=ui.CARD).pack(side=tk.LEFT)
        ui.button(actions, "Reset to defaults", self._reset_settings,
                  variant="ghost", size="sm", bg=ui.CARD).pack(side=tk.RIGHT)

        self.var_settings_summary = tk.StringVar(value="Settings are saved automatically")
        page.summary(self.var_settings_summary)
        ui.button(page.action_row, "Save now", self._save_settings,
                  variant="secondary", size="lg").pack(side=tk.RIGHT)
        return page

    def _checkbox(self, parent, text, variable, hint=None):
        holder = tk.Frame(parent, bg=ui.CARD)
        holder.pack(fill=tk.X, pady=(2, 6))
        box = tk.Checkbutton(holder, text=text, variable=variable, bg=ui.CARD, fg=ui.TEXT,
                             selectcolor=ui.FIELD, activebackground=ui.CARD,
                             activeforeground=ui.TEXT, font=ui.f("small"), bd=0,
                             highlightthickness=0, anchor="w", cursor="hand2",
                             command=self._save_settings)
        box.pack(fill=tk.X)
        if hint:
            label = tk.Label(holder, text=hint, bg=ui.CARD, fg=ui.TEXT_FAINT,
                             font=ui.f("small"), anchor="w", justify="left")
            label.pack(fill=tk.X, padx=(22, 0))
            ui.wrap_to_parent(label, inset=ui.px(30))
        return box

    # ── Settings plumbing ────────────────────────────────────────────────────

    def _restore_settings(self):
        cfg = self.config_data
        self.var_exe.set(cfg.get("builder_exe", ""))
        self.var_args.set(cfg.get("builder_args", ""))
        self.var_timeout.set(str(cfg.get("timeout", 600)))
        self.var_copy_builder.set(bool(cfg.get("builder_in_workdir", True)))
        self.var_pass_workdir.set(bool(cfg.get("pass_workdir_arg", False)))
        self.var_prepare_only.set(bool(cfg.get("prepare_only", False)))
        self.var_cfg_outdir.set(cfg.get("output_dir", ""))
        self.var_template.set(cfg.get("name_template", "{source}"))
        self.var_open_after.set(bool(cfg.get("open_after_success", True)))
        self.var_keep_staging.set(bool(cfg.get("keep_staging", False)))
        self.var_cfg_toolkey.set(cfg.get("toolkey", ""))
        self.var_library.set(cfg.get("library_dir", ""))
        self.var_customer.set(cfg.get("last_customer", ""))
        for var in (self.var_exe, self.var_args, self.var_timeout, self.var_cfg_outdir,
                    self.var_template, self.var_cfg_toolkey, self.var_library):
            var.trace_add("write", lambda *_: self._save_settings())
        self._update_setup_hint()
        self._apply_prepare_mode()

    def _collect_settings(self) -> dict:
        try:
            timeout = max(30, int(re.sub(r"[^0-9]", "", self.var_timeout.get()) or 600))
        except ValueError:
            timeout = 600
        return {
            "builder_exe": self.var_exe.get().strip(),
            "builder_args": self.var_args.get().strip(),
            "pass_workdir_arg": bool(self.var_pass_workdir.get()),
            "builder_in_workdir": bool(self.var_copy_builder.get()),
            "prepare_only": bool(self.var_prepare_only.get()),
            "output_dir": self.var_cfg_outdir.get().strip(),
            "name_template": self.var_template.get().strip() or "{source}",
            "keep_staging": bool(self.var_keep_staging.get()),
            "open_after_success": bool(self.var_open_after.get()),
            "timeout": timeout,
            "toolkey": self.var_cfg_toolkey.get().strip(),
            "library_dir": self.var_library.get().strip(),
            "last_customer": self.var_customer.get().strip(),
        }

    def _save_settings(self):
        self.config_data = self._collect_settings()
        ok = save_config(self.config_data)
        self.var_settings_summary.set("Saved automatically" if ok
                                      else "Could not write the settings file")
        if hasattr(self, "setup_card"):
            self._update_setup_hint()
        self._apply_prepare_mode()

    def _apply_prepare_mode(self):
        """Folder mode moves the weight from locking to preparing.

        The lock button is withdrawn rather than greyed out: a disabled control
        invites people to look for what would enable it, and here nothing would.
        """
        if not hasattr(self, "btn_stage"):
            return
        prepare = bool(self.config_data.get("prepare_only", False))
        self.btn_stage.set_variant("primary" if prepare else "secondary")
        # winfo_ismapped() is false for everything on a page that is not on
        # screen, so it cannot answer "is this button packed?" - winfo_manager can.
        packed = bool(self.btn_lock.winfo_manager())
        if prepare and packed:
            self.btn_lock.pack_forget()
            self.btn_stage.pack_configure(padx=0)
        elif not prepare and not packed:
            self.btn_lock.pack(side=tk.RIGHT)
            self.btn_stage.pack_forget()
            self.btn_stage.pack(side=tk.RIGHT, padx=(0, 10))
        if hasattr(self, "btn_batch_run"):
            self.btn_batch_run.configure(
                text="Prepare folders" if prepare else "Run batch  ▶")
        self.shell.set_subtitle("lock", PREPARE_SUBTITLE if prepare else LOCK_SUBTITLE)
        self.shell.set_subtitle("batch", BATCH_PREPARE_SUBTITLE if prepare
                                else BATCH_SUBTITLE)

    def _reset_settings(self):
        self.config_data = dict(DEFAULT_CONFIG)
        save_config(self.config_data)
        self._restore_settings()
        self.status.set("Settings reset to defaults", "info")

    # ── Input helpers ────────────────────────────────────────────────────────

    def _pick_file(self, variable, title, filetypes):
        initial = os.path.dirname(variable.get()) if variable.get() else ""
        path = filedialog.askopenfilename(title=title, filetypes=filetypes,
                                          initialdir=initial or None)
        if path:
            variable.set(path)

    def _pick_dir(self, variable, title):
        path = filedialog.askdirectory(title=title, initialdir=variable.get() or None)
        if path:
            variable.set(path)

    def _current_job(self) -> LockJob:
        tuned = self.var_tuned.get().strip()
        return LockJob(
            customer=self.var_customer.get().strip(),
            vin=normalise_vin(self.var_vin.get()),
            stock_bin=self.var_stock.get().strip(),
            tuned_bin=tuned,
            xdf=self.var_xdf.get().strip(),
            toolkey=self.var_toolkey.get().strip(),
            output_dir=(self.config_data.get("output_dir", "").strip()
                        or (os.path.dirname(tuned) if tuned else "")),
        )

    def _definition(self, path: str) -> XdfDefinition | None:
        """Parse the XDF once and reuse it while the file does not change."""
        if not path or not os.path.isfile(path):
            return None
        stamp = os.path.getmtime(path)
        if self._xdf_cache and self._xdf_cache[0] == path and self._xdf_cache[1] == stamp:
            return self._xdf_cache[2]
        try:
            definition = XdfDefinition.load(path)
        except Exception:
            return None
        self._xdf_cache = (path, stamp, definition)
        return definition

    # ── Running ──────────────────────────────────────────────────────────────

    def _busy(self, busy: bool):
        self._running = busy
        if busy:
            self._cancel_preflight()
        state = "disabled" if busy else "normal"
        for widget in (self.btn_lock, self.btn_stage, self.btn_batch_run):
            widget.config(state=state)
        self.btn_batch_stop.config(state="normal" if busy else "disabled")

    def _on_stop(self):
        self._stop_event.set()
        self.status.set("Stopping after the current job…", "warn")

    def _on_lock(self):
        job = self._current_job()
        report = preflight(job, self._definition(job.xdf))
        self._render_preflight(report, job)
        if not report.ok:
            self.lock_page.banner.show("error", "Pre-flight failed. Fix the points above first.")
            return
        exe = self.config_data.get("builder_exe", "")
        if not exe or not os.path.isfile(exe):
            self.lock_page.banner.show(
                "error", "No MHD map builder configured. Set its path in the Settings tab.",
                action_text="Open settings", action=lambda: self.tabs.select("settings"))
            return
        self.lock_page.banner.show("busy", f"Locking {os.path.basename(job.tuned_bin)}…")
        self._start([job], target="lock")

    def _on_stage_only(self):
        """Build the working folder without running anything, for a manual run."""
        job = self._current_job()
        report = preflight(job, self._definition(job.xdf))
        self._render_preflight(report, job)
        if not report.ok:
            self.lock_page.banner.show("error", "Pre-flight failed. Fix the points above first.")
            return
        try:
            manifest = prepare_folder(job, self.config_data)
        except OSError as exc:
            self.lock_page.banner.show("error", f"Could not prepare the folder: {exc}")
            return
        workdir = manifest["workdir"]
        self.log.write("")
        self.log.write(f"Working folder prepared: {workdir}", "ok")
        for key in ("stock", "tuned", "xdf", "toolkey", "vin_file"):
            self.log.write(f"    {manifest[key]}", "dim")
        if manifest["builder"]:
            self.log.write(f"    {os.path.basename(manifest['builder'])}", "dim")
        else:
            self.log.write("    (no map builder in the folder. Set its path under "
                           "Settings to have it copied in)", "warn")
        self.lock_page.banner.show("ok", f"Working folder ready:\n{workdir}",
                                   action_text="Show in folder",
                                   action=lambda: ui.reveal_in_file_manager(workdir))
        self.status.set("Working folder prepared", "ok")

    def _on_batch_run(self):
        if not self.batch_jobs:
            self.batch_page.banner.show("error", "The queue is empty.")
            return
        prepare = bool(self.config_data.get("prepare_only", False))
        exe = self.config_data.get("builder_exe", "")
        if not prepare and (not exe or not os.path.isfile(exe)):
            self.batch_page.banner.show(
                "error", "No MHD map builder configured. Set its path in the Settings tab.",
                action_text="Open settings", action=lambda: self.tabs.select("settings"))
            return
        self.batch_log.clear()
        for index in range(len(self.batch_jobs)):
            self.batch_table.update_row(str(index), tag="dim")
            self._set_batch_cell(index, status="queued", output="")
        verb = "Preparing" if prepare else "Running"
        self.batch_page.banner.show("busy", f"{verb} {len(self.batch_jobs)} job(s)…")
        self._start(list(self.batch_jobs), target="batch", prepare_only=prepare)

    def _start(self, jobs, target, prepare_only=False):
        if self._worker and self._worker.is_alive():
            return
        self._stop_event = threading.Event()
        self._busy(True)
        self.status.set("Working…", "busy")
        self._worker = threading.Thread(target=self._work,
                                        args=(jobs, target, prepare_only), daemon=True)
        self._worker.start()

    def _post(self, kind, **payload):
        self._events.put((kind, payload))

    def _work(self, jobs, target, prepare_only=False):
        """Worker thread: stage → run → collect, one isolated folder per job.

        In folder mode it stops after staging and keeps the folder."""
        cfg = dict(self.config_data)
        successes = failures = 0
        for index, job in enumerate(jobs):
            if self._stop_event.is_set():
                self._post("job", index=index, status="stopped", output="", tag="warn")
                break
            started = time.time()
            self._post("log", target=target, line="", tag=None)
            self._post("log", target=target,
                       line=f"━━ [{index + 1}/{len(jobs)}] {job.label} "
                            f"({os.path.basename(job.tuned_bin)})", tag="accent")
            self._post("job", index=index, status="running", output="", tag="busy")

            if not (job.stock_bin and job.xdf and job.toolkey):
                found = resolve_inputs(job.tuned_bin, cfg.get("library_dir", ""),
                                       cfg.get("toolkey", ""))
                job.stock_bin = job.stock_bin or found.stock
                job.xdf = job.xdf or found.xdf
                job.toolkey = job.toolkey or found.toolkey
                job.vin = job.vin or found.vin

            report = preflight(job)
            for issue in report.issues:
                if issue.level != "info":
                    self._post("log", target=target, line=f"   {issue.level}: {issue.text}",
                               tag="error" if issue.level == "error" else "warn")
            if not report.ok:
                failures += 1
                self._post("job", index=index, status="failed", tag="error",
                           output=report.errors[0].text[:60] if report.errors else "pre-flight")
                continue

            if prepare_only:
                try:
                    manifest = prepare_folder(job, cfg)
                except OSError as exc:
                    failures += 1
                    self._post("log", target=target, line=f"   ✕ {exc}", tag="error")
                    self._post("job", index=index, status="failed", tag="error",
                               output=str(exc)[:60])
                    continue
                folder = manifest["workdir"]
                successes += 1
                self._post("log", target=target, line=f"   ✓ {folder}", tag="ok")
                if not manifest["builder"]:
                    self._post("log", target=target,
                               line="   (no map builder in the folder)", tag="warn")
                self._post("job", index=index, status="prepared", tag="ok",
                           output=os.path.basename(folder))
                self._post("result", target=target, path=folder)
                continue

            workdir = tempfile.mkdtemp(prefix="dme_mhd_")
            keep = bool(cfg.get("keep_staging"))
            try:
                manifest = stage_job(job, workdir,
                                     cfg.get("builder_exe", "")
                                     if cfg.get("builder_in_workdir", True) else "")
                exe = manifest.get("builder") or cfg.get("builder_exe", "")
                before = snapshot_outputs(workdir)
                self._post("log", target=target,
                           line=f"   working folder: {workdir}", tag="dim")

                result = run_builder(
                    exe, workdir,
                    extra_args=cfg.get("builder_args", ""),
                    pass_workdir=bool(cfg.get("pass_workdir_arg")),
                    on_line=lambda line, tag: self._post("log", target=target,
                                                         line=f"   {line}", tag=tag),
                    timeout=int(cfg.get("timeout", 600)),
                    stop_event=self._stop_event)

                if result.launch_error:
                    failures += 1
                    self._post("log", target=target, line=f"   {result.launch_error}", tag="error")
                    self._post("job", index=index, status="failed", tag="error",
                               output=result.launch_error[:60])
                    continue

                produced = collect_outputs(workdir, before)
                if not produced:
                    failures += 1
                    detail = result.errors[0] if result.errors else "builder produced no .mhd"
                    self._post("log", target=target, line=f"   ✕ {detail}", tag="error")
                    self._post("job", index=index, status="failed", tag="error",
                               output=detail[:60])
                    continue

                out_dir = job.output_dir or cfg.get("output_dir") or os.path.dirname(job.tuned_bin)
                os.makedirs(out_dir, exist_ok=True)
                finals = []
                for number, source in enumerate(produced):
                    name = format_output_name(cfg.get("name_template", "{source}"),
                                              job, number, source)
                    final = unique_path(os.path.join(out_dir, name))
                    shutil.move(source, final)
                    finals.append(final)
                    self._post("log", target=target, line=f"   ✓ {final}", tag="ok")

                log_path = os.path.splitext(finals[0])[0] + ".log"
                try:
                    with open(log_path, "w", encoding="utf-8") as handle:
                        handle.write(f"{APP_NAME} v{APP_VERSION} · {brand.VENDOR}\n")
                        handle.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
                        handle.write(f"Customer : {job.customer}\nVIN      : {job.vin}\n")
                        handle.write(f"Stock    : {job.stock_bin}\nTuned    : {job.tuned_bin}\n")
                        handle.write(f"XDF      : {job.xdf}\n\n")
                        handle.write("Pre-flight:\n")
                        for issue in report.issues:
                            handle.write(f"  [{issue.level}] {issue.text}\n")
                        handle.write("\nBuilder output:\n")
                        handle.write("\n".join(result.lines))
                except OSError:
                    pass

                successes += 1
                took = time.time() - started
                self._post("log", target=target,
                           line=f"   done in {took:.1f}s", tag="dim")
                self._post("job", index=index, status="locked", tag="ok",
                           output=os.path.basename(finals[0]))
                self._post("result", target=target, path=finals[0])
            except Exception as exc:  # keep the queue alive
                failures += 1
                self._post("log", target=target, line=f"   ✕ {exc}", tag="error")
                self._post("job", index=index, status="failed", tag="error", output=str(exc)[:60])
            finally:
                if not keep:
                    shutil.rmtree(workdir, ignore_errors=True)
                else:
                    self._post("log", target=target,
                               line=f"   kept working folder: {workdir}", tag="dim")
        self._post("done", target=target, successes=successes, failures=failures,
                   total=len(jobs), prepared=prepare_only)

    def _drain_events(self):
        try:
            while True:
                kind, payload = self._events.get_nowait()
                handler = getattr(self, f"_on_event_{kind}", None)
                if handler:
                    handler(**payload)
        except queue.Empty:
            pass
        self.after(120, self._drain_events)

    def _on_event_log(self, target, line, tag):
        view = self.batch_log if target == "batch" else self.log
        view.write(line, tag, follow=True)

    def _on_event_job(self, index, status, output="", tag=None):
        if str(index) in self.batch_table.tree.get_children():
            self._set_batch_cell(index, status=status, output=output)
            self.batch_table.update_row(str(index), tag=tag or "dim")

    def _on_event_result(self, target, path):
        self._last_output = path

    def _on_event_done(self, target, successes, failures, total, prepared=False):
        self._busy(False)
        page = self.batch_page if target == "batch" else self.lock_page
        done = "prepared" if prepared else "locked"
        if failures == 0 and successes:
            tone, text = "ok", (f"{successes} of {total} job(s) {done}."
                                if total > 1 else
                                ("Folder prepared." if prepared else "Locked successfully."))
        elif successes:
            tone, text = "warn", f"{successes} {done}, {failures} failed. See the log."
        else:
            tone, text = "error", f"Nothing was {done}. See the log."
        last = getattr(self, "_last_output", "")
        if tone == "ok" and last:
            text = f"{text}\n{last}"
            page.banner.show(tone, text, action_text="Show in folder",
                             action=lambda p=last: ui.reveal_in_file_manager(p))
            if prepared or self.config_data.get("open_after_success"):
                ui.reveal_in_file_manager(last)
        else:
            page.banner.show(tone, text)
        self.status.set(f"{successes} {done} · {failures} failed", tone)
        if target == "batch":
            self.var_batch_summary.set(f"{successes} {done} · {failures} failed · "
                                       f"{total} total")

    # ── Batch plumbing ───────────────────────────────────────────────────────

    def _set_batch_cell(self, index, status=None, output=None):
        job = self.batch_jobs[index]
        current = self.batch_table.tree.item(str(index), "values")
        values = list(current) if current else [job.customer, job.vin,
                                                os.path.basename(job.tuned_bin), "", ""]
        values[0] = job.customer
        values[1] = job.vin
        values[2] = os.path.basename(job.tuned_bin)
        if status is not None:
            values[3] = status
        if output is not None:
            values[4] = output
        self.batch_table.update_row(str(index), values=values)

    def _batch_refresh(self):
        self.batch_table.clear()
        for index, job in enumerate(self.batch_jobs):
            self.batch_table.add([job.customer, job.vin, os.path.basename(job.tuned_bin),
                                  "queued", ""], iid=str(index), tag="dim")
        self.batch_card.set_hint(f"{len(self.batch_jobs)} job(s)")
        self.var_batch_summary.set("Queue is empty" if not self.batch_jobs
                                   else f"{len(self.batch_jobs)} job(s) queued")

    def _batch_add_files(self):
        paths = filedialog.askopenfilenames(
            title="Select tuned .bin files",
            filetypes=[("ROM image", "*.bin"), ("All files", "*.*")])
        if not paths:
            return
        base = self._current_job()
        unresolved = 0
        inherited = 0
        for path in paths:
            found = resolve_inputs(path, self.config_data.get("library_dir", ""),
                                   self.config_data.get("toolkey", ""))
            if not found.vin and base.vin:
                inherited += 1
            job = LockJob(
                customer=os.path.splitext(os.path.basename(path))[0],
                vin=found.vin or base.vin,
                stock_bin=found.stock or base.stock_bin,
                tuned_bin=path,
                xdf=found.xdf or base.xdf,
                toolkey=found.toolkey or base.toolkey,
                output_dir=base.output_dir)
            if not (job.stock_bin and job.xdf):
                unresolved += 1
            self.batch_jobs.append(job)
        self._batch_refresh()
        self.batch_log.write(f"Added {len(paths)} job(s) - stock ROM and XDF resolved "
                             f"per file.", "ok", follow=True)
        if unresolved:
            self.batch_log.write(f" ! {unresolved} job(s) without a stock ROM or XDF - "
                                 f"set a library folder in Settings.", "warn", follow=True)
        if inherited:
            # one VIN across several cars locks them all to the first one
            self.batch_log.write(f" ! {inherited} job(s) carry no VIN of their own and "
                                 f"took {base.vin} from the Lock tab - check the VIN "
                                 f"column row by row.", "warn", follow=True)
        missing_vin = [j for j in self.batch_jobs if not validate_vin(j.vin)[0]]
        if missing_vin:
            self.batch_log.write(f" ! {len(missing_vin)} job(s) still need a VIN - select a "
                                 f"row and fill it in below.", "warn", follow=True)

    def _batch_import_csv(self):
        path = filedialog.askopenfilename(title="Import batch CSV",
                                          filetypes=[("CSV", "*.csv"), ("All files", "*.*")])
        if not path:
            return
        try:
            jobs, problems = read_batch_csv(path, self._current_job())
        except OSError as exc:
            self.batch_page.banner.show("error", f"Could not read the CSV: {exc}")
            return
        self.batch_jobs.extend(jobs)
        self._batch_refresh()
        self.batch_log.write(f"Imported {len(jobs)} job(s) from {os.path.basename(path)}",
                             "ok", follow=True)
        for problem in problems:
            self.batch_log.write(f"  {problem}", "warn", follow=True)

    def _batch_export(self):
        if not self.batch_jobs:
            self.batch_page.banner.show("error", "Nothing to export. The queue is empty.")
            return
        path = filedialog.asksaveasfilename(title="Export batch report", defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        rows = []
        for index, job in enumerate(self.batch_jobs):
            values = self.batch_table.tree.item(str(index), "values") or ["", "", "", "", ""]
            rows.append({"customer": job.customer, "vin": job.vin,
                         "tuned_bin": job.tuned_bin, "status": values[3],
                         "output": values[4], "detail": ""})
        write_report_csv(path, rows)
        self.batch_page.banner.show("ok", f"Report written:\n{path}",
                                    action_text="Show in folder",
                                    action=lambda: ui.reveal_in_file_manager(path))

    def _batch_remove(self):
        selected = sorted((int(iid) for iid in self.batch_table.selection()), reverse=True)
        for index in selected:
            if 0 <= index < len(self.batch_jobs):
                self.batch_jobs.pop(index)
        self._batch_refresh()

    def _batch_clear(self):
        self.batch_jobs.clear()
        self._batch_refresh()

    def _batch_selected_index(self):
        selection = self.batch_table.selection()
        return int(selection[0]) if selection else None

    def _batch_load_selected(self):
        index = self._batch_selected_index()
        if index is None or index >= len(self.batch_jobs):
            self.lbl_batch_file.config(text="No job selected")
            return
        job = self.batch_jobs[index]
        self.var_b_customer.set(job.customer)
        self.var_b_vin.set(job.vin)
        self.lbl_batch_file.config(text=job.tuned_bin)

    def _batch_apply_edit(self):
        index = self._batch_selected_index()
        if index is None or index >= len(self.batch_jobs):
            return
        job = self.batch_jobs[index]
        job.customer = self.var_b_customer.get().strip()
        job.vin = normalise_vin(self.var_b_vin.get())
        self._set_batch_cell(index)

    def _batch_vin_to_all(self):
        vin = normalise_vin(self.var_b_vin.get())
        if not vin:
            return
        for index, job in enumerate(self.batch_jobs):
            job.vin = vin
            self._set_batch_cell(index)
        self.batch_log.write(f"VIN {vin} applied to {len(self.batch_jobs)} job(s).",
                             "info", follow=True)


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    if not TK_AVAILABLE:
        print(f"{APP_NAME} v{APP_VERSION} · {brand.VENDOR}", file=sys.stderr)
        print("tkinter is not available in this Python installation.", file=sys.stderr)
        print("Windows/macOS: reinstall Python and tick 'tcl/tk and IDLE'.", file=sys.stderr)
        print("Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
        return 1
    ui.enable_dpi_awareness()
    app = MhdLockTool()
    app.geometry(f"{ui.px(1040)}x{ui.px(820)}")
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
