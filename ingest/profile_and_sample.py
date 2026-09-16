"""Stream the registered October CSV and retain a fixed user-hash cohort."""

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import sys
import time

from ingest.ingest import (GIB, HEADER, IngestError, ROOT, SOURCE_ID,
                           load_config as load_ingest_config, sha256,
                           utc_now, write_new_json)

ALGORITHM = "rees46-user-sample-v1"
SEED = "20260916"
PREFIX = ALGORITHM + "|" + SEED + "|"
THRESHOLD = (5 * 2 ** 64) // 100
PARENT_SHA = "fedd938409b5f836ec89b39c861b13dad99fc7cd9beb1fddd97a2d50488b5b80"
START = "2019-10-01T00:00:00+00:00"
END = "2019-11-01T00:00:00+00:00"
EXPECTED_DATES = [(date(2019, 10, 1) + timedelta(days=i)).isoformat() for i in range(31)]
TIME_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC\Z")
MAX_NEW_BYTES = 10 * GIB
MIN_FREE_BYTES = 150 * GIB
DB_RESERVE = 256 * 1024 ** 2
METADATA_RESERVE = 16 * 1024 ** 2
SERIALIZATION = "csv-v1;UTF-8;LF;QUOTE_MINIMAL;header-once;original-field-strings;source-order"


def selected(user_id):
    if user_id == "" or user_id.isspace():
        return False
    digest = hashlib.sha256((PREFIX + user_id).encode("utf-8")).hexdigest()
    return int(digest[:16], 16) < THRESHOLD


def parse_time(value):
    if value == "" or value.isspace():
        return "missing", None
    if not TIME_PATTERN.fullmatch(value):
        return "invalid", None
    try:
        datetime.fromisoformat(value[:19])  # Validate the calendar and clock.
    except ValueError:
        return "invalid", None
    return "valid", value[:10] + "T" + value[11:19] + "+00:00"


def add_fields(digest, row):
    # Length framing makes field boundaries and record ordering unambiguous.
    digest.update(len(row).to_bytes(4, "big"))
    for value in row:
        raw = value.encode("utf-8")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)


class Profile:
    def __init__(self):
        self.records = 0
        self.width_errors = 0
        self.time_missing = 0
        self.time_invalid = 0
        self.outside_month = 0
        self.earliest = None
        self.latest = None
        self.days = Counter()
        self.hours = Counter()
        self.events = Counter()
        self.empty_fields = Counter({key: 0 for key in HEADER})
        self.user_empty = 0
        self.user_whitespace = 0
        self.user_non_digit = 0
        self.user_leading_zero = 0

    def observe(self, row, parsed=None):
        if len(row) != len(HEADER):
            self.width_errors += 1
            raise IngestError("CSV width anomaly; full-file profiling cannot continue safely")
        self.records += 1
        for key, value in zip(HEADER, row):
            if value == "":
                self.empty_fields[key] += 1
        self.events[row[1]] += 1
        user = row[7]
        if user == "":
            self.user_empty += 1
        elif user.isspace():
            self.user_whitespace += 1
        else:
            if not (user.isascii() and user.isdecimal()):
                self.user_non_digit += 1
            if len(user) > 1 and user.startswith("0"):
                self.user_leading_zero += 1
        parsed = parse_time(row[0]) if parsed is None else parsed
        status, timestamp = parsed
        if status == "missing":
            self.time_missing += 1
        elif status == "invalid":
            self.time_invalid += 1
        else:
            self.earliest = timestamp if self.earliest is None else min(self.earliest, timestamp)
            self.latest = timestamp if self.latest is None else max(self.latest, timestamp)
            self.days[timestamp[:10]] += 1
            self.hours[timestamp[:13] + ":00:00+00:00"] += 1
            self.outside_month += not START <= timestamp < END
        return parsed

    def summary(self):
        return {
            "record_count": self.records, "header": HEADER,
            "field_count_anomaly_records": self.width_errors,
            "time_range_utc": {"min": self.earliest, "max": self.latest},
            "time_missing_records": self.time_missing,
            "time_parse_failure_records": self.time_invalid,
            "outside_expected_month_records": self.outside_month,
            "daily_records": dict(sorted(self.days.items())),
            "hourly_records": dict(sorted(self.hours.items())),
            "event_type_counts": dict(sorted(self.events.items())),
            "empty_field_records": dict(self.empty_fields),
            "user_id_missing_or_unusable_records": self.user_empty + self.user_whitespace,
            "user_id_empty_records": self.user_empty,
            "user_id_whitespace_only_records": self.user_whitespace,
            "user_id_non_ascii_digit_string_records": self.user_non_digit,
            "user_id_leading_zero_records": self.user_leading_zero,
            "expected_dates_without_records": [day for day in EXPECTED_DATES if not self.days[day]],
        }


