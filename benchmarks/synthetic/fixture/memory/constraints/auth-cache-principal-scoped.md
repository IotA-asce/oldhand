---
schema_version: 1
id: synthetic_auth_cache_is_principal_scoped
type: constraint
status: current
importance: critical
scope: subsystem
risk: critical
durability: invariant
evidence: verified
topics: [authorization, cache, security]
created_at: 2026-09-18T00:00:00+00:00
updated_at: 2026-09-18T00:00:00+00:00
expires_at: null
relations: {}
---

# Synthetic: authorization cache entries are principal scoped

## Summary

An authorization cache key must include the authenticated principal and the
resource; never reuse a decision across users.

## Knowledge

The fictional authorization service can cache a permit decision only for the
same principal, resource, action, and policy revision. A shared response cache
would leak permission between users.

## Verification

Verified by the synthetic cross-user access test.
