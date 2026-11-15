"""Offline writing guidance shipped with the package, never indexed as memory."""

GUIDES = {
    "writing": """Writing a useful record

Record knowledge only when forgetting it would repeat an expensive discovery,
violate a non-obvious constraint, repeat a failed approach, or lose a rationale.
It is fine to record nothing. Prefer code, tests or current documentation when
they already preserve the fact cheaply.

Write the Summary for the future question: state the finding and its consequence,
not a date, branch name or list of work performed. In Knowledge, explain the scope,
evidence, affected behavior and limits. In Verification, name the actual checks
and results; distinguish observed behavior from inference. Add source references
without copying credentials or confidential payloads. Review the generated skeleton
before treating it as established knowledge. Run oldhand validate after edits.
""",
    "vocabulary": """Use the words a future searcher will know

Name the symptom, component and identifiers someone would search for, rather than
only an internal project nickname. Include an exact error or API name when it is
relevant and safe to retain. Explain an acronym once. A title and Summary should
identify the subject without requiring the reader to open another record.

Use existing topic vocabulary when it fits: oldhand topics lists the indexed
terms. Do not stuff keywords or repeat boilerplate across every Summary. Test
retrieval with a plausible task-specific question using oldhand search, then open
the source with oldhand show before relying on it. Search rankings are evidence
to inspect, not proof that a claim is correct or current.
""",
    "importance": """Choose importance by the cost of forgetting

Use normal for most durable knowledge. Use high for a non-obvious constraint or
expensive failure that would materially harm future work if missed. Reserve
critical for exceptional, well-supported constraints with a severe consequence;
it is a retrieval budget, not praise for a project or task.

Separate importance from evidence, risk and durability. A high-impact hypothesis
is still a hypothesis; record its uncertainty and verification needs. Revisit an
importance label when scope or evidence changes. Prefer a clear subject and
Summary over boosting importance to compensate for poor retrieval wording.
""",
    "lifecycle": """Try a disposable create, find and retire walkthrough

These commands use a new local directory, not your production archive:

oldhand init ./guide-memory
oldhand --root ./guide-memory new --id guide-example --title "Fixture cache invalidation" --type lesson --importance normal --topics fixture-cache --summary "Fixture cache entries must be invalidated when their source changes."
oldhand --root ./guide-memory search "fixture cache"
oldhand --root ./guide-memory show guide-example
oldhand --root ./guide-memory status guide-example historical
oldhand --root ./guide-memory search --history "fixture cache"

Review and complete the record's Knowledge and Verification before keeping it.
Retire outdated knowledge rather than deleting its history: use historical when
it remains useful context, deprecated when it should no longer guide work, and
resolved for a finished incident. If a replacement exists, use oldhand supersede
OLD_ID --by NEW_ID. Inspect both records and verify current evidence first.
""",
    "exclusions": """What to leave out of memory

Do not record credentials, access tokens, private keys or raw sensitive payloads.
Do not create a record for every commit, routine test pass, status update or
transcript. Current implementation facts belong in code and current docs unless
a non-obvious constraint or rationale would otherwise be lost.

Do not elevate an agent's guess into a verified fact, silently rewrite history,
or copy an entire document when a concise finding plus reference is enough.
Preserve uncertainty and owner decisions. Skip records whose future value is
unclear; an archive can become harder to search when routine summaries compete
with the few findings that prevent expensive mistakes.
""",
}


def render_guide(topic: str | None = None) -> str:
    if topic is not None:
        return GUIDES[topic].strip()
    return "Offline Oldhand guides\n\n" + "\n".join(
        f"oldhand guide {name} — {content.splitlines()[0]}"
        for name, content in GUIDES.items()
    )
