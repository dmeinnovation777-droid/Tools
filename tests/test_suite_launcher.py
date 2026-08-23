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

    def test_installer_script_is_ascii_only(self):
        # Inno Setup needs a BOM for non-ASCII sources; staying ASCII avoids it.
        with open(os.path.join(ROOT, "installer", "dme-innovation-tools.iss"), "rb") as handle:
            self.assertTrue(all(byte < 128 for byte in handle.read()))

    def test_tools_report_the_suite_version(self):
        import autotuner_tool
        import mhd_lock_tool
        self.assertEqual(autotuner_tool.APP_VERSION, brand.VERSION)
        self.assertEqual(mhd_lock_tool.APP_VERSION, brand.VERSION)


if __name__ == "__main__":
    unittest.main(verbosity=2)
