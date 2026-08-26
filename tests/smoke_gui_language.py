"""
Switching the language throws the pages away and builds them again.

That is the cheap way to do it, and it is only allowed to be cheap if nothing
of yours is thrown away with them. Values live on the controllers in tk
variables, not in the widgets, so this test checks the ones that would hurt:
the picked file, the VIN, the customer, the queue, and every setting.

Only the log window is allowed to start over, and the switch says so.

    xvfb-run -a -s "-screen 0 1120x880x24" python tests/smoke_gui_language.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORK = tempfile.mkdtemp(prefix="lang_smoke_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(WORK, "config")

import dme_app     # noqa: E402
import dme_text    # noqa: E402
import mhd_lock_tool as m  # noqa: E402

assert dme_app.TK_AVAILABLE, "tkinter missing"

TUNED = os.path.join(WORK, "MAP1 E45 MAP2 E30.bin")
with open(TUNED, "wb") as handle:
    handle.write(b"\x00" * 4096)

app = dme_app.DmeApp()
app.geometry("1120x820")
app.update()
lock = app.lock

# ── fill the app with things that must survive ──────────────────────────────
lock.var_tuned.set(TUNED)
lock.var_vin.set("WBS21DM0408F91146")
lock.var_customer.set("Mathias")
lock.var_cfg_outdir.set(WORK)
lock.var_timeout.set("120")
lock.var_prepare_only.set(True)
lock.save_settings()
lock.batch_jobs.append(m.LockJob(customer="Kunde", vin="WBS42AY040FR10018",
                                 stock_bin="", tuned_bin=TUNED, xdf="", toolkey="",
                                 output_dir=WORK))
lock._batch_refresh()
app.backup._z2b_zip_var.set(os.path.join(WORK, "backup.zip"))
app.shell.select("batch")
app.update()

start = dme_text.language()
other = "en" if start == "de" else "de"

# ── switch ──────────────────────────────────────────────────────────────────
app.set_language(other)
app.update()
lock = app.lock          # same controller, new widgets

problems = []
if dme_text.language() != other:
    problems.append(f"language is {dme_text.language()}, not {other}")
if app.shell.active != "batch":
    problems.append(f"the area changed to {app.shell.active}")
if app.shell.nav.label_of("lock") != dme_text.t("nav.lock"):
    problems.append("the navigation kept the old words")
if lock.var_tuned.get() != TUNED:
    problems.append("the tuned file was lost")
if lock.var_vin.get() != "WBS21DM0408F91146":
    problems.append("the VIN was lost")
if lock.var_customer.get() != "Mathias":
    problems.append("the customer was lost")
if lock.var_timeout.get() != "120":
    problems.append("the timeout was lost")
if not lock.var_prepare_only.get():
    problems.append("folder mode was lost")
if len(lock.batch_jobs) != 1:
    problems.append("the queue was lost")
if lock.batch_table.tree.item("0", "values")[1] != "WBS42AY040FR10018":
    problems.append("the queue was not drawn again")
if app.backup._z2b_zip_var.get() != os.path.join(WORK, "backup.zip"):
    problems.append("the backup path was lost")
if lock.btn_stage.cget("text") != dme_text.t("lock.btn.prepare_main"):
    problems.append("the action button kept the old words")

# It is written down, so the next start comes up in the new language.
saved = m.load_config()
if saved.get("language") != other:
    problems.append(f"the settings file says {saved.get('language')!r}")

# ── and back again ──────────────────────────────────────────────────────────
app.set_language(start)
app.update()
lock = app.lock
if lock.var_vin.get() != "WBS21DM0408F91146":
    problems.append("the VIN was lost on the way back")
if dme_text.t("nav.lock") != app.shell.nav.label_of("lock"):
    problems.append("the navigation did not come back")

app.destroy()

if problems:
    for line in problems:
        print("FAIL:", line)
    sys.exit(1)
print(f"switched {start} -> {other} -> {start}, nothing lost")
print("SMOKE TEST PASSED")
