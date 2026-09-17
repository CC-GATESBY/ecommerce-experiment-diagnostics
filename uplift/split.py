"""Frozen treatment-stratified split and independent streaming verification."""

import argparse
from decimal import Decimal
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time

from ingest.ingest import ROOT, GIB, IngestError, sha256, utc_now, write_new_json
from ingest.ingest_criteo_source import independent_records
from uplift.ingest_criteo import CSV_SHA, RECORDS, SOURCE_ID, bind_source, rows

IDENTITY_VERSION = "criteo-row-id-v1"
SPLIT_VERSION = "criteo-stratified-hash-split-v1"
SEED = 20260917
TRAIN_THRESHOLD = (3 * 2**64) // 5
VALID_THRESHOLD = (4 * 2**64) // 5
SPLITS = ("train", "valid", "test")
LABELS = ("treatment", "conversion", "visit", "exposure")
MEMBERSHIP_HEADER = b"source_record_ordinal\trow_id\ttreatment\tsplit\n"
BASE = ROOT / ".local/t31"
MAX_BYTES = 4 * GIB
MIN_FREE = 150 * GIB


def row_id(source_sha, ordinal):
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha) or type(ordinal) is not int or ordinal < 0:
        raise IngestError("Invalid identity namespace or ordinal")
    return hashlib.sha256(f"criteo-row-v1|{source_sha}|{ordinal}".encode("utf-8")).hexdigest()


def choose_uint64(h):
    if type(h) is not int or not 0 <= h < 2**64:
        raise IngestError("Split hash must be uint64")
    return "train" if h < TRAIN_THRESHOLD else "valid" if h < VALID_THRESHOLD else "test"


def assign(identity, treatment):
    if treatment not in ("0", "1") or not re.fullmatch(r"[0-9a-f]{64}", identity):
        raise IngestError("Invalid treatment or row ID")
    payload = f"criteo-split-v1|{SEED}|t={treatment}|{identity}".encode("utf-8")
    return choose_uint64(int.from_bytes(hashlib.sha256(payload).digest()[:8], "big"))


def finish(n, split_counts, arm_counts, source_counts, logical, sequences, logical_bytes):
    # Only serialization is shared; independent counters and hash logic are not.
    return {"n": n, "ordinal_min": 0 if n else None, "ordinal_max": n-1 if n else None,
            "split_counts": split_counts, "treatment_split_counts": arm_counts,
            "source_binary_counts": source_counts, "logical_bytes": logical_bytes,
            "logical_sha256": logical.hexdigest(),
            "sequence_sha256": {k: v.hexdigest() for k, v in sequences.items()}}


def generate(path, source_sha, destination, progress=None):
    destination = Path(destination)
    start = time.monotonic()
    sc = {k: {"n": 0, "conversion": 0, "visit": 0, "exposure": 0} for k in SPLITS}
    ac = {f"{t}/{s}": dict(n=0, conversion=0, visit=0, exposure=0) for t in ("0", "1") for s in SPLITS}
    source = {k: {"0": 0, "1": 0} for k in LABELS}
    sequences = {k: hashlib.sha256() for k in list(sc) + list(ac)}
    logical = hashlib.sha256(MEMBERSHIP_HEADER)
    logical_bytes, n = len(MEMBERSHIP_HEADER), 0
    with destination.open("xb") as target:
        with gzip.GzipFile(filename="", mode="wb", fileobj=target, mtime=0, compresslevel=6) as gz:
            gz.write(MEMBERSHIP_HEADER)
            for ordinal, row in rows(path):
                identity = row_id(source_sha, ordinal)
                treatment = row[12]
                split = assign(identity, treatment)
                arm_key = treatment + "/" + split
                line = f"{ordinal}\t{identity}\t{treatment}\t{split}\n".encode("utf-8")
                gz.write(line); logical.update(line); logical_bytes += len(line)
                sequence_item = (identity + "\n").encode("ascii")
                sequences[split].update(sequence_item); sequences[arm_key].update(sequence_item)
                sc[split]["n"] += 1; ac[arm_key]["n"] += 1
                for j, label in enumerate(LABELS, 12):
                    source[label][row[j]] += 1
                    if j > 12:
                        sc[split][label] += int(row[j]); ac[arm_key][label] += int(row[j])
                n += 1
                if n % 500000 == 0 and progress:
                    progress("generate", n, time.monotonic()-start)
        target.flush(); os.fsync(target.fileno())
    result = finish(n, sc, ac, source, logical, sequences, logical_bytes)
    result.update(compressed_bytes=destination.stat().st_size, compressed_sha256=sha256(destination),
                  elapsed_seconds=round(time.monotonic()-start, 3))
    return result


