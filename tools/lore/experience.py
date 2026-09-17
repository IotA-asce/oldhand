"""Canonical discovery traces and offline replay support for Lore."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


TRACE_SCHEMA_VERSION = 1
TRACE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def runs_dir(root: Path) -> Path:
    return root / "experience" / "runs"


def run_path(root: Path, run_id: str) -> Path:
    return runs_dir(root) / f"{run_id}.json"


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
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


def generated_run_id() -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S%f")
    return f"run_{stamp}"


def start_run(root: Path, task: str, evaluator: str, policy: str,
              goal: str = "maximize", workers: int = 1,
              run_id: str | None = None, workspace_ref: str | None = None,
              json_output: bool = False) -> int:
    run_id = run_id or generated_run_id()
    if not TRACE_ID_RE.fullmatch(run_id):
        print("Invalid run id: use 1-128 portable id characters.", file=os.sys.stderr)
        return 2
    if workers < 1:
        print("workers must be a positive integer", file=os.sys.stderr)
        return 2
    path = run_path(root, run_id)
    if path.exists():
        print(f"Discovery run already exists: {run_id}", file=os.sys.stderr)
        return 1
    created = now_iso()
    payload: dict[str, Any] = {
        "schema_version": TRACE_SCHEMA_VERSION,
        "id": run_id,
        "task": task,
        "evaluator": evaluator,
        "policy": policy,
        "goal": goal,
        "max_workers": workers,
        "workspace_ref": workspace_ref,
        "status": "active",
        "created_at": created,
        "updated_at": created,
        "finished_at": None,
        "nodes": [],
    }
    _atomic_json(path, payload)
    receipt = {"created": True, "id": run_id, "path": str(path.relative_to(root)),
               "status": "active"}
    if json_output:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(f"Started discovery run {run_id}")
        print(f"path: {receipt['path']}")
    return 0
