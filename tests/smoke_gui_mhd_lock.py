"""
Headless GUI smoke test for the MHD Lock Tool.

Needs a display and tkinter; not collected by `unittest discover` on purpose.
A stub builder stands in for the licensed MHD tool: it prints the same console
markers the real one prints and writes a .mhd, so the whole chain — resolution,
pre-flight, staging, run, output collection, renaming, logging — is exercised
for real.

    xvfb-run -a -s "-screen 0 1040x820x24" python tests/smoke_gui_mhd_lock.py
"""
import os
import stat
import sys
import tempfile
import textwrap
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORK = tempfile.mkdtemp(prefix="mhd_smoke_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(WORK, "config")

from _screenshot import shoot  # noqa: E402

import mhd_lock_tool as m  # noqa: E402

assert m.TK_AVAILABLE, "tkinter missing"

# A customer folder exactly like a hand-built one: stock ROM and XDF named after
# the program id, the tool key next to them, several tunes.
CAR = os.path.join(WORK, "M4 Kunde")
ROM_ID = "00005C6414C808"

STUB = textwrap.dedent("""\
    #!/bin/sh
    echo "opened BIN: $(ls *_original.bin) , size 0x800000"
    echo "Found 1373 tables"
    echo "Restrict to VIN : $(ls *_vin.txt | sed 's/_vin.txt//')"
    echo "Total bytes changed: 96"
    for f in *.bin; do
        case "$f" in
            *_original.bin) ;;
            *) head -c 91136 /dev/zero > "${f%.bin}.mhd"
               echo "Map correctly written : ${f%.bin}.mhd" ;;
        esac
    done
    echo "Press a key..."
    """)

SAMPLE_XDF = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <XDFFORMAT version="1.80">
      <XDFHEADER>
        <deftitle>S55 00005C6414C808</deftitle>
        <BASEOFFSET offset="0" subtract="0" />
        <REGION type="0xFFFFFFFF" startaddress="0x0" size="0x100000" name="Binary File" />
      </XDFHEADER>
      <XDFTABLE><title>Boost target (Gear x RPM)</title>
        <XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x100" mmedelementsizebits="16"
          mmedrowcount="8" mmedcolcount="8" /></XDFAXIS></XDFTABLE>
      <XDFTABLE><title>Timing (Main) Path 1</title>
        <XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x400" mmedelementsizebits="16"
          mmedrowcount="16" mmedcolcount="16" /></XDFAXIS></XDFTABLE>
    </XDFFORMAT>
    """)


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(path, mode) as handle:
        handle.write(data)
    return path


def build_fixture():
    stock = bytearray(0x100000)
    stock[0x1000:0x1007] = bytes.fromhex(ROM_ID)   # program id, packed, as in a real ROM
    write(os.path.join(CAR, f"{ROM_ID}_original.bin"), bytes(stock))
    for tag, offsets in (("v2", (0x100, 0x404)), ("v3", (0x100, 0x410)), ("v4", (0x408,))):
        tuned = bytearray(stock)
        for offset in offsets:
            tuned[offset:offset + 32] = b"\x11\x22" * 16
        write(os.path.join(CAR, f"MAP1 E45 MAP2 E30 {tag}.bin"), bytes(tuned))
    write(os.path.join(CAR, f"{ROM_ID}.xdf"), SAMPLE_XDF)
    write(os.path.join(CAR, "Gen.toolkey"), b"\x00" * 128)
    stub = write(os.path.join(WORK, "TuningMapBuilder-stub.sh"), STUB)
    os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
    os.makedirs(os.path.join(WORK, "locked"), exist_ok=True)
    return stub


def wait_for_worker(app, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.update()
        if not (app._worker and app._worker.is_alive()) and app._events.empty():
            app.update()
            return True
        time.sleep(0.05)
    return False


stub = build_fixture()
app = m.MhdLockTool()
app.geometry("1040x820")
app.update()

# ── Settings: the two things you set once ───────────────────────────────────
app.tabs.select("settings")
app.update()
app.var_exe.set(stub)
app.var_cfg_toolkey.set(os.path.join(CAR, "Gen.toolkey"))
app.var_cfg_outdir.set(os.path.join(WORK, "locked"))
app.var_open_after.set(False)
app.var_timeout.set("60")
app._save_settings()
app.update()
assert app.config_data["builder_exe"] == stub
assert os.path.isfile(m.config_path()), "settings were not persisted"
print("settings OK ->", m.config_path())
shoot("mhd_settings")

# ── Lock: ONE file is picked, everything else must resolve itself ───────────
app.tabs.select("lock")
app.update()
app.var_tuned.set(os.path.join(CAR, "MAP1 E45 MAP2 E30 v2.bin"))
app._resolve_and_check(force=True)
app.update()

assert app.var_stock.get().endswith(f"{ROM_ID}_original.bin"), app.var_stock.get()
assert app.var_xdf.get().endswith(f"{ROM_ID}.xdf"), app.var_xdf.get()
assert app.var_toolkey.get().endswith("Gen.toolkey"), app.var_toolkey.get()
assert "ROM 00005C6414C808" in app._step1.hint_var.get(), app._step1.hint_var.get()
for key in ("stock", "xdf", "toolkey"):
    assert app.res_rows[key]._icon.cget("text") == "✓", key
print("auto-resolved  :", ", ".join(
    f"{k}={os.path.basename(getattr(app, 'var_' + k).get())}" for k in ("stock", "xdf", "toolkey")))

# nothing typed yet -> the VIN is the only thing still missing
assert "✕" in app.lbl_vin.cget("text")
app.var_vin.set("dmetest0000000001")
app._resolve_and_check(force=True)
app.update()
assert "✓" in app.lbl_vin.cget("text")
log = app.log.text.get("1.0", "end")
assert "Boost target (Gear x RPM)" in log, log
assert "Timing (Main) Path 1" in log, log
print("pre-flight     :", app.var_summary.get())
shoot("mhd_lock")

# ── the actual run ──────────────────────────────────────────────────────────
app._on_lock()
assert wait_for_worker(app), "worker did not finish"
produced = sorted(os.listdir(os.path.join(WORK, "locked")))
assert "MAP1 E45 MAP2 E30 v2.mhd" in produced, produced
assert "MAP1 E45 MAP2 E30 v2.log" in produced, produced
run_log = app.log.text.get("1.0", "end")
assert "Map correctly written" in run_log
job_log = open(os.path.join(WORK, "locked", "MAP1 E45 MAP2 E30 v2.log"), encoding="utf-8").read()
assert "DMETEST0000000001" in job_log and "Map correctly written" in job_log
print("lock run OK    ->", produced)
assert not [p for p in os.listdir(tempfile.gettempdir()) if p.startswith("dme_mhd_")]

# ── "Prepare folder only" must rebuild a hand-built folder ──────────────────
app._on_stage_only()
app.update()
work_dirs = [p for p in os.listdir(os.path.join(WORK, "locked")) if p.endswith("_work")]
assert work_dirs, os.listdir(os.path.join(WORK, "locked"))
staged = sorted(os.listdir(os.path.join(WORK, "locked", work_dirs[0])))
assert staged == [f"{ROM_ID}.xdf", f"{ROM_ID}_original.bin", "DMETEST0000000001_vin.txt",
                  "Gen.toolkey", "MAP1 E45 MAP2 E30 v2.bin",
                  "TuningMapBuilder-stub.sh"], staged
print("prepare-only OK->", staged)

# picking another tune must re-resolve without any extra input
app.var_tuned.set(os.path.join(CAR, "MAP1 E45 MAP2 E30 v4.bin"))
app._resolve_and_check(force=True)
app.update()
assert app.var_stock.get().endswith(f"{ROM_ID}_original.bin")
assert app.var_vin.get() == "DMETEST0000000001"     # VIN stays for the same customer
print("switch tune OK :", app.var_summary.get())

# ── Batch ───────────────────────────────────────────────────────────────────
app.tabs.select("batch")
app.update()
m.filedialog.askopenfilenames = lambda **k: (os.path.join(CAR, "MAP1 E45 MAP2 E30 v3.bin"),)
app._batch_add_files()
app.update()
assert len(app.batch_jobs) == 1 and app.batch_jobs[0].stock_bin.endswith("_original.bin")
app._on_batch_run()
assert wait_for_worker(app, timeout=90), "batch did not finish"
assert app.batch_table.tree.item("0", "values")[3] == "locked", \
    app.batch_table.tree.item("0", "values")
print("batch OK       :", app.var_batch_summary.get())
shoot("mhd_batch")

# ── error path ──────────────────────────────────────────────────────────────
app.var_exe.set("")
app._save_settings()
app.tabs.select("lock")
app.update()
app._on_lock()
app.update()
assert "No MHD map builder" in app.lock_page.banner._text.cget("text")
print("missing-builder path OK")

app.destroy()
print("SMOKE TEST PASSED")
