"""
DME Innovation Tools — suite launcher
=====================================

The single entry point installed on the PC: it lists the tools of the suite and
starts the one you pick.

From source it starts the .py next to it. The installed build is ONE executable
that carries all three programs: it starts itself again with --tool <key>, so
Python and tkinter are packed once instead of three times.

© DME Innovation
"""

import os
import subprocess
import sys

import dme_brand as brand

try:
    import tkinter as tk

    import dme_ui as ui
    TK_AVAILABLE = True
except ImportError:  # headless box / python3-tk not installed
    tk = ui = None
    TK_AVAILABLE = False

APP_NAME = brand.SUITE
APP_VERSION = brand.VERSION
APP_TAGLINE = "ECU tooling for the workshop"

# key (--tool argument and module), name, script (source checkout), pitch, bullets
TOOLS = [
    {
        "key": "autotuner",
        "name": "AutoTuner Backup Tool",
        "module": "autotuner_tool",
        "script": "autotuner_tool.py",
        "pitch": "Turn AutoTuner ECU backups into one continuous binary — and back.",
        "bullets": [
            "ZIP / BAK → BIN with the exact part order and offsets",
            "BIN → ZIP with presets, templates and a live size check",
            "Vehicle and ECU metadata written to contents.ini",
        ],
    },
    {
        "key": "mhd",
        "name": "MHD Lock Tool",
        "module": "mhd_lock_tool",
        "script": "mhd_lock_tool.py",
        "pitch": "Lock MHD+ tune files without the folder juggling.",
        "bullets": [
            "Checks VIN, sizes, modifications and XDF coverage up front",
            "Builds a clean working folder and drives your MHD tool",
            "Batch mode with CSV import and a per-job report",
        ],
    },
]


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


TOOL_FLAG = "--tool"


