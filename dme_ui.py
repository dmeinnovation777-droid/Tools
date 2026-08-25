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
BG = "#F5F5F7"          # working canvas
SURFACE = "#FFFFFF"     # sidebar (must match dme_brand.HEADER_BG)
CARD = "#FFFFFF"        # raised surface - it reads against BG, not by a border
CARD_ALT = "#F5F5F7"    # nested rows, table headers
HOVER = "#EFEFF2"       # hover fill
BORDER = "#D2D2D7"      # hairline
BORDER_SOFT = "#E5E5EA"
FIELD = "#FFFFFF"       # input well
FIELD_BORDER = "#C7C7CC"

# Three steps, and all three clear 4.5:1 on both grounds - the faint one carries
# hints, provenance and table rows, so it is body copy and may not sit below AA.
TEXT = "#1D1D1F"        # 16.8:1 on white
TEXT_DIM = "#48484B"    #  8.6:1
TEXT_FAINT = "#6E6E73"  #  5.1:1

ACCENT = "#FFAA00"      # DME amber. On light it fills, it never sets type.
ACCENT_HOVER = "#F0A000"
ACCENT_PRESS = "#D99000"
ON_ACCENT = "#1D1D1F"   # 8.8:1 on the amber fill

# Every status pair clears 4.5:1 twice over: against white and against its own
# tint, so a tone reads whether it sits on a card or inside a banner.
OK = "#177A44"
OK_BG = "#E7F4EC"
ERR = "#B3261E"
ERR_BG = "#FBEAE9"
WARN = "#8A5A00"
WARN_BG = "#FBF1E0"
INFO = "#0066CC"
INFO_BG = "#E8F1FD"

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

# Pixels per logical unit. 1.0 on a normal display, 1.5 at 150 % Windows scaling.
SCALE = 1.0


def enable_dpi_awareness() -> None:
    """
    Tell Windows we paint at the real pixel grid.

    Without this a tkinter window is rendered at 96 dpi and then bitmap-stretched
    by the compositor - which is exactly what makes the app look washed out on
    any display running above 100 %. Must be called before the first Tk window.
    """
    if os.name != "nt":
        return
    import ctypes
    for attempt in (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),   # per monitor
                    lambda: ctypes.windll.shcore.SetProcessDpiAwareness(1),   # system
                    lambda: ctypes.windll.user32.SetProcessDPIAware()):
        try:
            attempt()
            return
        except Exception:
            continue


def px(value: float) -> int:
    """Scale a pixel dimension to the current display."""
    return max(1, int(round(value * SCALE)))


def _pick(root, candidates, fallback):
    available = {name.lower() for name in tkfont.families(root)}
    for name in candidates:
        if name.lower() in available:
            return name
    return fallback


def init(root) -> None:
    """Resolve the display scale, fonts and ttk styles. Call once, right after Tk()."""
    global SCALE
    try:
        dpi = float(root.winfo_fpixels("1i"))
    except tk.TclError:
        dpi = 96.0
    SCALE = min(max(dpi / 96.0, 1.0), 3.0)
    try:
        # point-sized fonts now render at their true physical size, sharp
        root.tk.call("tk", "scaling", dpi / 72.0)
    except tk.TclError:
        pass

    ui = _pick(root, _UI_CANDIDATES, "TkDefaultFont")
    mono = _pick(root, _MONO_CANDIDATES, "TkFixedFont")
    FONTS.update({
        "title":  (ui, 15, "bold"),
        "h1":     (ui, 20, "bold"),   # the screen title carries the page
        "h1s":    (ui, 12, "bold"),
        "h2":     (ui, 11, "bold"),   # card titles
        "body":   (ui, 10),
        "label":  (ui, 9),
        "small":  (ui, 9),
        "micro":  (ui, 8),
        "tab":    (ui, 10, "bold"),
        "nav":    (ui, 10, "bold"),
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
                    relief="flat", width=px(10))
    style.map("DME.Vertical.TScrollbar",
              background=[("active", BORDER_SOFT), ("pressed", TEXT_FAINT)])
    style.layout("DME.Horizontal.TScrollbar", [
        ("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [
            ("Horizontal.Scrollbar.thumb", {"expand": 1, "sticky": "nswe"})]})])
    style.configure("DME.Horizontal.TScrollbar", troughcolor=BG, bordercolor=BG,
                    background=BORDER, darkcolor=BORDER, lightcolor=BORDER,
                    relief="flat", height=px(10))
    style.configure("DME.Treeview", background=CARD, fieldbackground=CARD,
                    foreground=TEXT, bordercolor=BORDER, borderwidth=0,
                    relief="flat", rowheight=px(27), font=f("small"))
    style.configure("DME.Treeview.Heading", background=CARD_ALT, foreground=TEXT_FAINT,
                    relief="flat", borderwidth=0, font=f("micro"), padding=(px(8), px(6)))
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


