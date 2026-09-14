# What building this taught us

Everything here was measured on a real archive of 293 records across four
collections, migrated from two existing memory systems. Each entry cost
something to learn. They are recorded because most of them are not obvious
beforehand and several are actively counter-intuitive.

If you are adopting Lore, the first four will save you the most time.

---

## 1. The summary is the whole game

Retrieval quality tracked summary quality far more closely than it tracked
anything in the ranker. The interventions that moved the numbers most were all
about what the summary said:

| change | effect |
|---|---|
| stop putting metadata blocks where summaries go | 126 records fixed |
| index sections as well as whole records | secondary findings 36% -> 82% |
| split code identifiers into words | two collections to 100% recall@1 |
| rewrite one weak summary | that record: unfindable -> rank 1 |

Three rounds of ranker tuning, by contrast, moved one collection's recall@1 by
exactly zero. See `WRITING_RECORDS.md`.

## 2. A label on everything ranks nothing

Importance inflation is the failure a memory archive is most likely to suffer
and least likely to notice, because every record was written by someone who
thought it mattered.

Measured, holding everything else constant:

```
share of archive marked critical:   0%    10%    25%    50%
recall@5:                          92%    67%    33%    17%
```

It collapses early. At a quarter critical, retrieval is worse than it was at
zero with no metadata at all. And the damage is not limited to inflated
archives: with only **four** critical records out of 293, seven other records
were being beaten by one of those four on unrelated queries.

Lore now caps every metadata boost below the text-relevance range and warns
above 10% critical. The discipline still has to come from the writer.

## 3. Automate detection, never resolution

An early version of `lore conflicts` auto-retired records whose text announced
they were stale. It seemed obviously safe: the record had already decided, the
metadata had simply not caught up.

On real data it was **wrong on two of its four candidates**. One read
`OUTDATED HEADLINE, KEPT FOR THE HISTORY`, deliberately preserved because the
failure was instructive. Another read `SUPERSEDED ... Still true: no other
method works`. Retiring either would have removed working knowledge from every
default search, silently.

The distinction between "announces staleness" and "should be retired" is
authorial intent, and no pattern recovers it.

> A wrong detection costs a minute of reading. A wrong resolution costs
> knowledge, silently, and you find out months later when someone confidently
> repeats a mistake you already solved.

## 4. In an engineering archive, the vocabulary of staleness is the domain vocabulary

Three separate false-positive waves came from this. Contracts *supersede* each
other. Packages are *deprecated*. Models become *outdated*. `ContractStatus.Superseded`
is an enum value. "The superseded push-registration model" is an adjective.

Substring matching cannot work here, and no amount of tightening the word list
helps, because the words are correct: they are simply being used about the
subject rather than about the record.

The fix is to match the **announcement**, not the word: capitals, at the start
of a line, dated or introduced with a colon. A record correcting itself says
so loudly. A record discussing a deprecated API does not.

## 5. Measure with two independent signals or you are fitting to one

A hand-written eval set is biased twice over: toward the collections someone
cared about, and toward the records they remembered existed. Optimising it
alone tunes the system to the query list.

Lore therefore has two:

- **eval** : hand-written questions with known answers. Question-shaped, biased.
- **findability** : every record queried by its own title. Unbiased, complete,
  needs no ground truth, cannot be gamed by writing friendly queries.

Every tuning decision here was checked against both. One candidate improved
eval and degraded findability; it was fitted to the measure, not to retrieval,
and was discarded. A third signal (can a record's internal findings be
reached?) caught a change that helped both while quietly undoing the feature it
was meant to support.

## 6. Recall@1 is the wrong target for an interface that returns five results

One collection sat at 50% recall@1 and 100% recall@3. Three rounds of work
moved recall@1 by nothing, because the "failures" were near-ties among
genuinely related records losing by two or three points out of eighty.

A reader scanning five ranked summaries does not care whether the answer was
first or second. Chasing recall@1 against a finite query set is the one
reliable way to make the number stop meaning anything.

## 7. Retrieval granularity should not dictate how knowledge is filed

Large records looked like the problem: 135 of 293 were over 2,500 tokens. They
were not. Records were perfectly findable by their own subject regardless of
size (94% at 4,000+ tokens against 98% for the smallest).

What failed was reaching a record's *fourth* finding: only 36% of internal
findings returned their own record. A record is one indexable unit however
many things it says.

The obvious fix, splitting them, was wrong. Splitting is irreversible and the
grouping is information: a record gathering five findings under one
investigation is asserting they belong together. Indexing sections separately
took reachability to 82% without touching a single record.

That change then introduced its own bias, which is the next lesson.

## 8. Adding index rows advantages whoever has more of them

After sections were indexed, long records had 19.6 index rows each against
short records' 2.5, one with 48. A record with 48 chances to match outranks a
record with one, whatever it is about. Five of one collection's six failures
were exactly that.

A main-row match means the record **is** about the query. A section match means
one part of it **mentions** the query. Both should surface the record; only the
first should win a close contest. A small discount on section matches fixed it
and improved every measure at once.

## 9. Your first pass of any heuristic mostly measures itself

Across the reconciliation of this archive, the health checks flagged **29
items and found 4 real defects.** The other 25 were the detectors being wrong
in seven distinct ways: containment scoring that rewarded short summaries,
metadata blocks in two spellings, correction words appearing in ordinary
prose, staleness words that were domain vocabulary, and so on.

This is not an argument against the checks. The four they found included
summaries stating claims their own bodies had retracted, which nothing else
would have surfaced. It is an argument for reading the flagged record before
acting, and for expecting the first instinct to be that the check is wrong.

## 10. A migration that is not idempotent cannot be trusted

Re-running the migration rewrote 18 of 118 records every time, because records
without a timestamp fell back to "now". The archive churned when no source had
changed, which makes "did anything change?" unanswerable, and that is the only
question a scheduled re-sync exists to ask.

Related: a partial re-sync is worse than none. Refresh three collections of
four and search keeps working, validation keeps passing, and the answers
quietly describe last week.

## 11. Instrumentation that measures itself is worse than none

`lore doctor` issues one search per record and `lore eval` one per query.
Both were writing to the retrieval log. A single doctor run would have added
293 entries to an archive with a handful of real searches, so usage statistics
would have looked rich and described nothing but tooling.

Diagnostic traffic is now excluded. If you add a feature that searches, check
what it logs.

## 12. A check that reports zero may just be broken

Every health check here was falsified by planting a case it should catch and
confirming it does, then removing it and confirming the count returns. A clean
report from an unfalsified check is not evidence.

The same discipline applies to the privacy guarantee on `lore metrics`:
rather than documenting that exports contain no content, the export audits
itself and refuses to write if any string value is not a version, a date, a
platform name or a schema value.
