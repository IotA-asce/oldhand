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


def validate_run_payload(payload: Any, label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return [f"{label}: trace must be a JSON object"]
    required = {
        "schema_version", "id", "task", "evaluator", "policy", "goal",
        "max_workers", "status", "created_at", "updated_at", "nodes",
    }
    missing = sorted(required - set(payload))
    if missing:
        errors.append(f"{label}: missing fields: {', '.join(missing)}")
    if payload.get("schema_version") != TRACE_SCHEMA_VERSION:
        errors.append(f"{label}: schema_version must be {TRACE_SCHEMA_VERSION}")
    run_id = payload.get("id")
    if not isinstance(run_id, str) or not TRACE_ID_RE.fullmatch(run_id):
        errors.append(f"{label}: invalid run id")
    if payload.get("goal") not in ("maximize", "minimize"):
        errors.append(f"{label}: goal must be maximize or minimize")
    if payload.get("status") not in ("active", "completed"):
        errors.append(f"{label}: status must be active or completed")
    if not isinstance(payload.get("max_workers"), int) or payload.get("max_workers", 0) < 1:
        errors.append(f"{label}: max_workers must be a positive integer")
    nodes = payload.get("nodes")
    if not isinstance(nodes, list):
        errors.append(f"{label}: nodes must be a list")
        return errors
    ids: set[str] = set()
    child_counts: dict[str, int] = {}
    for index, node in enumerate(nodes, 1):
        node_label = f"{label}: node {index}"
        if not isinstance(node, dict):
            errors.append(f"{node_label} must be an object")
            continue
        node_id = node.get("id")
        if not isinstance(node_id, str) or not TRACE_ID_RE.fullmatch(node_id):
            errors.append(f"{node_label} has invalid id")
            continue
        if node_id in ids:
            errors.append(f"{label}: duplicate node id {node_id}")
        parent = node.get("parent_id")
        if parent != "root" and parent not in ids:
            errors.append(f"{label}: node {node_id} has unknown or forward parent {parent}")
        if parent != "root":
            child_counts[str(parent)] = child_counts.get(str(parent), 0) + 1
        if node.get("created_order") != index:
            errors.append(f"{label}: node {node_id} has invalid created_order")
        evaluation = node.get("evaluation")
        if evaluation is not None:
            if not isinstance(evaluation, dict):
                errors.append(f"{label}: node {node_id} evaluation must be an object")
            else:
                score = evaluation.get("score")
                if not isinstance(score, (int, float)) or isinstance(score, bool) or not math.isfinite(score):
                    errors.append(f"{label}: node {node_id} has invalid score")
                if type(evaluation.get("correct")) is not bool:
                    errors.append(f"{label}: node {node_id} correct must be boolean")
                if evaluation.get("outcome") not in ("success", "failure", "error"):
                    errors.append(f"{label}: node {node_id} has invalid outcome")
                for field in ("cost", "duration_ms"):
                    value = evaluation.get(field)
                    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                        errors.append(f"{label}: node {node_id} has invalid {field}")
        ids.add(node_id)
    for parent, count in child_counts.items():
        if count > 1:
            errors.append(f"{label}: non-root node {parent} has multiple continuations")
    if payload.get("status") == "completed":
        if not nodes:
            errors.append(f"{label}: completed run has no attempts")
        incomplete = [str(node.get("id")) for node in nodes
                      if isinstance(node, dict) and node.get("evaluation") is None]
        if incomplete:
            errors.append(f"{label}: completed run has unevaluated attempts: {', '.join(incomplete)}")
        if not payload.get("finished_at"):
            errors.append(f"{label}: completed run requires finished_at")
    return errors


def validate_runs(root: Path, run_id: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    paths = [run_path(root, run_id)] if run_id else sorted(runs_dir(root).glob("*.json"))
    if run_id and not paths[0].is_file():
        return [], [f"Unknown discovery run: {run_id}"]
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for path in paths:
        label = str(path.relative_to(root))
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{label}: cannot parse JSON: {error}")
            continue
        current = validate_run_payload(payload, label)
        if current:
            errors.extend(current)
        else:
            valid.append(payload)
    return valid, errors


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


def finish_run(root: Path, run_id: str, json_output: bool = False) -> int:
    valid, errors = validate_runs(root, run_id)
    if errors:
        for error in errors:
            print(error, file=os.sys.stderr)
        return 1
    run = valid[0]
    if run.get("status") == "completed":
        print(f"Discovery run is already completed: {run_id}")
        return 0
    if not run.get("nodes"):
        print("Cannot finish a run with no attempts.", file=os.sys.stderr)
        return 1
    incomplete = [node["id"] for node in run["nodes"] if node.get("evaluation") is None]
    if incomplete:
        print(f"Unevaluated attempts: {', '.join(incomplete)}", file=os.sys.stderr)
        return 1
    finished = now_iso()
    run["status"] = "completed"
    run["updated_at"] = finished
    run["finished_at"] = finished
    post_errors = validate_run_payload(run, str(run_path(root, run_id).relative_to(root)))
    if post_errors:
        for error in post_errors:
            print(error, file=os.sys.stderr)
        return 1
    _atomic_json(run_path(root, run_id), run)
    receipt = {"completed": True, "id": run_id, "attempts": len(run["nodes"]),
               "finished_at": finished}
    if json_output:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))
    else:
        print(f"Completed discovery run {run_id} with {len(run['nodes'])} attempt(s)")
    return 0


