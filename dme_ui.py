"""
DME Innovation desktop UI kit
=============================

A small, dependency-free widget set that gives the DME tools one consistent,
modern look: flat dark surfaces, card-based layout, underline tabs, inline
status banners and a single amber accent taken from the DME logo tile.

Everything here is plain tkinter — no third-party packages, no images beyond
the embedded logo in dme_brand.py.
"""

import os
import subprocess
import sys
import tkinter as tk
from tkinter import font as tkfont

# ─────────────────────────────────────────────────────────────────────────────
# Palette
# ─────────────────────────────────────────────────────────────────────────────
BG = "#0E0F13"          # window / page background
SURFACE = "#15171C"     # header + status bar (must match dme_brand.HEADER_BG)
CARD = "#181B21"        # card background
CARD_ALT = "#1C2027"    # table header / nested rows
HOVER = "#20242C"       # hover fill
BORDER = "#272C35"      # card + control borders
BORDER_SOFT = "#1F242B"
FIELD = "#0F1217"       # entry background
FIELD_BORDER = "#2C323C"

TEXT = "#E9ECF1"
TEXT_DIM = "#8E97A5"
TEXT_FAINT = "#5C6572"

ACCENT = "#FFAA00"      # DME amber
ACCENT_HOVER = "#FFC24D"
ACCENT_PRESS = "#DE9400"
ON_ACCENT = "#12130F"

OK = "#3DDC84"
OK_BG = "#122A1E"
ERR = "#FF6B6B"
ERR_BG = "#2B1719"
WARN = "#FFC857"
WARN_BG = "#2B2314"
INFO = "#63A9FF"
INFO_BG = "#15212F"

_TONE = {
    "ok": (OK, OK_BG),
    "error": (ERR, ERR_BG),
    "warn": (WARN, WARN_BG),
    "info": (INFO, INFO_BG),
    "idle": (TEXT_FAINT, CARD),
    "busy": (ACCENT, WARN_BG),
}

# ─────────────────────────────────────────────────────────────────────────────
# Fonts
# ─────────────────────────────────────────────────────────────────────────────
_UI_CANDIDATES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text",
                  "Helvetica Neue", "Noto Sans", "DejaVu Sans", "Arial"]
_MONO_CANDIDATES = ["Cascadia Mono", "Consolas", "JetBrains Mono", "SF Mono",
                    "Menlo", "DejaVu Sans Mono", "Courier New"]

FONTS: dict[str, tuple] = {}


def _pick(root, candidates, fallback):
    available = {name.lower() for name in tkfont.families(root)}
    for name in candidates:
        if name.lower() in available:
            return name
    return fallback


def init(root) -> None:
    """Resolve fonts and install ttk styles. Call once, right after Tk()."""
    ui = _pick(root, _UI_CANDIDATES, "TkDefaultFont")
    mono = _pick(root, _MONO_CANDIDATES, "TkFixedFont")
    FONTS.update({
        "title":  (ui, 15, "bold"),
        "h1":     (ui, 12, "bold"),
        "h2":     (ui, 10, "bold"),
        "body":   (ui, 10),
        "label":  (ui, 9),
        "small":  (ui, 9),
        "micro":  (ui, 8),
        "tab":    (ui, 10, "bold"),
        "button": (ui, 10, "bold"),
        "mono":   (mono, 9),
        "mono_sm": (mono, 8),
        "mono_lg": (mono, 10),
    })
    _install_ttk(root)


def f(name: str):
    """Font lookup with a safe fallback if init() was not called."""
    return FONTS.get(name, ("TkDefaultFont", 10))