class HashingReader(io.RawIOBase):
    def __init__(self, file):
        self.file = file
        self.digest = hashlib.sha256()
        self.bytes = 0

    def readable(self):
        return True

    def readinto(self, buffer):
        count = self.file.readinto(buffer)
        if count:
            self.digest.update(memoryview(buffer)[:count])
            self.bytes += count
        return count


class OutputBudget:
    def __init__(self, directory, limit=MAX_NEW_BYTES, minimum_free=MIN_FREE_BYTES):
        self.directory = Path(directory)
        self.limit = limit
        self.minimum_free = minimum_free
        self.max_csv = limit - DB_RESERVE - METADATA_RESERVE
        if self.max_csv <= 0:
            raise IngestError("Insufficient output budget after verification reserves")
        self.check()
        if shutil.disk_usage(directory).free - limit < minimum_free:
            raise IngestError("Projected free disk below the required minimum")

    def check(self):
        used = sum(p.stat().st_size for p in self.directory.iterdir() if p.is_file())
        if used > self.limit - METADATA_RESERVE:
            raise IngestError("Run output budget exhausted")
        if shutil.disk_usage(self.directory).free < self.minimum_free:
            raise IngestError("Available disk below the required minimum")


class CSVOutput:
    def __init__(self, file, budget):
        self.file = file
        self.budget = budget
        self.bytes = 0
        self.digest = hashlib.sha256()

    def write(self, text):
        raw = text.encode("utf-8")
        if self.bytes + len(raw) > self.budget.max_csv:
            raise IngestError("Candidate would exceed the output budget; no truncation allowed")
        self.file.write(raw)
        self.digest.update(raw)
        self.bytes += len(raw)
        return len(text)


def scan(source, output, source_profile, candidate_profile, budget, progress_every, start):
    field_digest = hashlib.sha256()
    with Path(source).open("rb") as binary, Path(output).open("xb") as target:
        hashing = HashingReader(binary)
        with io.TextIOWrapper(io.BufferedReader(hashing), encoding="utf-8", newline="") as text:
            reader = csv.reader(text, strict=True)
            if next(reader, None) != HEADER:
                raise IngestError("Source header does not match the registered nine fields")
            sink = CSVOutput(target, budget)
            writer = csv.writer(sink, lineterminator="\n")
            writer.writerow(HEADER)
            add_fields(field_digest, HEADER)
            for row in reader:
                parsed = source_profile.observe(row)
                if selected(row[7]):
                    writer.writerow(row)
                    candidate_profile.observe(row, parsed)
                    add_fields(field_digest, row)
                if source_profile.records % progress_every == 0:
                    target.flush()
                    budget.check()
                    print(json.dumps({"phase": "source_scan", "processed_records": source_profile.records,
                                      "selected_records": candidate_profile.records,
                                      "elapsed_seconds": round(time.monotonic() - start, 2)}), flush=True)
            target.flush()
            os.fsync(target.fileno())
            budget.check()
            return {"source_sha256": hashing.digest.hexdigest(), "source_bytes": hashing.bytes,
                    "sample_sha256": sink.digest.hexdigest(), "sample_bytes": sink.bytes,
                    "field_sequence_sha256": field_digest.hexdigest()}


