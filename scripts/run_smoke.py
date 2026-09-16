"""Launch the project venv's spark-submit after validation, before any JVM exists."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

from project_config import ConfigError, load_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--run-id")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        config = load_config(args.config, root)
        if sys.version_info[:2] != (3, 11) or Path(sys.prefix) != root / ".venv":
            raise ConfigError("launch with the project's Python 3.11 .venv/bin/python")
        import pyspark
        spark_home = Path(pyspark.__file__).resolve().parent
        submit = root / ".venv/bin/spark-submit"
        if pyspark.__version__ != "3.5.8" or not spark_home.is_relative_to(root / ".venv"):
            raise ConfigError("PySpark 3.5.8 must be installed in the project venv")
        if not submit.is_file() or not os.access(submit, os.X_OK):
            raise ConfigError("project venv spark-submit is missing")
        java = subprocess.run([str(config.java_home / "bin/java"), "-version"],
                              capture_output=True, text=True, check=True)
        if not re.search(r'version "17\.', java.stderr + java.stdout):
            raise ConfigError("configured JAVA_HOME must provide JDK 17")
        run_id = args.run_id or "smoke-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", run_id):
            raise ConfigError("run-id must be a simple directory name")
        output = config.warehouse_root / run_id
        temp = config.temp_root / run_id
        if output.exists() or temp.exists():
            raise ConfigError("run-id already exists; previous runs will not be overwritten")
        output.mkdir()
        temp.mkdir()
        conf_dir = temp / "spark-conf"
        conf_dir.mkdir()
        properties = conf_dir / "spark-defaults.conf"
        properties.write_text("# Intentionally empty: no external Spark defaults.\n")
        env = os.environ.copy()
        for key in ("PYTHONPATH", "PYTHONHOME", "SPARK_SUBMIT_OPTS", "JAVA_TOOL_OPTIONS",
                    "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "SPARK_REMOTE", "SPARK_CONNECT_MODE_ENABLED"):
            env.pop(key, None)
        env.update(JAVA_HOME=str(config.java_home), SPARK_HOME=str(spark_home),
                   SPARK_CONF_DIR=str(conf_dir), SPARK_LOCAL_DIRS=str(temp),
                   SPARK_LOCAL_IP="127.0.0.1", PYTHONNOUSERSITE="1", TZ="UTC",
                   PYSPARK_PYTHON=str(config.python_executable),
                   PYSPARK_DRIVER_PYTHON=str(config.python_executable))
        env["PATH"] = os.pathsep.join([str(config.python_executable.parent),
                                        str(config.java_home / "bin"), env.get("PATH", "")])
        command = [str(submit), "--master", config.master, "--driver-memory", config.driver_memory,
                   "--properties-file", str(properties)]
        settings = {"spark.sql.shuffle.partitions": str(config.shuffle_partitions),
                    "spark.sql.session.timeZone": config.session_timezone,
                    "spark.local.dir": str(temp), "spark.sql.warehouse.dir": output.as_uri(),
                    "spark.pyspark.python": str(config.python_executable),
                    "spark.pyspark.driver.python": str(config.python_executable),
                    "spark.driver.host": "127.0.0.1", "spark.driver.bindAddress": "127.0.0.1",
                    "spark.ui.enabled": "false", "spark.sql.catalogImplementation": "in-memory"}
        for key, value in settings.items():
            command += ["--conf", key + "=" + value]
        command += [str(root / "scripts/smoke_spark.py"), "--config", str(config.source), "--run-id", run_id]
        manifest = {"run_id": run_id, "status": "running", "command": command,
                    "config_sha256": hashlib.sha256(config.source.read_bytes()).hexdigest(),
                    "python": sys.version, "java_version_output": java.stderr.strip(),
                    "spark_home": str(spark_home), "started_at": datetime.now(timezone.utc).isoformat()}
        manifest_path = output / "launch.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        try:
            with (output / "spark.log").open("w") as log:
                result = subprocess.run(command, env=env, cwd=root, stdout=log, stderr=subprocess.STDOUT)
            manifest.update(returncode=result.returncode, status="passed" if result.returncode == 0 else "failed")
        except OSError as exc:
            manifest.update(returncode=1, status="failed", error=str(exc))
        manifest["finished_at"] = datetime.now(timezone.utc).isoformat()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps({"run_id": run_id, "status": manifest["status"], "local_output": str(output)}))
        return manifest["returncode"]
    except (ConfigError, OSError, subprocess.CalledProcessError) as exc:
        print(f"configuration/runtime error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
