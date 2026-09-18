"""Oldhand: workspace layer. Split out of the former single-file CLI."""

from __future__ import annotations

import tempfile
from pathlib import Path
import hashlib
import os

from .constants import PRUNE_DIRS


def workspace_root(explicit: str | None) -> Path:
    """Resolve the workspace root.

    Precedence: --root, then OLDHAND_ROOT, then the *topmost* marker-bearing
    ancestor of the current directory. Taking the topmost rather than the
    nearest marker means running from inside a repository still searches the
    whole workspace; use --root to deliberately narrow the scope.

    LORE_ROOT is still honoured so archives created before the rename keep
    working; OLDHAND_ROOT wins when both are set.
    """
    if explicit:
        return Path(explicit).resolve()
    env = os.environ.get("OLDHAND_ROOT") or os.environ.get("LORE_ROOT")
    if env:
        return Path(env).resolve()

    cur = Path.cwd().resolve()
    try:
        home = Path.home().resolve()
    except Exception:
        home = None

    best: Path | None = None
    for candidate in [cur, *cur.parents]:
        if (candidate / "AGENTS.md").exists() or (candidate / "memory").is_dir():
            best = candidate
        if home is not None and candidate == home:
            break
    return best or cur


def discover_collections(root: Path, max_depth: int = 4) -> list[Path]:
    """Find every directory that owns a `memory/` archive, root included.

    A workspace holds one archive per repository. Sub-collections are not
    descended into, so a repository's own subdirectories never become separate
    collections.
    """
    found: list[Path] = []
    root_memory = root / "memory"
    # The CLI's own directory is not an archive, even if someone relocates it
    # next to one. Without this
    # guard the starter indexes its own source directory as a collection.
    tool_dir = Path(__file__).resolve().parent

    def is_archive(candidate: Path) -> bool:
        mem = candidate / "memory"
        if not mem.is_dir():
            return False
        try:
            return mem.resolve() != tool_dir
        except OSError:
            return True

    if is_archive(root):
        found.append(root)

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(p for p in directory.iterdir() if p.is_dir())
        except (PermissionError, OSError):
            return
        for child in children:
            if child.name in PRUNE_DIRS or child.name.startswith("."):
                continue
            if child == root_memory:
                continue
            if is_archive(child):
                found.append(child)
                continue
            walk(child, depth + 1)

    walk(root, 1)
    return found


def collection_name(root: Path, collection_root: Path) -> str:
    if collection_root == root:
        return root.name or str(root)
    try:
        return collection_root.relative_to(root).as_posix()
    except ValueError:
        return str(collection_root)


def collection_id(root: Path, collection_root: Path) -> str:
    rel = collection_name(root, collection_root)
    return "col:" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]


def db_path(root: Path) -> Path:
    return root / ".oldhand" / "oldhand.db"


def schema_path() -> Path:
    """Resolve the schema next to this script, not next to the detected root.

    Anchoring it to the root made the CLI unusable from any directory that did
    not happen to carry its own copy of the tool.
    """
    p = Path(__file__).resolve().parent / "schema.sql"
    if not p.exists():
        raise FileNotFoundError(f"Missing schema: {p}")
    return p


def display_path(root: Path, path: Path) -> str:
    """Render a path for output as POSIX on every platform.

    The JSON emitted by `new`, `list` and friends is a machine-readable
    interface, so it must not change shape on Windows. `str()` on a
    WindowsPath yields backslashes and silently breaks any consumer that
    compares or joins these values across platforms.
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _atomic_write(path: Path, data: bytes) -> None:
    fd, temporary_name = tempfile.mkstemp(prefix=path.name + ".updating.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
