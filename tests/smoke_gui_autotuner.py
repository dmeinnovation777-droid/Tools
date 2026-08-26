"""
Headless GUI smoke test for the AutoTuner Backup Tool.

Needs a display and tkinter; not collected by `unittest discover` on purpose.

    xvfb-run -a -s "-screen 0 1000x800x24" python3 tests/smoke_gui_autotuner.py

Writes /tmp/shot_tab1.xwd and /tmp/shot_tab2.xwd; convert them with
    python3 tools/xwd2png.py /tmp/shot_tab1.xwd docs/screenshot-....png
"""
import os, sys, tempfile, zipfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _screenshot import shoot  # noqa: E402

import autotuner_tool as at
import dme_app
import dme_text

assert at.TK_AVAILABLE, "tkinter missing"
tmp = tempfile.mkdtemp()

zip_path = os.path.join(tmp, "MED1711_backup.zip")
parts = [("iflash0.bin", b"\x01"*4096), ("iflash1.bin", b"\x02"*4096),
         ("dflash0.bin", b"\x03"*512), ("dflash1.bin", b"\x04"*512)]
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for n, d in reversed(parts):          # stored out of order on purpose
        zf.writestr(n, d)
    zf.writestr("contents.ini", at.build_contents_ini(
        {"make": "Lamborghini", "model": "Huracan", "variant": "5.2 V10 FSI",
         "year": "2014", "ecu_model": "MED17.1.1", "ecu_maker": "Bosch",
         "fuel": "PETROL", "ps": "610", "vin": "ZHWUC1ZF9ELA02345",
         "series": "LB724", "kw": "449"}))
    zf.writestr("how-to-use-backup.html", at.HOW_TO_USE_HTML)

app = dme_app.DmeApp(start_page="backup")
app.geometry("1120x820")
app.update()
backup = app.backup

# ── Page 1 ──────────────────────────────────────────────────────────────────
out_bin = os.path.join(tmp, "combined.bin")
backup._z2b_zip_var.set(zip_path)
backup._z2b_out_var.set(out_bin)
backup._analyze_zip()
app.update()
preview = backup._z2b_log.text.get("1.0", "end")
assert "iflash0.bin" in preview and "Lamborghini" in preview, preview
assert backup._z2b_step2._note.cget("text").startswith("4 "), \
    backup._z2b_step2._note.cget("text")
backup._run_zip_to_bin()
app.update()
with open(out_bin, "rb") as f:
    assert f.read() == b"\x01"*4096 + b"\x02"*4096 + b"\x03"*512 + b"\x04"*512
assert backup._z2b_banner._visible and "Combined 4 part(s)" in backup._z2b_banner._text.cget("text")
print("ZIP->BIN OK:", backup._z2b_banner._text.cget("text").splitlines()[0])
shoot("tab1")

# ── Page 2 ──────────────────────────────────────────────────────────────────
backup.switch.select("b2z")
app.update()
backup._load_preset("MED17.1.1")
app.update()
assert len(backup._part_rows) == 4 and backup._meta_vars["EcuBuild"].get() == "MED17.1.1"
backup._delete_part_row(backup._part_rows[-1])
app.update()
assert len(backup._part_rows) == 3 and backup._part_rows[0].index_lbl.cget("text") == "1"
backup._add_part_row("eflash.bin", 1024)
app.update()
assert len(backup._part_rows) == 4

at.filedialog.askopenfilename = lambda **k: zip_path
backup._load_parts_from_zip()
app.update()
assert [r.name_var.get() for r in backup._part_rows] == \
       ["iflash0.bin", "iflash1.bin", "dflash0.bin", "dflash1.bin"]
assert backup._meta_vars["VehicleProducer"].get() == "Lamborghini"
assert backup._meta_vars["VehicleVIN"].get() == "ZHWUC1ZF9ELA02345"

backup._b2z_bin_var.set(out_bin)
backup._update_totals()
app.update()
assert dme_text.t("backup.parts.match") in backup._b2z_match.cget("text"), \
    backup._b2z_match.cget("text")
print("totals OK:", backup._b2z_total_var.get(), "|", backup._b2z_match.cget("text"))

out_zip = os.path.join(tmp, "rebuilt.zip")
backup._b2z_out_var.set(out_zip)
backup._run_bin_to_zip()
app.update()
with zipfile.ZipFile(out_zip) as zf:
    assert zf.namelist()[:4] == ["iflash0.bin", "iflash1.bin", "dflash0.bin", "dflash1.bin"]
    assert zf.read("iflash1.bin") == b"\x02"*4096
    meta = at.parse_ini(zf.read("contents.ini").decode())
    assert meta["VehicleProducer"] == "Lamborghini" and meta["EcuBuild"] == "MED17.1.1"
    assert meta["VehicleVIN"] == "ZHWUC1ZF9ELA02345"
print("BIN->ZIP OK:", backup._b2z_banner._text.cget("text").splitlines()[0])
shoot("tab2")

# ── an empty line in the split table ────────────────────────────────────────
# Found on a real Mercedes GLE on 3.2.0: the page said the step was done,
# counted the empty line as a part and reported that the sizes matched, and
# then refused to write the archive because of it.
backup._b2z_bin_var.set(out_bin)
backup._b2z_out_var.set(out_zip)
app.update()
real = len(backup._part_rows)
backup._add_part_row()
app.update()
assert backup._b2z_step2.state == "done", \
    f"an empty line made the step {backup._b2z_step2.state}"
