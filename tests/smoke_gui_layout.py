"""
Does the page stand still when you switch pages?

The complaint was "die Zeilen verrutschen": every click on the sidebar moved
the content up or down and the whole page reflowed on the way. Three causes,
all of them measurable from here:

  * the header reserved room for the current page's subtitle only, so a two
    line subtitle followed by a three line one pushed everything down,
  * a page was packed and the others unpacked on every click, and a freshly
    packed frame is one pixel wide for an instant, so every wrapped label
    reflowed before settling,
  * the scrollbar took a column of its own, so it changed the canvas width
    when it appeared, which rewrapped the text, which changed the height.

This test walks every page of both tools and asserts that the content sits at
exactly the same pixel each time. It fails on the old code and passes on the
new one.

    xvfb-run -a -s "-screen 0 1100x860x24" python tests/smoke_gui_layout.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORK = tempfile.mkdtemp(prefix="layout_smoke_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(WORK, "config")

import dme_ui as ui            # noqa: E402
import autotuner_tool as a     # noqa: E402
import mhd_lock_tool as m      # noqa: E402

assert m.TK_AVAILABLE and a.TK_AVAILABLE, "tkinter missing"

failures = []


def probe(app, keys, size):
    """Where does each page's content sit, and does it stay there?"""
    app.geometry(size)
    app.update()

    seen = {}
    for key in keys:
        app.tabs.select(key)
        app.update()
        page = app.pages[key]
        seen[key] = {
            "host": app.shell.host.winfo_rooty(),
            "page": page.winfo_rooty(),
            "body": page.body.winfo_rooty(),
            "width": page.winfo_width(),
            "bar": page.scroll.scrollbar.winfo_manager(),
        }

    # Every page starts at the same pixel: the header reserves one height for
    # all of them, whatever their subtitle says.
    tops = set(v["page"] for v in seen.values())
    if len(tops) != 1:
        failures.append(f"{app.__class__.__name__}: pages start at {sorted(tops)}, "
                        f"the header changes height between pages")

    widths = set(v["width"] for v in seen.values())
    if len(widths) != 1:
        failures.append(f"{app.__class__.__name__}: pages are {sorted(widths)} px wide, "
                        f"they should all fill the host")

    for key, v in seen.items():
        if v["bar"] == "pack":
            failures.append(f"{app.__class__.__name__}/{key}: the scrollbar is packed, "
                            f"so showing it steals width from the content")

    # Go round again. Nothing may have moved in the meantime.
    for key in list(keys) + list(reversed(keys)):
        app.tabs.select(key)
        app.update()
        page = app.pages[key]
        for name, value in (("page", page.winfo_rooty()), ("body", page.body.winfo_rooty()),
                            ("host", app.shell.host.winfo_rooty())):
            if value != seen[key][name]:
                failures.append(f"{app.__class__.__name__}/{key}: {name} moved from "
                                f"{seen[key][name]} to {value} on the second visit")
    return seen


# ── The tool with the three pages and three different subtitles ─────────────
lock = m.MhdLockTool()
seen = probe(lock, ("lock", "batch", "settings"), "1040x820")
print("MHD Lock Tool   :", ", ".join(f"{k} y={v['page']}" for k, v in seen.items()))

# A subtitle that grows must not move the page either: the header already keeps
# room for the longest one of all pages.
before = lock.pages["lock"].winfo_rooty()
lock.shell.set_subtitle("lock", m.PREPARE_SUBTITLE)
lock.update()
after = lock.pages["lock"].winfo_rooty()
if before != after:
    failures.append(f"MhdLockTool: rewording the subtitle moved the page {before} -> {after}")
print("subtitle swap   : page stays at", after)
lock.destroy()

# ── And the two page tool ───────────────────────────────────────────────────
auto = a.AutoTunerTool()
seen = probe(auto, ("z2b", "b2z"), "980x780")
print("AutoTuner Tool  :", ", ".join(f"{k} y={v['page']}" for k, v in seen.items()))

# _active() no longer asks a widget whether it is mapped - every page is.
for key in ("b2z", "z2b"):
    auto.tabs.select(key)
    auto.update()
    if auto._active() != key:
        failures.append(f"AutoTunerTool: _active() says {auto._active()!r}, not {key!r}")
print("active page     : reported correctly on both pages")
auto.destroy()

if failures:
    for line in failures:
        print("FAIL:", line)
    sys.exit(1)
print("SMOKE TEST PASSED")
