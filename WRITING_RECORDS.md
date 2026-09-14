# Writing records people can find

Most of what makes an archive useful happens when a record is written, not
when it is searched. A perfectly ranked search over badly written records
returns badly written records.

This is the shortest set of rules that produced a measurable difference on a
real 293-record archive, with the before and after of each.

---

## 1. Write the summary for the question, not the artifact

`## Summary` is the retrieval surface. It is weighted six times more heavily
than the body, it is what search displays, and it is often the only part
anything reads. Everything else in the record is for the person who has
already decided to open it.

So the summary answers the question someone will ask. It does not describe the
work you did.

```diff
- **Date:** 2026-08-11 · **Type:** feature · **Tickets:** #1074
- **Branch:** `feat/publisher-table-extension` -> merged via PR !672
+ 42 new publisher mappings and one family rule, taking deterministic
+ publisher coverage from 12,738 rows to 16,141 of 19,833. No model at runtime.
```

On that archive, **126 of 176 records** opened with a metadata block like the
one above. Their summaries ranked on dates and branch names, so every one of
them competed against every other on identical boilerplate.

## 2. Six ways a summary fails, all of which look fine while writing

| Written | What it says to a searcher |
|---|---|
| `**Date:** 2026-09-04 **Type:** fix **PR:** !594` | nothing; every record says this |
| `Three things, in one commit:` | nothing; the content is below |
| `` `Catalog.WebApi/Configuration.cs`: `` | a location, not a finding |
| `**What changed.** The picker now...` | three wasted words in the most weighted position |
| `> **A recommendation this work overturned.** ...` | an aside, displacing the summary |
| `**Therefore: do NOT delete `legacy-main` yet.**` | a conclusion without its argument |

Each is a reasonable thing to write somewhere in a record. None of them is the
sentence that says what the record is about.

## 3. Use the words a stranger would use

Write the terms someone reaching for this knowledge would type, not only the
terms your team settled on.

```diff
- The header-filter pickers on the catalog grids now offer one option
- per case-insensitively distinct value.
+ The header-filter pickers (the column filter dropdowns) on the catalog grids
+ no longer show a duplicate entry per casing and now offer one option per
+ case-insensitively distinct value.
```

"Pickers" is what the team calls them. "Dropdown" and "duplicate" are what
someone hitting the bug will search for.

**A standing example of this failing.** One record says *vars file*, *env_vars*
and *keys*. A search saying *"I added one variable and the deployment lost its
other settings"* finds nothing, because the two share no distinctive term. No
ranking work fixes that. Only the writer can.

## 4. Spell out identifiers at least once

Search tokenizers split on punctuation and nothing else, so `totalCost` is one
token. The words "total" and "cost" **do not match it**:

```
"totalcost"  -> MATCH
"total"      -> no match
"cost"       -> no match
```

Lore indexes identifiers by their parts as well as whole, which handles most
of this. Help it anyway: the first time an identifier appears in a summary,
say what it is in words too. `totalCost`, the stored purchase total.

## 5. Say what is distinctive, not what is true

An accurate summary that could describe twenty neighbouring records will lose
to all of them.

```diff
- A mapped feature link can now say "any version", and the entitlement keeps
- matching when the vendor renumbers the feature.
+ A mapped feature link can now say "any version", and the entitlement keeps
+ matching when the vendor renumbers the feature. Before this every entitlement
+ was tied to one fixed version, so a vendor version bump silently broke the
+ match. Versionless entitlements remove that coupling.
```

The first version is true and was unfindable: 28 of 95 records in that
collection mention "entitlement". The second names the thing that is only true
of this record. It went from not being returned at all to rank 1.

## 6. Lead with what is true now

When a record is corrected, the correction goes in the summary. A body that
retracts a claim the summary still makes is the worst state a record can be
in: search shows the summary, so the retraction is invisible to anything that
does not open the record, and it reads exactly like a confident right answer.

```diff
- validation runs before auth, so field probing proves which build a pod runs;
- kubectl and the saved dashboard host both dead-end
+ validation runs before auth, so field probing proves which build a pod runs.
+ CORRECTED 2026-08-10: both DEV dashboards DO work, via the Rancher-style
+ `/dashboard/api/v1` prefix; only the PROD dashboards dead-end.
```

`lore conflicts` finds these. Fixing them is manual, because only the author
knows which sentence still holds.

## 7. Importance is a budget, not a compliment

`critical` means an agent that misses this record will probably break
something. It does not mean the finding was hard-won.

Measured: retrieval recall fell from 92% to 33% once a quarter of records
carried a `critical` label. A label on everything ranks nothing. Expect
`critical` to stay in single digits as a percentage of the archive, and when
torn between two levels, take the lower one. A record that deserved `critical`
and got `high` still surfaces.

## 8. Group by subject, not by size

Do not split a record because it got long. Sections are indexed separately, so
a question about a record's fourth finding still reaches it, and a record that
gathers five findings under one investigation is asserting they belong
together, which is information.

Split when a record covers subjects that genuinely do not belong together.
That is a judgement about the knowledge, never about a token count.

## 9. Do not write the record at all, usually

The gate is not "is this interesting". It is:

> Would forgetting this make someone repeat an expensive discovery, violate a
> non-obvious constraint, misunderstand business behaviour, repeat a failed
> approach, or lose an important rationale?

If code, tests, Git history or current documentation already preserve it
cheaply, they will do it better and stay current for free. A routine fix
should produce no record.

---

## Checking your own writing

```bash
lore doctor
```

- **findability** queries every record by its own title. A record that cannot
  be returned first for its own title will not be found by a question phrased
  in other words, and the report names what beat it.
- **thin summaries** are too short to rank on anything.
- **summaries that only restate the title** carry no information the title did
  not already carry.

```bash
lore conflicts
```

- summaries that no longer match their own corrected bodies
- records declaring themselves stale while still marked current
- near-duplicate subjects, which usually want merging or linking

Neither command changes anything. Both are wrong sometimes: on the archive
they were built against, 29 flagged items contained 4 real defects. Read the
record before acting on the report.
