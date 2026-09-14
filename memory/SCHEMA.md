# Memory Record Schema v1

A normal memory record is one Markdown file with frontmatter.

```yaml
---
schema_version: 1
id: mem_<generated>
type: decision
status: current
importance: high
scope: subsystem
risk: high
durability: long_lived
evidence: documented
topics:
  - authentication
created_at: <generated>
updated_at: <generated>
expires_at: null
relations: {}
---
```

## Type

- `topic_summary`
- `decision`
- `constraint`
- `fix`
- `investigation`
- `migration`
- `incident`
- `lesson`
- `reference` - a durable pointer rather than a finding: where something
  lives, which endpoint answers, what the connection details are. Use it when
  the value is the location, not the insight.
- `feature` - a record of something built: what it does, where it lives, and
  what constrained it. Use it when the durable value is the capability, not
  the decision behind it.

## Status

- `current`
- `resolved`
- `superseded`
- `deprecated`
- `historical`

## Importance

- `critical` - missing this record probably breaks something. Rare by design;
  see the budget rule in `agent/MEMORY_POLICY.md`.
- `high`
- `normal`
- `low`

## Scope

- `workspace`
- `repository`
- `subsystem`
- `feature`
- `local`

## Risk

- `critical`
- `high`
- `medium`
- `low`
- `none`

## Durability

- `invariant`
- `long_lived`
- `situational`
- `temporary`

## Evidence

- `verified` - checked by running something
- `documented` - stated by a source of record
- `observed` - seen once, not re-checked
- `inferred` - reasoned, not confirmed

Evidence contributes to retrieval ranking. It is the one dimension that is
checkable when the record is written rather than guessed, so claiming
`verified` for something merely read is a direct corruption of ranking.

## Relations

```yaml
relations:
  supersedes:
    - mem_old_record
```

Valid types: `supersedes`, `depends_on`, `related_to`, `caused_by`,
`contradicts`.

Targets must resolve to a record id in the workspace, and a record may not
reference itself.

A `supersedes` target must already carry status `superseded` or `deprecated`.
Declaring supersession without retiring the target is a validation error.

## Body

Prefer:

```markdown
# Title

## Summary

Short retrieval-oriented summary.

## Knowledge

What a future engineer or agent needs to know.

## Verification

Evidence, if relevant.

## References

Pointers to source, Git, PRs, tickets, docs, commands, or other records.
```

Avoid repeating implementation details that are obvious from code or Git.