def _round_points(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def round_corners(widget, radius=None, outer_bg=BG):
    """
    Give a normally packed widget rounded corners.

    Four small canvases sit in the corners and paint the area outside the arc in
    the surrounding colour. The widget keeps its own geometry manager, so this
    costs nothing in layout terms.
    """
    radius = px(10) if radius is None else radius
    inner_bg = widget["bg"]
    corners = []
    # corner order: top-left, top-right, bottom-right, bottom-left. The arc's
    # bounding box is twice the radius and shifted so its centre lands on the
    # inner corner; the visible quadrant is the one pointing outwards.
    for index in range(4):
        canvas = tk.Canvas(widget, width=radius, height=radius, bg=outer_bg,
                           highlightthickness=0, bd=0)
        start = (90, 0, 270, 180)[index]
        offset = ((0, 0), (-radius, 0), (-radius, -radius), (0, -radius))[index]
        canvas.create_arc(offset[0], offset[1], offset[0] + radius * 2,
                          offset[1] + radius * 2, start=start, extent=90,
                          fill=inner_bg, outline=inner_bg)
        corners.append(canvas)

    def place(_=None):
        corners[0].place(x=0, y=0)
        corners[1].place(relx=1.0, x=-radius, y=0)
        corners[2].place(relx=1.0, rely=1.0, x=-radius, y=-radius)
        corners[3].place(rely=1.0, x=0, y=-radius)

    widget.bind("<Configure>", place, add="+")
    place()
    return corners


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


# ─────────────────────────────────────────────────────────────────────────────
# Buttons
# ─────────────────────────────────────────────────────────────────────────────
_VARIANTS = {
    "primary":   dict(bg=ACCENT, fg=ON_ACCENT, hover=ACCENT_HOVER, press=ACCENT_PRESS),
    "secondary": dict(bg=CARD_ALT, fg=TEXT, hover=HOVER, press=BORDER,
                      border=FIELD_BORDER),
    "ghost":     dict(bg=CARD, fg=TEXT_DIM, hover=HOVER, press=BORDER),
    "danger":    dict(bg=CARD_ALT, fg=ERR, hover=ERR_BG, press=ERR_BG),
}
_SIZES = {
    "lg": dict(padx=20, pady=9, font="button"),
    "md": dict(padx=14, pady=6, font="button"),
    "sm": dict(padx=10, pady=4, font="small"),
}


class RoundedButton(tk.Canvas):
    """A pill button drawn on a canvas - tk has no border radius of its own."""

    def __init__(self, parent, text, command=None, variant="primary", size="md",
                 bg=None, **_ignored):
        spec = _VARIANTS[variant]
        dims = _SIZES[size]
        self._outer = bg or parent["bg"]
        self._fill = spec["bg"] if variant != "ghost" else self._outer
        self._hover = spec["hover"]
        self._press = spec["press"]
        self._fg = spec["fg"]
        self._command = command
        self._state = "normal"
        self._font = f(dims["font"])
        self._padx, self._pady = px(dims["padx"]), px(dims["pady"])
        # a pill, not a rounded box - the radius is half the height, set in _draw
        self._radius = px(999)
        self._border = spec.get("border")

        super().__init__(parent, bg=self._outer, highlightthickness=0, bd=0,
                         takefocus=1, cursor="hand2")
        self._shape = None
        self._label = None
        self._text = text
        self._measure()
        self.bind("<Configure>", lambda _e: self._draw())
        self.bind("<Enter>", lambda _e: self._paint(self._hover))
        self.bind("<Leave>", lambda _e: self._paint(self._fill))
        self.bind("<ButtonPress-1>", lambda _e: self._paint(self._press))
        self.bind("<ButtonRelease-1>", self._release)
        self.bind("<FocusIn>", lambda _e: self._paint(self._hover))
        self.bind("<FocusOut>", lambda _e: self._paint(self._fill))
        self.bind("<Return>", lambda _e: self._invoke())
        self.bind("<space>", lambda _e: self._invoke())

    # geometry ---------------------------------------------------------------
    def _measure(self):
        probe = tkfont.Font(font=self._font)
        width = probe.measure(self._text) + self._padx * 2
        height = probe.metrics("linespace") + self._pady * 2
        self.configure(width=width, height=height)

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return
        fill = self._fill if self._state != "disabled" else CARD_ALT
        outline = self._border or fill
        radius = max(px(4), min(self._radius, (h - 2) // 2))
        if self._radius * 2 >= h - 2:      # asked for a pill
            # A pill. Tk's smooth polygon never quite reaches the asked-for
            # radius, so the caps are drawn as real half circles instead.
            cap = h - 2
            self.create_oval(1, 1, 1 + cap, h - 1, fill=fill, outline=outline,
                             tags="shape")
            self.create_oval(w - 1 - cap, 1, w - 1, h - 1, fill=fill,
                             outline=outline, tags="shape")
            self.create_rectangle(1 + cap / 2, 1, w - 1 - cap / 2, h - 1,
                                  fill=fill, outline=fill, tags="shape")
        else:
            self.create_polygon(
                _round_points(1, 1, w - 1, h - 1, radius), smooth=True,
                splinesteps=24, fill=fill, outline=outline, tags="shape")
        self._shape = "shape"
        colour = self._fg if self._state != "disabled" else TEXT_FAINT
        self._label = self.create_text(w / 2, h / 2, text=self._text, fill=colour,
                                       font=self._font)

    def _paint(self, colour):
        if self._state == "disabled" or self._shape is None:
            return
        self.itemconfigure(self._shape, fill=colour,
                           outline=self._border or colour)

    def _release(self, _event=None):
        self._paint(self._hover)
        self._invoke()

    def _invoke(self):
        if self._state != "disabled" and self._command:
            self._command()

    # tk-compatible surface --------------------------------------------------
    def configure(self, cnf=None, **kw):
        options = dict(cnf or {}, **kw)
        redraw = False
        if "state" in options:
            self._state = options.pop("state")
            self.configure(cursor="arrow" if self._state == "disabled" else "hand2")
            redraw = True
        if "text" in options:
            self._text = options.pop("text")
            self._measure()
            redraw = True
        if "command" in options:
            self._command = options.pop("command")
        for key in ("bg", "background"):
            if key in options and options[key]:
                self._outer = options.pop(key)
                if self._fill == self._outer or True:
                    pass
                super().configure(bg=self._outer)
                redraw = True
        for key in ("fg", "foreground"):
            if key in options:
                self._fg = options.pop(key)
                redraw = True
        options.pop("activebackground", None)
        options.pop("activeforeground", None)
        if options:
            super().configure(**options)
        if redraw:
            self._draw()
        return None

    config = configure

    def cget(self, key):
        if key == "state":
            return self._state
        if key == "text":
            return self._text
        return super().cget(key)

    def invoke(self):
        self._invoke()


def button(parent, text, command=None, variant="primary", size="md", bg=None, **kw):
    return RoundedButton(parent, text, command, variant=variant, size=size, bg=bg, **kw)


def icon_button(parent, text, command=None, bg=CARD, fg=TEXT_FAINT, hover_fg=ERR,
                hover_bg=None, font_key="body"):
    btn = tk.Button(parent, text=text, command=command, relief="flat", bd=0,
                    highlightthickness=0, cursor="hand2", bg=bg, fg=fg,
                    activebackground=hover_bg or HOVER, activeforeground=hover_fg,
                    font=f(font_key), padx=px(6), pady=px(1))
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
    """Label + path entry + Browse button, with a visible hint line below."""

    def __init__(self, parent, label, variable, on_browse, browse_text="Browse",
                 hint=None, bg=CARD):
        super().__init__(parent, bg=bg)
        field_label(self, label, bg=bg).pack(fill=tk.X, pady=(0, 4))
        row = tk.Frame(self, bg=bg)
        row.pack(fill=tk.X)
        self.entry = entry(row, variable)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=px(6))
        self.button = button(row, browse_text, on_browse, variant="secondary", size="md")
        self.button.pack(side=tk.LEFT, padx=(px(8), 0))
        self.hint_var = tk.StringVar(value=hint or "")
        self.hint = tk.Label(self, textvariable=self.hint_var, bg=bg, fg=TEXT_FAINT,
                             font=f("small"), anchor="w")
        self.hint.pack(fill=tk.X, pady=(px(5), 0))

    def set_hint(self, text, tone="idle"):
        self.hint_var.set(text)
        self.hint.configure(fg=_TONE.get(tone, (TEXT_FAINT, None))[0])


class LabeledEntry(tk.Frame):
    """Compact label-above-field cell for form grids."""

    def __init__(self, parent, label, variable, bg=CARD, mono=True, width=None):
        super().__init__(parent, bg=bg)
        field_label(self, label, bg=bg).pack(fill=tk.X, pady=(0, px(3)))
        self.entry = entry(self, variable, mono=mono, width=width)
        self.entry.pack(fill=tk.X, ipady=px(5))


# ─────────────────────────────────────────────────────────────────────────────
# Structure
# ─────────────────────────────────────────────────────────────────────────────
class Card(tk.Frame):
    """Bordered content block with an optional title row."""

    def __init__(self, parent, title=None, hint=None, bg=CARD, pad=(16, 14)):
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0)
        round_corners(self, px(18), outer_bg=parent["bg"])
        px_, py = px(pad[0]), px(pad[1])
        self.hint_var = tk.StringVar(value=hint or "")
        if title:
            head = tk.Frame(self, bg=bg)
            head.pack(fill=tk.X, padx=px_, pady=(py - 2, 0))
            tk.Label(head, text=title, bg=bg, fg=TEXT, font=f("h2"),
                     anchor="w").pack(side=tk.LEFT)
            self.hint_label = tk.Label(head, textvariable=self.hint_var, bg=bg,
                                       fg=TEXT_FAINT, font=f("small"), anchor="e")
            self.hint_label.pack(side=tk.RIGHT)
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill=tk.BOTH, expand=True, padx=px_, pady=(px(10), py))

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
        strip.pack(fill=tk.X, padx=px(22))
        for key, label in tabs:
            holder = tk.Frame(strip, bg=bg)
            holder.pack(side=tk.LEFT)
            btn = tk.Label(holder, text=label, bg=bg, fg=TEXT_DIM, font=f("tab"),
                           padx=px(4), pady=px(11), cursor="hand2")
            btn.pack()
            underline = tk.Frame(holder, bg=bg, height=px(2))
            underline.pack(fill=tk.X)
            btn.bind("<Button-1>", lambda _e, k=key: self.select(k))
            btn.bind("<Enter>", lambda _e, b=btn, k=key:
                     b.configure(fg=TEXT) if self._active != k else None)
            btn.bind("<Leave>", lambda _e, b=btn, k=key:
                     b.configure(fg=TEXT_DIM) if self._active != k else None)
            self._buttons[key] = btn
            self._underlines[key] = underline
            tk.Frame(strip, bg=bg, width=px(22)).pack(side=tk.LEFT)
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
        self._bar = tk.Frame(self._wrap, bg=OK, width=px(3))
        self._bar.pack(side=tk.LEFT, fill=tk.Y)
        inner = tk.Frame(self._wrap, bg=OK_BG)
        inner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._inner = inner
        self._icon = tk.Label(inner, text="", bg=OK_BG, fg=OK, font=f("h2"))
        self._icon.pack(side=tk.LEFT, padx=(px(12), px(8)), pady=px(10))
        self._text = tk.Label(inner, text="", bg=OK_BG, fg=TEXT, font=f("small"),
                              anchor="w", justify="left", wraplength=560)
        self._text.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=px(10))
        self._action = tk.Label(inner, text="", bg=OK_BG, fg=OK, font=f("small"),
                                cursor="hand2", padx=px(8))
        self._action_command = None
        self._action.bind("<Button-1>", lambda _e: self._action_command
                          and self._action_command())
        self._close = icon_button(inner, "✕", self.hide, bg=OK_BG, fg=TEXT_FAINT,
                                  hover_fg=TEXT, hover_bg=OK_BG)
        self._corners = round_corners(self._wrap, px(10), outer_bg=bg)
        self._visible = False

    def show(self, kind, text, action_text=None, action=None):
        fg, bg = _TONE.get(kind, _TONE["info"])
        icons = {"ok": "✓", "error": "✕", "warn": "!", "info": "i", "busy": "•"}
        self._wrap.configure(bg=bg)
        self._inner.configure(bg=bg)
        for corner in self._corners:
            corner.itemconfigure("all", fill=bg, outline=bg)
        self._bar.configure(bg=fg)
        self._icon.configure(bg=bg, fg=fg, text=icons.get(kind, "i"))
        self._text.configure(bg=bg, text=text)
        self._close.configure(bg=bg, activebackground=bg)
        on_hover(self._close, bg, bg, fg_normal=TEXT_FAINT, fg_active=TEXT)
        self._close.pack_forget()
        self._action.pack_forget()
        if action_text and action:
            self._action_command = action
            self._action.configure(text=action_text, bg=bg, fg=fg,
                                   font=(f("small")[0], f("small")[1], "underline"))
            self._action.pack(side=tk.RIGHT, padx=(px(6), px(4)))
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
        super().__init__(parent, bg=SURFACE, height=px(30))
        self.pack_propagate(False)
        hr(self, bg=BORDER_SOFT)
        row = tk.Frame(self, bg=SURFACE)
        row.pack(fill=tk.BOTH, expand=True)
        self._dot = tk.Label(row, text="●", bg=SURFACE, fg=TEXT_FAINT, font=f("micro"))
        self._dot.pack(side=tk.LEFT, padx=(px(14), px(6)))
        self._var = tk.StringVar(value="Ready")
        tk.Label(row, textvariable=self._var, bg=SURFACE, fg=TEXT_DIM,
                 font=f("small"), anchor="w").pack(side=tk.LEFT)
        tk.Label(row, text=signature, bg=SURFACE, fg=TEXT_FAINT,
                 font=f("small"), anchor="e").pack(side=tk.RIGHT, padx=px(14))

    def set(self, text, tone="idle"):
        self._var.set(text)
        self._dot.configure(fg=_TONE.get(tone, _TONE["idle"])[0])
        self.update_idletasks()


