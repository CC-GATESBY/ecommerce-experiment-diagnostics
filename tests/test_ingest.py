"""Synthetic-only ingestion cases. No real data or network access."""

import csv
import gzip
import io
import json
from pathlib import Path
import tempfile
import unittest

from ingest.ingest import (IngestError, ROOT, GIB, budget, csv_header, extract_gzip,
                           load_config, register_file, sample_csv, sha256,
                           stream_download)


class SyntheticIngestTests(unittest.TestCase):
    def setUp(self):
        base = ROOT / ".local/t04/synthetic-tests"
        base.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-", dir=base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "synthetic.csv"
        self.header = ["event_time", "brand", "price", "user_id", "user_session"]
        self.rows = [
            ["2019-10-01 00:00:00 UTC", 'synthetic, "quoted"', "0001.20", "0007", ""],
            ["2019-10-01 00:00:00 UTC", 'synthetic, "quoted"', "0001.20", "0007", ""],
            ["invalid synthetic time", "synthetic\nmultiline", "", "0099", "s"],
            ["2019-10-01 01:00:00 UTC", "", "0.00", "0010", "s"],
        ]
        with self.source.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(self.header)
            writer.writerows(self.rows)
        self.receipt = {"status": "complete", "bytes": self.source.stat().st_size,
                        "sha256": sha256(self.source), "acquired_at_utc": "synthetic"}
        self.metadata = {"source_id": "synthetic", "format": "csv", "header": self.header}

    def test_same_file_registration_is_idempotent(self):
        records = []
        self.assertTrue(register_file(records, self.source, self.receipt, self.metadata)[1])
        self.assertFalse(register_file(records, self.source, self.receipt, self.metadata)[1])
        self.assertEqual(len(records), 1)

    def test_renamed_identical_content_is_one_record(self):
        records = []
        register_file(records, self.source, self.receipt, self.metadata)
        renamed = self.root / "synthetic-renamed.csv"
        renamed.write_bytes(self.source.read_bytes())
        record, added = register_file(records, renamed, self.receipt, self.metadata)
        self.assertFalse(added)
        self.assertEqual(len(records), 1)
        self.assertEqual(record["observed_filenames"], [self.source.name, renamed.name])

    def test_same_filename_different_content_rejected(self):
        records = []
        register_file(records, self.source, self.receipt, self.metadata)
        self.source.write_bytes(self.source.read_bytes() + b"synthetic changed\n")
        receipt = dict(self.receipt, bytes=self.source.stat().st_size, sha256=sha256(self.source))
        with self.assertRaisesRegex(IngestError, "Same filename"):
            register_file(records, self.source, receipt, self.metadata)
        self.assertEqual(len(records), 1)

    def test_header_excluded_limit_applies_to_records(self):
        result = sample_csv(self.source, sha256(self.source), self.root / "sample", 2)
        self.assertEqual(result["record_count"], 2)
        with (self.root / "sample/engineering_sample.csv").open(newline="") as f:
            self.assertEqual(list(csv.reader(f)), [self.header] + self.rows[:2])

    def test_short_input_quotes_commas_empty_values_duplicates_preserved(self):
        result = sample_csv(self.source, sha256(self.source), self.root / "sample")
        self.assertEqual(result["record_count"], 4)
        with (self.root / "sample/engineering_sample.csv").open(newline="") as f:
            self.assertEqual(list(csv.reader(f)), [self.header] + self.rows)
        self.assertEqual(result["time_parse_failures"], 1)
        self.assertEqual(result["sample_time_range_utc"], {
            "min": "2019-10-01T00:00:00+00:00", "max": "2019-10-01T01:00:00+00:00"})

    def test_sampling_reproducible_and_never_overwrites(self):
        one = sample_csv(self.source, sha256(self.source), self.root / "sample1")
        two = sample_csv(self.source, sha256(self.source), self.root / "sample2")
        self.assertEqual(one["sha256"], two["sha256"])
        self.assertEqual(one["scope_id"], two["scope_id"])
        with self.assertRaises(FileExistsError):
            sample_csv(self.source, sha256(self.source), self.root / "sample1")

    def test_parent_change_blocks_sampling(self):
        with self.assertRaisesRegex(IngestError, "Parent content"):
            sample_csv(self.source, "0" * 64, self.root / "sample")

    def test_malformed_width_is_incomplete(self):
        self.source.write_text("event_time,brand\nsynthetic\n")
        with self.assertRaises(IngestError):
            sample_csv(self.source, sha256(self.source), self.root / "sample")
        self.assertFalse((self.root / "sample/receipt.json").exists())
        self.assertFalse((self.root / "sample/engineering_sample.csv").exists())

    def test_invalid_limit_rejected(self):
        for limit in [0, -1, 100001, True]:
            with self.subTest(limit=limit), self.assertRaises(IngestError):
                sample_csv(self.source, sha256(self.source), self.root / "sample", limit)

    def test_incomplete_download_never_registers(self):
        dest = self.root / "synthetic.download.csv"
        with self.assertRaisesRegex(IngestError, "Incomplete"):
            stream_download(io.BytesIO(b"synthetic"), dest, 100)
        failed = json.loads(dest.with_name(dest.name + ".download.json").read_text())
        self.assertEqual(failed["status"], "failed")
        self.assertFalse(dest.exists())
        records = []
        with self.assertRaises(IngestError):
            register_file(records, dest.with_name(dest.name + ".part"), failed, self.metadata)
        self.assertEqual(records, [])

    def test_network_failure_keeps_partial_without_complete_receipt(self):
        class BrokenResponse:
            def read(self, size):
                raise ConnectionError("synthetic network failure")
        dest = self.root / "synthetic-failed.csv"
        with self.assertRaises(ConnectionError):
            stream_download(BrokenResponse(), dest, 100)
        self.assertFalse(dest.exists())
        self.assertEqual(json.loads(dest.with_name(dest.name + ".download.json").read_text())["status"], "failed")

    def test_oversize_download_rejected(self):
        dest = self.root / "synthetic-too-large.csv"
        with self.assertRaisesRegex(IngestError, "exceeds"):
            stream_download(io.BytesIO(b"synthetic"), dest, 3)
        self.assertFalse(dest.exists())

    def test_completed_download_receipt_and_tamper_check(self):
        dest = self.root / "synthetic-ok.csv"
        receipt = stream_download(io.BytesIO(self.source.read_bytes()), dest, self.source.stat().st_size)
        register_file([], dest, receipt, self.metadata)
        dest.write_bytes(b"tampered synthetic")
        with self.assertRaises(IngestError):
            register_file([], dest, receipt, self.metadata)

    def test_download_never_overwrites(self):
        with self.assertRaises(IngestError):
            stream_download(io.BytesIO(b"synthetic"), self.source, 9)
        self.assertEqual(sha256(self.source), self.receipt["sha256"])

    def test_safe_gzip_extraction_and_existing_file(self):
        archive = self.root / "synthetic.csv.gz"
        payload = self.source.read_bytes()
        archive.write_bytes(gzip.compress(payload))
        dest = self.root / "2019-Oct.csv"
        receipt = extract_gzip(archive, dest, len(payload), self.root)
        self.assertEqual(receipt["gzip_crc"], "pass")
        self.assertEqual(dest.read_bytes(), payload)
        with self.assertRaises(IngestError):
            extract_gzip(archive, dest, len(payload), self.root)

    def test_gzip_escape_and_corruption_rejected(self):
        archive = self.root / "synthetic.csv.gz"
        archive.write_bytes(gzip.compress(b"synthetic")[:-6])
        with self.assertRaises(IngestError):
            extract_gzip(archive, self.root / "../2019-Oct.csv", 9, self.root)
        with self.assertRaises((EOFError, OSError)):
            extract_gzip(archive, self.root / "2019-Oct.csv", 9, self.root)
        self.assertFalse((self.root / "2019-Oct.csv").exists())

    def test_gzip_size_cap(self):
        archive = self.root / "synthetic.csv.gz"
        archive.write_bytes(gzip.compress(b"synthetic"))
        with self.assertRaises(IngestError):
            extract_gzip(archive, self.root / "2019-Oct.csv", 2, self.root)
        self.assertFalse((self.root / "2019-Oct.csv").exists())

    def test_invalid_and_duplicate_header(self):
        for content in ["", "x,x\n", "event_time,\n"]:
            self.source.write_text(content)
            with self.assertRaises(IngestError):
                csv_header(self.source)

    def test_budget_limits(self):
        cfg = {"archive_bytes": 1741928540, "csv_expected_bytes": 5668612855}
        self.assertGreater(budget(cfg, 200 * GIB)["projected_free_bytes"], 150 * GIB)
        for bad, free in [(cfg, 151 * GIB), (dict(cfg, archive_bytes=9 * GIB), 500 * GIB),
                          (dict(cfg, csv_expected_bytes=25 * GIB), 500 * GIB)]:
            with self.assertRaises(IngestError):
                budget(bad, free)

    def test_config_missing_template_escape_unknown_fields(self):
        with self.assertRaises(IngestError):
            load_config(self.root / "missing.json")
        template = ROOT / "config/ingest.example.json"
        with self.assertRaises(IngestError):
            load_config(template)
        cfg = json.loads(template.read_text())
        for key in ["staging_root", "raw_root", "sample_root"]:
            p = self.root / key
            p.mkdir()
            cfg[key] = str(p)
        local = self.root / "synthetic-config.json"
        local.write_text(json.dumps(cfg))
        self.assertEqual(load_config(local)["max_records"], 100000)
        for bad in [dict(cfg, raw_root="/tmp"), dict(cfg, raw_root=cfg["staging_root"]),
                    dict(cfg, extra="synthetic"), dict(cfg, max_records=True),
                    {k: v for k, v in cfg.items() if k != "raw_root"}]:
            local.write_text(json.dumps(bad))
            with self.assertRaises(IngestError):
                load_config(local)


if __name__ == "__main__":
    unittest.main()
