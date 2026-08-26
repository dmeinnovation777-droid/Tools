"""
DME Innovation Tools · the application
=====================================

One window. Four areas across the top: Lock, Batch, Backup, Settings. Inside
each area the same shape, a chain of steps from top to bottom, and whatever a
step produces appears inside that step. Nothing opens a second window.

The two tools are no longer programs, they are controllers: `LockUI` from
mhd_lock_tool builds the Lock and Batch pages, `BackupUI` from autotuner_tool
builds the Backup page, and both write into the one status line at the bottom.
Their engines are untouched by any of this.

The language switch rebuilds the pages instead of relabelling every widget.
Values live on the controllers in tk variables, not in the widgets, so files,
VIN, queue and settings survive the rebuild; only the log window starts over,
and the switch says so.

© DME Innovation
"""

import sys

import dme_brand as brand
from dme_text import t
import dme_text as text

try:
    import tkinter as tk

    import dme_ui as ui
    TK_AVAILABLE = True
except ImportError:  # headless box / python3-tk not installed
    tk = ui = None
    TK_AVAILABLE = False

APP_NAME = brand.SUITE
APP_VERSION = brand.VERSION

# The areas, in the order they sit in the bar. "page" is who builds them.
AREAS = ("lock", "batch", "backup", "settings")
START_PAGES = {"mhd": "lock", "autotuner": "backup"}

_TkBase = tk.Tk if TK_AVAILABLE else object


