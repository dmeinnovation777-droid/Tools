"""
Headless GUI smoke test for the MHD Lock Tool.

Needs a display and tkinter; not collected by `unittest discover` on purpose.
A stub builder stands in for the licensed MHD tool: it prints the same console
markers the real one prints and writes a .mhd, so the whole chain — pre-flight,
staging, run, output collection, renaming, logging — is exercised for real.

    xvfb-run -a -s "-screen 0 1040x820x24" python3 tests/smoke_gui_mhd_lock.py
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

STUB = textwrap.dedent("""\
    #!/bin/sh
    # Stand-in for TuningMapBuilder-v6.exe — same console markers, same outputs.
    echo "opened BIN: $(ls *_original.bin) , size 0x100000"
    echo "Found 1373 tables"
    echo "Restrict to VIN : $(ls *_vin.txt | sed 's/_vin.txt//')"
    echo "Total bytes changed: 4"
    echo "WARNING: overlapping blocks:"
    for f in *.bin; do
        case "$f" in
            *_original.bin) ;;
            *) head -c 91136 /dev/zero > "${f%.bin}.mhd"
               echo "Map correctly written : ${f%.bin}.mhd" ;;
        esac
    done
    echo "Total time 00:00:04"
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
      <XDFTABLE><title>Fuel (Spool)</title>
        <XDFAXIS id="z"><EMBEDDEDDATA mmedaddress="0x800" mmedelementsizebits="8"
          mmedcolcount="32" /></XDFAXIS></XDFTABLE>
      <XDFFLAG><title>Enable Antilag</title>
        <EMBEDDEDDATA mmedaddress="0x900" mmedelementsizebits="8" /></XDFFLAG>
    </XDFFORMAT>
    """)


def build_fixture():
    stock = bytearray(0x100000)
    stock[0x1000:0x100E] = b"00005C6414C808"
    write(os.path.join(WORK, "00005C6414C808_original.bin"), bytes(stock))
    for tag, offsets in (("v2", (0x100, 0x404)), ("v3", (0x100, 0x810)), ("v4", (0x902,))):
        tuned = bytearray(stock)
        for offset in offsets:
            tuned[offset:offset + 4] = b"\x11\x22\x33\x44"
        write(os.path.join(WORK, f"MAP1 E45 MAP2 E30 {tag}.bin"), bytes(tuned))
    write(os.path.join(WORK, "00005C6414C808.xdf"), SAMPLE_XDF)
    write(os.path.join(WORK, "Gen.toolkey"), b"\x00" * 128)
    stub = write(os.path.join(WORK, "TuningMapBuilder-stub.sh"), STUB)
    os.chmod(stub, os.stat(stub).st_mode | stat.S_IEXEC)
    os.makedirs(os.path.join(WORK, "locked"), exist_ok=True)
    return stub


def write(path, data):
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(path, mode) as handle:
        handle.write(data)
    return path


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

# ── Settings ────────────────────────────────────────────────────────────────
app.tabs.select("settings")
app.update()
app.var_exe.set(stub)
app.var_cfg_outdir.set(os.path.join(WORK, "locked"))
app.var_template.set("{source}")
app.var_open_after.set(False)
app.var_timeout.set("60")
app._save_settings()
app.update()
assert app.config_data["builder_exe"] == stub
assert os.path.isfile(m.config_path()), "settings were not persisted"
print("settings OK ->", m.config_path())
shoot("mhd_settings")

# ── Lock tab: pre-flight ────────────────────────────────────────────────────
app.tabs.select("lock")
app.update()
app.var_customer.set("Demo Kunde")
app.var_vin.set("dmetest0000000001")
app.var_stock.set(os.path.join(WORK, "00005C6414C808_original.bin"))
app.var_tuned.set(os.path.join(WORK, "MAP1 E45 MAP2 E30 v2.bin"))
app.var_xdf.set(os.path.join(WORK, "00005C6414C808.xdf"))
app.var_toolkey.set(os.path.join(WORK, "Gen.toolkey"))
app.var_outdir.set(os.path.join(WORK, "locked"))
app._run_preflight(force=True)
app.update()
log = app.log.text.get("1.0", "end")
assert "Boost target (Gear x RPM)" in log, log
assert "Timing (Main) Path 1" in log, log
assert "8 byte(s) changed" in log, log
assert "✓" in app.lbl_vin.cget("text")
print("pre-flight OK:", app.var_summary.get())

# bad VIN must block
app.var_vin.set("TOO-SHORT")
app._run_preflight(force=True)
app.update()
assert "problem" in app.log_card.hint_var.get(), app.log_card.hint_var.get()
app.var_vin.set("DMETEST0000000001")
app._run_preflight(force=True)
app.update()
print("VIN validation OK")

# ── Lock tab: real run through the stub builder ─────────────────────────────
app._on_lock()
assert wait_for_worker(app), "worker did not finish"
produced = sorted(os.listdir(os.path.join(WORK, "locked")))
assert "MAP1 E45 MAP2 E30 v2.mhd" in produced, produced
assert "MAP1 E45 MAP2 E30 v2.log" in produced, produced
run_log = app.log.text.get("1.0", "end")
assert "Map correctly written" in run_log
assert "Total bytes changed: 4" in run_log
job_log = open(os.path.join(WORK, "locked", "MAP1 E45 MAP2 E30 v2.log"), encoding="utf-8").read()
assert "DMETEST0000000001" in job_log and "Map correctly written" in job_log
print("lock run OK ->", produced)
shoot("mhd_lock")

# staging must be cleaned up
leftovers = [p for p in os.listdir(tempfile.gettempdir()) if p.startswith("dme_mhd_")]
assert not leftovers, leftovers
print("staging cleaned up OK")

# ── Prepare folder only ─────────────────────────────────────────────────────
app._on_stage_only()
app.update()
work_dirs = [p for p in os.listdir(os.path.join(WORK, "locked")) if p.endswith("_work")]
assert work_dirs, os.listdir(os.path.join(WORK, "locked"))
staged = sorted(os.listdir(os.path.join(WORK, "locked", work_dirs[0])))
assert "DMETEST0000000001_vin.txt" in staged and "00005C6414C808_original.bin" in staged
assert "TuningMapBuilder-stub.sh" in staged
print("prepare-only OK ->", staged)

# ── Batch tab ───────────────────────────────────────────────────────────────
app.tabs.select("batch")
app.update()
m.filedialog.askopenfilenames = lambda **k: (
    os.path.join(WORK, "MAP1 E45 MAP2 E30 v3.bin"),
    os.path.join(WORK, "MAP1 E45 MAP2 E30 v4.bin"))
app._batch_add_files()
app.update()
assert len(app.batch_jobs) == 2, app.batch_jobs

csv_path = write(os.path.join(WORK, "jobs.csv"),
                 "customer,vin,tuned_bin\n"
                 "Kunde CSV,DMETEST0000000002,MAP1 E45 MAP2 E30 v2.bin\n")
m.filedialog.askopenfilename = lambda **k: csv_path
app._batch_import_csv()
app.update()
assert len(app.batch_jobs) == 3
assert app.batch_jobs[2].customer == "Kunde CSV"

app._on_batch_run()
assert wait_for_worker(app, timeout=90), "batch did not finish"
statuses = [app.batch_table.tree.item(str(i), "values")[3] for i in range(3)]
assert statuses == ["locked", "locked", "locked"], statuses
final = sorted(os.listdir(os.path.join(WORK, "locked")))
for expected in ("MAP1 E45 MAP2 E30 v3.mhd", "MAP1 E45 MAP2 E30 v4.mhd"):
    assert expected in final, final
print("batch OK:", statuses, "->", app.var_batch_summary.get())
shoot("mhd_batch")

# error path: no builder configured
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
