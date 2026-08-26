"""
DME Innovation Tools · what tkinter cannot draw
===============================================

tkinter has no rounded corner, no soft shadow and no smooth edge. What it does
have is the picture: hand Tk an image and it puts it on the screen exactly as
it is. Every ground in this app is one flat, known colour, so a rounded and
softly shadowed shape can be worked out here against that colour and handed
over as an ordinary picture. Nothing has to be installed for it. The PNG is
written by hand, in plain Python, and Tk 8.6 reads it.

Two shapes are drawn here and everything in the app is made of them:

* `panel()`   a rounded rectangle with a fill, an optional hairline and an
              optional shadow. Fields, buttons, cards, pills, chips, banners,
              rings, the progress track and its runner are all this.
* `strokes()` thin lines with round ends: the six step symbols and the tick
              inside a finished ring.

Both are worked out once per size and colour and then kept, because the same
button is asked for again every time a page is built anew.

Nothing in here touches a widget. It takes numbers and colours and gives back
a picture, which makes it straightforward to check on its own.

© DME Innovation
"""

import base64
import math
import struct
import zlib

try:
    import tkinter as tk
    TK_AVAILABLE = True
except ImportError:                                   # headless box
    tk = None
    TK_AVAILABLE = False

#: Worked out pictures, kept by everything that describes them. A page built
#: again in the other language asks for exactly the same buttons.
_CACHE = {}

#: How far outside the shape a shadow may still be seen. Anything past this is
#: transparent anyway and only costs pixels.
_SHADOW_ROOM = 3


def forget() -> None:
    """Drop every kept picture. Only the tests need this."""
    _CACHE.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Colour
# ─────────────────────────────────────────────────────────────────────────────
def rgb(colour) -> tuple:
    """'#1D1D1F' to (29, 29, 31). Anything already a triple is passed through."""
    if isinstance(colour, tuple):
        return colour
    text = colour.lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def over(top, bottom, alpha: float) -> tuple:
    """`top` laid over `bottom` at `alpha`, both already triples."""
    if alpha <= 0:
        return bottom
    if alpha >= 1:
        return top
    rest = 1.0 - alpha
    return (int(top[0] * alpha + bottom[0] * rest + 0.5),
            int(top[1] * alpha + bottom[1] * rest + 0.5),
            int(top[2] * alpha + bottom[2] * rest + 0.5))


# ─────────────────────────────────────────────────────────────────────────────
# PNG, written by hand
# ─────────────────────────────────────────────────────────────────────────────
def encode_png(width: int, height: int, rows) -> bytes:
    """A plain RGB PNG. `rows` is one bytes object of 3 * width per line.

    No transparency: everything here is already worked out against the ground
    it will sit on, which is what makes the edges smooth in the first place.
    """
    raw = bytearray()
    for row in rows:
        raw.append(0)                                  # filter: none
        raw += row

    def chunk(kind, payload):
        body = kind + payload
        return (struct.pack(">I", len(payload)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 1))
            + chunk(b"IEND", b""))


def _image(width, height, rows):
    """The picture as Tk wants it."""
    data = base64.b64encode(encode_png(width, height, rows))
    return tk.PhotoImage(data=data, width=width, height=height)


# ─────────────────────────────────────────────────────────────────────────────
# The rounded rectangle
# ─────────────────────────────────────────────────────────────────────────────
def _distance(x, y, half_w, half_h, radius):
    """How far a point is outside a rounded rectangle centred on the origin.

    Negative inside, zero on the edge, positive outside, and it is a real
    distance in pixels, which is what makes a smooth edge possible: a pixel
    half a pixel outside gets half the colour.
    """
    dx = abs(x) - (half_w - radius)
    dy = abs(y) - (half_h - radius)
    outside = math.hypot(max(dx, 0.0), max(dy, 0.0))
    inside = min(max(dx, dy), 0.0)
    return outside + inside - radius


def _coverage(distance):
    """How much of a pixel the shape covers, from its distance to the edge."""
    if distance <= -0.5:
        return 1.0
    if distance >= 0.5:
        return 0.0
    return 0.5 - distance