def validate_runs_cmd(root: Path, run_id: str | None = None,
                      json_output: bool = False) -> int:
    valid, errors = validate_runs(root, run_id)
    payload = {"valid": not errors, "run_count": len(valid),
               "error_count": len(errors), "errors": errors}
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif errors:
        print(f"Discovery validation failed ({len(errors)} issue(s)):")
        for error in errors:
            print(f"  - {error}")
    else:
        print(f"Discovery validation passed: {len(valid)} run(s).")
    return 1 if errors else 0


def run_summary(run: dict[str, Any]) -> dict[str, Any]:
    evaluations = [node["evaluation"] for node in run.get("nodes", [])
                   if isinstance(node, dict) and isinstance(node.get("evaluation"), dict)]
    correct_scores = [item["score"] for item in evaluations if item.get("correct")]
    best_score = None
    if correct_scores:
        best_score = (max(correct_scores) if run.get("goal") == "maximize"
                      else min(correct_scores))
    return {
        "id": run["id"], "task": run["task"], "status": run["status"],
        "evaluator": run["evaluator"], "policy": run["policy"],
        "goal": run["goal"], "max_workers": run["max_workers"],
        "attempt_count": len(run.get("nodes", [])),
        "evaluated_count": len(evaluations),
        "correct_count": sum(1 for item in evaluations if item.get("correct")),
        "best_score": best_score,
        "total_cost": sum(item.get("cost", 0) for item in evaluations),
        "total_duration_ms": sum(item.get("duration_ms", 0) for item in evaluations),
        "created_at": run["created_at"], "updated_at": run["updated_at"],
        "finished_at": run.get("finished_at"),
    }


def _tree_nodes(run: dict[str, Any], parent_id: str = "root") -> list[dict[str, Any]]:
    children = []
    for node in run.get("nodes", []):
        if node.get("parent_id") == parent_id:
            item = dict(node)
            item["children"] = _tree_nodes(run, str(node["id"]))
            children.append(item)
    return children


def list_runs(root: Path, status: str | None = None,
              json_output: bool = False) -> int:
    valid, errors = validate_runs(root)
    if errors:
        for error in errors:
            print(error, file=os.sys.stderr)
        return 1
    summaries = [run_summary(run) for run in valid if status is None or run["status"] == status]
    summaries.sort(key=lambda item: (item["created_at"], item["id"]), reverse=True)
    if json_output:
        print(json.dumps({"count": len(summaries), "status": status, "runs": summaries},
                         ensure_ascii=False, indent=2))
    else:
        print(f"{len(summaries)} discovery run(s).")
        for item in summaries:
            score = "n/a" if item["best_score"] is None else f"{item['best_score']:g}"
            print(f"- {item['id']} [{item['status']}] {item['task']}")
            print(f"  attempts {item['evaluated_count']}/{item['attempt_count']} · "
                  f"correct {item['correct_count']} · best {score} · cost {item['total_cost']}")
    return 0


