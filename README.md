<div align="center">

# Lore

**Durable engineering memory for coding agents.**

The constraint nobody wrote down. The approach that looks obvious and fails.<br/>
The reason something surprising is the way it is.

<br/>

[![version](https://img.shields.io/badge/version-0.4.3-bc8cff?style=flat-square&labelColor=0d1117)](https://github.com/IotA-asce/lore)
[![license](https://img.shields.io/badge/license-MIT-3fb950?style=flat-square&labelColor=0d1117)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-58a6ff?style=flat-square&labelColor=0d1117)](tools/lore/requirements.txt)
[![dependencies](https://img.shields.io/badge/dependencies-1-8b949e?style=flat-square&labelColor=0d1117)](tools/lore/requirements.txt)
[![network](https://img.shields.io/badge/network-none-39c5cf?style=flat-square&labelColor=0d1117)](#quickstart)
[![findability](https://img.shields.io/badge/findability-99%25-3fb950?style=flat-square&labelColor=0d1117)](#how-records-are-written-beats-how-they-are-ranked)

</div>

<br/>

An agent works inside a bounded session. Whatever it determines during that
session is discarded when the session ends, and the same determination is then
made again, at the same cost, by the same agent with no memory of having made
it.

Lore keeps that knowledge, ranks it so the piece that matters surfaces when
its subject comes up, and retires it when it stops being true. It is a folder
of Markdown plus a search tool that decides which records you should see.

![Architecture: Markdown is canonical, the SQLite index is derived](docs/img/architecture.svg)

The dependency points one way, and that is the whole design. The Markdown is
the archive; the index is a cache. Delete the database and you lose nothing:
your records stay readable, editable, diffable and reviewable with ordinary
tools, with or without Lore installed.

**Recency carries no authority.** A two-year-old invariant outranks last
week's debugging note when both match. Age is evidence of durability, not of
irrelevance, and this is the opposite of most memory systems.

### What it deliberately does not hold

| Question | Answered by |
|---|---|
| which commit changed this | Git, CI, tickets |
| how does it work today | `documentation/` |
| what am I doing right now | `implement/` |
| **what should I know before touching this** | **`memory/`, which is Lore** |

Only the last one is Lore's. If Git, tests or current documentation already
preserve something cheaply, they will do it better and stay current for free.
A routine bug fix should produce no record at all.

<br/>

## The part that took measuring

Everything below was measured on a real archive of 293 records across four
collections, migrated from two memory systems in daily use at a commercial
software organisation. Three of these findings were counter-intuitive enough
that we got them wrong first, and only measurement exposed it.

### A label on everything ranks nothing

![recall@5 collapsing from 92 percent to 17 percent as importance labels inflate](docs/img/inflation.svg)

Curation metadata is added to improve retrieval. Past a low threshold it
destroys it.

The cause was arithmetic rather than a tuning accident. `critical` importance
plus `critical` risk plus `invariant` durability summed to exactly the entire
text-relevance range, so a record carrying those labels and **no textual
relevance whatsoever** tied a record that matched the query perfectly.

Nothing in the design resisted inflation either. Labels are assigned once, at
write time, by an author with no feedback about whether their previous labels
were well calibrated, and there is no review, decay or quota anywhere in the
lifecycle. Inflation is the expected steady state rather than a risk. Every
author believes their own finding is important, which is not a failure of
discipline but a property of the position they write from.

So the budget is structural rather than advisory:

![Text relevance caps at 60, all metadata combined caps at 44](docs/img/budget.svg)

Damage starts well before an archive looks inflated. With only **four**
critical records out of 293, seven unrelated records were being displaced from
first place on queries about entirely other subjects.

### Read the collections, not the average

![Per-collection recall, from 100 percent down to 50 percent](docs/img/collections.svg)

An archive can average 80% while one collection sits at 50% and another at
100%. The average sends you to tune the ranker when the real problem is the
summaries in one repository.

It also shows why `recall@1` is the wrong optimisation target for an interface
that returns five ranked summaries. A reader scanning five results is
indifferent to whether the answer came first or second, and chasing `recall@1`
against a finite query set is the one reliable way to make the number stop
meaning anything.

### Your first pass of any heuristic mostly measures itself

![29 items flagged, 4 genuine defects, 13.8 percent precision](docs/img/precision.svg)

This is not an argument against the checks. The four genuine defects included
records whose summaries asserted claims their own bodies had explicitly
retracted, which nothing else would have surfaced, and which is the most
dangerous state a record can occupy: search displays the summary, so the
retraction is invisible to anything that does not open the record, and the
result is indistinguishable from a confident correct answer.

It is an argument for treating a first-pass report as a list of things to read
rather than a list of things to fix.

> A wrong detection costs a minute of reading. A wrong resolution costs
> knowledge, silently, and you find out months later when someone confidently
> repeats a mistake you already solved.

One cause of false positives is specific to engineering corpora: **the
vocabulary of staleness is the domain vocabulary.** Contracts supersede one
another, packages are deprecated, models become outdated, and
`ContractStatus.Superseded` is an enum value. Matching the announcement form
rather than the token took one detector from 102 false positives to 0.

### How records are written beats how they are ranked

| intervention | effect |
|---|---|
| stop admitting metadata blocks as summaries | 126 records fixed |
| index sections as well as whole records | secondary findings 36% -> 82% |
| split code identifiers into words | two collections to 100% recall@1 |
| rewrite **one** weak summary | that record: unfindable -> rank 1 |
| **three rounds of ranker tuning** | one collection's recall@1: **zero change** |

Large records were never the problem. Findability by size was 98% for the
smallest records and 94% above 4,000 tokens. What failed was reaching a
record's *fourth* finding: a record is one indexable unit however many things
it says, so its fourth finding competes using the whole document's vocabulary
and loses.

Splitting them would have been the wrong fix. Splitting is irreversible, and
the grouping is information: a record gathering five findings under one
investigation is asserting they belong together. Indexing each section
separately, and deduplicating by record at query time, took sub-document
reachability from 36% to 82% without touching a single record.

![Before and after across recall@1, recall@3, recall@5, MRR and reachability](docs/img/beforeafter.svg)

This is why `WRITING_RECORDS.md` is the document that matters most here, and
why it is short.

<br/>

## What we are doing, and the end goal

![Stage one complete, stage two running now, stage three the goal](docs/img/stages.svg)

Every number above came from one archive, in one organisation, in one domain.
No amount of further work on that archive can fix that, because its author
cannot forget that it exists. So Lore measures itself, in a form that is safe
to hand to a stranger.

```
lore 0.4.2   2026-09-15T00:59:42+05:30

  records            293 across 4 collection(s)
  index rows         3751 (12.8 per record)
  record tokens      p50 2070  p90 5704  max 13439
  critical share     4/293 (1%)

  searches           47 over 9 day(s) (5.2/day)
  found nothing      6%
  archive coverage   31% of records returned at least once
  open rate          22% of returned records were opened
```

Any command appends one snapshot per day to `metrics/daily.jsonl`, silently,
and it can never fail a command. `lore metrics --full --export mine.json`
bundles the history into a file you can send. It carries counts, rates,
percentiles and scores, and never titles, ids, paths, summaries, query text,
topic names or collection names.

That is **enforced, not promised**: before writing, every string value in the
bundle must be a version, a timestamp, a platform name or a schema value, and
the export refuses to write and names the field if it is not. On the
293-record archive the bundle contained eleven string values in total.
Everything else was numbers, and a count cannot carry a sentence.

### The questions a single archive cannot answer

- Does the importance budget hold when the writer is not the person who
  designed the rule?
- Does the zero-result rate fall with archive size, or rise?
- Is the section-match discount right for archives whose records are short?
- What share of records does a healthy archive never retrieve? Nobody knows.
  It might be 70% and fine.
- **Does anything reach for search without being told to?**

The last one decides whether any of this matters. An archive that is never
queried is irrelevant however good its ranking is, and it is exactly the
question the author of an archive can never answer about their own.

If you are trying Lore, two weeks of ordinary use and one export is the most
useful thing you can do for it. Not a clean archive, not a demonstration: the
real one, including the days you forgot it existed.

<br/>

## Quickstart

```bash
python -m pip install -r tools/lore/requirements.txt
python tools/lore/lore.py rebuild
python tools/lore/lore.py search "my consumer test passed but nothing ran"
```

That last command returns a record whose title shares almost no words with the
question. That is the whole product.

Then make it a real command, because the gap between `lore search` and a
forty-character invocation is most of what decides whether anyone searches on
a hunch, and searching on a hunch is the behaviour the whole system depends
on:

```bash
python tools/install.py /path/to/your/archive
```

```bash
lore search "why did the consumer test pass without running"
lore new --type constraint --importance high --title "..."
lore doctor        # can every record be found by its own subject?
lore conflicts     # does anything contradict itself?
lore metrics       # is this archive earning its keep?
```

Nothing is installed system-wide, nothing needs administrator rights, and
there is no server, no account and no network access at any point.

<br/>

## Two honest caveats

**Nothing makes anything search.** Retrieval depends on something choosing to
run it. Give your agent a concrete trigger rather than a judgement call:
*search before non-trivial work, and whenever something is surprising or looks
like it has been hit before.* Asking someone to search "when history might
matter" asks them to suspect the trap before looking, and the traps worth
recording are the ones nobody suspects.

**`compact` and `supersede` are not implemented.** Nothing yet stops an
archive accumulating stale records at scale. `validate` catches a half-finished
retirement and `conflicts` finds contradictions, so the manual path works, but
this is the known gap.

<br/>

## Where to go next

| file | what it answers |
|---|---|
| `START_HERE.md` | the five-minute version |
| `WRITING_RECORDS.md` | **read this second.** How to write a record people can find |
| `INSTALL.md` | getting `lore` onto your PATH, and undoing it |
| `RECONCILING_AN_EXISTING_ARCHIVE.md` | merging notes you already have |
| `LESSONS.md` | what building this taught us, and what it cost to learn |
| `METRICS.md` | what is measured, and what is shared |
| `tools/lore/CLI_SPEC.md` | every command, and why it behaves as it does |
| `memory/SCHEMA.md` | the record format |

Lore is tool-agnostic. `AGENTS.md` is the portable entry point and `CLAUDE.md`
is a thin Claude Code adapter; other harnesses need only the smallest adapter
that makes them discover the canonical rules.

The figures above are generated from the measured numbers by
`docs/charts.py`, so a figure cannot drift away from the result it shows.

<div align="center"><br/>

MIT licensed.

</div>
