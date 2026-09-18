# Advanced replay: inspect a recorded search without rerunning it

Lore's discovery-replay feature is an offline analysis tool for a completed
engineering exploration. It is deliberately separate from durable Markdown
memory: a trace records attempts that happened; a person decides whether an
outcome deserves to be distilled into a reviewed record.

Use it when a task had several plausible approaches and you want to ask a
bounded question about the recorded history: under the same budget, in what
order would one of Lore's built-in policies have uncovered the successful
attempts?

It is not an agent runtime, an optimizer that writes its own policies, or a
claim that one small archive is a general benchmark.

## Record a discovery trace

Run these commands from an initialized Lore archive, using the checked-out CLI
until a packaged command is installed. The example creates one root attempt
and its continuation; root attempts may instead open several branches.

```bash
python tools/lore/lore.py run-start \
  --id config-loader-investigation \
  --task "Find why deployed configuration loses defaults" \
  --evaluator "config-regression-suite" \
  --policy manual \
  --goal maximize \
  --workers 2

python tools/lore/lore.py attempt-add config-loader-investigation \
  --id inspect-loader \
  --parent root \
  --proposal "Inspect replacement and merge behavior" \
  --artifact-ref examples/sample-project/config_loader.py

python tools/lore/lore.py attempt-evaluate config-loader-investigation inspect-loader \
  --score 4 --incorrect --outcome failure --cost 1 --duration-ms 120

python tools/lore/lore.py attempt-add config-loader-investigation \
  --id preserve-defaults \
  --parent inspect-loader \
  --proposal "Preserve defaults while applying an environment override"

python tools/lore/lore.py attempt-evaluate config-loader-investigation preserve-defaults \
  --score 9 --correct --outcome success --cost 2 --duration-ms 180

python tools/lore/lore.py run-finish config-loader-investigation
python tools/lore/lore.py run-validate config-loader-investigation
python tools/lore/lore.py run-show config-loader-investigation
```

Traces live at `experience/runs/<run-id>.json`. The CLI records a fixed task,
evaluator name, score goal, worker limit, attempt proposals, and one grounded
evaluation per attempt. It refuses to finish a run with no attempts or pending
evaluations. `run-validate` checks the trace structure before replay.

The trace shape is intentionally constrained. The synthetic root can have
multiple children, representing alternative starting directions. Each non-root
attempt can have at most one recorded continuation. That makes a continuation
unambiguous when it is revealed during replay; it does not model every possible
search graph.

## Replay is deterministic and prefix-only

Replay does not execute an agent, test suite, or evaluator. It consumes the
completed trace and returns the attempts that would be revealed under one of
the bundled policies:

- `breadth` favors shallower available parents.
- `depth` favors deeper available parents.
- `score-greedy` favors a parent with the best already observed *correct*
  result, then depth.

```bash
python tools/lore/lore.py replay config-loader-investigation \
  --policy score-greedy --budget 2 --workers 2 --json
```

For a fixed valid trace and identical flags, output is deterministic. At each
round the policy can select only from parents whose prefix is already observed;
the replay environment then reveals the next recorded child for each selected
parent. It cannot inspect an unrevealed child, its score, correctness, or
continuation to choose a parent. The JSON result includes `decisions`,
`revealed`, `rounds`, `best_score`, `total_cost`, `parallelism`, and
`objective`, so the ordering can be audited.

`--budget` caps revealed attempts. `--workers` caps selections in a round and
defaults to the trace's recorded maximum. A run may therefore expose fewer
than its budget if its recorded branches are exhausted.

## Read the objective carefully

For a maximize trace, quality is the highest score among revealed correct
attempts. For a minimize trace, it is the negative of the lowest correct score
so that a larger objective remains better. The original-direction `best_score`
is still returned for inspection.

When there is a correct revealed attempt, the reported objective is:

```text
quality - beta_cost × recorded_cost + beta_parallel × attempts / rounds
```

Use `--beta-cost` and `--beta-parallel` only to make an explicit trade-off you
want to inspect:

```bash
python tools/lore/lore.py replay config-loader-investigation \
  --policy depth --budget 8 --beta-cost 0.25 --beta-parallel 0.10
```

The objective is `null` when no correct attempt has been revealed. Recorded
cost and duration are trace metadata, not independently measured resource
usage. The formula is a comparison aid for histories that share a meaningful
evaluator and score scale; it is not a universal quality metric, a benchmark,
or proof that a policy will perform the same way on a new task.

## Compare policies with a chronological holdout

`policy-compare` replays the incumbent plus requested candidates over completed
traces. If the archive contains multiple evaluator names, select exactly one;
Lore refuses to silently average them.

```bash
python tools/lore/lore.py policy-compare depth score-greedy \
  --incumbent breadth \
  --budget 8 \
  --holdout 1 \
  --evaluator config-regression-suite \
  --workers 2 \
  --beta-cost 0.25 \
  --beta-parallel 0.10 \
  --json
```

The newest `--holdout N` matching completed traces, ordered by `created_at`
then run id, form the holdout; older traces form the training group. A holdout
must leave at least one training trace. The output reports every replay result
and each group's mean objective. When a holdout exists, the printed and JSON
ordering uses its mean objective; otherwise it uses training.

This is a convenience split, not a controlled evaluation:

- It is chronological rather than randomized, and `created_at` is not the
  time an evaluation finished.
- Repeated or closely related tasks can still make training and holdout
  dependent.
- The comparison does not normalize score scales or enforce a common score
  goal across traces. Keep an evaluator's task family and score semantics
  comparable, and run separate comparisons when they are not.
- A small or synthetic archive can show a useful local signal, but cannot
  establish general policy superiority.

Most importantly, comparison is read-only. Lore does **not** rewrite a policy,
switch an incumbent, promote a candidate, or change a future agent's behavior.
Treat the result as evidence for a human review decision.

## Carry forward only reviewed learning

Replay is an advanced supplement to durable engineering memory. Inspect an
evaluated node and, if it captures a reusable constraint, decision, lesson, or
hazard, create a normal Lore record with a trace reference:

```bash
python tools/lore/lore.py run-distill config-loader-investigation preserve-defaults \
  --title "Environment overrides must preserve configuration defaults" \
  --type constraint \
  --importance high \
  --topics "configuration,deployment" \
  --dry-run
```

`run-distill` requires a completed run and an evaluated attempt. It generates a
normal record proposal; review it, remove `--dry-run` only when it is accurate,
then rebuild or validate the archive as usual. This human boundary keeps raw
exploration from becoming unreviewed institutional memory.

For the command reference, see [the CLI specification](../tools/lore/CLI_SPEC.md).
