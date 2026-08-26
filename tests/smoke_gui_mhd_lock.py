"""
Headless GUI smoke test for the Lock and Batch areas of the app.

Needs a display and tkinter; not collected by `unittest discover` on purpose.
A stub builder stands in for the licensed MHD tool: it prints the same console
markers the real one prints and writes a .mhd, so the whole chain — resolution,
pre-flight, staging, run, output collection, renaming, logging — is exercised
for real.

    xvfb-run -a -s "-screen 0 1120x860x24" python tests/smoke_gui_mhd_lock.py
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

import dme_app  # noqa: E402
import dme_text  # noqa: E402
import mhd_lock_tool as m  # noqa: E402

assert m.TK_AVAILABLE, "tkinter missing"

# A customer folder exactly like a hand-built one: stock ROM and XDF named after
# the program id, the tool key next to them, several tunes.
CAR = os.path.join(WORK, "M4 Kunde")
ROM_ID = "00005C6414C808"

# The stub behaves like the real builder in the two ways that broke a customer
# job, so that a regression in either shows up here instead of on his machine:
#
#   * it works on the file handed to it as an argument, the way dropping a .bin
#     onto the .exe does. No argument, no work - exactly what the real one did.
#   * it does not exit. It ends on its prompt and waits, like Console.ReadKey().
STUB = textwrap.dedent("""\
    #!/bin/sh
    target="$1"
    if [ -n "$target" ] && [ -f "$target" ]; then
        echo "opened BIN: $(ls *_original.bin) , size 0x800000"
        echo "Found 1373 tables"
        echo "Restrict to VIN : $(ls *_vin.txt | sed 's/_vin.txt//')"
        echo "Total bytes changed: 96"
        base=$(basename "$target" .bin)
        head -c 91136 /dev/zero > "$base.mhd"
        echo "Map correctly written : $base.mhd"
    fi
    echo "Press a key..."
    sleep 300
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