class Header(tk.Frame):
    """Top bar: DME wordmark, product name, version, optional right-hand slot."""

    def __init__(self, parent, brand, product, version, tagline=""):
        super().__init__(parent, bg=SURFACE)
        row = tk.Frame(self, bg=SURFACE, height=px(62))
        row.pack(fill=tk.X)
        row.pack_propagate(False)

        logo = brand.header_logo(row, scale=SCALE)
        if logo is not None:
            logo.pack(side=tk.LEFT, padx=(px(20), px(16)))
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

        tk.Frame(self, bg=ACCENT, height=px(2)).pack(fill=tk.X)


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
                            padx=px(12), pady=px(10), insertbackground=ACCENT,
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

    def __init__(self, parent, bg=BG, pad=32):
        super().__init__(parent, bg=bg)
        pad = px(pad)
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


class _NavItem(tk.Frame):
    """One sidebar entry. Selected is a quiet rounded fill, never a coloured bar."""

    def __init__(self, parent, label, on_click, bg=SURFACE):
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._label = tk.Label(self, text=label, bg=bg, fg=TEXT_DIM, font=f("nav"),
                               anchor="w", padx=px(14), pady=px(9), cursor="hand2")
        self._label.pack(fill=tk.X)
        for widget in (self, self._label):
            widget.bind("<Button-1>", lambda _e: on_click())
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
        self._active = False
        round_corners(self, px(8), outer_bg=bg)

    def _enter(self, _=None):
        if not self._active:
            self._paint(HOVER, TEXT)

    def _leave(self, _=None):
        if not self._active:
            self._paint(self._bg, TEXT_DIM)

    def _paint(self, bg, fg):
        self.configure(bg=bg)
        self._label.configure(bg=bg, fg=fg)
        for child in self.winfo_children():
            if isinstance(child, tk.Canvas):
                child.itemconfigure("all", fill=bg, outline=bg)

    def set_active(self, active):
        self._active = active
        self._paint(CARD_ALT if active else self._bg, TEXT if active else TEXT_DIM)


