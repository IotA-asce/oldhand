# Five iteration improvements

The executable plan is maintained at
`docs/plans/2026-09-17-five-iteration-improvements.md`.

This is a standard task: additive CLI behavior, tests, command documentation,
and a repository README rewrite. It does not change the record schema, ranking
weights, index schema, or canonical Markdown storage model.

Acceptance criteria:

- search supports exact type and topic filters;
- search and show support stable JSON documents;
- records can be browsed without a search query;
- existing human-readable output and retrieval logging remain compatible;
- the README is fully rewritten and uses both product diagrams and measured charts;
- the full clean-checkout verifier passes.
