"""Temporary loopback-only viewer with sample reports for browser checks."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import sys
import tempfile
import time
import wave

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from report_viewer import app as viewer


def populate_demo(root):
    source = APP / "tests/fixtures/demo"
    shutil.copytree(source / "assets", root / "assets")
    catalog = json.loads((source / "catalog.json").read_text())
    now = time.time()
    for item in catalog:
        destination = root / item["path"]
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((source / item["source"]).read_bytes())
        modified = now - item["minutes_ago"] * 60
        os.utime(destination, (modified, modified))


def populate_checks(root):
    shutil.copytree(APP / "tests/fixtures/export", root / "export")
    with wave.open(str(root / "export/tone.wav"), "wb") as sound:
        sound.setparams((1, 2, 8000, 800, "NONE", "not compressed"))
        sound.writeframes(bytes(1600))
    (root / "example.html").write_bytes(
        (APP / "tests/fixtures/report.html").read_bytes()
    )
    (root / "links.html").write_text(
        (APP / "tests/fixtures/links.html").read_text().replace("REPORT_ROOT", str(root))
    )
    (root / "notes-tool").write_text("#!/bin/sh\necho Notes tool \u2192 ok\n")
    (root / "older.html").write_text("<title>Older report</title><h1>Older report</h1>")
    os.utime(root / "older.html", (1, 1))
    (root / "recent.html").write_text(
        "<title>Recent report</title><h1>Recent report</h1>"
    )
    for name, title in [
        ("templates/login.html", "Portal template"),
        ("tests/golden/invoice.html", "Invoice fixture"),
        (".worktrees/feature-a/example-app/ui/index.html", "Application preview"),
        (".worktrees/feature-b/toolbox/preview/panel.html", "Tool preview"),
    ]:
        source = root / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(f"<title>{title}</title><h1>{title}</h1>")
    recent_time = (root / "example.html").stat().st_mtime - 60
    os.utime(root / "recent.html", (recent_time, recent_time))
    os.utime(root / "links.html", (recent_time - 45, recent_time - 45))
    for exported in (root / "export").rglob("*.html"):
        os.utime(exported, (recent_time - 30, recent_time - 30))
    for index in range(8):
        catalog = root / f"catalog-{index}.html"
        catalog.write_text(
            f"<title>Catalog report {index + 1}</title><h1>Catalog report {index + 1}</h1>"
        )
        modified = recent_time - (index + 1) * 60
        os.utime(catalog, (modified, modified))


parser = argparse.ArgumentParser(
    description=__doc__,
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""Open the printed viewer URL in a named Playwright CLI session.
Then run the browser checks:
  playwright-cli -s=SESSION run-code --filename tests/browser-check.js
  playwright-cli -s=SESSION run-code --filename tests/navigation-check.js
  playwright-cli -s=SESSION run-code --filename tests/open-preview-check.js
  playwright-cli -s=SESSION run-code --filename tests/source-filter-check.js
  playwright-cli -s=SESSION run-code --filename tests/export-check.js
  playwright-cli -s=SESSION run-code --filename tests/link-check.js

For the README screenshot, start this fixture with --demo, then run:
  playwright-cli -s=SESSION run-code --filename tests/capture-readme.js
The demo uses fictional projects and results. Stop the fixture with Ctrl+C.
""",
)
parser.add_argument(
    "--demo",
    action="store_true",
    help="Use fictional reports for the README screenshot",
)
options = parser.parse_args()

os.chdir(APP.parent)
with tempfile.TemporaryDirectory() as temporary:
    config_home = Path(temporary) / "config"
    os.environ["XDG_CONFIG_HOME"] = str(config_home)
    if not options.demo:
        settings = config_home / "report-viewer" / "code-patterns"
        settings.parent.mkdir(parents=True)
        settings.write_text("example-app/ui/*.html\ntoolbox/preview/*.html\n")
    root = Path(temporary) / "reports"
    root.mkdir()
    (populate_demo if options.demo else populate_checks)(root)
    viewer.ROOT = root
    os.chdir(root)
    server = viewer.ThreadingHTTPServer(("127.0.0.1", 0), viewer.Handler)
    import threading

    preview = viewer.ThreadingHTTPServer(("127.0.0.1", 0), viewer.Handler)
    preview.preview_only = True
    preview.viewer_origins = [f"http://127.0.0.1:{server.server_port}"]
    server.preview_origin = f"http://127.0.0.1:{preview.server_port}"
    threading.Thread(target=preview.serve_forever, daemon=True).start()
    server.viewer_token = secrets.token_urlsafe(32)
    addresses = {"viewer": f"http://127.0.0.1:{server.server_port}"}
    (APP / ".runtime").mkdir(exist_ok=True)
    (APP / ".runtime" / "browser-test.json").write_text(json.dumps(addresses))
    print(json.dumps(addresses), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        preview.shutdown()
        preview.server_close()
