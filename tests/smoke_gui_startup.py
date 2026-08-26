"""
Does anything move after the window is already on screen?

3.1.0 opened badly. The window was built at its natural size and only then told
to be 1120 x 800, and the debounce added in the same version made every wrapped
text wait fifty milliseconds before it reflowed. So the app appeared, stood
there, and then rearranged itself. Measured on this fixture, six things changed
after the first frame, the content column of every area among them:

    wraplength       750  ->  1088
    lock body w      707  ->   916
    batch body w     892  ->   979
    backup body w    716  ->   937
    settings body w  864  ->   895
    hint wrap        670  ->   856

This test takes the same reading at the moment the window appears, pumps the
event loop for half a second, and takes it again. Anything that differs is a
wobble. It fails against 3.1.0 and passes from 3.1.1 on.

    xvfb-run -a -s "-screen 0 1200x900x24" python tests/smoke_gui_startup.py
"""
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORK = tempfile.mkdtemp(prefix="startup_smoke_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(WORK, "config")

import dme_app      # noqa: E402
import dme_ui as ui  # noqa: E402

assert dme_app.TK_AVAILABLE, "tkinter missing"

failures = []


def probe(app):
    """Everything a wobble would disturb, in one reading."""
    out = {
        "window size": (app.winfo_width(), app.winfo_height()),
        "subtitle height": app.shell._subtitle.winfo_height(),
        "subtitle wrap": app.shell._subtitle.cget("wraplength"),
        "tuned hint wrap": app.lock.row_tuned.hint.cget("wraplength"),
        "tuned hint height": app.lock.row_tuned.hint.winfo_height(),
        "step 1 ring y": app.lock.step_file.winfo_rooty(),
    }
    for key, page in app.pages.items():
        out[f"{key}: content top"] = page.body.winfo_rooty()
        out[f"{key}: content width"] = page.body.winfo_width()
        out[f"{key}: scrollbar"] = page.scroll.scrollbar.winfo_manager() or "none"
    return out


def pump(app, seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.005)


def compare(label, first, second):
    moved = [(key, first[key], second[key]) for key in first
             if first[key] != second[key]]
    if moved:
        for key, before, after in moved:
            failures.append(f"{label}: {key} went {before} -> {after} after the "
                            f"window was already visible")
    else:
        print(f"    {label}: nothing moved")
    return moved


# ── opening the app ─────────────────────────────────────────────────────────
# Exactly the path dme_app.main() takes, minus the mainloop: the size belongs
# to the window, not to the caller, so there is no resize after the build.
app = dme_app.DmeApp(start_page="lock")
app.update()
first = probe(app)
print(f"opened at {first['window size'][0]} x {first['window size'][1]}")
pump(app, 0.6)
compare("on open", first, probe(app))

expected = (ui.px(dme_app.DmeApp.DEFAULT_SIZE[0]), ui.px(dme_app.DmeApp.DEFAULT_SIZE[1]))
if first["window size"] != expected:
    failures.append(f"opened at {first['window size']}, not at {expected}")

# ── and the language switch rebuilds the pages, so it must land as cleanly ──
app.set_language("en")
app.update()
first_en = probe(app)
pump(app, 0.6)
compare("after the language switch", first_en, probe(app))

# ── switching areas must not disturb the resting places either ──────────────
for key in dme_app.AREAS:
    app.shell.select(key)
    app.update()
    app.shell.settle()
    app.update()
before = probe(app)
pump(app, 0.4)
compare("after walking every area", before, probe(app))

app.destroy()

if failures:
    for line in failures:
        print("FAIL:", line)
    sys.exit(1)
print("SMOKE TEST PASSED")