def _install_ttk(root):
    from tkinter import ttk
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    # Thin, flat scrollbar without arrow buttons
    style.layout("DME.Vertical.TScrollbar", [
        ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
            ("Vertical.Scrollbar.thumb", {"expand": 1, "sticky": "nswe"})]})])
    style.configure("DME.Vertical.TScrollbar", troughcolor=BG, bordercolor=BG,
                    background=BORDER, darkcolor=BORDER, lightcolor=BORDER,
                    relief="flat", width=10)
    style.map("DME.Vertical.TScrollbar",
              background=[("active", BORDER_SOFT), ("pressed", TEXT_FAINT)])
    style.layout("DME.Horizontal.TScrollbar", [
        ("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [
            ("Horizontal.Scrollbar.thumb", {"expand": 1, "sticky": "nswe"})]})])
    style.configure("DME.Horizontal.TScrollbar", troughcolor=BG, bordercolor=BG,
                    background=BORDER, darkcolor=BORDER, lightcolor=BORDER,
                    relief="flat", height=10)
    style.configure("DME.Treeview", background=CARD, fieldbackground=CARD,
                    foreground=TEXT, bordercolor=BORDER, borderwidth=0,
                    relief="flat", rowheight=27, font=f("small"))
    style.configure("DME.Treeview.Heading", background=CARD_ALT, foreground=TEXT_FAINT,
                    relief="flat", borderwidth=0, font=f("micro"), padding=(8, 6))
    style.map("DME.Treeview.Heading", background=[("active", HOVER)])
    style.map("DME.Treeview", background=[("selected", BORDER)],
              foreground=[("selected", TEXT)])
    style.layout("DME.Treeview", [("DME.Treeview.treearea", {"sticky": "nswe"})])
    style.configure("DME.TCombobox", fieldbackground=FIELD, background=CARD_ALT,
                    foreground=TEXT, arrowcolor=TEXT_DIM, bordercolor=FIELD_BORDER,
                    lightcolor=FIELD_BORDER, darkcolor=FIELD_BORDER, relief="flat")
    style.map("DME.TCombobox", fieldbackground=[("readonly", FIELD)],
              foreground=[("readonly", TEXT)])


# ─────────────────────────────────────────────────────────────────────────────
# Small helpers
# ─────────────────────────────────────────────────────────────────────────────
def on_hover(widget, normal, active, fg_normal=None, fg_active=None):
    def enter(_=None):
        if str(widget["state"]) == "disabled":
            return
        widget.configure(bg=active, **({"fg": fg_active} if fg_active else {}))

    def leave(_=None):
        widget.configure(bg=normal, **({"fg": fg_normal} if fg_normal else {}))

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", leave, add="+")


def hr(parent, bg=BORDER, pady=0, padx=0):
    line = tk.Frame(parent, bg=bg, height=1)
    line.pack(fill=tk.X, pady=pady, padx=padx)
    return line


def spacer(parent, height=1, bg=None):
    frame = tk.Frame(parent, bg=bg or parent["bg"], height=height)
    frame.pack(fill=tk.X)
    return frame


def reveal_in_file_manager(path: str) -> None:
    """Open the OS file manager with `path` selected (best effort, never raises)."""
    try:
        path = os.path.abspath(path)
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", f"/select,{os.path.normpath(path)}"])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path) or "."])
    except Exception:
        pass


class ToolTip:
    """Lightweight dark tooltip."""

    def __init__(self, widget, text, delay=450):
        self.widget = widget
        self.text = text
        self.delay = delay
        self._after = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _=None):
        self._cancel()
        self._after = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after:
            self.widget.after_cancel(self._after)
            self._after = None

    def _show(self):
        if self._tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 14
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        wrap = tk.Frame(self._tip, bg=BORDER)
        wrap.pack()
        tk.Label(wrap, text=self.text, bg=CARD_ALT, fg=TEXT_DIM, font=f("small"),
                 justify="left", wraplength=320, padx=10, pady=6).pack(padx=1, pady=1)

    def _hide(self, _=None):
        self._cancel()
        if self._tip:
            self._tip.destroy()
            self._tip = None


# ─────────────────────────────────────────────────────────────────────────────
# Buttons
# ─────────────────────────────────────────────────────────────────────────────
_VARIANTS = {
    "primary":   dict(bg=ACCENT, fg=ON_ACCENT, hover=ACCENT_HOVER, press=ACCENT_PRESS),
    "secondary": dict(bg=CARD_ALT, fg=TEXT, hover=HOVER, press=BORDER),
    "ghost":     dict(bg=CARD, fg=TEXT_DIM, hover=HOVER, press=BORDER),
    "danger":    dict(bg=CARD_ALT, fg=ERR, hover=ERR_BG, press=ERR_BG),
}
_SIZES = {
    "lg": dict(padx=20, pady=9, font="button"),
    "md": dict(padx=14, pady=6, font="button"),
    "sm": dict(padx=10, pady=4, font="small"),
}


