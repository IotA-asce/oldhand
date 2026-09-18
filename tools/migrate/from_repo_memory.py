#!/usr/bin/env python3
"""Migrate an in-repo `memory/` directory into a Oldhand collection.

Source shape: one *directory* per memory entry, not one file. The canonical
files are SUMMARY.md, CONTEXT.md, CHANGES.md and LINKS.md, with optional
RISKS.md, TESTING.md, FOLLOW_UP.md and ROLLBACK.md. Entries are grouped under
a category directory (fixes/, features/, decisions/, ...) and usually prefixed
with a date.

Why this script has to exist
---------------------------

Oldhand indexes files. Pointed at one of these repositories it would happily
create four records per entry: a CONTEXT with no summary, a CHANGES with no
context, and so on. It would not error. Every fragment would be individually
searchable and individually useless, and `stats` would report a healthy record
count. The failure would look exactly like success, which is why the
conversion is explicit rather than a scanning rule.

The mapping is close to exact, because the in-repo convention and Oldhand's body
structure were designed for the same job:

    SUMMARY.md                -> ## Summary
    CONTEXT.md + CHANGES.md   -> ## Knowledge
    TESTING.md + RISKS.md     -> ## Verification
    LINKS.md                  -> ## References
    FOLLOW_UP.md, ROLLBACK.md -> appended to ## Knowledge under their own heading

Ids are prefixed with the collection name. Oldhand requires ids to be unique
across the whole workspace, and three repositories independently naming an
entry `auth-fix` is not a hypothetical.
"""
from __future__ import annotations

import hashlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _overrides import (load_overrides, apply_status, extra_relations,
                        render_relations)
from from_markdown import parse_frontmatter

CATEGORY_TO_TYPE = {
    "fixes": "fix",
    "features": "feature",
    "decisions": "decision",
    "investigations": "investigation",
    "migrations": "migration",
    "refactors": "decision",   # documents a design change; only a couple exist
    "tickets": "investigation",
    "incidents": "incident",
}

KNOWLEDGE_FILES = ["CONTEXT.md", "CHANGES.md"]
VERIFY_FILES = ["TESTING.md", "RISKS.md"]
EXTRA_FILES = ["FOLLOW_UP.md", "ROLLBACK.md"]

TOPIC_WORDS = {
    "kafka": ["kafka", "topic", "partition", "consumer"],
    "mongodb": ["mongo", "cosmos", "bson"],
    "graphql": ["graphql", "resolver", "mutation", "query"],
    "auth": ["auth", "token", "scope", "policy", "role", "permission"],
    "testing": ["test", "coverage", "harness"],
    "ci": ["pipeline", "build", "ci", "sonar", "trivy"],
    "deployment": ["deploy", "release", "k8s", "helm", "pod"],
    "config": ["config", "setting", "appsettings", "env"],
    "api": ["api", "endpoint", "controller", "rest", "dto"],
    "data": ["schema", "model", "migration", "index", "repository"],
    "ui": ["ui", "angular", "grid", "screen", "component"],
    "contracts": ["contract", "procurement", "entitlement"],
    "catalog": ["catalog", "enrichment", "publisher", "approval"],
    "discovery": ["discovery", "scan", "agent", "inventory"],
}


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", value) or "entry"


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def clean_title(title: str) -> str:
    """Strip filing noise the author used inside the heading.

    Source headings carry the file's own name as a label: "SUMMARY: the Cosmos
    switch", "Batch approve/reject (backend) - SUMMARY". Harmless in a file
    called SUMMARY.md, actively harmful as a Oldhand title, which is the most
    heavily weighted field in the index. Every such title contributes the same
    meaningless token and competes on it.
    """
    title = re.sub(r"^\s*SUMMARY\s*[:\-\u2013\u2014]\s*", "", title, flags=re.I)
    title = re.sub(r"\s*[\-\u2013\u2014]\s*SUMMARY\s*$", "", title, flags=re.I)
    title = re.sub(r"^\s*SUMMARY\s+of\s+", "", title, flags=re.I)
    title = title.strip().strip("-\u2013\u2014 ").strip()
    return title


def strip_h1(text: str) -> tuple[str, str]:
    """Return (title-if-the-text-starts-with-one, remaining text)."""
    m = re.match(r"^#\s+(.+?)\s*$", text, re.M)
    if m and text.lstrip().startswith("#"):
        return clean_title(m.group(1).strip()), text[m.end():].strip()
    return "", text


def first_sentence(text: str, limit: int = 400) -> str:
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    body = re.sub(r"\s+", " ", body).strip()
    return body[:limit]