def independent_check(path, source_sha, membership, progress=None):
    """Recompute from raw with a different lexer/formula and read every output row."""
    start = time.monotonic()
    split_names = ["train", "valid", "test"]
    outcomes = ["conversion", "visit", "exposure"]
    grouped = {key: [0, 0, 0, 0] for key in split_names + [str(t)+"/"+s for t in range(2) for s in split_names]}
    binary = {key: [0, 0] for key in ["treatment"]+outcomes}
    digest_map = {key: hashlib.sha256() for key in grouped}
    head = "source_record_ordinal\trow_id\ttreatment\tsplit\n".encode()
    overall = hashlib.sha256(head)
    size, ordinal = len(head), 0
    with Path(path).open(encoding="utf-8", newline="") as raw, gzip.open(membership, "rb") as output:
        records = independent_records(raw)
        expected_header = [f"f{i}" for i in range(12)] + ["treatment", "conversion", "visit", "exposure"]
        if next(records, None) != expected_header or output.readline(256) != head:
            raise IngestError("Independent raw/membership header mismatch")
        for fields in records:
            if len(fields) != 16 or any(x not in {"0", "1"} for x in fields[12:]):
                raise IngestError("Independent field width or domain mismatch")
            rid = hashlib.sha256(b"criteo-row-v1|" + source_sha.encode("ascii") + b"|" + str(ordinal).encode("ascii")).hexdigest()
            key = "criteo-split-v1|20260917|t=" + fields[12] + "|" + rid
            number = int(hashlib.sha256(key.encode()).hexdigest()[0:16], 16)
            if number < (2**64 * 3 // 5):
                label = "train"
            elif number < (2**64 * 4 // 5):
                label = "valid"
            else:
                label = "test"
            expected_line = ("\t".join([str(ordinal), rid, fields[12], label])+"\n").encode()
            if output.readline(256) != expected_line:
                raise IngestError("Independent membership row mismatch at ordinal " + str(ordinal))
            overall.update(expected_line); size += len(expected_line)
            group = fields[12] + "/" + label
            for counter in (grouped[label], grouped[group]):
                counter[0] += 1
                counter[1] += fields[13] == "1"
                counter[2] += fields[14] == "1"
                counter[3] += fields[15] == "1"
            for col, name in enumerate(["treatment"]+outcomes, 12):
                binary[name][0 if fields[col] == "0" else 1] += 1
            digest_map[label].update(bytes(rid+"\n", "ascii"))
            digest_map[group].update(bytes(rid+"\n", "ascii"))
            ordinal += 1
            if ordinal % 500000 == 0 and progress:
                progress("independent", ordinal, time.monotonic()-start)
        if output.read(1):
            raise IngestError("Membership contains extra records")
    if not ordinal:
        raise IngestError("Independent header-only input rejected")
    counters = {key: dict(zip(["n"]+outcomes, values)) for key, values in grouped.items()}
    result = finish(ordinal, {k: counters[k] for k in split_names},
                    {k: v for k, v in counters.items() if "/" in k},
                    {k: dict(zip(["0", "1"], v)) for k, v in binary.items()}, overall, digest_map, size)
    result.update(readback_rows=ordinal, gzip_crc="pass", elapsed_seconds=round(time.monotonic()-start, 3))
    return result


def validate(primary, independent, expected_count, source_counts, sanity=True):
    checks = []
    def check(name, expected, actual):
        checks.append({"check": name, "expected": expected, "actual": actual, "pass": expected == actual})
        if expected != actual:
            raise IngestError("Validation mismatch: " + name)
    for key in ("n", "ordinal_min", "ordinal_max", "split_counts", "treatment_split_counts",
                "source_binary_counts", "logical_bytes", "logical_sha256", "sequence_sha256"):
        check("independent_"+key, primary[key], independent[key])
    check("full_source_count", expected_count, primary["n"])
    check("readback_every_record", expected_count, independent["readback_rows"])
    check("ordinal_bounds", [0, expected_count-1], [primary["ordinal_min"], primary["ordinal_max"]])
    check("split_sum", expected_count, sum(v["n"] for v in primary["split_counts"].values()))
    for field, counts in source_counts.items():
        check("source_"+field, {k: counts[k] for k in ("0", "1")}, primary["source_binary_counts"][field])
    for arm in ("0", "1"):
        total = source_counts["treatment"][arm]
        check("arm_"+arm, total, sum(primary["treatment_split_counts"][f"{arm}/{s}"]["n"] for s in SPLITS))
        if sanity:
            for split, target in zip(SPLITS, (Decimal("0.6"), Decimal("0.2"), Decimal("0.2"))):
                share = Decimal(primary["treatment_split_counts"][f"{arm}/{split}"]["n"]) / total
                check("sanity_"+arm+"/"+split, True, abs(share-target) <= Decimal("0.005"))
    return checks


def qc_rows(summary):
    result = []
    for treatment in ("all", "0", "1"):
        denominator = summary["n"] if treatment == "all" else summary["source_binary_counts"]["treatment"][treatment]
        for split in SPLITS:
            counts = summary["split_counts"][split] if treatment == "all" else summary["treatment_split_counts"][f"{treatment}/{split}"]
            row = {"treatment": treatment, "split": split, **counts,
                   "split_share_within_treatment": str(Decimal(counts["n"])/denominator) if denominator else None}
            for label in LABELS[1:]:
                row[label+"_rate"] = str(Decimal(counts[label])/counts["n"]) if counts["n"] else None
            result.append(row)
    return result


class Budget:
    def __init__(self, base):
        self.base, self.minimum_free = base, shutil.disk_usage(base).free
    def check(self, reserve=0):
        free = shutil.disk_usage(self.base).free
        self.minimum_free = min(self.minimum_free, free)
        used = sum(x.stat().st_size for x in self.base.rglob("*") if x.is_file())
        if used+reserve > MAX_BYTES or free-reserve < MIN_FREE:
            raise IngestError("T3.1 disk budget exceeded")
        return used
    def progress(self, stage, n, elapsed):
        self.check()
        print(json.dumps({"stage": stage, "records": n, "elapsed_seconds": round(elapsed, 3),
                          "minimum_free_sampled_bytes": self.minimum_free}), flush=True)


def publish_validated(staging, complete):
    """Keep directory writable until rename (required by this local filesystem)."""
    if complete.exists():
        raise IngestError("Complete output cannot be overwritten")
    staging.chmod(0o755)
    for p in staging.iterdir():
        p.chmod(0o444)
    staging.rename(complete)
    complete.chmod(0o555)


def resume_validated(run_id):
    """Publish only an already fully validated, unchanged staging artifact."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,70}", run_id):
        raise IngestError("Invalid run ID")
    run_dir = BASE / run_id; staging = run_dir / "staging"; complete = run_dir / "complete"
    if complete.exists() or not staging.is_dir():
        raise IngestError("No unpublished validated staging to resume")
    failed = json.loads((run_dir / "failed.json").read_text())
    if failed.get("stage") != "validate" or failed.get("error_type") != "PermissionError":
        raise IngestError("Only the recorded publication permission failure can resume")
    start = time.monotonic(); budget = Budget(BASE); budget.check()
    path, entry, current = bind_source()
    result = json.loads((staging / "run.json").read_text())
    validation = json.loads((staging / "validation.json").read_text())
    primary = json.loads((staging / "primary.json").read_text())
    independent = json.loads((staging / "independent.json").read_text())
    if (validation.get("status") != "pass" or validation["source_before"] != current
            or result["run_id"] != run_id or result["split_seed"] != SEED
            or result["row_identity_version"] != IDENTITY_VERSION
            or result["split_version"] != SPLIT_VERSION or result["source_csv_sha256"] != CSV_SHA
            or result["primary"] != primary or result["independent"] != independent
            or result["contract_sha256"] != sha256(ROOT / "docs/criteo_split_contract.md")):
        raise IngestError("Validated staging evidence changed")
    checks = validate(primary, independent, RECORDS, entry["profile"]["binary_counts"])
    member = staging / "split_membership.tsv.gz"
    if member.stat().st_size != primary["compressed_bytes"] or sha256(member) != primary["compressed_sha256"]:
        raise IngestError("Validated staging membership changed")
    recovery = {"status": "validated_for_publication", "run_id": run_id,
                "original_failure_preserved": True, "new_scan_or_split": False,
                "source_rechecked": current, "validation_checks": len(checks),
                "compressed_sha256": primary["compressed_sha256"],
                "publication_script_sha256": sha256(Path(__file__)),
                "elapsed_seconds": round(time.monotonic()-start, 3),
                "minimum_free_sampled_bytes": budget.minimum_free, "at_utc": utc_now()}
    write_new_json(run_dir / "publication_recheck.json", recovery)
    publish_validated(staging, complete)
    write_new_json(run_dir / "published.json", {"status": "complete", "run_id": run_id,
                   "at_utc": utc_now(), "recovery_evidence": "publication_recheck.json"})
    return result


def run(run_id):
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,70}", run_id):
        raise IngestError("Invalid run ID")
    BASE.mkdir(exist_ok=True)
    run_dir = BASE / run_id
    run_dir.mkdir(exist_ok=False)
    staging = run_dir / "staging"; staging.mkdir()
    started = time.monotonic()
    budget = Budget(BASE)
    stage = "preflight"
    try:
        # Conservative uncompressed-size bound plus space for safe receipts.
        budget.check(RECORDS*96 + 256*1024**2)
        path, entry, before = bind_source()
        contract_sha = sha256(ROOT / "docs/criteo_split_contract.md")
        write_new_json(staging / "preflight.json", {"checked_at_utc": utc_now(), **before,
                       "contract_sha256": contract_sha, "source_id": SOURCE_ID})
        stage = "generate"
        membership = staging / "split_membership.tsv.gz"
        primary = generate(path, CSV_SHA, membership, budget.progress)
        write_new_json(staging / "primary.json", primary)
        stage = "independent"
        independent = independent_check(path, CSV_SHA, membership, budget.progress)
        write_new_json(staging / "independent.json", independent)
        stage = "validate"
        checks = validate(primary, independent, RECORDS, entry["profile"]["binary_counts"])
        if sha256(path) != CSV_SHA or [path.stat().st_size, path.stat().st_mtime_ns] != before["csv_stat"]:
            raise IngestError("Raw changed during split")
        if sha256(ROOT / "data/manifest.json") != before["manifest_sha256"] or sha256(ROOT / ".local/t04/criteo_v2_1/registry.json") != before["registry_sha256"]:
            raise IngestError("Original source evidence changed")
        if sha256(membership) != primary["compressed_sha256"]:
            raise IngestError("Membership changed after write")
        if sha256(ROOT / "docs/criteo_split_contract.md") != contract_sha:
            raise IngestError("Frozen contract changed during run")
        new_bytes = budget.check()
        validation = {"status": "pass", "checks": checks, "source_before": before,
                      "source_after_sha256": CSV_SHA, "raw_unchanged": True,
                      "full_membership_readback": True, "gzip_crc": "pass"}
        write_new_json(staging / "validation.json", validation)
        result = {"status": "complete", "run_id": run_id, "created_at_utc": utc_now(),
                  "row_identity_version": IDENTITY_VERSION, "split_version": SPLIT_VERSION,
                  "split_seed": SEED, "source_id": SOURCE_ID, "source_csv_sha256": CSV_SHA,
                  "source_bytes": path.stat().st_size, "contract_sha256": contract_sha,
                  "script_sha256": sha256(Path(__file__)), "ingest_script_sha256": sha256(ROOT / "uplift/ingest_criteo.py"),
                  "membership": f".local/t31/{run_id}/complete/split_membership.tsv.gz",
                  "primary": primary, "independent": independent, "qc": qc_rows(primary),
                  "elapsed_seconds": round(time.monotonic()-started, 3),
                  "resources": {"minimum_free_sampled_bytes": budget.minimum_free,
                                "output_tree_bytes_before_receipts": new_bytes,
                                "maximum_new_bytes": MAX_BYTES, "minimum_free_required": MIN_FREE,
                                "peak_memory": "not_measured"}}
        write_new_json(staging / "run.json", result)
        complete = run_dir / "complete"
        publish_validated(staging, complete)
        return result
    except BaseException as exc:
        write_new_json(run_dir / "failed.json", {"status": "failed", "stage": stage,
                       "error_type": type(exc).__name__, "recorded_at_utc": utc_now()})
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resume-validated", action="store_true")
    args = parser.parse_args()
    result = resume_validated(args.run_id) if args.resume_validated else run(args.run_id)
    print(json.dumps({"status": result["status"], "run_id": result["run_id"],
                      "records": result["primary"]["n"]}), flush=True)
