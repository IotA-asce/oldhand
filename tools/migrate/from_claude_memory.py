#!/usr/bin/env python3
"""Migrate a Claude Code project-memory directory into a Oldhand archive.

Source shape: one Markdown file per fact, YAML frontmatter carrying `name`,
`description` and a `metadata` block, body in free Markdown with `[[slug]]`
links between records, plus a `MEMORY.md` index of one-line hooks.

This is a shadow migration. It reads the source and never writes to it. The
original archive keeps working untouched while the Oldhand copy is measured
against it, so a bad migration costs a directory, not a working system.

Deliberate non-decisions
------------------------

**Records are migrated one to one and never split.** Several source records
cover four or five distinct findings accreted over months. Oldhand ranks atomic
records better, so splitting would probably improve retrieval, but the
grouping is the author's curation and guessing at it would destroy
information that is not recoverable. Split later, by hand, when `oldhand usage`
shows a specific record being retrieved for the wrong reason.

**Importance is left flat except for a short, defensible critical list.**
Inventing a hierarchy across 117 records would be a hundred unfounded
judgements, and importance inflation is the one failure that measurably
destroys retrieval (recall@5 92% to 33% at a quarter critical). Uniform
metadata also measured *best* in testing, because it lets text relevance do
the work. Tune importance later from real retrieval data, upward, one record
at a time, with a reason.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _overrides import load_overrides, apply_status, extra_relations
from from_markdown import parse_frontmatter

# Their `metadata.type` to Oldhand's entry type.
TYPE_MAP = {
    "feedback": "lesson",        # guidance on how to work: a lesson learned
    "project": "investigation",  # ongoing work, findings, context
    "reference": "reference",    # durable pointer to where something lives
    "user": "reference",         # who the user is: a durable fact, not a finding
}

# Violating one of these causes irreversible or externally visible harm.
# Kept deliberately short: see the module docstring.
CRITICAL = {
    "never-write-to-mongodb",
    "owned-repos",
    "do-not-file-tickets-on-my-own-offer",
    "contract-upload-cannot-be-tested-without-a-user",
}

# Links in the source that point at renamed files. Repairing them here rather
# than dropping them preserves real relational data the author created.
LINK_REPAIRS = {
    "a-join-that-matches-nothing": "join-that-matches-nothing",
    "ado-mcp-auth-azcli": "azure-devops-mcp-auth",
}

# Topic vocabulary. Matched against title and description only, never the
# body: a record that mentions Kafka once in passing is not about Kafka, and
# the topic boost is meant to reward subject matter, not vocabulary overlap.
TOPICS = {
    "kafka": ["kafka", "topic", "partition", "consumer", "offset", "broker"],
    "mongodb": ["mongo", "mongodb", "cosmos", "bson", "objectid"],
    "graphql": ["graphql", "schema", "resolver", "introspection", "sdl"],
    "ci": ["ci", "build", "pipeline", "trivy", "sonarqube", "test run"],
    "testing": ["test", "tests", "suite", "assert", "vacuous", "eval", "coverage"],
    "azure-devops": ["ado", "azure devops", "work item", "ticket", "pr ", "backlog"],
    "deployment": ["deploy", "release", "pod", "k8s", "kubernetes", "cluster", "image tag"],
    "config": ["config", "setting", "appsettings", "env_var", "envsubst", "binding"],
    "auth": ["auth", "token", "scope", "credential", "authz", "oauth", "login"],
    "catalog": ["catalog", "enrichment", "approval", "publisher"],
    "product-discovery": ["product discovery", "productdiscovery", " pd ", "scan"],
    "contracts": ["contract", "procurement", "entitlement", "po extraction"],
    "llm": ["gemini", "llm", "model", "prompt", "grounding", "confidence"],
    "git": ["git", "branch", "commit", "merge", "worktree", "checkout"],
    "workflow": ["workflow", "routine", "convention", "style", "process"],
    "tooling": ["bash", "powershell", "script", "cli", "heredoc", "grep"],
    "docs": ["documentation", "google doc", "docx", "diagram", "drawio"],
    "agents": ["agent", "subagent", "session", "memory", "claude"],
}

VERIFIED = ["verified", "confirmed", "reproduced", "measured", "proved",
            "i ran", "checked", "observed on build"]


def read_index_hooks(src: Path) -> dict[str, str]:
    """Pull the one-line hook for each record out of MEMORY.md.

    The hook and the record's own frontmatter `description` are two summaries
    written at different times, and they are not interchangeable. The hook is
    the curated retrieval surface: it gets edited when knowledge changes,
    while the description is usually written once and left. Measured on this
    archive, 107 of 116 differ materially, and in at least one case the
    description still states a rule the hook has since retracted.

    So the hook wins, and the description is kept underneath it rather than
    discarded, because occasionally it carries detail the hook trimmed.
    """
    index = src / "MEMORY.md"
    if not index.exists():
        return {}
    hooks: dict[str, str] = {}
    pattern = re.compile(r"^- \[[^\]]+\]\(([^)]+\.md)\)\s*(.*)$", re.M)
    for m in pattern.finditer(index.read_text(encoding="utf-8", errors="replace")):
        slug = m.group(1).replace(".md", "")
        hook = m.group(2).strip().lstrip("-\u2013\u2014 ").strip()
        if hook:
            hooks[slug] = hook
    return hooks


def build_summary(hook: str, description: str) -> str:
    """Hook first, description second when it adds something."""
    if not hook:
        return description
    if not description:
        return hook
    # If one contains the other, the longer already says everything.
    a, b = hook.lower(), description.lower()
    if a[:60] in b or b[:60] in a:
        return hook if len(hook) >= len(description) else description
    return hook + "\n\n" + description


def parse_source(text: str) -> tuple[dict, str]:
    """Split frontmatter from body. Returns (fields, body)."""
    fields, body = parse_frontmatter(text)
    metadata = fields.get("metadata")
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            fields.setdefault(key, value)
    return fields, body.strip()


def pick_topics(title: str, description: str) -> list[str]:
    hay = f"{title} {description}".lower()
    found = [name for name, words in TOPICS.items() if any(w in hay for w in words)]
    return found[:4] or ["general"]


def pick_status(description: str) -> str:
    d = description.upper()
    if d.startswith("SUPERSEDED") or "SUPERSEDED " in d[:60]:
        return "superseded"
    if re.search(r"\b(?:UNRESOLVED|NOT\s+RESOLVED)\b", d[:60]):
        return "current"
    if re.search(r"\bRESOLVED\b", d[:60]):
        return "resolved"
    return "current"


def pick_evidence(body: str, description: str) -> str:
    hay = (description + " " + body[:4000]).lower()
    return "verified" if any(w in hay for w in VERIFIED) else "documented"


def pick_scope(slug: str, description: str) -> str:
    hay = f"{slug} {description}".lower()
    if any(w in hay for w in ["workspace", "owned repos", "never ", "always ", "all three"]):
        return "workspace"
    return "repository"


def to_iso(value: str | None, fallback_file: Path | None = None) -> str:
    """Timestamp for a record, stable across re-runs.

    `datetime.now()` as the fallback made the migration non-idempotent: 18 of
    118 records here carry no `modified` field, so every re-sync rewrote their
    timestamps and the archive churned even when no source had changed. That
    turns "did anything change?" into a question the fingerprint cannot
    answer, which is the question a weekly re-sync exists to ask.

    The source file's mtime is stable, meaningful, and already on disk.
    """
    if value:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone().isoformat()
        except ValueError:
            pass
    if fallback_file is not None:
        try:
            return (datetime.fromtimestamp(fallback_file.stat().st_mtime, timezone.utc)
                    .astimezone().replace(microsecond=0).isoformat())
        except OSError:
            pass
    return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: from_claude_memory.py <source-memory-dir> <oldhand-archive-root>")
        return 2
    src = Path(sys.argv[1])
    dst_root = Path(sys.argv[2])
    overrides = load_overrides(dst_root)
    if not src.is_dir():
        print(f"no such source directory: {src}", file=sys.stderr)
        return 1

    files = [f for f in sorted(src.glob("*.md")) if f.name != "MEMORY.md"]
    known = {f.stem for f in files}
    hooks = read_index_hooks(src)
    print(f"index hooks found: {len(hooks)} for {len(files)} record(s)")

    records = []
    for f in files:
        fields, body = parse_source(f.read_text(encoding="utf-8", errors="replace"))
        slug = str(fields.get("name") or f.stem)
        description = str(fields.get("description") or "").strip()
        title = slug.replace("-", " ")
        title = title[0].upper() + title[1:] if title else slug

        links = []
        for raw in re.findall(r"\[\[([a-z0-9\-]+)\]\]", body):
            target = LINK_REPAIRS.get(raw, raw)
            if target in known and target != slug and target not in links:
                links.append(target)

        records.append({
            "slug": slug,
            "title": title,
            "summary": build_summary(hooks.get(slug, ""), description) or title,
            "body": body,
            "type": TYPE_MAP.get(str(fields.get("type") or ""), "lesson"),
            "status": pick_status(description),
            "id": "lore_" + slug.replace("-", "_"),
            "importance": "critical" if slug in CRITICAL else "normal",
            "scope": pick_scope(slug, description),
            "risk": "high" if slug in CRITICAL else "medium",
            "durability": "invariant" if slug in CRITICAL else "long_lived",
            "evidence": pick_evidence(body, description),
            "topics": pick_topics(title, description),
            "when": to_iso(fields.get("modified"), f),
        })

    from collections import Counter
    dirs = Counter()
    written = 0
    for r in records:
        subdir = {"lesson": "lessons", "investigation": "investigations",
                  "reference": "reference", "constraint": "constraints"}[r["type"]]
        out_dir = dst_root / "memory" / subdir
        out_dir.mkdir(parents=True, exist_ok=True)
        dirs[subdir] += 1

        lines = ["---", "schema_version: 1", f"id: lore_{r['slug'].replace('-', '_')}",
                 f"type: {r['type']}",
                 f"status: {apply_status(r['id'], r['status'], overrides)}",
                 f"importance: {r['importance']}", f"scope: {r['scope']}",
                 f"risk: {r['risk']}", f"durability: {r['durability']}",
                 f"evidence: {r['evidence']}", "topics:"]
        lines += [f"  - {t}" for t in r["topics"]]
        lines += [f"created_at: {r['when']}", f"updated_at: {r['when']}", "expires_at: null"]
        related = []
        seen = set()
        for raw in re.findall(r"\[\[([a-z0-9\-]+)\]\]", r["body"]):
            target = LINK_REPAIRS.get(raw, raw)
            if target in known and target != r["slug"] and target not in seen:
                seen.add(target)
                related.append(f"lore_{target.replace('-', '_')}")
        rel_map: dict[str, list[str]] = {"related_to": list(related)} if related else {}
        for rtype, targets in extra_relations(r["id"], overrides).items():
            bucket = rel_map.setdefault(rtype, [])
            for target in targets:
                if target not in bucket:
                    bucket.append(target)
        rel_map = {k: v for k, v in rel_map.items() if v}
        if rel_map:
            lines.append("relations:")
            for rtype, targets in rel_map.items():
                lines.append(f"  {rtype}:")
                lines += [f"    - {x}" for x in targets]
        else:
            lines.append("relations: {}")
        lines += ["---", "", f"# {r['title']}", "", "## Summary", "", r["summary"], "",
                  "## Knowledge", "", r["body"], ""]

        (out_dir / f"{r['slug']}.md").write_text("\n".join(lines), encoding="utf-8")
        written += 1

    stats = Counter(r["status"] for r in records)
    imps = Counter(r["importance"] for r in records)
    evs = Counter(r["evidence"] for r in records)
    rel_count = sum(1 for r in records if re.search(r"\[\[[a-z0-9\-]+\]\]", r["body"]))

    print(f"migrated {written} record(s) into {dst_root / 'memory'}")
    print("  by directory:  " + ", ".join(f"{k}={v}" for k, v in sorted(dirs.items())))
    print("  by status:     " + ", ".join(f"{k}={v}" for k, v in stats.items()))
    print("  by importance: " + ", ".join(f"{k}={v}" for k, v in imps.items()))
    print("  by evidence:   " + ", ".join(f"{k}={v}" for k, v in evs.items()))
    print(f"  records with relations: {rel_count}")
    print(f"\nsource untouched: {src}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
