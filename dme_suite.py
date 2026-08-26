"""
DME Innovation Tools · the entry point
======================================

There is one program and one window. This file is only the door: it reads
``--tool`` and tells the app which area to open on.

    DME Innovation Tools.exe                    opens on Lock
    DME Innovation Tools.exe --tool mhd         opens on Lock
    DME Innovation Tools.exe --tool autotuner   opens on Backup

Up to 2.3.4 this was a launcher with a window of its own that started one of
three programs. The three are one now, so the launcher screen is gone; the
Start menu keeps all three entries because they are three ways into the same
app, and that is what the entries below describe.

© DME Innovation
"""

import sys

import dme_brand as brand

APP_NAME = brand.SUITE
APP_VERSION = brand.VERSION

TOOL_FLAG = "--tool"

# key (--tool argument), the Start menu name, the module that owns the area,
# and the area the app opens on.
TOOLS = [
    {
        "key": "autotuner",
        "name": "AutoTuner Backup Tool",
        "module": "autotuner_tool",
        "script": "autotuner_tool.py",
        "page": "backup",
    },
    {
        "key": "mhd",
        "name": "MHD Lock Tool",
        "module": "mhd_lock_tool",
        "script": "mhd_lock_tool.py",
        "page": "lock",
    },
]


def tool_by_key(key: str) -> dict | None:
    return next((t for t in TOOLS if t["key"] == key), None)


def run_tool(key: str) -> int:
    """Open the app on the area that key names."""
    tool = tool_by_key(key)
    if tool is None:
        known = ", ".join(t["key"] for t in TOOLS)
        print(f"Unknown tool '{key}'. Known: {known}", file=sys.stderr)
        return 2
    # Imported here, not at module level: importing tkinter is what makes the
    # start slow, and --help must not pay for it.
    import importlib
    return importlib.import_module(tool["module"]).main()


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if TOOL_FLAG in argv:
        index = argv.index(TOOL_FLAG)
        if index + 1 >= len(argv):
            print(f"{TOOL_FLAG} needs a tool key", file=sys.stderr)
            return 2
        return run_tool(argv[index + 1])
    import dme_app
    return dme_app.main("lock")


if __name__ == "__main__":
    sys.exit(main())
