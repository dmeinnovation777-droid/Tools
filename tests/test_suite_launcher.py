"""Tests for the suite launcher and for keeping the build files in sync."""

import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import dme_brand as brand      # noqa: E402
import dme_suite as suite      # noqa: E402


class TestToolResolution(unittest.TestCase):
    def test_source_checkout_finds_the_scripts(self):
        for tool in suite.TOOLS:
            command = suite.resolve_tool(tool, frozen=False, base=ROOT)
            self.assertIsNotNone(command, tool["name"])
            self.assertTrue(command[-1].endswith(tool["script"]))
            self.assertTrue(os.path.isfile(command[-1]))

    def test_installed_build_starts_the_sibling_exe(self):
        with tempfile.TemporaryDirectory() as folder:
            for tool in suite.TOOLS:
                open(os.path.join(folder, tool["exe"]), "wb").close()
            for tool in suite.TOOLS:
                command = suite.resolve_tool(tool, frozen=True, base=folder)
                self.assertEqual(command, [os.path.join(folder, tool["exe"])])

    def test_missing_tool_returns_none(self):
        with tempfile.TemporaryDirectory() as folder:
            for tool in suite.TOOLS:
                self.assertIsNone(suite.resolve_tool(tool, frozen=True, base=folder))
                self.assertIsNone(suite.resolve_tool(tool, frozen=False, base=folder))

    def test_every_tool_is_fully_described(self):
        for tool in suite.TOOLS:
            for key in ("name", "exe", "script", "pitch", "bullets"):
                self.assertIn(key, tool)
            self.assertTrue(tool["exe"].endswith(".exe"))
            self.assertTrue(tool["script"].endswith(".py"))
            self.assertTrue(tool["bullets"])


class TestBuildFilesStayInSync(unittest.TestCase):
    """A renamed tool must not silently break the installer."""

    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_build_script_builds_every_tool_and_the_launcher(self):
        script = self.read("build_exe.bat")
        for tool in suite.TOOLS:
            self.assertIn(f'--name "{os.path.splitext(tool["exe"])[0]}"', script)
            self.assertIn(tool["script"], script)
        self.assertIn(f'--name "{brand.SUITE}"', script)
        self.assertIn("dme_suite.py", script)

    def test_installer_ships_every_tool(self):
        iss = self.read("installer", "dme-innovation-tools.iss")
        for tool in suite.TOOLS:
            self.assertIn(tool["exe"], iss)
        self.assertIn(f"{brand.SUITE}.exe", iss)

    def test_installer_default_version_matches_the_suite(self):
        iss = self.read("installer", "dme-innovation-tools.iss")
        match = re.search(r'#define\s+AppVersion\s+"([^"]+)"', iss)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), brand.VERSION)

    def test_header_plate_matches_the_sidebar(self):
        """Tk cannot alpha-composite, so the wordmark plate is baked in at
        dme_brand.HEADER_BG. If that drifts from dme_ui.SURFACE, a lighter
        rectangle shows behind the logo - which is exactly what shipped in 1.3.0."""
        surface = re.search(r'^SURFACE = "([^"]+)"', self.read("dme_ui.py"), re.M)
        self.assertIsNotNone(surface)
        self.assertEqual(brand.HEADER_BG.upper(), surface.group(1).upper())

    def test_asset_generator_bakes_the_same_colour(self):
        baked = re.search(r"^HEADER_BG = \((\d+), (\d+), (\d+)\)",
                          self.read("tools", "generate_assets.py"), re.M)
        self.assertIsNotNone(baked)
        self.assertEqual("#%02X%02X%02X" % tuple(int(g) for g in baked.groups()),
                         brand.HEADER_BG.upper())

    def test_installer_script_is_ascii_only(self):
        # Inno Setup needs a BOM for non-ASCII sources; staying ASCII avoids it.
        with open(os.path.join(ROOT, "installer", "dme-innovation-tools.iss"), "rb") as handle:
            self.assertTrue(all(byte < 128 for byte in handle.read()))

    def test_tools_report_the_suite_version(self):
        import autotuner_tool
        import mhd_lock_tool
        self.assertEqual(autotuner_tool.APP_VERSION, brand.VERSION)
        self.assertEqual(mhd_lock_tool.APP_VERSION, brand.VERSION)

    def test_documented_setup_file_name_matches_the_suite(self):
        """A stale file name here is what the customer reads on the download page."""
        pattern = re.compile(r"DME-Innovation-Tools-Setup-([0-9]+(?:\.[0-9]+)+)\.exe")
        for parts in (("README.md",), ("installer", "RELEASE_NOTES.md")):
            found = pattern.findall(self.read(*parts))
            self.assertTrue(found, f"{'/'.join(parts)} names no setup file")
            for version in found:
                self.assertEqual(version, brand.VERSION, "/".join(parts))

    def test_status_notes_quote_the_current_version(self):
        match = re.search(r'`VERSION = "([^"]+)"`', self.read("STATUS.md"))
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), brand.VERSION)


if __name__ == "__main__":
    unittest.main(verbosity=2)
