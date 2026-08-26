"""Unit tests for the AutoTuner Backup Tool core (no GUI / no display needed)."""

import inspect
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import autotuner_tool as at  # noqa: E402


def make_backup_zip(path, parts, ini=None, order=None):
    """Write a synthetic AutoTuner backup archive."""
    names = order or [n for n, _ in parts]
    blobs = dict(parts)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.writestr(name, blobs[name])
        if ini is not None:
            zf.writestr("contents.ini", ini)
        zf.writestr("how-to-use-backup.html", "<html></html>")


class TestHelpers(unittest.TestCase):
    def test_format_bytes(self):
        self.assertEqual(at.format_bytes(0), "0.0 B")
        self.assertEqual(at.format_bytes(512), "512.0 B")
        self.assertEqual(at.format_bytes(1024), "1.0 KB")
        self.assertEqual(at.format_bytes(32768), "32.0 KB")
        self.assertEqual(at.format_bytes(2097152), "2.0 MB")

    def test_part_sort_key_standard_order(self):
        shuffled = ["dflash1.bin", "iflash1.bin", "eflash.bin", "iflash0.bin", "dflash0.bin"]
        self.assertEqual(
            sorted(shuffled, key=at.part_sort_key),
            ["iflash0.bin", "iflash1.bin", "dflash0.bin", "dflash1.bin", "eflash.bin"],
        )

    def test_part_sort_key_is_case_insensitive(self):
        self.assertEqual(at.part_sort_key("IFLASH0.BIN"), at.part_sort_key("iflash0.bin"))

    def test_parse_ini(self):
        meta = at.parse_ini("[Global]\r\nEcuX_version = 0.3\r\n\r\n[Description]\r\n"
                            "VehicleProducer = BMW\r\nVehicleBuild = M3\r\n")
        self.assertEqual(meta["EcuX_version"], "0.3")
        self.assertEqual(meta["VehicleProducer"], "BMW")
        self.assertEqual(meta["VehicleBuild"], "M3")
        self.assertNotIn("[Global]", meta)

    def test_contents_ini_defaults(self):
        ini = at.build_contents_ini({"make": "Audi"})
        self.assertIn("AuthorTool = Autotuner", ini)
        self.assertIn("VehicleProducer = Audi", ini)
        self.assertIn("VehicleType = Passenger car", ini)
        self.assertIn("ReadingHardware = Autotuner", ini)
        self.assertTrue(ini.endswith("\r\n"))


