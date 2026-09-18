# README with soul — implementation plan

## Goal

Rewrite the repository README as a truthful, visual, end-to-end introduction to Oldhand: what it remembers, how it works, what has been measured, and where its limits are.

## Work

1. Audit the CLI, repository structure, published metrics, lessons, and existing visuals so every claim is traceable to the codebase.
2. Add a source-controlled discovery-replay diagram that explains the experience loop introduced in Oldhand 0.5.0.
3. Replace the README wholesale with a narrative that covers the promise, quick start, daily workflow, replay loop, evidence, architecture, safety, privacy, CLI, record format, development, and limitations.
4. Clearly separate observed archive metrics from controlled experiments and state the single-archive evidence limitation next to the numbers.
5. Validate diagram XML/SVG, local README links, formatting, and the clean-checkout verifier; visually inspect the new diagram.
6. Commit on the dedicated branch, merge into `main`, and push both refs.

## Acceptance criteria

- The first screen explains Oldhand in plain language and includes a meaningful visual.
- Commands and repository paths match the current 0.5.0 implementation.
- All numerical claims agree with `METRICS.md` or `LESSONS.md` and are labeled by evidence type.
- The discovery replay architecture is available as editable draw.io source and rendered SVG.
- Local links resolve and the full verifier passes from a clean checkout.