def wait_for_worker(lock, timeout=60):
    """Wait until nothing is running any more and everything is drawn."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.update()
        if not lock.is_busy():
            app.update()
            app.update()
            return True
        time.sleep(0.03)
    return False


stub = build_fixture()
# Whatever language the app opens in, the assertions ask the word list for the
# same key it shows, so this test passes in both.
app = dme_app.DmeApp()
app.geometry("1120x820")
app.update()
lock = app.lock

# ── Settings: the two things you set once ───────────────────────────────────
app.tabs.select("settings")
app.update()
lock.var_exe.set(stub)
lock.var_cfg_toolkey.set(os.path.join(CAR, "Gen.toolkey"))
lock.var_cfg_outdir.set(os.path.join(WORK, "locked"))
lock.var_open_after.set(False)
lock.var_timeout.set("60")
lock.save_settings()
app.update()
assert lock.config_data["builder_exe"] == stub
assert os.path.isfile(m.config_path()), "settings were not persisted"
print("settings OK ->", m.config_path())
shoot("mhd_settings")

# ── Lock: ONE file is picked, everything else must resolve itself ───────────
app.tabs.select("lock")
app.update()
lock.var_tuned.set(os.path.join(CAR, "MAP1 E45 MAP2 E30 v2.bin"))
lock._resolve_and_check(force=True)
app.update()

assert lock.var_stock.get().endswith(f"{ROM_ID}_original.bin"), lock.var_stock.get()
assert lock.var_xdf.get().endswith(f"{ROM_ID}.xdf"), lock.var_xdf.get()
assert lock.var_toolkey.get().endswith("Gen.toolkey"), lock.var_toolkey.get()
assert f"ROM {ROM_ID}" in lock.step_file._note.cget("text"), lock.step_file._note.cget("text")
for key in ("stock", "xdf", "toolkey"):
    assert lock.res_tags[key]._label.cget("text").startswith("\u2713"), key
assert lock.step_file.state == "done"
print("auto-resolved  :", ", ".join(
    f"{k}={os.path.basename(getattr(lock, 'var_' + k).get())}"
    for k in ("stock", "xdf", "toolkey")))

# nothing typed yet -> the VIN is the only thing still missing
assert "\u2715" in lock.lbl_vin.cget("text")
assert lock.step_vin.state == "now", lock.step_vin.state
lock.var_vin.set("dmetest0000000001")
lock._resolve_and_check(force=True)
app.update()
assert "\u2713" in lock.lbl_vin.cget("text")
assert lock.step_vin.state == "done", lock.step_vin.state
assert lock.step_run.state == "now", lock.step_run.state
log = lock.log.text.get("1.0", "end")
assert "Boost target (Gear x RPM)" in log, log
assert "Timing (Main) Path 1" in log, log
print("pre-flight     :", lock.var_summary.get())
shoot("mhd_lock")

# ── the actual run ──────────────────────────────────────────────────────────
lock._on_lock()
assert wait_for_worker(lock), "worker did not finish"
produced = sorted(os.listdir(os.path.join(WORK, "locked")))
assert "MAP1 E45 MAP2 E30 v2.mhd" in produced, produced
assert "MAP1 E45 MAP2 E30 v2.log" in produced, produced
run_log = lock.log.text.get("1.0", "end")
assert "Map correctly written" in run_log
job_log = open(os.path.join(WORK, "locked", "MAP1 E45 MAP2 E30 v2.log"),
               encoding="utf-8").read()
assert "DMETEST0000000001" in job_log and "Map correctly written" in job_log
assert lock.step_run.state == "done", lock.step_run.state
print("lock run OK    ->", produced)
assert not [p for p in os.listdir(tempfile.gettempdir()) if p.startswith("dme_mhd_")]

# ── "Folder only" must rebuild a hand-built folder ──────────────────────────
# It has to be reachable without opening anything: the action row, not the log.
assert lock.btn_stage.winfo_ismapped(), "the folder button is not visible"
assert lock.btn_stage.master is lock.lock_page.action_row
lock.btn_stage._invoke()
app.update()
work_dirs = [p for p in os.listdir(os.path.join(WORK, "locked")) if p.endswith("_work")]
assert work_dirs, os.listdir(os.path.join(WORK, "locked"))
staged = sorted(os.listdir(os.path.join(WORK, "locked", work_dirs[0])))
assert staged == [f"{ROM_ID}.xdf", f"{ROM_ID}_original.bin", "DMETEST0000000001_vin.txt",
                  "Gen.toolkey", "MAP1 E45 MAP2 E30 v2.bin",
                  "TuningMapBuilder-stub.sh"], staged
print("folder only OK ->", staged)

# picking another tune must re-resolve without any extra input
lock.var_tuned.set(os.path.join(CAR, "MAP1 E45 MAP2 E30 v4.bin"))
lock._resolve_and_check(force=True)
app.update()
assert lock.var_stock.get().endswith(f"{ROM_ID}_original.bin")
assert lock.var_vin.get() == "DMETEST0000000001"     # VIN stays for the same customer
print("switch tune OK :", lock.var_summary.get())

# ── Batch ───────────────────────────────────────────────────────────────────
app.tabs.select("batch")
app.update()
m.filedialog.askopenfilenames = lambda **k: (os.path.join(CAR, "MAP1 E45 MAP2 E30 v3.bin"),)
lock._batch_add_files()
# The lookup per file runs on a worker now, so the window stays alive while it
# happens and the queue fills when it is done.
assert wait_for_worker(lock), "the queue was not built"
assert len(lock.batch_jobs) == 1 and lock.batch_jobs[0].stock_bin.endswith("_original.bin")
lock._on_batch_run()
assert wait_for_worker(lock, timeout=90), "batch did not finish"
assert lock.batch_table.tree.item("0", "values")[3] == dme_text.t("word.locked"), \
    lock.batch_table.tree.item("0", "values")
print("batch OK       :", lock.var_batch_summary.get())
shoot("mhd_batch")

# ── folder mode: no builder needed, and the queue only prepares ─────────────
lock.var_prepare_only.set(True)
lock.var_exe.set("")                      # the whole point: no builder configured
lock.save_settings()
app.update()
assert not m.missing_setup(lock.config_data, lock.var_toolkey.get()), \
    m.missing_setup(lock.config_data, lock.var_toolkey.get())
app.tabs.select("lock")
app.update()
assert not lock.setup_card.winfo_manager(), "folder mode still demands a builder"
app.tabs.select("batch")
app.update()
assert lock.btn_batch_run.cget("text") == dme_text.t("batch.btn.prepare"), \
    lock.btn_batch_run.cget("text")
lock._on_batch_run()
assert wait_for_worker(lock, timeout=90), "batch prepare did not finish"
assert lock.batch_table.tree.item("0", "values")[3] == dme_text.t("word.prepared"), \
    lock.batch_table.tree.item("0", "values")
prepared = [p for p in os.listdir(os.path.join(WORK, "locked")) if p.endswith("_work")]
assert len(prepared) >= 2, prepared          # the lock-page one plus this batch one
print("folder mode OK :", lock.var_batch_summary.get())

app.tabs.select("lock")
app.update()
assert not lock.btn_lock.winfo_manager(), "the lock button survives in folder mode"
lock.var_prepare_only.set(False)
lock.save_settings()
app.update()
assert lock.btn_lock.winfo_manager(), "the lock button does not come back"

# ── error path ──────────────────────────────────────────────────────────────
lock._on_lock()
app.update()
assert dme_text.t("setup.what.builder") in lock.lock_page.banner._text.cget("text"), \
    lock.lock_page.banner._text.cget("text")
print("missing-builder path OK")

app.destroy()
print("SMOKE TEST PASSED")
