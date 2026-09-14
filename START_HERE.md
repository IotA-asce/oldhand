# Start here

Lore is what a team knows about a system that never made it into the
documentation: the constraint nobody wrote down, the approach that looks
obvious and fails, the reason something surprising is the way it is.

It is expensive to acquire and normally lost when the session ends. This keeps
it as Markdown, ranks it so the piece that matters surfaces when its subject
comes up, and retires it when it stops being true.

## Five minutes

```bash
python -m pip install -r tools/lore/requirements.txt
python tools/lore/lore.py rebuild
python tools/lore/lore.py search "my consumer test passed but nothing ran"
```

The last command finds a record whose title shares almost no words with the
question. That is the whole product.

Then make it a real command, because every example below reads `lore <verb>`:

```bash
python tools/install.py /path/to/your/archive
```

That puts a `lore` launcher on your PATH and sets `LORE_ROOT` to your archive,
so you never type either path again. It is reversible with `--uninstall` and
touches nothing else. See `INSTALL.md` for the manual equivalent, and for why
the short command matters more than it sounds: the gap between `lore search`
and a forty-character invocation is most of what decides whether anyone
searches on a hunch, and searching on a hunch is the behaviour the whole
system depends on.

---

## What goes where

| State | Home | Answers |
|---|---|---|
| Operating rules | `AGENTS.md`, `agent/` | how should work be done here |
| Current task state | `implement/` | what am I doing right now |
| Durable knowledge | `memory/` | what should I know before touching this |
| Current system truth | `documentation/` | how does it work today |
| What actually changed | Git, CI, tickets | which commit, which build |

Only the third is Lore's. The separation is the point: documentation goes
stale because it describes a moving target; memory does not, because it
describes what was learned.

## The gate

Most work should produce no record at all.

> Would forgetting this make someone repeat an expensive discovery, violate a
> non-obvious constraint, misunderstand business behaviour, repeat a failed
> approach, or lose an important rationale?

If Git, tests or current documentation already preserve it cheaply, they will
do it better and stay current for free. A routine bug fix leaves nothing
behind.

When the answer is yes, create the record with the tool rather than by hand:

```bash
lore new --type constraint --importance high --topics "kafka,testing" \
         --title "A rejected message still commits its offset"
```

It generates the id, timestamps, file location and required headings, so you
supply only the knowledge. Hand-written frontmatter was the main source of
records that failed validation and therefore never became searchable.

**Then read `WRITING_RECORDS.md`.** It is short, and it is where the quality
actually comes from: retrieval tracked summary quality far more closely than
it tracked anything in the ranker.

## Retrieval

```bash
lore search "why did the consumer test pass without running"
lore show <id>
lore search --history "the old authentication mechanism"
```

Search returns a few ranked summaries, not documents: about 500 tokens, cheap
enough to reach for on a hunch. Open a record only once a summary has earned
it.

Three things worth knowing about the ranking:

- **Recency has no authority.** A two-year-old invariant outranks last week's
  debugging note when both match. This is deliberate, and the opposite of most
  memory systems.
- **Metadata breaks ties, it does not decide.** Every label combined is worth
  less than textual relevance, because a label on everything ranks nothing.
- **Sections are indexed too**, so a question about a long record's fourth
  finding still reaches it. Do not split records because they got long.

Retired records are excluded by default and reachable with `--history`.

## Keeping it healthy

```bash
lore doctor       # can every record be found by its own subject?
lore conflicts    # does anything contradict itself or another record?
lore stats        # size, distribution, critical share
lore usage        # what has retrieval actually done?
lore eval         # score against questions with known answers
```

Nothing here changes a record. All of it is advisory and some of it is wrong:
on the archive these were built against, 29 flagged items contained 4 real
defects. Read the record before acting on the report.

`lore selftest` asserts the ranking invariants and fails if a scoring change
breaks one. Run it in CI if you change anything.

## Importance is a budget

`critical` means missing this record will probably break something. It does
not mean the finding was hard-won.

Measured: recall fell from 92% to 33% once a quarter of records carried a
`critical` label. Expect single digits as a share of the archive. When torn
between two levels, take the lower one.

## Adopting it with notes you already have

```bash
python tools/migrate/from_markdown.py ~/notes /path/to/archive
```

works on any folder of Markdown. Claude Code memory and per-entry directory
layouts have their own scripts; see `tools/migrate/`.

Read **`RECONCILING_AN_EXISTING_ARCHIVE.md`** before trusting a migrated
result. Two archives merged into one index will contradict each other, because
they drifted apart while nothing compared them, and those contradictions only
become a retrieval problem once they share a ranking.

The order that works:

1. migrate one to one, splitting and merging nothing;
2. `lore validate` until clean;
3. `lore doctor`, fixing thin and unfindable records first;
4. `lore conflicts`;
5. `lore eval --save baseline`, last, so the baseline measures a coherent
   archive rather than a contradictory one.

## Measuring, and sharing what you measure

Any `lore` command writes one anonymous health snapshot per day to
`metrics/daily.jsonl`. It costs nothing and it is the only way to answer
whether the archive is earning its keep.

```bash
lore metrics                      # today, at a glance
lore metrics --full               # plus findability and eval
lore metrics --export mine.json   # a bundle safe to share
```

The export contains counts, rates and scores: no titles, ids, paths, queries,
topic names or collection names. It audits itself and refuses to write if any
string in it is not a version, a date, a platform name or a schema value. See
`METRICS.md`.

If you are trying Lore, sending that file back after a couple of weeks is the
most useful thing you can do for it. Every number in this repository came from
one archive.

## Two honest caveats

**Nothing makes anything search.** Retrieval depends on something choosing to
run it. If your agent never reaches for the archive, the archive is irrelevant
however good its ranking is. Give it a concrete trigger rather than a
judgement call: *search before non-trivial work, and whenever something is
surprising or looks like it has been hit before.* Asking someone to search
"when history might matter" asks them to suspect the trap before looking, and
the traps worth recording are the ones nobody suspects.

**`compact` and `supersede` are not implemented.** Nothing yet stops an archive
accumulating stale records at scale. `validate` catches a half-finished
retirement and `conflicts` finds contradictions, so the manual path works, but
this is the known gap.

## Harness adapters

`AGENTS.md` is the portable entry point; `CLAUDE.md` is a thin Claude Code
adapter. Other harnesses need only the smallest adapter that makes them
discover the canonical rules. Harness-specific configuration may accelerate
this workflow but must never be the only place a requirement exists.

## Further reading

- `INSTALL.md` : getting `lore` onto your PATH, and undoing it
- `WRITING_RECORDS.md` : how to write a record people can find
- `RECONCILING_AN_EXISTING_ARCHIVE.md` : merging notes you already have
- `MIGRATING_AN_ARCHIVE.md` : the phased adoption plan
- `LESSONS.md` : what building this taught us, and what it cost to learn
- `METRICS.md` : what is measured, and what is shared
- `tools/lore/CLI_SPEC.md` : every command, and why it behaves as it does
- `memory/SCHEMA.md` : the record format
