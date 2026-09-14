# Durable Memory Policy

## Purpose

Memory preserves knowledge that future agents cannot cheaply or reliably reconstruct
from source code, Git history, tests, current documentation, tickets, or CI evidence.

Memory is not a development diary.

## Memory-worthiness gate

Create durable memory when forgetting the knowledge could cause:
- expensive rediscovery;
- repetition of a failed approach;
- violation of a non-obvious invariant;
- misunderstanding of product or business behavior;
- migration, security, reliability, or compatibility risk;
- loss of important architectural rationale;
- confusion caused by behavior that appears redundant or surprising.

Otherwise do not create a memory entry.

## Canonical storage

Markdown under `memory/` is canonical.

Generated SQLite/FTS indexes are disposable derived state.

A workspace may hold one archive per repository. Records are addressed by an id
that must be unique across the whole workspace.

## Writing a record

Create records with `lore new`, not by hand. The tool owns the bookkeeping
(id, timestamps, file location, required headings); the model owns the
knowledge. Hand-written frontmatter is the main source of records that fail
validation and therefore never become searchable.

## Retiring a record

Superseding is two edits, not one: the new record declares
`relations: {supersedes: [<old-id>]}` **and** the old record's status becomes
`superseded`. `lore validate` treats a half-finished supersession as an
error, because otherwise the replaced record keeps outranking the record that
replaced it and nothing ever says so.

## Retrieval

Use ranked search first. Retrieve full records only after a summary or metadata hit
demonstrates relevance.

Normal retrieval should exclude `superseded` and `deprecated` records.

## Topic summaries

`memory/topics/` contains current distilled knowledge.

Historical records preserve provenance; topic summaries preserve the current mental
model.

Do not compact after every task. Compact when history becomes expensive to retrieve
or when a major decision changes current truth.

## Importance and trust

Use the schema in `memory/SCHEMA.md`.

Importance, status, scope, risk, durability, and evidence are independent dimensions.
Do not use recency as a substitute for importance.

### Importance is a budget, not a compliment

`critical` means: an agent that misses this record will probably break
something. It does not mean the finding was hard-won, or surprising, or that
you are pleased with it. Every agent believes its own discovery is critical,
and nothing in the tooling can tell the difference.

This matters because the label is spent from a shared pool. Measured on a
117-record archive, retrieval recall fell from 92% to 33% once a quarter of
the records carried a `critical` label, because a label that is on everything
ranks nothing. If a plausible reading of the archive is "most of this is
critical", the labels have stopped carrying information and the archive has
quietly lost its ranking.

Expect `critical` to be rare: single digits as a percentage of the archive.
When unsure between two levels, take the lower one. A record that deserved
`critical` and got `high` still surfaces; a hundred records that took
`critical` because it felt right surface nothing.
