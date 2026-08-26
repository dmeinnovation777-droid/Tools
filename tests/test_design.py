"""
The design was handed over as a written specification, so it can be checked.

These are not about how the app looks - a picture cannot be asserted - but
about the decisions underneath it that are easy to undo by accident later:
which colours exist, what may be amber, where the language switch lives, that
every step carries a symbol, and that the walking line only ever walks while
something is really being done.

The contrast rules have their own file and stay there. This one is about the
handoff.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import dme_paint as paint      # noqa: E402
import dme_text                # noqa: E402

# Everything below is read out of the source rather than imported. The widget
# kit needs tkinter, which the machine running the plain test suite does not
# have, and a check that quietly skips on the build machine is not a check.


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as handle:
        return handle.read()


class TestThePaletteIsTheOneHandedOver(unittest.TestCase):
    """Every colour named in the handoff, to the digit."""

    WANTED = {
        "SURFACE": "#FFFFFF", "BG": "#FFFFFF", "CARD": "#FFFFFF",
        "CARD_ALT": "#F7F7F9", "HOVER": "#F0F0F3", "BORDER": "#DCDCE1",
        "BORDER_SOFT": "#E8E8EC", "HAIRLINE": "#EDEDF1",
        "FIELD": "#F7F7F9", "FIELD_BORDER": "#E8E8EC",
        "TEXT": "#1D1D1F", "TEXT_DIM": "#48484B", "TEXT_FAINT": "#67676C",
        "ACCENT": "#FFAA00", "ON_ACCENT": "#1D1D1F", "ACCENT_INK": "#8F5C00",
        "OK": "#177A44", "OK_BG": "#E7F4EC",
        "ERR": "#B3261E", "ERR_BG": "#FBEAE9",
        "INFO": "#0066CC", "INFO_BG": "#E8F1FD",
    }

    def test_every_colour_is_unchanged(self):
        source = read("dme_ui.py")
        for name, value in self.WANTED.items():
            found = re.search(rf'^{name} = "(#[0-9A-Fa-f]{{6}})"', source, re.M)
            self.assertIsNotNone(found, f"{name} is gone from the palette")
            self.assertEqual(found.group(1).upper(), value,
                             f"{name} is no longer {value}")

    def test_amber_is_never_used_as_a_text_colour(self):
        """It is 1.9:1 on white. Where the brand has to be read, it is ACCENT_INK."""
        source = read("dme_ui.py")
        for line in source.splitlines():
            if "ACCENT" not in line or "ACCENT_INK" in line or "ACCENT_HOVER" in line:
                continue
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            self.assertNotRegex(stripped, r"\bfg\s*=\s*ACCENT\b",
                                f"amber used as type: {stripped}")


class TestTheShapesAreTheOnesAskedFor(unittest.TestCase):

    def test_the_radii_match_the_handoff(self):
        # Fields and buttons 10, step rings 30 across, symbols 15.
        source = read("dme_ui.py")
        for setting in (r"^    RADIUS = 10$", r"^RING_SIZE = 30$",
                        r"^SYMBOL_SIZE = 15$"):
            self.assertIsNotNone(re.search(setting, source, re.M),
                                 f"dme_ui no longer has {setting.strip('^$')}")
        for size in ("lg", "md"):
            row = re.search(rf'"{size}": dict\(([^)]*)\)', source)
            self.assertIsNotNone(row, f"the {size} button size is gone")
            self.assertIn("radius=10", row.group(1),
                          f"the {size} button is no longer a ten")

    def test_the_shadows_match_the_handoff(self):
        # The amber button carries its own colour into its shadow; a grey one
        # under a warm fill reads as dirt.
        source = read("dme_ui.py")
        block = source[source.index("_SHADOWS = {"):]
        block = block[:block.index("}")]
        self.assertIn('"primary":   (1, 3, ACCENT_INK, 0.35)', block)
        self.assertIn('"secondary": (1, 2, TEXT, 0.06)', block)
        self.assertIn('"ghost":     None', block)

    def test_the_running_line_is_the_one_described(self):
        source = read("dme_ui.py")
        block = source[source.index("class Running(tk.Canvas):"):]
        for setting in ("TRACK = 5", "SHARE = 0.28", "MS = 1300"):
            self.assertIn(setting, block[:2000],
                          f"the walking line no longer has {setting}")

    def test_there_is_a_symbol_for_every_step_the_handoff_names(self):
        source = read("dme_ui.py")
        block = source[source.index("_SYMBOLS = {"):]
        block = block[:block.index("\n}")]
        for name in ("file", "shield", "hash", "lock", "list", "archive"):
            self.assertIn(f'"{name}":', block, f"the {name} symbol is missing")

    def test_every_step_in_the_app_is_given_one(self):
        for name in ("mhd_lock_tool.py", "autotuner_tool.py"):
            source = read(name)
            for call in re.findall(r"flow\.step\(.*", source):
                self.assertIn("symbol=", call,
                              f"{name}: a step without a symbol: {call}")


class TestTheLanguageSwitchMovedIntoTheBar(unittest.TestCase):

    def test_the_bar_carries_it(self):
        source = read("dme_app.py")
        self.assertIn("languages=[(code, text.LANGUAGE_SHORT[code])", source)

    def test_it_says_two_letters_and_not_two_words(self):
        self.assertEqual(dme_text.LANGUAGE_SHORT["de"], "DE")
        self.assertEqual(dme_text.LANGUAGE_SHORT["en"], "EN")

    def test_the_settings_page_no_longer_has_a_language_row(self):
        source = read("dme_app.py")
        settings = source[source.index("def _build_settings"):
                          source.index("def set_language")]
        self.assertNotIn("word.language_hint", settings,
                         "the language line is still on the settings page")


class TestTheWalkingLineOnlyWalksForRealWork(unittest.TestCase):
    """The one rule in the handoff that a picture cannot show."""

    def test_it_is_not_tied_to_the_state_of_a_step(self):
        source = read("dme_ui.py")
        start = source.index("    def set_state(self, state):")
        body = source[start:source.index("    def settle(self):", start)]
        self.assertNotIn("set_running", body,
                         "a step becoming current would start the line")

    def test_every_run_switches_it_on_and_off_again(self):
        for name in ("mhd_lock_tool.py", "autotuner_tool.py"):
            source = read(name)
            on = len(re.findall(r"set_running\(True\)", source))
            off = len(re.findall(r"set_running\(False\)", source))
            self.assertGreater(on, 0, f"{name}: nothing ever starts the line")
            self.assertGreaterEqual(
                off, on, f"{name}: the line is started {on} times but only "
                         f"stopped {off}, so it would keep walking after a run")


class TestTheDrawingNeedsNothingInstalled(unittest.TestCase):
    """The pictures are the whole design. They may not add a dependency."""

    def test_it_imports_nothing_but_the_standard_library(self):
        source = read("dme_paint.py")
        imported = re.findall(r"^\s*import (\w+)", source, re.M)
        allowed = {"base64", "math", "struct", "zlib", "tkinter"}
        for name in imported:
            self.assertIn(name, allowed,
                          f"dme_paint reached for {name}, which has to ship")

    def test_it_works_with_no_display_at_all(self):
        """Everything that decides how a shape looks is plain arithmetic."""
        rows = paint._panel_rows(20, 12, 4, "#FFAA00", "#FFFFFF")
        self.assertEqual(len(rows), 12)
        self.assertEqual(len(rows[0]), 20 * 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
