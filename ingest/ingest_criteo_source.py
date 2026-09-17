"""Corrected Criteo v2.1 source acceptance only; no split or effect estimation."""

import argparse
import csv
from decimal import Decimal
import gzip
import json
import math
import os
from pathlib import Path
import shutil
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from ingest.ingest import (ROOT, CHUNK, GIB, IngestError, publish_raw,
                           register_file, sha256, stream_download, utc_now,
                           write_new_json)

SOURCE_ID = "criteo_uplift_v2_1_corrected"
VERSION = "criteo-source-v1"
HEADER = [f"f{i}" for i in range(12)] + ["treatment", "conversion", "visit", "exposure"]
LABELS = HEADER[12:]
FILENAME = "criteo-research-uplift-v2.1.csv.gz"
HF_COMMIT = "2424920019e49d52d72c13ac1143ec5d53af276b"
SOURCE_URL = f"https://huggingface.co/datasets/criteo/criteo-uplift/resolve/{HF_COMMIT}/{FILENAME}"
EXPECTED_BYTES = 311422618
EXPECTED_SHA = "2716e1bf0fd157a93b5bf86924d9088419dfbac2022c6cd90030220634f616dc"
BASE = ROOT / ".local/t04/criteo_v2_1"
MAX_GROWTH = 8 * GIB
MIN_FREE = 150 * GIB
# Reserve 512 MiB for metadata, tests and receipts.
MAX_CSV_BYTES = MAX_GROWTH - EXPECTED_BYTES - 512 * 1024 ** 2


class ProfileError(IngestError):
    def __init__(self, message, progress):
        super().__init__(message)
        self.progress = progress


def usage_bytes(base):
    return sum(p.stat().st_size for p in Path(base).rglob("*") if p.is_file())


def check_budget(base, reserve=0):
    if usage_bytes(base) + reserve > MAX_GROWTH:
        raise IngestError("Criteo turn output budget exceeded")
    if shutil.disk_usage(base).free - reserve < MIN_FREE:
        raise IngestError("Criteo free disk budget exceeded")


def extract_archive(archive, destination, max_bytes=MAX_CSV_BYTES, guard=None):
    """Decode through EOF/CRC into one exclusive target; ignore gzip names."""
    destination = Path(destination)
    if destination.exists() or destination.is_symlink():
        raise IngestError("Extraction cannot overwrite an existing destination")
    partial = destination.with_name(destination.name + ".part")
    count = 0
    with gzip.open(archive, "rb") as source, partial.open("xb") as target:
        while block := source.read(min(CHUNK, max_bytes - count + 1)):
            count += len(block)
            if count > max_bytes:
                raise IngestError("Uncompressed CSV exceeds byte budget")
            target.write(block)
            if guard and count % (64 * CHUNK) < CHUNK:
                guard()
        target.flush()
        os.fsync(target.fileno())
    os.link(partial, destination)
    partial.unlink()
    return {"status": "complete", "bytes": count, "sha256": sha256(destination),
            "acquired_at_utc": utc_now(), "gzip_crc": "pass"}


