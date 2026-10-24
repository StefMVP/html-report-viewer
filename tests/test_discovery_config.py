"""Local source patterns must stay outside the repository and reload on edits."""

import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from report_viewer import discovery


class DiscoveryConfigTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.root = self.directory / "workspace"
        self.root.mkdir()
        self.config_home = self.directory / "config"
        self.settings = self.config_home / "report-viewer" / "code-patterns"
        self.enterContext(patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config_home)}))
        self.enterContext(patch.object(discovery, "CACHE", {"time": 0}))
        self.enterContext(patch.object(discovery, "HEAD_CACHE", {}))

    def write_page(self, name, metadata=""):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"<head><title>Example</title>{metadata}</head>")

    def write_settings(self, content):
        self.settings.parent.mkdir(parents=True, exist_ok=True)
        self.settings.write_text(content)

    def kinds(self, pins=frozenset()):
        rows, warnings = discovery.scan(self.root, days=0, pins=pins)
        self.assertEqual(warnings, 0)
        return {row["path"]: row["kind"] for row in rows}

    def test_missing_settings_leave_app_pages_visible(self):
        self.write_page("example-app/ui/index.html")
        self.write_page("tests/fixture.html")
        self.assertEqual(self.kinds(), {
            "example-app/ui/index.html": "HTML",
            "tests/fixture.html": "Code and tests",
        })
        self.assertFalse(self.settings.exists())

    def test_local_patterns_match_worktrees_without_hiding_reports(self):
        self.write_settings("# Source page patterns\n\nEXAMPLE-APP/UI/*.HTML\ntoolbox/preview/*.html\n")
        source = {
            "example-app/ui/index.html",
            ".worktrees/feature-a/example-app/ui/index.html",
            "repo/.worktrees/feature-b/example-app/ui/PANEL.HTML",
            "reports/worktree-archive/saved/example-app/ui/index.html",
            "toolbox/preview/panel.html",
        }
        pages = {
            "example-app/ui-notes/index.html",
            "other-example-app/ui/index.html",
            "example-app/ui/nested/page.html",
        }
        for name in source:
            self.write_page(name, '<meta name="report:title" content="Example">')
        for name in pages | {"example-app/reports/results.html"}:
            self.write_page(name)
        expected = {name: "Code and tests" for name in source}
        expected.update({name: "HTML" for name in pages})
        expected["example-app/reports/results.html"] = "Report"
        rg = shutil.which("rg")
        for executable in [None] + ([rg] if rg else []):
            with self.subTest(scanner=executable or "os.walk"):
                discovery.CACHE["time"] = 0
                with patch.object(discovery.shutil, "which", return_value=executable):
                    self.assertEqual(self.kinds(), expected)

    def test_setting_edits_and_removal_invalidate_the_scan_cache(self):
        name = "example-app/ui/page.html"
        self.write_page(name)
        self.assertEqual(self.kinds()[name], "HTML")
        self.write_settings("example-app/ui/*.html\n")
        self.assertEqual(self.kinds()[name], "Code and tests")
        self.write_settings("another-app/ui/*.html\n")
        self.assertEqual(self.kinds()[name], "HTML")
        self.write_settings("example-app/ui/*.html\n")
        self.assertEqual(self.kinds()[name], "Code and tests")
        self.settings.unlink()
        self.assertEqual(self.kinds()[name], "HTML")

    def test_default_config_directory_is_under_the_users_home(self):
        self.write_page("example-app/ui/page.html")
        settings = self.directory / ".config/report-viewer/code-patterns"
        settings.parent.mkdir(parents=True)
        settings.write_text("example-app/ui/*.html\n")
        with patch.dict(os.environ), patch.object(Path, "home", return_value=self.directory):
            os.environ.pop("XDG_CONFIG_HOME", None)
            self.assertEqual(self.kinds()["example-app/ui/page.html"], "Code and tests")

    def test_ignore_patterns_hide_report_copies_and_reload(self):
        settings = self.settings.with_name("ignore-patterns")
        settings.parent.mkdir(parents=True)
        settings.write_text(
            "# Unwanted reports\n\nAPP/PERFORMANCE/REPORT.HTML\nfleet/status.html\n"
        )
        hidden = {
            "app/performance/report.html",
            "example-repo/.worktrees/example-main/.worktrees/example-feature/app/performance/REPORT.HTML",
            "knowledge/fleet/status.html",
            "archive/knowledge/fleet/status.html",
        }
        visible = {"app/reports/report.html", "fleet/results.html"}
        for name in hidden | visible:
            self.write_page(name)
        rg = shutil.which("rg")
        for executable in [None] + ([rg] if rg else []):
            with self.subTest(scanner=executable or "os.walk"):
                discovery.CACHE["time"] = 0
                with patch.object(discovery.shutil, "which", return_value=executable):
                    self.assertEqual(set(self.kinds(pins=frozenset(hidden))), visible)
        settings.write_text("fleet/status.html\n")
        self.assertEqual(
            set(self.kinds()), visible | {p for p in hidden if "performance" in p}
        )
        settings.unlink()
        self.assertEqual(set(self.kinds()), visible | hidden)
