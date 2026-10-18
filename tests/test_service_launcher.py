"""Configured service ports must survive restart and drive the health check."""

from contextlib import redirect_stdout
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from report_viewer.runtime import version

SOURCE = Path(__file__).resolve().parents[1] / "scripts/report-viewer-service"
LOADER = importlib.machinery.SourceFileLoader("service_launcher", str(SOURCE))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
launcher = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(launcher)


class ServiceTests(unittest.TestCase):
    def test_custom_ports_and_root_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "reports with % sign"
            root.mkdir()
            payload = json.dumps(
                {
                    "app": "workspace-report-viewer",
                    "root": str(root),
                    "version": version(),
                }
            ).encode()
            with (
                patch.dict(os.environ, {"XDG_CONFIG_HOME": str(base / "config")}),
                patch.object(
                    launcher.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ),
                patch.object(
                    launcher,
                    "urlopen",
                    side_effect=lambda *a, **kw: io.BytesIO(payload),
                ) as health,
                redirect_stdout(io.StringIO()),
            ):
                with patch.object(
                    sys,
                    "argv",
                    [
                        "service",
                        "start",
                        "--root",
                        str(root),
                        "--port",
                        "15520",
                        "--preview-port",
                        "15522",
                    ],
                ):
                    launcher.main()
                unit = base / "config/systemd/user/report-viewer.service"
                content = unit.read_text()
                self.assertIn("--port 15520 --preview-port 15522", content)
                self.assertIn("reports with %% sign", content)
                with patch.object(sys, "argv", ["service", "restart"]):
                    launcher.main()
                self.assertEqual(unit.read_text(), content)
                self.assertEqual(health.call_count, 2)
                for call in health.call_args_list:
                    self.assertEqual(call.args[0], "http://127.0.0.1:15520/api/health")

    def test_health_rejects_a_different_root_or_runtime_version(self):
        for wrong in ({"root": "/different/reports"}, {"version": "old"}):
            with self.subTest(wrong=wrong), tempfile.TemporaryDirectory() as directory:
                base = Path(directory)
                payload = json.dumps(
                    {
                        "app": "workspace-report-viewer",
                        "root": str(base),
                        "version": version(),
                        **wrong,
                    }
                ).encode()
                with (
                    patch.dict(os.environ, {"XDG_CONFIG_HOME": str(base / "config")}),
                    patch.object(
                        launcher.subprocess,
                        "run",
                        return_value=subprocess.CompletedProcess([], 0),
                    ),
                    patch.object(
                        launcher,
                        "urlopen",
                        side_effect=lambda *a, **kw: io.BytesIO(payload),
                    ),
                    patch.object(launcher.time, "sleep"),
                    redirect_stdout(io.StringIO()),
                    patch.object(
                        sys, "argv", ["service", "start", "--root", str(base)]
                    ),
                    self.assertRaises(SystemExit),
                ):
                    launcher.main()

    def test_restart_selects_this_checkout_and_keeps_the_saved_root(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            unit = base / "config/systemd/user/report-viewer.service"
            unit.parent.mkdir(parents=True)
            unit.write_text(
                f'[Service]\nExecStart=/old/checkout/python --root "{base}" --port 15520 --preview-port 15522\n'
            )
            payload = json.dumps(
                {
                    "app": "workspace-report-viewer",
                    "root": str(base),
                    "version": version(),
                }
            ).encode()
            with (
                patch.dict(os.environ, {"XDG_CONFIG_HOME": str(base / "config")}),
                patch.object(
                    launcher.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess([], 0),
                ),
                patch.object(
                    launcher,
                    "urlopen",
                    side_effect=lambda *a, **kw: io.BytesIO(payload),
                ),
                redirect_stdout(io.StringIO()),
                patch.object(sys, "argv", ["service", "restart"]),
            ):
                launcher.main()
            self.assertNotIn("/old/checkout", unit.read_text())
            self.assertIn(str(SOURCE.parent.parent), unit.read_text())
            settings = launcher.configured(unit)
            self.assertEqual(
                (settings.root, settings.port, settings.preview_port),
                (base, 15520, 15522),
            )


if __name__ == "__main__":
    unittest.main()
