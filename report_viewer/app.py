#!/usr/bin/env python3
"""Browse local HTML reports with a separate preview origin."""

import argparse
import json
import math
import os
import re
from pathlib import Path
import threading
import secrets
import hmac
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlsplit
from .runtime import version as runtime_version
from .paths import resolve_visible
from .discovery import scan

APP = Path(__file__).resolve().parent
ROOT = Path.cwd()
UI_ASSETS = {
    "viewer.mjs",
    "state.mjs",
    "export.mjs",
    "styles.css",
    "vendor/es-module-lexer.mjs",
}
# Internet sites usually refuse frames, so framed reports open them in a new tab.
LINK_SCRIPT = b"""<script>
addEventListener("click", (event) => {
  const link = event.target.closest?.("a[href]");
  if (top === self || !(link instanceof HTMLAnchorElement) || event.defaultPrevented) return;
  if (event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
  if ((link.target && link.target !== "_self") || link.hasAttribute("download")) return;
  const url = new URL(link.href);
  if (!/^https?:$/.test(url.protocol) || url.origin === location.origin) return;
  if (["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)) return;
  event.preventDefault();
  window.open(link.href, "_blank", "noopener");
});
</script>
"""


def https_origin(value):
    """A configured reverse-proxy origin, without credentials or a path."""
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Remote origins must be HTTPS origins without a path or credentials."
        )
    return "https://" + parsed.netloc


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".wav": "audio/wav"}

    def send_error(self, code, message=None, explain=None):
        # Reject with no reflected path, reason detail, filesystem clue or banner.
        self.send_response_only(404)
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def request_origin(self):
        remote = getattr(self.server, "remote_origin", "")
        if remote and self.headers.get("Host") == urlsplit(remote).netloc:
            return remote
        return "http://" + self.headers.get("Host", "")

    def local_request(self):
        hosts = {
            f"127.0.0.1:{self.server.server_port}",
            f"localhost:{self.server.server_port}",
        }
        remote = getattr(self.server, "remote_origin", "")
        host = self.headers.get("Host")
        if len(self.headers.get_all("Host", [])) != 1:
            return False
        if remote and host == urlsplit(remote).netloc:
            # Both listeners bind loopback. Only the local Tailscale proxy can supply
            # this identity to a remote browser; knowing the hostname grants nothing.
            owner = getattr(self.server, "trusted_user", "")
            if not owner or self.headers.get_all("Tailscale-User-Login", []) != [owner]:
                return False
        elif host not in hosts:
            return False
        if self.headers.get("Sec-Fetch-Site") not in ("cross-site", "same-site"):
            return True
        if getattr(self.server, "preview_only", False):
            if (
                urlsplit(self.path).path.startswith("/files/")
                and self.headers.get("Sec-Fetch-Mode") == "navigate"
                and self.headers.get("Sec-Fetch-Dest") in ("document", "iframe")
            ):
                # frame-ancestors still limits which pages can show a report.
                return True
            ref = urlsplit(self.headers.get("Referer", ""))
            return (ref.scheme + "://" + ref.netloc) in self.server.viewer_origins
        # An ordinary link from another site may open the viewer, but a
        # report iframe cannot fetch the viewer's controls or token cross-origin.
        return (
            urlsplit(self.path).path in ("/", "/index.html")
            and self.headers.get("Sec-Fetch-Mode") == "navigate"
            and self.headers.get("Sec-Fetch-Dest") == "document"
        )

    def authorized(self):
        token = self.headers.get("X-Viewer-Token", "")
        return self.local_request() and hmac.compare_digest(
            token, self.server.viewer_token
        )

    def do_POST(self):
        self.send_error(405)

    def do_GET(self):
        if not self.local_request():
            self.send_error(403)
            return
        url = urlsplit(self.path)
        if getattr(self.server, "preview_only", False) and not url.path.startswith(
            "/files/"
        ):
            self.send_error(404)
            return
        if url.path.startswith("/assets/"):
            name = url.path[len("/assets/") :]
            if name not in UI_ASSETS:
                self.send_error(404)
                return
            body = (APP / name).read_bytes()
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/css" if name.endswith(".css") else "text/javascript",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if url.path in ("/", "/index.html"):
            nonce = self.server.viewer_token
            preview_origin = (
                getattr(self.server, "remote_preview_origin", "")
                if self.request_origin().startswith("https:")
                else self.server.preview_origin
            )
            page = (APP / "index.html").read_text()
            page = page.replace(
                "<script>",
                '<script nonce="'
                + nonce
                + '">const viewerToken='
                + json.dumps(nonce)
                + ";const previewOrigin="
                + json.dumps(preview_origin)
                + ";",
                1,
            )
            page = page.replace(
                '<script type="module"', '<script nonce="' + nonce + '" type="module"'
            )
            body = page.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'nonce-"
                + nonce
                + "'; style-src 'self'; img-src 'self' data:; frame-src http: https:"
                + " blob:; connect-src 'self' http: https:; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)
            return
        if url.path == "/api/health":
            self.send_json(
                200,
                {
                    "app": "workspace-report-viewer",
                    "root": str(ROOT),
                    "previousRoot": getattr(self.server, "previous_root", None),
                    "version": getattr(self.server, "version", "test"),
                },
            )
            return
        if url.path == "/api/reports":
            if not self.authorized():
                self.send_error(403)
                return
            try:
                query = parse_qs(url.query)
                days = float(query.get("days", ["3"])[0])
                if not math.isfinite(days) or days < 0 or days > 36500:
                    raise ValueError("Days must be between 0 and 36500.")
                pins = frozenset(query.get("pin", []))
                rows, warnings = scan(ROOT, days, pins)
                cutoff = time.time() - days * 86400 if days else 0
                rows = [r for r in rows if r["modified"] >= cutoff or r["path"] in pins]
                self.send_json(
                    200,
                    {"reports": rows, "scannedAt": time.time(), "warnings": warnings},
                )
            except ValueError as error:
                self.send_json(400, {"error": str(error)})
            except Exception as error:
                self.send_json(500, {"error": str(error)})
            return
        if not url.path.startswith("/files/"):
            self.send_error(404)
            return
        else:
            relative = unquote(url.path[len("/files/") :])
            candidate = resolve_visible(ROOT, Path(relative))
            if candidate is None or not candidate.is_file():
                self.send_error(404)
                return
            self.path = "/" + quote(candidate.relative_to(ROOT).as_posix())
        self.serving_report = True
        if getattr(self.server, "preview_only", False) and candidate.suffix.lower() in (
            ".html",
            ".htm",
        ):
            body = candidate.read_bytes() + LINK_SCRIPT
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def do_HEAD(self):
        self.send_error(405)

    def send_json(self, status, value):
        payload = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Referrer-Policy",
            "origin"
            if urlsplit(self.path).path in ("/", "/index.html")
            else "no-referrer",
        )
        if getattr(self, "serving_report", False):
            if getattr(self.server, "preview_only", False):
                ancestors = " ".join(self.server.viewer_origins)
                self.send_header(
                    "Content-Security-Policy",
                    "sandbox allow-scripts allow-same-origin allow-popups"
                    + " allow-popups-to-escape-sandbox; frame-ancestors 'self' "
                    + ancestors
                    + "; base-uri 'none'; form-action 'none'",
                )
            else:
                self.send_header(
                    "Content-Security-Policy",
                    "sandbox allow-scripts; frame-ancestors 'self'; base-uri 'none'; form-action 'none'",
                )
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404)