class Shell(tk.Frame):
    """
    Application frame: a sidebar for navigation, a title bar that names the
    current view, the view itself, and a status line at the bottom.
    """

    def __init__(self, root, brand, product, version, nav, on_select):
        super().__init__(root, bg=BG)
        self._on_select = on_select
        self._nav = {}
        self._pages = dict((entry["key"], entry) for entry in nav)
        self._active = None

        side = tk.Frame(self, bg=SURFACE, width=px(238))
        side.pack(side=tk.LEFT, fill=tk.Y)
        side.pack_propagate(False)

        head = tk.Frame(side, bg=SURFACE)
        head.pack(fill=tk.X, padx=px(18), pady=(px(22), px(18)))
        logo = brand.header_logo(head, scale=SCALE)
        if logo is not None:
            logo.pack(anchor="w")
        else:
            tk.Label(head, text=brand.VENDOR.upper(), bg=SURFACE, fg=TEXT,
                     font=f("title")).pack(anchor="w")
        tk.Label(head, text=product, bg=SURFACE, fg=TEXT_DIM, font=f("small"),
                 anchor="w").pack(fill=tk.X, pady=(px(10), 0))

        items = tk.Frame(side, bg=SURFACE)
        items.pack(fill=tk.X, padx=px(12))
        for entry in nav:
            item = _NavItem(items, entry["label"], lambda k=entry["key"]: self.select(k))
            item.pack(fill=tk.X, pady=px(2))
            self._nav[entry["key"]] = item

        foot = tk.Frame(side, bg=SURFACE)
        foot.pack(side=tk.BOTTOM, fill=tk.X, padx=px(18), pady=px(18))
        tk.Label(foot, text=f"v{version}", bg=SURFACE, fg=TEXT_FAINT,
                 font=f("micro"), anchor="w").pack(fill=tk.X)

        main = tk.Frame(self, bg=BG)
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        bar = tk.Frame(main, bg=BG)
        bar.pack(fill=tk.X, padx=px(32), pady=(px(26), px(18)))
        self._title = tk.Label(bar, text="", bg=BG, fg=TEXT, font=f("h1"), anchor="w")
        self._title.pack(fill=tk.X)
        self._subtitle = tk.Label(bar, text="", bg=BG, fg=TEXT_DIM, font=f("body"),
                                  anchor="w", justify="left", wraplength=px(720))
        self._subtitle.pack(fill=tk.X, pady=(px(4), 0))
        bar.bind("<Configure>",
                 lambda e: self._subtitle.configure(wraplength=max(px(320), e.width - px(8))))

        self.status = StatusBar(main, f"{brand.VENDOR}  ·  {product}")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.host = tk.Frame(main, bg=BG)
        self.host.pack(fill=tk.BOTH, expand=True)

    def select(self, key):
        if key == self._active:
            return
        self._active = key
        for name, item in self._nav.items():
            item.set_active(name == key)
        entry = self._pages[key]
        self._title.configure(text=entry.get("title", entry["label"]))
        self._subtitle.configure(text=entry.get("subtitle", ""))
        self._on_select(key)