def profile_csv(path, guard=None, progress_every=1_000_000):
    """Stream strings with Python's CSV parser; never retain event rows."""
    start = time.monotonic()
    result = {"header": [], "record_count": 0, "field_width_counts": {},
              "csv_structure_errors": 0,
              "binary_counts": {k: {"0": 0, "1": 0, "invalid": 0} for k in LABELS},
              "empty_counts": dict.fromkeys(HEADER, 0),
              "whitespace_only_counts": dict.fromkeys(HEADER, 0),
              "feature_nonfinite_or_invalid_counts": dict.fromkeys(HEADER[:12], 0)}
    try:
        with Path(path).open(encoding="utf-8", newline="") as f:
            reader = csv.reader(f, strict=True)
            result["header"] = next(reader, [])
            if result["header"] != HEADER:
                raise ValueError("Unexpected header")
            for row in reader:
                width = str(len(row))
                result["field_width_counts"][width] = result["field_width_counts"].get(width, 0) + 1
                if len(row) != 16:
                    raise ValueError("Unexpected field width")
                for i, (name, value) in enumerate(zip(HEADER, row)):
                    if value == "":
                        result["empty_counts"][name] += 1
                    elif value.isspace():
                        result["whitespace_only_counts"][name] += 1
                    if i < 12:
                        try:
                            finite = math.isfinite(float(value))
                        except (ValueError, OverflowError):
                            finite = False
                        if not finite:
                            result["feature_nonfinite_or_invalid_counts"][name] += 1
                    else:
                        result["binary_counts"][name][value if value in ("0", "1") else "invalid"] += 1
                result["record_count"] += 1
                if progress_every and result["record_count"] % progress_every == 0:
                    if guard:
                        guard()
                    print(json.dumps({"stage": "csv_profile", "records": result["record_count"],
                                      "elapsed_seconds": round(time.monotonic() - start, 3)}), flush=True)
    except (csv.Error, UnicodeError, ValueError) as exc:
        result["csv_structure_errors"] += 1
        result["status"] = "failed_partial_scan"
        raise ProfileError("CSV structure failed: " + type(exc).__name__, result) from None
    result["rates"] = {k: str(Decimal(v["1"]) / Decimal(result["record_count"]))
                       if result["record_count"] else None
                       for k, v in result["binary_counts"].items()}
    result.update(status="full_scan_complete", elapsed_seconds=round(time.monotonic() - start, 3))
    return result


def independent_records(stream):
    """RFC-style independent lexer with a validated unquoted-record fast path.

    Physical lines count as records only after ruling out quoting. Quoted
    records can span lines, have escaped quotes and empty fields. Memory is
    bounded to one 1 MiB logical record, never the complete input.
    """
    pending = ""
    for line in stream:
        pending += line
        if len(pending) > 1024 * 1024:
            raise IngestError("Independent logical record exceeds size limit")
        if pending.count('"') % 2:
            continue
        text = pending
        pending = ""
        if text.endswith("\r\n"):
            text = text[:-2]
        elif text.endswith(("\r", "\n")):
            text = text[:-1]
        if '"' not in text:
            yield text.split(",")
            continue
        row, field, state = [], [], "start"
        for char in text:
            if state == "quoted":
                if char == '"':
                    state = "after_quote"
                else:
                    field.append(char)
            elif state == "after_quote":
                if char == '"':
                    field.append(char)
                    state = "quoted"
                elif char == ",":
                    row.append("".join(field)); field = []; state = "start"
                else:
                    raise IngestError("Independent invalid character after closing quote")
            elif char == ",":
                row.append("".join(field)); field = []; state = "start"
            elif char == '"' and state == "start":
                state = "quoted"
            elif char in ('"', "\r", "\n"):
                raise IngestError("Independent invalid unquoted field")
            else:
                field.append(char); state = "unquoted"
        if state == "quoted":
            raise IngestError("Independent unterminated quoted field")
        row.append("".join(field))
        yield row
    if pending:
        raise IngestError("Independent unterminated final record")


def independent_csv_check(path, guard=None, progress_every=2_000_000):
    """Separate lexer and counters: no csv.reader, primary profile or summary."""
    start = time.monotonic()
    labels = ["treatment", "conversion", "visit", "exposure"]
    counts = {k: {"0": 0, "1": 0, "invalid": 0} for k in labels}
    total, widths = 0, {}
    with Path(path).open(encoding="utf-8", newline="") as f:
        records = independent_records(f)
        header = next(records, [])
        if header != [f"f{i}" for i in range(12)] + labels:
            raise IngestError("Independent header check failed")
        for row in records:
            if len(row) != 16:
                raise IngestError("Independent field width failed")
            total += 1
            widths[str(len(row))] = widths.get(str(len(row)), 0) + 1
            for index, name in enumerate(labels, 12):
                value = row[index]
                if value == "0":
                    counts[name]["0"] += 1
                elif value == "1":
                    counts[name]["1"] += 1
                else:
                    counts[name]["invalid"] += 1
            if progress_every and total % progress_every == 0:
                if guard:
                    guard()
                print(json.dumps({"stage": "independent_csv_check", "records": total,
                                  "elapsed_seconds": round(time.monotonic() - start, 3)}), flush=True)
    return {"header": header, "record_count": total, "field_width_counts": widths,
            "csv_structure_errors": 0, "binary_counts": counts,
            "implementation": "independent streaming CSV state lexer / counters",
            "elapsed_seconds": round(time.monotonic() - start, 3)}


