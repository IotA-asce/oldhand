---
schema_version: 1
id: synthetic_migrations_are_explicit
type: decision
status: current
importance: high
scope: repository
risk: high
durability: long_lived
evidence: documented
topics: [database, migrations, deployment]
created_at: 2026-09-18T00:00:00+00:00
updated_at: 2026-09-18T00:00:00+00:00
expires_at: null
relations: {}
---

# Synthetic: production schema changes use explicit migrations

## Summary

The application must not create or alter production database tables during
startup; reviewed migration jobs own schema changes.

## Knowledge

Startup-time DDL races across replicas and bypasses the deployment review
boundary. The fictional service waits for the migration job before serving
traffic.

## Verification

Documented architecture decision in this synthetic corpus.
