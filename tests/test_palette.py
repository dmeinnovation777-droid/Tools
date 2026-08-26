"""The palette has to survive its own maintenance.

The suite moved from a dark ground to a light one. Colours that
read fine as white-on-dark can be invisible as dark-on-white: the DME amber
went from 9.6:1 to 1.9:1 overnight, and it was still setting the type in the
archive listing. These tests compute the contrast instead of trusting the
comment beside the constant.

dme_ui needs tkinter, which the headless box does not have, so the palette is
read out of the source with ast. That is not a workaround - it also proves
every colour is a plain literal and none is computed at import time.
"""

import ast
import glob
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import autotuner_tool                       # noqa: E402  (tk-optional)

AA = 4.5        # body text
AA_LARGE = 3.0  # >=18 pt, and graphical objects such as the size bars


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


def _module():
    return ast.parse(_read("dme_ui.py"))


def _palette():
    """Every module-level NAME = "#rrggbb"."""
    out = {}
    for node in _module().body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
                and re.fullmatch(r"#[0-9A-Fa-f]{6}", node.value.value)):
            out[node.targets[0].id] = node.value.value
    return out


def _tone_pairs(palette):
    """_TONE maps a state to (ink, ground); both must be palette names."""
    for node in _module().body:
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "_TONE"):
            pairs = {}
            for key, value in zip(node.value.keys, node.value.values):
                names = [element.id for element in value.elts]
                pairs[key.value] = tuple(palette[name] for name in names)
            return pairs
    raise AssertionError("dme_ui._TONE not found")


def _log_tags(palette):
    for node in ast.walk(_module()):
        if isinstance(node, ast.ClassDef) and node.name == "LogView":
            for item in node.body:
                if (isinstance(item, ast.Assign)
                        and getattr(item.targets[0], "id", "") == "TAGS"):
                    return {k.value: palette[v.id]
                            for k, v in zip(item.value.keys, item.value.values)}
    raise AssertionError("dme_ui.LogView.TAGS not found")


def _luminance(colour):
    channels = [int(colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    channels = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
                for c in channels]
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a, b):
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


class ContrastCase(unittest.TestCase):
    def setUp(self):
        self.p = _palette()
        self.grounds = {name: self.p[name] for name in
                        ("BG", "SURFACE", "CARD", "CARD_ALT", "HOVER", "FIELD",
                         "HAIRLINE")}

    def assertReadable(self, ink, ground, minimum=AA, label=""):
        got = contrast(ink, ground)
        self.assertGreaterEqual(round(got, 2), minimum,
                                f"{label}: {ink} on {ground} is {got:.2f}:1")


class TestTheHelper(ContrastCase):
    def test_it_agrees_with_the_known_extremes(self):
        self.assertAlmostEqual(contrast("#000000", "#FFFFFF"), 21.0, places=2)
        self.assertAlmostEqual(contrast("#FFFFFF", "#FFFFFF"), 1.0, places=2)

    def test_the_palette_actually_parsed(self):
        self.assertGreaterEqual(len(self.p), 20)
        self.assertEqual(self.p["ACCENT"], "#FFAA00")


