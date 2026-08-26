"""
Does the page stand still when you switch areas?

The complaint was "die Zeilen verrutschen": every click in the navigation moved
the content up or down and the whole page reflowed on the way. Three causes,
all of them measurable from here:

  * the header reserved room for the current page's subtitle only, so a two
    line subtitle followed by a three line one pushed everything down,
  * a page was packed and the others unpacked on every click, and a freshly
    packed frame is one pixel wide for an instant, so every wrapped label
    reflowed before settling,
  * the scrollbar took a column of its own, so it changed the canvas width
    when it appeared, which rewrapped the text, which changed the height.

This test walks every area of the app and asserts that the content sits at
exactly the same pixel each time, in both languages. It fails on 2.3.3 and
passes from 2.3.4 on.

    xvfb-run -a -s "-screen 0 1120x880x24" python tests/smoke_gui_layout.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORK = tempfile.mkdtemp(prefix="layout_smoke_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(WORK, "config")

import dme_app   # noqa: E402
import dme_text  # noqa: E402

assert dme_app.TK_AVAILABLE, "tkinter missing"

failures = []
AREAS = dme_app.AREAS


def probe(app, label):
    """Where does each area's content sit, and does it stay there?"""
    app.update()
    seen = {}
    for key in AREAS:
        app.shell.select(key)
        app.update()
        page = app.pages[key]
        seen[key] = {
            "host": app.shell.host.winfo_rooty(),
            "page": page.winfo_rooty(),
            "body": page.body.winfo_rooty(),
            "width": page.winfo_width(),
            "bar": page.scroll.scrollbar.winfo_manager(),
        }

    # Every area starts at the same pixel: the header reserves one height for
    # all of them, whatever their subtitle says.
    tops = set(v["page"] for v in seen.values())
    if len(tops) != 1:
        failures.append(f"{label}: areas start at {sorted(tops)}, the header "
                        f"changes height between them")

    widths = set(v["width"] for v in seen.values())
    if len(widths) != 1:
        failures.append(f"{label}: areas are {sorted(widths)} px wide, they should "
                        f"all fill the host")

    for key, value in seen.items():
        if value["bar"] == "pack":
            failures.append(f"{label}/{key}: the scrollbar is packed, so showing it "
                            f"steals width from the content")

    # Go round again. Nothing may have moved in the meantime.
    for key in list(AREAS) + list(reversed(AREAS)):
        app.shell.select(key)
        app.update()
        page = app.pages[key]
        for name, value in (("page", page.winfo_rooty()),
                            ("body", page.body.winfo_rooty()),
                            ("host", app.shell.host.winfo_rooty())):
            if value != seen[key][name]:
                failures.append(f"{label}/{key}: {name} moved from {seen[key][name]} "
                                f"to {value} on the second visit")
    return seen


app = dme_app.DmeApp()
app.geometry("1120x820")
seen = probe(app, "German")
print("German  :", ", ".join(f"{k} y={v['page']}" for k, v in seen.items()))

# A setting that rewords the header must not move the page either: the header
# already keeps room for the longest subtitle any area can show.
app.shell.select("lock")
app.update()
before = app.pages["lock"].winfo_rooty()
app.lock.var_prepare_only.set(True)
app.lock.save_settings()
app.update()
after = app.pages["lock"].winfo_rooty()
if before != after:
    failures.append(f"folder mode moved the page {before} -> {after}")
print("folder mode: page stays at", after)
app.lock.var_prepare_only.set(False)
app.lock.save_settings()
app.update()

# The other language has longer words in places. It may not move anything.
app.set_language("en")
seen_en = probe(app, "English")
print("English :", ", ".join(f"{k} y={v['page']}" for k, v in seen_en.items()))
app.destroy()

if failures:
    for line in failures:
        print("FAIL:", line)
    sys.exit(1)
print("SMOKE TEST PASSED")