def panel(width: int, height: int, radius: float, fill, bg,
          border=None, border_width: float = 1.0, shadow=None):
    """A rounded rectangle, worked out against `bg`, as a Tk picture.

    `shadow` is (dy, blur, colour, opacity) or None. It is drawn under the
    shape, shifted down by `dy`, with an edge that fades over `blur` pixels.
    The shape itself keeps its size; the picture simply grows enough at the
    bottom to have room for the shadow.
    """
    width = max(1, int(round(width)))
    height = max(1, int(round(height)))
    key = ("panel", width, height, round(float(radius), 2), fill, bg, border,
           round(float(border_width), 2), shadow)
    kept = _CACHE.get(key)
    if kept is not None:
        return kept

    fill_rgb = rgb(fill)
    bg_rgb = rgb(bg)
    border_rgb = rgb(border) if border else None
    if shadow:
        sh_dy, sh_blur, sh_colour, sh_alpha = shadow
        sh_rgb = rgb(sh_colour)
        sh_ramp = max(1.0, 2.0 * sh_blur + 1.0)
    else:
        sh_dy = sh_blur = sh_alpha = 0
        sh_rgb = None
        sh_ramp = 1.0

    radius = max(0.0, min(float(radius), width / 2.0, height / 2.0))
    half_w, half_h = width / 2.0, height / 2.0
    inner_w = max(0.0, half_w - border_width)
    inner_h = max(0.0, half_h - border_width)
    inner_r = max(0.0, radius - border_width)

    def pixel(px_x, px_y):
        """The colour of one pixel, centre at (px_x, px_y), origin in the middle."""
        colour = bg_rgb
        if sh_rgb is not None:
            far = _distance(px_x, px_y - sh_dy, half_w, half_h, radius)
            alpha = 0.5 - far / sh_ramp
            if alpha > 0.0:
                colour = over(sh_rgb, colour, min(1.0, alpha) * sh_alpha)
        outer = _coverage(_distance(px_x, px_y, half_w, half_h, radius))
        if outer <= 0.0:
            return colour
        if border_rgb is None:
            return over(fill_rgb, colour, outer)
        inside = _coverage(_distance(px_x, px_y, inner_w, inner_h, inner_r))
        edge = max(0.0, outer - inside)
        if edge > 0.0:
            colour = over(border_rgb, colour, edge)
        if inside > 0.0:
            colour = over(fill_rgb, colour, inside)
        return colour

    # Room underneath for the shadow, and never less than the shape itself.
    below = 0
    if sh_rgb is not None:
        below = max(0, int(math.ceil(sh_dy + sh_blur + _SHADOW_ROOM)))
    picture_h = height + below

    # A row is symmetric left to right, so only half of it is worked out. Rows
    # far from the top and the bottom are all the same row, so that one is
    # worked out once and repeated. On a wide card that is the difference
    # between fourteen thousand pixels and three hundred thousand.
    band = int(math.ceil(radius + border_width + sh_blur + abs(sh_dy))) + 2
    half_row = (width + 1) // 2

    # Away from the left and right edge nothing changes along a row either, so
    # only the edge is worked out and the middle is one colour repeated.
    edge_span = min(half_row, band)

    def row_bytes(y):
        py = y - half_h + 0.5
        half = [pixel(x - half_w + 0.5, py) for x in range(edge_span)]
        flat = half[-1] if half else bg_rgb
        half += [flat] * (half_row - edge_span)
        row = bytearray()
        for colour in half:
            row += bytes(colour)
        for x in range(half_row, width):
            row += bytes(half[width - 1 - x])
        return bytes(row)

    rows = []
    if 2 * band >= picture_h:
        rows = [row_bytes(y) for y in range(picture_h)]
    else:
        for y in range(band):
            rows.append(row_bytes(y))
        middle = row_bytes(band)
        rows.extend([middle] * (picture_h - 2 * band))
        for y in range(picture_h - band, picture_h):
            rows.append(row_bytes(y))

    picture = _image(width, picture_h, rows)
    _CACHE[key] = picture
    return picture


