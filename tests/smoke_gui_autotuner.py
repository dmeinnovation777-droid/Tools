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
         "fuel": "PETROL", "ps": "610", "vin": "ZHWUC1ZF9ELA02345"}))
    zf.writestr("how-to-use-backup.html", at.HOW_TO_USE_HTML)

app = at.AutoTunerTool()
app.geometry("1000x800")
app.update()

# ── Page 1 ──────────────────────────────────────────────────────────────────
out_bin = os.path.join(tmp, "combined.bin")
app._z2b_zip_var.set(zip_path)
app._z2b_out_var.set(out_bin)
app._analyze_zip()
app.update()
preview = app._z2b_log.text.get("1.0", "end")
assert "iflash0.bin" in preview and "Lamborghini" in preview, preview
assert app._z2b_preview_card.hint_var.get().startswith("4 part"), app._z2b_preview_card.hint_var.get()
app._run_zip_to_bin()
app.update()
with open(out_bin, "rb") as f:
    assert f.read() == b"\x01"*4096 + b"\x02"*4096 + b"\x03"*512 + b"\x04"*512
assert app._z2b_banner._visible and "Combined 4 part(s)" in app._z2b_banner._text.cget("text")
print("ZIP->BIN OK:", app._z2b_banner._text.cget("text").splitlines()[0])
shoot("tab1")

# ── Page 2 ──────────────────────────────────────────────────────────────────
app.tabs.select("b2z")
app.update()
app._load_preset("MED17.1.1")
app.update()
assert len(app._part_rows) == 4 and app._meta_vars["EcuBuild"].get() == "MED17.1.1"
app._delete_part_row(app._part_rows[-1])
app.update()
assert len(app._part_rows) == 3 and app._part_rows[0].index_lbl.cget("text") == "1"
app._add_part_row("eflash.bin", 1024)
app.update()
assert len(app._part_rows) == 4

at.filedialog.askopenfilename = lambda **k: zip_path
app._load_parts_from_zip()
app.update()
assert [r.name_var.get() for r in app._part_rows] == \
       ["iflash0.bin", "iflash1.bin", "dflash0.bin", "dflash1.bin"]
assert app._meta_vars["VehicleProducer"].get() == "Lamborghini"
assert app._meta_vars["VehicleVIN"].get() == "ZHWUC1ZF9ELA02345"

app._b2z_bin_var.set(out_bin)
app._update_totals()
app.update()
assert "sizes match" in app._b2z_match.cget("text"), app._b2z_match.cget("text")
print("totals OK:", app._b2z_total_var.get(), "|", app._b2z_match.cget("text"))

out_zip = os.path.join(tmp, "rebuilt.zip")
app._b2z_out_var.set(out_zip)
app._run_bin_to_zip()
app.update()
with zipfile.ZipFile(out_zip) as zf:
    assert zf.namelist()[:4] == ["iflash0.bin", "iflash1.bin", "dflash0.bin", "dflash1.bin"]
    assert zf.read("iflash1.bin") == b"\x02"*4096
    meta = at.parse_ini(zf.read("contents.ini").decode())
    assert meta["VehicleProducer"] == "Lamborghini" and meta["EcuBuild"] == "MED17.1.1"
    assert meta["VehicleVIN"] == "ZHWUC1ZF9ELA02345"
print("BIN->ZIP OK:", app._b2z_banner._text.cget("text").splitlines()[0])
shoot("tab2")

# error path -> banner, no crash
app._b2z_bin_var.set("")
app._run_bin_to_zip()
app.update()
assert app._b2z_banner._text.cget("text").startswith("Select a source")
app.destroy()
print("SMOKE TEST PASSED")
