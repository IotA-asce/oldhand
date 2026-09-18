---
schema_version: 1
id: synthetic_feature_flag_retirement
type: lesson
status: current
importance: normal
scope: feature
risk: medium
durability: situational
evidence: observed
topics: [feature-flags, rollout, cleanup]
created_at: 2026-09-18T00:00:00+00:00
updated_at: 2026-09-18T00:00:00+00:00
expires_at: null
relations: {}
---

# Synthetic: retire a feature flag only after its rollback window

## Summary

Remove a completed feature flag only after the rollout is stable and the
published rollback window has expired.

## Knowledge

The fictional release process keeps a flag available through the rollback
window even at one hundred percent rollout. Deleting it earlier turns an
operational rollback into a code deployment.

## Verification

Observed in the fictional rollout exercise.
