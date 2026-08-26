"""
DME Innovation desktop UI kit
=============================

A small, dependency-free widget set that gives the DME tools one consistent,
modern look: flat dark surfaces, card-based layout, underline tabs, inline
status banners and a single amber accent taken from the DME logo tile.

Everything here is plain tkinter, no third party packages and no images beyond
the embedded logo in dme_brand.py.
"""

import math
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import font as tkfont

import dme_paint as paint

# ─────────────────────────────────────────────────────────────────────────────
# Palette
# ─────────────────────────────────────────────────────────────────────────────
# White first. The old look stacked three greys because the content sat on
# cards; the flow has no cards, so the page itself is the paper and the only
# tinted surfaces are the wells that hold a value. Two hairlines carry the
# structure: the soft one inside a box, the faint one under the top bar.
SURFACE = "#FFFFFF"     # top bar and action bar (must match dme_brand.HEADER_BG)
BG = "#FFFFFF"          # the page
CARD = "#FFFFFF"        # a box on the page, told apart by its outline
CARD_ALT = "#F7F7F9"    # wells, table headers, input fields
HOVER = "#F0F0F3"       # hover fill
BORDER = "#DCDCE1"      # hairline that has to be seen
BORDER_SOFT = "#E8E8EC" # hairline inside a box
HAIRLINE = "#EDEDF1"    # under the top bar, over the action bar
RAIL = "#E8E8EC"        # the line down the side of a flow
FIELD = "#F7F7F9"
FIELD_BORDER = "#E8E8EC"

# Three steps. All three clear 4.5:1 on every ground the app can put behind
# them, HOVER included - the faint one carries hints, provenance and table rows,
# so it is body copy and may not sit below AA anywhere.
TEXT = "#1D1D1F"        # 16.8:1 on white
TEXT_DIM = "#48484B"    #  8.6:1
TEXT_FAINT = "#67676C"  #  5.5:1 on white, 4.7:1 on the hover fill

# The amber fills, it does not set type: against white it is 1.9:1. Where the
# brand colour has to be read, ACCENT_INK is the same hue taken down to AA.
ACCENT = "#FFAA00"
ACCENT_HOVER = "#F0A000"
ACCENT_PRESS = "#D99000"
ON_ACCENT = "#1D1D1F"   # 8.8:1 on the amber fill
ACCENT_INK = "#8F5C00"  # 5.6:1 on white, 4.7:1 on the hover fill

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
    "busy": (ACCENT_INK, WARN_BG),
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
    # A picture belongs to the Tk that made it, and the sizes below depend on
    # the scale about to be worked out. A new window therefore starts with an
    # empty drawer: keeping the old pictures would hand the new window images
    # that no longer exist.
    paint.forget()
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
        "h1":     (ui, 22, "bold"),   # the screen title carries the page
        "h1s":    (ui, 12, "bold"),
        "h2":     (ui, 11, "bold"),   # card titles
        "step":   (ui, 11, "bold"),   # the name of a step in a flow
        "ring":   (ui, 9, "bold"),    # the number inside the ring
        "section": (ui, 8, "bold"),   # the quiet header above a grouped list
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
    install_wheel(root)


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


def round_corners(widget, radius=None, outer_bg=BG, border=None):
    """Fake a rounded corner by painting the outside of it.

    tk has no border radius. Each corner gets a small canvas filled with the
    OUTER colour, and an arc in the widget's own fill painted on top; the square
    corner underneath disappears. With ``border`` the arc is stroked as well, so
    a box with a hairline outline keeps that hairline around the bend.
    """
    radius = px(10) if radius is None else radius
    inner_bg = widget["bg"]
    # One painted corner, cut into four. The arc tk draws has a staircase on
    # it; this one is worked out against the colour outside the box, so the
    # bend is as smooth as the straight edge beside it.
    corners = _Corners(widget, radius, outer_bg, border)
    corners.set_fill(inner_bg)

    # Placed with relx/rely, so tk keeps them in their corners by itself as the
    # widget grows. The only thing a resize can change is whether they fit at
    # all, and that answer is acted on once, not once per pixel of a drag.
    hidden = [None]

    def place(_=None):
        # A corner wider than half the widget would paint the whole thing in
        # the outer colour and the widget would simply vanish. It happened.
        width, height = widget.winfo_width(), widget.winfo_height()
        hide = width > 1 and height > 1 and radius * 2 > min(width, height)
        if hide == hidden[0]:
            return
        hidden[0] = hide
        if hide:
            for corner in corners:
                corner.place_forget()
            return
        corners[0].place(x=0, y=0)
        corners[1].place(relx=1.0, x=-radius, y=0)
        corners[2].place(relx=1.0, rely=1.0, x=-radius, y=-radius)
        corners[3].place(rely=1.0, x=0, y=-radius)

    widget.bind("<Configure>", place, add="+")
    place()
    return corners


class _Corners(list):
    """The four painted corners of one box, and the way to recolour them.

    A picture has no fill to change, so a box whose colour depends on what it
    is saying - a banner turning from green to red - has to be given a new
    picture rather than a new colour. That is what set_fill does.
    """

    def __init__(self, widget, radius, outer_bg, border):
        super().__init__()
        self._radius = radius
        self._outer = outer_bg
        self._border = border
        self._offsets = ((0, 0), (-radius, 0), (-radius, -radius), (0, -radius))
        for _ in range(4):
            self.append(tk.Canvas(widget, width=radius, height=radius,
                                  bg=outer_bg, highlightthickness=0, bd=0))

    def set_fill(self, fill):
        """One picture, shown four times, each canvas a different quarter."""
        radius = self._radius
        whole = paint.panel(radius * 2, radius * 2, radius, fill, self._outer,
                            border=self._border, border_width=max(1, px(1)))
        for canvas, (dx, dy) in zip(self, self._offsets):
            canvas.delete("all")
            canvas.create_image(dx, dy, anchor="nw", image=whole)
            canvas._picture = whole            # tk keeps no reference itself


def outlined(parent, fill=CARD, border=BORDER_SOFT, radius=12, bg=None):
    """A box with a hairline outline and rounded corners. Sizes to its content.

    The new design has no drop shadows and almost no fills, so a box is told
    from the page by its outline alone. Returns the frame to pack into.
    """
    outer = bg or parent["bg"]
    box = tk.Frame(parent, bg=fill, highlightthickness=1,
                   highlightbackground=border, highlightcolor=border, bd=0)
    round_corners(box, px(radius), outer_bg=outer, border=border)
    return box


# ─────────────────────────────────────────────────────────────────────────────
# Motion
# ─────────────────────────────────────────────────────────────────────────────
# Until 3.1.0 nothing in this app moved. Every state change was a hard swap:
# the page, the switch, the pill in the bar, the ring on a step. That is the
# difference you feel against a phone, and most of it is fixable, because the
# things that have to move are drawn on canvases and tk moves those quickly.
#
# What is NOT fixable here: there is no compositor, so there is no cross fade
# and no blur. Where a phone dissolves, this slides.

FRAME_MS = 16          # about 60 a second, which is what tk manages


def ease_out(t: float) -> float:
    """Fast at the start, gentle at the end. The curve a phone uses."""
    return 1.0 - (1.0 - t) ** 3


def ease_in_out(t: float) -> float:
    return 4 * t * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


# Every tween that is in flight. A window that closes mid animation would
# otherwise leave a pending after() calling into a widget that is gone, and Tcl
# prints that on the console.
_RUNNING: set = set()


def stop_animations():
    """Cancel everything in flight. Called before a window goes away."""
    for animation in list(_RUNNING):
        animation.cancel()
    _RUNNING.clear()


def finish_animations():
    """Jump everything in flight to its end. Used before the window is shown,
    and by the tests: an abandoned tween would leave a half faded ring."""
    for animation in list(_RUNNING):
        animation.finish()
    _RUNNING.clear()


class Animation:
    """One running tween. Keep it to cancel it."""

    def __init__(self, widget, ms, step, done=None, ease=ease_out):
        self._widget = widget
        self._ms = max(1, ms)
        self._step = step
        self._done = done
        self._ease = ease
        self._after = None
        self._start = time.perf_counter()
        _RUNNING.add(self)
        self._tick()

    def _tick(self):
        # Real time, not a frame counter: a dropped frame must not stretch the
        # curve, it must skip a piece of it.
        elapsed = (time.perf_counter() - self._start) * 1000.0
        fraction = min(1.0, elapsed / self._ms)
        try:
            self._step(self._ease(fraction))
        except tk.TclError:
            _RUNNING.discard(self)
            return                        # the widget went away mid flight
        if fraction >= 1.0:
            self._after = None
            _RUNNING.discard(self)
            if self._done:
                self._done()
            return
        try:
            self._after = self._widget.after(FRAME_MS, self._tick)
        except tk.TclError:
            self._after = None

    def cancel(self):
        _RUNNING.discard(self)
        if self._after is not None:
            try:
                self._widget.after_cancel(self._after)
            except tk.TclError:
                pass
            self._after = None

    def finish(self):
        """Go straight to the end of the curve rather than stop halfway."""
        self.cancel()
        try:
            self._step(self._ease(1.0))
        except tk.TclError:
            return
        if self._done:
            self._done()

    @property
    def running(self):
        return self._after is not None


