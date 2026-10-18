"""Help and invalid configuration must have useful CLI results."""

from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest

from report_viewer import app


class StartupTests(unittest.TestCase):
    def test_help_does_not_depend_on_saved_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "remote-access.json").write_text("{broken")
            with (
                redirect_stdout(io.StringIO()),
                self.assertRaises(SystemExit) as result,
            ):
                app.main(["--state-dir", directory, "--help"])
            self.assertEqual(result.exception.code, 0)

    def test_invalid_saved_configuration_has_a_cli_error(self):
        for content in ("{broken", "[]", '{"viewer_origin":42}'):
            with (
                self.subTest(content=content),
                tempfile.TemporaryDirectory() as directory,
            ):
                (Path(directory) / "remote-access.json").write_text(content)
                error = io.StringIO()
                with redirect_stderr(error), self.assertRaises(SystemExit) as result:
                    app.main(["--state-dir", directory])
                self.assertEqual(result.exception.code, 2)
                self.assertIn("remote-access.json", error.getvalue())