# Two spellings in the wild, and the colon is optional in one of them:
#   **Date:** 2026-08-11 - **Type:** feature
#   **Date** 2026-08-27 | **Ticket** #1234 | **Branch** feat/...
# Requiring the colon let the second form through, and those summaries
# then matched each other on shared boilerplate rather than on subject.
_META_LINE = re.compile(
    r"^\s*\**\s*(date|type|status|ticket|tickets|story|bug|task|branch|"
    r"pr|commit|merge|epic|author|owner|worktree|base|build|release|"
    r"phase)\b\**\s*[:|]?\s*\S",
    re.I)


def strip_metadata_block(text: str) -> str:
    """Drop a leading **Date:** / **Ticket:** header from a summary.

    These blocks are filing metadata, not content. Left in place they become
    the record's summary, which is what search ranks and displays, so the
    record competes on dates and PR numbers instead of on what it says. Every
    such record also looks similar to every other, because they share the same
    boilerplate vocabulary.
    """
    kept = []
    for block in text.split("\n\n"):
        stripped = block.strip()
        if not stripped:
            continue
        lines = [l for l in stripped.splitlines() if l.strip()]
        meta_lines = sum(1 for l in lines if _META_LINE.match(l.strip()))
        # A block is metadata if most of its lines are key: value pairs, or it
        # is a continuation of one (a wrapped PR link, say).
        if lines and (meta_lines / len(lines)) >= 0.5:
            continue
        if not kept and meta_lines:
            continue
        kept.append(stripped)
    return " ".join(" ".join(kept).split()).strip()


# Below this a summary is a label. The retrieval surface carries four times
# the weight of the body, so a fragment here costs the record its ranking.
MIN_SUMMARY_CHARS = 120


# A lead made only of a code span and a colon is a location, not a summary.
# A blockquote is an aside by convention: a warning, a digression, a quoted
# recommendation. It is in the record, not about it.
_BLOCKQUOTE = re.compile(r"^\s*>")

# A paragraph opening on a connective is a conclusion, and a conclusion read
# without its argument is not a summary. "Therefore: do NOT delete X yet" says
# nothing about what the record decided.
_CONNECTIVE = re.compile(
    r"^\s*\**\s*(therefore|so|however|but|thus|hence|note|caveat|"
    r"update|correction|warning)\b\s*[:,]",
    re.I)

# A bold label naming the section rather than its content. Harmless in place,
# wasteful at the front of a summary, where every record would start with the
# same three words.
_SECTION_LABEL = re.compile(
    r"^\s*\*\*\s*(what changed( and why it mattered)?|what was wrong|"
    r"what happened|the change|summary|background|context)\s*[.:]?\s*\*\*\s*[.:]?\s*",
    re.I)


def is_aside(block: str) -> bool:
    """True when a block is in the record but not about it."""
    return bool(_BLOCKQUOTE.match(block) or _CONNECTIVE.match(block))


_PATH_ONLY = re.compile(r"^\s*`[^`]+`\s*[:\-]?\s*$")


def _flatten(block: str) -> str:
    """One line of readable prose from a paragraph or a list.

    Fenced code contributes tokens and no meaning to a retrieval surface, so
    it is dropped rather than flattened.
    """
    block = block.strip()
    if block.startswith("```"):
        return ""
    block = re.sub(r"```.*?```", " ", block, flags=re.S)
    block = re.sub(r"^#{1,6}\s+", "", block, flags=re.M)
    items = re.findall(r"^\s*(?:[-*+]|\d+\.)\s+(.*)$", block, re.M)
    if items:
        return "; ".join(" ".join(i.split()) for i in items)
    return " ".join(_SECTION_LABEL.sub("", block).split())


def _extend_lead(lead: str, rest: str) -> str:
    """Grow a too-short lead using the blocks that follow it."""
    body = re.sub(r"^#{1,6}\s+.*$", "", rest, count=1, flags=re.M)
    out = "" if _PATH_ONLY.match(lead) else lead.rstrip()
    for block in body.split("\n\n"):
        block = block.strip()
        if not block or _META_LINE.match(block):
            continue
        # A path-only line is a location wherever it appears, not just as the
        # lead. Skipping it only at the front left it as the first thing
        # appended, which put a filename where the ranked subject belongs.
        if _PATH_ONLY.match(block) or is_aside(block):
            continue
        text = _flatten(block)
        if not text:
            continue
        out = (out + " " + text).strip() if out else text
        # Length is a floor, not a finish line: a summary that trails off on
        # a colon is still a fragment however long it is.
        if len(out) >= MIN_SUMMARY_CHARS and not out.rstrip().endswith(":"):
            break
    return " ".join(out.split())[:600]


