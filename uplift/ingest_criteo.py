"""Bind only the accepted corrected CSV; no download or source mutation."""

import csv
import json
from pathlib import Path

from ingest.ingest import ROOT, IngestError, sha256
from ingest.ingest_criteo_source import HEADER, SOURCE_ID

CSV_SHA = "e4d7c710ca1f38e523309d0f8a0745d1b53e7392d51f20d1088b6cfeaef222ef"
CSV_BYTES = 3248115221
RECORDS = 13979592


def rows(path):
    """Yield zero-based logical ordinals and strings, including duplicate rows."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f, strict=True)
        if next(reader, None) != HEADER:
            raise IngestError("Criteo CSV header mismatch or empty file")
        count = 0
        try:
            for ordinal, row in enumerate(reader):
                if len(row) != 16:
                    raise IngestError("Criteo CSV field width mismatch")
                if any(value not in ("0", "1") for value in row[12:]):
                    raise IngestError("Criteo binary domain mismatch")
                count += 1
                yield ordinal, row
        except (csv.Error, UnicodeError) as exc:
            raise IngestError("Criteo CSV structure/encoding failure") from exc
        if not count:
            raise IngestError("Header-only input cannot form a split")


def validate_entry(entry):
    if (entry.get("source_id") != SOURCE_ID or entry.get("version") != "corrected_v2.1"
            or entry.get("validation_status") != "passed_source_acceptance"
            or entry.get("gzip_crc") != "pass" or entry.get("independent_status") != "pass"):
        raise IngestError("Source manifest identity or acceptance mismatch")
    files = [x for x in entry["files"] if x.get("format") == "csv"]
    if len(files) != 1:
        raise IngestError("Exactly one CSV must be registered")
    item = files[0]
    required = {"source_id": SOURCE_ID, "kind": "raw", "status": "complete",
                "sha256": CSV_SHA, "bytes": CSV_BYTES, "full_record_count": RECORDS,
                "header": HEADER}
    if any(item.get(k) != v for k, v in required.items()):
        raise IngestError("CSV manifest identity mismatch")
    if (entry["profile"]["record_count"] != RECORDS
            or entry["profile"]["binary_counts"] != entry["independent"]["binary_counts"]):
        raise IngestError("Source profile evidence mismatch")
    return item


def bind_source(root=ROOT):
    manifest_path = root / "data/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    entry = manifest["additional_sources"][SOURCE_ID]
    item = validate_entry(entry)
    relative = Path(item["local_relative_path"])
    if relative.is_absolute() or ".." in relative.parts:
        raise IngestError("Raw locator must be a safe project-relative path")
    original = root / relative
    path = original.resolve()
    allowed = (root / ".local/t04/criteo_v2_1/raw" / CSV_SHA).resolve()
    if original.is_symlink() or path.parent != allowed or not path.is_file():
        raise IngestError("Raw path mismatch")
    if path.stat().st_size != CSV_BYTES or path.stat().st_mode & 0o222:
        raise IngestError("Raw bytes or read-only permission mismatch")
    registry_path = root / ".local/t04/criteo_v2_1/registry.json"
    registry = json.loads(registry_path.read_text())
    if (registry.get("status") != "registered" or registry.get("source_id") != SOURCE_ID
            or registry.get("files") != entry["files"]
            or registry.get("independent_status") != "pass"):
        raise IngestError("Local source registry mismatch")
    if sha256(path) != CSV_SHA:
        raise IngestError("Raw SHA256 changed")
    with path.open(encoding="utf-8", newline="") as f:
        if next(csv.reader(f, strict=True), None) != HEADER:
            raise IngestError("Raw header changed")
    return path, entry, {"manifest_sha256": sha256(manifest_path),
                         "registry_sha256": sha256(registry_path),
                         "csv_stat": [path.stat().st_size, path.stat().st_mtime_ns],
                         "csv_sha256": CSV_SHA}
