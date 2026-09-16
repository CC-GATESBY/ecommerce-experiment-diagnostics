"""Sample cumulative local output bytes, including retained runs and temporary files."""

import json
from pathlib import Path
import shutil


def directory_bytes(root):
    size = 0
    for path in Path(root).rglob('*'):
        try:
            if path.is_file():
                size += path.stat().st_size
        except FileNotFoundError:
            pass  # Spark may remove a temporary file between listing and stat.
    return size


class Budget:
    def __init__(self, root, source):
        self.root = Path(root) / '.local/t11'
        self.config = json.loads(Path(source).read_text())
        if (set(self.config) != {'initial_bytes', 'max_new_bytes', 'minimum_free_bytes'}
                or any(type(v) is not int or v < 0 for v in self.config.values())
                or not 0 < self.config['max_new_bytes'] <= 20 * 1024**3
                or self.config['minimum_free_bytes'] < 150 * 1024**3):
            raise ValueError('invalid budget; cap <=20 GiB and reserve >=150 GiB required')
        self.peak_new_bytes = 0
        self.minimum_free_observed = shutil.disk_usage(self.root).free
        self.samples = 0

    def check(self):
        new = max(0, directory_bytes(self.root) - self.config['initial_bytes'])
        free = shutil.disk_usage(self.root).free
        self.peak_new_bytes = max(self.peak_new_bytes, new)
        self.minimum_free_observed = min(self.minimum_free_observed, free)
        self.samples += 1
        if new > self.config['max_new_bytes'] or free < self.config['minimum_free_bytes']:
            raise RuntimeError('resource budget exceeded; stop without publishing partial input')
        return new

    def summary(self):
        return dict(self.config, sampled_peak_new_bytes=self.peak_new_bytes,
                    minimum_free_observed_bytes=self.minimum_free_observed, samples=self.samples,
                    sampling='every 10000 oracle records and at most 2 seconds while Spark runs')
