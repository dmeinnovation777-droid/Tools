"""Unit tests for the MHD Lock Tool core (no GUI / no vendor tool needed)."""

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mhd_lock_tool as m  # noqa: E402


SAMPLE_XDF = textwrap.dedent("""\
    <?xml version="1.0" encoding="utf-8"?>
    <XDFFORMAT version="1.80">
      <XDFHEADER>
        <deftitle>Test definition</deftitle>
        <BASEOFFSET offset="0" subtract="0" />
        <REGION type="0xFFFFFFFF" startaddress="0x0" size="0x1000" name="Binary File" />
      </XDFHEADER>
      <XDFTABLE>
        <title>Boost target</title>
        <XDFAXIS id="x"><EMBEDDEDDATA /><indexcount>4</indexcount></XDFAXIS>
        <XDFAXIS id="y"><EMBEDDEDDATA /><indexcount>2</indexcount></XDFAXIS>
        <XDFAXIS id="z">
          <EMBEDDEDDATA mmedaddress="0x100" mmedelementsizebits="16"
                        mmedrowcount="2" mmedcolcount="4"
                        mmedmajorstridebits="0" mmedminorstridebits="0" />
        </XDFAXIS>
      </XDFTABLE>
      <XDFTABLE>
        <title>Timing main</title>
        <XDFAXIS id="z">
          <EMBEDDEDDATA mmedaddress="0x200" mmedelementsizebits="8" mmedcolcount="16" />
        </XDFAXIS>
      </XDFTABLE>
      <XDFFLAG>
        <title>Enable antilag</title>
        <EMBEDDEDDATA mmedaddress="0x300" mmedelementsizebits="8" />
      </XDFFLAG>
    </XDFFORMAT>
    """)


def write(path, data):
    mode = "wb" if isinstance(data, (bytes, bytearray)) else "w"
    with open(path, mode) as handle:
        handle.write(data)
    return path


class TestVin(unittest.TestCase):
    def test_accepts_a_real_vin(self):
        ok, vin, _ = m.validate_vin("dmetest0000000001")
        self.assertTrue(ok)
        self.assertEqual(vin, "DMETEST0000000001")

    def test_strips_spaces_and_dashes(self):
        ok, vin, _ = m.validate_vin(" DMETES T0000-000001 ")
        self.assertTrue(ok)
        self.assertEqual(len(vin), 17)

    def test_rejects_wrong_length(self):
        ok, _vin, message = m.validate_vin("DMETEST000000000")
        self.assertFalse(ok)
        self.assertIn("17", message)

    def test_rejects_forbidden_letters(self):
        ok, _vin, message = m.validate_vin("DMETEST000000000I")
        self.assertFalse(ok)
        self.assertIn("invalid characters", message)

    def test_rejects_empty(self):
        self.assertFalse(m.validate_vin("")[0])


class TestDiff(unittest.TestCase):
    def test_finds_single_region(self):
        stock = bytes(64)
        tuned = bytearray(stock)
        tuned[10:14] = b"\x01\x02\x03\x04"
        self.assertEqual(m.diff_regions(stock, bytes(tuned)), [(10, 4)])
        self.assertEqual(m.changed_byte_count(stock, bytes(tuned)), 4)

    def test_merges_regions_within_the_gap(self):
        stock = bytes(64)
        tuned = bytearray(stock)
        tuned[10] = 1
        tuned[20] = 1          # 9 bytes apart -> merged with the default gap of 16
        tuned[60] = 1          # far away -> separate
        regions = m.diff_regions(bytes(stock), bytes(tuned))
        self.assertEqual(regions, [(10, 11), (60, 1)])

    def test_keeps_regions_apart_without_merging(self):
        stock = bytes(64)
        tuned = bytearray(stock)
        tuned[10] = 1
        tuned[20] = 1
        self.assertEqual(m.diff_regions(bytes(stock), bytes(tuned), merge_gap=0),
                         [(10, 1), (20, 1)])

    def test_reports_appended_data(self):
        regions = m.diff_regions(bytes(16), bytes(16) + b"\xff" * 4)
        self.assertEqual(regions, [(16, 4)])

    def test_spans_block_boundaries(self):
        stock = bytes(9000)
        tuned = bytearray(stock)
        tuned[4090:4106] = b"\x01" * 16      # crosses the 4096 byte scan block
        self.assertEqual(m.diff_regions(bytes(stock), bytes(tuned)), [(4090, 16)])

    def test_identical_files_have_no_regions(self):
        data = bytes(range(256))
        self.assertEqual(m.diff_regions(data, data), [])
        self.assertEqual(m.changed_byte_count(data, data), 0)