def animate(widget, ms, step, done=None, ease=ease_out, previous=None):
    """Run `step(fraction)` for `ms`, then `done()`. Cancels `previous` first."""
    if previous is not None:
        previous.cancel()
    return Animation(widget, ms, step, done, ease)


def mix(first: str, second: str, fraction: float) -> str:
    """A colour between two hex colours. Used to fade a fill instead of
    swapping it, since tk cannot fade a whole widget."""
    fraction = 0.0 if fraction < 0 else (1.0 if fraction > 1 else fraction)
    a = (int(first[1:3], 16), int(first[3:5], 16), int(first[5:7], 16))
    b = (int(second[1:3], 16), int(second[3:5], 16), int(second[5:7], 16))
    return "#%02X%02X%02X" % tuple(
        int(round(x + (y - x) * fraction)) for x, y in zip(a, b))


# Every debounced resize watcher, so a pending one can be pulled forward.
_RESIZERS: list = []


def on_resize(widget, callback, delay=50):
    """Run `callback(width, height)` once the resizing stops.

    A window drag fires <Configure> for every pixel. Every wrapped label in the
    app used to answer each one, on all four pages at once, because all four are
    mounted. That is what made dragging the window edge feel like wading. Fifty
    milliseconds after the last pixel is soon enough to look instant and rare
    enough to cost nothing.
    """
    state = {"after": None, "size": None, "seen": False, "widget": widget}

    def fire():
        state["after"] = None
        if state["size"]:
            callback(*state["size"])

    def configured(event):
        if event.width <= 1:
            return
        size = (event.width, event.height)
        if size == state["size"]:
            return
        state["size"] = size
        if not state["seen"]:
            # The very first size is the window being built, not somebody
            # dragging its edge. Waiting 50 ms for that one is what made the
            # app wobble on open: it stood there and then rewrapped itself.
            state["seen"] = True
            fire()
            return
        if state["after"] is not None:
            try:
                widget.after_cancel(state["after"])
            except tk.TclError:
                pass
        state["after"] = widget.after(delay, fire)

    state["fire"] = fire
    _RESIZERS.append(state)
    widget.bind("<Configure>", configured, add="+")
    return state


def flush_resize():
    """Run everything the debounce still owes, right now.

    Used before the window is shown, and by the tests, so that what is measured
    is the finished layout and not one that is still fifty milliseconds away.
    Returns how many fired: one flush can change a width, which owes another,
    so the caller runs this until it comes back quiet.
    """
    fired = 0
    alive = []
    for state in list(_RESIZERS):
        widget = state["widget"]
        try:
            if not widget.winfo_exists():
                continue                      # its page was thrown away
        except tk.TclError:
            continue
        alive.append(state)
        if state["after"] is not None:
            try:
                widget.after_cancel(state["after"])
            except tk.TclError:
                pass
            state["after"] = None
            state["fire"]()
            fired += 1
    _RESIZERS[:] = alive
    return fired


def wrap_to_parent(label, minimum=None, inset=None):
    """Keep a label's wraplength equal to the width it actually gets.

    A fixed wraplength was fine while the surfaces were fixed too. On the card
    layout the same number clips, because the card is narrower than the window.
    The Shell subtitle was the first place that needed it; this is that
    pattern, made reusable.

    ``inset`` is what the label does not get - siblings on the same row plus
    padding. Pass a callable when that only becomes known once tk has laid out.
    """
    floor = px(280) if minimum is None else minimum
    gap = px(10) if inset is None else inset
    parent = label.master
    last = [None]

    def resize(width, _height):
        taken = gap() if callable(gap) else gap
        wrap = max(floor, width - taken)
        # tk lays the whole branch out again on every configure(), even one
        # that changes nothing. Only a width that is really new is worth that.
        if wrap == last[0]:
            return
        last[0] = wrap
        label.configure(wraplength=wrap)

    on_resize(parent, resize)
    return label


def wrapped_lines(text, font, width):
    """How many lines ``text`` needs at ``width``, by tk's own greedy rule.

    Used to reserve height for something whose text changes. Reserved height
    is what keeps the rows under it still.
    """
    if not text:
        return 1
    lines = 0
    for paragraph in text.split("\n"):
        lines += 1
        current = ""
        for word in paragraph.split():
            candidate = word if not current else current + " " + word
            if not current or font.measure(candidate) <= width:
                current = candidate
            else:
                lines += 1
                current = word
    return max(1, lines)