def show_run(root: Path, run_id: str, json_output: bool = False) -> int:
    valid, errors = validate_runs(root, run_id)
    if errors:
        for error in errors:
            print(error, file=os.sys.stderr)
        return 1
    run = valid[0]
    summary = run_summary(run)
    tree = _tree_nodes(run)
    if json_output:
        print(json.dumps({"summary": summary, "run": run, "tree": tree},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"{run['task']} ({run_id}) [{run['status']}]")
    print(f"evaluator: {run['evaluator']} · policy: {run['policy']} · goal: {run['goal']}")
    print(f"attempts: {summary['evaluated_count']}/{summary['attempt_count']} evaluated · "
          f"correct: {summary['correct_count']} · cost: {summary['total_cost']}")

    def render(nodes: list[dict[str, Any]], depth: int) -> None:
        for node in nodes:
            evaluation = node.get("evaluation")
            result = "pending"
            if evaluation:
                mark = "✓" if evaluation["correct"] else "✗"
                result = f"{mark} score={evaluation['score']:g} cost={evaluation['cost']}"
            print(f"{'  ' * depth}- {node['id']}: {node['proposal']} [{result}]")
            render(node["children"], depth + 1)

    render(tree, 0)
    return 0


REPLAY_POLICIES = ("breadth", "depth", "score-greedy")


def replay_run(run: dict[str, Any], policy: str, budget: int, workers: int = 1,
               beta_cost: float = 0.0, beta_parallel: float = 0.0) -> dict[str, Any]:
    """Reveal a recorded tree without exposing future nodes to the policy."""
    if policy not in REPLAY_POLICIES:
        raise ValueError(f"Unknown replay policy: {policy}")
    if budget < 1:
        raise ValueError("budget must be a positive integer")
    if workers < 1:
        raise ValueError("workers must be a positive integer")
    if beta_cost < 0 or beta_parallel < 0:
        raise ValueError("replay coefficients must be non-negative")
    nodes = sorted(run.get("nodes", []), key=lambda item: item["created_order"])
    by_id = {node["id"]: node for node in nodes}
    children: dict[str, list[str]] = {"root": []}
    for node in nodes:
        children.setdefault(node["parent_id"], []).append(node["id"])
        children.setdefault(node["id"], [])
    observed: list[str] = []
    observed_set: set[str] = set()
    exhausted: set[str] = set()
    decisions: list[dict[str, Any]] = []

    def depth(node_id: str) -> int:
        if node_id == "root":
            return -1
        value = 0
        parent = by_id[node_id]["parent_id"]
        while parent != "root":
            value += 1
            parent = by_id[parent]["parent_id"]
        return value

    def adjusted_score(node_id: str) -> float:
        if node_id == "root":
            return float("-inf")
        evaluation = by_id[node_id].get("evaluation") or {}
        if not evaluation.get("correct"):
            return float("-inf")
        score = float(evaluation["score"])
        return score if run.get("goal") == "maximize" else -score

    while len(observed) < budget:
        candidates = []
        if "root" not in exhausted:
            candidates.append("root")
        for node_id in observed:
            if node_id in exhausted:
                continue
            if not any(child in observed_set for child in children[node_id]):
                candidates.append(node_id)
        if not candidates:
            break
        if policy == "breadth":
            ordered = sorted(candidates, key=lambda item: (depth(item), item))
        elif policy == "depth":
            ordered = sorted(candidates,
                             key=lambda item: (depth(item), item != "root"), reverse=True)
        else:
            ordered = sorted(candidates,
                             key=lambda item: (adjusted_score(item), depth(item)), reverse=True)
        selected = ordered[:min(workers, budget - len(observed))]
        revealed_this_round = []
        for parent in selected:
            child = next((item for item in children[parent] if item not in observed_set), None)
            if child is None:
                exhausted.add(parent)
                continue
            observed.append(child)
            observed_set.add(child)
            revealed_this_round.append(child)
        decisions.append({"round": len(decisions) + 1, "selected": selected,
                          "revealed": revealed_this_round})

    evaluations = [by_id[node_id]["evaluation"] for node_id in observed
                   if by_id[node_id].get("evaluation", {}).get("correct")]
    scores = [float(item["score"]) for item in evaluations]
    best_score = None
    if scores:
        best_score = max(scores) if run.get("goal") == "maximize" else min(scores)
    quality = None if best_score is None else (
        best_score if run.get("goal") == "maximize" else -best_score)
    total_cost = sum(float(by_id[node_id]["evaluation"].get("cost", 0))
                     for node_id in observed)
    parallelism = len(observed) / max(1, len(decisions))
    objective = None if quality is None else (
        quality - beta_cost * total_cost + beta_parallel * parallelism)
    return {
        "run_id": run["id"], "policy": policy, "budget": budget,
        "workers": workers, "beta_cost": beta_cost, "beta_parallel": beta_parallel,
        "revealed": observed, "attempt_count": len(observed),
        "rounds": len(decisions), "decisions": decisions,
        "best_score": best_score, "quality": quality, "total_cost": total_cost,
        "parallelism": parallelism, "objective": objective,
    }


def replay_cmd(root: Path, run_id: str, policy: str, budget: int,
               workers: int | None = None, beta_cost: float = 0.0,
               beta_parallel: float = 0.0,
               json_output: bool = False) -> int:
    valid, errors = validate_runs(root, run_id)
    if errors:
        for error in errors:
            print(error, file=os.sys.stderr)
        return 1
    run = valid[0]
    if run.get("status") != "completed":
        print("Replay requires a completed discovery run.", file=os.sys.stderr)
        return 1
    effective_workers = workers or int(run["max_workers"])
    try:
        result = replay_run(run, policy, budget, effective_workers,
                            beta_cost, beta_parallel)
    except ValueError as error:
        print(error, file=os.sys.stderr)
        return 2
    if json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Replay {run_id} with {policy}: {len(result['revealed'])} attempt(s), "
              f"{result['rounds']} round(s), best={result['best_score']}, "
              f"objective={result['objective']}")
        print("revealed: " + ", ".join(result["revealed"]))
    return 0