def validate_candidate(path, extraction, expected_profile, database, budget, progress_every, start):
    profile = Profile()
    field_digest = hashlib.sha256()
    db = sqlite3.connect(database)
    try:
        # Scratch-only database: a failed run is never resumed or registered.
        db.execute("PRAGMA journal_mode=OFF")
        db.execute("PRAGMA page_size=4096")
        db.execute("PRAGMA temp_store=FILE")
        db.execute("PRAGMA cache_size=-4096")
        db.execute("PRAGMA max_page_count=65536")  # 256 MiB at the default 4 KiB page size.
        db.execute("CREATE TABLE users (user_id TEXT COLLATE BINARY PRIMARY KEY) WITHOUT ROWID")
        batch = []
        with Path(path).open("rb") as binary:
            hashing = HashingReader(binary)
            with io.TextIOWrapper(io.BufferedReader(hashing), encoding="utf-8", newline="") as text:
                reader = csv.reader(text, strict=True)
                if next(reader, None) != HEADER:
                    raise IngestError("Candidate header changed")
                add_fields(field_digest, HEADER)
                for row in reader:
                    profile.observe(row)
                    user = row[7]
                    # Independently express the same 64-bit hash threshold.
                    value = int.from_bytes(hashlib.sha256((PREFIX + user).encode("utf-8")).digest()[:8], "big")
                    if user == "" or user.isspace() or value >= THRESHOLD:
                        raise IngestError("Candidate contains an unselected user")
                    add_fields(field_digest, row)
                    batch.append((user,))
                    if len(batch) == 4096:
                        db.executemany("INSERT OR IGNORE INTO users VALUES (?)", batch)
                        db.commit()
                        batch.clear()
                        budget.check()
                    if profile.records % progress_every == 0:
                        print(json.dumps({"phase": "sample_reread", "processed_records": profile.records,
                                          "elapsed_seconds": round(time.monotonic() - start, 2)}), flush=True)
                db.executemany("INSERT OR IGNORE INTO users VALUES (?)", batch)
                db.commit()
                actual = profile.summary()
                if actual != expected_profile:
                    raise IngestError("Candidate profile differs from extraction counters")
                if hashing.digest.hexdigest() != extraction["sample_sha256"] or hashing.bytes != extraction["sample_bytes"]:
                    raise IngestError("Candidate serialization or bytes changed")
                if field_digest.hexdigest() != extraction["field_sequence_sha256"]:
                    raise IngestError("Candidate field values or record order changed")
                budget.check()
                return {"profile": actual, "distinct_user_count": db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                        "all_user_hash_conditions": "pass", "field_values_and_order": "pass",
                        "serialization_and_sha256": "pass", "profile_matches_extraction": "pass",
                        "distinct_count_method": "SQLite BINARY primary key; bounded 4096-row batches"}
    finally:
        db.close()


