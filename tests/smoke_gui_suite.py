"""
Headless GUI smoke test for the DME Innovation Tools launcher.

    xvfb-run -a -s "-screen 0 880x560x24" python tests/smoke_gui_suite.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from _screenshot import shoot  # noqa: E402

import dme_suite as suite  # noqa: E402

assert suite.TK_AVAILABLE, "tkinter missing"

started = []
suite.launch = lambda command: started.append(command)   # no real child processes here

app = suite.SuiteLauncher()
app.geometry("880x560")
app.update()

for tool in suite.TOOLS:
    app._open(tool)
    app.update()
    assert started[-1][-1].endswith(tool["script"]), started[-1]
    assert tool["name"] in app.banner._text.cget("text")
    print(f"{tool['name']}: OK")

shoot("suite")
app.destroy()
print("SMOKE TEST PASSED")
