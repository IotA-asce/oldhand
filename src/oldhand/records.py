"""Oldhand: records layer. Split out of the former single-file CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .constants import FRONTMATTER_RE, HEADING_RE, RELATION_TYPES, SECTION_RE, yaml


def parse_sections(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        sections[m.group(1).strip().lower()] = body[start:end].strip()
    return sections


def normalize_relations(value: Any) -> dict[str, list[str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("relations must be a mapping")
    out: dict[str, list[str]] = {}
    for k, v in value.items():
        if k not in RELATION_TYPES:
            raise ValueError(f"invalid relation type '{k}'")
        targets = [v] if isinstance(v, str) else v
        if not isinstance(targets, list) or any(
            not isinstance(target, str) or not target.strip() for target in targets
        ):
            raise ValueError(f"relation '{k}' must contain nonempty string targets")
        out[k] = targets
    return out


def parse_record(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("missing YAML frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    if not isinstance(meta, dict):
        raise ValueError("frontmatter must be a mapping")

    body = text[m.end():].strip()
    hm = HEADING_RE.search(body)
    title = hm.group(1).strip() if hm else str(meta.get("title") or path.stem)
    sections = parse_sections(body)

    topics = meta.get("topics") or []
    if isinstance(topics, str):
        topics = [topics]
    topics = [str(x).strip() for x in topics if str(x).strip()]

    return {
        "meta": meta,
        "title": title,
        "summary": sections.get("summary", "").strip(),
        "sections": sections,
        "body": body,
        "topics": topics,
        "relations": normalize_relations(meta.get("relations")),
        "text": text,
    }


def record_files(collection_root: Path) -> list[Path]:
    mem = collection_root / "memory"
    if not mem.is_dir():
        return []
    files = []
    for p in mem.rglob("*.md"):
        if p.name in {"README.md", "SCHEMA.md", "MEMORY_INDEX.md"}:
            continue
        # examples document the format but are not live memory
        if "examples" in p.parts:
            continue
        files.append(p)
    return sorted(files)
