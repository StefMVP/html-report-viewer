"""A runtime version must change with discovery behavior."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from report_viewer import runtime


class RuntimeTests(unittest.TestCase):
    def test_paths_and_discovery_rules_change_the_runtime_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("app.py", "paths.py", "index.html", "discovery.ignore"):
                (root / name).write_text(name)
            with patch.object(runtime, "__file__", str(root / "runtime.py")):
                previous = runtime.version()
                for name in ("paths.py", "discovery.ignore"):
                    (root / name).write_text(name + "\nchanged")
                    current = runtime.version()
                    self.assertNotEqual(current, previous)
                    previous = current

    def test_new_ui_modules_change_the_runtime_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("app.py", "paths.py", "index.html", "discovery.ignore"):
                (root / name).write_text(name)
            with patch.object(runtime, "__file__", str(root / "runtime.py")):
                first = runtime.version()
                (root / "export.mjs").write_text("export function example() {}")
                self.assertNotEqual(runtime.version(), first)


if __name__ == "__main__":
    unittest.main()
