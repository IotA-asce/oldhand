"""Canonical discovery traces and offline replay support for Lore."""

from __future__ import annotations

import json
import math
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


def load_run(root: Path, run_id: str) -> dict[str, Any]:
    path = run_path(root, run_id)
    if not path.is_file():
        raise ValueError(f"Unknown discovery run: {run_id}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read discovery run {run_id}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Discovery run {run_id} must be a JSON object")
    return payload


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


def add_attempt(root: Path, run_id: str, node_id: str, parent_id: str,
                proposal: str, artifact_ref: str | None = None,
                policy_version: str | None = None,
                json_output: bool = False) -> int:
    if not TRACE_ID_RE.fullmatch(node_id):
        print("Invalid attempt id: use 1-128 portable id characters.", file=os.sys.stderr)
        return 2
    if not proposal.strip():
        print("proposal cannot be empty", file=os.sys.stderr)
        return 2
    try:
        run = load_run(root, run_id)
    except ValueError as error:
        print(error, file=os.sys.stderr)
        return 1
    if run.get("status") != "active":
        print(f"Discovery run is not active: {run_id}", file=os.sys.stderr)
        return 1
    nodes = run.get("nodes", [])
    ids = {str(node.get("id")) for node in nodes if isinstance(node, dict)}
    if node_id in ids:
        print(f"Attempt already exists: {node_id}", file=os.sys.stderr)
        return 1
    if parent_id != "root" and parent_id not in ids:
        print(f"Unknown parent attempt: {parent_id}", file=os.sys.stderr)
        return 1
    if parent_id != "root" and any(node.get("parent_id") == parent_id for node in nodes):
        print(f"Non-root attempt already has a continuation: {parent_id}", file=os.sys.stderr)
        return 1
    created = now_iso()
    node = {
        "id": node_id,
        "parent_id": parent_id,
        "created_order": len(nodes) + 1,
        "proposal": proposal.strip(),
        "artifact_ref": artifact_ref,
        "policy_version": policy_version or run.get("policy"),
        "created_at": created,
        "evaluation": None,
    }
    nodes.append(node)
    run["nodes"] = nodes
    run["updated_at"] = created
    _atomic_json(run_path(root, run_id), run)
    receipt = {"created": True, "run_id": run_id, "node": node}
    if json_output:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(f"Added attempt {node_id} to {run_id} from {parent_id}")
    return 0


def evaluate_attempt(root: Path, run_id: str, node_id: str, score: float,
                     correct: bool, outcome: str, cost: int = 1,
                     duration_ms: int = 0, diagnostics_ref: str | None = None,
                     json_output: bool = False) -> int:
    if not math.isfinite(score):
        print("score must be finite", file=os.sys.stderr)
        return 2
    if cost < 0 or duration_ms < 0:
        print("cost and duration must be non-negative", file=os.sys.stderr)
        return 2
    try:
        run = load_run(root, run_id)
    except ValueError as error:
        print(error, file=os.sys.stderr)
        return 1
    if run.get("status") != "active":
        print(f"Discovery run is not active: {run_id}", file=os.sys.stderr)
        return 1
    node = next((item for item in run.get("nodes", []) if item.get("id") == node_id), None)
    if node is None:
        print(f"Unknown attempt: {node_id}", file=os.sys.stderr)
        return 1
    if node.get("evaluation") is not None:
        print(f"Attempt is already evaluated: {node_id}", file=os.sys.stderr)
        return 1
    evaluated = now_iso()
    evaluation = {
        "score": score,
        "correct": correct,
        "outcome": outcome,
        "cost": cost,
        "duration_ms": duration_ms,
        "diagnostics_ref": diagnostics_ref,
        "evaluated_at": evaluated,
    }
    node["evaluation"] = evaluation
    run["updated_at"] = evaluated
    _atomic_json(run_path(root, run_id), run)
    receipt = {"updated": True, "run_id": run_id, "node_id": node_id,
               "evaluation": evaluation}
    if json_output:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        state = "correct" if correct else "incorrect"
        print(f"Evaluated {node_id}: score={score:g}, {state}, outcome={outcome}")
    return 0