class Switch(tk.Canvas):
    """A real switch, not a tick box.

    tk's Checkbutton draws the platform's box, which on Windows is a 13 px
    square from another decade. This is the same control the phone in your
    pocket uses: a track, a knob, and the state readable across the room.
    """

    def __init__(self, parent, variable=None, command=None, bg=None):
        # Not _w/_h: tkinter keeps the widget's Tcl path name in Misc._w.
        self._track_w, self._track_h = px(38), px(22)
        self._outer = bg or parent["bg"]
        self._var = variable if variable is not None else tk.BooleanVar()
        self._command = command
        self._state = "normal"
        super().__init__(parent, width=self._track_w, height=self._track_h, bg=self._outer,
                         highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
        self.bind("<Button-1>", lambda _e: self.toggle())
        self.bind("<Return>", lambda _e: self.toggle())
        self.bind("<space>", lambda _e: self.toggle())
        # Where the knob is right now, 0 left and 1 right. Not the same thing
        # as the value: between a click and 160 ms later it is in between.
        self._pos = 1.0 if bool(self._var.get()) else 0.0
        self._motion = None
        self.bind("<Configure>", lambda _e: self._draw())
        self._trace = self._var.trace_add("write", lambda *_: self._glide())
        self._draw()

    def toggle(self):
        if self._state == "disabled":
            return
        self._var.set(not self._var.get())
        if self._command:
            self._command()

    def _glide(self):
        target = 1.0 if bool(self._var.get()) else 0.0
        if abs(target - self._pos) < 0.001:
            return
        origin = self._pos

        def step(fraction):
            self._pos = origin + (target - origin) * fraction
            self._draw()

        self._motion = animate(self, 160, step, previous=self._motion)

    def _draw(self):
        self.delete("all")
        w, h = self._track_w, self._track_h
        if self._state == "disabled":
            track, knob = CARD_ALT, BORDER_SOFT
        else:
            # The track colours travel with the knob instead of snapping.
            track, knob = mix(BORDER, ACCENT, self._pos), "#FFFFFF"
        self._track_picture = paint.panel(w, h, h / 2.0, track, self._outer)
        self.create_image(0, 0, anchor="nw", image=self._track_picture)
        pad = max(1, px(2))
        d = h - 2 * pad
        x = pad + (w - 2 * pad - d) * self._pos
        self._knob_picture = paint.panel(d, d, d / 2.0, knob, track,
                                         border=BORDER_SOFT)
        self.create_image(x, pad, anchor="nw", image=self._knob_picture)

    def configure(self, cnf=None, **kw):
        options = dict(cnf or {}, **kw)
        if "state" in options:
            self._state = options.pop("state")
            self.configure(cursor="arrow" if self._state == "disabled" else "hand2")
            self._draw()
        if options:
            super().configure(options)
    config = configure

    def settle(self):
        if self._motion is not None:
            self._motion.cancel()
            self._motion = None
        self._pos = 1.0 if bool(self._var.get()) else 0.0
        self._draw()


class GroupedList(tk.Frame):
    """A quiet header, then one white block of hairline separated rows.

    This is the shape macOS settings use, and it beats a stack of labelled
    fields for the same reason: the eye follows one edge down the page instead
    of hunting for where each control begins.
    """

    def __init__(self, parent, label=None, bg=BG, radius=None):
        super().__init__(parent, bg=bg)
        if label:
            # Capitals, because at this size and weight it is a marker above a
            # block rather than a sentence to be read.
            tk.Label(self, text=label.upper(), bg=bg, fg=TEXT_FAINT,
                     font=f("section"), anchor="w").pack(fill=tk.X, padx=px(4),
                                                         pady=(0, px(6)))
        self.body = tk.Frame(self, bg=CARD, highlightthickness=1, bd=0,
                             highlightbackground=BORDER_SOFT,
                             highlightcolor=BORDER_SOFT)
        self.body.pack(fill=tk.BOTH, expand=True)
        self._corners = round_corners(self.body, px(14) if radius is None else radius,
                                      outer_bg=bg, border=BORDER_SOFT)
        self._rows = 0

    def row(self, pad=(14, 11)):
        """One row. The separator above it appears for every row but the first."""
        if self._rows:
            tk.Frame(self.body, bg=BORDER_SOFT, height=1).pack(
                fill=tk.X, padx=(px(pad[0]), 0))
        holder = tk.Frame(self.body, bg=CARD)
        holder.pack(fill=tk.X, padx=px(pad[0]), pady=px(pad[1]))
        self._rows += 1
        return holder

    def switch_row(self, text, variable, hint=None, command=None):
        holder = self.row()
        line = tk.Frame(holder, bg=CARD)
        line.pack(fill=tk.X)
        copy = tk.Frame(line, bg=CARD)
        copy.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(copy, text=text, bg=CARD, fg=TEXT, font=f("body"),
                 anchor="w", justify="left").pack(fill=tk.X)
        if hint:
            note = tk.Label(copy, text=hint, bg=CARD, fg=TEXT_FAINT, font=f("small"),
                            anchor="w", justify="left")
            note.pack(fill=tk.X, pady=(px(2), 0))
            wrap_to_parent(note, inset=px(60))
        switch = Switch(line, variable=variable, command=command, bg=CARD)
        switch.pack(side=tk.RIGHT, padx=(px(14), 0))
        return switch


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
# Amber for the one action, white with a hairline for the one beside it, and
# nothing at all for everything further down the ladder. That is the whole
# ranking, and it is the same on every page.
_VARIANTS = {
    "primary":   dict(bg=ACCENT, fg=ON_ACCENT, hover=ACCENT_HOVER, press=ACCENT_PRESS),
    "secondary": dict(bg=CARD, fg=TEXT, hover=HOVER, press=BORDER,
                      border=BORDER),
    "ghost":     dict(bg=CARD, fg=TEXT_DIM, hover=HOVER, press=BORDER),
    "danger":    dict(bg=CARD, fg=ERR, hover=ERR_BG, press=ERR_BG, border=BORDER),
}
_SIZES = {
    "lg": dict(padx=20, pady=11, font="button", radius=10),
    "md": dict(padx=17, pady=9, font="button", radius=10),
    "sm": dict(padx=13, pady=6, font="small", radius=8),
}

# A button is lifted off the page by a hair. The amber one carries its own
# colour into its shadow, because a grey shadow under a warm fill looks like
# dirt. A ghost is flat: it is not a surface, it is a word you can press.
_SHADOWS = {
    "primary":   (1, 3, ACCENT_INK, 0.35),
    "secondary": (1, 2, TEXT, 0.06),
    "danger":    (1, 2, TEXT, 0.06),
    "ghost":     None,
}


def _shadow_for(variant):
    """The shadow of a variant, in real pixels for the screen in front of us."""
    shadow = _SHADOWS.get(variant)
    if not shadow:
        return None
    dy, blur, colour, alpha = shadow
    return (px(dy), px(blur), colour, alpha)


def _shadow_room(shadow) -> int:
    """How many pixels a shadow needs below the shape it belongs to."""
    if not shadow:
        return 0
    dy, blur = shadow[0], shadow[1]      # already in real pixels
    return int(math.ceil(dy + blur + px(paint._SHADOW_ROOM)))


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
        # A rounded box, not a pill. The drawing puts an 11 px radius on a
        # 42 px button, and a pill at that height reads as a chip, not a button.
        self._radius = px(dims["radius"])
        self._border = spec.get("border")
        self._shadow = _shadow_for(variant)
        self._below = _shadow_room(self._shadow)
        self._picture = None

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
        # The shadow falls below the shape, so the canvas has to be that much
        # taller or it would be cut off. The shape itself keeps its height.
        self.configure(width=width, height=height + self._below)

    def _draw(self, fill=None):
        """Put the painted shape down and the word on top of it.

        The shape is a picture worked out against the colour behind the button,
        because tkinter has no rounded corner and no shadow of its own. Asking
        for the same button twice costs nothing: the picture is kept.
        """
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w <= 1 or h <= 1:
            return
        shape_h = h - self._below
        if self._state == "disabled":
            fill, shadow, border = CARD_ALT, None, None
        else:
            fill = fill or self._fill
            shadow = self._shadow
            border = self._border
        picture = paint.panel(w, shape_h, self._radius, fill, self._outer,
                              border=border, border_width=max(1, px(1)),
                              shadow=shadow)
        self._picture = picture                    # tk keeps no reference itself
        self._shape = self.create_image(0, 0, anchor="nw", image=picture)
        colour = self._fg if self._state != "disabled" else TEXT_FAINT
        self._label = self.create_text(w / 2, shape_h / 2, text=self._text,
                                       fill=colour, font=self._font)

    def set_variant(self, variant):
        """Re-rank a button in place - the same action, a different weight.

        A page whose primary action changes with a setting would otherwise have
        to build two buttons and pack one away."""
        spec = _VARIANTS[variant]
        self._fill = spec["bg"] if variant != "ghost" else self._outer
        self._hover, self._press = spec["hover"], spec["press"]
        self._fg = spec["fg"]
        self._border = spec.get("border")
        self._shadow = _shadow_for(variant)
        below = _shadow_room(self._shadow)
        if below != self._below:
            self._below = below
            self._measure()
        self._draw()

    def _paint(self, colour):
        if self._state == "disabled" or self._shape is None:
            return
        self._draw(fill=colour)

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
class Field(tk.Frame):
    """A value in a rounded well.

    tkinter has no rounded entry and no smooth edge, so the well is a picture
    lying behind an ordinary entry. The entry keeps its own square corners, it
    just sits far enough inside the well that they are never on top of a
    rounded one. Everything an entry can do it still does; this only changes
    what it looks like.
    """

    PAD_X = 12
    PAD_Y = 8
    RADIUS = 10

    #: Which settings belong to the entry inside rather than to the well.
    _INNER = frozenset((
        "state", "width", "justify", "font", "textvariable", "fg", "foreground",
        "show", "validate", "validatecommand", "invalidcommand", "exportselection",
        "insertbackground", "readonlybackground", "disabledforeground",
    ))

    def __init__(self, parent, textvariable, mono=True, width=None,
                 justify="left", bg=None, **kw):
        outer = bg or parent["bg"]
        super().__init__(parent, bg=outer)
        self._outer = outer
        self._picture = None
        self._border = FIELD_BORDER
        self._size = (0, 0)

        self._well = tk.Label(self, bg=outer, bd=0, highlightthickness=0)
        self._well.place(x=0, y=0, relwidth=1, relheight=1)

        self.entry = tk.Entry(self, textvariable=textvariable, bg=FIELD, fg=TEXT,
                              insertbackground=ACCENT, relief="flat", bd=0,
                              highlightthickness=0, disabledbackground=CARD_ALT,
                              disabledforeground=TEXT_FAINT,
                              readonlybackground=CARD_ALT,
                              font=f("mono" if mono else "body"),
                              justify=justify, **kw)
        if width:
            self.entry.configure(width=width)
        self.entry.pack(fill=tk.BOTH, expand=True,
                        padx=px(self.PAD_X), pady=px(self.PAD_Y))
        # The entry is made after the well, so it is on top of it.
        self.entry.bind("<FocusIn>", lambda _e: self._edge(ACCENT), add="+")
        self.entry.bind("<FocusOut>", lambda _e: self._edge(FIELD_BORDER), add="+")
        self.bind("<Configure>", self._resized)

    # ── the well ────────────────────────────────────────────────────────────
    def _resized(self, event):
        if (event.width, event.height) == self._size or event.width <= 1:
            return
        self._size = (event.width, event.height)
        self._repaint()

    def _repaint(self):
        width, height = self._size
        if width <= 1 or height <= 1:
            return
        fill = FIELD
        if str(self.entry.cget("state")) in ("disabled", "readonly"):
            fill = CARD_ALT
        self._picture = paint.panel(width, height, px(self.RADIUS), fill,
                                    self._outer, border=self._border,
                                    border_width=max(1, px(1)))
        self._well.configure(image=self._picture)

    def _edge(self, colour):
        """A field being typed into says so with its own edge."""
        if colour == self._border:
            return
        self._border = colour
        self._repaint()

    # ── it still behaves like the entry it holds ────────────────────────────
    def configure(self, cnf=None, **kw):
        options = dict(cnf or {}, **kw)
        inner = {key: options.pop(key) for key in list(options)
                 if key in self._INNER}
        if inner:
            self.entry.configure(**inner)
            if "state" in inner:
                self._repaint()
        if options:
            super().configure(**options)
        return None

    config = configure

    def cget(self, key):
        if key in self._INNER:
            return self.entry.cget(key)
        return super().cget(key)

    def focus_set(self):
        self.entry.focus_set()

    focus = focus_set

    def __getattr__(self, name):
        # Anything a Frame does not have - get, insert, select_range, icursor -
        # belongs to the entry. Only reached when the lookup has already failed.
        if name.startswith("_") or "entry" not in self.__dict__:
            raise AttributeError(name)
        return getattr(self.__dict__["entry"], name)


def entry(parent, textvariable, mono=True, width=None, justify="left", **kw):
    return Field(parent, textvariable, mono=mono, width=width, justify=justify,
                 **kw)


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
                             font=f("small"), anchor="w", justify="left")
        self.hint.pack(fill=tk.X, pady=(px(5), 0))
        wrap_to_parent(self.hint)

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
        # The page is white too, so the outline is what makes this a box.
        super().__init__(parent, bg=bg, highlightthickness=1, bd=0,
                         highlightbackground=BORDER_SOFT, highlightcolor=BORDER_SOFT)
        round_corners(self, px(14), outer_bg=parent["bg"], border=BORDER_SOFT)
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


