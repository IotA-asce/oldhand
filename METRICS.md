# Metrics

Every number in this repository came from one archive. That is the honest
limit of what is known about Lore, and the only way past it is archives that
are not this one.

So Lore measures itself, in a form that is safe to hand to a stranger.

## What happens automatically

Any `lore` command appends one snapshot per day to `metrics/daily.jsonl` and
moves on. It is pure SQL and a line count, it costs nothing noticeable, and it
never raises: if it fails, your command still works.

This is automatic on purpose. Daily metrics that depend on someone remembering
to run a command are not daily metrics.

## Looking at it

```bash
lore metrics          # today, at a glance
lore metrics --full   # plus findability and eval, several hundred searches
```

```
lore 0.4.0   2026-09-15T00:59:42+05:30

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

The four retrieval lines are the ones that decide whether the archive is
working:

- **searches per day** near zero means nothing reaches for it, and ranking
  quality is then irrelevant;
- **found nothing** above roughly 15% means queries and records are using
  different vocabulary;
- **coverage** is the share of records anything has ever returned. A record
  nothing retrieves costs tokens to write, adds noise to every ranking
  afterwards, and has never been useful;
- **open rate** near zero means summaries are not earning the click, or are so
  good that nobody needs the record. `lore usage` separates those.

Read coverage patiently. Early on it only means "nobody has asked yet", which
is why `lore usage` withholds its never-retrieved verdict until 50 searches.

## Sharing it

```bash
lore metrics --export mine.json
```

Then send the file. That is the whole protocol.

### What it contains

Counts, rates, percentiles and scores. Specifically:

- archive shape: record and collection counts, collection **sizes**, index
  rows, token and summary-length percentiles, distributions across every
  schema dimension
- retrieval: searches, shows, active days, zero-result rate, coverage, open
  rate
- health: findability, thin summaries, invalid records
- eval scores, if you keep an eval set
- Lore version, Python version, operating system name

### What it never contains

Record titles, ids, paths, summaries, bodies. Query text. Topic names.
Collection names. File names, usernames, hostnames, absolute paths.

Topic and collection names are excluded specifically because they describe a
company's products and team structure more precisely than almost anything else
in an archive.

### Why you can believe that

Because it is enforced, not promised. Before writing, the export checks every
string value in the bundle against a rule: it must be a version, an ISO
timestamp, the platform name, a schema enum, or the fixed disclosure note.
Anything else and it refuses to write and names the offending field.

On a 293-record archive the resulting bundle contained **eleven string
values** in total. Everything else was numbers. A count cannot carry a
sentence.

The file is also plain, indented JSON, deliberately short enough to read
before you send it. A privacy guarantee nobody can verify is not a guarantee,
so read it. If you find anything in there that identifies your work, that is a
bug in Lore and worth reporting on its own.

## What would actually help

If you are trying Lore, the useful thing is two weeks of ordinary use and then
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
