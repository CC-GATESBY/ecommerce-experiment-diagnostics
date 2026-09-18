"""T3.2: one corrected-source scan, two assignment groups, bounded ITT output."""

import argparse
import csv
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from uplift.ingest_criteo import CSV_SHA, HEADER, SOURCE_ID, validate_entry
from scripts.project_config import load_config

VERSION = "criteo-assignment-itt-v1"
METRICS = ("conversion", "visit", "exposure")
ROLES = ("primary", "secondary", "descriptive")
MIN_CELL = 5  # Project normal-approximation diagnostic, not a universal threshold.


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def file_state(path):
    s = Path(path).stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode]


def write_json(path, data):
    with Path(path).open("x") as f:
        json.dump(data, f, indent=2, allow_nan=False)
        f.write("\n")


def estimate(n0, n1, k0, k1, metric="conversion"):
    """Unpooled Bernoulli difference; no p-value or exposure-conditioned effect."""
    require(metric in METRICS, "unknown metric")
    require(all(type(x) is int and x >= 0 for x in (n0, n1, k0, k1))
            and k0 <= n0 and k1 <= n1, "invalid binary sufficient statistics")
    out = dict(metric=metric, role=ROLES[METRICS.index(metric)], control_n=n0,
               treatment_n=n1, control_events=k0, treatment_events=k1)
    fields = ("control_rate treatment_rate absolute_difference absolute_difference_pp "
              "absolute_difference_bp relative_lift standard_error ci95_low ci95_high "
              "incremental_per_10k incremental_per_10k_ci_low incremental_per_10k_ci_high")
    out.update({f: None for f in fields.split()})
    out["normal_approximation_min_cell"] = min(k0, n0-k0, k1, n1-k1)
    if not n0 or not n1:
        out["status"] = "empty_group"
        return out
    with localcontext() as context:
        context.prec = 40
        p0, p1 = Decimal(k0)/n0, Decimal(k1)/n1
        diff = p1-p0
        values = dict(control_rate=p0, treatment_rate=p1, absolute_difference=diff,
                      absolute_difference_pp=diff*100, absolute_difference_bp=diff*10000)
        if metric == "exposure":
            out["status"] = "descriptive_post_treatment_only"
        else:
            se = (p1*(1-p1)/n1 + p0*(1-p0)/n0).sqrt()
            values.update(relative_lift=diff/p0 if p0 else None,
                          standard_error=se, incremental_per_10k=diff*10000)
            if out["normal_approximation_min_cell"] < MIN_CELL:
                out["status"] = "sparse_cells_ci_not_reported"
            else:
                low, high = diff-Decimal("1.96")*se, diff+Decimal("1.96")*se
                values.update(ci95_low=low, ci95_high=high,
                              incremental_per_10k_ci_low=low*10000,
                              incremental_per_10k_ci_high=high*10000)
                out["status"] = "ok_published_sample_normal_approximation"
        out.update({k: str(v) if v is not None else None for k, v in values.items()})
    return out


def effects(groups):
    require([r["treatment"] for r in groups] == [0, 1], "exactly two assignment groups required")
    a, b = groups
    return [estimate(a["n"], b["n"], a[m+"_count"], b[m+"_count"], m) for m in METRICS]


def independent_formula_check(groups, table):
    """Independent float/math formula on two counts only; no primary estimator call."""
    checks = []
    for metric, row in zip(METRICS[:2], table[:2]):
        a, b = groups
        p = a[metric+"_count"]/a["n"]
        q = b[metric+"_count"]/b["n"]
        difference = q-p
        error = math.sqrt(q*(1-q)/b["n"] + p*(1-p)/a["n"])
        expected = dict(absolute_difference=difference, standard_error=error,
                        ci95_low=difference-1.96*error, ci95_high=difference+1.96*error,
                        incremental_per_10k=10000*difference,
                        incremental_per_10k_ci_low=10000*(difference-1.96*error),
                        incremental_per_10k_ci_high=10000*(difference+1.96*error))
        passed = all(row[k] is not None and math.isclose(float(row[k]), v, rel_tol=1e-12, abs_tol=1e-14)
                     for k, v in expected.items())
        checks.append(dict(metric=metric, expected=expected,
                           actual={k: row[k] for k in expected}, passed=passed))
    require(all(c["passed"] for c in checks), "independent formula mismatch")
    return checks