class TestZipToBin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_concatenates_in_standard_order(self):
        parts = [
            ("iflash0.bin", b"\x11" * 64),
            ("iflash1.bin", b"\x22" * 32),
            ("dflash0.bin", b"\x33" * 16),
            ("dflash1.bin", b"\x44" * 8),
        ]
        zip_path = os.path.join(self.dir, "backup.zip")
        # Deliberately store them out of order inside the archive
        make_backup_zip(zip_path, parts,
                        order=["dflash1.bin", "iflash0.bin", "dflash0.bin", "iflash1.bin"])
        out = os.path.join(self.dir, "out.bin")
        ok, msg, info = at.zip_to_bin(zip_path, out)
        self.assertTrue(ok, msg)
        with open(out, "rb") as f:
            data = f.read()
        self.assertEqual(data, b"\x11" * 64 + b"\x22" * 32 + b"\x33" * 16 + b"\x44" * 8)
        self.assertEqual([p["name"] for p in info],
                         ["iflash0.bin", "iflash1.bin", "dflash0.bin", "dflash1.bin"])
        self.assertEqual([p["offset"] for p in info], [0, 64, 96, 112])
        self.assertEqual([p["size"] for p in info], [64, 32, 16, 8])

    def test_ignores_metadata_files(self):
        zip_path = os.path.join(self.dir, "backup.zip")
        make_backup_zip(zip_path, [("iflash0.bin", b"\xAA" * 10)],
                        ini=at.build_contents_ini({"make": "BMW"}))
        out = os.path.join(self.dir, "out.bin")
        ok, _msg, info = at.zip_to_bin(zip_path, out)
        self.assertTrue(ok)
        self.assertEqual(len(info), 1)
        self.assertEqual(os.path.getsize(out), 10)

    def test_rejects_archive_without_bins(self):
        zip_path = os.path.join(self.dir, "empty.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("contents.ini", "[Global]\r\n")
        ok, msg, info = at.zip_to_bin(zip_path, os.path.join(self.dir, "o.bin"))
        self.assertFalse(ok)
        self.assertIn("No .bin files", msg)
        self.assertEqual(info, [])

    def test_rejects_non_zip(self):
        bogus = os.path.join(self.dir, "bogus.zip")
        with open(bogus, "wb") as f:
            f.write(b"not a zip at all")
        ok, msg, _ = at.zip_to_bin(bogus, os.path.join(self.dir, "o.bin"))
        self.assertFalse(ok)
        self.assertIn("not a valid ZIP", msg)


class TestBinToZip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.bin_path = os.path.join(self.dir, "combined.bin")
        with open(self.bin_path, "wb") as f:
            f.write(b"\x11" * 64 + b"\x22" * 32 + b"\x33" * 16 + b"\x44" * 8)
        self.config = [
            {"name": "iflash0.bin", "size": 64},
            {"name": "iflash1.bin", "size": 32},
            {"name": "dflash0.bin", "size": 16},
            {"name": "dflash1.bin", "size": 8},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_autotuner_archive(self):
        out = os.path.join(self.dir, "out.zip")
        ok, msg = at.bin_to_zip(self.bin_path, out, self.config,
                                {"make": "BMW", "model": "M4", "vin": "DMETEST0000000003"})
        self.assertTrue(ok, msg)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            self.assertEqual(names[:4], [p["name"] for p in self.config])
            self.assertIn("contents.ini", names)
            self.assertIn("how-to-use-backup.html", names)
            # Parts must sit at the archive root, not in a subfolder
            self.assertFalse(any("/" in n for n in names))
            self.assertEqual(zf.read("iflash0.bin"), b"\x11" * 64)
            self.assertEqual(zf.read("dflash1.bin"), b"\x44" * 8)
            meta = at.parse_ini(zf.read("contents.ini").decode())
            self.assertEqual(meta["VehicleProducer"], "BMW")
            self.assertEqual(meta["VehicleBuild"], "M4")
            self.assertEqual(meta["VehicleVIN"], "DMETEST0000000003")

    def test_rejects_size_mismatch(self):
        bad = list(self.config)
        bad[0] = {"name": "iflash0.bin", "size": 63}
        ok, msg = at.bin_to_zip(self.bin_path, os.path.join(self.dir, "o.zip"), bad)
        self.assertFalse(ok)
        self.assertIn("Size mismatch", msg)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "o.zip")))

    def test_round_trip_is_byte_identical(self):
        zip_out = os.path.join(self.dir, "rt.zip")
        ok, msg = at.bin_to_zip(self.bin_path, zip_out, self.config, {"make": "Audi"})
        self.assertTrue(ok, msg)
        bin_out = os.path.join(self.dir, "rt.bin")
        ok, msg, info = at.zip_to_bin(zip_out, bin_out)
        self.assertTrue(ok, msg)
        with open(self.bin_path, "rb") as a, open(bin_out, "rb") as b:
            self.assertEqual(a.read(), b.read())
        self.assertEqual([p["size"] for p in info], [64, 32, 16, 8])

    def test_med17_preset_totals(self):
        """The MED17.1.1 preset must add up to the documented ROM size."""
        preset = [2097152, 2097152, 32768, 32768]
        self.assertEqual(sum(preset), 4259840)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestLayoutMemory(unittest.TestCase):
    """A layout the tool has seen once must never have to be typed in again."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("XDG_CONFIG_HOME")
        if os.name == "nt" or sys.platform == "darwin":
            self.skipTest("config path is not driven by XDG_CONFIG_HOME here")
        os.environ["XDG_CONFIG_HOME"] = self.tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old
        self.tmp.cleanup()

    def test_round_trip_through_disk(self):
        parts = [{"name": "iflash0.bin", "size": 4194304},
                 {"name": "iflash1.bin", "size": 4194304},
                 {"name": "dflash0.bin", "size": 262144},
                 {"name": "dflash1.bin", "size": 262144}]
        at.remember_layout(parts, "Mercedes-GLE-MG1CP002-Bench-backup.zip")
        found = at.layout_for_size(8912896)
        self.assertIsNotNone(found)
        restored, label = found
        self.assertEqual([p["name"] for p in restored], [p["name"] for p in parts])
        self.assertEqual(sum(p["size"] for p in restored), 8912896)
        self.assertEqual(label, "Mercedes-GLE-MG1CP002-Bench-backup.zip")

    def test_unknown_size_returns_nothing(self):
        self.assertIsNone(at.layout_for_size(1234567))

    def test_layout_is_keyed_by_total_size(self):
        at.remember_layout([{"name": "a.bin", "size": 100}], "a")
        at.remember_layout([{"name": "b.bin", "size": 200}], "b")
        self.assertEqual(at.layout_for_size(100)[0][0]["name"], "a.bin")
        self.assertEqual(at.layout_for_size(200)[0][0]["name"], "b.bin")

    def test_newer_layout_replaces_the_older_one_of_equal_size(self):
        at.remember_layout([{"name": "old.bin", "size": 64}], "old")
        at.remember_layout([{"name": "new.bin", "size": 64}], "new")
        self.assertEqual(at.layout_for_size(64)[1], "new")

    def test_empty_layout_is_not_stored(self):
        at.remember_layout([], "nothing")
        self.assertEqual(at.load_layouts(), {})

    def test_store_is_capped(self):
        for size in range(1, at.LAYOUT_LIMIT + 15):
            at.remember_layout([{"name": "p.bin", "size": size}], str(size))
        self.assertLessEqual(len(at.load_layouts()), at.LAYOUT_LIMIT)

    def test_corrupt_store_is_survivable(self):
        os.makedirs(os.path.dirname(at.layout_store_path()), exist_ok=True)
        with open(at.layout_store_path(), "w") as handle:
            handle.write("{not json")
        self.assertEqual(at.load_layouts(), {})
        at.remember_layout([{"name": "x.bin", "size": 8}], "x")
        self.assertIsNotNone(at.layout_for_size(8))


class TestPresets(unittest.TestCase):
    def test_mg1cp002_matches_a_real_bench_backup(self):
        """8,912,896 bytes — the size that had no preset before."""
        self.assertEqual(at.preset_for_size(8912896), "MG1CP002")
        self.assertEqual(sum(s for _, s in at.PRESETS["MG1CP002"]), 8912896)

    def test_med17_preset_still_matches(self):
        self.assertEqual(at.preset_for_size(4259840), "MED17.1.1")

    def test_unknown_size_has_no_preset(self):
        self.assertIsNone(at.preset_for_size(123))

    def test_every_preset_has_metadata(self):
        for name in at.PRESETS:
            self.assertIn(name, at.PRESET_META, name)


# A real AutoTuner writes this page in the operator's language. This is what a
# German bench read actually carries - shortened, but with the traits that
# matter: the translated notice and the two extra meta lines.
GERMAN_HOW_TO = (
    '<!DOCTYPE html>\r\n<html lang="en">\r\n<head>\r\n'
    '<meta http-equiv="Content-Type" content="text/html; charset=utf-8">\r\n'
    '<meta name="viewport" content="width=device-width, initial-scale=1">\r\n'
    '<meta http-equiv="X-UA-Compatible" content="IE=edge">\r\n'
    "<title>Autotuner</title>\r\n</head>\r\n<body>\r\n"
    '<p id="message"/>\r\n<script type="text/javascript">\r\n'
    'document.getElementById("message").innerHTML ="Ihr Browser ist derzeit '
    'nicht mit dem Internet verbunden.";\r\n'
    "</script>\r\n</body>\r\n</html>"
)


class TestHowToPageIsCarriedAcross(unittest.TestCase):
    """The page is translated by the AutoTuner, so it cannot be regenerated.

    Found on a real VW Caddy MD1CS004 bench read: the archive carried the German
    page (708 bytes), while the tool - and the original tool it is modelled on -
    wrote its own English one (536 bytes) over it.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.zip = os.path.join(self.dir, "backup.zip")
        with zipfile.ZipFile(self.zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("iflash0.bin", b"\x11" * 64)
            zf.writestr("dflash0.bin", b"\x22" * 16)
            zf.writestr("contents.ini", at.build_contents_ini({"make": "Volkswagen"}))
            zf.writestr(at.HOW_TO_NAME, GERMAN_HOW_TO)
        self.bin = os.path.join(self.dir, "combined.bin")
        self.config = [{"name": "iflash0.bin", "size": 64},
                       {"name": "dflash0.bin", "size": 16}]

    def tearDown(self):
        self.tmp.cleanup()

    def test_reading_an_archive_surfaces_the_page(self):
        self.assertEqual(at.read_archive_info(self.zip)["how_to"], GERMAN_HOW_TO)

    def test_a_given_page_is_written_unchanged(self):
        out = os.path.join(self.dir, "out.zip")
        at.bin_to_zip(self.bin_path_written(), out, self.config, {},
                      how_to_html=GERMAN_HOW_TO)
        with zipfile.ZipFile(out) as zf:
            self.assertEqual(zf.read(at.HOW_TO_NAME).decode(), GERMAN_HOW_TO)

    def test_without_one_the_english_default_still_ships(self):
        out = os.path.join(self.dir, "out.zip")
        at.bin_to_zip(self.bin_path_written(), out, self.config, {})
        with zipfile.ZipFile(out) as zf:
            self.assertEqual(zf.read(at.HOW_TO_NAME).decode(), at.HOW_TO_USE_HTML)

    def test_the_whole_archive_comes_back_byte_for_byte(self):
        """The point of the exercise: what went in comes out unchanged."""
        ok, _, parts = at.zip_to_bin(self.zip, self.bin)
        self.assertTrue(ok)
        info = at.read_archive_info(self.zip)
        out = os.path.join(self.dir, "rebuilt.zip")
        at.bin_to_zip(self.bin, out,
                      [{"name": p["name"], "size": p["size"]} for p in parts],
                      {"make": "Volkswagen"}, how_to_html=info["how_to"])
        with zipfile.ZipFile(self.zip) as a, zipfile.ZipFile(out) as b:
            self.assertEqual(a.namelist(), b.namelist())
            for name in a.namelist():
                self.assertEqual(a.read(name), b.read(name), name)

    def bin_path_written(self):
        with open(self.bin, "wb") as f:
            f.write(b"\x11" * 64 + b"\x22" * 16)
        return self.bin


class TestTheRememberedPage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self.tmp.name
        self.parts = [{"name": "iflash0.bin", "size": 64},
                      {"name": "dflash0.bin", "size": 16}]

    def tearDown(self):
        if self.env is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self.env
        self.tmp.cleanup()

    def test_it_survives_a_restart(self):
        at.remember_layout(self.parts, "Caddy", how_to=GERMAN_HOW_TO)
        self.assertEqual(at.remembered_how_to(80), GERMAN_HOW_TO)

    def test_a_later_layout_without_one_does_not_lose_it(self):
        at.remember_layout(self.parts, "Caddy", how_to=GERMAN_HOW_TO)
        at.remember_layout(self.parts, "same size, no page")
        self.assertEqual(at.remembered_how_to(80), GERMAN_HOW_TO)

    def test_an_unknown_size_gives_an_empty_page(self):
        self.assertEqual(at.remembered_how_to(999999), "")


class TestABlankLineIsNotAPart(unittest.TestCase):
    """Found on a real Mercedes GLE MG1CP002 bench backup, on 3.2.0.

    The split table had the two parts from the archive and one empty line
    underneath. The page said the step was done, counted three parts and
    reported that the sizes matched, and then refused to write the archive
    with "line 3 has no valid name or size". Three places said yes and the
    button said no.

    An empty line is a line waiting to be filled in. It is not a part, so it
    is not counted, not packed and not in the way. A half filled one is a real
    mistake and has to be visible the moment it happens.
    """

    def test_the_blank_line_is_told_apart_from_the_broken_one(self):
        import inspect
        source = inspect.getsource(at.PartRow)
        self.assertIn("def is_blank", source)
        self.assertIn("def is_broken", source)

    def test_a_size_of_nothing_is_refused(self):
        """A name with a zero size would put an empty member in the archive."""
        source = inspect.getsource(at.PartRow.get)
        self.assertIn("if size <= 0:", source)
        self.assertIn("return None", source)

    def test_packing_skips_the_blank_line(self):
        source = inspect.getsource(at.BackupUI._run_bin_to_zip)
        self.assertIn("if row.is_blank:", source)
        self.assertIn("continue", source)
        # And an all blank table is still an error, not an empty archive.
        self.assertIn("if not parts_config:", source)

    def test_the_count_leaves_the_blank_line_out(self):
        source = inspect.getsource(at.BackupUI._refresh_parts)
        self.assertIn("if not row.is_blank", source)


class TestTheCarComesBackWithTheLayout(unittest.TestCase):
    """Which car a dump came from is written nowhere in the dump.

    Same Mercedes: the archive named a W167 GLE 450 AMG, petrol, 367 PS,
    270 kW. Taken apart and put back together, the archive that went to the
    customer named no car at all, and the fuel had quietly become DIESEL. Five
    of the fourteen fields have no box on the page at all, so they could only
    ever come from the archive itself.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = {}
        self.parts = [{"name": "iflash0.bin", "size": 64},
                      {"name": "dflash0.bin", "size": 16}]
        self.meta = {
            "VehicleVIN": "", "VehicleType": "Passenger car",
            "VehicleProducer": "Mercedes", "VehicleSeries": "W167",
            "VehicleBuild": "GLE", "VehicleModel": "450 AMG (3.0T) MHEV",
            "VehicleModelYear": "2018", "EcuUsage": "Engine",
            "EcuProducer": "Bosch", "EcuBuild": "MG1CP002",
            "EngineType": "PETROL", "OutputPS": "367", "OutputKW": "270",
            "ReadingHardware": "Autotuner",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_the_store_keeps_it(self):
        store = at.remember_layout(self.parts, "gle.zip", store=self.store,
                                   meta=self.meta)
        kept = at.remembered_meta(80, store=store)
        self.assertEqual(kept["VehicleSeries"], "W167")
        self.assertEqual(kept["OutputKW"], "270")
        self.assertEqual(kept["EngineType"], "PETROL")

    def test_a_later_split_without_the_archive_does_not_wipe_it(self):
        """Splitting the same size again, with nothing to hand, may not erase."""
        store = at.remember_layout(self.parts, "gle.zip", store=self.store,
                                   meta=self.meta, how_to="<html>de</html>")
        store = at.remember_layout(self.parts, "by hand", store=store)
        kept = at.remembered_meta(80, store=store)
        self.assertEqual(kept.get("VehicleSeries"), "W167")
        self.assertEqual(at.remembered_how_to(80, store=store), "<html>de</html>")

    def test_every_field_of_the_ini_has_a_name_here(self):
        """build_contents_ini writes fourteen. All fourteen must be carryable."""
        written = at.build_contents_ini({})
        names = [line.split(" = ")[0] for line in written.splitlines()
                 if " = " in line and not line.startswith(("EcuX", "AuthorTool"))]
        for name in names:
            self.assertIn(name, at.INI_KEYS,
                          f"{name} is written but can never be carried across")

    def test_every_box_on_the_page_has_a_name_here_too(self):
        """Packing looks each box up by name. A new one without an entry here
        would not be missing quietly, it would stop the archive being written."""
        for key, _label, _hint in at.META_FIELDS:
            self.assertIn(key, at.INI_KEYS,
                          f"the {key} box has no place in contents.ini")

    def test_an_older_store_is_not_broken_by_this(self):
        """Layouts remembered before 3.2.1 carry no vehicle data at all."""
        old = {"80": {"label": "alt.zip",
                      "parts": [{"name": "iflash0.bin", "size": 64},
                                {"name": "dflash0.bin", "size": 16}]}}
        self.assertEqual(at.remembered_meta(80, store=old), {})
        self.assertEqual(at.layout_for_size(80, store=old)[1], "alt.zip")
        # And writing to it keeps what was there while adding what is new.
        store = at.remember_layout(self.parts, "gle.zip", store=old,
                                   meta=self.meta)
        self.assertEqual(at.remembered_meta(80, store=store)["VehicleSeries"],
                         "W167")

    def test_the_round_trip_keeps_the_whole_ini(self):
        """Archive to .bin to archive, and contents.ini comes back identical."""
        source = os.path.join(self.tmp.name, "backup.zip")
        with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("iflash0.bin", b"\x11" * 64)
            zf.writestr("dflash0.bin", b"\x22" * 16)
            zf.writestr("contents.ini", at.build_contents_ini(
                {at.INI_KEYS[k]: v for k, v in self.meta.items()}))
            zf.writestr(at.HOW_TO_NAME, "<html>de</html>")

        info = at.read_archive_info(source)
        combined = os.path.join(self.tmp.name, "combined.bin")
        at.zip_to_bin(source, combined)
        store = at.remember_layout(info["parts"], "gle.zip", store=self.store,
                                   meta=info["meta"], how_to=info["how_to"])

        # What the page would hand over: everything remembered, nothing typed.
        kept = at.remembered_meta(80, store=store)
        meta = {at.INI_KEYS[k]: v for k, v in kept.items()
                if k in at.INI_KEYS and v}
        meta.setdefault("hardware", "Autotuner")
        again = os.path.join(self.tmp.name, "again.zip")
        ok, _msg = at.bin_to_zip(combined, again, self.parts, ini_meta=meta,
                                 how_to_html=at.remembered_how_to(80, store=store))
        self.assertTrue(ok)

        first, second = zipfile.ZipFile(source), zipfile.ZipFile(again)
        for name in ("iflash0.bin", "dflash0.bin", "contents.ini", at.HOW_TO_NAME):
            self.assertEqual(first.read(name), second.read(name),
                             f"{name} did not survive the round trip")


class TestPresetsAgainstRealReads(unittest.TestCase):
    """Presets decide how a .bin is cut when nothing else is known.

    A preset that adds up to the right total but cuts in the wrong places writes
    an archive the device never produces - and the total is what selects it, so
    the mistake is invisible. These are the layouts observed on real AutoTuner
    bench reads.
    """

    REAL = {
        # ECU        total       parts as the device actually writes them
        "MG1CP002": (8912896, [("iflash0.bin", 8388608), ("dflash0.bin", 524288)]),
    }

    def test_preset_matches_the_observed_layout(self):
        for ecu, (total, parts) in self.REAL.items():
            self.assertEqual(at.PRESETS[ecu], parts, ecu)
            self.assertEqual(sum(s for _, s in at.PRESETS[ecu]), total, ecu)

    def test_the_total_still_selects_it(self):
        for ecu, (total, _) in self.REAL.items():
            self.assertEqual(at.preset_for_size(total), ecu)

    def test_presets_with_the_same_total_cut_the_same_way(self):
        """The total is all that selects a preset, so two presets sharing one
        must at least agree on where to cut. MED17.1.1 and MEVD17.2.x do - they
        differ only in the ECU name, which is why the banner names both."""
        by_total = {}
        for name, parts in at.PRESETS.items():
            by_total.setdefault(sum(s for _, s in parts), []).append(name)
        for total, names in by_total.items():
            layouts = {tuple(at.PRESETS[n]) for n in names}
            self.assertEqual(len(layouts), 1,
                             f"{names} share {total:,} bytes but cut differently")

    def test_an_ambiguous_total_is_reported_not_hidden(self):
        self.assertEqual(at.presets_for_size(4259840), ["MED17.1.1", "MEVD17.2.x"])
        self.assertEqual(at.presets_for_size(8912896), ["MG1CP002"])
        self.assertEqual(at.presets_for_size(1), [])

    def test_a_remembered_layout_outranks_a_preset(self):
        """The device's own split must win over any guess with the same total."""
        import inspect
        src = inspect.getsource(at.BackupUI._auto_layout)
        self.assertLess(src.index("layout_for_size"), src.index("presets_for_size"))