# ─────────────────────────────────────────────────────────────────────────────
# Thin lines with round ends
# ─────────────────────────────────────────────────────────────────────────────
def _to_segment(px_x, px_y, ax, ay, bx, by):
    """Distance from a point to a line that stops at both ends."""
    vx, vy = bx - ax, by - ay
    wx, wy = px_x - ax, px_y - ay
    length = vx * vx + vy * vy
    if length <= 1e-9:
        return math.hypot(wx, wy)
    along = (wx * vx + wy * vy) / length
    along = max(0.0, min(1.0, along))
    return math.hypot(wx - along * vx, wy - along * vy)


def strokes(width: int, height: int, paths, colour, bg, thickness: float = 2.0,
            base=None):
    """Lines with round ends and round corners, as a Tk picture.

    `paths` is a list of point lists in picture pixels. Every line is a
    capsule; drawing them together is the union of those capsules, which is
    why corners and ends come out round without any extra work.

    `base` is an already drawn picture description to sit on: a (kind, ...)
    key of a panel, so a tick can be put inside a filled ring in one picture.
    Passing None means the lines sit on the flat `bg`.
    """
    width = max(1, int(round(width)))
    height = max(1, int(round(height)))
    flat = tuple(tuple(tuple(point) for point in path) for path in paths)
    key = ("strokes", width, height, flat, colour, bg,
           round(float(thickness), 2), base)
    kept = _CACHE.get(key)
    if kept is not None:
        return kept

    line_rgb = rgb(colour)
    bg_rgb = rgb(bg)
    reach = thickness / 2.0

    ground = None
    if base is not None:
        ground = _panel_rows(*base)

    rows = []
    for y in range(height):
        py = y + 0.5
        row = bytearray()
        for x in range(width):
            px_x = x + 0.5
            under = bg_rgb
            if ground is not None:
                at = ground[y][x * 3:x * 3 + 3]
                under = (at[0], at[1], at[2])
            nearest = None
            for path in flat:
                if len(path) == 1:
                    here = math.hypot(px_x - path[0][0], py - path[0][1])
                    nearest = here if nearest is None else min(nearest, here)
                    continue
                for index in range(len(path) - 1):
                    ax, ay = path[index]
                    bx, by = path[index + 1]
                    here = _to_segment(px_x, py, ax, ay, bx, by)
                    nearest = here if nearest is None else min(nearest, here)
                    if nearest <= 0.0:
                        break
            alpha = _coverage(nearest - reach) if nearest is not None else 0.0
            row += bytes(over(line_rgb, under, alpha))
        rows.append(bytes(row))

    picture = _image(width, height, rows)
    _CACHE[key] = picture
    return picture


def _panel_rows(width, height, radius, fill, bg, border=None,
                border_width=1.0):
    """The pixels a panel would have, without making a picture of them.

    Only `strokes` needs this, to draw a tick on top of a ring in one go, so
    it knows nothing about shadows: a ring does not have one.
    """
    width = max(1, int(round(width)))
    height = max(1, int(round(height)))
    fill_rgb, bg_rgb = rgb(fill), rgb(bg)
    border_rgb = rgb(border) if border else None
    radius = max(0.0, min(float(radius), width / 2.0, height / 2.0))
    half_w, half_h = width / 2.0, height / 2.0
    inner_w = max(0.0, half_w - border_width)
    inner_h = max(0.0, half_h - border_width)
    inner_r = max(0.0, radius - border_width)
    rows = []
    for y in range(height):
        py = y - half_h + 0.5
        row = bytearray()
        for x in range(width):
            px_x = x - half_w + 0.5
            colour = bg_rgb
            outer = _coverage(_distance(px_x, py, half_w, half_h, radius))
            if outer > 0.0:
                if border_rgb is None:
                    colour = over(fill_rgb, colour, outer)
                else:
                    inside = _coverage(_distance(px_x, py, inner_w, inner_h, inner_r))
                    edge = max(0.0, outer - inside)
                    if edge > 0.0:
                        colour = over(border_rgb, colour, edge)
                    if inside > 0.0:
                        colour = over(fill_rgb, colour, inside)
            row += bytes(colour)
        rows.append(bytes(row))
    return rows
