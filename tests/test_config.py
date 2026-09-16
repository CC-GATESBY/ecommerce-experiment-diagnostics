"""Exercise invalid configuration and launch boundaries without starting Spark."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from project_config import ConfigError, load_config


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "project with trailing space "
        self.python = self.root / ".venv/bin/python"
        self.java = self.root / "jdk/bin/java"
        for executable in (self.python, self.java):
            executable.parent.mkdir(parents=True)
            executable.write_text("#!/bin/sh\nexit 0\n")
            executable.chmod(0o755)
        self.temp = self.root / ".local/temp"
        self.output = self.root / ".local/output"
        self.temp.mkdir(parents=True)
        self.output.mkdir()
        self.source = self.root / "local.yaml"
        self.data = {"profile": "local", "runtime": {"python_executable": str(self.python), "java_home": str(self.java.parent.parent)},
                     "compute": {"mode": "local", "master": "local[4]", "driver_memory": "4g", "shuffle_partitions": 32},
                     "storage": {"backend": "local", "temp_root": str(self.temp), "warehouse_root": str(self.output)},
                     "metrics": {"version": "v4.0", "session_timezone": "UTC"}}

    def write(self, data=None):
        self.source.write_text(yaml.safe_dump(self.data if data is None else data))

    def rejects(self, data):
        self.write(data)
        with self.assertRaises(ConfigError):
            load_config(self.source, self.root)

    def test_valid_paths_preserve_trailing_space(self):
        self.write()
        config = load_config(self.source, self.root)
        self.assertEqual(config.python_executable, self.python.parent.resolve() / self.python.name)
        self.assertEqual(config.warehouse_root, self.output.resolve())
        self.assertEqual(self.root.name[-1], " ")

    def test_missing_file_has_no_fallback(self):
        with self.assertRaises(ConfigError):
            load_config(self.source, self.root)

    def test_each_missing_root_field(self):
        for key in self.data:
            with self.subTest(key=key):
                data = deepcopy(self.data)
                del data[key]
                self.rejects(data)

    def test_each_missing_nested_field(self):
        for section in ("runtime", "compute", "storage", "metrics"):
            for key in self.data[section]:
                with self.subTest(section=section, key=key):
                    data = deepcopy(self.data)
                    del data[section][key]
                    self.rejects(data)

    def test_unknown_field_rejected(self):
        data = deepcopy(self.data)
        data["compute"]["driver_memroy"] = "4g"
        self.rejects(data)

    def test_all_null_paths_rejected(self):
        for section, key in [("runtime", "python_executable"), ("runtime", "java_home"),
                             ("storage", "temp_root"), ("storage", "warehouse_root")]:
            with self.subTest(key=key):
                data = deepcopy(self.data)
                data[section][key] = None
                self.rejects(data)

    def test_invalid_path_values(self):
        for value in ("", " ", "<PROJECT_ROOT>/temp", "relative/temp", "file:///tmp/data", str(self.root / "missing"), str(self.python)):
            with self.subTest(value=value):
                data = deepcopy(self.data)
                data["storage"]["temp_root"] = value
                self.rejects(data)

    def test_other_python_rejected(self):
        data = deepcopy(self.data)
        data["runtime"]["python_executable"] = str(self.java)
        self.rejects(data)

    def test_non_executable_python_rejected(self):
        self.python.chmod(0o644)
        self.rejects(self.data)

    def test_missing_java_executable_rejected(self):
        self.java.unlink()
        self.rejects(self.data)

    def test_same_or_nested_storage_rejected(self):
        child = self.output / "nested"
        child.mkdir()
        for path in (self.output, child, self.root / ".local"):
            with self.subTest(path=path):
                data = deepcopy(self.data)
                data["storage"]["temp_root"] = str(path)
                self.rejects(data)

    def test_storage_outside_ignored_area_rejected(self):
        outside = self.root / "not_ignored"
        outside.mkdir()
        data = deepcopy(self.data)
        data["storage"]["temp_root"] = str(outside)
        self.rejects(data)

    def test_symlink_escape_rejected(self):
        alias = self.root / ".local/escape"
        alias.symlink_to(Path(self.temporary.name), target_is_directory=True)
        data = deepcopy(self.data)
        data["storage"]["temp_root"] = str(alias)
        self.rejects(data)

    def test_unapproved_compute_or_metrics_rejected(self):
        changes = [("compute", "master", "local[*]"), ("compute", "driver_memory", "8g"),
                   ("compute", "shuffle_partitions", "32"), ("compute", "shuffle_partitions", True),
                   ("compute", "mode", "yarn"), ("storage", "backend", "hdfs"),
                   ("metrics", "session_timezone", "Australia/Melbourne"), ("metrics", "version", "v5")]
        for section, key, value in changes:
            with self.subTest(key=key, value=value):
                data = deepcopy(self.data)
                data[section][key] = value
                self.rejects(data)

    def test_invalid_yaml_and_non_mapping_rejected(self):
        for text in ("compute: [", "[]", "", "profile: local\nprofile: other\n", "!!python/object:os.system {}"):
            with self.subTest(text=text):
                self.source.write_text(text)
                with self.assertRaises(ConfigError):
                    load_config(self.source, self.root)

    def test_unfilled_repository_template_rejected(self):
        with self.assertRaises(ConfigError):
            load_config(ROOT / "config/local.example.yaml", ROOT)

    def test_launcher_rejects_missing_config_before_spark(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/run_smoke.py"), "--config", str(self.source)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("configuration file does not exist", result.stderr)
        self.assertNotIn("SparkContext", result.stderr)
        self.assertEqual(list(self.output.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
