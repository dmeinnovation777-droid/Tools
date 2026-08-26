"""
Does the window stay alive while it works?

3.0.0 ran the whole pre-flight in the window thread, 350 ms after every
keystroke in the VIN field: reading 16 MB, diffing it, searching both images
for program ids, mapping the result onto the XDF. On a real 8 MB S58 job that
is about a second, and typing a VIN is seventeen of them.

This test builds a real 8 MB pair and measures. It fails if the expensive half
comes back into the window thread, if it runs for something typed, or if it
runs twice for the same file.

    xvfb-run -a -s "-screen 0 1120x880x24" python tests/smoke_gui_responsive.py
"""
import os
import random
import sys
import tempfile
import textwrap
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORK = tempfile.mkdtemp(prefix="fluid_smoke_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(WORK, "config")

import dme_app          # noqa: E402
import dme_ui as ui     # noqa: E402
import mhd_lock_tool as m   # noqa: E402

assert dme_app.TK_AVAILABLE, "tkinter missing"

# Typing may never block the window for longer than this. The old code took
# about a second per keystroke; anything in this range is a different animal.
BUDGET_MS = 60
SIZE = 8 * 1024 * 1024
ROM_ID = "00005C6414C808"

SAMPLE_XDF = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <XDFFORMAT version="1.80"><XDFHEADER><deftitle>S58</deftitle>
      <BASEOFFSET offset="0" subtract="0" />
      <REGION type="0xFFFFFFFF" startaddress="0x0" size="0x800000" name="Binary File" />
    </XDFHEADER>
    <XDFTABLE><title>Boost target</title><XDFAXIS id="z">
      <EMBEDDEDDATA mmedaddress="0x1000" mmedelementsizebits="16" mmedrowcount="16"
        mmedcolcount="16" /></XDFAXIS></XDFTABLE>
    </XDFFORMAT>
    """)

failures = []


def note(line):
    print("   ", line, flush=True)


# ── a real pair, the size of a real job ─────────────────────────────────────
CAR = os.path.join(WORK, "Kunde")
os.makedirs(CAR, exist_ok=True)
rng = random.Random(1)
stock = bytearray(rng.randbytes(SIZE))
stock[0x1000:0x1007] = bytes.fromhex(ROM_ID)
tuned = bytearray(stock)
for _ in range(178):
    off = rng.randrange(0, SIZE - 128)
    for i in range(73):
        tuned[off + i] ^= 0x5A

STOCK = os.path.join(CAR, f"{ROM_ID}_original.bin")
TUNED_A = os.path.join(CAR, "MAP1 E45 Flammes MAP2 E30.bin")
TUNED_B = os.path.join(CAR, "Stage 2 MAP1 E45.bin")
open(STOCK, "wb").write(bytes(stock))
open(TUNED_A, "wb").write(bytes(tuned))
tuned[0x2000:0x2020] = b"\xAA" * 32
open(TUNED_B, "wb").write(bytes(tuned))
open(os.path.join(CAR, f"{ROM_ID}.xdf"), "w").write(SAMPLE_XDF)
open(os.path.join(CAR, "Gen.toolkey"), "wb").write(b"\x00" * 128)
print(f"fixture        : two {SIZE // 1024 // 1024} MB images, 178 changed places")

# ── watch where and how often the expensive half runs ───────────────────────
scans = []
real_scan = m.scan_files


def counted_scan(job, definition=None):
    scans.append((threading.current_thread() is threading.main_thread(),
                  job.tuned_bin))
    return real_scan(job, definition)


m.scan_files = counted_scan

app = dme_app.DmeApp()
app.geometry("1120x820")
app.update()
lock = app.lock
lock.var_cfg_toolkey.set(os.path.join(CAR, "Gen.toolkey"))
lock.save_settings()
app.update()


def wait_idle(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.update()
        if not lock.is_busy():
            app.update()
            return True
        time.sleep(0.01)
    return False


def pump(seconds):
    """Keep the window alive for a while and report the worst hiccup."""
    worst = 0.0
    end = time.time() + seconds
    while time.time() < end:
        started = time.perf_counter()
        app.update()
        worst = max(worst, (time.perf_counter() - started) * 1000)
        time.sleep(0.005)
    return worst


# ── how long the expensive half actually takes, for the record ──────────────
started = time.perf_counter()
job = m.LockJob(vin="", stock_bin=STOCK, tuned_bin=TUNED_A,
                xdf=os.path.join(CAR, f"{ROM_ID}.xdf"), toolkey="", output_dir=CAR)
real_scan(job, m.definition_for(job.xdf))
cost = (time.perf_counter() - started) * 1000
note(f"one scan of this pair costs {cost:.0f} ms")
m.forget_files()
scans.clear()

# ── picking a file: the window may not stop ─────────────────────────────────
started = time.perf_counter()
lock.var_tuned.set(TUNED_A)
app.update()
picked = (time.perf_counter() - started) * 1000
worst = max(picked, pump(0.4))
assert wait_idle(), "the scan never finished"
note(f"picking a file blocked the window for {worst:.1f} ms")
if worst > BUDGET_MS:
    failures.append(f"picking a file blocked for {worst:.0f} ms")
if not scans:
    failures.append("no scan ran at all")
elif any(main for main, _ in scans):
    failures.append("the scan ran in the window thread")
else:
    note(f"the scan ran off the window, {len(scans)} time(s)")

# ── typing the VIN: not one byte may be read ────────────────────────────────
before = len(scans)
typed = 0.0
for char in "WBS21DM0408F91146":
    started = time.perf_counter()
    lock.var_vin.set(lock.var_vin.get() + char)
    app.update()
    typed = max(typed, (time.perf_counter() - started) * 1000)
# Well past the old 350 ms delay: if anything was still owed, it lands here.
idle = pump(1.0)
assert wait_idle(), "something is still running after typing"
note(f"typing 17 characters: worst keystroke {typed:.1f} ms, "
     f"worst moment in the second after {idle:.1f} ms")
worst = max(typed, idle)
if worst > BUDGET_MS:
    failures.append(f"typing blocked the window for {worst:.0f} ms")
if len(scans) != before:
    failures.append(f"typing a VIN started {len(scans) - before} scan(s)")
else:
    note("typing the VIN started no scan")

# ── the customer name is the file name, nothing more ────────────────────────
before = len(scans)
for char in "Mathias":
    lock.var_customer.set(lock.var_customer.get() + char)
    app.update()
pump(1.0)
assert wait_idle()
if len(scans) != before:
    failures.append(f"typing a customer name started {len(scans) - before} scan(s)")
else:
    note("typing the customer name started no scan")

# ── the verdict is there, and it is the right one ───────────────────────────
report = lock._recheck()
if report is None:
    failures.append("no verdict after the scan")
else:
    if not report.ok:
        failures.append(f"the job did not pass: {[str(i) for i in report.errors]}")
    if report.changed_bytes != 12994:
        failures.append(f"changed bytes {report.changed_bytes}, expected 12994")
    else:
        note(f"verdict: {report.changed_bytes} changed bytes, "
             f"{len(report.regions)} regions")

# ── a second file overtakes the first ───────────────────────────────────────
scans.clear()
lock.var_tuned.set(TUNED_B)
app.update()
lock.var_tuned.set(TUNED_A)            # changed my mind before the first landed
app.update()
assert wait_idle(), "the scan never finished"
job_now = lock._current_job()
if lock._scan is None or not lock._scan.matches(job_now):
    failures.append("the answer in hand does not belong to the file on screen")
elif lock._scan.tuned != TUNED_A:
    failures.append(f"a stale answer won: {os.path.basename(lock._scan.tuned)}")
else:
    note("the newer file won, the overtaken answer was dropped")

# ── the page slides, and it slides at a rate worth having ───────────────────
frames = []
original_tick = ui.Animation._tick


def counting_tick(self):
    frames.append(time.perf_counter())
    return original_tick(self)


ui.Animation._tick = counting_tick
frames.clear()
started = time.perf_counter()
app.shell.select("batch")
while ui._RUNNING and time.perf_counter() - started < 2.0:
    app.update()
    time.sleep(0.004)
span = time.perf_counter() - started
ui.Animation._tick = original_tick
if len(frames) < 5:
    failures.append(f"the page transition ran {len(frames)} frames")
else:
    note(f"page transition: {len(frames)} frames in {span * 1000:.0f} ms "
         f"({len(frames) / max(span, 0.001):.0f} a second)")
app.shell.settle()
app.update()

# ── the wheel glides instead of jumping ─────────────────────────────────────
app.shell.select("settings")
app.update()
app.shell.settle()
app.update()
scroll = app.pages["settings"].scroll
top_before = scroll.canvas.canvasy(0)
scroll.wheel(-1)
started = time.perf_counter()
while scroll._glide_after is not None and time.perf_counter() - started < 2.0:
    app.update()
    time.sleep(0.004)
travelled = scroll.canvas.canvasy(0) - top_before
if travelled <= 0:
    failures.append("one notch of the wheel moved the page nowhere")
else:
    note(f"one notch of the wheel coasted {travelled:.0f} px "
         f"in {(time.perf_counter() - started) * 1000:.0f} ms")

# ── and the wheel reaches the page from anywhere on it ─────────────────────
# The old rule bound the wheel while the pointer was over the canvas, and
# entering any content makes the canvas report that the pointer left. So the
# page scrolled only over empty space. It is routed by what is under the
# pointer now, which is what this checks.
scroll.settle()
scroll.canvas.yview_moveto(0)
app.update()
victim = None
for child in scroll.inner.winfo_children():
    victim = child
    break
if victim is None:
    failures.append("the settings page has no content to aim at")
else:
    top_before = scroll.canvas.canvasy(0)
    for sequence, extra in (("<Button-5>", {}), ("<MouseWheel>", {"delta": -120})):
        try:
            victim.event_generate(sequence, x=5, y=5, **extra)
        except Exception:
            continue
        started = time.perf_counter()
        while scroll._glide_after is not None and time.perf_counter() - started < 2.0:
            app.update()
            time.sleep(0.004)
        if scroll.canvas.canvasy(0) > top_before:
            note(f"the wheel over the content scrolled the page ({sequence})")
            break
    else:
        failures.append("the wheel over the content did not scroll the page")

app.destroy()
m.scan_files = real_scan

if failures:
    for line in failures:
        print("FAIL:", line)
    sys.exit(1)
print("SMOKE TEST PASSED")
