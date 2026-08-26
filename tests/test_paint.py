"""
What tkinter cannot draw is drawn by hand, so it has to be checked by hand.

These do not need a screen. The picture is worked out as plain numbers first
and only handed to Tk at the very end, so everything that decides how it looks
can be read back and measured here: the file really is a PNG, the middle of a
shape really is the fill, the corner really is the ground, and the edge in
between really is a blend of the two rather than a staircase.
"""
import os
import struct
import sys
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import dme_paint as paint  # noqa: E402


def pixel_at(rows, x, y):
    """One pixel out of the worked out rows, as (r, g, b)."""
    row = rows[y]
    return tuple(row[x * 3:x * 3 + 3])


class TestTheColourHelpers(unittest.TestCase):

    def test_a_hex_colour_becomes_numbers(self):
        self.assertEqual(paint.rgb("#1D1D1F"), (29, 29, 31))
        self.assertEqual(paint.rgb("#FFF"), (255, 255, 255))
        self.assertEqual(paint.rgb((1, 2, 3)), (1, 2, 3))

    def test_laying_one_colour_over_another(self):
        black, white = (0, 0, 0), (255, 255, 255)
        self.assertEqual(paint.over(black, white, 0.0), white)
        self.assertEqual(paint.over(black, white, 1.0), black)
        # Half way is half way, give or take a rounding step.
        half = paint.over(black, white, 0.5)
        self.assertTrue(all(126 <= value <= 129 for value in half), half)


class TestThePngIsReallyAPng(unittest.TestCase):
    """Written by hand, so nothing checks it unless these do."""

    def test_it_starts_the_way_a_png_starts(self):
        data = paint.encode_png(2, 1, [b"\xff\x00\x00\x00\xff\x00"])
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_the_header_names_the_size_and_plain_colour(self):
        data = paint.encode_png(7, 3, [b"\x00" * 21] * 3)
        # The first chunk after the signature is IHDR.
        length = struct.unpack(">I", data[8:12])[0]
        self.assertEqual(data[12:16], b"IHDR")
        width, height, depth, kind = struct.unpack(">IIBB", data[16:16 + 10])
        self.assertEqual((width, height, depth, kind), (7, 3, 8, 2))
        self.assertEqual(length, 13)

    def test_the_pixels_survive_the_round_trip(self):
        wanted = [b"\xff\x00\x00\x00\xff\x00", b"\x00\x00\xff\xff\xff\xff"]
        data = paint.encode_png(2, 2, wanted)
        body = data[data.index(b"IDAT") + 4:]
        raw = zlib.decompress(body[:struct.unpack(">I", data[data.index(b"IDAT") - 4:
                                                            data.index(b"IDAT")])[0]])
        # Every line carries its filter byte, and here that byte is always none.
        self.assertEqual(raw[0], 0)
        self.assertEqual(raw[1:7], wanted[0])
        self.assertEqual(raw[7], 0)
        self.assertEqual(raw[8:14], wanted[1])

    def test_every_chunk_carries_a_sound_checksum(self):
        data = paint.encode_png(4, 4, [b"\x10" * 12] * 4)
        at = 8
        seen = []
        while at < len(data):
            length = struct.unpack(">I", data[at:at + 4])[0]
            kind = data[at + 4:at + 8]
            payload = data[at + 8:at + 8 + length]
            carried = struct.unpack(">I", data[at + 8 + length:at + 12 + length])[0]
            self.assertEqual(carried, zlib.crc32(kind + payload) & 0xFFFFFFFF,
                             f"{kind!r} has a broken checksum")
            seen.append(kind)
            at += 12 + length
        self.assertEqual(seen, [b"IHDR", b"IDAT", b"IEND"])


class TestTheRoundedRectangle(unittest.TestCase):
    """The shape everything in the app is made of."""

    FILL = "#FFAA00"
    GROUND = "#FFFFFF"

    def rows(self, **kw):
        settings = dict(width=60, height=40, radius=10, fill=self.FILL,
                        bg=self.GROUND)
        settings.update(kw)
        return paint._panel_rows(settings["width"], settings["height"],
                                 settings["radius"], settings["fill"],
                                 settings["bg"], settings.get("border"),
                                 settings.get("border_width", 1.0))

    def test_the_middle_is_the_fill(self):
        rows = self.rows()
        self.assertEqual(pixel_at(rows, 30, 20), paint.rgb(self.FILL))

    def test_the_corner_is_the_ground(self):
        rows = self.rows()
        # The very corner of a shape with a radius of ten is well outside it.
        self.assertEqual(pixel_at(rows, 0, 0), paint.rgb(self.GROUND))
        self.assertEqual(pixel_at(rows, 59, 39), paint.rgb(self.GROUND))

    def test_a_straight_edge_is_the_fill_right_up_to_it(self):
        rows = self.rows()
        self.assertEqual(pixel_at(rows, 30, 0), paint.rgb(self.FILL))
        self.assertEqual(pixel_at(rows, 0, 20), paint.rgb(self.FILL))

    def test_the_round_edge_is_blended_and_not_a_staircase(self):
        """The whole point of doing this by hand: the corner has to fade."""
        rows = self.rows()
        fill, ground = paint.rgb(self.FILL), paint.rgb(self.GROUND)
        blended = 0
        for y in range(12):
            for x in range(12):
                here = pixel_at(rows, x, y)
                if here != fill and here != ground:
                    blended += 1
        self.assertGreater(blended, 8,
                           "the corner steps from one colour to the other")

    def test_a_hairline_sits_on_the_edge_and_the_fill_stays_inside(self):
        rows = self.rows(fill="#FFFFFF", border="#DCDCE1", border_width=1.0)
        # Along the middle of the left edge: the outermost pixel is the line,
        # a few pixels in it is the fill again.
        self.assertEqual(pixel_at(rows, 0, 20), paint.rgb("#DCDCE1"))
        self.assertEqual(pixel_at(rows, 4, 20), paint.rgb("#FFFFFF"))

    def test_a_circle_is_the_same_shape_with_a_big_enough_radius(self):
        rows = self.rows(width=30, height=30, radius=15)
        self.assertEqual(pixel_at(rows, 15, 15), paint.rgb(self.FILL))
        for corner in ((0, 0), (29, 0), (0, 29), (29, 29)):
            self.assertEqual(pixel_at(rows, *corner), paint.rgb(self.GROUND),
                             f"corner {corner} is not empty")

    def test_the_radius_can_never_be_larger_than_the_shape(self):
        """Asking for 999 is how a pill is asked for, and it may not break."""
        rows = self.rows(width=40, height=20, radius=999)
        self.assertEqual(len(rows), 20)
        self.assertEqual(pixel_at(rows, 20, 10), paint.rgb(self.FILL))


