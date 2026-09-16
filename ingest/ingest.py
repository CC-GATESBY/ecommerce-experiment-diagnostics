"""October-only ingestion. No Spark, business filtering, or numeric coercion."""

import argparse
import csv
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
GIB = 1024 ** 3
MIB = 1024 ** 2
CHUNK = MIB
SOURCE_ID = "rees46_multicategory_2019_oct"
DATASET = "mkechinov/ecommerce-behavior-data-from-multi-category-store"
PUBLISHER = "https://rees46.com/en/datasets"
CATALOG = "https://www.kaggle.com/datasets/" + DATASET
ARCHIVE_URL = "https://data.rees46.com/datasets/marketplace/2019-Oct.csv.gz"
HEADER = ["event_time", "event_type", "product_id", "category_id",
          "category_code", "brand", "price", "user_id", "user_session"]
RULE = "head_csv_records_v1;utf8;csv_strict;strings;header_once;LF;QUOTE_MINIMAL"
MAX_SAMPLE_BYTES = 64 * MIB


class IngestError(ValueError):
    """A validation failure that must not be silently bypassed."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def write_new_json(path, value):
    with Path(path).open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_config(path, root=ROOT):
    try:
        def unique(pairs):
            out = {}
            for key, val in pairs:
                if key in out:
                    raise IngestError("Duplicate config key: " + key)
                out[key] = val
            return out
        cfg = json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=unique)
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError("Missing or invalid ingestion config") from exc
    required = {"source_id", "dataset_ref", "catalog_version", "archive_url",
                "archive_bytes", "csv_expected_bytes", "archive_etag",
                "staging_root", "raw_root", "sample_root", "max_records"}
    if not isinstance(cfg, dict) or set(cfg) != required:
        raise IngestError("Required ingestion fields must be supplied exactly")
    fixed = {"source_id": SOURCE_ID, "dataset_ref": DATASET, "catalog_version": 8,
             "archive_url": ARCHIVE_URL, "archive_bytes": 1741928540,
             "csv_expected_bytes": 5668612855, "archive_etag": '"646b587b-67d3b85c"'}
    if any(type(cfg[k]) is not type(v) or cfg[k] != v for k, v in fixed.items()):
        raise IngestError("Source metadata changed: recheck source and budget first")
    if type(cfg["max_records"]) is not int or not 1 <= cfg["max_records"] <= 100000:
        raise IngestError("max_records must be in 1..100000")
    roots = []
    for key in ("staging_root", "raw_root", "sample_root"):
        val = cfg[key]
        if not isinstance(val, str) or not val or "<" in val or "~" in val:
            raise IngestError("Unfilled path: " + key)
        p = Path(val)
        if not p.is_absolute():
            p = root / p
        p = p.resolve()
        local = (root / ".local").resolve()
        if not p.is_relative_to(local) or p == local or not p.is_dir():
            raise IngestError("Paths must be existing directories inside .local")
        if not os.access(p, os.W_OK | os.X_OK):
            raise IngestError("Ingestion path is not writable")
        roots.append(p)
        cfg[key] = p
    if any(a == b or a in b.parents or b in a.parents
           for i, a in enumerate(roots) for b in roots[i + 1:]):
        raise IngestError("Staging, raw and samples must be disjoint")
    return cfg


def budget(cfg, free_bytes):
    # Two bounded sample runs; staging files move into raw on the same volume.
    growth = cfg["archive_bytes"] + cfg["csv_expected_bytes"] + 2 * MAX_SAMPLE_BYTES
    if cfg["archive_bytes"] > 8 * GIB or growth > 25 * GIB:
        raise IngestError("Download or disk growth exceeds this turn's budget")
    if free_bytes - growth < 150 * GIB:
        raise IngestError("Projected free disk falls below 150 GiB")
    return {"free_before_bytes": free_bytes, "maximum_new_bytes": growth,
            "projected_free_bytes": free_bytes - growth,
            "download_limit_bytes": 8 * GIB, "growth_limit_bytes": 25 * GIB,
            "minimum_free_bytes": 150 * GIB}


class PublicSourceOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if newurl != ARCHIVE_URL:
            raise IngestError("Unexpected redirect; source must be reviewed again")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_source(method="GET"):
    request = urllib.request.Request(ARCHIVE_URL, method=method,
                                     headers={"Accept-Encoding": "identity"})
    try:
        return urllib.request.build_opener(PublicSourceOnly).open(request, timeout=60)
    except urllib.error.HTTPError as exc:
        raise IngestError("Source HTTP status " + str(exc.code)) from None
    except urllib.error.URLError:
        raise IngestError("Source network connection failed") from None


def verify_headers(response, cfg):
    if response.status != 200:
        raise IngestError("Source did not return HTTP 200")
    if response.headers.get("Content-Length") != str(cfg["archive_bytes"]):
        raise IngestError("Source Content-Length changed or missing")
    if response.headers.get("ETag") != cfg["archive_etag"]:
        raise IngestError("Source ETag changed or missing")
    if response.headers.get("Content-Encoding") not in (None, "identity"):
        raise IngestError("Unexpected HTTP content encoding")


def stream_download(response, destination, expected_bytes):
    """Keep partial files on failure; only complete transfers receive receipts."""
    destination = Path(destination)
    partial = destination.with_name(destination.name + ".part")
    receipt_path = destination.with_name(destination.name + ".download.json")
    if destination.exists() or receipt_path.exists():
        raise IngestError("Download destination already exists")
    count, digest, start = 0, hashlib.sha256(), time.monotonic()
    started = utc_now()
    try:
        with partial.open("xb") as f:
            while True:
                # Read at most one excess byte, then stop if server size is wrong.
                block = response.read(min(CHUNK, expected_bytes - count + 1))
                if not block:
                    break
                count += len(block)
                if count > expected_bytes:
                    raise IngestError("Download exceeds verified byte count")
                f.write(block)
                digest.update(block)
                if count // (64 * MIB) != (count - len(block)) // (64 * MIB):
                    if shutil.disk_usage(destination.parent).free < 150 * GIB:
                        raise IngestError("Free disk fell below 150 GiB during download")
                    print(json.dumps({"downloaded_bytes": count}), flush=True)
            f.flush()
            os.fsync(f.fileno())
        if count != expected_bytes:
            raise IngestError("Incomplete download byte count")
        os.link(partial, destination)  # Exclusive creation, never overwrite.
        partial.unlink()
        receipt = {"status": "complete", "filename": destination.name,
                   "bytes": count, "sha256": digest.hexdigest(),
                   "started_at_utc": started, "acquired_at_utc": utc_now(),
                   "elapsed_seconds": round(time.monotonic() - start, 3)}
        write_new_json(receipt_path, receipt)
        return receipt
    except Exception:
        if not receipt_path.exists():
            write_new_json(receipt_path, {"status": "failed", "received_bytes": count,
                                         "started_at_utc": started})
        raise


def extract_gzip(archive, destination, expected_bytes, allowed_root):
    """Ignore embedded gzip names; output only the explicitly allowed basename."""
    destination, allowed_root = Path(destination), Path(allowed_root).resolve()
    if destination.name != "2019-Oct.csv" or destination.parent.resolve() != allowed_root:
        raise IngestError("Unsafe extraction destination")
    if destination.exists() or destination.is_symlink():
        raise IngestError("Extraction would overwrite an existing file")
    partial = destination.with_name(destination.name + ".part")
    count, digest = 0, hashlib.sha256()
    with gzip.open(archive, "rb") as source, partial.open("xb") as target:
        while True:
            block = source.read(min(CHUNK, expected_bytes - count + 1))
            if not block:
                break  # Reading through EOF also checks gzip CRC/trailer.
            count += len(block)
            if count > expected_bytes:
                raise IngestError("Extracted size exceeds verified expectation")
            target.write(block)
            digest.update(block)
            if count // (256 * MIB) != (count - len(block)) // (256 * MIB):
                if shutil.disk_usage(allowed_root).free < 150 * GIB:
                    raise IngestError("Free disk fell below 150 GiB during extraction")
        target.flush()
        os.fsync(target.fileno())
    if count != expected_bytes:
        raise IngestError("Extracted size differs from catalog expectation")
    os.link(partial, destination)
    partial.unlink()
    receipt = {"status": "complete", "filename": destination.name, "bytes": count,
               "sha256": digest.hexdigest(), "acquired_at_utc": utc_now(),
               "gzip_crc": "pass"}
    write_new_json(destination.with_name(destination.name + ".extract.json"), receipt)
    return receipt


def csv_header(path, expected=None):
    try:
        with Path(path).open(encoding="utf-8", newline="") as f:
            header = next(csv.reader(f, strict=True))
    except (StopIteration, UnicodeError, csv.Error) as exc:
        raise IngestError("CSV header is unreadable") from exc
    if not header or len(set(header)) != len(header) or any(not x for x in header):
        raise IngestError("CSV header is empty or has duplicate columns")
    if expected is not None and header != expected:
        raise IngestError("CSV header does not match the verified field list")
    return header


def register_file(registry, path, receipt, metadata):
    """Deduplicate by content and reject a filename reused for different bytes."""
    path = Path(path)
    if receipt.get("status") != "complete" or path.suffix == ".part":
        raise IngestError("Incomplete input cannot be registered")
    if path.stat().st_size != receipt.get("bytes") or sha256(path) != receipt.get("sha256"):
        raise IngestError("File no longer matches the completed receipt")
    digest = receipt["sha256"]
    for record in registry:
        if path.name in record["observed_filenames"] and record["sha256"] != digest:
            raise IngestError("Same filename has different content; review required")
    for record in registry:
        if record["sha256"] == digest:
            if path.name not in record["observed_filenames"]:
                record["observed_filenames"].append(path.name)
            return record, False
    record = dict(metadata)
    record.update({"filename": path.name, "observed_filenames": [path.name],
                   "bytes": receipt["bytes"], "sha256": digest,
                   "acquired_at_utc": receipt["acquired_at_utc"],
                   "status": "complete", "full_record_count": "not_measured",
                   "full_time_range": "not_measured"})
    registry.append(record)
    return record, True


def publish_raw(staged, raw_root, digest):
    """Promote complete input exclusively; never replace or delete raw files."""
    directory = Path(raw_root) / digest
    directory.mkdir(exist_ok=True)
    if directory.resolve().parent != Path(raw_root).resolve():
        raise IngestError("Raw destination escapes configured root")
    destination = directory / Path(staged).name
    if destination.exists():
        if sha256(destination) != digest:
            raise IngestError("Existing raw content is inconsistent")
        return destination
    os.link(staged, destination)
    Path(staged).unlink()
    destination.chmod(0o444)
    return destination


def sample_csv(source, parent_sha, output_dir, max_records=100000):
    if type(max_records) is not int or not 1 <= max_records <= 100000:
        raise IngestError("Sample limit must be in 1..100000")
    if sha256(source) != parent_sha:
        raise IngestError("Parent content changed before sampling")
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=False)  # Reruns must use a fresh directory.
    output = output_dir / "engineering_sample.csv"
    partial = output_dir / "engineering_sample.csv.part"
    count, failures, earliest, latest = 0, 0, None, None
    header = csv_header(source)
    if "event_time" not in header:
        raise IngestError("event_time is required for the sample receipt")
    time_column = header.index("event_time")
    with Path(source).open(encoding="utf-8", newline="") as f, \
            partial.open("x", encoding="utf-8", newline="") as out:
        reader, writer = csv.reader(f, strict=True), csv.writer(out, lineterminator="\n")
        next(reader)
        writer.writerow(header)
        for _ in range(max_records):
            row = next(reader, None)
            if row is None:
                break
            if len(row) != len(header):
                raise IngestError("Malformed CSV width; sample left incomplete")
            writer.writerow(row)  # All values remain strings, including empties.
            count += 1
            if out.tell() > MAX_SAMPLE_BYTES:
                raise IngestError("Sample byte budget exceeded")
            try:
                timestamp = datetime.strptime(row[time_column], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
                earliest = timestamp if earliest is None else min(earliest, timestamp)
                latest = timestamp if latest is None else max(latest, timestamp)
            except ValueError:
                failures += 1  # Preserve the original value in the output.
        out.flush()
        os.fsync(out.fileno())
    os.link(partial, output)
    partial.unlink()
    output.chmod(0o444)
    script_sha = sha256(Path(__file__))
    rule = RULE + ";max_records=" + str(max_records)
    scope = hashlib.sha256((parent_sha + "\n" + rule).encode()).hexdigest()[:20]
    result = {"kind": "engineering_sample", "scope_id": "rees46_oct_head_" + scope,
              "parent_sha256": parent_sha, "extraction_rule": rule,
              "script_sha256": script_sha, "random_seed": "not_applicable_ordered_prefix",
              "record_count": count, "header": header, "bytes": output.stat().st_size,
              "sha256": sha256(output), "created_at_utc": utc_now(),
              "sample_time_range_utc": {"min": earliest.isoformat() if earliest else None,
                                        "max": latest.isoformat() if latest else None},
              "time_parse_failures": failures, "parsing_status": "sample_records_parsed",
              "limitations": "ordered prefix; no population, retention, long-window or CUPED claims"}
    write_new_json(output_dir / "receipt.json", result)
    return result


def metadata(kind, header="not_applicable"):
    return {"source_id": SOURCE_ID, "publisher_entry": PUBLISHER, "catalog_entry": CATALOG,
            "dataset_ref": DATASET, "catalog_version": 8,
            "version": "publisher_unversioned_object; catalog_v8_context_only",
            "source_url": ARCHIVE_URL, "format": kind, "header": header,
            "parsing_status": "gzip_crc_verified" if kind == "gzip" else "header_parsed_only",
            "authenticity": "original_publisher_link_and_https; SHA256_is_content_tracking_only"}


def run(cfg):
    registry_path = cfg["raw_root"].parent / "registry.json"
    if registry_path.exists():
        result = json.loads(registry_path.read_text())
        if result.get("status") != "registered":
            raise IngestError("Existing registry requires review")
        for item in result["files"]:
            path = (ROOT / item["local_relative_path"]).resolve()
            if not path.is_relative_to(cfg["raw_root"]) or sha256(path) != item["sha256"]:
                raise IngestError("Existing raw registry verification failed")
        print("Existing registered content verified; no download or overwrite.", flush=True)
        return result
    free = shutil.disk_usage(cfg["staging_root"]).free
    costs = budget(cfg, free)
    with open_source("HEAD") as r:
        verify_headers(r, cfg)
    run_id = "rees46-oct-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    staging = cfg["staging_root"] / run_id
    staging.mkdir()
    write_new_json(staging / "preflight.json", costs)
    archive = staging / "2019-Oct.csv.gz"
    with open_source() as response:
        verify_headers(response, cfg)
        downloaded = stream_download(response, archive, cfg["archive_bytes"])
    unpacked = staging / "2019-Oct.csv"
    extracted = extract_gzip(archive, unpacked, cfg["csv_expected_bytes"], staging)
    header = csv_header(unpacked, HEADER)
    files = []
    gz_record, _ = register_file(files, archive, downloaded, metadata("gzip"))
    csv_record, _ = register_file(files, unpacked, extracted, metadata("csv", header))
    csv_record["parent_archive_sha256"] = gz_record["sha256"]
    gz_record["extracted_csv_sha256"] = csv_record["sha256"]
    for path, record in [(archive, gz_record), (unpacked, csv_record)]:
        dest = publish_raw(path, cfg["raw_root"], record["sha256"])
        record["local_relative_path"] = dest.relative_to(ROOT).as_posix()
    result = {"status": "registered", "run_id": run_id, "files": files,
              "download_payload_bytes": downloaded["bytes"], "budget": costs,
              "free_after_raw_bytes": shutil.disk_usage(cfg["raw_root"]).free}
    write_new_json(registry_path, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["check", "acquire", "sample"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    try:
        cfg = load_config(args.config)
        if args.command == "check":
            result = budget(cfg, shutil.disk_usage(cfg["staging_root"]).free)
        elif args.command == "acquire":
            result = run(cfg)
        else:
            if not args.run_id or not all(c.isalnum() or c in "-_" for c in args.run_id):
                raise IngestError("Supply a new, safe --run-id")
            registry_path = cfg["raw_root"].parent / "registry.json"
            registry = json.loads(registry_path.read_text())
            if registry.get("status") != "registered":
                raise IngestError("Raw input has not completed registration")
            record = next(r for r in registry["files"] if r["format"] == "csv")
            path = (ROOT / record["local_relative_path"]).resolve()
            if not path.is_relative_to(cfg["raw_root"]):
                raise IngestError("Registered input is outside configured raw root")
            result = sample_csv(path, record["sha256"], cfg["sample_root"] / args.run_id,
                                cfg["max_records"])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (IngestError, OSError, EOFError, UnicodeError, json.JSONDecodeError,
            csv.Error, StopIteration, KeyError) as exc:
        # Avoid printing URLs, secrets or local paths from external exceptions.
        message = str(exc) if isinstance(exc, IngestError) else type(exc).__name__
        print("Ingestion failed: " + message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
