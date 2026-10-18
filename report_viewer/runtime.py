"""Runtime source version, useful for diagnosing a stale browser/backend."""

import hashlib
from pathlib import Path


def version():
    root = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for source in sorted(root.rglob("*")):
        if source.is_file() and source.suffix in {
            ".py",
            ".html",
            ".js",
            ".mjs",
            ".css",
            ".ignore",
        }:
            digest.update(source.relative_to(root).as_posix().encode() + b"\0")
            digest.update(source.read_bytes())
    return digest.hexdigest()