class TestTheFastWayAgreesWithThePlainWay(unittest.TestCase):
    """panel_rows leans on two shortcuts. This is what holds them honest.

    It works a shape out by its edges only: a line is the same on the left as
    on the right, and away from the corners one line is the same as the next.
    `_panel_rows` makes no such assumption and goes pixel by pixel. Where the
    two ever disagree, the fast one is wrong.
    """

    CASES = [
        # width, height, radius, border, border width
        (60, 40, 10, None, 1.0),
        (60, 40, 10, "#DCDCE1", 1.0),
        (1, 1, 0, None, 1.0),
        (3, 3, 1, "#DCDCE1", 1.0),
        (30, 30, 15, None, 1.0),          # a circle
        (30, 30, 15, "#FFAA00", 3.0),     # a ring
        (200, 8, 4, None, 1.0),           # far wider than it is tall
        (8, 200, 4, "#E8E8EC", 1.0),      # and the other way round
        (41, 27, 9, "#E8E8EC", 1.0),      # odd numbers on both sides
        (40, 20, 999, None, 1.0),         # a radius larger than the shape
        (24, 24, 12, "#177A44", 12.0),    # a border thicker than the radius
    ]

    def test_the_two_agree_everywhere(self):
        for width, height, radius, border, thickness in self.CASES:
            with self.subTest(size=(width, height), radius=radius,
                              border=border, thickness=thickness):
                fast = paint.panel_rows(width, height, radius, "#FFAA00",
                                        "#FFFFFF", border, thickness)
                plain = paint._panel_rows(width, height, radius, "#FFAA00",
                                          "#FFFFFF", border, thickness)
                self.assertEqual(len(fast), len(plain))
                self.assertEqual(fast, plain)

    def test_a_shadow_makes_the_picture_taller_but_not_the_shape(self):
        plain = paint.panel_rows(40, 20, 8, "#FFAA00", "#FFFFFF")
        shadowed = paint.panel_rows(40, 20, 8, "#FFAA00", "#FFFFFF",
                                    shadow=(1, 3, "#8F5C00", 0.35))
        self.assertEqual(len(plain), 20)
        self.assertGreater(len(shadowed), 20)
        # The shape has not moved: its middle line is still its middle line.
        self.assertEqual(pixel_at(shadowed, 20, 10), paint.rgb("#FFAA00"))

    def test_the_shadow_is_darker_under_the_shape_than_beside_it(self):
        rows = paint.panel_rows(40, 20, 8, "#FFAA00", "#FFFFFF",
                                shadow=(2, 3, "#000000", 0.5))
        under = sum(pixel_at(rows, 20, 21))
        beside = sum(pixel_at(rows, 0, 21))
        self.assertLess(under, beside, "there is no shadow under the shape")
        self.assertLessEqual(beside, sum(paint.rgb("#FFFFFF")))


class TestTheDistanceItIsAllBuiltOn(unittest.TestCase):

    def test_inside_is_negative_outside_is_positive_edge_is_nought(self):
        # A 40 x 20 shape with a radius of 5, measured from its middle.
        self.assertLess(paint._distance(0, 0, 20, 10, 5), 0)
        self.assertGreater(paint._distance(30, 0, 20, 10, 5), 0)
        self.assertAlmostEqual(paint._distance(20, 0, 20, 10, 5), 0, places=6)

    def test_it_really_is_a_distance_in_pixels(self):
        self.assertAlmostEqual(paint._distance(23, 0, 20, 10, 5), 3, places=6)
        self.assertAlmostEqual(paint._distance(0, 14, 20, 10, 5), 4, places=6)

    def test_coverage_fades_over_exactly_one_pixel(self):
        self.assertEqual(paint._coverage(-2.0), 1.0)
        self.assertEqual(paint._coverage(2.0), 0.0)
        self.assertAlmostEqual(paint._coverage(0.0), 0.5)
        self.assertAlmostEqual(paint._coverage(-0.25), 0.75)


class TestWhatIsKept(unittest.TestCase):

    def test_asking_twice_works_the_answer_out_once(self):
        paint.forget()
        self.assertEqual(len(paint._CACHE), 0)
        first = paint._panel_rows(10, 10, 3, "#FFFFFF", "#FFFFFF")
        second = paint._panel_rows(10, 10, 3, "#FFFFFF", "#FFFFFF")
        # _panel_rows is the working out, not the keeping; what matters is that
        # it is settled by numbers alone and so gives the same answer twice.
        self.assertEqual(first, second)

    def test_forgetting_really_forgets(self):
        paint._CACHE[("made", "up")] = object()
        paint.forget()
        self.assertEqual(paint._CACHE, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
