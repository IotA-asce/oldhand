# Reconciling an existing archive

If you are adopting Lore you almost certainly have notes already: a memory
directory, a wiki, per-repository records, or all three. Migrating them is the
easy half. The half that decides whether the result is trustworthy is finding
where they **disagree**.

They will disagree. Knowledge written down twice in two places drifts apart
independently, because nothing was ever comparing them. A correction applied
in one archive does not reach the other. A record gets a "CORRECTED" section
at the bottom while its summary keeps stating the claim that was corrected.
Two repositories each record the same CI failure and reach different
conclusions a month apart.

None of this is visible while the archives are separate. All of it becomes a
retrieval problem the moment they share one index, because search returns the
confident stale record exactly as readily as the correct one.

Run this after migrating and before trusting anything:

```bash
lore conflicts
```

## What it finds

### 1. The summary does not carry the correction

The body corrects an earlier claim and the summary still states the old one.

This is the worst of the three and the least visible. Search ranks and
displays summaries, so the correction only exists for someone who opens the
record, and an agent that reads the summary and moves on gets the superseded
answer with no indication anything is wrong. It looks exactly like a confident
correct answer.

On the archive this tool was built against, 11 of 293 records were in this
state, including one whose summary still stated a rule the author had
retracted in writing three weeks earlier.

**Fix by hand.** Rewrite the summary so it leads with what is true now. Only
you know which sentence still holds.

### 2. Declared stale, still marked current

The record announces that it is superseded or outdated, and its `status` is
still `current`, so it keeps ranking as live knowledge.

**Fix by hand, after reading it.** See the warning below: this class looks
automatable and is not.

**A note on why this check is fussy.** It requires the announcement, not the
word: capitals, at the start of a line, dated or introduced. Matching the word
alone is useless in an engineering archive, because *the vocabulary of
staleness is the domain vocabulary*. Contracts supersede each other, packages
are deprecated, models become outdated, and the records describing those
things say so on every line. Three separate false positives on a real archive
came from exactly this, including a C# enum value (`ContractStatus.Superseded`)
and an adjective ("the superseded push-registration model"). Code spans are
stripped before matching for the same reason: an identifier is never a claim
about the record containing it.

### 3. Near-duplicate subjects

Two records covering the same subject, flagged by vocabulary overlap on title
and summary. Pairs that cross collections are marked, because those are the
usual result of merging archives that were maintained separately.

For each pair, one of three things is true, and only a person can say which:
they agree and should merge; one supersedes the other; or they genuinely
differ and the overlap is coincidental. Merging is usually right, and the
merged record should keep both provenance trails.

## Recording what you decide

A migration gets re-run: weekly during a trial, and again whenever a source
changes. Anything decided *about* the migrated records rather than written in
the sources is destroyed on every run, including every answer you just gave to
`lore conflicts`.

Losing those silently is worse than never recording them, because the report
comes back clean the first time and full the next, and nothing distinguishes
reconsidered from reverted.

Put resolutions in `reconcile.jsonl` at the archive root. Every migration
applies it:

```jsonl
{"id": "lore_x", "relations": {"related_to": ["lore_y"]}, "note": "finding <-> fix"}
{"id": "lore_x", "status": "superseded", "note": "replaced by lore_y"}
```

`note` is for whoever reads the file in six months and is not written into the
record. Comment lines starting with `#` are ignored, so the file can explain
itself.

Linking also closes the question: `lore conflicts` does not report a pair that
carries a relation, so the next run shows what is still open rather than
everything ever detected. That is the point of writing the decision down.

Prefer linking to merging. Two records that cover one subject from different
angles, a finding and the fix for it, usually both deserve to exist; merging
buries the reusable half inside the specific one. Merge when one record says
nothing the other does not.

## Why none of this is applied automatically

An earlier version of this command auto-retired records whose text announced
they were stale. It seemed obviously safe: the record had already made the
decision and the metadata had simply not caught up.

Measured against a real archive, it was **wrong on two of its four
candidates**:

- one summary read `OUTDATED HEADLINE, KEPT FOR THE HISTORY`, a record
  deliberately preserved because the failure it describes is instructive;
- another read `SUPERSEDED ... Still true: no MCP tool covers releases`, where
  the headline had aged but the method underneath was still the only one that
  worked.

Retiring either would have removed working knowledge from every default search
without saying so. That is the precise failure a memory system exists to
prevent, and it would have been caused by the tool meant to improve it.

The distinction between "announces staleness" and "should be retired" is
authorial intent, and no pattern recovers it. So `lore conflicts` finds and
explains; a person decides. A counter-signal check suppresses the obvious
keep-me cases so the report stays worth reading, but that is a filter on the
report, not a licence to act on it.

This is the general shape of the rule: **automate detection, never
resolution.** Detection that is wrong costs you a minute of reading. Resolution
that is wrong costs you knowledge, silently, and you find out months later when
an agent confidently repeats a mistake you already solved.

## Getting your notes in

Three migrations ship, in `tools/migrate/`:

| script | source shape |
|---|---|
| `from_markdown.py` | any folder of Markdown notes |
| `from_claude_memory.py` | a Claude Code project-memory directory |
| `from_repo_memory.py` | one directory per entry, with `SUMMARY.md` |

`from_markdown.py` is the one most people want. It assumes only that the files
are Markdown: frontmatter is used where present and inferred where not, and
every inference is reported at the end, because a guess you cannot see is
worse than no guess.

```bash
python tools/migrate/from_markdown.py ~/notes /path/to/archive
```

Everything arrives as `importance: normal`, deliberately. A migration that
handed out `critical` on keyword matches would destroy retrieval before the
archive was a day old; see the budget rule below. Raise records later, one at
a time, once they have proven they matter.

**Consider not migrating at all.** Ten records you write deliberately will
teach you more about whether this suits you than three hundred converted ones,
and the writing is the part that decides quality. An archive you migrated is
also an archive you have never read.

## Suggested order when adopting Lore

1. Migrate everything, one to one. Do not split, merge or retire anything
   during the migration; a migration that also edits cannot be verified.
2. `lore validate` until it passes.
3. `lore doctor`. Fix thin summaries and unfindable records first: a record
   nothing can retrieve cannot contradict anything, it is simply absent.
4. `lore conflicts`. Work through class 1, then 2, then 3.
5. `lore eval --save baseline` only once the above is clean, so your baseline
   measures a coherent archive rather than a contradictory one.

Step 5 matters more than it looks. A baseline taken over an archive that still
contradicts itself bakes the contradictions into the number you spend the next
month trying to beat.