class _Chip(tk.Frame):
    """A rounded label whose fill can change: nav pill, segment, tag."""

    def __init__(self, parent, text, command=None, radius=9, outer=None,
                 pad=(13, 7), font_key="tab", bg=None):
        outer = outer or parent["bg"]
        super().__init__(parent, bg=outer)
        self._outer = outer
        self._radius = px(radius)
        self._fill = bg or outer
        self._picture = None
        self._size = (0, 0)
        # The rounded shape is a picture behind the word, worked out against
        # whatever the chip is standing on.
        self._back = tk.Label(self, bg=outer, bd=0, highlightthickness=0)
        self._back.place(x=0, y=0, relwidth=1, relheight=1)
        self._label = tk.Label(self, text=text, bg=self._fill, fg=TEXT_DIM,
                               font=f(font_key), padx=px(pad[0]), pady=px(pad[1]))
        self._label.pack()
        self.bind("<Configure>", self._resized)
        if command is not None:
            for widget in (self, self._label):
                widget.configure(cursor="hand2")
                widget.bind("<Button-1>", lambda _e: command())

    def _resized(self, event):
        if (event.width, event.height) == self._size or event.width <= 1:
            return
        self._size = (event.width, event.height)
        self._repaint()

    def _repaint(self):
        width, height = self._size
        if width <= 1 or height <= 1:
            return
        self._picture = paint.panel(width, height, self._radius, self._fill,
                                    self._outer)
        self._back.configure(image=self._picture)

    def set_fill(self, bg, fg, font_key=None):
        self._fill = bg
        self._label.configure(bg=bg, fg=fg)
        if font_key:
            self._label.configure(font=f(font_key))
        self._repaint()

    def set_text(self, text):
        self._label.configure(text=text)


def tag(parent, text, tone="idle", bg=None):
    """A small state word on a tinted pill. Reads at a glance, says one thing."""
    fg, fill = _TONE.get(tone, _TONE["idle"])
    chip = _Chip(parent, text, radius=11, outer=bg or parent["bg"],
                 pad=(9, 3), font_key="micro")
    chip.set_fill(fill, fg)
    return chip


class _Strip(tk.Canvas):
    """A row of words with one moving highlight behind them, drawn as a whole.

    One canvas rather than a widget per word, for one reason: a highlight that
    slides has to be able to sit half under two words at once, and a tk widget
    cannot be transparent. Drawn as text items it is trivial, and moving a
    canvas item is the one thing tk does at 60 a second.
    """

    def __init__(self, parent, items, command=None, bg=None, font_key="tab",
                 pad=(13, 7), radius=9, fill=HOVER, on_fg=TEXT, off_fg=TEXT_FAINT,
                 gap=2, track=None, track_radius=8, inset=0, shadow=None):
        self._bg = bg or parent["bg"]
        super().__init__(parent, bg=self._bg, highlightthickness=0, bd=0)
        self._command = command
        self._font = tkfont.Font(font=f(font_key))
        self._fill, self._on_fg, self._off_fg = fill, on_fg, off_fg
        self._radius = px(radius)
        # A strip may sit on a pill of its own: that is what tells a switch
        # (two choices, one of them true) apart from a row of tabs.
        self._track = track
        self._track_radius = px(track_radius)
        self._inset = px(inset)
        self._shadow = shadow
        self._pill_bg = track or self._bg
        self._pictures = {}
        self._active = None
        self._motion = None
        self._slots = {}
        self._labels = {}
        self._order = [key for key, _ in items]

        padx, pady = px(pad[0]), px(pad[1])
        height = self._font.metrics("linespace") + pady * 2
        x = self._inset
        for key, label in items:
            width = self._font.measure(label) + padx * 2
            self._slots[key] = (x, width)
            self._labels[key] = self.create_text(
                x + width / 2, self._inset + height / 2, text=label,
                font=f(font_key), fill=self._off_fg)
            x += width + px(gap)
        total_w = max(1, x - px(gap) + self._inset)
        total_h = height + self._inset * 2
        self.configure(width=total_w, height=total_h)
        self._height = height

        if self._track:
            self._track_picture = paint.panel(total_w, total_h,
                                              self._track_radius, self._track,
                                              self._bg)
            self.tag_lower(self.create_image(0, 0, anchor="nw",
                                             image=self._track_picture))

        # The highlight is a painted picture, because tkinter draws neither a
        # rounded corner nor a smooth edge. It is worked out once per width and
        # kept, so sliding from one word to the next costs nothing after the
        # first time.
        self._pill = self.create_image(0, self._inset, anchor="nw",
                                       image=self._pill_picture(1))
        self.tag_lower(self._pill)
        if self._track:
            self.tag_raise(self._pill)
            for item in self._labels.values():
                self.tag_raise(item)
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._hover)
        self.bind("<Leave>", lambda _e: self._paint_text())
        self.configure(cursor="hand2")

    # ── geometry ────────────────────────────────────────────────────────────
    def _at(self, x):
        for key, (left, width) in self._slots.items():
            if left <= x <= left + width:
                return key
        return None

    def _pill_picture(self, width):
        """The highlight at one width, worked out once and then remembered."""
        width = max(1, int(round(width)))
        kept = self._pictures.get(width)
        if kept is None:
            kept = paint.panel(width, self._height, self._radius, self._fill,
                               self._pill_bg, shadow=self._shadow)
            self._pictures[width] = kept
        return kept

    def _place_pill(self, left, width):
        self.itemconfigure(self._pill, image=self._pill_picture(width))
        self.coords(self._pill, left, self._inset)

    def _paint_text(self, pointer=None):
        for key, item in self._labels.items():
            if key == self._active:
                colour = self._on_fg
            elif key == pointer:
                colour = TEXT
            else:
                colour = self._off_fg
            self.itemconfigure(item, fill=colour)

    # ── behaviour ───────────────────────────────────────────────────────────
    def _click(self, event):
        key = self._at(event.x)
        if key is not None:
            self.select(key)

    def _hover(self, event):
        self._paint_text(self._at(event.x))

    def select(self, key, notify=True, animated=True):
        if key not in self._slots or key == self._active:
            return
        previous = self._active
        self._active = key
        target = self._slots[key]
        if previous is None or not animated:
            self._place_pill(*target)
        else:
            origin = self._slots[previous]

            def step(fraction):
                left = origin[0] + (target[0] - origin[0]) * fraction
                width = origin[1] + (target[1] - origin[1]) * fraction
                self._place_pill(left, width)

            self._motion = animate(self, 180, step, ease=ease_in_out,
                                   previous=self._motion)
        self._paint_text()
        if notify and self._command:
            self._command(key)

    def settle(self):
        if self._motion is not None:
            self._motion.cancel()
            self._motion = None
        if self._active is not None:
            self._place_pill(*self._slots[self._active])

    def set_label(self, key, text):
        if key not in self._labels:
            return
        self.itemconfigure(self._labels[key], text=text)

    def label_of(self, key):
        return self.itemcget(self._labels[key], "text") if key in self._labels else ""

    @property
    def active(self):
        return self._active


