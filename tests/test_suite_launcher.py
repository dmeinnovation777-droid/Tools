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
    def test_every_tool_names_a_real_script_in_the_checkout(self):
        for tool in suite.TOOLS:
            self.assertTrue(os.path.isfile(os.path.join(ROOT, tool["script"])),
                            tool["name"])

    def test_every_tool_opens_a_real_area_of_the_app(self):
        """Three Start menu entries, one window: the key picks the page."""
        import dme_app
        for tool in suite.TOOLS:
            self.assertIn(tool["page"], dme_app.AREAS, tool["name"])

    def test_every_tool_is_fully_described(self):
        for tool in suite.TOOLS:
            for key in ("key", "name", "module", "script", "page"):
                self.assertIn(key, tool)
            self.assertTrue(tool["script"].endswith(".py"))
            self.assertEqual(tool["script"], tool["module"] + ".py")

    def test_tool_keys_are_unique_and_argument_safe(self):
        keys = [t["key"] for t in suite.TOOLS]
        self.assertEqual(len(set(keys)), len(keys))
        for key in keys:
            self.assertRegex(key, r"^[a-z][a-z0-9-]*$")

    def test_an_unknown_key_is_refused_not_guessed(self):
        self.assertIsNone(suite.tool_by_key("nope"))
        self.assertEqual(suite.run_tool("nope"), 2)
        self.assertEqual(suite.main(["--tool"]), 2)

    def test_every_key_reaches_a_real_module(self):
        import importlib
        for tool in suite.TOOLS:
            module = importlib.import_module(tool["module"])
            self.assertTrue(callable(module.main), tool["module"])

    def test_the_flag_hands_over_to_that_tool_and_returns_its_code(self):
        """The whole one-executable idea rests on this one hop."""
        import importlib
        for tool in suite.TOOLS:
            module = importlib.import_module(tool["module"])
            original, called = module.main, []
            module.main = lambda: (called.append(tool["key"]), 7)[1]
            try:
                self.assertEqual(suite.main(["--tool", tool["key"]]), 7)
            finally:
                module.main = original
            self.assertEqual(called, [tool["key"]])

    def test_the_flag_may_sit_anywhere_on_the_command_line(self):
        import importlib
        module = importlib.import_module(suite.TOOLS[0]["module"])
        original = module.main
        module.main = lambda: 0
        try:
            self.assertEqual(suite.main(["-x", "--tool", suite.TOOLS[0]["key"]]), 0)
        finally:
            module.main = original


class TestBuildFilesStayInSync(unittest.TestCase):
    """A renamed tool must not silently break the installer."""

    def read(self, *parts):
        with open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
            return handle.read()

    def test_every_build_bundles_every_tool(self):
        """A tool PyInstaller never sees is a tool the .exe cannot open, and
        nothing imports them at module level, so each needs a hidden import.

        Checked in BOTH places that call pyinstaller. The first version of this
        test only read build_exe.bat, while the release is built by the
        workflow - so 2.2.0 and 2.3.0 shipped a launcher whose tools died on
        ModuleNotFoundError, with a green test sitting next to it.
        """
        for parts in (("build_exe.bat",), (".github", "workflows", "build.yml")):
            script = self.read(*parts)
            where = "/".join(parts)
            self.assertIn(f'--name "{brand.SUITE}"', script, where)
            self.assertIn("dme_suite.py", script, where)
            # dme_app is imported inside main(), the areas inside dme_app, so
            # PyInstaller sees none of them without being told.
            for module in ["dme_app"] + [tool["module"] for tool in suite.TOOLS]:
                self.assertIn(f'--hidden-import {module}', script,
                              f"{where} does not bundle {module}")

    def test_no_build_still_makes_a_separate_exe_per_tool(self):
        """Leftovers would be shipped by neither installer nor launcher."""
        for parts in (("build_exe.bat",), (".github", "workflows", "build.yml")):
            script = self.read(*parts)
            for stale in ("AutoTuner Backup Tool.exe", "MHD Lock Tool.exe",
                          "autotuner_tool.py", "mhd_lock_tool.py"):
                if stale.endswith(".py"):
                    self.assertNotIn(f"{stale}\n", script, "/".join(parts))

    def test_the_release_build_starts_the_tools_before_shipping(self):
        """Reading a flag is not proof. The workflow runs the built .exe."""
        workflow = self.read(".github", "workflows", "build.yml")
        self.assertIn("tools/check_frozen_tools.py", workflow)
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "tools",
                                                    "check_frozen_tools.py")))

    def test_installer_ships_the_one_executable_and_a_shortcut_per_tool(self):
        iss = self.read("installer", "dme-innovation-tools.iss")
        self.assertIn(f"{brand.SUITE}.exe", iss)
        for tool in suite.TOOLS:
            self.assertIn(tool["name"], iss)
            self.assertIn(f'Parameters: "--tool {tool["key"]}"', iss)

    def test_installer_clears_the_executables_it_replaced(self):
        """Up to 2.1.1 each tool was its own .exe. Inno removes only what it
        ships, so an upgrade would leave two stale programs behind."""
        iss = self.read("installer", "dme-innovation-tools.iss")
        self.assertIn("[InstallDelete]", iss)
        for stale in ("AutoTuner Backup Tool.exe", "MHD Lock Tool.exe"):
            self.assertIn(f'Type: files; Name: "{{app}}\\{stale}"', iss)

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

    def test_documented_test_count_matches_the_suite(self):
        """Both files promise a number of tests. Every added test made that
        promise a little more wrong, three releases in a row."""
        suite = unittest.defaultTestLoader.discover(os.path.join(ROOT, "tests"))

        def count(item):
            if isinstance(item, unittest.TestSuite):
                return sum(count(child) for child in item)
            return 1

        actual = count(suite)
        pattern = re.compile(r"(\d+) Tests")
        for name in ("README.md", "STATUS.md"):
            claimed = pattern.findall(self.read(name))
            self.assertTrue(claimed, f"{name} names no test count")
            for number in claimed:
                self.assertEqual(int(number), actual,
                                 f"{name} says {number} tests, the suite has {actual}")


class TestTheSmokeTestsStandOnTheirOwn(unittest.TestCase):
    """A test that reads the machine's own settings is not a test.

    smoke_gui_autotuner passed here for a week and failed on the build machine
    for one reason: it used the real settings file, this machine had the app
    set to English, and the build machine had nothing and so ran in German.
    """

    def test_every_screen_test_brings_its_own_settings(self):
        folder = os.path.join(ROOT, "tests")
        for name in sorted(os.listdir(folder)):
            if not name.startswith("smoke_gui_"):
                continue
            with open(os.path.join(folder, name), encoding="utf-8") as handle:
                source = handle.read()
            self.assertIn("XDG_CONFIG_HOME", source,
                          f"{name} reads and writes the real settings")
            before = source.index("XDG_CONFIG_HOME")
            for module in ("import dme_app", "import autotuner_tool",
                           "import mhd_lock_tool"):
                at = source.find(module)
                if at >= 0:
                    self.assertLess(before, at,
                                    f"{name} sets XDG_CONFIG_HOME after "
                                    f"{module}, which is too late")


if __name__ == "__main__":
    unittest.main(verbosity=2)
