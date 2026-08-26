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
from dme_text import t

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
# The builder ends on Console.ReadKey(), which reads the console input buffer
# and not stdin. A process started without a console, or with stdin redirected,
# therefore does not merely miss the keypress: .NET raises
# InvalidOperationException and the run produces nothing. That is what happened
# on a customer's machine, and it is why run_builder gives it a real console.
# Seen through a pipe the prompt is still the last thing it prints, so it is
# also the signal that the work is over.
END_MARKER = "Press a key"
BENIGN_MARKERS = (
    "Cannot read keys",             # English Windows
    "Press a key",
    "System.Console.ReadKey",       # the type name is the same in every language
    "InvalidOperationException",
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
    """Return (ok, normalised, message). The builder demands exactly 17 chars.

    The message comes out of the word list, so the one place that decides
    whether a VIN is good also speaks whichever language the window is in.
    """
    value = normalise_vin(vin)
    if not value:
        return False, value, t("vin.required")
    if len(value) != 17:
        return False, value, t("vin.length", n=len(value))
    if not VIN_RE.match(value):
        return False, value, t("vin.chars")
    return True, value, t("vin.ok")


# Two things done to a whole ROM image cost real time on an 8 MB file: reading
# it, and searching it for program ids. Both used to be asked for again and
# again while nothing about the file had changed - once per pre-flight, and a
# pre-flight ran 350 ms after every keystroke. Both are remembered here, keyed
# by path, modification time and size, so a changed file is never served stale.
# Few slots on purpose: an entry is the whole image.
_CACHE_SLOTS = 3
_BYTES_CACHE: dict[str, tuple] = {}
_IDS_CACHE: dict[str, tuple] = {}


def _file_stamp(path: str):
    info = os.stat(path)
    return info.st_mtime_ns, info.st_size


def _remember(store: dict, path: str, stamp, value):
    if len(store) >= _CACHE_SLOTS:
        store.pop(next(iter(store)), None)
    store[path] = (stamp, value)
    return value


def forget_files():
    """Drop what is remembered. For tests, and for a fresh job."""
    _BYTES_CACHE.clear()
    _IDS_CACHE.clear()
    _XDF_CACHE.clear()


def read_bytes(path: str) -> bytes:
    try:
        stamp = _file_stamp(path)
    except OSError:
        stamp = None
    if stamp is not None:
        hit = _BYTES_CACHE.get(path)
        if hit is not None and hit[0] == stamp:
            return hit[1]
    with open(path, "rb") as handle:
        data = handle.read()
    return _remember(_BYTES_CACHE, path, stamp, data) if stamp is not None else data


def rom_ids_of(path: str, data: bytes = None, limit: int = 12) -> list[str]:
    """detect_rom_ids for a file, remembered while the file stays as it is."""
    try:
        stamp = _file_stamp(path)
    except OSError:
        return detect_rom_ids(data if data is not None else b"", limit)
    hit = _IDS_CACHE.get(path)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    if data is None:
        data = read_bytes(path)
    return _remember(_IDS_CACHE, path, stamp, detect_rom_ids(data, limit))


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


def changed_byte_count(stock: bytes, tuned: bytes, block: int = 4096) -> int:
    """How many bytes differ.

    Counted in C, not one byte at a time in Python. Block by block, as
    diff_regions does: an equal block is settled by one memcmp and skipped, and
    a block that differs is XORed as a single integer and its zero bytes
    counted, both in C. On an 8 MB pair this takes 0.04 s where the byte loop
    it replaces took 0.28 s, and it copies nothing.
    """
    shared = min(len(stock), len(tuned))
    tail = abs(len(tuned) - len(stock))
    view_a, view_b = memoryview(stock), memoryview(tuned)
    count = 0
    for base in range(0, shared, block):
        # Both slices end at `shared`, never at the longer file's end: two ints
        # of different width would XOR to something too wide to write back.
        end = min(base + block, shared)
        chunk_a = view_a[base:end]
        chunk_b = view_b[base:end]
        if chunk_a == chunk_b:
            continue
        size = end - base
        xor = int.from_bytes(chunk_a, "big") ^ int.from_bytes(chunk_b, "big")
        count += size - xor.to_bytes(size, "big").count(0)
    return count + tail


def detect_rom_ids(data: bytes, limit: int = 12) -> list[str]:
    """Heuristic: the 14-digit program id and SGBM tokens BMW ROMs carry."""
    # finditer, not findall: findall builds the complete list of matches over
    # the whole 8 MB before the loop below gets to stop at the limit.
    found: list[str] = []
    for match in ROM_ID_RE.finditer(data):
        text = match.group().decode("ascii")
        if text != "0" * 14 and text not in found:
            found.append(text)
        if len(found) >= limit:
            break
    for match in SGBM_RE.finditer(data):
        text = match.group().decode("ascii").lower()
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
    # Which step this belongs to. The flow shows the pre-flight in step 2 and
    # the VIN in step 3, so a missing VIN must not paint step 2 red.
    topic: str = ""

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
    region_tables: list[list[str]] = field(default_factory=list)
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

    def add(self, level, text, topic=""):
        self.issues.append(Issue(level, text, topic))


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


@dataclass
class FileScan:
    """What only the files decide: sizes, differences, ids, table coverage.

    Split out of the pre-flight because it is the expensive half. On a real
    8 MB S58 pair it is about a second; the other half is a VIN and four stats.
    The window runs this in a worker and keeps the answer for as long as the
    three files are untouched, so typing a VIN never pays for it again.
    """
    stock: str = ""
    tuned: str = ""
    xdf: str = ""
    stamps: tuple = ()
    ran: bool = False
    file_size: int = 0
    changed_bytes: int = 0
    regions: list[tuple[int, int]] = field(default_factory=list)
    # The table names each region falls into, one list per region and in the
    # same order. Worked out here so the window can print the log without
    # touching the XDF again.
    region_tables: list[list[str]] = field(default_factory=list)
    touched_tables: list[str] = field(default_factory=list)
    uncovered: list[tuple[int, int]] = field(default_factory=list)
    stock_ids: list[str] = field(default_factory=list)
    tuned_ids: list[str] = field(default_factory=list)
    xdf_title: str = ""
    xdf_tables: int = 0
    issues: list[Issue] = field(default_factory=list)

    def matches(self, job: "LockJob") -> bool:
        """Is this still the answer for these three files, as they are now?"""
        return (self.ran and self.stock == job.stock_bin
                and self.tuned == job.tuned_bin and self.xdf == job.xdf
                and self.stamps == stamps_of(job))

    def add(self, level, text, topic=""):
        self.issues.append(Issue(level, text, topic))


def stamps_of(job: "LockJob") -> tuple:
    """Path, time and size of the three files a scan depends on."""
    out = []
    for path in (job.stock_bin, job.tuned_bin, job.xdf):
        try:
            out.append(_file_stamp(path))
        except OSError:
            out.append(None)
    return tuple(out)


_XDF_CACHE: dict[str, tuple] = {}


def definition_for(path: str) -> "XdfDefinition | None":
    """Parse an XDF once and reuse it while the file does not change.

    Shared between the worker and the window on purpose: the worker parses it,
    and by the time the window renders the answer it is already here. Two
    threads racing only means it is parsed twice, never wrongly.
    """
    if not path or not os.path.isfile(path):
        return None
    try:
        stamp = _file_stamp(path)
    except OSError:
        return None
    hit = _XDF_CACHE.get(path)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    try:
        definition = XdfDefinition.load(path)
    except Exception:
        definition = None
    return _remember(_XDF_CACHE, path, stamp, definition)


def scan_files(job: LockJob, definition: XdfDefinition = None) -> FileScan:
    """Read both images, find the differences, and map them onto the XDF.

    Everything in here is decided by the files alone. Nothing typed into the
    window changes any of it, which is what makes it cacheable and what makes
    it safe to run away from the window.
    """
    scan = FileScan(stock=job.stock_bin, tuned=job.tuned_bin, xdf=job.xdf,
                    stamps=stamps_of(job), ran=True)

    has_stock = bool(job.stock_bin) and os.path.isfile(job.stock_bin)
    has_tuned = bool(job.tuned_bin) and os.path.isfile(job.tuned_bin)
    has_xdf = bool(job.xdf) and os.path.isfile(job.xdf)
    if has_stock and has_tuned and \
            os.path.abspath(job.stock_bin) == os.path.abspath(job.tuned_bin):
        has_tuned = False

    stock = tuned = b""
    if has_stock:
        stock = read_bytes(job.stock_bin)
    if has_tuned:
        tuned = read_bytes(job.tuned_bin)
        scan.file_size = len(tuned)

    if stock and tuned:
        if len(stock) != len(tuned):
            scan.add("error", f"Size mismatch: stock is {len(stock):,} bytes, "
                              f"tuned is {len(tuned):,} bytes.")
        else:
            scan.regions = diff_regions(stock, tuned)
            scan.changed_bytes = changed_byte_count(stock, tuned)
            if scan.changed_bytes == 0:
                scan.add("error", "Stock and tuned .bin are identical, "
                                  "the builder would report 'NO modifications found'.")
            else:
                scan.add("info", f"{scan.changed_bytes:,} byte(s) changed in "
                                 f"{len(scan.regions)} region(s).")

        scan.stock_ids = rom_ids_of(job.stock_bin, stock)
        scan.tuned_ids = rom_ids_of(job.tuned_bin, tuned)
        shared_ids = set(scan.stock_ids) & set(scan.tuned_ids)
        if scan.stock_ids and scan.tuned_ids and not shared_ids:
            scan.add("warn", "No common software id found in stock and tuned image. The "
                             "the builder may report a software version mismatch.")

    if has_xdf and definition is None:
        try:
            definition = XdfDefinition.load(job.xdf)
        except ET.ParseError as exc:
            scan.add("error", f"XDF is not valid XML: {exc}")
            definition = None
        except Exception as exc:
            scan.add("error", f"XDF could not be read: {exc}")
            definition = None

    if definition is not None:
        scan.xdf_title = definition.title
        scan.xdf_tables = definition.table_count
        scan.add("info", f"XDF '{definition.title}' \u00b7 {definition.table_count} table(s).")
        if definition.rom_size and scan.file_size and definition.rom_size != scan.file_size:
            scan.add("warn", f"XDF describes a {human_size(definition.rom_size)} ROM, "
                             f"the .bin is {human_size(scan.file_size)}.")
        if scan.regions:
            for start, length in scan.regions:
                names = definition.tables_at(start, length, scan.file_size)
                scan.region_tables.append(names)
                for name in names:
                    if name not in scan.touched_tables:
                        scan.touched_tables.append(name)
            scan.uncovered = definition.uncovered(scan.regions, scan.file_size)
            if scan.uncovered:
                total = sum(length for _, length in scan.uncovered)
                scan.add("info",
                         f"{total:,} changed byte(s) in {len(scan.uncovered)} region(s) "
                         f"are outside this XDF. The builder also carries its own table "
                         f"definitions, so this is not necessarily a problem, but if it "
                         f"reports 'Modification not in xdf', these are the offsets.")
            else:
                scan.add("info", f"All modifications are covered by the XDF "
                                 f"({len(scan.touched_tables)} table(s) touched).")
    if len(scan.region_tables) != len(scan.regions):
        scan.region_tables = [[] for _ in scan.regions]
    return scan


def preflight(job: LockJob, definition: XdfDefinition = None,
              scan: FileScan = None) -> Preflight:
    """Check everything the builder would choke on, before spending a run.

    ``scan`` is a FileScan from an earlier run. When it still fits these files
    it is folded in and nothing is read; without it the scan happens here, so
    calling preflight(job) alone behaves exactly as it always did.
    """
    report = Preflight()

    ok_vin, vin, message = validate_vin(job.vin)
    report.vin = vin
    report.add("error" if not ok_vin else "info", message, topic="vin")

    has_stock = _require_file(report, job.stock_bin, "Stock (original) .bin", ".bin")
    has_tuned = _require_file(report, job.tuned_bin, "Tuned .bin", ".bin")
    _require_file(report, job.xdf, "XDF definition", XDF_EXT)
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

    if scan is None or not scan.matches(job):
        scan = scan_files(job, definition)
    report.file_size = scan.file_size
    report.changed_bytes = scan.changed_bytes
    report.regions = scan.regions
    report.region_tables = scan.region_tables
    report.touched_tables = scan.touched_tables
    report.uncovered = scan.uncovered
    report.stock_ids = scan.stock_ids
    report.tuned_ids = scan.tuned_ids
    report.xdf_title = scan.xdf_title
    report.xdf_tables = scan.xdf_tables
    report.issues.extend(scan.issues)
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


def _terminate_tree(process) -> None:
    """End the builder and anything it started. It is waiting for a keypress."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(process.pid)],
                       capture_output=True)
    else:
        process.kill()
    try:
        process.wait(timeout=15)
    except Exception:
        pass


# A .NET console writes in the machine's OEM code page, not UTF-8. Decoding it
# as UTF-8 turned the customer's "Schlüssel" into "Schl?ssel" and would mangle
# any file name with an umlaut in it.
_OUTPUT_ENCODINGS = ("utf-8", "cp850", "cp1252")


def decode_console(raw: bytes) -> str:
    for encoding in _OUTPUT_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace")


def run_builder(exe: str, workdir: str, target: str = "", extra_args=None,
                pass_workdir=False, on_line=None, timeout: int = 600,
                stop_event=None) -> RunResult:
    """Run the MHD builder on `target` and stream its output line by line.

    Two things about this tool, both learned from a failed customer job:

    `target` is the tuned .bin, handed over as a command line argument. That is
    what dropping a file onto the .exe in Explorer does, and it is how tuners
    use it. Started without one the builder has nothing to work on: it prints
    nothing, goes straight to its closing prompt, and the run yields no .mhd.

    And it is started the way a double click starts it, with its own console and
    with stdin left alone. The builder finishes on Console.ReadKey(), which .NET
    refuses when the process has no console or when stdin is redirected - it
    raises instead. Writing a newline into stdin cannot help either, because
    ReadKey does not read stdin. Nobody is going to press that key, so
    `Press a key` is treated as the end of the work and the process ends there.
    """
    if not exe or not os.path.isfile(exe):
        result = RunResult()
        result.launch_error = ("MHD map builder not configured. Set the path to "
                               "TuningMapBuilder / MHD Map Encryption in Settings.")
        return result

    command = [exe]
    if target:
        command.append(target)
    if pass_workdir:
        command.append(workdir)
    if extra_args:
        command.extend(extra_args if isinstance(extra_args, (list, tuple))
                       else extra_args.split())

    kwargs = {}
    if os.name == "nt":
        # Its own console, with the window hidden: the builder gets what it
        # needs, the tuner sees nothing flash up.
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = info
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

    lines: list[str] = []
    state = {"timed_out": False}
    try:
        # stdin is deliberately NOT redirected.
        process = subprocess.Popen(
            command, cwd=workdir, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, **kwargs)
    except OSError as exc:
        result = RunResult()
        result.launch_error = f"Could not start the builder: {exc}"
        return result

    def _on_timeout():
        state["timed_out"] = True
        _terminate_tree(process)

    timer = threading.Timer(timeout, _on_timeout)
    timer.daemon = True
    timer.start()
    try:
        while True:
            raw = process.stdout.readline()
            if not raw:
                break
            line = decode_console(raw).rstrip("\r\n")
            lines.append(line)
            if on_line:
                on_line(line, classify_line(line))
            if END_MARKER in line:
                break
            if stop_event is not None and stop_event.is_set():
                break
    finally:
        timer.cancel()
        _terminate_tree(process)
        try:
            process.stdout.close()
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
    "language": "de",
}


def missing_setup(config: dict, toolkey_override: str = "") -> list[str]:
    """What still has to be set once before jobs stop needing anything.

    In folder mode the builder is never started, so its path is no longer a
    condition - it only decides whether the .exe is copied into the folder.
    The .toolkey stays required either way: it belongs in the folder.

    Returns keys, not sentences: "builder" and "toolkey". The window turns them
    into a sentence in whichever language it is showing.
    """
    problems = []
    if not config.get("prepare_only", False):
        exe = config.get("builder_exe", "")
        if not exe or not os.path.isfile(exe):
            problems.append("builder")
    key = config.get("toolkey", "")
    if (not key or not os.path.isfile(key)) and not toolkey_override.strip():
        problems.append("toolkey")
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

# Status words the worker posts, translated on the way into the table.
STATUS_KEYS = {"word.queued", "word.running", "word.failed", "word.stopped",
               "word.prepared", "word.locked"}


class LockUI:
    """The Lock and Batch areas, and everything under Settings that belongs to
    the builder.

    It used to be a window of its own. Now it builds its pages into the shared
    host and writes into the shared status line; nothing below this line knows
    or cares that it is not a window any more. The engine underneath it,
    everything above the GUI section in this file, is unchanged.
    """

    def __init__(self, app):
        self.app = app
        self.config_data = app.config_data
        self.batch_jobs: list[LockJob] = []
        self._events: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()
        self._drain_id = None
        # The expensive half of the check, its answer, and which request it
        # belongs to. A late answer from an overtaken request is dropped.
        self._scan: FileScan | None = None
        self._scan_after = None
        self._scan_thread: threading.Thread | None = None
        self._queue_thread: threading.Thread | None = None
        self._scan_generation = 0
        self._save_after = None
        self._manual: set[str] = set()
        self._job_folder = ""       # which customer folder the VIN belongs to
        self._vin_auto = False      # VIN was resolved, not typed - may be corrected
        self._setting_vin = False
        self._log_shown = False
        self._log_signature = None
        self._batch_counts = {"total": 0, "unresolved": 0, "no_vin": 0}
        self._last_output = ""
        self._traced = False

        # Everything the user has typed or picked lives here, not in a widget,
        # which is what lets the language switch throw the pages away.
        self.var_tuned = tk.StringVar()
        self.var_stock = tk.StringVar()
        self.var_xdf = tk.StringVar()
        self.var_toolkey = tk.StringVar()
        self.var_vin = tk.StringVar()
        self.var_customer = tk.StringVar()
        self.var_summary = tk.StringVar()
        self.var_batch_summary = tk.StringVar()
        self.var_b_customer = tk.StringVar()
        self.var_b_vin = tk.StringVar()
        self.var_exe = tk.StringVar()
        self.var_args = tk.StringVar()
        self.var_timeout = tk.StringVar()
        self.var_copy_builder = tk.BooleanVar()
        self.var_pass_workdir = tk.BooleanVar()
        self.var_prepare_only = tk.BooleanVar()
        self.var_cfg_toolkey = tk.StringVar()
        self.var_library = tk.StringVar()
        self.var_cfg_outdir = tk.StringVar()
        self.var_template = tk.StringVar()
        self.var_open_after = tk.BooleanVar()
        self.var_keep_staging = tk.BooleanVar()
        self.var_settings_summary = tk.StringVar()
        self._restore_settings()

    # ── the two pages ───────────────────────────────────────────────────────
    def build_pages(self):
        return {"lock": self._build_lock_page(), "batch": self._build_batch_page()}

    def after_mount(self):
        """Once the pages hang in the shell, put the state back on them."""
        self._update_setup_hint()
        self._apply_prepare_mode()
        self._batch_refresh()
        # Always, not only with a file in hand: the empty branch is what paints
        # the marks in step 2 grey instead of leaving them white on white.
        self._paint_marks()
        self._recheck()
        if self.var_tuned.get().strip():
            self._schedule_scan(delay=0)
        else:
            self.app.set_status(t("status.waiting_file"))
        if not self._traced:
            self.var_tuned.trace_add("write", lambda *_: self._on_tuned_changed())
            self.var_vin.trace_add("write", lambda *_: self._on_vin_typed())
            # The customer name is the file name and nothing else. It used to
            # start a full pre-flight per keystroke, which is a second of the
            # window standing still for a field that changes no verdict.
            self.var_customer.trace_add("write", lambda *_: self._save_later())
            # Only these two change what the search finds, so only these two
            # throw the scan away.
            for var in (self.var_cfg_toolkey, self.var_library):
                var.trace_add("write", lambda *_: self._on_sources_changed())
            for var in (self.var_exe, self.var_args, self.var_timeout,
                        self.var_cfg_outdir, self.var_template):
                var.trace_add("write", lambda *_: self._save_later())
            self._traced = True
        if self._drain_id is None:
            self._drain_id = self.app.after(60, self._drain_events)

    def is_busy(self) -> bool:
        """Is anything still running for this controller?

        Three things can be: the job worker, the file scan and the queue
        builder. Plus whatever they have already posted and nobody has drawn
        yet. Used by the tests to wait for the window to be finished.
        """
        if self._scan_after is not None:       # a scan is due but not started
            return True
        for thread in (self._worker, self._scan_thread, self._queue_thread):
            if thread is not None and thread.is_alive():
                return True
        return not self._events.empty()

    def shutdown(self):
        # The queue poller is rearmed every 120 ms. Without this, closing the
        # window leaves one pending call that fires against a widget that is
        # already gone.
        self._cancel_scan()
        if self._save_after:
            try:
                self.app.after_cancel(self._save_after)
            except tk.TclError:
                pass
            self._save_after = None
        if self._drain_id is not None:
            try:
                self.app.after_cancel(self._drain_id)
            except tk.TclError:
                pass
            self._drain_id = None

    # ── small parts the flow is built from ──────────────────────────────────
    def _file_row(self, parent, variable, on_browse, hint="", width=None,
                  browse=None, mono=True):
        """A well with a value in it and one button beside it."""
        holder = tk.Frame(parent, bg=ui.BG)
        row = tk.Frame(holder, bg=ui.BG)
        row.pack(fill=tk.X)
        field = ui.entry(row, variable, mono=mono)
        field.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=ui.px(7))
        if width:
            field.configure(width=width)
            field.pack_configure(expand=False)
        ui.button(row, browse or t("word.choose"), on_browse, variant="secondary",
                  size="md", bg=ui.BG).pack(side=tk.LEFT, padx=(ui.px(9), 0))
        label = tk.Label(holder, text=hint, bg=ui.BG, fg=ui.TEXT_FAINT,
                         font=ui.f("small"), anchor="w", justify="left")
        label.pack(fill=tk.X, pady=(ui.px(7), 0))
        ui.wrap_to_parent(label)
        holder.hint = label
        holder.entry = field
        return holder

    # ── Lock page ───────────────────────────────────────────────────────────
    def _build_lock_page(self):
        page = ui.Page(self.app.host, width=880)
        self.lock_page = page

        # Shown only while something global is still missing.
        self.setup_card = ui.Card(page.body, title=t("setup.title"))
        self.setup_msg = tk.Label(self.setup_card.body, text="", bg=ui.CARD,
                                  fg=ui.TEXT_DIM, font=ui.f("small"), anchor="w",
                                  justify="left", wraplength=ui.px(700))
        self.setup_msg.pack(fill=tk.X)
        ui.wrap_to_parent(self.setup_msg)
        ui.button(self.setup_card.body, t("setup.open"),
                  lambda: self.app.go("settings"), variant="secondary",
                  size="sm").pack(anchor="e", pady=(ui.px(10), 0))

        flow = ui.Flow(page.body)
        flow.pack(fill=tk.X)
        self.flow = flow

        # ── 1 · the only file you have to pick ──────────────────────────────
        step = flow.step(t("lock.step1"), state="now")
        self.step_file = step
        self.row_tuned = self._file_row(step.body, self.var_tuned, self._pick_tuned,
                                        hint=t("lock.step1.hint"))
        self.row_tuned.pack(fill=tk.X)

        # ── 2 · what the tool found on its own ──────────────────────────────
        step = flow.step(t("lock.step2"))
        self.step_check = step
        marks = tk.Frame(step.body, bg=ui.BG)
        marks.pack(fill=tk.X)
        self.res_tags = {}
        for key in ("stock", "xdf", "toolkey", "builder"):
            chip = ui.tag(marks, t(f"lock.step2.{key}"), "idle", bg=ui.BG)
            chip.pack(side=tk.LEFT, padx=(0, ui.px(7)))
            self.res_tags[key] = chip
        self.manual = ui.Collapsible(step.body, t("lock.step2.manual"), bg=ui.BG)
        self.manual.pack(fill=tk.X, pady=(ui.px(12), 0))
        for var, label, types, key in (
                (self.var_stock, t("dlg.stock"),
                 [("ROM image", "*.bin *.org"), ("All files", "*.*")], "stock"),
                (self.var_xdf, t("dlg.xdf"),
                 [("TunerPro XDF", "*.xdf"), ("All files", "*.*")], "xdf"),
                (self.var_toolkey, t("dlg.toolkey"),
                 [("MHD tool key", "*.toolkey"), ("All files", "*.*")], "toolkey")):
            ui.PathRow(self.manual.body, label, var,
                       lambda v=var, l=label, ty=types, k=key:
                       self._pick_override(v, l, ty, k), bg=ui.BG,
                       browse_text=t("word.browse")).pack(fill=tk.X, pady=(ui.px(8), 0))

        # ── 3 · the only thing you have to type ─────────────────────────────
        step = flow.step(t("lock.step3"))
        self.step_vin = step
        self.row_vin = self._file_row(step.body, self.var_vin, self._paste_vin,
                                      hint=t("lock.step3.hint"), width=22,
                                      browse=t("word.change"))
        self.row_vin.pack(fill=tk.X)
        self.row_vin.entry.configure(state="normal")
        name = tk.Frame(step.body, bg=ui.BG)
        name.pack(fill=tk.X, pady=(ui.px(12), 0))
        ui.LabeledEntry(name, t("lock.step3.customer"), self.var_customer,
                        bg=ui.BG, mono=False).pack(fill=tk.X)
        self.lbl_vin = tk.Label(step.body, text="", bg=ui.BG, fg=ui.TEXT_FAINT,
                                font=ui.f("small"), anchor="w")
        self.lbl_vin.pack(fill=tk.X, pady=(ui.px(8), 0))

        # ── 4 · the action, and everything it says while it works ───────────
        step = flow.step(t("lock.step4"))
        self.step_run = step
        self.lbl_run = tk.Label(step.body, text=t("lock.step4.hint"), bg=ui.BG,
                                fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w",
                                justify="left")
        self.lbl_run.pack(fill=tk.X)
        ui.wrap_to_parent(self.lbl_run)
        self.log_holder = tk.Frame(step.body, bg=ui.BG)
        self.log = ui.LogView(self.log_holder, height=11)
        self.log.pack(fill=tk.BOTH, expand=True)
        tools = tk.Frame(self.log_holder, bg=ui.BG)
        tools.pack(fill=tk.X, pady=(ui.px(9), 0))
        ui.button(tools, t("word.save_log"), self._save_log, variant="secondary",
                  size="sm", bg=ui.BG).pack(side=tk.LEFT)
        ui.button(tools, t("word.clear"), self._clear_log, variant="ghost",
                  size="sm", bg=ui.BG).pack(side=tk.RIGHT)
        self.result_box = tk.Frame(step.body, bg=ui.BG)

        self.var_summary.set(t("status.waiting_file"))
        page.summary(self.var_summary)
        # Two ways out of this page, both always visible. Which one is the
        # primary button depends on the folder mode, see _apply_prepare_mode.
        self.btn_lock = ui.button(page.action_row, t("lock.btn.lock"), self._on_lock,
                                  variant="primary", size="lg", bg=ui.SURFACE)
        self.btn_lock.pack(side=tk.RIGHT)
        self.btn_stage = ui.button(page.action_row, t("lock.btn.prepare"),
                                   self._on_stage_only, variant="secondary",
                                   size="lg", bg=ui.SURFACE)
        self.btn_stage.pack(side=tk.RIGHT, padx=(0, ui.px(10)))
        return page

    def _clear_log(self):
        self.log.clear()
        self._log_signature = None
        self._hide_log()

    def _show_log(self):
        if not self._log_shown:
            self.log_holder.pack(fill=tk.BOTH, expand=True, pady=(ui.px(12), 0))
            self._log_shown = True

    def _hide_log(self):
        if self._log_shown:
            self.log_holder.pack_forget()
            self._log_shown = False

    def _paste_vin(self):
        """The VIN comes from the customer read; this is the way to correct it."""
        self.row_vin.entry.focus_set()
        self.row_vin.entry.select_range(0, tk.END)

    # ── Batch page ──────────────────────────────────────────────────────────
    def _build_batch_page(self):
        page = ui.Page(self.app.host, width=940)
        self.batch_page = page

        flow = ui.Flow(page.body)
        flow.pack(fill=tk.X)
        self.batch_flow = flow

        step = flow.step(t("batch.step1"), state="now")
        self.step_files = step
        self.batch_table = ui.Table(step.body, columns=[
            {"key": "customer", "title": t("batch.col.customer"), "width": 150},
            {"key": "vin", "title": t("batch.col.vin"), "width": 150},
            {"key": "tuned", "title": t("batch.col.file"), "width": 250},
            {"key": "status", "title": t("batch.col.status"), "width": 100},
            {"key": "output", "title": t("batch.col.result"), "width": 190},
        ], height=8)
        self.batch_table.pack(fill=tk.BOTH, expand=True)
        self.batch_table.tree.bind("<<TreeviewSelect>>",
                                   lambda _e: self._batch_load_selected())
        bar = tk.Frame(step.body, bg=ui.BG)
        bar.pack(fill=tk.X, pady=(ui.px(11), 0))
        ui.button(bar, t("batch.add_files"), self._batch_add_files,
                  variant="secondary", size="sm", bg=ui.BG).pack(side=tk.LEFT)
        ui.button(bar, t("batch.import_csv"), self._batch_import_csv,
                  variant="secondary", size="sm", bg=ui.BG).pack(side=tk.LEFT,
                                                                 padx=(ui.px(8), 0))
        ui.button(bar, t("batch.export"), self._batch_export, variant="secondary",
                  size="sm", bg=ui.BG).pack(side=tk.LEFT, padx=(ui.px(8), 0))
        ui.button(bar, t("batch.clear"), self._batch_clear, variant="ghost",
                  size="sm", bg=ui.BG).pack(side=tk.RIGHT)
        ui.button(bar, t("batch.remove"), self._batch_remove, variant="ghost",
                  size="sm", bg=ui.BG).pack(side=tk.RIGHT, padx=(0, ui.px(8)))

        edit = tk.Frame(step.body, bg=ui.BG)
        edit.pack(fill=tk.X, pady=(ui.px(14), 0))
        grid = tk.Frame(edit, bg=ui.BG)
        grid.pack(fill=tk.X)
        ui.LabeledEntry(grid, t("batch.col.customer"), self.var_b_customer,
                        bg=ui.BG, mono=False).grid(row=0, column=0, sticky="ew",
                                                   padx=(0, ui.px(14)))
        ui.LabeledEntry(grid, t("batch.col.vin"), self.var_b_vin, bg=ui.BG).grid(
            row=0, column=1, sticky="ew")
        grid.grid_columnconfigure(0, weight=1, uniform="b")
        grid.grid_columnconfigure(1, weight=1, uniform="b")
        apply_row = tk.Frame(edit, bg=ui.BG)
        apply_row.pack(fill=tk.X, pady=(ui.px(10), 0))
        self.lbl_batch_file = tk.Label(apply_row, text=t("batch.selected"), bg=ui.BG,
                                       fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w")
        self.lbl_batch_file.pack(side=tk.LEFT)
        ui.button(apply_row, t("batch.apply"), self._batch_apply_edit,
                  variant="secondary", size="sm", bg=ui.BG).pack(side=tk.RIGHT)
        ui.button(apply_row, t("batch.vin_to_all"), self._batch_vin_to_all,
                  variant="ghost", size="sm", bg=ui.BG).pack(side=tk.RIGHT,
                                                             padx=(0, ui.px(8)))

        step = flow.step(t("batch.step2"))
        self.step_batch_check = step
        self.batch_marks = tk.Frame(step.body, bg=ui.BG)
        self.batch_marks.pack(fill=tk.X)
        self.lbl_batch_check = tk.Label(step.body, text=t("batch.step2.idle"), bg=ui.BG,
                                        fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w",
                                        justify="left")
        self.lbl_batch_check.pack(fill=tk.X)
        ui.wrap_to_parent(self.lbl_batch_check)

        step = flow.step(t("batch.step3"))
        self.step_batch_run = step
        hint = tk.Label(step.body, text=t("batch.step3.hint"), bg=ui.BG,
                        fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w", justify="left")
        hint.pack(fill=tk.X)
        ui.wrap_to_parent(hint)
        self.batch_log = ui.LogView(step.body, height=9)
        self.batch_log.pack(fill=tk.BOTH, expand=True, pady=(ui.px(12), 0))

        self.var_batch_summary.set(t("batch.step1.empty"))
        page.summary(self.var_batch_summary)
        self.btn_batch_run = ui.button(page.action_row, t("batch.btn.run"),
                                       self._on_batch_run, variant="primary",
                                       size="lg", bg=ui.SURFACE)
        self.btn_batch_run.pack(side=tk.RIGHT)
        self.btn_batch_stop = ui.button(page.action_row, t("word.stop"), self._on_stop,
                                        variant="secondary", size="lg", bg=ui.SURFACE)
        self.btn_batch_stop.pack(side=tk.RIGHT, padx=(0, ui.px(10)))
        self.btn_batch_stop.config(state="disabled")
        return page

    # ── Settings ────────────────────────────────────────────────────────────
    def build_settings(self, page):
        def group(label):
            block = ui.GroupedList(page.body, label)
            block.pack(fill=tk.X, pady=(0, ui.px(20)))
            return block

        tools = group(t("settings.group.tools"))
        row = tools.row()
        ui.PathRow(row, t("settings.builder"), self.var_exe,
                   lambda: self._pick_file(self.var_exe, t("dlg.builder"),
                                           [("Programs", "*.exe"), ("All files", "*.*")]),
                   browse_text=t("word.browse"),
                   hint=t("settings.builder.hint")).pack(fill=tk.X)
        row = tools.row()
        ui.PathRow(row, t("settings.toolkey"), self.var_cfg_toolkey,
                   lambda: self._pick_file(self.var_cfg_toolkey, t("dlg.toolkey"),
                                           [("MHD tool key", "*.toolkey"),
                                            ("All files", "*.*")]),
                   browse_text=t("word.browse"),
                   hint=t("settings.toolkey.hint")).pack(fill=tk.X)
        row = tools.row()
        ui.PathRow(row, t("settings.library"), self.var_library,
                   lambda: self._pick_dir(self.var_library, t("dlg.library")),
                   browse_text=t("word.choose"),
                   hint=t("settings.library.hint")).pack(fill=tk.X)
        opts = tools.row()
        ui.LabeledEntry(opts, t("settings.args"), self.var_args).grid(
            row=0, column=0, sticky="ew", padx=(0, ui.px(14)))
        ui.LabeledEntry(opts, t("settings.timeout"), self.var_timeout,
                        width=10).grid(row=0, column=1, sticky="ew")
        opts.grid_columnconfigure(0, weight=3)
        opts.grid_columnconfigure(1, weight=1)

        flow = group(t("settings.group.flow"))
        flow.switch_row(t("settings.prepare_only"), self.var_prepare_only,
                        t("settings.prepare_only.hint"), command=self.save_settings)
        flow.switch_row(t("settings.copy_builder"), self.var_copy_builder,
                        t("settings.copy_builder.hint"), command=self.save_settings)
        flow.switch_row(t("settings.pass_workdir"), self.var_pass_workdir,
                        t("settings.pass_workdir.hint"), command=self.save_settings)
        flow.switch_row(t("settings.keep_staging"), self.var_keep_staging,
                        t("settings.keep_staging.hint"), command=self.save_settings)

        target = group(t("settings.group.target"))
        row = target.row()
        ui.PathRow(row, t("settings.output"), self.var_cfg_outdir,
                   lambda: self._pick_dir(self.var_cfg_outdir, t("dlg.output")),
                   browse_text=t("word.choose"),
                   hint=t("settings.output.hint")).pack(fill=tk.X)
        holder = target.row()
        ui.LabeledEntry(holder, t("settings.name_template"), self.var_template).pack(fill=tk.X)
        tokens = tk.Label(holder, text=t("settings.name_template.hint",
                                         tokens=NAME_TOKENS),
                          bg=ui.CARD, fg=ui.TEXT_FAINT, font=ui.f("small"),
                          anchor="w", justify="left")
        tokens.pack(fill=tk.X, pady=(ui.px(6), 0))
        ui.wrap_to_parent(tokens)
        target.switch_row(t("settings.open_after"), self.var_open_after,
                          command=self.save_settings)

    def bind_settings_summary(self, variable):
        self.var_settings_summary = variable
        variable.set(t("settings.saved"))

    # ── which step is where ─────────────────────────────────────────────────
    def _paint_steps(self, outcome=None, report=None):
        """Set the four rings from what is actually known right now."""
        tuned = self.var_tuned.get().strip()
        has_file = bool(tuned) and os.path.isfile(tuned)
        found = all(self._resolved(key) for key in ("stock", "xdf", "toolkey"))
        vin_ok = validate_vin(self.var_vin.get())[0]
        # A missing VIN is step 3's business, not step 2's, so it is taken out
        # of the pre-flight before the ring is painted.
        blocking = [i for i in (report.errors if report else []) if i.topic != "vin"]
        checked = report is not None and not blocking

        self.step_file.set_state("done" if has_file else "now")
        if not has_file:
            self.step_check.set_state("next")
        elif blocking:
            self.step_check.set_state("err")
        elif checked and found:
            self.step_check.set_state("done")
        else:
            self.step_check.set_state("now")
        if not has_file or self.step_check.state in ("next", "err"):
            self.step_vin.set_state("next")
        else:
            self.step_vin.set_state("done" if vin_ok else "now")
        ready = (self.step_check.state == "done" and self.step_vin.state == "done"
                 and report is not None and report.ok)
        if outcome == "ok":
            self.step_run.set_state("done")
        elif outcome == "err":
            self.step_run.set_state("err")
        else:
            self.step_run.set_state("now" if ready else "next")

    def _resolved(self, key):
        path = getattr(self, f"var_{key}").get().strip()
        return bool(path) and os.path.isfile(path)

    def _on_vin_typed(self):
        """A VIN is upper case and has no spaces, the file name must match exactly."""
        raw = self.var_vin.get()
        clean = normalise_vin(raw)
        if clean != raw:
            self.var_vin.set(clean)   # re-enters once, then raw == clean
            return
        if not self._setting_vin:
            self._vin_auto = False    # typed by hand: the app stops correcting it
        # The VIN changes no byte of the diff, so nothing is read and nothing
        # is scheduled: the verdict is redrawn from the scan that is already in
        # hand, here and now.
        self._save_later()
        self._recheck()

    # ── automatic resolution ────────────────────────────────────────────────
    def _pick_tuned(self):
        path = filedialog.askopenfilename(
            title=t("dlg.tuned"),
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
                    self.var_vin.set(vin)   # the customer read carries the VIN
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

    def _mark(self, key, ok, detail=""):
        chip = self.res_tags.get(key)
        if chip is None:
            return
        fg, bg = (ui.OK, ui.OK_BG) if ok else (ui.TEXT_DIM, ui.HOVER)
        chip.set_text(("\u2713  " if ok else "") + t(f"lock.step2.{key}")
                      + (f"  {detail}" if detail else ""))
        chip.set_fill(bg, fg)

    def _resolve_and_check(self, force=False):
        """Derive every companion file from the tuned ROM, then run the checks."""
        self._cancel_preflight()
        if self._running:
            return
        self._update_setup_hint()

        tuned = self.var_tuned.get().strip()
        if not tuned or not os.path.isfile(tuned):
            for key in ("stock", "xdf", "toolkey"):
                self._mark(key, False)
            self._mark("builder", bool(self.config_data.get("builder_exe")
                                       and os.path.isfile(self.config_data["builder_exe"])))
            self.row_tuned.hint.configure(text=t("lock.step1.hint"), fg=ui.TEXT_FAINT)
            self.var_summary.set(t("status.waiting_file"))
            self.step_check.set_note("")
            self._paint_steps()
            return

        size = os.path.getsize(tuned)
        when = datetime.datetime.fromtimestamp(os.path.getmtime(tuned))
        self.row_tuned.hint.configure(
            text=t("lock.step1.size", size=human_size(size), when=f"{when:%d.%m.%Y %H:%M}"),
            fg=ui.OK)

        try:
            found = resolve_inputs(tuned, self.config_data.get("library_dir", ""),
                                   self.config_data.get("toolkey", ""))
        except OSError as exc:
            self._show_log()
            self.log.set_text(str(exc), "error")
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
            self.step_file.set_note(f"ROM {found.rom_id}")
        for key in ("stock", "xdf", "toolkey"):
            path = getattr(self, f"var_{key}").get().strip()
            self._mark(key, bool(path) and os.path.isfile(path),
                       os.path.basename(path) if key == "xdf" and path else "")
        exe = self.config_data.get("builder_exe", "")
        self._mark("builder", bool(exe) and os.path.isfile(exe))

        missing = [k for k in ("stock", "xdf", "toolkey") if not self._resolved(k)]
        self.manual.set_title(t("lock.step2.manual") +
                              (f"  ({len(missing)} {t('word.missing')})" if missing else ""))
        for note in found.notes:
            self._show_log()
            self.log.write(f" ! {note}", "warn")
        self._run_preflight()

    def _update_setup_hint(self):
        """The setup card only exists while something global is still missing."""
        problems = missing_setup(self.config_data, self.var_toolkey.get())
        if problems:
            self.setup_msg.config(text=t("setup.body", what=", ".join(
                t(f"setup.what.{key}") for key in problems)))
            if not self.setup_card.winfo_manager():
                self.setup_card.pack(fill=tk.X, pady=(0, ui.px(18)),
                                     before=self.flow)
        elif self.setup_card.winfo_manager():
            self.setup_card.pack_forget()

    # ── The check ───────────────────────────────────────────────────────────
    # It has two halves and they cost wildly different amounts. What the files
    # decide (read 16 MB, diff them, search both for ids, map them onto the
    # XDF) is about a second on a real S58 job. What you type decides (is the
    # VIN 17 characters, does the output folder exist) is a few microseconds.
    #
    # Until 3.0.0 both ran together, in the window, 350 ms after every
    # keystroke in the VIN field. That is the hanging. Now the expensive half
    # runs on a worker and its answer is kept for as long as the three files
    # are untouched, and typing only ever runs the cheap half.

    def _cancel_scan(self):
        if self._scan_after:
            try:
                self.app.after_cancel(self._scan_after)
            except tk.TclError:
                pass
            self._scan_after = None

    _cancel_preflight = _cancel_scan      # the old name, still called from _busy

    def _schedule_scan(self, delay=250):
        """The files changed: throw the old answer away and get a new one."""
        self._cancel_scan()
        self._scan = None
        if self._running:
            return
        if delay <= 0:
            self._start_scan()
        else:
            self._scan_after = self.app.after(delay, self._start_scan)

    def _schedule_preflight(self):
        """Kept under its old name: something the files decide has changed."""
        self._save_later()
        self._schedule_scan()

    def _on_sources_changed(self):
        """Tool key or library folder: the search finds something else now."""
        self._save_later()
        self._schedule_scan()

    def _file_snapshot(self, tuned):
        """Everything the worker needs, read here so it touches no tk variable."""
        return {
            "tuned": tuned,
            "library": self.config_data.get("library_dir", ""),
            "toolkey": self.config_data.get("toolkey", ""),
            "manual": {key: getattr(self, f"var_{key}").get().strip()
                       for key in ("stock", "xdf", "toolkey") if key in self._manual},
            "vin": normalise_vin(self.var_vin.get()),
            "customer": self.var_customer.get().strip(),
            "output_dir": (self.config_data.get("output_dir", "").strip()
                           or os.path.dirname(tuned)),
        }

    def _no_file(self):
        """Nothing picked: grey marks, no verdict, no work."""
        self._scan = None
        self._paint_marks()
        self.row_tuned.hint.configure(text=t("lock.step1.hint"), fg=ui.TEXT_FAINT)
        self.var_summary.set(t("status.waiting_file"))
        self.step_file.set_note("")
        self.step_check.set_note("")
        self._paint_steps()

    def _show_file(self, tuned):
        size = os.path.getsize(tuned)
        when = datetime.datetime.fromtimestamp(os.path.getmtime(tuned))
        self.row_tuned.hint.configure(
            text=t("lock.step1.size", size=human_size(size),
                   when=f"{when:%d.%m.%Y %H:%M}"), fg=ui.OK)

    def _start_scan(self):
        """Hand the expensive half to a worker and say so in step 2."""
        self._scan_after = None
        if self._running:
            return
        self._update_setup_hint()
        tuned = self.var_tuned.get().strip()
        if not tuned or not os.path.isfile(tuned):
            self._no_file()
            return
        self._show_file(tuned)
        self._scan_generation += 1
        self.step_file.set_state("done")
        self.step_check.set_state("now")
        self.step_check.set_note(t("lock.step2.checking"))
        self.app.set_status(t("status.checking"), "busy")
        self._scan_thread = threading.Thread(
            target=self._scan_worker,
            args=(self._scan_generation, self._file_snapshot(tuned)), daemon=True)
        self._scan_thread.start()

    def _scan_worker(self, generation, snapshot):
        """Off the window. Touches no widget and no tk variable, only the
        snapshot it was handed."""
        try:
            found = resolve_inputs(snapshot["tuned"], snapshot["library"],
                                   snapshot["toolkey"])
            job = self._job_from(snapshot, found)
            scan = scan_files(job, definition_for(job.xdf))
        except Exception as exc:                       # never take the app down
            self._post("scan", generation=generation, error=str(exc))
            return
        self._post("scan", generation=generation, found=found, scan=scan)

    @staticmethod
    def _job_from(snapshot, found) -> LockJob:
        manual = snapshot["manual"]
        return LockJob(
            customer=snapshot["customer"], vin=snapshot["vin"],
            stock_bin=manual.get("stock") or found.stock,
            tuned_bin=snapshot["tuned"],
            xdf=manual.get("xdf") or found.xdf,
            toolkey=manual.get("toolkey") or found.toolkey,
            output_dir=snapshot["output_dir"])

    def _on_event_scan(self, generation, found=None, scan=None, error=""):
        if generation != self._scan_generation:
            return                                      # a newer answer is coming
        if error:
            self._show_log()
            self.log.set_text(error, "error")
            self.step_check.set_state("err")
            self.app.set_status(t("word.failed"), "error")
            return
        self._apply_resolution(found)
        self._scan = scan
        self._recheck()

    def _apply_resolution(self, found):
        for key in ("stock", "xdf", "toolkey"):
            if key not in self._manual:
                getattr(self, f"var_{key}").set(getattr(found, key))
        # A resolved VIN fills an empty field and corrects an earlier resolved one;
        # a VIN typed by hand is left alone (the check warns if it disagrees).
        if found.vin and (self._vin_auto or not self.var_vin.get().strip()):
            if found.vin != self.var_vin.get():
                self._set_vin(found.vin)
            self._vin_auto = True
        if found.rom_id:
            self.step_file.set_note(f"ROM {found.rom_id}")
        self._paint_marks()
        for note in found.notes:
            self._show_log()
            self.log.write(f" ! {note}", "warn")

    def _paint_marks(self):
        """The four chips in step 2, from what is resolved right now."""
        for key in ("stock", "xdf", "toolkey"):
            path = getattr(self, f"var_{key}").get().strip()
            self._mark(key, bool(path) and os.path.isfile(path),
                       os.path.basename(path) if key == "xdf" and path else "")
        exe = self.config_data.get("builder_exe", "")
        self._mark("builder", bool(exe) and os.path.isfile(exe))
        missing = [k for k in ("stock", "xdf", "toolkey") if not self._resolved(k)]
        self.manual.set_title(t("lock.step2.manual") +
                              (f"  ({len(missing)} {t('word.missing')})" if missing else ""))

    def _recheck(self):
        """The cheap half. Reads no file, so it is safe on every keystroke."""
        job = self._current_job()
        ok_vin, _vin, vin_msg = validate_vin(job.vin)
        self.lbl_vin.config(text=("\u2713  " if ok_vin else "\u2715  ") + vin_msg,
                            fg=ui.OK if ok_vin else (ui.TEXT_FAINT if not job.vin else ui.ERR))
        if self._scan is not None and self._scan.matches(job):
            report = preflight(job, scan=self._scan)
            self._render_preflight(report, job)
            return report
        if not (job.tuned_bin and os.path.isfile(job.tuned_bin)):
            self.var_summary.set(t("status.waiting_file"))
        else:
            self.var_summary.set(t("lock.step2.idle"))
        self._paint_steps()
        return None

    def check_now(self):
        """Resolve and check right here, on this thread.

        The window never calls this, it would hang. Re-check and the tests do,
        because they want the answer before the next line runs.
        """
        self._cancel_scan()
        if self._running:
            return None
        self._update_setup_hint()
        tuned = self.var_tuned.get().strip()
        if not tuned or not os.path.isfile(tuned):
            self._no_file()
            return None
        self._show_file(tuned)
        self._scan_generation += 1
        snapshot = self._file_snapshot(tuned)
        try:
            found = resolve_inputs(tuned, snapshot["library"], snapshot["toolkey"])
        except OSError as exc:
            self._show_log()
            self.log.set_text(str(exc), "error")
            return None
        self._apply_resolution(found)
        job = self._current_job()
        self._scan = scan_files(job, definition_for(job.xdf))
        return self._recheck()

    def _resolve_and_check(self, force=False):
        """The old name of check_now. Still used by Re-check and the tests."""
        return self.check_now()

    def _run_preflight(self):
        return self._recheck()

    def _render_preflight(self, report: Preflight, job: LockJob):
        self._show_log()
        # Built as a list and written in one call. As sixty separate writes this
        # cost a tenth of a second, and it happens on every keystroke.
        lines = [("PRE-FLIGHT CHECKS", "dim"), ("\u2500" * 62, "dim")]
        for issue in report.issues:
            # The VIN has its own line under its own field in step 3. Leaving it
            # out here is not only tidier: it is what makes the log identical
            # from one keystroke to the next, so it is not rewritten at all.
            if issue.topic == "vin":
                continue
            tag = {"error": "error", "warn": "warn"}.get(issue.level, "info")
            mark = {"error": "\u2715", "warn": "!", "info": "\u00b7"}[issue.level]
            lines.append((f" {mark} {issue.text}", tag))
        if report.regions:
            lines.append(("", None))
            lines.append((f"MODIFIED REGIONS ({len(report.regions)})", "dim"))
            lines.append(("\u2500" * 62, "dim"))
            # The names came with the scan, so nothing here reopens the XDF.
            tables = report.region_tables or [[] for _ in report.regions]
            for index, (start, length) in enumerate(report.regions[:25]):
                names = tables[index] if index < len(tables) else []
                label = ", ".join(names[:2]) if names else "not in this XDF"
                lines.append((f"  0x{start:07X}  {length:>6,} B   {label[:64]}",
                              "accent" if names else "warn"))
            if len(report.regions) > 25:
                lines.append((f"  \u2026 and {len(report.regions) - 25} more region(s)",
                              "dim"))
        if report.touched_tables:
            lines.append(("", None))
            lines.append((f"TABLES TOUCHED ({len(report.touched_tables)})", "dim"))
            lines.append(("\u2500" * 62, "dim"))
            for name in report.touched_tables[:20]:
                lines.append((f"  \u00b7 {name[:70]}", None))
            if len(report.touched_tables) > 20:
                lines.append((f"  \u2026 and {len(report.touched_tables) - 20} more", "dim"))
        # Only the log is skipped when the files still say the same thing. The
        # verdict below it is redrawn every time, because the VIN is part of it.
        signature = tuple(lines)
        if signature != self._log_signature:
            self._log_signature = signature
            self.log.set_all(lines)

        if report.ok:
            note = t("lock.step2.note", bytes=f"{report.changed_bytes:,}".replace(",", "."),
                     tables=len(report.touched_tables))
            self.step_check.set_note(note)
            self.var_summary.set(note)
            self.app.set_status(t("status.ready_prepare")
                                if self.config_data.get("prepare_only", False)
                                else t("status.ready"), "ok")
        else:
            blocking = [i for i in report.errors if i.topic != "vin"]
            first = (blocking or report.errors)[0].text
            self.step_check.set_note(first[:70] if blocking else "", "error")
            self.var_summary.set(first)
            self.app.set_status(t("status.blocked"), "error")
        self._paint_steps(report=report)
        return report

    # ── Settings plumbing ───────────────────────────────────────────────────
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
            "language": self.config_data.get("language", DEFAULT_CONFIG["language"]),
        }

    def _save_later(self, delay=600):
        """Write the settings once the typing stops, not once per keystroke."""
        if self._save_after:
            try:
                self.app.after_cancel(self._save_after)
            except tk.TclError:
                pass
        self._save_after = self.app.after(delay, self.save_settings)

    def save_settings(self):
        if self._save_after:
            try:
                self.app.after_cancel(self._save_after)
            except tk.TclError:
                pass
            self._save_after = None
        collected = self._collect_settings()
        if collected == self.config_data:
            # Nothing actually changed. Typing a VIN reaches here every time
            # through the debounce, and writing the file plus refreshing the
            # buttons for no reason is a visible pause a second after you stop.
            return
        self.config_data.update(collected)
        self.app.config_data = self.config_data
        ok = save_config(self.config_data)
        self.var_settings_summary.set(t("settings.saved") if ok
                                      else t("settings.save_failed"))
        if hasattr(self, "setup_card"):
            self._update_setup_hint()
        self._apply_prepare_mode()

    def reset_settings(self):
        self.config_data.clear()
        self.config_data.update(DEFAULT_CONFIG)
        save_config(self.config_data)
        self._restore_settings()
        self._update_setup_hint()
        self._apply_prepare_mode()
        self.app.set_status(t("settings.saved"), "info")

    def _apply_prepare_mode(self):
        """Folder mode moves the weight from locking to preparing.

        The lock button is withdrawn rather than greyed out: a disabled control
        invites people to look for what would enable it, and here nothing would.
        """
        if not hasattr(self, "btn_stage"):
            return
        prepare = bool(self.config_data.get("prepare_only", False))
        self.btn_stage.set_variant("primary" if prepare else "secondary")
        self.btn_stage.configure(text=t("lock.btn.prepare_main") if prepare
                                 else t("lock.btn.prepare"))
        # winfo_ismapped() cannot answer "is this button packed?" for a page
        # that is not on top; winfo_manager can.
        packed = bool(self.btn_lock.winfo_manager())
        if prepare and packed:
            self.btn_lock.pack_forget()
            self.btn_stage.pack_configure(padx=0)
        elif not prepare and not packed:
            self.btn_lock.pack(side=tk.RIGHT)
            self.btn_stage.pack_forget()
            self.btn_stage.pack(side=tk.RIGHT, padx=(0, ui.px(10)))
        if hasattr(self, "btn_batch_run"):
            self.btn_batch_run.configure(text=t("batch.btn.prepare") if prepare
                                         else t("batch.btn.run"))
        if hasattr(self, "lbl_run"):
            self.lbl_run.configure(text=t("lock.step4.hint_prepare") if prepare
                                   else t("lock.step4.hint"))
        self.step_run.set_title(t("lock.step4"))
        shell = self.app.shell
        shell.set_subtitle("lock", t("lock.sub_prepare") if prepare else t("lock.sub"))
        shell.set_subtitle("batch", t("batch.sub_prepare") if prepare else t("batch.sub"))

    # ── Input helpers ───────────────────────────────────────────────────────
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
        """The parsed XDF. Shared with the worker, so it is normally already
        there by the time the window asks."""
        return definition_for(path)

    # ── Running ─────────────────────────────────────────────────────────────
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
        self.app.set_status(t("status.stopped"), "warn")

    def _on_lock(self):
        job = self._current_job()
        report = preflight(job, self._definition(job.xdf), scan=self._scan)
        self._render_preflight(report, job)
        if not report.ok:
            self.lock_page.banner.show("error", t("status.blocked"))
            return
        exe = self.config_data.get("builder_exe", "")
        if not exe or not os.path.isfile(exe):
            self.lock_page.banner.show("error", t("setup.body",
                                                  what=t("setup.what.builder")),
                                       action_text=t("setup.open"),
                                       action=lambda: self.app.go("settings"))
            return
        self.lock_page.banner.show("busy", t("status.locking"))
        self.step_run.set_state("now")
        self._start([job], target="lock")

    def _save_log(self):
        """Write the panel text to a file, so a failed run can be handed on.

        A failed lock leaves no .log next to an output, because there is no
        output. Without this the only way to pass on what the builder said is a
        photograph of the screen.
        """
        text_body = self.log.text.get("1.0", tk.END).rstrip()
        if not text_body:
            self.lock_page.banner.show("info", t("log.empty"))
            return
        job = self._current_job()
        stem = safe_name(job.label, "mhd") or "mhd"
        target = filedialog.asksaveasfilename(
            title=t("dlg.save_log"), defaultextension=".log",
            initialfile=f"{stem}_{datetime.datetime.now():%Y%m%d_%H%M}.log",
            initialdir=job.output_dir or None,
            filetypes=[("Log file", "*.log"), ("All files", "*.*")])
        if not target:
            return
        try:
            with open(target, "w", encoding="utf-8") as handle:
                handle.write(f"{APP_NAME} v{APP_VERSION} \u00b7 {brand.VENDOR}\n")
                handle.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
                handle.write(f"Tuned    : {job.tuned_bin}\n")
                handle.write(f"Stock    : {job.stock_bin}\n")
                handle.write(f"XDF      : {job.xdf}\n")
                handle.write(f"Tool key : {job.toolkey}\n")
                handle.write(f"VIN      : {job.vin}\n")
                handle.write(f"Builder  : {self.config_data.get('builder_exe', '')}\n\n")
                handle.write(text_body + "\n")
        except OSError as exc:
            self.lock_page.banner.show("error", str(exc))
            return
        self.lock_page.banner.show("ok", t("banner.log_saved",
                                           name=os.path.basename(target)),
                                   action_text=t("word.open_folder"),
                                   action=lambda: ui.reveal_in_file_manager(target))

    def _on_stage_only(self):
        """Build the working folder without running anything, for a manual run."""
        job = self._current_job()
        report = preflight(job, self._definition(job.xdf), scan=self._scan)
        self._render_preflight(report, job)
        if not report.ok:
            self.lock_page.banner.show("error", t("status.blocked"))
            return
        try:
            manifest = prepare_folder(job, self.config_data)
        except OSError as exc:
            self.lock_page.banner.show("error", str(exc))
            return
        workdir = manifest["workdir"]
        self._show_log()
        self.log.write("")
        self.log.write(f"{t('log.folder')}: {workdir}", "ok")
        for key in ("stock", "tuned", "xdf", "toolkey", "vin_file"):
            self.log.write(f"    {manifest[key]}", "dim")
        if manifest["builder"]:
            self.log.write(f"    {os.path.basename(manifest['builder'])}", "dim")
        self.lock_page.banner.show("ok", t("banner.prepared"),
                                   action_text=t("word.open_folder"),
                                   action=lambda: ui.reveal_in_file_manager(workdir))
        self._last_output = workdir
        self.step_run.set_state("done")
        self.step_run.set_note(os.path.basename(workdir))
        self.app.set_status(t("word.done"), "ok")

    def _on_batch_run(self):
        if not self.batch_jobs:
            self.batch_page.banner.show("error", t("err.no_jobs"))
            return
        prepare = bool(self.config_data.get("prepare_only", False))
        exe = self.config_data.get("builder_exe", "")
        if not prepare and (not exe or not os.path.isfile(exe)):
            self.batch_page.banner.show("error", t("setup.body",
                                                   what=t("setup.what.builder")),
                                        action_text=t("setup.open"),
                                        action=lambda: self.app.go("settings"))
            return
        self.batch_log.clear()
        for index in range(len(self.batch_jobs)):
            self.batch_table.update_row(str(index), tag="dim")
            self._set_batch_cell(index, status=t("word.queued"), output="")
        self.batch_page.banner.show("busy", t("status.locking"))
        self.step_batch_run.set_state("now")
        self._start(list(self.batch_jobs), target="batch", prepare_only=prepare)

    def _start(self, jobs, target, prepare_only=False):
        if self._worker and self._worker.is_alive():
            return
        self._stop_event = threading.Event()
        self._busy(True)
        self.app.set_status(t("status.preparing") if prepare_only
                            else t("status.locking"), "busy")
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
                    target=os.path.join(workdir, manifest["tuned"]),
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
        self._drain_id = self.app.after(60, self._drain_events)

    def _on_event_log(self, target, line, tag):
        if target == "batch":
            self.batch_log.write(line, tag, follow=True)
        else:
            self._show_log()
            self.log.write(line, tag, follow=True)

    def _on_event_job(self, index, status, output="", tag=None):
        if str(index) in self.batch_table.tree.get_children():
            self._set_batch_cell(index, status=t(f"word.{status}")
                                 if f"word.{status}" in STATUS_KEYS else status,
                                 output=output)
            self.batch_table.update_row(str(index), tag=tag or "dim")

    def _on_event_result(self, target, path):
        self._last_output = path

    def _on_event_done(self, target, successes, failures, total, prepared=False):
        self._busy(False)
        page = self.batch_page if target == "batch" else self.lock_page
        key = "banner.batch_prepared" if prepared else "banner.batch_done"
        if failures == 0 and successes:
            tone = "ok"
            if target == "batch" or total > 1:
                message = t(key, ok=successes, failed=failures, total=total)
            elif prepared:
                message = t("banner.prepared")
            else:
                message = t("banner.locked", vin=self.var_vin.get() or "?")
        elif successes:
            tone = "warn"
            message = t(key, ok=successes, failed=failures, total=total)
        else:
            tone = "error"
            message = t("banner.nothing")
        last = self._last_output
        if tone == "ok" and last:
            page.banner.show(tone, message, action_text=t("word.open_folder"),
                             action=lambda p=last: ui.reveal_in_file_manager(p))
            if prepared or self.config_data.get("open_after_success"):
                ui.reveal_in_file_manager(last)
        else:
            page.banner.show(tone, message)
            # The message says the log has it, so put the log in front of them.
            if target != "batch":
                self._show_log()
        self.app.set_status(message if len(message) < 60 else t("word.done"), tone)
        if target == "batch":
            self.var_batch_summary.set(t(key, ok=successes, failed=failures,
                                         total=total))
            self.step_batch_run.set_state("done" if tone == "ok" else "err")
            self.step_batch_run.set_note(t("batch.step3.progress", done=successes,
                                           total=total))
        else:
            self.step_run.set_state("done" if tone == "ok" else "err")
            if tone == "ok" and last:
                self.step_run.set_note(os.path.basename(last))
                self.step_run.set_title(t("lock.step4.done") if not prepared
                                        else t("lock.step4"))

    # ── Batch plumbing ──────────────────────────────────────────────────────
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
            self.batch_table.add([job.customer, job.vin,
                                  os.path.basename(job.tuned_bin),
                                  t("word.queued"), ""], iid=str(index), tag="dim")
        count = len(self.batch_jobs)
        self.var_batch_summary.set(t("batch.step1.empty") if not count
                                   else t("batch.step1.count", n=count))
        self.step_files.set_note(t("batch.step1.count", n=count) if count else "")
        self.step_files.set_state("done" if count else "now")
        self._batch_marks()

    def _batch_marks(self):
        for child in self.batch_marks.winfo_children():
            child.destroy()
        count = len(self.batch_jobs)
        if not count:
            self.step_batch_check.set_state("next")
            self.step_batch_run.set_state("next")
            self.lbl_batch_check.configure(text=t("batch.step2.idle"))
            return
        bad = self._batch_counts.get("unresolved", 0) + self._batch_counts.get("no_vin", 0)
        ready = max(0, count - bad)
        chip = ui.tag(self.batch_marks, f"{ready} {t('word.ready').lower()}",
                      "ok" if ready else "idle", bg=ui.BG)
        chip.pack(side=tk.LEFT, padx=(0, ui.px(7)))
        if bad:
            chip = ui.tag(self.batch_marks, f"{bad} {t('word.missing')}", "error",
                          bg=ui.BG)
            chip.pack(side=tk.LEFT, padx=(0, ui.px(7)))
        self.lbl_batch_check.configure(text="")
        self.step_batch_check.set_state("done" if not bad else "err")
        self.step_batch_run.set_state("now" if ready else "next")

    def _batch_add_files(self):
        paths = filedialog.askopenfilenames(
            title=t("dlg.batch_files"),
            filetypes=[("ROM image", "*.bin"), ("All files", "*.*")])
        if not paths:
            return
        # Every file gets its own stock ROM and XDF looked up, and that means
        # reading it. Twenty files used to be twenty freezes of the window.
        self.step_files.set_state("now")
        self.step_files.set_note(t("lock.step2.checking"))
        self.app.set_status(t("status.checking"), "busy")
        snapshot = {"library": self.config_data.get("library_dir", ""),
                    "toolkey": self.config_data.get("toolkey", ""),
                    "base": self._current_job()}
        self._queue_thread = threading.Thread(
            target=self._queue_worker, args=(list(paths), snapshot), daemon=True)
        self._queue_thread.start()

    def _queue_worker(self, paths, snapshot):
        """Off the window. Builds jobs out of plain values, touches no widget."""
        base = snapshot["base"]
        jobs, unresolved, inherited = [], 0, 0
        for path in paths:
            try:
                found = resolve_inputs(path, snapshot["library"], snapshot["toolkey"])
            except Exception:
                unresolved += 1
                continue
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
            jobs.append(job)
        self._post("queued", jobs=jobs, added=len(paths), unresolved=unresolved,
                   inherited=inherited, base_vin=base.vin)

    def _on_event_queued(self, jobs, added, unresolved, inherited, base_vin):
        self.batch_jobs.extend(jobs)
        missing_vin = [j for j in self.batch_jobs if not validate_vin(j.vin)[0]]
        self._batch_counts = {"total": len(self.batch_jobs),
                              "unresolved": unresolved,
                              "no_vin": len(missing_vin)}
        self._batch_refresh()
        self.batch_log.write(f"+ {added}", "ok", follow=True)
        if unresolved:
            self.batch_log.write(f" ! {unresolved} without a stock ROM or XDF",
                                 "warn", follow=True)
        if inherited:
            # one VIN across several cars locks them all to the first one
            self.batch_log.write(f" ! {inherited} carry no VIN of their own and took "
                                 f"{base_vin} from the Lock page", "warn", follow=True)
        if missing_vin:
            self.batch_log.write(f" ! {len(missing_vin)} still need a VIN",
                                 "warn", follow=True)
        self.app.set_status(t("word.ready"), "ok")

    def _batch_import_csv(self):
        path = filedialog.askopenfilename(title=t("dlg.csv"),
                                          filetypes=[("CSV", "*.csv"),
                                                     ("All files", "*.*")])
        if not path:
            return
        try:
            jobs, problems = read_batch_csv(path, self._current_job())
        except OSError as exc:
            self.batch_page.banner.show("error", str(exc))
            return
        self.batch_jobs.extend(jobs)
        self._batch_counts["total"] = len(self.batch_jobs)
        self._batch_refresh()
        self.batch_log.write(f"+ {len(jobs)} ({os.path.basename(path)})", "ok",
                             follow=True)
        for problem in problems:
            self.batch_log.write(f"  {problem}", "warn", follow=True)

    def _batch_export(self):
        if not self.batch_jobs:
            self.batch_page.banner.show("error", t("err.no_jobs"))
            return
        path = filedialog.asksaveasfilename(title=t("dlg.report"),
                                            defaultextension=".csv",
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
        self.batch_page.banner.show("ok", t("banner.log_saved",
                                            name=os.path.basename(path)),
                                    action_text=t("word.open_folder"),
                                    action=lambda: ui.reveal_in_file_manager(path))

    def _batch_remove(self):
        selected = sorted((int(iid) for iid in self.batch_table.selection()),
                          reverse=True)
        for index in selected:
            if 0 <= index < len(self.batch_jobs):
                self.batch_jobs.pop(index)
        self._batch_refresh()

    def _batch_clear(self):
        self.batch_jobs.clear()
        self._batch_counts = {"total": 0, "unresolved": 0, "no_vin": 0}
        self._batch_refresh()

    def _batch_selected_index(self):
        selection = self.batch_table.selection()
        return int(selection[0]) if selection else None

    def _batch_load_selected(self):
        index = self._batch_selected_index()
        if index is None or index >= len(self.batch_jobs):
            self.lbl_batch_file.config(text=t("batch.selected"))
            return
        job = self.batch_jobs[index]
        self.var_b_customer.set(job.customer)
        self.var_b_vin.set(job.vin)
        self.lbl_batch_file.config(text=os.path.basename(job.tuned_bin))

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
        self._batch_counts["no_vin"] = 0
        self._batch_marks()


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    """The Lock area of the one app. Kept so the Start menu entry still works."""
    import dme_app
    return dme_app.main("lock")


if __name__ == "__main__":
    sys.exit(main())
