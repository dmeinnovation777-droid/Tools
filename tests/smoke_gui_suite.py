"""
Headless GUI smoke test for the three ways into the one app.

The Start menu keeps three entries: the app itself, the MHD Lock Tool and the
AutoTuner Backup Tool. They are one program now, so all three have to open the
same window and land on the right area.

    xvfb-run -a -s "-screen 0 1120x860x24" python tests/smoke_gui_suite.py
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WORK = tempfile.mkdtemp(prefix="suite_smoke_")
os.environ["XDG_CONFIG_HOME"] = os.path.join(WORK, "config")

from _screenshot import shoot  # noqa: E402

import dme_app  # noqa: E402
import dme_suite as suite  # noqa: E402

assert dme_app.TK_AVAILABLE, "tkinter missing"

# The plain start, then one per Start menu entry.
wanted = [(None, "lock")] + [(tool["key"], tool["page"]) for tool in suite.TOOLS]

for key, page in wanted:
    start = suite.tool_by_key(key)["page"] if key else "lock"
    assert start == page, f"{key} should open {page}, not {start}"
    app = dme_app.DmeApp(start_page=start)
    app.geometry("1120x820")
    app.update()
    assert app.shell.active == page, f"{key or 'no flag'} opened {app.shell.active}"
    # Every area exists and can be reached, from wherever the app opened.
    for area in dme_app.AREAS:
        app.shell.select(area)
        app.update()
        assert app.shell.active == area
        assert app.pages[area].winfo_manager() == "place", area
    app.shell.select(page)
    app.update()
    print(f"{key or 'no flag'}: opens on {page}, all four areas reachable")
    if key is None:
        shoot("suite")
    app.destroy()

print("SMOKE TEST PASSED")