class Segmented(_Strip):
    """Two or three ways of doing the same thing, side by side in one pill.

    A grounding pill, and the chosen one lifted out of it in white. It is the
    same strip the tabs are made of, only sitting on a ground of its own: that
    is what tells a switch, where one of two is true, apart from a row of tabs,
    where one of four is open.
    """

    def __init__(self, parent, options, command=None, bg=None, font_key="tab"):
        super().__init__(parent, options, command=command, bg=bg,
                         font_key=font_key, pad=(13, 6), radius=8, fill=CARD,
                         on_fg=TEXT, off_fg=TEXT_FAINT, gap=0, track=HOVER,
                         track_radius=10, inset=3,
                         shadow=(px(1), px(2), TEXT, 0.10))
        if options:
            self.select(options[0][0], notify=False, animated=False)


# ─────────────────────────────────────────────────────────────────────────────
# The flow
# ─────────────────────────────────────────────────────────────────────────────
# One page, one chain of steps, top to bottom. A step that is done keeps its
# place and its answer; the one being worked on carries the only amber on the
# page; the ones after it stand there greyed so you can see what is coming.
# Everything a step produces - a log, an error, a result - appears inside that
# step, which is the whole reason there is no second window any more.

# A ring is thirty pixels across. Done is a filled circle with a drawn tick,
# running is white with a thick amber edge and its number, failed is a filled
# circle with a drawn cross, and coming is white with a thin grey edge. The
# tick and the cross are drawn rather than typed: a glyph from a font sits
# differently in every font and is never quite in the middle.
RING_SIZE = 30
_RING = {
    "done": dict(fill=OK, edge=None, width=0, ink="#FFFFFF", mark="tick"),
    "now":  dict(fill=CARD, edge=ACCENT, width=3, ink=TEXT, mark=None),
    "err":  dict(fill=ERR, edge=None, width=0, ink="#FFFFFF", mark="cross"),
    "next": dict(fill=CARD, edge=BORDER, width=1.5, ink=TEXT_FAINT, mark=None),
}
_STEP_TITLE = {"done": TEXT, "now": TEXT, "err": TEXT, "next": TEXT_FAINT}

# The six step symbols, drawn on a twenty four grid, two units thick, round
# ends. A symbol says what a step is about before the title is read.
SYMBOL_SIZE = 15
_SYMBOLS = {
    "file":    [[(5, 2), (14, 2), (18, 6), (18, 22), (5, 22), (5, 2)],
                [(14, 2), (14, 6), (18, 6)]],
    "shield":  [[(12, 2), (20, 6), (20, 13), (12, 20), (4, 13), (4, 6), (12, 2)],
                [(8, 11), (11, 14), (16, 8)]],
    "hash":    [[(4, 9), (20, 9)], [(4, 16), (20, 16)],
                [(10, 3), (8, 22)], [(17, 3), (15, 22)]],
    "lock":    [[(7, 11), (7, 7), (12, 3), (17, 7), (17, 11)],
                [(4, 11), (20, 11), (20, 21), (4, 21), (4, 11)]],
    "list":    [[(9, 6), (21, 6)], [(9, 12), (21, 12)], [(9, 18), (21, 18)],
                [(4, 6)], [(4, 12)], [(4, 18)]],
    "archive": [[(3, 4), (21, 4), (21, 9), (3, 9), (3, 4)],
                [(5, 9), (5, 21), (19, 21), (19, 9)],
                [(10, 14), (14, 14)]],
}


def symbol_picture(name, bg, colour=TEXT_FAINT, size=None):
    """One step symbol as a picture, worked out against the page behind it."""
    size = size or px(SYMBOL_SIZE)
    scale = size / 24.0
    paths = [[(x * scale, y * scale) for x, y in path]
             for path in _SYMBOLS[name]]
    return paint.strokes(size, size, paths, colour, bg,
                         thickness=max(1.2, 2.0 * scale))


# Drawn on a thirty by thirty grid and scaled to whatever the screen asks for.
_MARKS = {
    "tick":  [[(9.0, 15.5), (13.5, 20.0), (21.5, 10.5)]],
    "cross": [[(10.5, 10.5), (19.5, 19.5)], [(19.5, 10.5), (10.5, 19.5)]],
}


def ring_picture(state, size, bg):
    """The picture of one step ring, worked out against the page behind it."""
    spec = _RING[state]
    scale = size / float(RING_SIZE)
    edge_width = max(1, px(spec["width"])) if spec["width"] else 1.0
    if spec["mark"]:
        paths = [[(x * scale, y * scale) for x, y in path]
                 for path in _MARKS[spec["mark"]]]
        return paint.strokes(size, size, paths, spec["ink"], bg,
                             thickness=max(1.5, 3.0 * scale),
                             base=(size, size, size / 2.0, spec["fill"], bg))
    return paint.panel(size, size, size / 2.0, spec["fill"], bg,
                       border=spec["edge"], border_width=edge_width)


class Step(tk.Frame):
    """One link in the chain: a ring, a name, a note, and a body you fill."""

    RAIL = 38

    def __init__(self, parent, number, title, state="next", note="", bg=BG,
                 symbol=None):
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._number = number
        self._state = state
        self._symbol = symbol
        self.columnconfigure(1, weight=1)

        rail = tk.Frame(self, bg=bg, width=px(self.RAIL))
        rail.grid(row=0, column=0, sticky="ns")
        self._ring = tk.Canvas(rail, width=px(self.RAIL), height=px(self.RAIL),
                               bg=bg, highlightthickness=0, bd=0)
        self._ring.pack()
        self._line = tk.Frame(rail, bg=RAIL, width=max(1, px(2)))
        self._has_line = False

        content = tk.Frame(self, bg=bg)
        content.grid(row=0, column=1, sticky="nsew", padx=(px(10), 0))
        self._content = content

        head = tk.Frame(content, bg=bg, height=px(self.RAIL))
        head.pack(fill=tk.X)
        head.pack_propagate(False)
        if symbol:
            self._mark = symbol_picture(symbol, bg)
            tk.Label(head, image=self._mark, bg=bg, bd=0,
                     highlightthickness=0).pack(side=tk.LEFT,
                                                padx=(0, px(8)))
        self._title = tk.Label(head, text=title, bg=bg, fg=_STEP_TITLE[state],
                               font=f("step"), anchor="w")
        self._title.pack(side=tk.LEFT)
        self._note = tk.Label(head, text=note, bg=bg, fg=TEXT_FAINT,
                              font=f("small"), anchor="w")
        self._note.pack(side=tk.LEFT, padx=(px(9), 0))
        if not note:
            self._note.pack_forget()

        self.body = tk.Frame(content, bg=bg)
        self.body.pack(fill=tk.X, pady=(px(4), px(20)))
        self._motion = None
        self._walk = None
        self._paint()

    # ── the rail ────────────────────────────────────────────────────────────
    def connect(self):
        """Draw the line down to the next step. The last step never gets one."""
        if not self._has_line:
            self._line.pack(fill=tk.Y, expand=True, pady=(px(5), 0))
            self._has_line = True

    def last(self):
        self.body.pack_configure(pady=(px(4), 0))

    # ── state ───────────────────────────────────────────────────────────────
    def set_state(self, state):
        """Swap the ring. A step becoming done is a fact, not a transition.

        Until 3.1.1 the ring faded from one colour to the next. A picture
        cannot be faded without working out a new one for every frame, and the
        fade bought nothing: what a ring says is either true or it is not.
        """
        if state == self._state:
            return
        self._state = state
        self._title.configure(fg=_STEP_TITLE[state])
        self._paint()

    def settle(self):
        """Nothing is in flight any more, but the callers still say this."""
        self._paint()

    @property
    def state(self):
        return self._state

    def set_note(self, text, tone=None):
        self._note.configure(text=text or "",
                             fg=_TONE[tone][0] if tone else TEXT_FAINT)
        if text:
            if not self._note.winfo_manager():
                self._note.pack(side=tk.LEFT, padx=(px(9), 0))
        elif self._note.winfo_manager():
            self._note.pack_forget()

    def set_title(self, text):
        self._title.configure(text=text)

    def set_running(self, on: bool):
        """Show or hide the walking line inside this step.

        Deliberately not tied to the state: a step can be the one you are on
        without anything happening yet. The line says work is going on, so it
        is only ever switched on where work actually starts, and off where it
        honestly finishes or honestly fails.
        """
        if on:
            if self._walk is None:
                self._walk = Running(self.body, bg=self._bg)
            if not self._walk.winfo_manager():
                self._walk.pack(fill=tk.X, anchor="w", pady=(px(12), px(2)))
            self._walk.start()
        elif self._walk is not None:
            self._walk.stop()
            if self._walk.winfo_manager():
                self._walk.pack_forget()

    @property
    def is_running(self):
        return self._walk is not None and self._walk.running

    def clear(self):
        for child in self.body.winfo_children():
            child.destroy()
        self._walk = None

    def _paint(self):
        spec = _RING[self._state]
        canvas = self._ring
        canvas.delete("all")
        full = px(self.RAIL)
        size = px(RING_SIZE)
        at = (full - size) / 2
        self._picture = ring_picture(self._state, size, self._bg)
        canvas.create_image(at, at, anchor="nw", image=self._picture)
        if spec["mark"] is None:
            canvas.create_text(full / 2, full / 2 + px(0.5),
                               text=str(self._number), fill=spec["ink"],
                               font=f("ring"))