def split_summary(text: str) -> tuple[str, str]:
    """Split SUMMARY.md into a short retrieval summary and the rest.

    Two reasons this is not just "take the whole file". A summary carrying its
    own `##` headings silently terminates Oldhand's `## Summary` section and
    produces an empty one, which validate catches but only after the fact. And
    a summary is the retrieval surface: it is what search displays and ranks,
    so a thousand words of it is not a summary at all.

    Everything before the first subheading becomes the summary. The remainder
    keeps its content under Knowledge, with headings demoted so they nest
    under it instead of competing with it.
    """
    parts = re.split(r"^##\s+", text, maxsplit=1, flags=re.M)
    lead = strip_metadata_block(parts[0])
    # A lead made only of asides is worse than no lead: it displaces the
    # summary with something that reads authoritative and is off-topic.
    if lead and all(is_aside(b.strip()) for b in parts[0].split("\n\n")
                    if b.strip() and not _META_LINE.match(b.strip())):
        lead = ""
    lead = _SECTION_LABEL.sub("", lead).strip()
    rest = ("## " + parts[1]).strip() if len(parts) > 1 else ""
    # A lead that trails off into what follows is an introduction, not a
    # summary. Keep reading until there is something to rank on.
    if rest and (len(lead) < MIN_SUMMARY_CHARS or lead.rstrip().endswith(":")):
        lead = _extend_lead(lead, rest)
    if not lead and rest:
        # The prose lives under the first heading. Take its opening paragraph
        # rather than the heading itself, which is usually "What changed".
        after = re.sub(r"^##\s+.*$", "", rest, count=1, flags=re.M).strip()
        para = next((b.strip() for b in after.split("\n\n")
                     if b.strip() and not _META_LINE.match(b.strip())), "")
        lead = " ".join(para.split())[:500]
    if not lead:
        lead = first_sentence(rest) or ""
    # Demote so nothing competes with Oldhand's own section headings.
    rest = re.sub(r"^(#{1,3})\s+", r"#### ", rest, flags=re.M) if rest else ""
    return lead, rest


def pick_topics(hay: str) -> list[str]:
    hay = hay.lower()
    found = [k for k, words in TOPIC_WORDS.items() if any(w in hay for w in words)]
    return found[:4] or ["general"]


def entry_date(name: str, fallback: Path) -> str:
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", name)
    if m:
        return f"{m.group(1)}T12:00:00+05:30"
    try:
        ts = datetime.fromtimestamp(fallback.stat().st_mtime, timezone.utc)
        return ts.astimezone().replace(microsecond=0).isoformat()
    except OSError:
        return datetime.now(timezone.utc).astimezone().replace(microsecond=0).isoformat()