def button(parent, text, command=None, variant="primary", size="md", bg=None, **kw):
    spec = _VARIANTS[variant]
    dims = _SIZES[size]
    base_bg = spec["bg"] if variant != "ghost" else (bg or parent["bg"])
    btn = tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                    highlightthickness=0, cursor="hand2",
                    bg=base_bg, fg=spec["fg"],
                    activebackground=spec["press"], activeforeground=spec["fg"],
                    disabledforeground=TEXT_FAINT,
                    font=f(dims["font"]), padx=dims["padx"], pady=dims["pady"], **kw)
    on_hover(btn, base_bg, spec["hover"])
    return btn


def icon_button(parent, text, command=None, bg=CARD, fg=TEXT_FAINT, hover_fg=ERR,
                hover_bg=None, font_key="body"):
    btn = tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                    highlightthickness=0, cursor="hand2", bg=bg, fg=fg,
                    activebackground=hover_bg or HOVER, activeforeground=hover_fg,
                    font=f(font_key), padx=6, pady=1)
    on_hover(btn, bg, hover_bg or HOVER, fg_normal=fg, fg_active=hover_fg)
    return btn


# ─────────────────────────────────────────────────────────────────────────────
# Inputs
# ─────────────────────────────────────────────────────────────────────────────
def entry(parent, textvariable, mono=True, width=None, justify="left", **kw):
    ent = tk.Entry(parent, textvariable=textvariable, bg=FIELD, fg=TEXT,
                   insertbackground=ACCENT, relief="flat", bd=0,
                   highlightthickness=1, highlightbackground=FIELD_BORDER,
                   highlightcolor=ACCENT, disabledbackground=CARD_ALT,
                   disabledforeground=TEXT_FAINT, readonlybackground=CARD_ALT,
                   font=f("mono" if mono else "body"), justify=justify, **kw)
    if width:
        ent.configure(width=width)
    return ent


def field_label(parent, text, bg=CARD, fg=TEXT_DIM):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=f("label"), anchor="w")


class PathRow(tk.Frame):
    """Label + path entry + Browse button, stacked the modern way."""

    def __init__(self, parent, label, variable, on_browse, browse_text="Browse",
                 hint=None, bg=CARD, tooltip=None):
        super().__init__(parent, bg=bg)
        field_label(self, label, bg=bg).pack(fill=tk.X, pady=(0, 4))
        row = tk.Frame(self, bg=bg)
        row.pack(fill=tk.X)
        self.entry = entry(row, variable)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)
        self.button = button(row, browse_text, on_browse, variant="secondary", size="md")
        self.button.pack(side=tk.LEFT, padx=(8, 0))
        self.hint_var = tk.StringVar(value=hint or "")
        self.hint = tk.Label(self, textvariable=self.hint_var, bg=bg, fg=TEXT_FAINT,
                             font=f("small"), anchor="w")
        self.hint.pack(fill=tk.X, pady=(5, 0))
        if tooltip:
            ToolTip(self.entry, tooltip)

    def set_hint(self, text, tone="idle"):
        self.hint_var.set(text)
        self.hint.configure(fg=_TONE.get(tone, (TEXT_FAINT, None))[0])


class LabeledEntry(tk.Frame):
    """Compact label-above-field cell for form grids."""

    def __init__(self, parent, label, variable, bg=CARD, mono=True, width=None,
                 placeholder=None):
        super().__init__(parent, bg=bg)
        field_label(self, label, bg=bg).pack(fill=tk.X, pady=(0, 3))
        self.entry = entry(self, variable, mono=mono, width=width)
        self.entry.pack(fill=tk.X, ipady=5)
        if placeholder:
            ToolTip(self.entry, placeholder)


# ─────────────────────────────────────────────────────────────────────────────
# Structure
# ─────────────────────────────────────────────────────────────────────────────
class Card(tk.Frame):
    """Bordered content block with an optional title row."""

    def __init__(self, parent, title=None, hint=None, bg=CARD, pad=(16, 14)):
        super().__init__(parent, bg=bg, highlightbackground=BORDER,
                         highlightthickness=1, bd=0)
        px, py = pad
        self.hint_var = tk.StringVar(value=hint or "")
        if title:
            head = tk.Frame(self, bg=bg)
            head.pack(fill=tk.X, padx=px, pady=(py - 2, 0))
            tk.Label(head, text=title, bg=bg, fg=TEXT, font=f("h2"),
                     anchor="w").pack(side=tk.LEFT)
            self.hint_label = tk.Label(head, textvariable=self.hint_var, bg=bg,
                                       fg=TEXT_FAINT, font=f("small"), anchor="e")
            self.hint_label.pack(side=tk.RIGHT)
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill=tk.BOTH, expand=True, padx=px, pady=(10, py))

    def set_hint(self, text, tone="idle"):
        self.hint_var.set(text)
        if hasattr(self, "hint_label"):
            self.hint_label.configure(fg=_TONE.get(tone, (TEXT_FAINT, None))[0])