def main(argv=None):
    global ROOT
    defaults = argparse.ArgumentParser(add_help=False)
    defaults.add_argument(
        "--state-dir",
        type=Path,
        default=Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
        / "report-viewer",
    )
    parser = argparse.ArgumentParser(description=__doc__, parents=[defaults])
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Folder to discover local HTML reports in",
    )
    parser.add_argument(
        "--previous-root",
        type=Path,
        help="Previous discovery root for migrating saved browser paths when expanding the root",
    )
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--preview-port", type=int, default=8768)
    parser.add_argument("--viewer-origin")
    parser.add_argument("--preview-origin")
    parser.add_argument("--trusted-user")
    args = parser.parse_args(argv)
    state = args.state_dir.expanduser().resolve()
    remote_file = state / "remote-access.json"
    try:
        remote = json.loads(remote_file.read_text()) if remote_file.exists() else {}
        if not isinstance(remote, dict):
            raise ValueError
        for name in ("viewer_origin", "preview_origin", "trusted_user"):
            value = remote.get(name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError
            if getattr(args, name) is None:
                setattr(args, name, value)
    except (OSError, ValueError):
        parser.error("Cannot read valid settings from remote-access.json")
    if any((args.viewer_origin, args.preview_origin, args.trusted_user)):
        if not all((args.viewer_origin, args.preview_origin, args.trusted_user)):
            parser.error(
                "Remote access requires viewer-origin, preview-origin and trusted-user together"
            )
        try:
            args.viewer_origin = https_origin(args.viewer_origin)
            args.preview_origin = https_origin(args.preview_origin)
        except ValueError as error:
            parser.error(str(error))
        if args.viewer_origin == args.preview_origin:
            parser.error("Viewer and HTML preview must use separate origins")
    ROOT = args.root.expanduser().resolve(strict=True)
    if not ROOT.is_dir():
        parser.error("--root must be a directory")
    previous_root = (
        args.previous_root.expanduser().resolve() if args.previous_root else None
    )
    if previous_root and not previous_root.is_relative_to(ROOT):
        parser.error("--previous-root must be inside --root")
    if (
        not all(1 <= port <= 65535 for port in (args.port, args.preview_port))
        or args.port == args.preview_port
    ):
        parser.error("Viewer and preview require different ports between 1 and 65535")
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    token_file = state / "viewer-token"
    if not token_file.exists():
        fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as target:
            target.write(secrets.token_urlsafe(32))
    token = token_file.read_text().strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
        raise RuntimeError("Invalid local viewer token; refusing startup.")
    os.chdir(ROOT)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    preview_server = ThreadingHTTPServer(("127.0.0.1", args.preview_port), Handler)
    preview_server.preview_only = True
    preview_server.viewer_origins = [
        f"http://localhost:{args.port}",
        f"http://127.0.0.1:{args.port}",
    ]
    server.preview_origin = f"http://127.0.0.1:{preview_server.server_port}"
    if args.viewer_origin:
        server.remote_origin = args.viewer_origin
        server.remote_preview_origin = args.preview_origin
        server.trusted_user = preview_server.trusted_user = args.trusted_user
        preview_server.remote_origin = args.preview_origin
        preview_server.viewer_origins.append(args.viewer_origin)
    threading.Thread(target=preview_server.serve_forever, daemon=True).start()
    server.viewer_token = token
    server.previous_root = str(previous_root) if previous_root else None
    server.version = runtime_version()
    print(f"Report viewer: http://localhost:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        preview_server.shutdown()
        preview_server.server_close()
        server.server_close()


if __name__ == "__main__":
    main()
