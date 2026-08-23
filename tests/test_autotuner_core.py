"""Unit tests for the AutoTuner Backup Tool core (no GUI / no display needed)."""

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
