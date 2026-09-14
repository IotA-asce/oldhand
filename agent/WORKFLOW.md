# Engineering Workflow

## Principle

Use the cheapest process that preserves the required engineering quality.

## Standard sequence

1. Understand the request and affected ownership boundary.
2. Classify the task using `TASK_CLASSES.md`.
3. Inspect relevant source and current documentation.
4. Search memory only if prior decisions, failures, migrations, incidents, or rationale
   could materially affect the task.
5. Plan at the depth required by the task class.
6. Implement in small coherent phases.
7. Verify changed behavior at the lowest faithful layer first.
8. Expand verification according to risk and scope.
9. Update current documentation when system truth changed.
10. Apply the memory-worthiness gate from `MEMORY_POLICY.md`.
11. Finish with a truthful statement of what was and was not verified.

Implementation persistence is encouraged. Architectural authority is not unlimited:
if completing the task requires violating a documented invariant, changing product
semantics, weakening a safety boundary, or silently changing scope, stop that path and
surface the conflict rather than routing around it.
