---
schema_version: 1
id: synthetic_config_replaces_defaults
type: constraint
status: current
importance: critical
scope: repository
risk: critical
durability: invariant
evidence: verified
topics: [config, deployment]
created_at: 2026-09-18T00:00:00+00:00
updated_at: 2026-09-18T00:00:00+00:00
expires_at: null
relations: {}
---

# Synthetic: environment configuration replaces defaults

## Summary

An environment configuration is a complete reviewed replacement, not a merge
with shared defaults.

## Knowledge

The fictional deployment renderer consumes exactly one document. When staging
configuration exists, it replaces the defaults document. A merge would let
unreviewed defaults reach a deployment and hide omitted settings.

## Verification

Verified in this fictional fixture by rendering each document independently.
