"""
MHD Lock Tool — DME Innovation
==============================

Automates the tune-locking workflow described in the MHD+ Tuning Guide
("Locking Tune Files with MHD+ Features"): it stages a clean working directory
for the official MHD Map Encryption tool (TuningMapBuilder / XDF_Tools),
validates every input before the run, drives the tool, reads its console
output and files the resulting *.mhd away per customer.

The locking itself is done by the tuner's own licensed copy of the MHD tool —
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
        return False, value, "VIN is required — the builder needs a <VIN>_vin.txt file."
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
    Minimal TunerPro XDF reader — enough to know which byte ranges the
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
    """Check everything the builder would choke on — before spending a run."""
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
                report.add("error", "Stock and tuned .bin are identical — "
                                    "the builder would report 'NO modifications found'.")
            else:
                report.add("info", f"{report.changed_bytes:,} byte(s) changed in "
                                   f"{len(report.regions)} region(s).")

        report.stock_ids = detect_rom_ids(stock)
        report.tuned_ids = detect_rom_ids(tuned)
        shared_ids = set(report.stock_ids) & set(report.tuned_ids)
        if report.stock_ids and report.tuned_ids and not shared_ids:
            report.add("warn", "No common software id found in stock and tuned image — "
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
        report.add("info", f"XDF '{definition.title}' — {definition.table_count} table(s).")
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
                           f"definitions, so this is not necessarily a problem — but if it "
                           f"reports 'Modification not in xdf', these are the offsets.")
            else:
                report.add("info", f"All modifications are covered by the XDF "
                                   f"({len(report.touched_tables)} table(s) touched).")
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Staging — a clean directory the builder cannot misread
# ─────────────────────────────────────────────────────────────────────────────
def stock_staged_name(path: str) -> str:
    stem = os.path.splitext(os.path.basename(path))[0]
    for suffix in ("_original", "_orig", "_stock", "_stk"):
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


# ─────────────────────────────────────────────────────────────────────────────
# Running the builder
# ─────────────────────────────────────────────────────────────────────────────
def classify_line(line: str) -> str:
    text = line.strip()
    if not text:
        return ""
    if any(marker in text for marker in SUCCESS_MARKERS):
        return "ok"
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

    The exit code is unreliable — the tool ends on a `Press a key…` prompt and
    can fault there after a perfectly good run — so success is decided by the
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
        result.launch_error = ("MHD map builder not configured — set the path to "
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
    try:
        process = subprocess.Popen(
            command, cwd=workdir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, encoding="utf-8",
            errors="replace", bufsize=1, **kwargs)
    except OSError as exc:
        result = RunResult()
        result.launch_error = f"Could not start the builder: {exc}"
        return result

    timer = threading.Timer(timeout, process.kill)
    timer.daemon = True
    timer.start()
    try:
        try:  # the builder ends on "Press a key…" — feed it one
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
    result.timed_out = not timer.is_alive() and process.returncode not in (0, None) and False
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
    "output_dir": "",
    "name_template": "{source}",
    "keep_staging": False,
    "open_after_success": True,
    "timeout": 600,
    "last_stock": "",
    "last_xdf": "",
    "last_toolkey": "",
    "last_customer": "",
}


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
    """Read customer,vin,tuned_bin[,stock_bin][,xdf] — header optional."""
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
            problems.append(f"Row {number}: no tuned .bin given — skipped.")
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
        self.title(f"{APP_NAME} — {brand.VENDOR}")
        self.configure(bg=ui.BG)
        self.minsize(960, 700)
        ui.init(self)
        brand.apply_window_icon(self)

        self.config_data = load_config()
        self.batch_jobs: list[LockJob] = []
        self._events: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None
        self._running = False
        self._stop_event = threading.Event()
        self._preflight_after = None
        self._xdf_cache: tuple[str, float, XdfDefinition] | None = None

        self._build()
        self._restore_settings()
        self.after(120, self._drain_events)

    # ── Shell ────────────────────────────────────────────────────────────────

    def _build(self):
        ui.Header(self, brand, APP_NAME, APP_VERSION, APP_TAGLINE).pack(fill=tk.X)
        self.tabs = ui.TabBar(self, [("lock", "Lock"), ("batch", "Batch"),
                                     ("settings", "Settings")], self._show_page)
        self.tabs.pack(fill=tk.X)
        self.status = ui.StatusBar(self, f"{brand.VENDOR}  ·  {APP_NAME} v{APP_VERSION}")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)
        self._host = tk.Frame(self, bg=ui.BG)
        self._host.pack(fill=tk.BOTH, expand=True)
        self.pages = {"lock": self._build_lock_page(),
                      "batch": self._build_batch_page(),
                      "settings": self._build_settings_page()}
        self.tabs.select("lock")

    def _show_page(self, key):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[key].pack(fill=tk.BOTH, expand=True)

    # ── Lock page ────────────────────────────────────────────────────────────

    def _build_lock_page(self):
        page = ui.Page(self._host)
        self.lock_page = page
        page.intro("Prepares a clean working directory for the MHD map builder, checks every "
                   "input before the run, drives the builder and files the locked .mhd away. "
                   "The locking itself is done by your licensed MHD tool.")

        who = page.card("Customer & vehicle")
        row = tk.Frame(who.body, bg=ui.CARD)
        row.pack(fill=tk.X)
        self.var_customer = tk.StringVar()
        customer = ui.LabeledEntry(row, "Customer / job name", self.var_customer,
                                   mono=False, placeholder="Used for the output file name")
        customer.grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.var_vin = tk.StringVar()
        vin_cell = ui.LabeledEntry(row, "Customer VIN (17 characters)", self.var_vin,
                                   placeholder="The lock is bound to this VIN")
        vin_cell.grid(row=0, column=1, sticky="ew")
        row.grid_columnconfigure(0, weight=1, uniform="who")
        row.grid_columnconfigure(1, weight=1, uniform="who")
        self.lbl_vin = tk.Label(who.body, text="", bg=ui.CARD, fg=ui.TEXT_FAINT,
                                font=ui.f("small"), anchor="w")
        self.lbl_vin.pack(fill=tk.X, pady=(6, 0))

        files = page.card("Files")
        self.var_stock = tk.StringVar()
        self.row_stock = ui.PathRow(files.body, "Stock / original ROM (.bin)", self.var_stock,
                                    lambda: self._pick_file(self.var_stock, "Select the stock ROM",
                                                            [("ROM image", "*.bin *.org"),
                                                             ("All files", "*.*")]),
                                    tooltip="Staged as <name>_original.bin")
        self.row_stock.pack(fill=tk.X, pady=(0, 12))
        self.var_tuned = tk.StringVar()
        self.row_tuned = ui.PathRow(files.body, "Tuned ROM (.bin)", self.var_tuned,
                                    lambda: self._pick_file(self.var_tuned, "Select the tuned ROM",
                                                            [("ROM image", "*.bin"),
                                                             ("All files", "*.*")]),
                                    tooltip="The customer file that gets locked")
        self.row_tuned.pack(fill=tk.X, pady=(0, 12))
        self.var_xdf = tk.StringVar()
        self.row_xdf = ui.PathRow(files.body, "XDF definition (.xdf)", self.var_xdf,
                                  lambda: self._pick_file(self.var_xdf, "Select the XDF",
                                                          [("TunerPro XDF", "*.xdf"),
                                                           ("All files", "*.*")]),
                                  tooltip="Must contain the current MHD+ tables")
        self.row_xdf.pack(fill=tk.X, pady=(0, 12))
        self.var_toolkey = tk.StringVar()
        self.row_toolkey = ui.PathRow(files.body, "MHD tool key (.toolkey)", self.var_toolkey,
                                      lambda: self._pick_file(self.var_toolkey, "Select your .toolkey",
                                                              [("MHD tool key", "*.toolkey"),
                                                               ("All files", "*.*")]),
                                      tooltip="Your personal MHD key — never leaves this machine")
        self.row_toolkey.pack(fill=tk.X)

        out = page.card("Output")
        self.var_outdir = tk.StringVar()
        self.row_outdir = ui.PathRow(out.body, "Folder for the locked .mhd", self.var_outdir,
                                     lambda: self._pick_dir(self.var_outdir,
                                                            "Select the output folder"),
                                     browse_text="Choose…")
        self.row_outdir.pack(fill=tk.X)

        log_card = page.card("Checks & builder log", hint="")
        self.log_card = log_card
        self.log = ui.LogView(log_card.body, height=14)
        self.log.pack(fill=tk.BOTH, expand=True)
        tools = tk.Frame(log_card.body, bg=ui.CARD)
        tools.pack(fill=tk.X, pady=(10, 0))
        tk.Label(tools, text="Checks run automatically whenever an input changes.",
                 bg=ui.CARD, fg=ui.TEXT_FAINT, font=ui.f("small")).pack(side=tk.LEFT)
        ui.button(tools, "Clear", self.log.clear, variant="ghost", size="sm",
                  bg=ui.CARD).pack(side=tk.RIGHT)
        ui.button(tools, "Re-check  ⟳", lambda: self._run_preflight(force=True),
                  variant="secondary", size="sm").pack(side=tk.RIGHT, padx=(0, 8))
        self.log.set_text("Select the files above — the pre-flight checks start on their own.",
                          "dim")

        self.var_summary = tk.StringVar(value="Waiting for input")
        page.summary(self.var_summary)
        self.btn_lock = ui.button(page.action_row, "Lock now  🔒", self._on_lock,
                                  variant="primary", size="lg")
        self.btn_lock.pack(side=tk.RIGHT)
        self.btn_stage = ui.button(page.action_row, "Prepare folder only", self._on_stage_only,
                                   variant="secondary", size="lg")
        self.btn_stage.pack(side=tk.RIGHT, padx=(0, 10))

        for var in (self.var_customer, self.var_vin, self.var_stock, self.var_tuned,
                    self.var_xdf, self.var_toolkey, self.var_outdir):
            var.trace_add("write", lambda *_: self._schedule_preflight())
        return page

    # ── Batch page ───────────────────────────────────────────────────────────

    def _build_batch_page(self):
        page = ui.Page(self._host)
        self.batch_page = page
        page.intro("Lock a whole queue in one go. Every job is staged and run in its own clean "
                   "folder, so one bad file can never affect another customer. Stock ROM, XDF "
                   "and tool key come from the Lock tab unless a CSV row overrides them.")

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
        page.intro("The MHD map builder is not part of this tool — point it at your own "
                   "licensed copy (TuningMapBuilder / MHD Map Encryption). Settings are saved "
                   f"automatically to {config_path()}")

        builder = page.card("MHD map builder")
        self.var_exe = tk.StringVar()
        ui.PathRow(builder.body, "Path to the builder executable", self.var_exe,
                   lambda: self._pick_file(self.var_exe, "Select the MHD map builder",
                                           [("Programs", "*.exe"), ("All files", "*.*")]),
                   tooltip="e.g. TuningMapBuilder-v6.exe").pack(fill=tk.X, pady=(0, 12))
        opts = tk.Frame(builder.body, bg=ui.CARD)
        opts.pack(fill=tk.X)
        self.var_args = tk.StringVar()
        ui.LabeledEntry(opts, "Extra command line arguments (usually empty)",
                        self.var_args).grid(row=0, column=0, sticky="ew", padx=(0, 14))
        self.var_timeout = tk.StringVar()
        ui.LabeledEntry(opts, "Timeout per job (seconds)", self.var_timeout,
                        width=10).grid(row=0, column=1, sticky="ew")
        opts.grid_columnconfigure(0, weight=3)
        opts.grid_columnconfigure(1, weight=1)
        self.var_copy_builder = tk.BooleanVar()
        self.var_pass_workdir = tk.BooleanVar()
        self._checkbox(builder.body, "Copy the builder into the working folder and run it there",
                       self.var_copy_builder,
                       "Mirrors a hand-built folder — the builder always sees the right files.")
        self._checkbox(builder.body, "Pass the working folder as a command line argument",
                       self.var_pass_workdir,
                       "Only needed if your build of the tool expects a path argument.")

        output = page.card("Output")
        self.var_cfg_outdir = tk.StringVar()
        ui.PathRow(output.body, "Default output folder", self.var_cfg_outdir,
                   lambda: self._pick_dir(self.var_cfg_outdir, "Select the default output folder"),
                   browse_text="Choose…").pack(fill=tk.X, pady=(0, 12))
        self.var_template = tk.StringVar()
        ui.LabeledEntry(output.body, "File name template", self.var_template,
                        placeholder=NAME_TOKENS).pack(fill=tk.X)
        tk.Label(output.body, text=f"Tokens: {NAME_TOKENS}   ·   "
                                   "{source} keeps the name the builder produced",
                 bg=ui.CARD, fg=ui.TEXT_FAINT, font=ui.f("small"),
                 anchor="w").pack(fill=tk.X, pady=(6, 10))
        self.var_open_after = tk.BooleanVar()
        self._checkbox(output.body, "Open the output folder after a successful lock",
                       self.var_open_after)

        advanced = page.card("Advanced")
        self.var_keep_staging = tk.BooleanVar()
        self._checkbox(advanced.body, "Keep the temporary working folder after the run",
                       self.var_keep_staging,
                       "Useful when you want to inspect exactly what the builder saw.")
        actions = tk.Frame(advanced.body, bg=ui.CARD)
        actions.pack(fill=tk.X, pady=(10, 0))
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
            tk.Label(holder, text=hint, bg=ui.CARD, fg=ui.TEXT_FAINT, font=ui.f("small"),
                     anchor="w").pack(fill=tk.X, padx=(22, 0))
        return box

    # ── Settings plumbing ────────────────────────────────────────────────────

    def _restore_settings(self):
        cfg = self.config_data
        self.var_exe.set(cfg.get("builder_exe", ""))
        self.var_args.set(cfg.get("builder_args", ""))
        self.var_timeout.set(str(cfg.get("timeout", 600)))
        self.var_copy_builder.set(bool(cfg.get("builder_in_workdir", True)))
        self.var_pass_workdir.set(bool(cfg.get("pass_workdir_arg", False)))
        self.var_cfg_outdir.set(cfg.get("output_dir", ""))
        self.var_template.set(cfg.get("name_template", "{source}"))
        self.var_open_after.set(bool(cfg.get("open_after_success", True)))
        self.var_keep_staging.set(bool(cfg.get("keep_staging", False)))
        self.var_outdir.set(cfg.get("output_dir", ""))
        self.var_stock.set(cfg.get("last_stock", ""))
        self.var_xdf.set(cfg.get("last_xdf", ""))
        self.var_toolkey.set(cfg.get("last_toolkey", ""))
        self.var_customer.set(cfg.get("last_customer", ""))
        for var in (self.var_exe, self.var_args, self.var_timeout, self.var_cfg_outdir,
                    self.var_template):
            var.trace_add("write", lambda *_: self._save_settings())

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
            "output_dir": self.var_cfg_outdir.get().strip(),
            "name_template": self.var_template.get().strip() or "{source}",
            "keep_staging": bool(self.var_keep_staging.get()),
            "open_after_success": bool(self.var_open_after.get()),
            "timeout": timeout,
            "last_stock": self.var_stock.get().strip(),
            "last_xdf": self.var_xdf.get().strip(),
            "last_toolkey": self.var_toolkey.get().strip(),
            "last_customer": self.var_customer.get().strip(),
        }

    def _save_settings(self):
        self.config_data = self._collect_settings()
        ok = save_config(self.config_data)
        self.var_settings_summary.set("Saved automatically" if ok
                                      else "Could not write the settings file")

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
        return LockJob(
            customer=self.var_customer.get().strip(),
            vin=normalise_vin(self.var_vin.get()),
            stock_bin=self.var_stock.get().strip(),
            tuned_bin=self.var_tuned.get().strip(),
            xdf=self.var_xdf.get().strip(),
            toolkey=self.var_toolkey.get().strip(),
            output_dir=self.var_outdir.get().strip(),
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
        self._preflight_after = self.after(400, self._run_preflight)

    def _run_preflight(self, force=False):
        # A pending debounce must never fire during a run — it would wipe the log.
        self._cancel_preflight()
        if self._running:
            return
        job = self._current_job()
        ok_vin, vin, vin_msg = validate_vin(job.vin)
        self.lbl_vin.config(text=("✓  " if ok_vin else "✕  ") + vin_msg,
                            fg=ui.OK if ok_vin else ui.TEXT_FAINT if not job.vin else ui.ERR)
        for path, row in ((job.stock_bin, self.row_stock), (job.tuned_bin, self.row_tuned),
                          (job.xdf, self.row_xdf), (job.toolkey, self.row_toolkey)):
            if not path:
                row.set_hint("Not selected")
            elif not os.path.isfile(path):
                row.set_hint("File not found", "error")
            else:
                size = os.path.getsize(path)
                row.set_hint(f"{os.path.basename(path)} · {human_size(size)}", "ok")

        if not (job.stock_bin and job.tuned_bin and os.path.isfile(job.stock_bin)
                and os.path.isfile(job.tuned_bin)):
            if force:
                self.log.set_text("Select at least the stock and the tuned .bin.", "warn")
            self.var_summary.set("Waiting for input")
            return

        report = preflight(job, self._definition(job.xdf))
        self._render_preflight(report, job)

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
                label = ", ".join(names[:2]) if names else "— not in this XDF —"
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
            self.log_card.set_hint("ready to lock", "ok")
            self.var_summary.set(f"{report.changed_bytes:,} byte(s) changed · "
                                 f"{len(report.touched_tables)} table(s) · checks passed")
            self.status.set("Pre-flight passed", "ok")
        else:
            self.log_card.set_hint(f"{len(report.errors)} problem(s)", "error")
            self.var_summary.set(report.errors[0].text if report.errors else "Checks failed")
            self.status.set("Pre-flight failed", "error")
        return report

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
            self.lock_page.banner.show("error", "Pre-flight failed — fix the points above first.")
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
        """Build the working folder without running anything — for a manual run."""
        job = self._current_job()
        report = preflight(job, self._definition(job.xdf))
        self._render_preflight(report, job)
        if not report.ok:
            self.lock_page.banner.show("error", "Pre-flight failed — fix the points above first.")
            return
        target = job.output_dir or os.path.dirname(job.tuned_bin)
        workdir = unique_path(os.path.join(target, f"{safe_name(job.label, 'job')}_work"))
        try:
            manifest = stage_job(job, workdir,
                                 self.config_data.get("builder_exe", "")
                                 if self.config_data.get("builder_in_workdir", True) else "")
        except OSError as exc:
            self.lock_page.banner.show("error", f"Could not prepare the folder: {exc}")
            return
        self.log.write("")
        self.log.write(f"Working folder prepared: {workdir}", "ok")
        for key in ("stock", "tuned", "xdf", "toolkey", "vin_file"):
            self.log.write(f"    {manifest[key]}", "dim")
        self.lock_page.banner.show("ok", f"Working folder ready:\n{workdir}",
                                   action_text="Show in folder",
                                   action=lambda: ui.reveal_in_file_manager(workdir))
        self.status.set("Working folder prepared", "ok")

    def _on_batch_run(self):
        if not self.batch_jobs:
            self.batch_page.banner.show("error", "The queue is empty.")
            return
        exe = self.config_data.get("builder_exe", "")
        if not exe or not os.path.isfile(exe):
            self.batch_page.banner.show(
                "error", "No MHD map builder configured. Set its path in the Settings tab.",
                action_text="Open settings", action=lambda: self.tabs.select("settings"))
            return
        self.batch_log.clear()
        for index in range(len(self.batch_jobs)):
            self.batch_table.update_row(str(index), tag="dim")
            self._set_batch_cell(index, status="queued", output="")
        self.batch_page.banner.show("busy", f"Running {len(self.batch_jobs)} job(s)…")
        self._start(list(self.batch_jobs), target="batch")

    def _start(self, jobs, target):
        if self._worker and self._worker.is_alive():
            return
        self._stop_event = threading.Event()
        self._busy(True)
        self.status.set("Working…", "busy")
        self._worker = threading.Thread(target=self._work, args=(jobs, target), daemon=True)
        self._worker.start()

    def _post(self, kind, **payload):
        self._events.put((kind, payload))

    def _work(self, jobs, target):
        """Worker thread: stage → run → collect, one isolated folder per job."""
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
                        handle.write(f"{APP_NAME} v{APP_VERSION} — {brand.VENDOR}\n")
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
                   total=len(jobs))

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

    def _on_event_done(self, target, successes, failures, total):
        self._busy(False)
        page = self.batch_page if target == "batch" else self.lock_page
        if failures == 0 and successes:
            tone, text = "ok", (f"{successes} of {total} job(s) locked."
                                if total > 1 else "Locked successfully.")
        elif successes:
            tone, text = "warn", f"{successes} locked, {failures} failed — see the log."
        else:
            tone, text = "error", "Nothing was locked — see the log."
        last = getattr(self, "_last_output", "")
        if tone == "ok" and last:
            text = f"{text}\n{last}"
            page.banner.show(tone, text, action_text="Show in folder",
                             action=lambda p=last: ui.reveal_in_file_manager(p))
            if self.config_data.get("open_after_success"):
                ui.reveal_in_file_manager(last)
        else:
            page.banner.show(tone, text)
        self.status.set(f"{successes} locked · {failures} failed", tone)
        if target == "batch":
            self.var_batch_summary.set(f"{successes} locked · {failures} failed · {total} total")

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
        for path in paths:
            self.batch_jobs.append(LockJob(
                customer=base.customer or os.path.splitext(os.path.basename(path))[0],
                vin=base.vin, stock_bin=base.stock_bin, tuned_bin=path,
                xdf=base.xdf, toolkey=base.toolkey, output_dir=base.output_dir))
        self._batch_refresh()
        self.batch_log.write(f"Added {len(paths)} job(s) to the queue.", "ok", follow=True)

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
            self.batch_page.banner.show("error", "Nothing to export — the queue is empty.")
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
        print(f"{APP_NAME} v{APP_VERSION} — {brand.VENDOR}", file=sys.stderr)
        print("tkinter is not available in this Python installation.", file=sys.stderr)
        print("Windows/macOS: reinstall Python and tick 'tcl/tk and IDLE'.", file=sys.stderr)
        print("Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
        return 1
    app = MhdLockTool()
    app.geometry("1040x820")
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