def execute(source, expected_sha, staging, destination, progress_every=1000000,
            max_new_bytes=MAX_NEW_BYTES, minimum_free_bytes=MIN_FREE_BYTES):
    """Core entry point also used with independent synthetic fixtures in tests."""
    source, staging, destination = Path(source), Path(staging), Path(destination)
    if destination.exists() or destination.is_symlink():
        raise IngestError("Candidate destination already exists")
    staging.mkdir(exist_ok=False)
    start, started_at = time.monotonic(), utc_now()
    source_profile, candidate_profile = Profile(), Profile()
    phase = "preflight"
    try:
        budget = OutputBudget(staging, max_new_bytes, minimum_free_bytes)
        free_before = shutil.disk_usage(staging).free
        original_stat = source.stat()
        if sha256(source) != expected_sha:
            raise IngestError("Registered source SHA256 mismatch")
        phase = "source_scan"
        scan_start = time.monotonic()
        partial = staging / "user_sample_candidate.csv.part"
        extraction = scan(source, partial, source_profile, candidate_profile, budget, progress_every, start)
        scan_seconds = time.monotonic() - scan_start
        if extraction["source_sha256"] != expected_sha or extraction["source_bytes"] != original_stat.st_size:
            raise IngestError("Complete source scan hash/size does not match its registered input")
        phase = "candidate_validation"
        validation_start = time.monotonic()
        validation = validate_candidate(partial, extraction, candidate_profile.summary(),
                                        staging / "selected_users.sqlite3", budget, progress_every, start)
        validation_seconds = time.monotonic() - validation_start
        after_stat = source.stat()
        if (original_stat.st_size, original_stat.st_mtime_ns) != (after_stat.st_size, after_stat.st_mtime_ns):
            raise IngestError("Source file changed during this run")
        budget.check()
        local_bytes = sum(p.stat().st_size for p in staging.iterdir() if p.is_file())
        result = {
            "status": "validated", "kind": "user_sample_candidate", "run_id": staging.name,
            "scope_id": "rees46_2019_oct_user5_" + expected_sha[:16] + "_" + SEED + "_v1",
            "parent_sha256": expected_sha, "algorithm_version": ALGORITHM, "seed": SEED,
            "target_user_sampling_percent": 5, "selection_payload_prefix": PREFIX,
            "selection_threshold_uint64": THRESHOLD, "serialization": SERIALIZATION,
            "script_sha256": sha256(Path(__file__)),
            "helper_script_sha256": sha256(ROOT / "ingest/ingest.py"),
            "started_at_utc": started_at, "validated_at_utc": utc_now(),
            "expected_month_window": {"start_inclusive": START, "end_exclusive": END},
            "source_scan": {"status": "complete", **source_profile.summary(),
                            "distinct_user_count": "not_measured", "bytes": extraction["source_bytes"],
                            "sha256": extraction["source_sha256"]},
            "sample": {**validation, "bytes": extraction["sample_bytes"],
                       "sha256": extraction["sample_sha256"],
                       "field_sequence_sha256": extraction["field_sequence_sha256"],
                       "actual_event_extraction_ratio": candidate_profile.records / source_profile.records if source_profile.records else None},
            "source_dates_without_sample_records": sorted(set(source_profile.days) - set(candidate_profile.days)),
            "timing_seconds": {"source_scan_and_extract": round(scan_seconds, 3),
                               "sample_reread_validation": round(validation_seconds, 3),
                               "total_before_publish": round(time.monotonic() - start, 3)},
            "resources": {"max_new_bytes": max_new_bytes, "minimum_free_bytes": minimum_free_bytes,
                          "new_data_and_sqlite_bytes": local_bytes, "free_before_bytes": free_before,
                          "free_after_bytes": shutil.disk_usage(staging).free,
                          "source_full_csv_parse_passes": 1, "source_full_binary_precheck_passes": 1,
                          "sample_copies_written": 1, "sample_reread_passes": 1,
                          "python_event_buffer_limit": 4096, "sqlite_cache_kib": 4096},
            "limitations": ["Input preparation only; business quality gates have not been passed.",
                            "Observed daily coverage does not prove upstream completeness.",
                            "Trajectories include this source file only, not a user's entire platform history.",
                            "5% is a target probability for user IDs, not an event share or measured full-population user share."]}
        phase = "publish"
        destination.mkdir(exist_ok=False)
        final = destination / "user_sample_candidate.csv"
        os.link(partial, final)  # One file, exclusive target; same local filesystem.
        partial.unlink()
        final.chmod(0o444)
        write_new_json(destination / "receipt.json", result)
        return result
    except BaseException as exc:
        write_new_json(staging / "failure.json", {
            "status": "failed", "complete": False, "phase": phase,
            "error_type": type(exc).__name__, "started_at_utc": started_at,
            "failed_at_utc": utc_now(), "elapsed_seconds": round(time.monotonic() - start, 3),
            "partial_source_profile": source_profile.summary(),
            "partial_selected_records": candidate_profile.records})
        raise