class TestXdf(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = write(os.path.join(self.tmp.name, "test.xdf"), SAMPLE_XDF)
        self.xdf = m.XdfDefinition.load(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_header(self):
        self.assertEqual(self.xdf.title, "Test definition")
        self.assertEqual(self.xdf.rom_size, 0x1000)
        self.assertEqual(self.xdf.table_count, 3)

    def test_ignores_axes_without_an_address(self):
        # the two autogen axes carry <EMBEDDEDDATA /> and must not create ranges
        self.assertEqual(len(self.xdf.raw_ranges), 3)

    def test_span_of_a_2d_table(self):
        ranges = {r.title: r for r in self.xdf.resolve(0x1000)}
        boost = ranges["Boost target"]
        self.assertEqual(boost.start, 0x100)
        self.assertEqual(boost.end - boost.start, 2 * 4 * 2)     # rows*cols*2 byte
        timing = ranges["Timing main"]
        self.assertEqual(timing.end - timing.start, 16)          # 16 * 1 byte
        flag = ranges["Enable antilag"]
        self.assertEqual(flag.end - flag.start, 1)

    def test_tables_at(self):
        self.assertEqual(self.xdf.tables_at(0x102, 2, 0x1000), ["Boost target"])
        self.assertEqual(self.xdf.tables_at(0x400, 2, 0x1000), [])

    def test_uncovered_regions(self):
        # 0x100..0x110 is covered, 0x500 is not
        gaps = self.xdf.uncovered([(0x100, 16), (0x500, 8)], 0x1000)
        self.assertEqual(gaps, [(0x500, 8)])

    def test_partially_covered_region_reports_only_the_tail(self):
        gaps = self.xdf.uncovered([(0x100, 32)], 0x1000)
        self.assertEqual(gaps, [(0x110, 16)])

    def test_base_offset_is_resolved_so_ranges_fit(self):
        shifted = SAMPLE_XDF.replace('offset="0"', 'offset="0x8000"')
        path = write(os.path.join(self.tmp.name, "shifted.xdf"), shifted)
        definition = m.XdfDefinition.load(path)
        self.assertEqual(definition.base_offset, 0x8000)
        # raw addresses already fit the ROM, so the zero-shift variant must win
        starts = [r.start for r in definition.resolve(0x1000)]
        self.assertIn(0x100, starts)

    def test_malformed_xml_raises(self):
        path = write(os.path.join(self.tmp.name, "broken.xdf"), "<XDFFORMAT><oops>")
        with self.assertRaises(Exception):
            m.XdfDefinition.load(path)


class TestPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.stock = write(os.path.join(d, "00005C64_original.bin"), bytes(0x1000))
        tuned = bytearray(0x1000)
        tuned[0x100:0x104] = b"\x11\x22\x33\x44"     # inside "Boost target"
        self.tuned = write(os.path.join(d, "customer tune v2.bin"), bytes(tuned))
        self.xdf = write(os.path.join(d, "00005C64.xdf"), SAMPLE_XDF)
        self.key = write(os.path.join(d, "Gen.toolkey"), b"\x00" * 128)
        self.job = m.LockJob(customer="Kunde", vin="DMETEST0000000001",
                             stock_bin=self.stock, tuned_bin=self.tuned,
                             xdf=self.xdf, toolkey=self.key, output_dir=d)

    def tearDown(self):
        self.tmp.cleanup()

    def test_clean_job_passes(self):
        report = m.preflight(self.job)
        self.assertTrue(report.ok, [str(i) for i in report.issues])
        self.assertEqual(report.changed_bytes, 4)
        self.assertEqual(report.regions, [(0x100, 4)])
        self.assertEqual(report.touched_tables, ["Boost target"])
        self.assertEqual(report.uncovered, [])

    def test_identical_files_are_rejected(self):
        self.job.tuned_bin = self.stock
        report = m.preflight(self.job)
        self.assertFalse(report.ok)

    def test_unchanged_copy_is_rejected(self):
        copy = write(os.path.join(self.tmp.name, "copy.bin"), bytes(0x1000))
        self.job.tuned_bin = copy
        report = m.preflight(self.job)
        self.assertFalse(report.ok)
        self.assertTrue(any("identical" in i.text for i in report.errors))

    def test_size_mismatch_is_rejected(self):
        short = write(os.path.join(self.tmp.name, "short.bin"), bytes(0x800))
        self.job.tuned_bin = short
        report = m.preflight(self.job)
        self.assertFalse(report.ok)
        self.assertTrue(any("Size mismatch" in i.text for i in report.errors))

    def test_bad_vin_is_rejected(self):
        self.job.vin = "TOOSHORT"
        self.assertFalse(m.preflight(self.job).ok)

    def test_missing_toolkey_is_rejected(self):
        self.job.toolkey = os.path.join(self.tmp.name, "nope.toolkey")
        report = m.preflight(self.job)
        self.assertFalse(report.ok)
        self.assertTrue(any("toolkey" in i.text.lower() for i in report.errors))

    def test_changes_outside_the_xdf_are_reported_but_not_fatal(self):
        tuned = bytearray(0x1000)
        tuned[0x500:0x508] = b"\xAA" * 8            # no table there
        path = write(os.path.join(self.tmp.name, "outside.bin"), bytes(tuned))
        self.job.tuned_bin = path
        report = m.preflight(self.job)
        self.assertTrue(report.ok)                   # the builder has its own definitions
        self.assertEqual(report.uncovered, [(0x500, 8)])


class TestStaging(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.job = m.LockJob(
            customer="Demo Kunde", vin="DMETEST0000000001",
            stock_bin=write(os.path.join(d, "00005C6414C808_original.bin"), bytes(64)),
            tuned_bin=write(os.path.join(d, "MAP1 E45 MAP2 E30 v4.bin"), bytes(64)),
            xdf=write(os.path.join(d, "00005C6414C808.xdf"), SAMPLE_XDF),
            toolkey=write(os.path.join(d, "Gen.toolkey"), b"\x00" * 128))

    def tearDown(self):
        self.tmp.cleanup()

    def test_reproduces_a_hand_built_folder(self):
        workdir = os.path.join(self.tmp.name, "work")
        manifest = m.stage_job(self.job, workdir)
        self.assertEqual(sorted(os.listdir(workdir)), [
            "00005C6414C808.xdf",
            "00005C6414C808_original.bin",
            "DMETEST0000000001_vin.txt",
            "Gen.toolkey",
            "MAP1 E45 MAP2 E30 v4.bin",
        ])
        self.assertEqual(manifest["stock"], "00005C6414C808_original.bin")
        self.assertEqual(manifest["tuned"], "MAP1 E45 MAP2 E30 v4.bin")

    def test_vin_file_is_empty_and_named_after_the_vin(self):
        workdir = os.path.join(self.tmp.name, "work")
        manifest = m.stage_job(self.job, workdir)
        path = os.path.join(workdir, manifest["vin_file"])
        self.assertEqual(manifest["vin_file"], "DMETEST0000000001_vin.txt")
        self.assertEqual(os.path.getsize(path), 0)

    def test_stock_always_gets_the_original_suffix(self):
        self.assertEqual(m.stock_staged_name("/x/00005C64.bin"), "00005C64_original.bin")
        self.assertEqual(m.stock_staged_name("/x/00005C64_original.bin"),
                         "00005C64_original.bin")
        self.assertEqual(m.stock_staged_name("/x/rom_stock.bin"), "rom_original.bin")

    def test_tuned_never_collides_with_the_stock_glob(self):
        name = m.tuned_staged_name("/x/00005C64_original.bin", "00005C64_original.bin")
        self.assertTrue(name.endswith("_tuned.bin"))
        self.assertNotIn("_original", name)

    def test_builder_is_copied_into_the_folder(self):
        exe = write(os.path.join(self.tmp.name, "TuningMapBuilder-v6.exe"), b"MZ")
        workdir = os.path.join(self.tmp.name, "work2")
        manifest = m.stage_job(self.job, workdir, builder_exe=exe)
        self.assertTrue(os.path.isfile(manifest["builder"]))
        self.assertIn("TuningMapBuilder-v6.exe", os.listdir(workdir))


class TestBuilderOutput(unittest.TestCase):
    def test_classifies_real_messages(self):
        self.assertEqual(m.classify_line("Map correctly written : out.mhd"), "ok")
        self.assertEqual(m.classify_line("Error - several xdfs detected for x"), "error")
        self.assertEqual(m.classify_line("Missing your .toolkey file"), "error")
        self.assertEqual(m.classify_line("NO modifications found"), "error")
        self.assertEqual(m.classify_line("******** CRC error 0x1234"), "error")
        self.assertEqual(m.classify_line("WARNING: overlapping blocks:"), "warn")
        self.assertEqual(m.classify_line("1234 bytes not referenced in the XDFs"), "warn")
        self.assertEqual(m.classify_line("Total bytes changed: 11625"), "info")
        self.assertEqual(m.classify_line(""), "")

    def test_parses_a_successful_run(self):
        result = m.parse_builder_output([
            "opened BIN: tune.bin , size 0x800000",
            "Restrict to VIN : DMETEST0000000001",
            "Total bytes changed: 11625",
            "Map correctly written : tune.mhd",
            "Press a key...",
        ])
        self.assertTrue(result.ok)
        self.assertEqual(result.written, ["tune.mhd"])
        self.assertEqual(result.changed_bytes, 11625)
        self.assertEqual(result.vin_restriction, "DMETEST0000000001")
        self.assertEqual(result.errors, [])

    def test_parses_a_failed_run(self):
        result = m.parse_builder_output([
            "Error - one and only one xdf in the directory for programm ",
            "Press a key...",
        ])
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(result.written, [])

    def test_missing_builder_is_reported_not_raised(self):
        result = m.run_builder("", tempfile.gettempdir())
        self.assertFalse(result.ok)
        self.assertIn("not configured", result.launch_error)


class TestNaming(unittest.TestCase):
    def setUp(self):
        self.job = m.LockJob(customer="Müller GmbH", vin="DMETEST0000000001",
                             stock_bin="/x/00005C64_original.bin",
                             tuned_bin="/x/MAP1 E45 v4.bin")

    def test_source_token_keeps_the_builder_name(self):
        name = m.format_output_name("{source}", self.job, source="MAP1 E45 v4.mhd")
        self.assertEqual(name, "MAP1 E45 v4.mhd")

    def test_customer_template(self):
        name = m.format_output_name("{customer}_{vin}", self.job)
        self.assertTrue(name.startswith("Müller_GmbH_DMETEST0000000001"))
        self.assertTrue(name.endswith(".mhd"))

    def test_unknown_token_falls_back(self):
        name = m.format_output_name("{nope}", self.job)
        self.assertTrue(name.endswith(".mhd"))

    def test_illegal_characters_are_removed(self):
        self.job.customer = 'a/b\\c:d*e?'
        name = m.format_output_name("{customer}", self.job)
        self.assertNotRegex(name, r'[/\\:*?"<>|]')

    def test_unique_path_avoids_overwriting(self):
        with tempfile.TemporaryDirectory() as d:
            first = os.path.join(d, "a.mhd")
            open(first, "wb").close()
            second = m.unique_path(first)
            self.assertNotEqual(first, second)
            self.assertTrue(second.endswith("a_2.mhd"))


class TestBatchCsv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.defaults = m.LockJob(stock_bin="/x/stock.bin", xdf="/x/def.xdf",
                                  toolkey="/x/Gen.toolkey", output_dir="/out")
        for name in ("a.bin", "b.bin"):
            write(os.path.join(self.tmp.name, name), bytes(8))

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_with_header(self):
        path = write(os.path.join(self.tmp.name, "jobs.csv"),
                     "customer,vin,tuned_bin\n"
                     "Kunde A,DMETEST0000000001,a.bin\n"
                     "Kunde B,DMETEST0000000002,b.bin\n")
        jobs, problems = m.read_batch_csv(path, self.defaults)
        self.assertEqual(problems, [])
        self.assertEqual([j.customer for j in jobs], ["Kunde A", "Kunde B"])
        self.assertTrue(jobs[0].tuned_bin.endswith("a.bin"))
        self.assertTrue(os.path.isabs(jobs[0].tuned_bin))
        self.assertEqual(jobs[0].stock_bin, "/x/stock.bin")

    def test_reads_without_header(self):
        path = write(os.path.join(self.tmp.name, "plain.csv"),
                     "Kunde A;DMETEST0000000001;a.bin\n")
        jobs, _ = m.read_batch_csv(path, self.defaults)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].vin, "DMETEST0000000001")

    def test_row_without_a_file_is_reported(self):
        path = write(os.path.join(self.tmp.name, "bad.csv"),
                     "customer,vin,tuned_bin\nKunde,DMETEST0000000001,\n")
        jobs, problems = m.read_batch_csv(path, self.defaults)
        self.assertEqual(jobs, [])
        self.assertEqual(len(problems), 1)


class TestConfig(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            old = os.environ.get("XDG_CONFIG_HOME")
            os.environ["XDG_CONFIG_HOME"] = d
            try:
                if os.name == "nt" or sys.platform == "darwin":
                    self.skipTest("config path is not driven by XDG_CONFIG_HOME here")
                config = m.load_config()
                self.assertEqual(config["name_template"], "{source}")
                config["builder_exe"] = "C:/tools/TuningMapBuilder-v6.exe"
                self.assertTrue(m.save_config(config))
                self.assertEqual(m.load_config()["builder_exe"],
                                 "C:/tools/TuningMapBuilder-v6.exe")
            finally:
                if old is None:
                    os.environ.pop("XDG_CONFIG_HOME", None)
                else:
                    os.environ["XDG_CONFIG_HOME"] = old


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestRunnerEdgeCases(unittest.TestCase):
    """The builder's exit is messy — these are the cases that decide the verdict."""

    def _stub(self, body):
        path = os.path.join(self.dir, "stub.sh")
        write(path, "#!/bin/sh\n" + body)
        os.chmod(path, 0o755)
        return path

    def setUp(self):
        if os.name == "nt":
            self.skipTest("shell stubs are POSIX only")
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_readkey_crash_after_success_is_not_a_failure(self):
        """.NET throws on Console.ReadKey with stdin redirected — after the write."""
        result = m.parse_builder_output([
            "Map correctly written : tune.mhd",
            "Press a key...",
            "Unhandled Exception: System.InvalidOperationException: Cannot read keys when "
            "either application does not have a console or when console input has been "
            "redirected from a file. Try Console.Read.",
            "   at System.Console.ReadKey(Boolean intercept)",
        ])
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.written, ["tune.mhd"])
        self.assertEqual(result.errors, [])

    def test_a_real_error_still_wins(self):
        result = m.parse_builder_output([
            "Error - several .toolkey detected.",
            "Press a key...",
        ])
        self.assertFalse(result.ok)
        self.assertEqual(len(result.errors), 1)

    def test_successful_stub_run(self):
        exe = self._stub('echo "Map correctly written : out.mhd"\n'
                         'echo "Press a key..."\n')
        seen = []
        result = m.run_builder(exe, self.dir, on_line=lambda line, tag: seen.append((line, tag)))
        self.assertTrue(result.ok, result.errors)
        self.assertEqual(result.written, ["out.mhd"])
        self.assertIn(("Press a key...", "dim"), seen)
        self.assertFalse(result.timed_out)

    def test_timeout_is_reported_as_a_timeout(self):
        # exec: the shell is replaced, so killing the process really frees the
        # pipe instead of leaving a grandchild holding it open
        exe = self._stub("exec sleep 30\n")
        result = m.run_builder(exe, self.dir, timeout=1)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.ok)
        self.assertIn("Timeout", result.errors[0])

    def test_unstartable_builder_is_reported(self):
        result = m.run_builder(os.path.join(self.dir, "does-not-exist.exe"), self.dir)
        self.assertFalse(result.ok)
        self.assertTrue(result.launch_error)