class DmeApp(_TkBase):
    """The window. It owns the shell, the config and the language."""

    #: How big the window opens. Set before anything is built, not after.
    DEFAULT_SIZE = (1120, 800)

    def __init__(self, start_page="lock", geometry=None):
        super().__init__()
        # Out of sight until it is finished. Assembling a window that is
        # already on screen is what made it wobble on open: it appeared at its
        # natural size, jumped to 1120 x 800, and every wrapped text reflowed
        # afterwards, in front of you.
        self.withdraw()
        ui.init(self)
        self.title(f"{APP_NAME} · {brand.VENDOR}")
        self.configure(bg=ui.BG)
        self.minsize(ui.px(980), ui.px(700))
        # The size comes first, so every text is wrapped to the width it will
        # really have, the first time, instead of to whatever tk guessed.
        self.geometry(geometry or "{}x{}".format(ui.px(self.DEFAULT_SIZE[0]),
                                                 ui.px(self.DEFAULT_SIZE[1])))
        brand.apply_window_icon(self)

        # The lock tool owns the settings file; the whole app shares it.
        import mhd_lock_tool as lock_tool
        self._lock_tool = lock_tool
        self.config_data = lock_tool.load_config()
        text.set_language(self.config_data.get("language", text.DEFAULT_LANGUAGE))

        self.pages = {}
        self._start_page = start_page if start_page in AREAS else "lock"
        self._build()
        self._compose()

    def _compose(self):
        """Lay it all out, settle it, and only then show it.

        What appears is one finished picture. Nothing wraps, jumps, fades or
        resizes after the window is visible.
        """
        self.update_idletasks()
        self.deiconify()
        self.update()            # map, take the resize, wrap everything to it
        # One width settling can change another, which owes a second pass.
        # Five is far more than the two this layout actually needs.
        for _ in range(5):
            ui.finish_animations()   # the rings fade on the way in, not after
            if not ui.flush_resize():
                break
            self.update_idletasks()
        self.update_idletasks()

    # ── build ───────────────────────────────────────────────────────────────
    def _nav(self):
        return [{"key": key, "label": t(f"nav.{key}"), "title": t(f"{key}.title"),
                 "subtitle": self._subtitle(key), "subtitles": self._subtitles(key)}
                for key in AREAS]

    def _subtitle(self, key):
        if key == "lock":
            return t("lock.sub_prepare") if self._prepare_only() else t("lock.sub")
        if key == "batch":
            return t("batch.sub_prepare") if self._prepare_only() else t("batch.sub")
        if key == "backup":
            return t("backup.sub.z2b")
        return t("settings.sub")

    def _subtitles(self, key):
        """Every wording a page can take, so the header reserves room once."""
        if key == "lock":
            return [t("lock.sub"), t("lock.sub_prepare")]
        if key == "batch":
            return [t("batch.sub"), t("batch.sub_prepare")]
        if key == "backup":
            return [t("backup.sub.z2b"), t("backup.sub.b2z")]
        return [t("settings.sub")]

    def _prepare_only(self):
        return bool(self.config_data.get("prepare_only", False))

    def _build(self):
        self.shell = ui.Shell(self, brand, APP_NAME, APP_VERSION, self._nav(),
                              self._show_page)
        self.shell.pack(fill=tk.BOTH, expand=True)
        self.status = self.shell.status
        self.host = self.shell.host
        # Kept for the tests and for anything that still says tabs.select(...)
        self.tabs = self.shell

        import autotuner_tool
        self.lock = self._lock_tool.LockUI(self)
        self.backup = autotuner_tool.BackupUI(self)
        self._mount()

    def _mount(self):
        pages = dict(self.lock.build_pages())
        pages["backup"] = self.backup.build_page()
        pages["settings"] = self._build_settings()
        self.pages = pages
        self.shell.mount(self.pages)
        self.shell.select(self._start_page)
        self.lock.after_mount()
        self.backup.after_mount()

    def _show_page(self, key):
        self.shell.show(key)
        # The switch beside the title belongs to one page, so it travels with it.
        switch = getattr(self.backup, "switch", None)
        if switch is not None:
            if key == "backup":
                switch.pack()
                self.backup.on_shown()
            else:
                switch.pack_forget()

    # ── settings ────────────────────────────────────────────────────────────
    def _build_settings(self):
        page = ui.Page(self.host, width=860)

        general = ui.GroupedList(page.body, t("settings.group.general"))
        general.pack(fill=tk.X, pady=(0, ui.px(20)))
        row = general.row()
        line = tk.Frame(row, bg=ui.CARD)
        line.pack(fill=tk.X)
        copy = tk.Frame(line, bg=ui.CARD)
        copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(copy, text=t("word.language"), bg=ui.CARD, fg=ui.TEXT,
                 font=ui.f("body"), anchor="w").pack(fill=tk.X)
        note = tk.Label(copy, text=t("word.language_hint"), bg=ui.CARD,
                        fg=ui.TEXT_FAINT, font=ui.f("small"), anchor="w",
                        justify="left")
        note.pack(fill=tk.X, pady=(ui.px(2), 0))
        ui.wrap_to_parent(note, inset=ui.px(190))
        self.lang_switch = ui.Segmented(
            line, [(code, text.LANGUAGE_NAMES[code]) for code in text.LANGUAGES],
            command=self.set_language, bg=ui.CARD)
        self.lang_switch.pack(side=tk.RIGHT, padx=(ui.px(14), 0))
        self.lang_switch.select(text.language(), notify=False)

        self.lock.build_settings(page)

        self.var_settings_summary = tk.StringVar(value=t("settings.saved"))
        page.summary(self.var_settings_summary)
        self.lock.bind_settings_summary(self.var_settings_summary)
        ui.button(page.action_row, t("settings.save_now"), self.lock.save_settings,
                  variant="primary", size="lg", bg=ui.SURFACE).pack(side=tk.RIGHT)
        ui.button(page.action_row, t("settings.reset"), self.lock.reset_settings,
                  variant="ghost", size="lg", bg=ui.SURFACE).pack(
                      side=tk.RIGHT, padx=(0, ui.px(10)))
        return page

    # ── language ────────────────────────────────────────────────────────────
    def set_language(self, code):
        if code == text.language():
            return
        text.set_language(code)
        self.config_data["language"] = code
        self._lock_tool.save_config(self.config_data)
        self.rebuild()

    def rebuild(self):
        """Throw the pages away and build them again in the new language."""
        active = self.shell.active or self._start_page
        self._start_page = active
        # Nothing may be in flight while the pages it moves are destroyed.
        ui.stop_animations()
        for page in self.pages.values():
            page.destroy()
        self.pages = {}
        for key in AREAS:
            self.shell.set_label(key, t(f"nav.{key}"))
            self.shell.set_title(key, t(f"{key}.title"), self._subtitle(key),
                                 self._subtitles(key))
        # select() short circuits on the page that is already active, and the
        # freshly built pages have to be told which one that is.
        self.shell._active = None
        self._mount()

    # ── shared helpers the controllers use ──────────────────────────────────
    # The bar has room for a word, the status line for a sentence.
    STATE_WORDS = {"ok": "word.ready", "busy": "word.running",
                   "error": "word.failed", "warn": "word.waiting",
                   "idle": "word.ready"}

    def set_status(self, message, tone="idle"):
        self.status.set(message, tone)
        self.shell.nav.set_state(t(self.STATE_WORDS.get(tone, "word.ready")), tone)

    def go(self, key):
        self.shell.select(key)

    def destroy(self):
        ui.stop_animations()
        for controller in (getattr(self, "lock", None), getattr(self, "backup", None)):
            if controller is not None and hasattr(controller, "shutdown"):
                controller.shutdown()
        super().destroy()


def main(start_page="lock") -> int:
    if not TK_AVAILABLE:
        print(f"{APP_NAME} v{APP_VERSION} · {brand.VENDOR}", file=sys.stderr)
        print("tkinter is not available in this Python installation.", file=sys.stderr)
        print("Windows/macOS: reinstall Python and tick 'tcl/tk and IDLE'.", file=sys.stderr)
        print("Debian/Ubuntu: sudo apt install python3-tk", file=sys.stderr)
        return 1
    ui.enable_dpi_awareness()
    app = DmeApp(start_page=start_page)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