def base_dir() -> str:
    """Where the tools live: next to the .exe, or next to this script."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def python_runner() -> str:
    """Prefer pythonw.exe on Windows so no console window flashes up."""
    if os.name != "nt":
        return sys.executable
    candidate = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return candidate if os.path.isfile(candidate) else sys.executable


def resolve_tool(tool: dict, frozen: bool = None, base: str = None) -> list | None:
    """Command line that starts `tool`, or None when it cannot be found."""
    frozen = is_frozen() if frozen is None else frozen
    base = base_dir() if base is None else base
    if frozen:
        # One executable, three programs. Starting it again with the key runs
        # that tool in its own process, so a crash cannot take the others down.
        return [sys.executable, TOOL_FLAG, tool["key"]]
    target = os.path.join(base, tool["script"])
    return [python_runner(), target] if os.path.isfile(target) else None


def launch(command: list) -> None:
    kwargs = {"cwd": base_dir()}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(command, **kwargs)


def tool_by_key(key: str) -> dict | None:
    return next((t for t in TOOLS if t["key"] == key), None)


def run_tool(key: str) -> int:
    """Hand over to one of the bundled programs."""
    tool = tool_by_key(key)
    if tool is None:
        known = ", ".join(t["key"] for t in TOOLS)
        print(f"Unknown tool '{key}'. Known: {known}", file=sys.stderr)
        return 2
    # Imported here, not at module level: the launcher must still start when a
    # tool fails to import, and from source only the picked one is loaded.
    import importlib
    return importlib.import_module(tool["module"]).main()


_TkBase = tk.Tk if TK_AVAILABLE else object


class SuiteLauncher(_TkBase):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.configure(bg=ui.BG)
        ui.init(self)
        self.minsize(ui.px(820), ui.px(520))
        self.resizable(True, False)
        brand.apply_window_icon(self)
        self._build()

    def _build(self):
        ui.Header(self, brand, APP_NAME, APP_VERSION, APP_TAGLINE).pack(fill=tk.X)

        self.status = ui.StatusBar(self, f"{brand.VENDOR}  ·  v{APP_VERSION}")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        banner_host = tk.Frame(self, bg=ui.BG)
        banner_host.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=(0, 14))
        self.banner = ui.Banner(banner_host)
        self.banner.pack(fill=tk.X)

        body = tk.Frame(self, bg=ui.BG)
        body.pack(fill=tk.BOTH, expand=True, padx=24, pady=(20, 6))
        tk.Label(body, text="Choose a tool", bg=ui.BG, fg=ui.TEXT_DIM,
                 font=ui.f("body"), anchor="w").pack(fill=tk.X, pady=(0, 14))

        grid = tk.Frame(body, bg=ui.BG)
        grid.pack(fill=tk.BOTH, expand=True)
        for index, tool in enumerate(TOOLS):
            self._tool_card(grid, tool).grid(row=0, column=index, sticky="nsew",
                                             padx=(0 if index == 0 else 14, 0))
            grid.grid_columnconfigure(index, weight=1, uniform="tool")
        grid.grid_rowconfigure(0, weight=1)

    def _tool_card(self, parent, tool):
        card = ui.Card(parent, title=tool["name"])
        pitch = tk.Label(card.body, text=tool["pitch"], bg=ui.CARD, fg=ui.TEXT,
                         font=ui.f("body"), anchor="w", justify="left",
                         wraplength=ui.px(330))
        pitch.pack(fill=tk.X, pady=(0, 12))
        ui.wrap_to_parent(pitch, minimum=ui.px(150))
        for bullet in tool["bullets"]:
            row = tk.Frame(card.body, bg=ui.CARD)
            row.pack(fill=tk.X, pady=1)
            tk.Label(row, text="›", bg=ui.CARD, fg=ui.ACCENT_INK,
                     font=ui.f("small")).pack(side=tk.LEFT, padx=(0, 8), anchor="n")
            text = tk.Label(row, text=bullet, bg=ui.CARD, fg=ui.TEXT_DIM,
                            font=ui.f("small"), anchor="w", justify="left",
                            wraplength=ui.px(300))
            text.pack(side=tk.LEFT, fill=tk.X)
            ui.wrap_to_parent(text, minimum=ui.px(130), inset=ui.px(26))

        available = resolve_tool(tool) is not None
        footer = tk.Frame(card.body, bg=ui.CARD)
        footer.pack(side=tk.BOTTOM, fill=tk.X, pady=(ui.px(16), 0))
        tk.Label(footer, text="" if available else "not installed", bg=ui.CARD,
                 fg=ui.ERR, font=ui.f("small")).pack(side=tk.LEFT)
        button = ui.button(footer, "Open  →", lambda t=tool: self._open(t),
                           variant="primary" if available else "secondary", size="lg")
        button.pack(side=tk.RIGHT)
        if not available:
            button.config(state="disabled")
        return card

    def _open(self, tool):
        command = resolve_tool(tool)
        if command is None:
            self.banner.show("error", f"{tool['name']} was not found next to this "
                                      f"launcher ({base_dir()}).")
            return
        try:
            launch(command)
        except OSError as exc:
            self.banner.show("error", f"{tool['name']} could not be started: {exc}")
            self.status.set("Start failed", "error")
            return
        self.banner.show("ok", f"{tool['name']} started.")
        self.status.set(f"Started {tool['name']}", "ok")


def main(argv: list = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if TOOL_FLAG in argv:
        index = argv.index(TOOL_FLAG)
        if index + 1 < len(argv):
            return run_tool(argv[index + 1])
        print(f"{TOOL_FLAG} needs a tool key", file=sys.stderr)
        return 2
    if not TK_AVAILABLE:
        print(f"{APP_NAME} v{APP_VERSION}", file=sys.stderr)
        print("tkinter is not available in this Python installation.", file=sys.stderr)
        print("Windows/macOS: reinstall Python and tick 'tcl/tk and IDLE'.", file=sys.stderr)
        print("Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
        return 1
    ui.enable_dpi_awareness()
    app = SuiteLauncher()
    app.geometry(f"{ui.px(880)}x{ui.px(560)}")
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