def aggregate_csv(spark, path):
    """Scan once; cache only the two aggregate rows for a repeat read."""
    from pyspark import StorageLevel
    from pyspark.sql import functions as F, types as T
    schema = T.StructType([T.StructField(c, T.StringType(), True) for c in HEADER])
    frame = (spark.read.schema(schema).option("header", True).option("enforceSchema", False)
             .option("mode", "FAILFAST").option("multiLine", True)
             .option("quote", '"').option("escape", '"')
             .option("ignoreLeadingWhiteSpace", False).option("ignoreTrailingWhiteSpace", False)
             .csv(str(path)))
    invalid = F.lit(False)
    for name in ("treatment", *METRICS):
        invalid = invalid | F.col(name).isNull() | ~F.col(name).isin("0", "1")
    summary = frame.groupBy("treatment").agg(
        F.count("*").alias("n"),
        *[F.sum(F.when(F.col(m) == "1", 1).otherwise(0)).alias(m+"_count") for m in METRICS],
        F.sum(F.when(invalid, 1).otherwise(0)).alias("invalid_labels")
    ).persist(StorageLevel.MEMORY_ONLY)
    try:
        rows = summary.orderBy("treatment").limit(3).collect()
        require(len(rows) == 2 and [r.treatment for r in rows] == ["0", "1"], "two valid arms required")
        require(all(r.invalid_labels == 0 for r in rows), "invalid or missing binary labels")
        repeated = summary.orderBy("treatment").limit(3).collect()
        require(rows == repeated, "cached two-row summary repeat mismatch")
        return [dict(treatment=int(r.treatment), **{c: r[c] for c in ("n", *[m+"_count" for m in METRICS])})
                for r in rows]
    finally:
        summary.unpersist(blocking=True)


def source_metadata():
    """Reuse accepted full hashes; verify receipts/stat without another raw scan."""
    entry = json.loads((ROOT/"data/manifest.json").read_text())["additional_sources"][SOURCE_ID]
    item = validate_entry(entry)
    relative = Path(item["local_relative_path"])
    require(not relative.is_absolute() and ".." not in relative.parts, "invalid raw locator")
    raw = ROOT/relative
    require(not raw.is_symlink() and raw.resolve().parent ==
            (ROOT/".local/t04/criteo_v2_1/raw"/CSV_SHA).resolve(), "raw location mismatch")
    split = json.loads((ROOT/"data/criteo_split_manifest.json").read_text())
    require(split["source"]["csv_sha256"] == CSV_SHA and split["validation"]["status"] == "pass"
            and split["run_id"] == "criteo-split-v1-01", "split evidence mismatch")
    complete = ROOT/".local/t31/criteo-split-v1-01/complete"
    checked = json.loads((complete/"preflight.json").read_text())
    validation = json.loads((complete/"validation.json").read_text())
    published = json.loads((complete.parent/"published.json").read_text())
    require(validation["status"] == "pass" and validation["raw_unchanged"]
            and published["status"] == "complete", "T3.1 not complete")
    require([raw.stat().st_size, raw.stat().st_mtime_ns] == checked["csv_stat"]
            and not raw.stat().st_mode & 0o222, "accepted raw stat/permission changed")
    require(checked["csv_sha256"] == CSV_SHA and validation["source_after_sha256"] == CSV_SHA,
            "accepted raw hash evidence mismatch")
    require(sha(ROOT/"data/manifest.json") == checked["manifest_sha256"] and
            sha(ROOT/".local/t04/criteo_v2_1/registry.json") == checked["registry_sha256"],
            "source registration changed")
    member = ROOT/split["membership"]["local_relative_path"]
    require(member.stat().st_size == split["membership"]["compressed_bytes"]
            and not member.stat().st_mode & 0o222, "membership stat/permission mismatch")
    profile = {}
    with (ROOT/"reports/criteo_source_profile.csv").open() as f:
        for row in csv.DictReader(f):
            if row["field"] in ("treatment", *METRICS):
                profile[row["field"]] = {"0": int(row["zero_count"]), "1": int(row["one_count"]),
                                         "invalid": int(row["invalid_binary_count"])}
    require(profile == entry["profile"]["binary_counts"], "source profile file disagrees")
    require(all(counts["invalid"] == 0 for counts in profile.values()), "source profile contains invalid labels")
    profile = {field: {k: counts[k] for k in ("0", "1")} for field, counts in profile.items()}
    return raw, member, profile


