#!/usr/bin/env python3
"""Migrate an ordinary folder of Markdown notes into a Lore archive.

The other two migrations target specific conventions. This one assumes almost
nothing, because most people arriving with existing notes have neither: an
Obsidian vault, a Jekyll `_posts` folder, a wiki export, a directory of files
someone has been appending to for three years.

What it needs: Markdown files. Frontmatter is used when present and invented
when not.

What it infers, and from where:

    title      an H1, else the frontmatter `title`, else the filename
    summary    frontmatter `description`/`summary`/`excerpt`, else the first
               real paragraph, else the title
    topics     frontmatter `tags`/`topics`/`categories`, else nothing
    dates      frontmatter `date`/`created`/`modified`, else the file's mtime
    type       a keyword guess from the title, defaulting to `lesson`
    the rest   schema defaults

Everything it guessed is reported at the end, because a guess you cannot see
is worse than no guess. Nothing is written to the source directory.

Deliberately does NOT invent importance. Everything arrives as `normal`.
Importance is a budget best spent later, deliberately, on records that have
proven they matter: a migration that hands out `critical` on keyword matches
would destroy retrieval before the archive is a day old.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _overrides import (apply_status, extra_relations, load_overrides,  # noqa: E402
                        render_relations)

TYPE_HINTS = [
    ("decision", ("decision", "decided", "chose", "rfc", "adr", "why we")),
    ("constraint", ("must", "never", "always", "invariant", "rule", "policy",
                    "cannot", "do not")),
    ("fix", ("fix", "fixed", "bug", "broke", "broken", "repair", "patch")),
    ("incident", ("incident", "outage", "postmortem", "post-mortem", "down")),
    ("migration", ("migration", "migrate", "upgrade", "port to", "moved to")),
    ("investigation", ("investigat", "why does", "why did", "root cause",
                       "looked into", "analysis")),
    ("reference", ("where", "how to find", "location", "credentials", "endpoint",
                   "url", "cheatsheet", "cheat sheet")),
    ("feature", ("feature", "added", "implement", "built", "shipped")),
]

FM = re.compile(r"\A---[^\S\r\n]*\r?\n(.*?)^---[^\S\r\n]*(?:\r?\n|\Z)", re.S | re.M)
STRUCTURAL = re.compile(
    r"^(summary|context|background|overview|notes?|contents?|toc)\b", re.I)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = FM.match(text)
    if not m:
        return {}, text
    try:
        fields = yaml.safe_load(m.group(1))
        nodes = yaml.compose(m.group(1), Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        return {}, text
    if fields is None:
        fields = {}
    if not isinstance(fields, dict):
        return {}, text
    fields = {str(key).lower(): value for key, value in fields.items()}
    text_fields = {"name", "title", "description", "summary", "excerpt", "abstract", "type", "kind"}
    if isinstance(nodes, yaml.MappingNode):
        for key, value in nodes.value:
            if isinstance(key, yaml.ScalarNode) and isinstance(value, yaml.ScalarNode):
                if key.value.lower() in text_fields:
                    fields[key.value.lower()] = value.value
    return fields, text[m.end():]


def first_value(fields: dict, *names) -> object:
    for n in names:
        if fields.get(n):
            return fields[n]
    return None


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [p.strip() for p in re.split(r"[,;]", str(value)) if p.strip()]


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", value) or "record"


def first_paragraph(body: str) -> str:
    """The first block that is prose, not a heading, list, quote or code."""
    body = re.sub(r"```.*?```", "", body, flags=re.S)
    for block in body.split("\n\n"):
        b = block.strip()
        if not b or b.startswith(("#", ">", "|", "```", "---")):
            continue
        if re.match(r"^\s*(?:[-*+]|\d+\.)\s", b):
            continue
        return " ".join(b.split())
    return ""


def guess_type(title: str, body: str) -> tuple[str, bool]:
    hay = f"{title} {body[:300]}".lower()
    for etype, words in TYPE_HINTS:
        if any(w in hay for w in words):
            return etype, True
    return "lesson", False


def to_iso(value, fallback: Path) -> str:
    if value:
        s = str(value).strip().strip("\"'")
        for fmt in (None, "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                dt = (datetime.fromisoformat(s.replace("Z", "+00:00")) if fmt is None
                      else datetime.strptime(s[:10], fmt))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone().replace(microsecond=0).isoformat()
            except ValueError:
                continue
    try:
        return (datetime.fromtimestamp(fallback.stat().st_mtime, timezone.utc)
                .astimezone().replace(microsecond=0).isoformat())
    except OSError:
        return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


TYPE_DIRS = {
    "topic_summary": "topics", "decision": "decisions", "constraint": "constraints",
    "fix": "fixes", "investigation": "investigations", "migration": "migrations",
    "incident": "incidents", "lesson": "lessons", "reference": "reference",
    "feature": "features",
}


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: from_markdown.py <notes-directory> <archive-directory> [collection]")
        print()
        print("Reads every .md file under the notes directory. Writes nothing to it.")
        return 2
    src = Path(sys.argv[1]).resolve()
    dst = Path(sys.argv[2]).resolve()
    collection = sys.argv[3] if len(sys.argv) > 3 else None
    if not src.is_dir():
        print(f"no such directory: {src}", file=sys.stderr)
        return 1

    skip_names = {"readme.md", "index.md", "memory_index.md", "schema.md",
                  "license.md", "contributing.md", "changelog.md"}
    files = [f for f in sorted(src.rglob("*.md"))
             if f.name.lower() not in skip_names and f.stat().st_size > 0]
    if not files:
        print(f"no Markdown files under {src}", file=sys.stderr)
        return 1

    overrides = load_overrides(dst.parent if collection else dst)
    prefix = f"lore_{slugify(collection)}_" if collection else "lore_"
    inferred = Counter()
    used_ids: set[str] = set()
    written = 0

    for f in files:
        raw = f.read_text(encoding="utf-8", errors="replace")
        fields, body = parse_frontmatter(raw)
        body = body.strip()

        h1 = re.match(r"^#\s+(.+?)\s*$", body, re.M)
        if h1 and body.lstrip().startswith("#"):
            title = h1.group(1).strip()
            body = body[h1.end():].strip()
        elif first_value(fields, "title", "name"):
            title = str(first_value(fields, "title", "name"))
        else:
            title = f.stem.replace("-", " ").replace("_", " ")
            title = title[:1].upper() + title[1:]
            inferred["title from filename"] += 1

        summary = first_value(fields, "description", "summary", "excerpt", "abstract")
        if summary:
            summary = " ".join(str(summary).split())
        else:
            summary = first_paragraph(body)
            if summary:
                inferred["summary from first paragraph"] += 1
        if not summary or STRUCTURAL.match(summary):
            summary = title
            inferred["summary fell back to the title"] += 1
        summary = summary[:600]

        topics = [slugify(t) for t in
                  as_list(first_value(fields, "topics", "tags", "categories", "keywords"))][:5]
        if not topics:
            topics = ["general"]
            inferred["no topics found"] += 1

        etype = str(first_value(fields, "type", "kind") or "").lower()
        if etype not in TYPE_DIRS:
            etype, confident = guess_type(title, body)
            inferred["type guessed from wording" if confident
                     else "type defaulted to lesson"] += 1

        when = to_iso(first_value(fields, "date", "created", "created_at", "modified"), f)
        if not first_value(fields, "date", "created", "created_at", "modified"):
            inferred["date from file mtime"] += 1

        rid = prefix + slugify(title).replace("-", "_")
        n = 2
        while rid in used_ids:
            rid = f"{prefix}{slugify(title).replace('-', '_')}_{n}"
            n += 1
        used_ids.add(rid)

        out_dir = dst / "memory" / TYPE_DIRS[etype]
        out_dir.mkdir(parents=True, exist_ok=True)
        lines = ["---", "schema_version: 1", f"id: {rid}", f"type: {etype}",
                 f"status: {apply_status(rid, 'current', overrides)}",
                 "importance: normal", "scope: repository", "risk: medium",
                 "durability: long_lived", "evidence: documented", "topics:"]
        lines += [f"  - {t}" for t in topics]
        lines += [f"created_at: {when}", f"updated_at: {when}", "expires_at: null"]
        lines += render_relations(extra_relations(rid, overrides))
        lines += ["---", "", f"# {title}", "", "## Summary", "", summary, "",
                  "## Knowledge", "", body or summary, "",
                  "## Verification", "", "Migrated from existing notes; not re-verified.", "",
                  "## References", "", f"Source note: `{f.relative_to(src).as_posix()}`", ""]

        name = slugify(title)[:80] or f.stem
        path = out_dir / f"{name}.md"
        if path.exists():
            path = out_dir / f"{name}-{written}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        written += 1

    print(f"migrated {written} note(s) from {src}")
    if inferred:
        print("\ninferred, because the source did not say:")
        for what, n in inferred.most_common():
            print(f"  {n:>4}  {what}")
    print("\nEverything arrived as `importance: normal` on purpose. Raise a record")
    print("only once it has proven it matters; see WRITING_RECORDS.md. Then:")
    print("  lore validate && lore doctor")
    print("\nExpect `doctor` to flag records whose summary is a heading or a")
    print("fragment. That is the migration reporting what your notes actually")
    print("contain, not a failure: fix the ones you care about.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
