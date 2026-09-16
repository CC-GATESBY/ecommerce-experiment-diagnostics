"""Strict, side-effect-free configuration for the local synthetic smoke."""

from dataclasses import dataclass
from pathlib import Path
import os

import yaml


class ConfigError(ValueError):
    """The supplied local configuration is incomplete or unsafe to run."""


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ConfigError("YAML keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


@dataclass(frozen=True)
class LocalConfig:
    source: Path
    python_executable: Path
    java_home: Path
    temp_root: Path
    warehouse_root: Path
    master: str
    driver_memory: str
    shuffle_partitions: int
    session_timezone: str


def _mapping(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise ConfigError(f"{label}: required keys are {', '.join(keys)}; unknown keys are rejected")
    return value


def _path(value, label, *, directory=True, writable=False):
    if not isinstance(value, str) or not value or value.isspace() or "<" in value or ">" in value:
        raise ConfigError(f"{label}: fill an absolute path; null/placeholder paths are invalid")
    # Do not strip whitespace: it may be part of the actual directory name.
    path = Path(value)
    if not path.is_absolute():
        raise ConfigError(f"{label}: absolute path required")
    access = os.R_OK | os.X_OK | (os.W_OK if writable else 0)
    if directory and (not path.is_dir() or not os.access(path, access)):
        raise ConfigError(f"{label}: existing accessible directory required")
    if not directory and (not path.is_file() or not os.access(path, os.X_OK)):
        raise ConfigError(f"{label}: existing executable required")
    return path


def load_config(source, project_root):
    source = Path(source)
    if not source.is_file():
        raise ConfigError("configuration file does not exist; no fallback is used")
    try:
        data = yaml.load(source.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot read valid YAML configuration: {exc}") from exc
    data = _mapping(data, ["profile", "runtime", "compute", "storage", "metrics"], "root")
    runtime = _mapping(data["runtime"], ["python_executable", "java_home"], "runtime")
    compute = _mapping(data["compute"], ["mode", "master", "driver_memory", "shuffle_partitions"], "compute")
    storage = _mapping(data["storage"], ["backend", "temp_root", "warehouse_root"], "storage")
    metrics = _mapping(data["metrics"], ["version", "session_timezone"], "metrics")
    required_values = [
        (data["profile"], "local", "profile"),
        (compute["mode"], "local", "compute.mode"),
        (compute["master"], "local[4]", "compute.master"),
        (compute["driver_memory"], "4g", "compute.driver_memory"),
        (compute["shuffle_partitions"], 32, "compute.shuffle_partitions"),
        (storage["backend"], "local", "storage.backend"),
        (metrics["version"], "v4.0", "metrics.version"),
        (metrics["session_timezone"], "UTC", "metrics.session_timezone"),
    ]
    for actual, expected, label in required_values:
        if type(actual) is not type(expected) or actual != expected:
            raise ConfigError(f"{label}: this T0.3 smoke requires {expected!r}")
    root = Path(project_root).resolve()
    python = _path(runtime["python_executable"], "runtime.python_executable", directory=False)
    python = python.parent.resolve() / python.name
    if python != root / ".venv/bin/python":
        raise ConfigError("runtime.python_executable must be this project's .venv/bin/python")
    java = _path(runtime["java_home"], "runtime.java_home")
    _path(str(java / "bin/java"), "runtime.java_home/bin/java", directory=False)
    temp = _path(storage["temp_root"], "storage.temp_root", writable=True).resolve()
    output = _path(storage["warehouse_root"], "storage.warehouse_root", writable=True).resolve()
    local = root / ".local"
    for path in (temp, output):
        if path == local or not path.is_relative_to(local):
            raise ConfigError("smoke storage must be inside the ignored project .local directory")
    if temp.is_relative_to(output) or output.is_relative_to(temp):
        raise ConfigError("temporary and output directories must not overlap")
    return LocalConfig(source.resolve(), python, java, temp, output,
                       compute["master"], compute["driver_memory"],
                       compute["shuffle_partitions"], metrics["session_timezone"])