def worker(args, run):
    from pyspark.sql import SparkSession
    spark = SparkSession.builder.appName("T3.2 synthetic" if args.test else "T3.2 overall ITT").getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    spark.conf.set("spark.sql.csv.parser.columnPruning.enabled", "false")
    started = time.monotonic()
    try:
        require(spark.sparkContext.master == "local[4]" and spark.conf.get("spark.driver.memory") == "4g"
                and spark.conf.get("spark.sql.session.timeZone") == "UTC", "runtime settings mismatch")
        if args.test:
            import unittest
            import tests.test_criteo_ate as test_module
            test_module.SPARK = spark
            suite = unittest.defaultTestLoader.loadTestsFromModule(test_module)
            result = unittest.TextTestRunner(verbosity=2).run(suite)
            require(result.wasSuccessful(), "synthetic tests failed")
            output = dict(status="passed", tests=result.testsRun, kind="synthetic",
                          code_sha256=sha(Path(__file__)), tests_sha256=sha(ROOT/"tests/test_criteo_ate.py"))
        else:
            raw, member, profile = source_metadata()
            before = {"raw": file_state(raw), "membership": file_state(member)}
            groups = aggregate_csv(spark, raw)
            require({str(r["treatment"]): r["n"] for r in groups} == profile["treatment"], "arm count mismatch")
            require(all(sum(r[m+"_count"] for r in groups) == profile[m]["1"] for m in METRICS),
                    "source outcome total mismatch")
            table = effects(groups)
            independent = independent_formula_check(groups, table)
            require(effects(groups) == table, "repeat two-row effect calculation mismatch")
            after = {"raw": file_state(raw), "membership": file_state(member)}
            require(before == after, "raw or membership metadata changed during execution")
            with (run/"criteo_effects.csv").open("x", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(table[0]), lineterminator="\n")
                writer.writeheader(); writer.writerows(table)
            output = dict(status="passed", run_id=args.run_id, version=VERSION,
                          source_id=SOURCE_ID, source_sha256=CSV_SHA, groups=groups,
                          independent_formula=independent, source_profile_reconciled=True,
                          cached_summary_repeat=True, effect_recalculation_repeat=True,
                          raw_and_membership_stat_before=before, raw_and_membership_stat_after=after,
                          hash_evidence="T0.4/T3.1 accepted full SHA; reused, not rehashed in T3.2",
                          real_csv_scans=1, input_bytes=raw.stat().st_size,
                          spark_version=spark.version, java_version=spark._jvm.java.lang.System.getProperty("java.version"),
                          python_version=sys.version.split()[0], master=spark.sparkContext.master,
                          driver_memory=spark.conf.get("spark.driver.memory"), timezone="UTC")
        output["worker_elapsed_seconds"] = round(time.monotonic()-started, 3)
    finally:
        spark.stop()
    output["spark_stopped"] = True
    write_json(run/"validation.json", output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runtime-config", default=str(ROOT/"config/local.yaml"))
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--synthetic-gate")
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", args.run_id), "invalid run id")
    run = ROOT/".local/t32"/args.run_id
    if args.worker:
        return worker(args, run)
    require(Path(sys.prefix) == ROOT/".venv" and sys.version_info[:2] == (3, 11), "project venv required")
    runtime = load_config(args.runtime_config, ROOT)
    import pyspark
    spark_home = Path(pyspark.__file__).resolve().parent
    require(pyspark.__version__ == "3.5.8" and spark_home.is_relative_to(ROOT/".venv"), "project Spark required")
    if not args.test:
        require(args.synthetic_gate, "synthetic gate required")
        gate = Path(args.synthetic_gate).resolve()
        require(gate.is_relative_to(ROOT/".local/t32") and gate.is_file(), "local synthetic receipt required")
        evidence = json.loads(gate.read_text())
        require(evidence["status"] == "passed" and evidence["kind"] == "synthetic"
                and evidence["code_sha256"] == sha(Path(__file__))
                and evidence["tests_sha256"] == sha(ROOT/"tests/test_criteo_ate.py"), "synthetic gate/code mismatch")
    run.mkdir(parents=True, exist_ok=False)
    temp = run/"temp"; temp.mkdir()
    conf = temp/"spark-conf"; conf.mkdir()
    props = conf/"spark-defaults.conf"; props.write_text("# isolated project settings\n")
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "SPARK_SUBMIT_OPTS", "JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS",
                "JDK_JAVA_OPTIONS", "SPARK_REMOTE", "SPARK_CONNECT_MODE_ENABLED"):
        env.pop(key, None)
    env.update(JAVA_HOME=str(runtime.java_home), SPARK_HOME=str(spark_home), SPARK_CONF_DIR=str(conf),
               TMPDIR=str(temp), SPARK_LOCAL_DIRS=str(temp), SPARK_LOCAL_IP="127.0.0.1", PYTHONNOUSERSITE="1", TZ="UTC",
               PYSPARK_PYTHON=str(runtime.python_executable), PYSPARK_DRIVER_PYTHON=str(runtime.python_executable))
    env["PATH"] = os.pathsep.join([str(runtime.python_executable.parent), str(runtime.java_home/"bin"), env.get("PATH", "")])
    command = [str(ROOT/".venv/bin/spark-submit"), "--master", "local[4]", "--driver-memory", "4g",
               "--properties-file", str(props), "--driver-java-options", '-Djava.io.tmpdir="'+str(temp)+'"']
    for key, value in {"spark.sql.shuffle.partitions": "32", "spark.sql.session.timeZone": "UTC",
                       "spark.driver.host": "127.0.0.1", "spark.driver.bindAddress": "127.0.0.1",
                       "spark.sql.warehouse.dir": (temp/"warehouse").as_uri(), "spark.ui.enabled": "false",
                       "spark.sql.catalogImplementation": "in-memory"}.items():
        command.extend(["--conf", key+"="+value])
    command += [str(Path(__file__).resolve()), *sys.argv[1:], "--worker"]
    started = time.monotonic(); minimum_free = shutil.disk_usage(ROOT).free; process = None
    def budget():
        nonlocal minimum_free
        minimum_free = min(minimum_free, shutil.disk_usage(ROOT).free)
        used = sum(p.stat().st_size for p in (ROOT/".local/t32").rglob("*") if p.is_file())
        require(used < 1024**3 and minimum_free >= 150*1024**3, "T3.2 resource budget exceeded")
        return used
    receipt = dict(status="running", run_id=args.run_id, started_utc=datetime.now(timezone.utc).isoformat())
    try:
        budget()
        with (run/"spark.log").open("x") as log:
            process = subprocess.Popen(command, env=env, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            while process.poll() is None:
                budget()
                try: process.wait(timeout=2)
                except subprocess.TimeoutExpired: pass
        require(process.returncode == 0, "worker failed; local log retained")
        receipt["status"] = "passed"
        receipt["local_tree_bytes"] = budget()
    except BaseException as exc:
        if process and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try: process.wait(timeout=10)
            except subprocess.TimeoutExpired: os.killpg(process.pid, signal.SIGKILL); process.wait()
        receipt.update(status="failed", error=str(exc))
        raise
    finally:
        receipt.update(elapsed_seconds=round(time.monotonic()-started, 3), minimum_free_sampled_bytes=minimum_free,
                       peak_memory="not_measured")
        write_json(run/"launch.json", receipt)
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
