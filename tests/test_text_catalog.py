"""
The word list has to stay a word list.

Every entry must carry both languages, both must be real text, and both must
use the same placeholders. A German sentence that forgot its {vin} would print
a line with a hole in it, in front of a customer, and nothing else in the app
would notice.
"""
import os
import re
import string
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import dme_text  # noqa: E402

PLACEHOLDER = string.Formatter()


def placeholders(text: str) -> set:
    return {name for _, name, _, _ in PLACEHOLDER.parse(text) if name}


class TestEveryEntry(unittest.TestCase):
    def test_both_languages_present(self):
        for key, entry in dme_text.CATALOG.items():
            for code in dme_text.LANGUAGES:
                with self.subTest(key=key, language=code):
                    self.assertIn(code, entry, f"{key} has no {code}")
                    self.assertTrue(entry[code].strip(), f"{key}/{code} is empty")

    def test_no_stray_languages(self):
        for key, entry in dme_text.CATALOG.items():
            extra = set(entry) - set(dme_text.LANGUAGES)
            self.assertFalse(extra, f"{key} carries {extra}")

    def test_placeholders_match(self):
        for key, entry in dme_text.CATALOG.items():
            names = {code: placeholders(entry[code]) for code in dme_text.LANGUAGES}
            with self.subTest(key=key):
                self.assertEqual(names["de"], names["en"],
                                 f"{key}: {names['de']} against {names['en']}")

    def test_placeholders_are_named(self):
        # "{0}" or "{}" breaks the moment a translation reorders the sentence.
        for key, entry in dme_text.CATALOG.items():
            for code, text in entry.items():
                for name in placeholders(text):
                    with self.subTest(key=key, language=code):
                        self.assertFalse(str(name).isdigit(), f"{key}/{code}: {{{name}}}")


class TestHowItReads(unittest.TestCase):
    # His rule for the whole product: no dash standing in for a pause.
    DASH = re.compile(r"(?<=\S)\s[-–—]\s(?=\S)|(?<=\w)--(?=\w)")

    def test_no_dashes_in_the_middle_of_a_sentence(self):
        for key, entry in dme_text.CATALOG.items():
            for code, text in entry.items():
                with self.subTest(key=key, language=code):
                    self.assertIsNone(self.DASH.search(text),
                                      f"{key}/{code}: {text!r}")

    def test_no_double_spaces(self):
        for key, entry in dme_text.CATALOG.items():
            for code, text in entry.items():
                with self.subTest(key=key, language=code):
                    self.assertNotIn("  ", text, f"{key}/{code}: {text!r}")

    def test_no_leading_or_trailing_space(self):
        for key, entry in dme_text.CATALOG.items():
            for code, text in entry.items():
                with self.subTest(key=key, language=code):
                    self.assertEqual(text, text.strip(), f"{key}/{code}: {text!r}")


class TestLookup(unittest.TestCase):
    def setUp(self):
        self.addCleanup(dme_text.set_language, dme_text.DEFAULT_LANGUAGE)

    def test_default_is_german(self):
        dme_text.set_language(dme_text.DEFAULT_LANGUAGE)
        self.assertEqual(dme_text.language(), "de")
        self.assertEqual(dme_text.t("nav.lock"), "Locken")

    def test_switching(self):
        dme_text.set_language("en")
        self.assertEqual(dme_text.t("nav.lock"), "Lock")
        dme_text.set_language("de")
        self.assertEqual(dme_text.t("nav.lock"), "Locken")

    def test_unknown_language_falls_back(self):
        self.assertEqual(dme_text.set_language("fr"), "de")

    def test_unknown_key_returns_the_key(self):
        # Never an exception: a missing word may not take the window down.
        self.assertEqual(dme_text.t("nothing.here"), "nothing.here")

    def test_formatting(self):
        dme_text.set_language("de")
        self.assertIn("WBS1", dme_text.t("banner.locked", vin="WBS1"))

    def test_missing_value_does_not_raise(self):
        self.assertIsInstance(dme_text.t("banner.locked"), str)


if __name__ == "__main__":
    unittest.main()
