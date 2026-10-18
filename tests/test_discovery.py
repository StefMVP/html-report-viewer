"""Discovery must return visible reports consistently with or without rg."""

from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from report_viewer import discovery


class DiscoveryTests(unittest.TestCase):
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