def entry_identities(entries: list[Path], src: Path, dst: Path,
                     name: str) -> dict[Path, tuple[str, Path]]:
    prefix = f"lore_{slugify(name)}_".replace("-", "_")
    legacy = {}
    for entry in entries:
        relative = entry.relative_to(src)
        stem = slugify(re.sub(r"^\d{4}-\d{2}-\d{2}-", "", entry.name))
        path = dst / "memory" / relative.parts[0] / f"{stem}.md"
        legacy.setdefault(path, []).append(entry)

    existing = {}
    used_ids = set()
    used_paths = set()
    by_source = {entry.relative_to(src).as_posix(): entry for entry in entries}
    for path in sorted((dst / "memory").rglob("*.md")):
        used_paths.add(path)
        text = read(path)
        fields, body = parse_frontmatter(text)
        rid = fields.get("id")
        if not isinstance(rid, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+", rid):
            rid = None
        if rid:
            used_ids.add(rid)
        provenance = re.search(r"(?:\A|\n)Source entry: `([^`]+)`\s*\Z", body)
        entry = by_source.get(provenance.group(1)) if provenance else None
        if not provenance and path in legacy and rid:
            candidates = legacy[path]
            stem = path.stem.replace("-", "_")
            if rid == prefix + stem:
                entry = candidates[-1]
        if entry is not None and rid and entry not in existing:
            existing[entry] = (rid, path)

    result = {}
    claimed_ids = set()
    claimed_paths = set()
    for entry, (rid, path) in existing.items():
        if path not in claimed_paths:
            result[entry] = (rid if rid not in claimed_ids else None, path)
            claimed_ids.add(rid)
            claimed_paths.add(path)

    for entry in entries:
        relative = entry.relative_to(src)
        stem = slugify(re.sub(r"^\d{4}-\d{2}-\d{2}-", "", entry.name))
        base_id = prefix + stem.replace("-", "_")
        out_dir = dst / "memory" / relative.parts[0]
        rid, path = result.get(entry, (None, None))
        digest = hashlib.sha256(relative.as_posix().encode("utf-8")).hexdigest()[:12]
        if rid is None:
            rid = base_id
            suffix = 1
            while rid in used_ids:
                ending = digest if suffix == 1 else f"{digest}_{suffix}"
                rid = f"{base_id}_{ending}"
                suffix += 1
        if path is None:
            path = out_dir / f"{stem}.md"
            suffix = 1
            while path in used_paths:
                ending = digest if suffix == 1 else f"{digest}-{suffix}"
                path = out_dir / f"{stem}-{ending}.md"
                suffix += 1
        used_ids.add(rid)
        used_paths.add(path)
        result[entry] = (rid, path)
    return result


def main() -> int:
    if len(sys.argv) < 4:
        print("usage: from_repo_memory.py <repo-memory-dir> <collection-dir> <collection-name>")
        return 2
    src, dst, name = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    # Collections sit one level under the archive root.
    overrides = load_overrides(dst.parent)
    if not src.is_dir():
        print(f"no such directory: {src}", file=sys.stderr)
        return 1

    entries = [d for d in sorted(src.rglob("*"))
               if d.is_dir() and (d / "SUMMARY.md").is_file()]
    if not entries:
        print(f"{name}: no entry directories with a SUMMARY.md found", file=sys.stderr)
        return 1

    from collections import Counter
    kinds = Counter()
    identities = entry_identities(entries, src, dst, name)
    written = 0
    for d in entries:
        rel = d.relative_to(src)
        category = rel.parts[0]
        etype = CATEGORY_TO_TYPE.get(category, "investigation")
        kinds[etype] += 1

        summary_raw = read(d / "SUMMARY.md")
        title, after_title = strip_h1(summary_raw)
        summary_body, summary_rest = split_summary(after_title)
        dir_name = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", d.name)
        if not title:
            title = dir_name.replace("-", " ")
            title = title[0].upper() + title[1:]

        knowledge = []
        if summary_rest:
            knowledge.append("### From the summary\n\n" + summary_rest)
        for fn in KNOWLEDGE_FILES:
            text = read(d / fn)
            if text:
                knowledge.append(f"### {fn[:-3].title().replace('_', ' ')}\n\n{text}")
        for fn in EXTRA_FILES:
            text = read(d / fn)
            if text:
                knowledge.append(f"### {fn[:-3].replace('_', ' ').title()}\n\n{text}")
        # Anything else the author added that this script does not know about.
        known = set(KNOWLEDGE_FILES + VERIFY_FILES + EXTRA_FILES) | {"SUMMARY.md", "LINKS.md"}
        for f in sorted(d.glob("*.md")):
            if f.name not in known:
                text = read(f)
                if text:
                    knowledge.append(f"### {f.stem.replace('_', ' ').title()}\n\n{text}")

        verification = []
        for fn in VERIFY_FILES:
            text = read(d / fn)
            if text:
                verification.append(f"### {fn[:-3].title()}\n\n{text}")

        references = read(d / "LINKS.md")

        when = entry_date(d.name, d / "SUMMARY.md")
        hay = f"{title} {summary_body} {' '.join(rel.parts)}"

        rid, out_path = identities[d]
        out_path.parent.mkdir(parents=True, exist_ok=True)

        lines = ["---", "schema_version: 1", f"id: {rid}", f"type: {etype}",
                 f"status: {apply_status(rid, 'current', overrides)}",
                 "importance: normal", "scope: repository",
                 "risk: medium", "durability: long_lived", "evidence: documented",
                 "topics:"]
        lines += [f"  - {t}" for t in pick_topics(hay)]
        lines += [f"created_at: {when}", f"updated_at: {when}", "expires_at: null"]
        lines += render_relations(extra_relations(rid, overrides))
        lines += ["---", "",
                  f"# {title}", "", "## Summary", "",
                  summary_body or first_sentence(summary_raw) or title, "",
                  "## Knowledge", ""]
        lines.append("\n\n".join(knowledge) if knowledge else "See the summary above.")
        lines += ["", "## Verification", ""]
        lines.append("\n\n".join(verification) if verification else "Not recorded.")
        lines += ["", "## References", ""]
        if references:
            lines.extend([references, ""])
        lines.append(f"Source entry: `{rel.as_posix()}`")
        lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")
        written += 1

    print(f"{name}: {written} entr(y/ies) from {len(list(src.rglob('*.md')))} source file(s)")
    print("   " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