class TestContrast(ContrastCase):
    def test_every_text_step_reads_on_every_ground(self):
        for name in ("TEXT", "TEXT_DIM", "TEXT_FAINT"):
            for ground, value in self.grounds.items():
                self.assertReadable(self.p[name], value, label=f"{name} on {ground}")

    def test_the_amber_pill_carries_its_label(self):
        for state in ("ACCENT", "ACCENT_HOVER", "ACCENT_PRESS"):
            self.assertReadable(self.p["ON_ACCENT"], self.p[state], label=state)

    def test_the_amber_that_sets_type_is_the_dark_one(self):
        for name in ("CARD", "BG", "CARD_ALT", "FIELD", "WARN_BG"):
            self.assertReadable(self.p["ACCENT_INK"], self.p[name],
                                label=f"ACCENT_INK on {name}")

    def test_status_inks_read_on_their_tint_and_on_a_card(self):
        for ink, tint in (("OK", "OK_BG"), ("ERR", "ERR_BG"),
                          ("WARN", "WARN_BG"), ("INFO", "INFO_BG")):
            for ground in (tint, "CARD", "BG"):
                self.assertReadable(self.p[ink], self.p[ground],
                                    label=f"{ink} on {ground}")

    def test_every_tone_pair_is_legible(self):
        for tone, (ink, ground) in _tone_pairs(self.p).items():
            self.assertReadable(ink, ground, label=f"tone {tone}")

    def test_log_tags_read_in_the_log_well(self):
        for tag, colour in _log_tags(self.p).items():
            self.assertReadable(colour, self.p["FIELD"], label=f"log tag {tag}")


class TestThePartColours(ContrastCase):
    def test_they_are_visible_bars(self):
        """They are 3 px bars and a proportion strip, not type - 3:1 applies."""
        for colour in autotuner_tool.PartRow.COLOURS:
            for ground in ("CARD", "CARD_ALT"):
                self.assertReadable(colour, self.p[ground], AA_LARGE,
                                    label=f"part colour on {ground}")

    def test_they_stay_distinct_from_one_another(self):
        colours = autotuner_tool.PartRow.COLOURS
        self.assertEqual(len(set(colours)), len(colours))


class TestTheFillAmberNeverSetsType(unittest.TestCase):
    """ACCENT is a fill. ACCENT_INK is the one that may be read."""

    FOREGROUND = re.compile(
        r"\b(?:fg|foreground|activeforeground|disabledforeground)\s*=\s*"
        r"(?:ui\.)?ACCENT\b(?!_)")

    def test_no_widget_paints_text_in_the_fill_amber(self):
        offenders = []
        for path in sorted(glob.glob(os.path.join(ROOT, "*.py"))):
            with open(path, encoding="utf-8") as handle:
                for number, line in enumerate(handle, 1):
                    if self.FOREGROUND.search(line):
                        offenders.append(f"{os.path.basename(path)}:{number}")
        self.assertEqual(offenders, [],
                         "ACCENT is 1.9:1 on white - text takes ACCENT_INK")

    def test_the_check_would_catch_a_relapse(self):
        for bad in ("fg=ui.ACCENT,", "foreground=ACCENT)", "activeforeground=ui.ACCENT"):
            self.assertTrue(self.FOREGROUND.search(bad), bad)
        for good in ("fg=ui.ACCENT_INK,", "bg=ACCENT", "insertbackground=ACCENT",
                     "fg=ON_ACCENT"):
            self.assertIsNone(self.FOREGROUND.search(good), good)


class TestNoDashesInWhatTheUserReads(unittest.TestCase):
    """The house style has no em dashes. They are easy to type back in.

    Checked on string literals only, so code, comments and real file names such
    as how-to-use-backup.html are none of this test's business.
    """

    DASHES = "\u2014\u2013\u2012\u2015"

    def offenders(self, path):
        import ast
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        found = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and any(d in node.value for d in self.DASHES)):
                found.append(f"{os.path.basename(path)}:{node.lineno}  {node.value[:60]!r}")
        return found

    def test_no_tool_writes_one(self):
        offenders = []
        for name in ("dme_ui.py", "dme_brand.py", "dme_suite.py",
                     "mhd_lock_tool.py", "autotuner_tool.py"):
            offenders += self.offenders(os.path.join(ROOT, name))
        self.assertEqual(offenders, [], "use a comma, a full stop or a middle dot")

    def test_the_check_would_catch_one(self):
        import ast, tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8") as handle:
            handle.write('x = "a \u2014 b"\n')
            name = handle.name
        try:
            self.assertEqual(len(self.offenders(name)), 1)
        finally:
            os.unlink(name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
