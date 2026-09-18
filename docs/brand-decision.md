# Public identity decision

**Status:** decided — `oldhand`  
**Owner:** repository owner  
**Decision date:** 2026-09-19

This document is a decision record and checklist, not a legal opinion.
The public name has been chosen; the trademark item below is still open
and must be closed before the name is used commercially or defended.

## Product position to preserve

> Git-tracked institutional memory for coding agents: reviewed constraints,
> decisions, failed approaches, and operational hazards stored as readable
> Markdown and retrieved locally.

This position distinguishes the product from automatic activity capture and
task trackers. The public identity must support it without implying an
affiliation with another project.

## Collision evidence

The following names were checked on **2026-09-18**. Each resolves to an
existing PyPI project, so none is available as this project's PyPI
distribution name.

| Candidate / normalized name | Evidence | Why it matters |
| --- | --- | --- |
| `lore` | [PyPI: lore](https://pypi.org/project/lore/) describes a machine-learning framework and documents `pip install lore`. | The obvious package and command name are already associated with another Python project. |
| `lore-memory` / `lore_memory` | [PyPI: lore-memory](https://pypi.org/project/lore-memory/) describes AI memory for coding agents, local SQLite/FTS5, and `pip install lore-memory`. | This is a direct category and messaging collision; PyPI normalizes hyphens and underscores. |
| `lore-cli` / `lore_cli` | [PyPI: lore-cli](https://pypi.org/project/lore-cli/) describes a local AI-powered codebase-intelligence CLI and exposes `lore` commands. | This is both a developer-tool and command-name collision. |

These observations establish practical naming risk, not trademark rights,
likelihood of confusion, or a legal conclusion. Re-check availability on the
day a candidate is selected; package registrations and third-party products
can change.

## Decision template

Fill in one row per shortlisted candidate. Keep rejected candidates so a
future contributor can see why they were not chosen.

| Field | Candidate A | Candidate B | Candidate C |
| --- | --- | --- | --- |
| Public product name | [pending] | [pending] | [pending] |
| Repository owner/slug | [pending] | [pending] | [pending] |
| PyPI distribution name | [pending] | [pending] | [pending] |
| Console command | [pending] | [pending] | [pending] |
| Python import package | [pending] | [pending] | [pending] |
| Homebrew formula name | [pending] | [pending] | [pending] |
| Primary domain | [pending] | [pending] | [pending] |
| Search/confusion notes | [pending] | [pending] | [pending] |
| Legal-review status | [pending] | [pending] | [pending] |
| Decision | [pending] | [pending] | [pending] |

### Required decision record

- **Chosen public identity:** Oldhand
- **Chosen package distribution:** `oldhand`
- **Chosen command:** `oldhand`
- **Chosen import package:** `oldhand`
- **Chosen repository slug and primary domain:** `IotA-asce/oldhand`; no
  domain registered yet.
- **Decision rationale:** "An old hand" is the experienced colleague who
  remembers why the strange-looking code must stay — the product's actual
  position. Every candidate that kept "Lore" collided on PyPI with
  `lore`, `lore-memory` (a direct category and messaging competitor) or
  `lore-cli`, so the obvious install command could not be offered and search
  results would have led users to a competitor. `oldhand` is free on PyPI,
  Homebrew and npm, and returns no colliding developer tool.
- **Approver:** repository owner
- **Date:** 2026-09-19

### Availability evidence for the chosen name

Checked 2026-09-19.

| Namespace | Result | How checked |
| --- | --- | --- |
| PyPI `oldhand` | available | `GET https://pypi.org/pypi/oldhand/json` returned 404 |
| Homebrew core | no formula | `GET https://formulae.brew.sh/api/formula/oldhand.json` returned 404 |
| npm `oldhand` | available | `GET https://registry.npmjs.org/oldhand` returned 404 |
| GitHub `IotA-asce/oldhand` | controlled by the owner | repository slug under the owner's account |
| GitHub user/org `oldhand` | taken | not required; the repository lives under `IotA-asce` |

**Trademark review has not been done.** These checks establish practical
namespace availability on the date shown. They are not a trademark search,
a clearance opinion, or a registration. Complete the trademark item in the
checklist below before using the name commercially or defending it.

## Availability and confusion checklist

For the selected identity, record the URL searched, result, checker, and
date. “Available” means checked at that time only; it is not a reservation or
legal clearance.

- [ ] **GitHub slug:** the intended owner/repository path is available or
  controlled by the project owner.
- [ ] **PyPI normalized name:** checked using the candidate's normalized form
  (case-insensitive; `-`, `_`, and `.` normalize together). Confirm it does
  not resolve to an existing project and can be registered by the intended
  publisher.
- [ ] **Console command:** checked against installed/common commands and web
  search; no material user-facing collision found.
- [ ] **Python import package:** checked on PyPI and in the Python package
  namespace; does not shadow an existing dependency likely to be installed
  with Lore.
- [ ] **Homebrew:** searched `homebrew/core` and relevant third-party taps for
  formula and cask conflicts.
- [ ] **Domain:** checked registration and existing use for the intended
  primary domain; acquisition and renewal ownership are recorded separately.
- [ ] **Trademark review:** qualified counsel or the responsible organization
  has reviewed relevant jurisdictions, classes, and confusingly similar
  marks. Record the scope and date; do not label a name “cleared” without that
  review.
- [ ] **Search-result review:** search the candidate alongside “AI memory”,
  “coding agent”, “developer tool”, and “Python”; record confusing results and
  the mitigation or rejection decision.
- [ ] **Identity consistency:** product name, repository slug, distribution,
  command, import package, documentation, screenshots, and release metadata
  are mapped in the release checklist before publication.

## Exit criteria

The naming gate is complete only when an approver has selected an identity,
the checklist has dated evidence, and packaging/release work uses the same
distribution name, command, and import package.

**Met on 2026-09-19.** The identity is `oldhand`; the distribution name,
console command and import package are all `oldhand`, verified by installing
the built wheel into a clean environment and running the console script.

One item remains open and is deliberately not claimed: no trademark review
has been performed.