class Flow(tk.Frame):
    """The chain itself. Add steps in order; the rail is drawn between them."""

    def __init__(self, parent, bg=BG):
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._steps = []

    def step(self, title, state="next", note="", symbol=None):
        if self._steps:
            self._steps[-1].connect()
        item = Step(self, len(self._steps) + 1, title, state=state, note=note,
                    bg=self._bg, symbol=symbol)
        item.pack(fill=tk.X)
        item.last()
        if len(self._steps) >= 1:
            self._steps[-1].body.pack_configure(pady=(px(4), px(20)))
        self._steps.append(item)
        return item

    def __getitem__(self, index):
        return self._steps[index]

    def __len__(self):
        return len(self._steps)

    @property
    def steps(self):
        return list(self._steps)


class Running(tk.Canvas):
    """The line that walks while a step is working.

    A track and a runner, both painted. The runner is a picture that is moved
    along the track, which is the one kind of movement tkinter is good at. It
    appears when the action is pressed and it stays until the step is honestly
    finished or honestly failed, so it never says work is going on when it is
    not.
    """

    TRACK = 5
    WIDTH = 620
    SHARE = 0.28            # how much of the track the runner covers
    MS = 1300               # one pass, left to right

    def __init__(self, parent, bg=BG, width=None):
        self._track_w = px(width or self.WIDTH)
        self._track_h = px(self.TRACK)
        super().__init__(parent, bg=bg, highlightthickness=0, bd=0,
                         width=self._track_w, height=self._track_h)
        self._bg = bg
        radius = self._track_h / 2.0
        self._back = paint.panel(self._track_w, self._track_h, radius, HOVER, bg)
        runner_w = max(px(8), int(self._track_w * self.SHARE))
        self._runner_w = runner_w
        self._runner = paint.panel(runner_w, self._track_h, radius, ACCENT, HOVER)
        self.create_image(0, 0, anchor="nw", image=self._back)
        self._item = self.create_image(-runner_w, 0, anchor="nw",
                                       image=self._runner)
        self._motion = None
        self._on = False

    def start(self):
        if self._on:
            return
        self._on = True
        self._walk()

    def _walk(self):
        span = self._track_w + self._runner_w

        def move(fraction):
            self.coords(self._item, -self._runner_w + span * fraction, 0)

        def again():
            if self._on:
                self._walk()

        # Steady, not eased: a thing that is working does not speed up and
        # slow down, and an eased loop looks like a heartbeat.
        self._motion = animate(self, self.MS, move, done=again,
                               ease=lambda t: t, previous=self._motion)

    def stop(self):
        self._on = False
        if self._motion is not None:
            self._motion.cancel()
            self._motion = None
        self.coords(self._item, -self._runner_w, 0)

    @property
    def running(self):
        return self._on


class Banner(tk.Frame):
    """Inline result strip that replaces modal popups for routine feedback."""

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
                              anchor="w", justify="left", wraplength=px(560))
        self._action = tk.Label(inner, text="", bg=OK_BG, fg=OK, font=f("small"),
                                cursor="hand2", padx=px(8))
        self._action_command = None
        self._action.bind("<Button-1>", lambda _e: self._action_command
                          and self._action_command())
        self._close = icon_button(inner, "✕", self.hide, bg=OK_BG, fg=TEXT_FAINT,
                                  hover_fg=TEXT, hover_bg=OK_BG)
        # Icon, action link and close button share the row; whatever they take
        # is not available for the message. show() decides the pack order.
        wrap_to_parent(self._text, minimum=px(200),
                       inset=lambda: (self._icon.winfo_width()
                                      + self._action.winfo_width()
                                      + self._close.winfo_width() + px(36)))
        self._corners = round_corners(self._wrap, px(10), outer_bg=bg)
        self._visible = False

    def show(self, kind, text, action_text=None, action=None):
        fg, bg = _TONE.get(kind, _TONE["info"])
        icons = {"ok": "✓", "error": "✕", "warn": "!", "info": "i", "busy": "•"}
        self._wrap.configure(bg=bg)
        self._inner.configure(bg=bg)
        self._corners.set_fill(bg)
        self._bar.configure(bg=fg)
        self._icon.configure(bg=bg, fg=fg, text=icons.get(kind, "i"))
        self._text.configure(bg=bg, text=text)
        self._close.configure(bg=bg, activebackground=bg)
        on_hover(self._close, bg, bg, fg_normal=TEXT_FAINT, fg_active=TEXT)
        # Pack order decides who gets squeezed: the packer serves each widget in
        # turn and the last one lives on the remainder. The message is therefore
        # packed last, so an unbreakable file path cannot crowd out the link -
        # "Show in folder" used to arrive as "in".
        self._close.pack_forget()
        self._action.pack_forget()
        self._text.pack_forget()
        self._close.pack(side=tk.RIGHT, padx=(0, 8))
        if action_text and action:
            self._action_command = action
            self._action.configure(text=action_text, bg=bg, fg=fg,
                                   font=(f("small")[0], f("small")[1], "underline"))
            self._action.pack(side=tk.RIGHT, padx=(px(6), px(4)))
        self._text.pack(side=tk.LEFT, fill=tk.X, expand=True, pady=px(10))
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
        hr(self, bg=HAIRLINE)
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


# How far one notch of the wheel throws the page, and how quickly that dies
# away. Together they decide the feel: a notch travels about 120 px and coasts
# to a stop in something under half a second.
WHEEL_PUSH = 12
WHEEL_DECAY = 0.90
WHEEL_FLOOR = 0.6


def _has_room(widget) -> bool:
    """Can this widget still scroll, or is everything already in view?"""
    try:
        first, last = widget.yview()
    except (tk.TclError, ValueError, TypeError):
        return False
    return not (float(first) <= 0.0 and float(last) >= 1.0)


def claim_wheel(widget, lines=3):
    """Let a text or a table answer the wheel while it has somewhere to go.

    While it does not, the wheel goes to the page, which is what you expect
    when a log window shows five lines in a box that holds twelve.
    """
    widget._wheel_self = lambda w=widget: _has_room(w)
    widget.wheel = lambda notches, w=widget: w.yview_scroll(
        int(round(-notches * lines)) or (-1 if notches > 0 else 1), "units")
    return widget


def _scrollable_under(widget):
    """The thing that should answer the wheel for the widget under the pointer.

    A log window or a queue table scrolls itself while the pointer is over it;
    anywhere else the page scrolls. Walking up from the widget under the
    pointer is the only way to know which, and it replaces the old rule, which
    was to bind the wheel while the pointer was over the canvas. That rule
    quietly stopped working the moment the pointer touched any content, because
    entering a child makes the parent report that the pointer left.
    """
    while widget is not None:
        own = getattr(widget, "_wheel_self", None)
        if own is not None and own():
            return widget
        if isinstance(widget, VScroll):
            return widget
        widget = getattr(widget, "master", None)
    return None


