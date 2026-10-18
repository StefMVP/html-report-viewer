"""Path rules for local discovery and previews."""

from pathlib import Path

SKIP = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".cache",
    ".next",
    ".nuxt",
    "site-packages",
}


def visible_path(path: Path) -> bool:
    return all(
        part not in SKIP and (not part.startswith(".") or part == ".worktrees")
        for part in path.parts
    )


def resolve_visible(root: Path, relative: Path) -> Path | None:
    """Check both the requested name and its resolved target."""
    try:
        resolved = (root / relative).resolve()
        if visible_path(relative) and visible_path(resolved.relative_to(root)):
            return resolved
    except (OSError, ValueError, RuntimeError):
        pass
    return None