def require_valid(primary, independent):
    for key in ("header", "record_count", "field_width_counts", "csv_structure_errors", "binary_counts"):
        if primary[key] != independent[key]:
            raise IngestError("Independent mismatch: " + key)
    if primary["status"] != "full_scan_complete" or primary["record_count"] <= 0:
        raise IngestError("Full nonempty scan required")
    if any(v["invalid"] for v in primary["binary_counts"].values()):
        raise IngestError("Binary label domain failed")
    if any(primary["empty_counts"].values()) or any(primary["whitespace_only_counts"].values()):
        raise IngestError("Missing field domain failed")
    if any(primary["feature_nonfinite_or_invalid_counts"].values()):
        raise IngestError("Finite feature domain failed")


class OfficialRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlsplit(newurl)
        allowed = u.hostname == "huggingface.co" or (u.hostname or "").endswith(".hf.co")
        if u.scheme != "https" or not allowed or u.username or u.password:
            raise IngestError("Unreviewed download redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def registered_or_none(base):
    path = base / "registry.json"
    if not path.exists():
        return None
    result = json.loads(path.read_text())
    if result.get("status") != "registered" or result.get("source_id") != SOURCE_ID:
        raise IngestError("Existing registration is not complete")
    if result.get("gzip_crc") != "pass" or result.get("independent_status") != "pass":
        raise IngestError("Existing registration lacks successful validation")
    require_valid(result["profile"], result["independent"])
    if len(result["files"]) != 2 or result["files"][0]["sha256"] != EXPECTED_SHA:
        raise IngestError("Existing registration identity conflicts")
    archive, unpacked = result["files"]
    if (archive.get("format") != "gzip" or unpacked.get("format") != "csv"
            or archive.get("extracted_csv_sha256") != unpacked["sha256"]
            or unpacked.get("parent_archive_sha256") != archive["sha256"]):
        raise IngestError("Existing archive/CSV relationship conflicts")
    for item in result["files"]:
        original = ROOT / item["local_relative_path"]
        p = original.resolve()
        if not p.is_relative_to((base / "raw").resolve()) or original.is_symlink():
            raise IngestError("Existing raw path is outside the source registry")
        if p.stat().st_size != item["bytes"] or sha256(p) != item["sha256"]:
            raise IngestError("Existing raw content conflicts")
    return result


def run(base=BASE):
    if not base.resolve().is_relative_to((ROOT / ".local/t04").resolve()):
        raise IngestError("Source storage must remain within project .local/t04")
    base.mkdir(parents=True, exist_ok=True)
    if previous := registered_or_none(base):
        print("Verified existing registration; no download or duplicate input.", flush=True)
        return previous
    check_budget(base, reserve=EXPECTED_BYTES + MAX_CSV_BYTES)
    start = time.monotonic()
    run_id = "criteo-v21-" + utc_now().replace(":", "").replace("+", "_")
    staging = base / "staging" / run_id
    staging.mkdir(parents=True, exist_ok=False)
    free_before = shutil.disk_usage(base).free
    stage = "download"
    try:
        opener = urllib.request.build_opener(OfficialRedirects)
        request = urllib.request.Request(SOURCE_URL, headers={"Accept-Encoding": "identity"})
        with opener.open(request, timeout=60) as r:
            if r.status != 200 or r.headers.get("Content-Length") != str(EXPECTED_BYTES):
                raise IngestError("Download HTTP identity/size changed")
            if r.headers.get("Content-Encoding") not in (None, "identity"):
                raise IngestError("Unexpected HTTP content encoding")
            downloaded = stream_download(r, staging / FILENAME, EXPECTED_BYTES)
        archive = staging / FILENAME
        if downloaded["sha256"] != EXPECTED_SHA:
            raise IngestError("Archive differs from pinned official LFS content")
        check_budget(base)
        stage = "extract_crc"
        csv_path = staging / FILENAME.removesuffix(".gz")
        extracted = extract_archive(archive, csv_path, guard=lambda: check_budget(base))
        stage = "python_full_profile"
        primary = profile_csv(csv_path, guard=lambda: check_budget(base))
        write_new_json(staging / "profile.json", primary)
        stage = "independent_full_scan"
        print(json.dumps({"stage": stage}), flush=True)
        independent = independent_csv_check(csv_path, guard=lambda: check_budget(base))
        write_new_json(staging / "independent.json", independent)
        check_budget(base)
        require_valid(primary, independent)
        stage = "register_publish"
        files = []
        for path, receipt, fmt in [(archive, downloaded, "gzip"), (csv_path, extracted, "csv")]:
            record, _ = register_file(files, path, receipt,
                                      {"source_id": SOURCE_ID, "kind": "raw", "format": fmt})
            record["full_record_count"] = primary["record_count"]
            record["full_time_range"] = "not_applicable_no_timestamp_field"
            record["header"] = primary["header"] if fmt == "csv" else "not_applicable"
        files[0]["extracted_csv_sha256"] = files[1]["sha256"]
        files[1]["parent_archive_sha256"] = files[0]["sha256"]
        raw = base / "raw"
        raw.mkdir(exist_ok=True)
        for path, record in zip([archive, csv_path], files):
            dest = publish_raw(path, raw, record["sha256"])
            record["local_relative_path"] = dest.relative_to(ROOT).as_posix()
            dest.parent.chmod(0o555)
        result = {"status": "registered", "source_id": SOURCE_ID, "run_id": run_id,
                  "version": "corrected_v2.1", "script_version": VERSION,
                  "script_sha256": sha256(Path(__file__)), "acquired_at_utc": downloaded["acquired_at_utc"],
                  "source_channel": "official_criteo_huggingface", "source_url": SOURCE_URL,
                  "hf_commit": HF_COMMIT, "files": files, "profile": primary,
                  "independent": independent, "gzip_crc": "pass", "independent_status": "pass",
                  "download_payload_bytes": downloaded["bytes"], "download_seconds": downloaded["elapsed_seconds"],
                  "elapsed_seconds": round(time.monotonic() - start, 3),
                  "budget": {"network_payload_limit": GIB, "output_limit": MAX_GROWTH,
                             "minimum_free": MIN_FREE, "free_before": free_before,
                             "free_after": shutil.disk_usage(base).free,
                             "current_source_directory_bytes": usage_bytes(base)},
                  "peak_memory": "not_measured", "registered_at_utc": utc_now()}
        write_new_json(staging / "complete.json", result)
        write_new_json(base / "registry.json", result)
        (base / "registry.json").chmod(0o444)
        return result
    except BaseException as exc:
        failed = {"status": "failed", "stage": stage, "error_type": type(exc).__name__,
                  "run_id": run_id, "at_utc": utc_now()}
        if isinstance(exc, ProfileError):
            failed["partial_profile_not_full_file"] = exc.progress
        write_new_json(staging / "failed.json", failed)
        # Network exception strings may contain signed redirects; never log them.
        raise IngestError("Run failed at " + stage + ": " + type(exc).__name__) from None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    parser.parse_args()
    result = run()
    print(json.dumps({"status": result["status"], "run_id": result["run_id"],
                      "record_count": result["profile"]["record_count"]}), flush=True)