class TabBar(tk.Frame):
    """Underline tab strip — the app's primary navigation."""

    def __init__(self, parent, tabs, command, bg=BG):
        super().__init__(parent, bg=bg)
        self._command = command
        self._buttons = {}
        self._underlines = {}
        self._active = None
        strip = tk.Frame(self, bg=bg)
        strip.pack(fill=tk.X, padx=22)
        for key, label in tabs:
            holder = tk.Frame(strip, bg=bg)
            holder.pack(side=tk.LEFT)
            btn = tk.Label(holder, text=label, bg=bg, fg=TEXT_DIM, font=f("tab"),
                           padx=4, pady=11, cursor="hand2")
            btn.pack()
            underline = tk.Frame(holder, bg=bg, height=2)
            underline.pack(fill=tk.X)
            btn.bind("<Button-1>", lambda _e, k=key: self.select(k))
            btn.bind("<Enter>", lambda _e, b=btn, k=key:
                     b.configure(fg=TEXT) if self._active != k else None)
            btn.bind("<Leave>", lambda _e, b=btn, k=key:
                     b.configure(fg=TEXT_DIM) if self._active != k else None)
            self._buttons[key] = btn
            self._underlines[key] = underline
            tk.Frame(strip, bg=bg, width=22).pack(side=tk.LEFT)
        hr(self, bg=BORDER_SOFT)

    def select(self, key):
        if key == self._active:
            return
        self._active = key
        for k, btn in self._buttons.items():
            active = k == key
            btn.configure(fg=TEXT if active else TEXT_DIM)
            self._underlines[k].configure(bg=ACCENT if active else self["bg"])
        self._command(key)