def load_config(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise IngestError("Duplicate sampling config key")
            result[key] = value
        return result
    try:
        cfg = json.loads(Path(path).read_text(), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError("Sampling configuration is missing or invalid") from exc
    fixed = {"manifest": "data/manifest.json", "ingest_config": "config/ingest.local.json",
             "source_id": SOURCE_ID, "parent_sha256": PARENT_SHA,
             "algorithm_version": ALGORITHM, "seed": SEED, "target_percent": 5,
             "expected_start_utc": START, "expected_end_utc": END,
             "max_new_bytes": MAX_NEW_BYTES, "minimum_free_bytes": MIN_FREE_BYTES,
             "progress_every_records": 1000000}
    if not isinstance(cfg, dict) or set(cfg) != set(fixed) | {"staging_root", "output_root"}:
        raise IngestError("Sampling configuration fields must be supplied exactly")
    if any(type(cfg[k]) is not type(v) or cfg[k] != v for k, v in fixed.items()):
        raise IngestError("Frozen sampling rule, source or resource limits changed")
    ingestion = load_ingest_config(ROOT / cfg["ingest_config"])
    manifest = json.loads((ROOT / cfg["manifest"]).read_text())
    matches = [r for r in manifest["files"] if r["format"] == "csv" and r["source_id"] == SOURCE_ID and r["sha256"] == PARENT_SHA]
    if len(matches) != 1 or matches[0]["status"] != "complete":
        raise IngestError("Exactly one complete registered October CSV is required")
    record = matches[0]
    source = (ROOT / record["local_relative_path"]).resolve()
    if not source.is_relative_to(ingestion["raw_root"]) or not source.is_file() or source.name != "2019-Oct.csv":
        raise IngestError("Manifest source does not resolve inside configured raw root")
    if source.stat().st_size != record["bytes"]:
        raise IngestError("Registered source size changed")
    roots = []
    for key in ["staging_root", "output_root"]:
        value = cfg[key]
        if not isinstance(value, str) or not value or "<" in value or "~" in value:
            raise IngestError("Unfilled sampling path: " + key)
        p = (ROOT / value).resolve()
        if not p.is_dir() or not p.is_relative_to(ROOT / ".local") or p == ROOT / ".local":
            raise IngestError("Sampling paths must be existing directories under .local")
        if not os.access(p, os.W_OK | os.X_OK):
            raise IngestError("Sampling output directory is not writable")
        if p.stat().st_dev != source.stat().st_dev:
            raise IngestError("Source and sampling roots must share the local filesystem")
        roots.append(p)
        cfg[key] = p
    all_roots = roots + [ingestion["raw_root"], ingestion["staging_root"], ingestion["sample_root"]]
    if any(a == b or a in b.parents or b in a.parents for i, a in enumerate(all_roots) for b in all_roots[i + 1:]):
        raise IngestError("Sampling roots must be disjoint from existing raw, staging and samples")
    cfg["source"] = source
    return cfg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    def interrupt(signum, frame):
        raise InterruptedError("Run interrupted")
    signal.signal(signal.SIGTERM, interrupt)
    try:
        if not args.run_id or not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
            raise IngestError("A fresh, safe run ID is required")
        cfg = load_config(args.config)
        result = execute(cfg["source"], cfg["parent_sha256"], cfg["staging_root"] / args.run_id,
                         cfg["output_root"] / args.run_id, cfg["progress_every_records"],
                         cfg["max_new_bytes"], cfg["minimum_free_bytes"])
        print(json.dumps({"status": result["status"], "run_id": result["run_id"],
                          "source_records": result["source_scan"]["record_count"],
                          "sample_records": result["sample"]["profile"]["record_count"],
                          "sample_users": result["sample"]["distinct_user_count"],
                          "sample_sha256": result["sample"]["sha256"],
                          "timing_seconds": result["timing_seconds"]}), flush=True)
    except (Exception, KeyboardInterrupt) as exc:
        print("Profiling/sampling failed: " + (str(exc) if isinstance(exc, IngestError) else type(exc).__name__), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