class TestAutomaticResolution(unittest.TestCase):
    """One picked file must be enough — that is the whole point of the tool."""

    ROM_ID = "00005C6414C808"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.car = os.path.join(self.tmp.name, "M4 Kunde")
        os.makedirs(self.car)
        stock = bytearray(0x2000)
        stock[0x100:0x107] = bytes.fromhex(self.ROM_ID)   # packed, as in a real ROM
        self.stock = write(os.path.join(self.car, f"{self.ROM_ID}_original.bin"), bytes(stock))
        tuned = bytearray(stock)
        tuned[0x800:0x810] = b"\xAA" * 16
        self.tuned = write(os.path.join(self.car, "Kunde tune v2.bin"), bytes(tuned))
        self.xdf = write(os.path.join(self.car, f"{self.ROM_ID}.xdf"), SAMPLE_XDF)
        self.key = write(os.path.join(self.car, "Gen.toolkey"), b"\x00" * 128)

    def tearDown(self):
        self.tmp.cleanup()

    def test_everything_comes_from_the_tuned_file(self):
        found = m.resolve_inputs(self.tuned)
        self.assertEqual(found.stock, self.stock)
        self.assertEqual(found.xdf, self.xdf)
        self.assertEqual(found.toolkey, self.key)
        self.assertEqual(found.rom_id, self.ROM_ID)
        self.assertTrue(found.complete)
        self.assertEqual(found.source("stock"), "matched by ROM id")

    def test_vin_is_reused_from_a_previous_run(self):
        write(os.path.join(self.car, "DMETEST0000000001_vin.txt"), "")
        self.assertEqual(m.resolve_inputs(self.tuned).vin, "DMETEST0000000001")

    def test_invalid_vin_file_is_ignored(self):
        write(os.path.join(self.car, "SHORT_vin.txt"), "")
        self.assertEqual(m.resolve_inputs(self.tuned).vin, "")

    def test_companions_are_found_in_a_library_folder(self):
        library = os.path.join(self.tmp.name, "library", "S55")
        os.makedirs(library)
        os.replace(self.stock, os.path.join(library, os.path.basename(self.stock)))
        os.replace(self.xdf, os.path.join(library, os.path.basename(self.xdf)))
        found = m.resolve_inputs(self.tuned, library_dir=os.path.join(self.tmp.name, "library"))
        self.assertTrue(found.stock.startswith(library))
        self.assertTrue(found.xdf.startswith(library))
        self.assertTrue(found.complete)

    def test_a_foreign_rom_is_not_picked_up(self):
        """A library entry for another car must not be matched."""
        library = os.path.join(self.tmp.name, "library")
        os.makedirs(library)
        write(os.path.join(library, "00001A841D1401_original.bin"), bytes(0x2000))
        write(os.path.join(library, "00001A841D1401.xdf"), SAMPLE_XDF)
        os.remove(self.stock)
        os.remove(self.xdf)
        found = m.resolve_inputs(self.tuned, library_dir=library)
        self.assertEqual(found.stock, "")
        self.assertEqual(found.xdf, "")
        self.assertFalse(found.complete)

    def test_unnamed_files_still_work_in_the_same_folder(self):
        """Files without a ROM id in the name: the only obvious one wins."""
        plain_stock = os.path.join(self.car, "stock_original.bin")
        plain_xdf = os.path.join(self.car, "definition.xdf")
        os.replace(self.stock, plain_stock)
        os.replace(self.xdf, plain_xdf)
        found = m.resolve_inputs(self.tuned)
        self.assertEqual(found.stock, plain_stock)
        self.assertEqual(found.xdf, plain_xdf)
        self.assertEqual(found.source("stock"), "only stock ROM in the folder")

    def test_the_tuned_file_is_never_its_own_stock(self):
        tuned = write(os.path.join(self.car, "something_original.bin"), bytes(0x2000))
        found = m.resolve_inputs(tuned)
        self.assertNotEqual(found.stock, tuned)

    def test_configured_key_wins_over_a_stray_one(self):
        other = write(os.path.join(self.tmp.name, "Mein.toolkey"), b"\x01" * 128)
        found = m.resolve_inputs(self.tuned, toolkey=other)
        self.assertEqual(found.toolkey, other)
        self.assertEqual(found.source("toolkey"), "from settings")

    def test_id_matching_is_exact(self):
        self.assertEqual(m.ids_in_name("/x/00005C6414C808_original.bin"), ["00005C6414C808"])
        self.assertEqual(m.ids_in_name("/x/tune v2.bin"), [])
        data = bytes(16) + bytes.fromhex(self.ROM_ID) + bytes(16)
        self.assertTrue(m.id_in_image(data, self.ROM_ID))
        self.assertFalse(m.id_in_image(data, "00001A841D1401"))
        self.assertFalse(m.id_in_image(data, "nothex"))

    def test_missing_file_is_handled(self):
        found = m.resolve_inputs(os.path.join(self.car, "nope.bin"))
        self.assertFalse(found.complete)
        self.assertTrue(found.notes)
