"""Synthetic source acceptance cases only; never download a real dataset."""

import csv
import gzip
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from ingest.ingest import IngestError, register_file, sha256, stream_download
from ingest import ingest_criteo_source as c


class CriteoSourceTests(unittest.TestCase):
    def setUp(self):
        root = c.BASE / "synthetic"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-", dir=root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "synthetic.csv"
        self.rows = [["1.25"] * 12 + ["1", "0", "1", "0"],
                     ["-2.5"] * 12 + ["0", "1", "0", "1"]]

    def write(self, rows=None, header=None):
        with self.path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(c.HEADER if header is None else header)
            writer.writerows(self.rows if rows is None else rows)

    def profile(self):
        return c.profile_csv(self.path, progress_every=0)

    def independent(self):
        return c.independent_csv_check(self.path, progress_every=0)

    def receipt(self, path):
        return {"status": "complete", "bytes": path.stat().st_size,
                "sha256": sha256(path), "acquired_at_utc": "synthetic"}

    def test_sixteen_columns_header_excluded_literal_counts(self):
        self.write()
        a, b = self.profile(), self.independent()
        for result in (a, b):
            self.assertEqual(result["header"], c.HEADER)
            self.assertEqual(result["record_count"], 2)
            self.assertEqual(result["field_width_counts"], {"16": 2})
            for counts in result["binary_counts"].values():
                self.assertEqual(counts, {"0": 1, "1": 1, "invalid": 0})
        self.assertEqual(a["rates"], dict.fromkeys(c.LABELS, "0.5"))
        c.require_valid(a, b)

    def test_short_and_long_records_fail_both_parsers(self):
        for row in [self.rows[0][:-1], self.rows[0] + ["extra"]]:
            with self.subTest(width=len(row)):
                self.write([row])
                with self.assertRaises(c.ProfileError) as ctx:
                    self.profile()
                self.assertEqual(ctx.exception.progress["status"], "failed_partial_scan")
                self.assertEqual(ctx.exception.progress["csv_structure_errors"], 1)
                with self.assertRaises(IngestError):
                    self.independent()

    def test_wrong_header_rejected_independently(self):
        self.write(header=["wrong"] + c.HEADER[1:])
        for fn in (self.profile, self.independent):
            with self.assertRaises(IngestError):
                fn()

    def test_binary_invalid_empty_and_whitespace_literal_expected(self):
        self.write([self.rows[0][:12] + ["2", "", "  ", "1.0"]])
        a, b = self.profile(), self.independent()
        for result in (a, b):
            for counts in result["binary_counts"].values():
                self.assertEqual(counts, {"0": 0, "1": 0, "invalid": 1})
        self.assertEqual(a["empty_counts"]["conversion"], 1)
        self.assertEqual(a["whitespace_only_counts"]["visit"], 1)
        with self.assertRaisesRegex(IngestError, "Binary"):
            c.require_valid(a, b)

    def test_feature_nan_inf_invalid_and_empty(self):
        row = ["NaN", "+Inf", "-Infinity", "bad", "", " "] + ["2"] * 6 + ["0"] * 4
        self.write([row])
        result = self.profile()
        self.assertEqual(list(result["feature_nonfinite_or_invalid_counts"].values()), [1]*6 + [0]*6)
        self.assertEqual(result["empty_counts"]["f4"], 1)
        self.assertEqual(result["whitespace_only_counts"]["f5"], 1)
        with self.assertRaises(IngestError):
            c.require_valid(result, self.independent())

    def test_quotes_commas_multiline_and_empty_are_csv_fields(self):
        row = ['synthetic, "quoted"', "synthetic\nmultiline", ""] + ["2"]*9 + ["0"]*4
        self.write([row])
        a, b = self.profile(), self.independent()
        self.assertEqual(a["record_count"], 1)
        self.assertEqual(b["record_count"], 1)
        self.assertEqual(a["field_width_counts"], {"16": 1})
        self.assertEqual(a["empty_counts"]["f2"], 1)
        self.assertEqual(a["feature_nonfinite_or_invalid_counts"]["f0"], 1)

    def test_unterminated_quote_is_not_complete(self):
        self.write([])
        with self.path.open("a") as f:
            f.write('"unterminated\n')
        for fn in (self.profile, self.independent):
            with self.assertRaises(IngestError):
                fn()

    def test_empty_file_or_header_only_cannot_pass(self):
        self.path.write_text("")
        with self.assertRaises(IngestError):
            self.profile()
        self.write([])
        with self.assertRaises(IngestError):
            c.require_valid(self.profile(), self.independent())

    def test_gzip_full_crc_and_no_overwrite(self):
        self.write()
        archive = self.root / "synthetic.gz"
        archive.write_bytes(gzip.compress(self.path.read_bytes(), mtime=0))
        dest = self.root / "extracted.csv"
        result = c.extract_archive(archive, dest)
        self.assertEqual(result["sha256"], sha256(self.path))
        self.assertEqual(result["bytes"], self.path.stat().st_size)
        self.assertEqual(result["gzip_crc"], "pass")
        with self.assertRaises(IngestError):
            c.extract_archive(archive, dest)

    def test_crc_damage_and_truncation_leave_only_partial(self):
        self.write()
        payload = gzip.compress(self.path.read_bytes(), mtime=0)
        damaged = bytearray(payload); damaged[-8] ^= 1
        for i, content in enumerate([bytes(damaged), payload[:-4]]):
            archive = self.root / f"bad{i}.gz"; archive.write_bytes(content)
            dest = self.root / f"bad{i}.csv"
            with self.assertRaises((gzip.BadGzipFile, EOFError)):
                c.extract_archive(archive, dest)
            self.assertFalse(dest.exists())
            self.assertTrue(dest.with_name(dest.name + ".part").exists())

    def test_decompression_budget_prevents_promotion(self):
        archive = self.root / "synthetic.gz"; archive.write_bytes(gzip.compress(b"123456"))
        dest = self.root / "bounded.csv"
        with self.assertRaisesRegex(IngestError, "budget"):
            c.extract_archive(archive, dest, max_bytes=5)
        self.assertFalse(dest.exists())

    def test_same_content_and_renamed_content_register_once(self):
        self.write(); records = []
        meta = {"source_id": "synthetic_criteo", "kind": "raw"}
        self.assertTrue(register_file(records, self.path, self.receipt(self.path), meta)[1])
        self.assertFalse(register_file(records, self.path, self.receipt(self.path), meta)[1])
        renamed = self.root / "renamed.csv"; shutil.copyfile(self.path, renamed)
        self.assertFalse(register_file(records, renamed, self.receipt(renamed), meta)[1])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["observed_filenames"], ["synthetic.csv", "renamed.csv"])

    def test_same_name_different_content_rejected(self):
        self.write(); records = []
        register_file(records, self.path, self.receipt(self.path), {})
        self.write(self.rows[:1])
        with self.assertRaisesRegex(IngestError, "Same filename"):
            register_file(records, self.path, self.receipt(self.path), {})
        self.assertEqual(len(records), 1)

    def test_failed_download_cannot_register(self):
        dest = self.root / "download.gz"
        with self.assertRaises(IngestError):
            stream_download(io.BytesIO(b"tiny"), dest, 10)
        receipt = json.loads(dest.with_name(dest.name + ".download.json").read_text())
        self.assertEqual(receipt["status"], "failed")
        with self.assertRaises(IngestError):
            register_file([], dest.with_name(dest.name + ".part"), receipt, {})

    def test_independent_mismatch_rejected(self):
        self.write(); primary = self.profile(); second = self.independent()
        second["record_count"] = 999
        with self.assertRaisesRegex(IngestError, "Independent mismatch"):
            c.require_valid(primary, second)

    def test_reuse_returns_before_network_or_new_output(self):
        with patch.object(c, "registered_or_none", return_value={"status": "registered"}), \
                patch.object(c.urllib.request, "build_opener") as network:
            self.assertEqual(c.run(self.root), {"status": "registered"})
            network.assert_not_called()

    def test_failure_receipt_no_registration(self):
        with patch.object(c, "check_budget"), \
                patch.object(c.urllib.request, "build_opener", side_effect=RuntimeError("synthetic")):
            with self.assertRaises(IngestError):
                c.run(self.root)
        failures = list(self.root.glob("staging/*/failed.json"))
        self.assertEqual(len(failures), 1)
        self.assertEqual(json.loads(failures[0].read_text())["status"], "failed")
        self.assertFalse((self.root / "registry.json").exists())

    def test_disk_budget_rejected_before_download(self):
        with patch.object(c.shutil, "disk_usage", return_value=shutil._ntuple_diskusage(100, 50, 50)):
            with self.assertRaisesRegex(IngestError, "disk budget"):
                c.check_budget(self.root)

    def test_independent_quoted_values_exact_literal_expected(self):
        text = 'a,"b,b","c""c","two\r\nlines",\r\nlast,record,no,newline,'
        result = list(c.independent_records(io.StringIO(text, newline="")))
        self.assertEqual(result, [["a", "b,b", 'c"c', "two\r\nlines", ""],
                                  ["last", "record", "no", "newline", ""]])

    def test_independent_rejects_quotes_inside_unquoted_fields(self):
        for text in ['ab"c"d,0\n', '"a"x,0\n', '"a\n', 'abc"\n']:
            with self.subTest(text=text), self.assertRaises(IngestError):
                list(c.independent_records(io.StringIO(text)))

    def test_partial_registration_rejected(self):
        (self.root / "registry.json").write_text(json.dumps({
            "status": "registered", "source_id": c.SOURCE_ID,
            "gzip_crc": "pass", "independent_status": "failed"}))
        with self.assertRaisesRegex(IngestError, "successful validation"):
            c.registered_or_none(self.root)

    def test_published_raw_is_read_only_and_not_overwritten(self):
        self.write(); digest = sha256(self.path)
        raw = self.root / "raw"; raw.mkdir()
        destination = c.publish_raw(self.path, raw, digest)
        self.assertEqual(destination.stat().st_mode & 0o777, 0o444)
        self.assertFalse(self.path.exists())
        self.write(self.rows[:1])
        with self.assertRaises(IngestError):
            register_file([{"sha256": digest, "observed_filenames": [self.path.name]}],
                          self.path, self.receipt(self.path), {})
        self.assertEqual(sha256(destination), digest)
        destination.chmod(0o644)


if __name__ == "__main__":
    unittest.main()