def install_wheel(root):
    """One wheel binding for the whole window, routed by what is under it."""
    def handle(event):
        target = _scrollable_under(event.widget)
        if target is None:
            return None
        if event.num == 4:
            notches = 1
        elif event.num == 5:
            notches = -1
        else:
            notches = event.delta / 120.0 or (1 if event.delta > 0 else -1)
        target.wheel(notches)
        return "break"

    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        root.bind_all(sequence, handle, add="+")


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
        self.canvas.pack(fill="both", expand=True)
        # The scrollbar floats over the canvas, it does not take a column of
        # its own. A column that comes and goes changes the canvas width, that
        # rewraps every label, that changes the height, and that can call the
        # scrollbar back: the page used to shiver. Floating, the canvas keeps
        # one width for good. It lands in the page padding, over nothing.
        self._bar_shown = False
        self._region = None
        self._width = None
        self._velocity = 0.0
        self._glide_after = None

        self.inner.bind("<Configure>", self._sync_region)
        self.canvas.bind("<Configure>", self._fit_width)

    def _fit_width(self, event):
        if event.width == self._width:
            return
        self._width = event.width
        self.canvas.itemconfigure(self._window, width=event.width)

    def _sync_region(self, _=None):
        region = self.canvas.bbox("all")
        if region == self._region:
            return
        self._region = region
        self.canvas.configure(scrollregion=region)

    def _on_scroll(self, first, last):
        # Hide the scrollbar when everything fits, without touching the layout
        fits = float(first) <= 0.0 and float(last) >= 1.0
        if fits and self._bar_shown:
            self.scrollbar.place_forget()
            self._bar_shown = False
        elif not fits and not self._bar_shown:
            self.scrollbar.place(relx=1.0, rely=0.0, relheight=1.0, anchor="ne")
            self._bar_shown = True
        self.scrollbar.set(first, last)

    # ── the wheel ───────────────────────────────────────────────────────────
    def wheel(self, notches):
        """A notch does not jump the page, it gives it a push that runs out."""
        self._velocity += notches * px(WHEEL_PUSH)
        if self._glide_after is None:
            self._glide()

    def _glide(self):
        self._glide_after = None
        if abs(self._velocity) < WHEEL_FLOOR:
            self._velocity = 0.0
            return
        moved = self.scroll_by(self._velocity)
        self._velocity *= WHEEL_DECAY
        if not moved:                       # against the end, stop dead
            self._velocity = 0.0
            return
        try:
            self._glide_after = self.after(FRAME_MS, self._glide)
        except tk.TclError:
            self._glide_after = None

    def scroll_by(self, pixels) -> bool:
        """Move by pixels, not by lines. False when it was already at the end."""
        region = self.canvas.bbox("all")
        if not region:
            return False
        height = region[3] - region[1]
        view = self.canvas.winfo_height()
        if height <= view or view <= 1:
            return False
        before = self.canvas.canvasy(0)
        top = max(0, min(before - pixels, height - view))
        if abs(top - before) < 0.5:
            return False                       # already against that end
        self.canvas.yview_moveto(top / height)
        return True

    def settle(self):
        self._velocity = 0.0
        if self._glide_after is not None:
            try:
                self.after_cancel(self._glide_after)
            except tk.TclError:
                pass
            self._glide_after = None


class LogView(tk.Frame):
    """Read-only monospace output pane with colour tags and auto-hiding bars."""

    TAGS = {"ok": OK, "error": ERR, "warn": WARN, "info": INFO,
            "dim": TEXT_FAINT, "accent": ACCENT_INK}

    #: How far the square content has to sit inside the rounded shape so that
    #: none of its corners pokes out past the bend. Three tenths of the radius
    #: is where the curve has come in furthest, at forty five degrees.
    INSET = 0.3

    def __init__(self, parent, height=12, bg=FIELD, radius=10):
        super().__init__(parent, bg=bg, highlightthickness=1, bd=0,
                         highlightbackground=BORDER_SOFT,
                         highlightcolor=BORDER_SOFT)
        round_corners(self, px(radius), outer_bg=parent["bg"], border=BORDER_SOFT)
        from tkinter import ttk
        inset = max(1, int(px(radius) * self.INSET))
        holder = tk.Frame(self, bg=bg)
        holder.pack(fill=tk.BOTH, expand=True, padx=inset, pady=inset)
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
        claim_wheel(self.text)
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

    def write_all(self, lines, follow=False):
        """Whole report in one go: a list of (line, tag).

        One Tcl call instead of one per line. Sixty separate inserts is what
        made the window pause for a tenth of a second every time the pre-flight
        was redrawn, and it was redrawn on every keystroke.
        """
        pieces = []
        for line, tag in lines:
            pieces.append(line + "\n")
            pieces.append((tag,) if tag else ())
        self.text.configure(state="normal")
        if pieces:
            self.text.insert(tk.END, *pieces)
        if follow:
            self.text.see(tk.END)
        self.text.configure(state="disabled")

    def set_all(self, lines):
        """Replace everything with one report, in one call."""
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.configure(state="disabled")
        self.write_all(lines)
        self.scroll_top()

    def set_text(self, content, tag=None):
        self.clear()
        self.write(content.rstrip("\n"), tag)
        self.scroll_top()

    def scroll_top(self):
        self.text.yview_moveto(0)
        self.text.xview_moveto(0)


class Table(tk.Frame):
    """Bordered, dark-styled ttk.Treeview with an auto-hiding scrollbar."""

    def __init__(self, parent, columns, height=8, bg=CARD, radius=10):
        super().__init__(parent, bg=bg, highlightthickness=1, bd=0,
                         highlightbackground=BORDER_SOFT,
                         highlightcolor=BORDER_SOFT)
        round_corners(self, px(radius), outer_bg=parent["bg"], border=BORDER_SOFT)
        from tkinter import ttk
        inset = max(1, int(px(radius) * LogView.INSET))
        holder = tk.Frame(self, bg=bg)
        holder.pack(fill=tk.BOTH, expand=True, padx=inset, pady=inset)
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
        claim_wheel(self.tree)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.tag_configure("ok", foreground=OK)
        self.tree.tag_configure("error", foreground=ERR)
        self.tree.tag_configure("warn", foreground=WARN)
        self.tree.tag_configure("busy", foreground=ACCENT_INK)
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

    def __init__(self, parent, bg=BG, pad=34, width=None):
        super().__init__(parent, bg=bg)
        pad = px(pad)
        self.action = tk.Frame(self, bg=SURFACE)
        self.action.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(self.action, bg=HAIRLINE, height=1).pack(fill=tk.X)
        self.action_row = tk.Frame(self.action, bg=SURFACE)
        self.action_row.pack(fill=tk.X, padx=pad, pady=px(13))

        holder = tk.Frame(self, bg=bg)
        holder.pack(side=tk.BOTTOM, fill=tk.X, padx=pad, pady=(0, 12))
        self.banner = Banner(holder, bg=bg)
        self.banner.pack(fill=tk.X)

        self.scroll = VScroll(self, bg=bg)
        self.scroll.pack(fill=tk.BOTH, expand=True)
        # A line of text that runs the full 1120 px is scanned, not read, so
        # the content keeps to a column and the window grows around it. Two
        # grid columns do it: the content one is held at a width by minsize,
        # the empty one beside it has all the weight and eats the remainder.
        row = tk.Frame(self.scroll.inner, bg=bg)
        row.pack(fill=tk.X, padx=pad, pady=(px(6), px(8)))
        row.columnconfigure(0, weight=0)
        row.columnconfigure(1, weight=1)
        self.body = tk.Frame(row, bg=bg)
        self.body.grid(row=0, column=0, sticky="new")
        tk.Frame(row, bg=bg).grid(row=0, column=1, sticky="nsew")
        if width:
            cap, floor, last = px(width), px(420), [None]

            def fit(width, _height):
                size = max(floor, min(cap, width))
                if size == last[0]:
                    return
                last[0] = size
                row.columnconfigure(0, minsize=size)

            on_resize(row, fit)

    def card(self, title, hint=None, pady=(0, 14)):
        card = Card(self.body, title=title, hint=hint)
        card.pack(fill=tk.X, pady=pady)
        return card

    def summary(self, variable):
        tk.Label(self.action_row, textvariable=variable, bg=SURFACE, fg=TEXT_DIM,
                 font=f("small"), anchor="w").pack(side=tk.LEFT)


