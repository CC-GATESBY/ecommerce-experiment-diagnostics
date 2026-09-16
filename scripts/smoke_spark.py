"""Four synthetic rows only: environment, Parquet, SQL, Decimal and UTC checks."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import platform
import sys
import time

import pyspark
from pyspark.sql import SparkSession, functions as F, types as T

from project_config import load_config


def worker_probe(_):
    import platform
    import sys
    import pyspark
    return {"python": platform.python_version(), "executable": sys.executable,
            "prefix": sys.prefix, "pyspark": pyspark.__version__}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    config = load_config(args.config, root)
    output = config.warehouse_root / args.run_id
    temp = config.temp_root / args.run_id
    if output.parent != config.warehouse_root or temp.parent != config.temp_root:
        raise ValueError("run-id must remain inside its configured directory")
    if not output.is_dir() or not (output / "launch.json").is_file():
        raise ValueError("use run_smoke.py to configure the JVM before startup")
    receipt_path = output / "validation.json"
    if receipt_path.exists():
        raise FileExistsError("previous validation receipt must not be overwritten")
    receipt = {"run_id": args.run_id, "input_scope": "synthetic_only", "input_rows": 4,
               "status": "running", "checks": [], "spark_stopped": False,
               "config_sha256": hashlib.sha256(config.source.read_bytes()).hexdigest(),
               "started_at": datetime.now(timezone.utc).isoformat()}
    started = time.monotonic()
    spark = None

    def check(name, expected, actual):
        passed = expected == actual
        receipt["checks"].append({"name": name, "expected": expected, "actual": actual, "pass": passed})
        if not passed:
            raise AssertionError(f"{name}: expected {expected!r}, actual {actual!r}")

    try:
        spark = SparkSession.builder.appName("T0.3 synthetic smoke").getOrCreate()
        spark.sparkContext.setLogLevel("WARN")
        sc = spark.sparkContext
        versions = {"python_driver": platform.python_version(), "pyspark": pyspark.__version__,
                    "spark_jvm": sc._jsc.sc().version(),
                    "java": sc._jvm.java.lang.System.getProperty("java.version")}
        receipt["versions"] = versions
        check("python_major_minor", [3, 11], list(sys.version_info[:2]))
        check("driver_prefix", str(root / ".venv"), sys.prefix)
        check("driver_executable", str(config.python_executable), sys.executable)
        check("pyspark_version", "3.5.8", versions["pyspark"])
        check("spark_jvm_version", "3.5.8", versions["spark_jvm"])
        check("java_major", "17", versions["java"].split(".")[0])
        check("master", "local[4]", sc.master)
        check("driver_memory_config", "4g", sc.getConf().get("spark.driver.memory"))
        check("jvm_max_heap_bytes", 4 * 1024**3, sc._jvm.java.lang.Runtime.getRuntime().maxMemory())
        check("shuffle_partitions", "32", spark.conf.get("spark.sql.shuffle.partitions"))
        check("session_timezone", "UTC", spark.conf.get("spark.sql.session.timeZone"))
        check("catalog", "in-memory", spark.conf.get("spark.sql.catalogImplementation"))
        check("temporary_directory", str(temp), sc.getConf().get("spark.local.dir"))
        check("python_worker_setting", str(config.python_executable), sc.pythonExec)

        # Explicit values and independent literal expectations, not business events.
        rows = [(1, "A", Decimal("0.10"), "2026-09-16T10:00:00+10:00"),
                (2, "A", Decimal("0.20"), "2026-09-16T00:30:00Z"),
                (3, "B", Decimal("2.35"), "2026-09-15T23:00:00-01:00"),
                (4, "B", Decimal("1.05"), "2026-09-16T01:00:00Z")]
        schema = T.StructType([T.StructField("id", T.IntegerType(), True),
                               T.StructField("category", T.StringType(), True),
                               T.StructField("amount", T.DecimalType(10, 2), True),
                               T.StructField("timestamp_text", T.StringType(), True)])
        data = spark.createDataFrame(rows, schema).select(
            "id", "category", "amount", F.to_timestamp("timestamp_text", "yyyy-MM-dd'T'HH:mm:ssXXX").alias("event_time"))
        expected_schema = [("id", "int", True), ("category", "string", True),
                           ("amount", "decimal(10,2)", True), ("event_time", "timestamp", True)]
        actual_schema = lambda df: [(field.name, field.dataType.simpleString(), field.nullable) for field in df.schema]
        check("input_schema", expected_schema, actual_schema(data))
        check("input_count", 4, data.count())
        parquet = output / "parquet"
        data.write.mode("errorifexists").parquet(str(parquet))
        loaded = spark.read.parquet(str(parquet))
        check("parquet_schema", expected_schema, actual_schema(loaded))
        check("parquet_count", 4, loaded.count())
        # Collection is bounded to four artificial rows or two synthetic groups.
        check("parquet_row_values", data.orderBy("id").toJSON().collect(),
              loaded.orderBy("id").toJSON().collect())
        loaded.createOrReplaceTempView("synthetic_smoke")
        grouped = spark.sql("SELECT category, COUNT(*) AS n, SUM(amount) AS total FROM synthetic_smoke GROUP BY category ORDER BY category")
        actual = [{"category": row.category, "n": row.n, "total": str(row.total)} for row in grouped.collect()]
        check("sql_group_totals", [{"category": "A", "n": 2, "total": "0.30"},
                                    {"category": "B", "n": 2, "total": "3.40"}], actual)
        total = spark.sql("SELECT SUM(amount) AS total FROM synthetic_smoke").first().total
        check("decimal_total", "3.70", str(total))
        utc = spark.sql("SELECT id, date_format(event_time, 'yyyy-MM-dd HH:mm:ss') AS utc FROM synthetic_smoke ORDER BY id")
        check("utc_values", ["2026-09-16 00:00:00", "2026-09-16 00:30:00", "2026-09-16 00:00:00", "2026-09-16 01:00:00"], [row.utc for row in utc.collect()])
        workers = sc.parallelize([0, 1], 2).map(worker_probe).collect()
        expected_worker = {"python": platform.python_version(), "executable": str(config.python_executable),
                           "prefix": str(root / ".venv"), "pyspark": "3.5.8"}
        check("python_worker_environment", [expected_worker, expected_worker], workers)
        receipt["output_rows"] = 4
        receipt["status"] = "passed"
    except Exception as exc:
        receipt.update(status="failed", error=type(exc).__name__ + ": " + str(exc))
        raise
    finally:
        try:
            if spark is not None:
                spark.stop()
                receipt["spark_stopped"] = True
        except Exception as exc:
            receipt.update(status="failed", stop_error=str(exc))
            raise
        finally:
            receipt.update(finished_at=datetime.now(timezone.utc).isoformat(),
                           elapsed_seconds=time.monotonic() - started)
            receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
