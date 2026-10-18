"""Report discovery and metadata caching."""

from html.parser import HTMLParser
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import quote

from .paths import SKIP, resolve_visible, visible_path

APP = Path(__file__).resolve().parent
SOURCE_FOLDERS = {
    "test",
    "tests",
    "__tests__",
    "template",
    "templates",
    "fixture",
    "fixtures",
    "__fixtures__",
    "golden",
    "goldens",
    "__snapshots__",
}
CACHE = {"time": 0, "rows": [], "warnings": 0}
HEAD_CACHE = {}
LOCK = threading.Lock()


class Head(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title = ""
        self.description = ""
        self.report = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            name = attrs.get("name", "").lower()
            self.report |= name.startswith("report:")
            if name == "description":
                self.description = attrs.get("content", "")

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def html_files(root):
    # Include ignored/untracked reports and worktrees; do not follow directory symlinks.
    if shutil.which("rg"):
        args = [
            "rg",
            "--files",
            "--hidden",
            "--no-ignore",
            "--ignore-file",
            str(APP / "discovery.ignore"),
            "-0",
            "--iglob",
            "*.html",
            "--iglob",
            "*.htm",
        ]
        for name in sorted(SKIP):
            args += ["-g", f"!**/{name}/**"]
        result = subprocess.run(args, cwd=root, capture_output=True, timeout=45)
        if result.returncode not in (0, 1):
            raise RuntimeError(
                "Some folders could not be scanned: "
                + result.stderr.decode(errors="replace")[:200]
            )
        return [
            root / os.fsdecode(p)
            for p in result.stdout.split(b"\0")
            if p and resolve_visible(root, Path(os.fsdecode(p))) is not None
        ]
    paths = []
    for parent, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP and visible_path(Path(d))]
        paths.extend(
            Path(parent) / f
            for f in files
            if not f.startswith(".")
            and f.lower().endswith((".html", ".htm"))
            and not (Path(parent) / f).is_symlink()
        )
    return [
        path
        for path in paths
        if resolve_visible(root, path.relative_to(root)) is not None
    ]


def page_kind(rel, head):
    """Separate source files before applying report metadata and page conventions."""
    parts = [part.lower() for part in rel.parts]
    if SOURCE_FOLDERS.intersection(parts[:-1]):
        return "Code and tests"
    stem = rel.stem.lower()
    words = set(re.split(r"[^a-z0-9]+", stem))
    report_folder = any(part in {"report", "reports"} for part in parts[:-1])
    if (
        "manifest" in words
        or (stem == "index" and report_folder)
        or head.title.strip().lower()
        in {"reports hub", "report hub", "reports index", "report index"}
    ):
        return None
    if head.report:
        return "Report"
    if words & {"storyboard", "storyboards", "animatic"}:
        return "Storyboard"
    if report_folder or words & {"report", "audit", "analysis"}:
        return "Report"
    if words & {"deck", "slides", "presentation"} or "decks" in parts:
        return "Deck"
    if "hyperframes" in parts:
        return "Video"
    if words & {"mockup", "prototype"} or any(
        part in {"mockups", "prototype", "prototypes"} for part in parts
    ):
        return "Mockup"
    if any(part in {"docs", "refs", "reference", "references"} for part in parts):
        return "Docs"
    return "HTML"


def scan(root, days=3, pins=frozenset()):
    with LOCK:
        if (
            time.monotonic() - CACHE["time"] < 10
            and CACHE.get("root") == root
            and CACHE.get("days") == days
            and CACHE.get("pins") == pins
        ):
            return CACHE["rows"], CACHE["warnings"]
        rows, warnings = [], 0
        cutoff = time.time() - days * 86400 if days else 0
        paths = html_files(root)
        existing = set(paths)
        for stale in HEAD_CACHE.keys() - existing:
            del HEAD_CACHE[stale]
        for path in paths:
            try:
                stat = path.stat()
                if (
                    stat.st_mtime < cutoff
                    and path.relative_to(root).as_posix() not in pins
                ):
                    continue
                if path.resolve().is_relative_to(APP):
                    continue
                rel = path.relative_to(root)
                signature = (stat.st_mtime_ns, stat.st_size)
                cached = HEAD_CACHE.get(path)
                if cached and cached[0] == signature:
                    head = cached[1]
                else:
                    head = Head()
                    with path.open(encoding="utf-8", errors="replace") as source:
                        head.feed(source.read(65536).split("</head>", 1)[0])
                    HEAD_CACHE[path] = (signature, head)
                kind = page_kind(rel, head)
                if kind is None:
                    continue
                rows.append(
                    {
                        "path": rel.as_posix(),
                        "title": " ".join(head.title.split())
                        or path.stem.replace("-", " "),
                        "description": head.description,
                        "modified": stat.st_mtime,
                        "kind": kind,
                        "url": "/files/" + quote(rel.as_posix()),
                    }
                )
            except (OSError, ValueError):
                warnings += 1
        rows.sort(key=lambda row: (-row["modified"], row["path"]))
        CACHE.update(
            root=root,
            time=time.monotonic(),
            rows=rows,
            warnings=warnings,
            days=days,
            pins=pins,
        )
        return rows, warnings