class Banner(tk.Frame):
    """Inline result strip — replaces modal popups for routine feedback."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self._outer_bg = bg
        self._wrap = tk.Frame(self, bg=OK_BG)
        self._bar = tk.Frame(self._wrap, bg=OK, width=3)
        self._bar.pack(side=tk.LEFT, fill=tk.Y)
        inner = tk.Frame(self._wrap, bg=OK_BG)
        inner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._inner = inner
        self._icon = tk.Label(inner, text="", bg=OK_BG, fg=OK, font=f("h2"))
        self._icon.pack(side=tk.LEFT, padx=(12, 8), pady=10)
        self._text = tk.Label(inner, text="", bg=OK_BG, fg=TEXT, font=f("small"),
                              anchor="w", justify="left", wraplength=560)
        self._text.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=10)
        self._action = button(inner, "", None, variant="ghost", size="sm", bg=OK_BG)
        self._close = icon_button(inner, "✕", self.hide, bg=OK_BG, fg=TEXT_FAINT,
                                  hover_fg=TEXT, hover_bg=OK_BG)
        self._visible = False

    def show(self, kind, text, action_text=None, action=None):
        fg, bg = _TONE.get(kind, _TONE["info"])
        icons = {"ok": "✓", "error": "✕", "warn": "!", "info": "i", "busy": "•"}
        self._wrap.configure(bg=bg)
        self._inner.configure(bg=bg)
        self._bar.configure(bg=fg)
        self._icon.configure(bg=bg, fg=fg, text=icons.get(kind, "i"))
        self._text.configure(bg=bg, text=text)
        self._close.configure(bg=bg, activebackground=bg)
        on_hover(self._close, bg, bg, fg_normal=TEXT_FAINT, fg_active=TEXT)
        self._close.pack_forget()
        self._action.pack_forget()
        if action_text and action:
            self._action.configure(text=action_text, command=action, bg=bg,
                                   fg=fg, activebackground=bg, activeforeground=fg)
            on_hover(self._action, bg, bg, fg_normal=fg, fg_active=TEXT)
            self._action.pack(side=tk.RIGHT, padx=(6, 4))
        self._close.pack(side=tk.RIGHT, padx=(0, 8))
        if not self._visible:
            self._wrap.pack(fill=tk.X)
            self._visible = True

    def hide(self):
        if self._visible:
            self._wrap.pack_forget()
            self._visible = False


class StatusBar(tk.Frame):
    """Bottom bar: state dot + message on the left, product signature right."""

    def __init__(self, parent, signature=""):
        super().__init__(parent, bg=SURFACE, height=30)
        self.pack_propagate(False)
        hr(self, bg=BORDER_SOFT)
        row = tk.Frame(self, bg=SURFACE)
        row.pack(fill=tk.BOTH, expand=True)
        self._dot = tk.Label(row, text="●", bg=SURFACE, fg=TEXT_FAINT, font=f("micro"))
        self._dot.pack(side=tk.LEFT, padx=(14, 6))
        self._var = tk.StringVar(value="Ready")
        tk.Label(row, textvariable=self._var, bg=SURFACE, fg=TEXT_DIM,
                 font=f("small"), anchor="w").pack(side=tk.LEFT)
        tk.Label(row, text=signature, bg=SURFACE, fg=TEXT_FAINT,
                 font=f("small"), anchor="e").pack(side=tk.RIGHT, padx=14)

    def set(self, text, tone="idle"):
        self._var.set(text)
        self._dot.configure(fg=_TONE.get(tone, _TONE["idle"])[0])
        self.update_idletasks()


class Header(tk.Frame):
    """Top bar: DME wordmark, product name, version, optional right-hand slot."""

    def __init__(self, parent, brand, product, version, tagline=""):
        super().__init__(parent, bg=SURFACE)
        row = tk.Frame(self, bg=SURFACE, height=62)
        row.pack(fill=tk.X)
        row.pack_propagate(False)

        logo = brand.header_logo(row, subsample=2)
        if logo is not None:
            logo.pack(side=tk.LEFT, padx=(20, 16))
        else:
            tk.Label(row, text=brand.VENDOR.upper(), bg=SURFACE, fg=TEXT,
                     font=f("title")).pack(side=tk.LEFT, padx=(20, 16))

        tk.Frame(row, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=16)

        titles = tk.Frame(row, bg=SURFACE)
        titles.pack(side=tk.LEFT, padx=16)
        line = tk.Frame(titles, bg=SURFACE)
        line.pack(anchor="w")
        tk.Label(line, text=product, bg=SURFACE, fg=TEXT,
                 font=f("title")).pack(side=tk.LEFT)
        chip = tk.Frame(line, bg=CARD_ALT)
        chip.pack(side=tk.LEFT, padx=10, pady=2)
        tk.Label(chip, text=f"v{version}", bg=CARD_ALT, fg=TEXT_DIM,
                 font=f("micro"), padx=7, pady=2).pack()
        if tagline:
            tk.Label(titles, text=tagline, bg=SURFACE, fg=TEXT_FAINT,
                     font=f("small")).pack(anchor="w")

        self.right = tk.Frame(row, bg=SURFACE)
        self.right.pack(side=tk.RIGHT, padx=20)

        tk.Frame(self, bg=ACCENT, height=2).pack(fill=tk.X)


class VScroll(tk.Frame):
    """Vertically scrollable region whose inner frame tracks the canvas width."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        from tkinter import ttk
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical",
                                       style="DME.Vertical.TScrollbar",
                                       command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._sync_region)
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        # Wheel only while the pointer is over this region
        self.canvas.bind("<Enter>", self._bind_wheel)
        self.canvas.bind("<Leave>", self._unbind_wheel)

    def _sync_region(self, _=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_scroll(self, first, last):
        # Hide the scrollbar when everything fits
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.pack_forget()
        else:
            self.scrollbar.pack(side="right", fill="y")
        self.scrollbar.set(first, last)

    def _wheel(self, event):
        if event.num == 4:
            delta = 1
        elif event.num == 5:
            delta = -1
        else:
            delta = int(event.delta / 120) or (1 if event.delta > 0 else -1)
        self.canvas.yview_scroll(-delta, "units")

    def _bind_wheel(self, _=None):
        self.canvas.bind_all("<MouseWheel>", self._wheel)
        self.canvas.bind_all("<Button-4>", self._wheel)
        self.canvas.bind_all("<Button-5>", self._wheel)

    def _unbind_wheel(self, _=None):
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.canvas.unbind_all(seq)


class LogView(tk.Frame):
    """Read-only monospace output pane with colour tags and auto-hiding bars."""

    TAGS = {"ok": OK, "error": ERR, "warn": WARN, "info": INFO,
            "dim": TEXT_FAINT, "accent": ACCENT}

    def __init__(self, parent, height=12, bg=FIELD):
        super().__init__(parent, bg=BORDER, highlightthickness=0, bd=0)
        from tkinter import ttk
        holder = tk.Frame(self, bg=bg)
        holder.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.text = tk.Text(holder, bg=bg, fg=TEXT_DIM, font=f("mono"), height=height,
                            relief="flat", bd=0, highlightthickness=0, wrap="none",
                            padx=12, pady=10, insertbackground=ACCENT,
                            selectbackground=BORDER, state="disabled")
        self.vbar = ttk.Scrollbar(holder, orient="vertical",
                                  style="DME.Vertical.TScrollbar", command=self.text.yview)
        self.hbar = ttk.Scrollbar(holder, orient="horizontal",
                                  style="DME.Horizontal.TScrollbar", command=self.text.xview)
        self.text.configure(yscrollcommand=lambda *a: self._sync(self.vbar, "ns", 0, 1, *a),
                            xscrollcommand=lambda *a: self._sync(self.hbar, "ew", 1, 0, *a))
        self.text.grid(row=0, column=0, sticky="nsew")
        for tag, colour in self.TAGS.items():
            self.text.tag_configure(tag, foreground=colour)

    @staticmethod
    def _sync(bar, sticky, row, column, first, last):
        if float(first) <= 0.0 and float(last) >= 1.0:
            bar.grid_remove()
        else:
            bar.grid(row=row, column=column, sticky=sticky)
        bar.set(first, last)

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.configure(state="disabled")

    def write(self, line="", tag=None, follow=False):
        self.text.configure(state="normal")
        self.text.insert(tk.END, line + "\n", tag or ())
        if follow:
            self.text.see(tk.END)
        self.text.configure(state="disabled")

    def set_text(self, content, tag=None):
        self.clear()
        self.write(content.rstrip("\n"), tag)
        self.scroll_top()

    def scroll_top(self):
        self.text.yview_moveto(0)
        self.text.xview_moveto(0)


class Table(tk.Frame):
    """Bordered, dark-styled ttk.Treeview with an auto-hiding scrollbar."""

    def __init__(self, parent, columns, height=8, bg=CARD):
        super().__init__(parent, bg=BORDER)
        from tkinter import ttk
        holder = tk.Frame(self, bg=bg)
        holder.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(holder, style="DME.Treeview", show="headings",
                                 height=height,
                                 columns=[c["key"] for c in columns])
        for col in columns:
            self.tree.heading(col["key"], text=col["title"].upper(), anchor=col.get("anchor", "w"))
            self.tree.column(col["key"], width=col.get("width", 120),
                             minwidth=col.get("minwidth", 60),
                             anchor=col.get("anchor", "w"),
                             stretch=col.get("stretch", True))
        self.scroll = ttk.Scrollbar(holder, orient="vertical",
                                    style="DME.Vertical.TScrollbar", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self._sync)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("ok", foreground=OK)
        self.tree.tag_configure("error", foreground=ERR)
        self.tree.tag_configure("warn", foreground=WARN)
        self.tree.tag_configure("busy", foreground=ACCENT)
        self.tree.tag_configure("dim", foreground=TEXT_FAINT)

    def _sync(self, first, last):
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scroll.grid_remove()
        else:
            self.scroll.grid(row=0, column=1, sticky="ns")
        self.scroll.set(first, last)

    # convenience passthroughs
    def clear(self):
        self.tree.delete(*self.tree.get_children())

    def add(self, values, tag=None, iid=None):
        return self.tree.insert("", "end", iid=iid, values=values,
                                tags=(tag,) if tag else ())

    def update_row(self, iid, values=None, tag=None):
        if values is not None:
            self.tree.item(iid, values=values)
        if tag is not None:
            self.tree.item(iid, tags=(tag,))

    def selection(self):
        return self.tree.selection()


class Page(tk.Frame):
    """
    Standard page layout: scrollable body, sticky inline banner and a sticky
    action bar, so the primary action never scrolls out of reach.
    """

    def __init__(self, parent, bg=BG, pad=22):
        super().__init__(parent, bg=bg)
        self.action = tk.Frame(self, bg=SURFACE)
        self.action.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(self.action, bg=BORDER_SOFT, height=1).pack(fill=tk.X)
        self.action_row = tk.Frame(self.action, bg=SURFACE)
        self.action_row.pack(fill=tk.X, padx=pad, pady=12)

        holder = tk.Frame(self, bg=bg)
        holder.pack(side=tk.BOTTOM, fill=tk.X, padx=pad, pady=(0, 12))
        self.banner = Banner(holder, bg=bg)
        self.banner.pack(fill=tk.X)

        self.scroll = VScroll(self, bg=bg)
        self.scroll.pack(fill=tk.BOTH, expand=True)
        self.body = tk.Frame(self.scroll.inner, bg=bg)
        self.body.pack(fill=tk.BOTH, expand=True, padx=pad, pady=(18, 8))

    def intro(self, text, wraplength=860):
        tk.Label(self.body, text=text, bg=self["bg"], fg=TEXT_DIM, font=f("body"),
                 anchor="w", justify="left", wraplength=wraplength).pack(fill=tk.X, pady=(0, 16))

    def card(self, title, hint=None, pady=(0, 14)):
        card = Card(self.body, title=title, hint=hint)
        card.pack(fill=tk.X, pady=pady)
        return card

    def summary(self, variable):
        tk.Label(self.action_row, textvariable=variable, bg=SURFACE, fg=TEXT_DIM,
                 font=f("small"), anchor="w").pack(side=tk.LEFT)


class Collapsible(tk.Frame):
    """A disclosure section — everything that is only needed occasionally."""

    def __init__(self, parent, title, bg=BG, expanded=False, on_toggle=None):
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._expanded = False
        self._on_toggle = on_toggle
        self._title = title

        self._header = tk.Label(self, text="", bg=bg, fg=TEXT_DIM, font=f("small"),
                                anchor="w", cursor="hand2", padx=0, pady=6)
        self._header.pack(fill=tk.X)
        self._header.bind("<Button-1>", lambda _e: self.toggle())
        on_hover(self._header, bg, bg, fg_normal=TEXT_DIM, fg_active=TEXT)

        self.body = tk.Frame(self, bg=bg)
        self._render()
        if expanded:
            self.expand()

    def _render(self):
        arrow = "▾" if self._expanded else "▸"
        self._header.configure(text=f"{arrow}  {self._title}")

    def expand(self):
        if not self._expanded:
            self._expanded = True
            self.body.pack(fill=tk.BOTH, expand=True)
            self._render()
            if self._on_toggle:
                self._on_toggle(True)

    def collapse(self):
        if self._expanded:
            self._expanded = False
            self.body.pack_forget()
            self._render()
            if self._on_toggle:
                self._on_toggle(False)

    def toggle(self):
        self.collapse() if self._expanded else self.expand()

    @property
    def expanded(self) -> bool:
        return self._expanded

    def set_title(self, title):
        self._title = title
        self._render()


class ResolvedRow(tk.Frame):
    """One auto-detected input: state icon, label, file name, where it came from."""

    def __init__(self, parent, label, bg=CARD):
        super().__init__(parent, bg=bg)
        self._icon = tk.Label(self, text="·", bg=bg, fg=TEXT_FAINT, font=f("h2"), width=2)
        self._icon.pack(side=tk.LEFT)
        tk.Label(self, text=label, bg=bg, fg=TEXT_DIM, font=f("small"), width=11,
                 anchor="w").pack(side=tk.LEFT)
        self._value = tk.Label(self, text="—", bg=bg, fg=TEXT_FAINT, font=f("mono"),
                               anchor="w")
        self._value.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._source = tk.Label(self, text="", bg=bg, fg=TEXT_FAINT, font=f("small"),
                                anchor="e")
        self._source.pack(side=tk.RIGHT)

    def set(self, value, source="", ok=True):
        self._icon.configure(text="✓" if ok and value else "✕" if not value else "·",
                             fg=OK if (ok and value) else ERR)
        self._value.configure(text=value or "not found",
                              fg=TEXT if value else ERR)
        self._source.configure(text=source)
