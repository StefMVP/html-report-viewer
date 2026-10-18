"""Local catalog, preview isolation and removed routes."""

import functools
import http.client
import json
from pathlib import Path
import secrets
import tempfile
import threading
import unittest
from urllib.parse import quote


def request(port, path, method="GET", headers=None, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=8)
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    result = response.status, dict(response.getheaders()), response.read()
    conn.close()
    return result


class LocalAPITests(unittest.TestCase):
    def test_sharing_routes_are_removed_even_for_the_owner(self):
        for path in (
            "/api/shares",
            "/api/share-preview/example",
            "/api/shared-document/example",
            "/share-ui.js",
        ):
            with self.subTest(path=path):
                status, _, body = request(self.port, path, headers=self.headers())
                self.assertEqual((status, body), (404, b""))
        for path in (
            "/api/shares/prepare",
            "/api/shares/publish",
            "/api/shares/revoke",
            "/api/shares/settings",
        ):
            with self.subTest(path=path):
                status, _, body = request(self.port, path, "POST", self.headers(), "{}")
                self.assertEqual((status, body), (404, b""))

    @classmethod
    def setUpClass(cls):
        from report_viewer import app

        cls.viewer = app
        cls.temp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temp.name)
        (cls.root / "report.html").write_text("<h1>Local API test</h1>")
        cls.viewer.ROOT = cls.root
        cls.server = cls.viewer.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            functools.partial(cls.viewer.Handler, directory=str(cls.root)),
        )
        cls.server.viewer_token = secrets.token_urlsafe(32)
        cls.port = cls.server.server_port
        cls.preview = cls.viewer.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            functools.partial(cls.viewer.Handler, directory=str(cls.root)),
        )
        cls.preview.preview_only = True
        cls.preview.viewer_origins = [
            f"http://127.0.0.1:{cls.port}",
            f"http://localhost:{cls.port}",
        ]
        cls.server.preview_origin = f"http://127.0.0.1:{cls.preview.server_port}"
        threading.Thread(target=cls.preview.serve_forever, daemon=True).start()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.preview.shutdown()
        cls.preview.server_close()
        cls.temp.cleanup()

    def test_private_tailnet_origins_preserve_preview_isolation(self):
        viewer_origin = "https://lab.example:8445"
        preview_origin = "https://lab.example:8446"
        self.server.remote_origin = viewer_origin
        self.server.remote_preview_origin = preview_origin
        self.server.trusted_user = self.preview.trusted_user = "owner@example.com"
        self.preview.remote_origin = preview_origin
        self.preview.viewer_origins.append(viewer_origin)
        try:
            headers = {
                "Host": "lab.example:8445",
                "Tailscale-User-Login": "owner@example.com",
            }
            for identity in ("", "someone@example.com"):
                self.assertEqual(
                    request(
                        self.port,
                        "/",
                        headers={**headers, "Tailscale-User-Login": identity},
                    )[0],
                    404,
                )
            code, response_headers, body = request(self.port, "/", headers=headers)
            self.assertEqual(code, 200)
            self.assertIn(preview_origin.encode(), body)
            # A top-level external link opens normally; an iframe/fetch from HTML cannot read controls.
            navigation = {
                **headers,
                "Sec-Fetch-Site": "same-site",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            }
            self.assertEqual(request(self.port, "/", headers=navigation)[0], 200)
            self.assertEqual(
                request(
                    self.port, "/", headers={**navigation, "Sec-Fetch-Dest": "iframe"}
                )[0],
                404,
            )
            private = {
                **headers,
                "X-Viewer-Token": self.server.viewer_token,
                "Sec-Fetch-Site": "same-site",
            }
            self.assertEqual(
                request(self.port, "/api/reports", headers=private)[0], 404
            )
            frame = {
                "Host": "lab.example:8446",
                "Tailscale-User-Login": "owner@example.com",
                "Referer": viewer_origin + "/",
                "Sec-Fetch-Site": "same-site",
            }
            code, response_headers, _ = request(
                self.preview.server_port, "/files/report.html", headers=frame
            )
            self.assertEqual(code, 200)
            self.assertIn(viewer_origin, response_headers["Content-Security-Policy"])
            self.assertEqual(
                request(self.preview.server_port, "/api/shares", headers=frame)[0], 404
            )
            self.assertEqual(
                request(
                    self.preview.server_port,
                    "/files/report.html",
                    headers={**frame, "Referer": "https://evil.example/"},
                )[0],
                404,
            )
            local = request(self.port, "/")[2]
            self.assertIn(self.server.preview_origin.encode(), local)
        finally:
            for obj, names in [
                (
                    self.server,
                    ("remote_origin", "remote_preview_origin", "trusted_user"),
                ),
                (self.preview, ("remote_origin", "trusted_user")),
            ]:
                for name in names:
                    delattr(obj, name)
            self.preview.viewer_origins.remove(viewer_origin)

    def test_remote_origins_are_exact_https_origins(self):
        self.assertEqual(
            self.viewer.https_origin("https://lab.example:8445/"),
            "https://lab.example:8445",
        )
        for value in (
            "http://lab.example",
            "https://" + "user" + ":" + "pass" + "@lab.example",
            "https://lab.example/path",
            "https://lab.example?x=1",
            "javascript:alert(1)",
        ):
            with self.assertRaises(ValueError):
                self.viewer.https_origin(value)

    def headers(self):
        return {
            "X-Viewer-Token": self.server.viewer_token,
            "Origin": f"http://127.0.0.1:{self.port}",
            "Content-Type": "application/json",
        }

    def test_catalog_requires_the_viewer_token(self):
        self.assertEqual(request(self.port, "/api/reports")[0], 404)
        self.assertEqual(
            request(self.port, "/api/reports", headers={"X-Viewer-Token": "wrong"})[0],
            404,
        )
        status, _, body = request(
            self.port, "/api/reports?days=0", headers=self.headers()
        )
        self.assertEqual(status, 200)
        self.assertIn(
            "report.html", {row["path"] for row in json.loads(body)["reports"]}
        )

    def test_file_paths_cannot_escape_or_read_hidden_files(self):
        (self.root / ".private.html").write_text("Private")
        (self.root / "outside").symlink_to(self.root.parent)
        for path in (
            "/files/../outside.html",
            "/files/%2e%2e/outside.html",
            "/files/.private.html",
            "/files/outside/",
            "/files/",
        ):
            with self.subTest(path=path):
                status, _, body = request(self.port, path)
                self.assertEqual((status, body), (404, b""))

    def test_aliases_cannot_bypass_hidden_and_dependency_folders(self):
        for index, name in enumerate(
            (".private/sentinel.txt", "node_modules/sentinel.txt")
        ):
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("Test sentinel")
            alias = f"alias-{index}.txt"
            (self.root / alias).symlink_to(target)
            for port in (self.port, self.preview.server_port):
                with self.subTest(target=name, port=port):
                    self.assertEqual(request(port, "/files/" + alias)[::2], (404, b""))
        (self.root / "allowed-alias.html").symlink_to(self.root / "report.html")
        self.assertEqual(request(self.port, "/files/allowed-alias.html")[0], 200)

    def test_wave_audio_has_a_browser_supported_content_type(self):
        (self.root / "sample.wav").write_bytes(b"RIFF")
        code, headers, _ = request(self.port, "/files/sample.wav")
        self.assertEqual(code, 200)
        content_type = next(
            value for key, value in headers.items() if key.lower() == "content-type"
        )
        self.assertEqual(content_type, "audio/wav")

    def test_separate_preview_allows_viewer_and_rejects_other_origins(self):
        for origin, site in (
            (f"http://127.0.0.1:{self.port}", "same-site"),
            (f"http://localhost:{self.port}", "cross-site"),
        ):
            code, headers, body = request(
                self.preview.server_port,
                "/files/report.html",
                headers={"Referer": origin + "/", "Sec-Fetch-Site": site},
            )
            self.assertEqual(code, 200)
            self.assertIn(b"Local API test", body)
            self.assertIn(
                "sandbox allow-scripts allow-same-origin",
                headers["Content-Security-Policy"],
            )
        for path in ("/files/report.html", "/api/shares", "/"):
            code, _, body = request(
                self.preview.server_port,
                path,
                headers={
                    "Referer": "https://evil.example/",
                    "Sec-Fetch-Site": "cross-site",
                },
            )
            self.assertEqual((code, body), (404, b""))
        code, _, body = request(
            self.preview.server_port,
            "/api/shares",
            headers={
                "Referer": f"http://localhost:{self.port}/",
                "Sec-Fetch-Site": "cross-site",
            },
        )
        self.assertEqual((code, body), (404, b""))
        self.assertEqual(
            request(self.preview.server_port, "/files/report.html")[0], 200
        )

    def test_preview_opens_as_document_without_viewer_referrer(self):
        headers = {
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
        }
        for referrer in ("", "https://example.com/"):
            with self.subTest(referrer=referrer):
                code, _, body = request(
                    self.preview.server_port,
                    "/files/report.html",
                    headers={**headers, "Referer": referrer},
                )
                self.assertEqual(code, 200)
                self.assertIn(b"Local API test", body)
        for destination in ("image", "script", "empty"):
            with self.subTest(destination=destination):
                code, _, body = request(
                    self.preview.server_port,
                    "/files/report.html",
                    headers={**headers, "Sec-Fetch-Dest": destination},
                )
                self.assertEqual((code, body), (404, b""))
        code, _, body = request(
            self.preview.server_port, "/api/shares", headers=headers
        )
        self.assertEqual((code, body), (404, b""))

    def test_report_links_can_load_in_the_preview_frame(self):
        status, headers, _ = request(self.port, "/")
        self.assertEqual(status, 200)
        self.assertIn("frame-src http: https: blob:", headers["Content-Security-Policy"])
        # A report link to the other loopback name is cross-site and has no referrer.
        code, headers, body = request(
            self.preview.server_port,
            "/files/report.html",
            headers={
                "Host": f"localhost:{self.preview.server_port}",
                "Sec-Fetch-Site": "cross-site",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "iframe",
            },
        )
        self.assertEqual(code, 200)
        self.assertIn(b"Local API test", body)
        self.assertIn(
            "sandbox allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox;",
            headers["Content-Security-Policy"],
        )

    def test_preview_opens_internet_links_in_a_new_tab(self):
        code, headers, body = request(self.preview.server_port, "/files/report.html")
        self.assertEqual(code, 200)
        self.assertTrue(body.startswith(b"<h1>Local API test</h1>"))
        self.assertIn(b'window.open(link.href, "_blank", "noopener")', body)
        self.assertEqual(headers["Content-Length"], str(len(body)))
        # Downloads read the unchanged file through the viewer.
        code, _, body = request(self.port, "/files/report.html")
        self.assertEqual((code, body), (200, b"<h1>Local API test</h1>"))
        (self.root / "data.json").write_text("{}")
        code, _, body = request(self.preview.server_port, "/files/data.json")
        self.assertEqual((code, body), (200, b"{}"))

    def test_preview_redirects_absolute_paths_under_the_root(self):
        (self.root / "notes dir").mkdir(exist_ok=True)
        (self.root / "notes dir/plan.md").write_text("Plan")
        (self.root / ".hidden.md").write_text("Hidden")
        absolute = quote(str(self.root / "notes dir/plan.md"))
        code, headers, _ = request(self.preview.server_port, absolute)
        self.assertEqual((code, headers.get("Location")), (302, "/files/notes%20dir/plan.md"))
        with tempfile.NamedTemporaryFile(dir=self.root.parent, suffix=".md") as outside:
            name = Path(outside.name).name
            for path in (
                outside.name,
                str(self.root) + "/../" + name,
                str(self.root / ".hidden.md"),
                str(self.root / "notes dir"),
            ):
                with self.subTest(path=path):
                    self.assertEqual(
                        request(self.preview.server_port, quote(path))[::2], (404, b"")
                    )
        self.assertEqual(request(self.port, absolute)[::2], (404, b""))

    def test_viewer_cannot_be_framed_and_has_nonce(self):
        status, headers, body = request(self.port, "/")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertIn(b'nonce="' + self.server.viewer_token.encode() + b'"', body)
        self.assertIn(b"const previewOrigin=", body)
        self.assertIn(
            b'id="frame" title="Selected report" sandbox="allow-scripts"', body
        )

    def test_viewer_query_navigation_preserves_preview_referrer(self):
        navigation = {
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Dest": "document",
        }
        for path in (
            "/?report=report.html",
            "/index.html?report=report.html",
            "/?days=7",
            "/?type=Report",
        ):
            with self.subTest(path=path):
                code, headers, body = request(self.port, path, headers=navigation)
                self.assertEqual(code, 200)
                self.assertEqual(headers["Referrer-Policy"], "origin")
                self.assertIn(b"const previewOrigin=", body)
                code, _, body = request(
                    self.port, path, headers={**navigation, "Sec-Fetch-Dest": "iframe"}
                )
                self.assertEqual((code, body), (404, b""))


if __name__ == "__main__":
    unittest.main()
