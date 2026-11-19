# Metrics

Every number in this repository came from one archive. That is the honest
limit of what is known about Oldhand, and the only way past it is archives that
are not this one.

So Oldhand measures itself, in a form that is safe to hand to a stranger.

## What happens automatically

Archive commands record one snapshot per day in `metrics/daily.jsonl` and
moves on. It is pure SQL and a line count, it costs nothing noticeable, and it
never raises: if it fails, your command still works.
Offline guides and setup previews do not need or create archive metrics.

This is automatic on purpose. Daily metrics that depend on someone remembering
to run a command are not daily metrics.

## Looking at it

```bash
oldhand metrics          # today, at a glance
oldhand metrics --full   # plus findability and eval, several hundred searches
```

Historical example from 0.4.2 (the unreleased source clarifies these labels below):

```
oldhand 0.4.2   2026-09-15T00:59:42+05:30

  records            293 across 4 collection(s)
  index rows         3751 (12.8 per record)
  record tokens      p50 2070  p90 5704  max 13439
  summary chars      p50 335  thin 0
  critical share     4/293 (1%)

  searches           47 over 9 day(s) (5.2/day)
  found nothing      6%
  archive coverage   31% of records returned at least once
  open rate          22% of returned records were opened
```

Retrieval totals cover the **available retrieval log**, not an assumed complete
lifetime or a selected observation window. They describe observed retrieval;
they do not establish whether the archive improved task outcomes:

- **searches per day** near zero means nothing reaches for it, and ranking
  quality is then irrelevant;
- **found nothing** above roughly 15% means queries and records are using
  different vocabulary;
- **coverage** is the share of currently indexed records returned in the available
  log. Missing retrieval evidence does not establish that a record is useless;
- **distinct open rate** is the fraction of distinct returned records that also
  have a show event in that log. It is not a per-search click-through rate and
  does not prove that a particular result caused a later opening.

The unreleased source prints exact empty-search and distinct-open numerators
and denominators. Rates retain their precision in JSON; a nonzero rate smaller
than 0.01% prints `<0.01%` instead of an exact zero. An unavailable denominator
prints `N/A`, while no searches yields a null rate in the snapshot.

Read coverage patiently. Early on it only means "nobody has asked yet", which
is why `oldhand usage` withholds its never-retrieved verdict until 50 searches.

## Sharing it

```bash
oldhand metrics --export mine.json
```

Then send the file. That is the whole protocol.

### What it contains

Counts, rates, percentiles and scores. Specifically:

- archive shape: record and collection counts, collection **sizes**, index
  rows, token and summary-length percentiles, distributions across every
  schema dimension
- retrieval: searches, shows, active days, empty-search count/rate, coverage,
  distinct returned/opened record counts and distinct open rate
- health: findability, thin summaries, invalid records
- eval scores, if you keep an eval set
- Oldhand version, Python version, operating system name

### Export versions and remaining scope

New snapshots use `schema: 2`, and new bundles use `metrics_schema: 2`. The
additive retrieval fields are `zero_result_searches` and
`distinct_records_opened`. Schema-1 daily snapshots, including the legacy
`lore_version` spelling, remain readable and retain their original fields in
exported history. Export does not rewrite old history to add missing counters.

The additive provenance fields are `log_available`, `valid_events`,
`malformed_events`, `blank_lines`, `first_event_date`, and `last_event_date`.
Missing and present-but-empty logs are distinguished. Bounds are the earliest
and latest accepted calendar-date prefixes, irrespective of file order; they
are not timezone-normalized timestamps, a selected window, or lifetime bounds.
Date-only legacy events remain accepted. A valid event has search/show action,
a real ISO calendar-date prefix, and a list of string returned IDs. Blank lines
are separate from malformed JSON, non-object rows, unsupported actions and
invalid shapes/dates. Legacy rows with ignored extra fields are supported.
No accepted events means null bounds, including an all-malformed log.
The CLI prints these counts and bounds even when there were no searches.

TODO for subsequent R2 slices: explicit observation-window filters and
missing-snapshot coverage diagnostics. This slice does not claim complete log history or infer inactivity
from missing snapshots.

### What it never contains

Record titles, ids, paths, summaries, bodies. Query text. Topic names.
Collection names. File names, usernames, hostnames, absolute paths.

Topic and collection names are excluded specifically because they describe a
company's products and team structure more precisely than almost anything else
in an archive.

### Why you can believe that

Because it is enforced, not promised. Before writing, the export checks every
string value in the bundle against a rule: it must be a version, an ISO
date or timestamp, the platform name, a schema enum, or the fixed disclosure note.
Anything else and it refuses to write and names the offending field.

On a 293-record archive the resulting bundle contained **eleven string
values** in total. Everything else was numbers. A count cannot carry a
sentence.

The file is also plain, indented JSON, deliberately short enough to read
before you send it. A privacy guarantee nobody can verify is not a guarantee,
so read it. If you find anything in there that identifies your work, that is a
bug in Oldhand and worth reporting on its own.

## What would actually help

If you are trying Oldhand, the useful thing is two weeks of ordinary use and then
one export. Not a clean archive, not a demonstration: the real one, including
the days you forgot it existed.

The questions that cannot be answered from a single archive:

- Does the importance budget hold when the writer is not the person who
  designed the rule?
- Does the zero-result rate fall with archive size, or rise?
- Is the section-match discount right for archives whose records are short?
- What share of records does a healthy archive never retrieve? Nobody knows.
  It might be 70% and fine.
- Does anything reach for search without being told to?

The last one matters most and is the one a single archive can never answer,
because its author cannot forget that the archive exists.