assert backup._b2z_step2._note.cget("text") == str(real), \
    f"the empty line was counted: {backup._b2z_step2._note.cget('text')} of {real}"
assert dme_text.t("backup.parts.match") in backup._b2z_match.cget("text")

# half filled is a real mistake and has to show at once, not at the button
backup._part_rows[-1].name_var.set("extra.bin")
app.update()
assert backup._b2z_step2.state == "err", "a half filled line passed as done"
assert dme_text.t("backup.parts.bad_row", n=real + 1) in backup._b2z_match.cget("text"), \
    backup._b2z_match.cget("text")

# and blank again, it packs, with the empty line simply left out
backup._part_rows[-1].name_var.set("")
app.update()
second = os.path.join(tmp, "with_blank.zip")
backup._b2z_out_var.set(second)
backup._run_bin_to_zip()
app.update()
assert os.path.exists(second), "an empty line still blocked the archive"
with zipfile.ZipFile(second) as zf:
    assert zf.namelist()[:4] == ["iflash0.bin", "iflash1.bin", "dflash0.bin", "dflash1.bin"]
print("blank line OK: not counted, not packed, not in the way")

# ── the car comes back with the layout ──────────────────────────────────────
# Five of the fourteen fields have no box on the page. They can only come from
# the archive the .bin came out of, and before 3.2.1 they came back empty.
with zipfile.ZipFile(second) as zf:
    meta = at.parse_ini(zf.read("contents.ini").decode())
assert meta["VehicleSeries"] == "LB724", \
    f"the series has no box and was lost: {meta['VehicleSeries']!r}"
assert meta["OutputKW"] == "449", \
    f"the kW has no box and was lost: {meta['OutputKW']!r}"
assert meta["EngineType"] == "PETROL", "the fuel changed on the way back"

# A field cleared on purpose stays cleared: the boxes have the last word, or a
# VIN wiped before handing the file on would quietly come back.
backup._meta_vars["VehicleVIN"].set("")
third = os.path.join(tmp, "no_vin.zip")
backup._b2z_out_var.set(third)
backup._run_bin_to_zip()
app.update()
with zipfile.ZipFile(third) as zf:
    meta = at.parse_ini(zf.read("contents.ini").decode())
assert meta["VehicleVIN"] == "", f"the wiped VIN came back: {meta['VehicleVIN']!r}"
assert meta["VehicleSeries"] == "LB724", "clearing the VIN took the series with it"
print("vehicle data OK: carried across, and a cleared field stays cleared")

# ── the split belongs to the file it was made for ───────────────────────────
# Reported from the workshop: after a Mercedes, a VW Caddy of a different size
# was picked and the page still showed the Mercedes split. It then refused to
# pack, because two parts added up to somebody else's file.
other_zip = os.path.join(tmp, "other_backup.zip")
with zipfile.ZipFile(other_zip, "w", zipfile.ZIP_DEFLATED) as zf:
    zf.writestr("iflash0.bin", b"\x0a" * 2048)
    zf.writestr("dflash0.bin", b"\x0b" * 256)
    zf.writestr("contents.ini", at.build_contents_ini({"ecu_model": "MD1CS004"}))
    zf.writestr(at.HOW_TO_NAME, at.HOW_TO_USE_HTML)
other_bin = os.path.join(tmp, "other-MD1CS004_combined.bin")
backup._set_direction("z2b")
backup._z2b_zip_var.set(other_zip)
backup._z2b_out_var.set(other_bin)
backup._run_zip_to_bin()
app.update()
backup._set_direction("b2z")
app.update()

backup._b2z_bin_var.set(out_bin)              # the four part file from above
app.update()
assert sum(r.size for r in backup._part_rows) == os.path.getsize(out_bin)
backup._b2z_bin_var.set(other_bin)            # now a different file
app.update()
assert sum(r.size for r in backup._part_rows) == os.path.getsize(other_bin), \
    (f"the split still belongs to the last file: "
     f"{sum(r.size for r in backup._part_rows)} for a file of "
     f"{os.path.getsize(other_bin)}")
assert [r.name_var.get() for r in backup._part_rows] == ["iflash0.bin", "dflash0.bin"]
print("split follows the file OK:", [r.name_var.get() for r in backup._part_rows])

# and the engine answers in the language the window is in
backup._b2z_bin_var.set(out_bin)
app.update()
backup._part_rows[0].size_var.set("1")
app.update()
backup._b2z_out_var.set(os.path.join(tmp, "never.zip"))
backup._run_bin_to_zip()
app.update()
shown = backup.banner._text.cget("text")
assert shown.startswith(dme_text.t("backup.msg.size_mismatch", total="", actual="")[:20]), \
    f"the engine answered in the wrong language: {shown!r}"
print("engine speaks the window's language OK")

# error path -> banner, no crash
backup._b2z_bin_var.set("")
backup._run_bin_to_zip()
app.update()
assert backup.banner._text.cget("text") == dme_text.t("err.no_bin"), \
    backup.banner._text.cget("text")
app.destroy()
print("SMOKE TEST PASSED")
