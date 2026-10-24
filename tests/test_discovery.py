"""Discovery must return visible reports consistently with or without rg."""

import os
from pathlib import Path
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch

from report_viewer import discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        config_home = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.dict("os.environ", {"XDG_CONFIG_HOME": config_home}))

    def test_age_filter_runs_before_path_resolution_and_keeps_old_pins(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("recent.html", "old.html", "pinned.html"):
                (root / name).write_text("<title>Example</title>")
            old_time = time.time() - 86400
            for name in ("old.html", "pinned.html"):
                os.utime(root / name, (old_time, old_time))
            rg = shutil.which("rg")
            for executable in [None] + ([rg] if rg else []):
                with (
                    self.subTest(scanner=executable or "os.walk"),
                    patch.object(discovery.shutil, "which", return_value=executable),
                    patch.object(discovery, "CACHE", {"time": 0}),
                    patch.object(discovery, "HEAD_CACHE", {}),
                    patch.object(
                        discovery, "resolve_visible", wraps=discovery.resolve_visible
                    ) as resolve,
                ):
                    rows, warnings = discovery.scan(
                        root, days=2 / 24, pins=frozenset({"pinned.html"})
                    )
                    self.assertEqual(warnings, 0)
                    self.assertEqual(
                        {row["path"] for row in rows}, {"recent.html", "pinned.html"}
                    )
                    self.assertNotIn(
                        Path("old.html"), [call.args[1] for call in resolve.call_args_list]
                    )
                    rows, _ = discovery.scan(root, days=0)
                    self.assertEqual(
                        {row["path"] for row in rows},
                        {"recent.html", "old.html", "pinned.html"},
                    )
                    rows, _ = discovery.scan(root, days=2 / 24)
                    self.assertEqual({row["path"] for row in rows}, {"recent.html"})

    def test_discovery_stays_on_the_root_filesystem(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "local.html").write_text("<title>Local</title>")
            mounted = root / "mounted"
            mounted.mkdir()
            (mounted / "external.html").write_text("<title>Other disk</title>")
            real_stat = os.stat
            root_device = root.stat().st_dev

            def device_stat(path, *args, **kwargs):
                self.assertNotEqual(Path(path), mounted / "external.html")
                result = real_stat(path, *args, **kwargs)
                if Path(path).is_relative_to(mounted):
                    values = list(result)
                    values[2] = root_device + 1
                    return os.stat_result(values)
                return result

            with (
                patch.object(discovery.shutil, "which", return_value=None),
                patch.object(discovery.os, "stat", side_effect=device_stat),
            ):
                self.assertEqual(discovery.html_files(root), [root / "local.html"])

    def test_rg_stays_on_one_filesystem(self):
        if not shutil.which("rg"):
            self.skipTest("rg is not installed")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                discovery.subprocess, "run", wraps=discovery.subprocess.run
            ) as run,
        ):
            discovery.html_files(Path(directory))
            self.assertIn("--one-file-system", run.call_args.args[0])

    def test_source_files_are_separate_from_reports_in_worktrees(self):
        source = {
            ".worktrees/example-feature/site/templates/login.html",
            ".worktrees/example-feature/app/tests/golden/invoice.html",
            "project/TESTS/fixtures/report.html",
            "project/__tests__/page.html",
            "project/__fixtures__/report.html",
            "project/__snapshots__/report.html",
            "project/template/report.html",
            "project/test/report.html",
            "project/fixture/report.html",
            "project/goldens/report.html",
        }
        reports = {
            ".worktrees/example-feature/reports/test-results.html",
            ".worktrees/example-feature/scripts/performance/report.html",
            "reports/templates-audit.html",
        }
        pages = {"project/testing-notes.html", "project/test-portal/page.html"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in source | reports | pages:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                # Fixtures can be copies of reports, including their metadata.
                metadata = (
                    '<meta name="report:title" content="Example">'
                    if name in source
                    else ""
                )
                target.write_text(f"<head><title>Example</title>{metadata}</head>")
            rg = shutil.which("rg")
            for executable in [None] + ([rg] if rg else []):
                with self.subTest(scanner=executable or "os.walk"):
                    with (
                        patch.object(
                            discovery.shutil, "which", return_value=executable
                        ),
                        patch.object(discovery, "CACHE", {"time": 0}),
                        patch.object(discovery, "HEAD_CACHE", {}),
                    ):
                        rows, warnings = discovery.scan(root, days=0)
                    self.assertEqual(warnings, 0)
                    self.assertEqual(
                        {r["path"] for r in rows if r["kind"] == "Code and tests"},
                        source,
                    )
                    self.assertEqual(
                        {r["path"] for r in rows if r["kind"] == "Report"}, reports
                    )
                    self.assertEqual(
                        {r["path"] for r in rows if r["kind"] == "HTML"}, pages
                    )

    def test_visible_ignored_reports_and_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = {
                "reports/ignored.html",
                "nested/REPORT.HTML",
                "page.htm",
                "PAGE.HTM",
                "Mixed.HtMl",
                ".worktrees/example-feature/reports/report.html",
                "nested/.worktrees/feature/report.HTM",
            }
            excluded = {
                ".hidden.html",
                "reports/.hidden.htm",
                ".config/page.html",
                "nested/.private/page.html",
                "node_modules/page.html",
                "nested/.venv/page.html",
                "nested/venv/page.html",
                ".worktrees/example-feature/.private/secret.html",
                ".worktrees/example-feature/reports/.hidden.html",
                ".worktrees/example-feature/node_modules/page.html",
                ".worktrees/.private/reports/secret.html",
            }
            for name in expected | excluded:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("<title>Discovery fixture</title>")
            (root / ".gitignore").write_text("reports/\n")
            (root / "linked").symlink_to(root / "reports", target_is_directory=True)
            rg = shutil.which("rg")
            for executable in [None] + ([rg] if rg else []):
                with self.subTest(scanner=executable or "os.walk"):
                    with patch.object(
                        discovery.shutil, "which", return_value=executable
                    ):
                        observed = {
                            p.relative_to(root).as_posix()
                            for p in discovery.html_files(root)
                        }
                    self.assertEqual(observed, expected)

    def test_symlink_targets_follow_the_same_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                ".private/secret.html",
                "node_modules/secret.html",
                "public.html",
            ):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("<title>Example</title>")
            (root / "hidden-alias.html").symlink_to(root / ".private/secret.html")
            (root / "dependency-alias.html").symlink_to(
                root / "node_modules/secret.html"
            )
            (root / "public-alias.html").symlink_to(root / "public.html")
            with (
                patch.object(discovery, "CACHE", {"time": 0}),
                patch.object(discovery, "HEAD_CACHE", {}),
            ):
                rows, _ = discovery.scan(root, days=0)
            self.assertEqual({row["path"] for row in rows}, {"public.html"})

    def test_deleted_metadata_is_removed_after_rescan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.html"
            report.write_text("<title>Example</title>")
            with (
                patch.object(discovery, "CACHE", {"time": 0}),
                patch.object(discovery, "HEAD_CACHE", {}),
            ):
                discovery.scan(root, days=0)
                self.assertIn(report, discovery.HEAD_CACHE)
                report.unlink()
                discovery.CACHE["time"] = 0
                rows, _ = discovery.scan(root, days=0)
                self.assertEqual(rows, [])
                self.assertNotIn(report, discovery.HEAD_CACHE)


if __name__ == "__main__":
    unittest.main()