class Collapsible(tk.Frame):
    """A disclosure section for everything that is only needed occasionally."""

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
        self._value = tk.Label(self, text="not set", bg=bg, fg=TEXT_FAINT, font=f("mono"),
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


class TopNav(tk.Frame):
    """The bar across the top: wordmark, the areas, and one word of state.

    It replaces the sidebar. A sidebar costs 238 px of width on every page and
    buys a column of four words; up here the same four words cost 68 px of
    height and the page gets the whole width back.
    """

    def __init__(self, parent, brand, items, command, bg=SURFACE,
                 languages=None, language=None, on_language=None):
        super().__init__(parent, bg=bg, height=px(60))
        self._bg = bg
        self._command = command
        self.language = None

        row = tk.Frame(self, bg=bg)
        row.pack(fill=tk.BOTH, expand=True, padx=px(26))

        logo = brand.header_logo(row, scale=SCALE)
        if logo is not None:
            logo.configure(bg=bg)
            logo.pack(side=tk.LEFT, pady=px(11))
        else:
            tk.Label(row, text=brand.VENDOR.upper(), bg=bg, fg=TEXT,
                     font=f("title")).pack(side=tk.LEFT)

        tk.Frame(row, bg=HAIRLINE, width=1).pack(side=tk.LEFT, fill=tk.Y,
                                                 padx=px(18), pady=px(20))

        # One canvas for the whole row, so the highlight can slide from one
        # word to the next instead of blinking out here and in over there.
        self.strip = _Strip(row, items, command=self._command, bg=bg)
        self.strip.pack(side=tk.LEFT)

        state = tk.Frame(row, bg=bg)
        state.pack(side=tk.RIGHT)

        # The language sits up here, on every page, instead of on a line
        # buried in the settings. It is one of the few things somebody changes
        # while looking at something else, so it has to be reachable from
        # wherever that is.
        if languages:
            self.language = _Strip(
                row, languages, command=on_language, bg=bg, font_key="section",
                pad=(9, 4), radius=6, fill=CARD, on_fg=TEXT, off_fg=TEXT_FAINT,
                gap=0, track=HOVER, track_radius=8, inset=2,
                shadow=(px(1), px(2), TEXT, 0.10))
            self.language.pack(side=tk.RIGHT, padx=(0, px(20)))
            if language:
                self.language.select(language, notify=False, animated=False)
        self._dot = tk.Canvas(state, width=px(9), height=px(9), bg=bg,
                              highlightthickness=0, bd=0)
        self._dot.pack(side=tk.LEFT, padx=(0, px(8)))
        self._state_var = tk.StringVar(value="")
        tk.Label(state, textvariable=self._state_var, bg=bg, fg=TEXT_DIM,
                 font=f("small")).pack(side=tk.LEFT)
        self.set_state("", "idle")

    def set_active(self, key):
        self.strip.select(key, notify=False)

    def settle(self):
        self.strip.settle()

    def set_label(self, key, text):
        self.strip.set_label(key, text)

    def label_of(self, key):
        return self.strip.label_of(key)

    def set_state(self, text, tone="idle"):
        self._state_var.set(text)
        colour = _TONE.get(tone, _TONE["idle"])[0]
        self._dot.delete("all")
        size = px(9)
        # Painted, not drawn: a nine pixel oval from tk has corners on it.
        self._dot_picture = paint.panel(size, size, size / 2.0, colour, self._bg)
        self._dot.create_image(0, 0, anchor="nw", image=self._dot_picture)


class Shell(tk.Frame):
    """
    The application frame: one bar across the top, a title block, the page
    itself, and a status line at the bottom. Every page lives in the same host
    and only the topmost one is seen, so switching areas moves nothing.
    """

    def __init__(self, root, brand, product, version, nav, on_select,
                 languages=None, language=None, on_language=None):
        super().__init__(root, bg=BG)
        self._on_select = on_select
        # Copied, not referenced: set_subtitle writes here, and the caller's nav
        # list is usually a class attribute that must not pick up per-instance edits.
        self._pages = dict((entry["key"], dict(entry)) for entry in nav)
        self._active = None
        self._mounted = {}
        self._motion = None

        self.nav = TopNav(self, brand,
                          [(entry["key"], entry["label"]) for entry in nav],
                          self.select, languages=languages, language=language,
                          on_language=on_language)
        self.nav.pack(fill=tk.X)
        self.nav.pack_propagate(False)
        tk.Frame(self, bg=HAIRLINE, height=1).pack(fill=tk.X)

        main = tk.Frame(self, bg=BG)
        main.pack(fill=tk.BOTH, expand=True)

        bar = tk.Frame(main, bg=BG)
        bar.pack(fill=tk.X, padx=px(34), pady=(px(24), px(16)))
        titles = tk.Frame(bar, bg=BG)
        titles.pack(fill=tk.X)
        self._title = tk.Label(titles, text="", bg=BG, fg=TEXT, font=f("h1"),
                               anchor="w")
        self._title.pack(side=tk.LEFT)
        # A page can hang one control up here, beside its own title: the
        # backup page puts its ZIP/BIN switch there, the way the drawing does.
        self.title_slot = tk.Frame(titles, bg=BG)
        self.title_slot.pack(side=tk.RIGHT)
        self._subtitle = tk.Label(bar, text="", bg=BG, fg=TEXT_FAINT, font=f("body"),
                                  anchor="nw", justify="left", wraplength=px(720))
        self._subtitle.pack(fill=tk.X, pady=(px(5), 0))
        wrap_to_parent(self._subtitle, minimum=px(320), inset=px(8))
        # The header keeps room for the longest subtitle of all pages, always.
        # Two pages whose subtitles need a different number of lines used to
        # move the whole page up or down on every click; this is why.
        self._subtitle_font = tkfont.Font(font=f("body"))
        self._subtitle_lines = None
        on_resize(bar, lambda width, _h: self._reserve_header(width))

        self.status = StatusBar(main, f"{brand.VENDOR}  \u00b7  v{version}")
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        self.host = tk.Frame(main, bg=BG)
        self.host.pack(fill=tk.BOTH, expand=True)
        self._reserve_header()

    def _reserve_header(self, bar_width=None):
        width = self._subtitle.cget("wraplength")
        if bar_width:
            width = max(px(320), bar_width - px(8))
        # Not just the subtitle a page shows now: every subtitle it can ever
        # show. A setting that rewords the header must not move the page under
        # it either. A nav entry lists its alternatives under "subtitles".
        lines = 1
        for page in self._pages.values():
            for text in page.get("subtitles") or [page.get("subtitle", "")]:
                lines = max(lines, wrapped_lines(text, self._subtitle_font, width))
        if lines == self._subtitle_lines:
            return
        self._subtitle_lines = lines
        self._subtitle.configure(height=lines)

    def mount(self, pages):
        """Put every page into the host at full size, and leave it there.

        Packing one page and unpacking the others on every click was the
        visible flaw: a page that has just been packed is one pixel wide for an
        instant, so every wrapped label reflows, the scroll region is measured
        again, and the rows settle in front of you. Placed, all pages carry the
        host's size from the first layout on, and a page change is one lift().
        """
        self._mounted = dict(pages)
        for page in self._mounted.values():
            page.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self.show(self._active, animated=False)

    # How far the incoming page starts below its place. Small on purpose: it
    # reads as arrival, not as a slideshow, and it is over in 140 ms.
    SLIDE = 0.02

    def show(self, key, animated=True):
        page = self._mounted.get(key)
        if page is None:
            return
        page.lift()
        if self._motion is not None:
            self._motion.cancel()
            self._motion = None
        if not animated:
            page.place_configure(rely=0.0)
            return
        # Every page is placed at full size, so this moves a frame. It does not
        # lay the page out again, which is what makes it cheap enough to run.
        def step(fraction):
            page.place_configure(rely=self.SLIDE * (1.0 - fraction))

        self._motion = animate(page, 140, step,
                               done=lambda: page.place_configure(rely=0.0))

    def settle(self):
        """Put everything exactly where it belongs, now. For the tests, and
        for a rebuild that must not catch a page mid flight."""
        if self._motion is not None:
            self._motion.cancel()
            self._motion = None
        finish_animations()
        for _ in range(5):
            if not flush_resize():
                break
            self.update_idletasks()
        for page in self._mounted.values():
            page.place_configure(rely=0.0)
        self.nav.settle()

    @property
    def active(self):
        """The key of the page on top. Every page stays mapped, so no widget
        can answer this any more."""
        return self._active

    def select(self, key):
        if key == self._active:
            return
        self._active = key
        self.nav.set_active(key)
        entry = self._pages[key]
        self._title.configure(text=entry.get("title", entry["label"]))
        self._subtitle.configure(text=entry.get("subtitle", ""))
        self._on_select(key)

    def set_label(self, key, text):
        """Rename an area. Used when the language changes."""
        self._pages[key]["label"] = text
        self.nav.set_label(key, text)

    def set_title(self, key, title, subtitle=None, subtitles=None):
        entry = self._pages[key]
        entry["title"] = title
        if subtitle is not None:
            entry["subtitle"] = subtitle
        if subtitles is not None:
            entry["subtitles"] = subtitles
        self._reserve_header()
        if self._active == key:
            self._title.configure(text=title)
            self._subtitle.configure(text=entry.get("subtitle", ""))

    def set_subtitle(self, key, text):
        """Reword a page header when a setting changes what the page does."""
        self._pages[key]["subtitle"] = text
        self._reserve_header()
        if self._active == key:
            self._subtitle.configure(text=text)
